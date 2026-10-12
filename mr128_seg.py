"""iter128 고정 FreeSurfer SynthSeg2.0: manifest 기반 감독·실패 보존·검증 재개."""
import argparse
import csv
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

import nibabel as nib
import numpy as np
from mr128_data import OUT, ROOT, read, save, sha, verify_files, utc
from mr127_seg import gpu_info

FS = ROOT.parent/'iter127/freesurfer'
PYTHON = ROOT.parent/'iter127/env_freesurfer/bin/python'
LIMIT = 20000
RESERVE = 2048
QC = ['general white matter','general grey matter','general csf','cerebellum','brainstem','thalamus','putamen+pallidum','hippocampus+amygdala']


def csv_values(p, required=None):
    with open(p,newline='') as f: rows=list(csv.reader(f))
    if len(rows)!=2 or len(rows[0])!=len(rows[1]) or rows[1][0]!='img': raise ValueError(f'CSV target/schema: {p}')
    header=rows[0][1:]
    if not header or len(set(header))!=len(header): raise ValueError('missing/duplicate CSV columns')
    if required is not None and header!=required: raise ValueError(f'QC schema mismatch: {header}')
    vals={k:float(v) for k,v in zip(header,rows[1][1:])}
    if not np.isfinite(list(vals.values())).all(): raise ValueError('nonfinite CSV')
    return vals


def verify_result(directory):
    vol=csv_values(directory/'vol.csv'); qc=csv_values(directory/'qc.csv',QC)
    names=['left lateral ventricle','right lateral ventricle','total intracranial']
    if any(k not in vol or vol[k]<=0 for k in names): raise ValueError(f'nonpositive official volume: { {k:vol.get(k) for k in names} }')
    if not all(0<=v<=1 for v in qc.values()): raise ValueError('QC out of range')
    seg=nib.load(directory/'seg.nii.gz'); a=np.asarray(seg.dataobj)
    if len(a.shape)!=3 or not np.isfinite(a).all() or not np.isfinite(seg.affine).all() or abs(np.linalg.det(seg.affine[:3,:3]))<1e-8: raise ValueError('seg grid')
    if not np.allclose(seg.header.get_zooms()[:3],1,atol=1e-5): raise ValueError('not 1mm')
    counts={str(k):int((a==k).sum()) for k in [4,43]}
    if not all(counts.values()): raise ValueError(f'missing left/right hard mask: {counts}')
    return dict(volumes_mm3=vol,qc_scores=qc,S=(vol[names[0]]+vol[names[1]])/vol[names[2]],
         foreground_voxels=int(np.count_nonzero(a)),ventricle_voxels=counts,
         shape=list(a.shape),affine=seg.affine.tolist(),
         artifacts={str(directory/n):sha(directory/n) for n in ['seg.nii.gz','vol.csv','qc.csv','official.log']})


def main(input_path,stage):
    fs_assets=read('results/iter_127/fs_assets.json'); verify_files(fs_assets['files'])
    inputs=read(input_path)
    if inputs['protocol_sha256']!=sha(OUT/'protocol.json'): raise ValueError('protocol changed')
    if stage!='tech':
        from mr128_remaining import tech_gate
        tech_gate()
        all_inputs=read(OUT/'all_inputs.json')['inputs']
        tech_inputs=read(OUT/'tech_inputs.json')['inputs']
        if set(inputs['inputs'])!=set(all_inputs)-set(tech_inputs):raise ValueError('fixed remaining52 set')
    verify_files({v['path']:v['sha256'] for c in inputs['inputs'].values() for v in c['files'].values()})
    allowed=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    if len(set(allowed))!=len(allowed) or not all(g.isdigit() for g in allowed): raise ValueError('allowed GPU set')
    cfg=dict(input_sha256=sha(input_path),assets_sha256=sha('results/iter_127/fs_assets.json'),
         environment_sha256=sha('results/iter_127/environment_record.json'),
         code={p:sha(p) for p in ['mr128_seg.py','mr128_data.py','mr127_seg.py','mr127_seg_entry.py','mr128_seg_entry.py']},
         official_flags=['--vol','--qc','--threads','4','--noaddctab'],version='SynthSeg2.0 default',
         gpu_limit_mib=LIMIT,reserve_per_worker_mib=RESERVE,allowed_physical_gpus=allowed,
         qc_required=QC,expected_studies=sorted(inputs['inputs']))
    directory=OUT/'seg'/stage; directory.mkdir(parents=True,exist_ok=True)
    with (directory/'stage.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (directory/'config.json').exists():
            if read(directory/'config.json')!=cfg: raise ValueError('stale stage config')
        else: save(directory/'config.json',cfg)
        done={}; pending=[]; prior_failures={}
        for study in sorted(inputs['inputs']):
            p=directory/(study+'.complete.json')
            if p.exists():
                c=read(p)
                if c['config_sha256']!=sha(directory/'config.json'): raise ValueError('stale completion')
                verify_files(c['result']['artifacts']); verify_result(Path(c['directory']))
                if stage!='tech':
                    timing=read(directory/(study+'.timing.json'))
                    if timing['answer_sha256']!=sha(p):raise ValueError('stale timing answer')
                done[study]=c
            elif (directory/(study+'.failure.json')).exists():
                c=read(directory/(study+'.failure.json'))
                if c['config_sha256']!=sha(directory/'config.json'):raise ValueError('stale failed result')
                prior_failures[study]=c
            else: pending.append(study)
        tag=uuid.uuid4().hex; active={}; failures=dict(prior_failures); peak={g:0 for g in allowed}; minfree={g:99999 for g in allowed}; stopped=False
        t0=time.monotonic()
        def stop(signum,frame):
            nonlocal stopped
            stopped=True
            for a in active.values(): a['process'].terminate()
        handlers={s:signal.signal(s,stop) for s in [signal.SIGTERM,signal.SIGINT]}
        log=directory/(tag+'.resources.jsonl')
        with log.open('x') as resource:
            try:
                while pending or active:
                    gs=gpu_info()
                    resource.write(__import__('json').dumps(dict(utc=utc(),gpus=gs))+'\n'); resource.flush()
                    for g in gs:
                        if g['index'] in peak:
                            peak[g['index']]=max(peak[g['index']],g['used_mib']); minfree[g['index']]=min(minfree[g['index']],g['free_mib'])
                    occupied={a['gpu'] for a in active.values()}
                    for g in sorted(gs,key=lambda g:g['free_mib'],reverse=True):
                        if stopped or (stage=='tech' and failures) or not pending: break
                        if g['index'] not in allowed or g['index'] in occupied: continue
                        # TF limit에 worker당 2GiB와 device 외부 할당 256MiB를 추가한다.
                        if g['free_mib']<LIMIT+RESERVE+256: continue
                        study=pending.pop(0); c=inputs['inputs'][study]
                        target=ROOT/'seg'/stage/study/tag; target.mkdir(parents=True,exist_ok=False)
                        entry='mr127_seg_entry.py' if stage=='tech' else 'mr128_seg_entry.py'
                        cmd=[str(PYTHON),str(Path(entry).absolute()),str(FS/'mri_synthseg.py'),
                             '--i',c['files']['img.nii.gz']['path'],'--o',str(target/'seg.nii.gz'),
                             '--vol',str(target/'vol.csv'),'--qc',str(target/'qc.csv'),'--threads','4','--noaddctab']
                        env=dict(os.environ,CUDA_VISIBLE_DEVICES=g['index'],FREESURFER_HOME=str(FS),
                             TF_USE_LEGACY_KERAS='1',TF_FORCE_GPU_ALLOW_GROWTH='true',SYNTHSEG_GPU_LIMIT_MIB=str(LIMIT),
                             TF_CPP_MIN_LOG_LEVEL='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
                        base=Path('results/environments/synthseg125').absolute()
                        libs=sorted(str(p) for p in base.glob('lib/python*/site-packages/nvidia/*/lib'))
                        env['LD_LIBRARY_PATH']=':'.join(libs+[str(base/'lib'),env.get('LD_LIBRARY_PATH','')])
                        save(target/'execution.json',dict(command=cmd,started_utc=utc(),physical_gpu=g['index'],logical_gpu=0,
                             admission=g,input=c,config_sha256=sha(directory/'config.json'),
                             environment={k:env[k] for k in ['CUDA_VISIBLE_DEVICES','FREESURFER_HOME','TF_USE_LEGACY_KERAS','LD_LIBRARY_PATH']}))
                        h=(target/'official.log').open('x'); proc=subprocess.Popen(cmd,env=env,stdout=h,stderr=subprocess.STDOUT)
                        active[study]=dict(process=proc,handle=h,gpu=g['index'],directory=target,start=time.monotonic())
                        occupied.add(g['index']); print('started',study,'GPU',g['index'],'pid',proc.pid,flush=True)
                    if pending and not active and not failures and not stopped:
                        failures['admission']=dict(error='허용 GPU의 limit+2GiB+외부256MiB 여유 부족',gpus=gs)
                    for study,a in list(active.items()):
                        rc=a['process'].poll()
                        if rc is None: continue
                        a['handle'].close()
                        try:
                            if rc!=0: raise ValueError(f'official exit {rc}')
                            result=verify_result(a['directory'])
                            timing=[]
                            if stage!='tech':
                                lines=(a['directory']/'official.log').read_text().splitlines()
                                timing=[__import__('json').loads(s.split(' ',1)[1]) for s in lines if s.startswith('SYNTHSEG_TIMING ')]
                                if len(timing)!=1 or 'warm_start_monotonic' not in timing[0]:raise ValueError('missing warm boundary')
                            c=dict(config_sha256=sha(directory/'config.json'),result=result,returncode=rc,
                                  directory=str(a['directory']),physical_gpu=a['gpu'],wall_s=time.monotonic()-a['start'])
                            save(directory/(study+'.complete.json'),c)
                            answer_end=time.monotonic()
                            if stage!='tech':
                                save(directory/(study+'.timing.json'),dict(official=timing[0],answer_saved_monotonic=answer_end,
                                     warm_raw_read_to_S_answer_saved_s=answer_end-timing[0]['warm_start_monotonic'],
                                     cold_subprocess_to_S_answer_saved_s=answer_end-a['start'],
                                     answer_sha256=sha(directory/(study+'.complete.json'))))
                            done[study]=c; print('verified',study,flush=True)
                        except Exception as e:
                            failures[study]=dict(error=str(e),returncode=rc,directory=str(a['directory']),config_sha256=sha(directory/'config.json'))
                            save(directory/(study+'.failure.json'),failures[study])
                            print('failed',study,str(e),flush=True)
                        del active[study]
                    if (stage=='tech' and failures) or 'admission' in failures or stopped:
                        pending=[]
                        for a in active.values():
                            if a['process'].poll() is None: a['process'].terminate()
                    if active: time.sleep(1)
            finally:
                for a in active.values():
                    if a['process'].poll() is None: a['process'].terminate()
                    a['process'].wait(); a['handle'].close()
                for s,h in handlers.items(): signal.signal(s,h)
        ok=set(done)==set(inputs['inputs']) and not failures and not stopped
        save(directory/(tag+'.result.json'),dict(checks_passed=ok,status='complete' if ok else 'failed',
             done=done,failures=failures,stopped=stopped,peak_gpu_total_mib=peak,min_gpu_free_mib=minfree,
             wall_s=time.monotonic()-t0,resource_log=str(log),resource_sha256=sha(log),
             config_sha256=sha(directory/'config.json'),expected_studies=cfg['expected_studies']))
        print('stage complete',ok,'done',len(done),'wall',time.monotonic()-t0,flush=True)
        return 0 if ok else 2


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--inputs',default=str(OUT/'tech_inputs.json')); ap.add_argument('--stage',default='tech')
    a=ap.parse_args(); raise SystemExit(main(a.inputs,a.stage))
