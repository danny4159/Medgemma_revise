"""고정 SynthSeg2.0 기술 실행. stage 잠금, GPU mapping, raw/volume/QC 검증 및 종료 보존."""
import argparse
import csv
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import nibabel as nib
import numpy as np
from mr127_select import read,save,sha,OUT
from mr127_assets import ROOT,SOURCE,ENVPY


def gpu_info():
    rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,memory.free','--format=csv,noheader,nounits'],text=True)
    return [dict(index=p[0].strip(),uuid=p[1].strip(),total_mib=int(p[2]),used_mib=int(p[3]),free_mib=int(p[4]))
            for p in csv.reader(rows.splitlines())]


def csv_result(p):
    with open(p) as f: rows=list(csv.reader(f))
    assert len(rows)==2 and len(rows[0])==len(rows[1]),(str(p),rows)
    out={k:float(v) for k,v in zip(rows[0][1:],rows[1][1:])}
    assert len(out)==len(rows[0])-1 and all(np.isfinite(list(out.values())))
    return out


def verify_result(directory):
    segmentation=nib.load(directory/'seg.nii.gz')
    vox=np.asarray(segmentation.dataobj)
    vol=csv_result(directory/'vol.csv'); qc=csv_result(directory/'qc.csv')
    keys=['left lateral ventricle','right lateral ventricle','total intracranial']
    assert all(k in vol and vol[k]>0 for k in keys), ('공식 부피 누락/0',vol)
    assert np.isfinite(vox).all() and np.any(vox) and np.isin(vox,[4,43]).any(), 'zero mask'
    assert np.allclose(segmentation.header.get_zooms()[:3],1,atol=1e-5)
    assert np.isfinite(segmentation.affine).all()
    assert all(0<=v<=1 for v in qc.values())
    return dict(volumes_mm3=vol,qc_scores=qc,S=(vol[keys[0]]+vol[keys[1]])/vol[keys[2]],
                foreground_voxels=int(np.count_nonzero(vox)),left_voxels=int(np.count_nonzero(vox==4)),
                right_voxels=int(np.count_nonzero(vox==43)),shape=list(vox.shape),affine=segmentation.affine.tolist(),
                artifacts={str(directory/n):sha(directory/n) for n in ['seg.nii.gz','vol.csv','qc.csv']})


def main(stage):
    out=Path('results/iter_127/seg')/stage
    out.mkdir(parents=True,exist_ok=True)
    assets=read('results/iter_127/assets.json')
    inp=read(OUT/'tech_inputs.json')
    assert inp['selection_sha256']==sha(OUT/'selection_lock.json')
    for p,h in assets['source_files'].items(): assert sha(p)==h,p
    for v in assets['weights'].values(): assert sha(v['path'])==v['sha256']
    allowed=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    assert len(allowed)==len(set(allowed)) and all(g.isdigit() for g in allowed)
    fs_mode=stage.startswith('fs_')
    fs_assets=read('results/iter_127/fs_assets.json') if fs_mode else None
    if fs_mode:
        for p,h in fs_assets['files'].items():assert sha(p)==h,p
    selected=['7ISDTZ2JVG','5SWPQWD3DD'] if stage.endswith('pilot') else [s for s in inp['inputs'] if s not in ['7ISDTZ2JVG','5SWPQWD3DD']]
    if stage.endswith('rest'):
        prior=read(f'results/iter_127/seg/{stage[:-4]+"pilot"}/completion.json')
        assert prior['status']=='complete' and prior['checks_passed']
        for p,h in prior['artifacts'].items(): assert sha(p)==h
    with (out/'stage.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        attempts=len(list(out.glob('launch_*.json')))
        tag=f'{attempts:03d}'
        cfg=dict(stage=stage,selected=selected,inputs_sha256=sha(OUT/'tech_inputs.json'),
                 assets_sha256=sha('results/iter_127/assets.json'),code={p:sha(p) for p in ['mr127_seg.py','mr127_seg_entry.py']},
                 official_flags=['--vol','--qc','--threads','4'],version='2.0 default',allowed_physical_gpus=allowed,
                 backend='FreeSurfer official' if fs_mode else 'UCL official',gpu_memory_limit_mib=20000,
                 fs_assets_sha256=sha('results/iter_127/fs_assets.json') if fs_mode else None,
                 mapping={str(i):g for i,g in enumerate(allowed)})
        save(out/f'launch_{tag}.json',cfg)
        pending=list(selected); active={}; done={}; failures={}; peaks={g:0 for g in allowed}
        t0=time.monotonic(); stopped=False
        def stop(sig,frame):
            nonlocal stopped
            stopped=True
            for p,_,_,_ in active.values(): p.terminate()
        old_handlers={s:signal.signal(s,stop) for s in [signal.SIGTERM,signal.SIGINT]}
        try:
            with (out/f'resources_{tag}.jsonl').open('x') as resources:
                while pending or active:
                    gpu=gpu_info()
                    resources.write(json.dumps(dict(time=time.time(),gpus=gpu))+'\n');resources.flush()
                    # pending 큐가 비어도 실행 중인 모든 GPU의 peak를 집계한다.
                    for g in gpu:
                        if g['index'] in peaks:
                            peaks[g['index']]=max(peaks[g['index']],g['used_mib'])
                    available=sorted([g for g in gpu if g['index'] in allowed],key=lambda g:g['free_mib'],reverse=True)
                    occupied={v[2] for v in active.values()}
                    for g in available:
                        if not pending or stopped: break
                        if g['index'] in occupied: continue
                        assert g['free_mib']>=20000, ('기술 실행 여유 부족',g)
                        s=pending.pop(0)
                        directory=ROOT/'seg'/stage/s/f'attempt_{tag}'
                        directory.mkdir(parents=True,exist_ok=False)
                        v=inp['inputs'][s]
                        for x in v['files'].values(): assert sha(x['path'])==x['sha256']
                        python=ROOT/'env_freesurfer/bin/python' if fs_mode else ENVPY
                        script=ROOT/'freesurfer/mri_synthseg.py' if fs_mode else SOURCE/'scripts/commands/SynthSeg_predict.py'
                        cmd=[str(python),str(Path('mr127_seg_entry.py').absolute()),str(script),
                             '--i',v['files']['img.nii.gz']['path'],'--o',str(directory/'seg.nii.gz'),
                             '--vol',str(directory/'vol.csv'),'--qc',str(directory/'qc.csv'),'--threads','4']
                        env=dict(os.environ,CUDA_VISIBLE_DEVICES=g['index'],TF_FORCE_GPU_ALLOW_GROWTH='true',
                                 TF_CPP_MIN_LOG_LEVEL='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',SYNTHSEG_GPU_LIMIT_MIB='20000')
                        if fs_mode:
                            cmd.append('--noaddctab')
                            env['FREESURFER_HOME']=str(ROOT/'freesurfer')
                            env['TF_USE_LEGACY_KERAS']='1'
                        libs=sorted(str(p) for p in ENVPY.parent.parent.glob('lib/python*/site-packages/nvidia/*/lib'))
                        env['LD_LIBRARY_PATH']=':'.join(libs+[str(ENVPY.parent.parent/'lib')]+[env.get('LD_LIBRARY_PATH','')])
                        h=(directory/'official.log').open('x')
                        save(directory/'execution.json',dict(command=cmd,physical_gpu=g['index'],logical_gpu_inside_child=0,
                             input=v,config=cfg,environment={k:env[k] for k in ['CUDA_VISIBLE_DEVICES','LD_LIBRARY_PATH','TF_FORCE_GPU_ALLOW_GROWTH']},
                             started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
                        p=subprocess.Popen(cmd,env=env,stdout=h,stderr=subprocess.STDOUT)
                        active[s]=(p,h,g['index'],directory)
                        print('started',s,'gpu',g['index'],'pid',p.pid,flush=True)
                    for s,(p,h,g,directory) in list(active.items()):
                        rc=p.poll()
                        if rc is None: continue
                        h.close()
                        try:
                            assert rc==0, f'official rc={rc}'
                            result=verify_result(directory)
                            done[s]=dict(**result,gpu=g,returncode=rc,directory=str(directory))
                            save(directory/'verified.json',done[s])
                            print('verified',s,flush=True)
                        except Exception as e:
                            failures[s]=dict(returncode=rc,error=str(e),directory=str(directory))
                            print('failed',s,str(e)[:300],flush=True)
                        del active[s]
                    if failures or stopped:
                        pending=[]
                        for p,_,_,_ in active.values(): p.terminate()
                    if active: time.sleep(2)
        finally:
            for p,h,_,_ in active.values():
                if p.poll() is None: p.terminate()
                p.wait(); h.close()
            for s,handler in old_handlers.items(): signal.signal(s,handler)
        result=dict(status='complete' if set(done)==set(selected) and not failures else 'failed',checks_passed=not failures and set(done)==set(selected),
             results=done,failures=failures,expected_studies=selected,peak_gpu_total_mib=peaks,wall_s=time.monotonic()-t0,
             config=cfg,artifacts={str(out/f'launch_{tag}.json'):sha(out/f'launch_{tag}.json')})
        for v in done.values(): result['artifacts'].update(v['artifacts'])
        save(out/'completion.json',result)
        return 0 if result['checks_passed'] else 2


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','rest','fs_pilot','fs_rest','fs_recovery_pilot','fs_recovery_rest','fs_compat_pilot','fs_compat_rest']);a=ap.parse_args()
    raise SystemExit(main(a.stage))
