"""E16의 두 환자 shard를 각 허용 GPU에서 실행하고 정확한 16개 집합을 봉인한다."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from i143_data import OUT
from i143_launch import smi
from i143_confirm_shard import runtime_bound,partition
from i143_runtime import save
from i143_train import bound
from i141_common import read,sha,now,digest


def merge(stage,swap):
    runtime_bound(); bound(read(OUT/'training_gate.json'))
    d=OUT/'confirm_sharded'/stage; manifest=read(OUT/'data_manifest.json')['rows']; files={}; ids=[]
    for shard in (0,1):
        sd=d/f'shard{shard}'; request=read(sd/'request.json'); completion=read(sd/'completion.json')
        assert request['shard']==shard and request['swap']==swap
        assert stage==f'{request["condition"]}_epoch{request["epoch"]:02d}'+('_swap' if swap else '')
        assert request['selection_sha256']==sha(OUT/'selection.json')
        assert request['runtime_sha256']==sha(OUT/'confirm_runtime_protocol.json')
        assert completion['request_digest']==digest(request) and completion['n']==8
        expected={r['patient_id']:r for r in partition(manifest,swap,shard)}
        assert request['rows']==[dict(patient_id=r['patient_id'],image_source_patient=r.get('image_source_patient',r['patient_id']),
                                     image_hashes=[im['sha256'] for im in r['images']]) for r in expected.values()]
        assert {Path(p).name for p in completion['files']}=={p+'.json' for p in expected}
        assert {p.name for p in (sd/'outputs').glob('*.json')}=={p+'.json' for p in expected}
        for p,h in completion['files'].items():
            assert sha(p)==h; r=read(p)
            assert r['digest']==digest({k:v for k,v in r.items() if k!='digest'})
            assert r['condition']==request['condition'] and r['epoch']==request['epoch']
            assert r['provenance']['gate_sha256']==sha(OUT/'training_gate.json')
            row=expected[r['patient_id']]
            assert r['input_hashes']==[im['sha256'] for im in row['images']]
            assert r['image_source_patient']==row.get('image_source_patient',row['patient_id'])
            ids.append(r['patient_id']); files[p]=h
    assert len(ids)==len(set(ids))==16
    assert set(ids)=={r['patient_id'] for r in manifest if r['split']=='E'}
    result=dict(n=16,stage=stage,swap=swap,files=files,selection_sha256=sha(OUT/'selection.json'),
                runtime_sha256=sha(OUT/'confirm_runtime_protocol.json'))
    if (d/'completion.json').exists(): assert read(d/'completion.json')==result
    else: save(d/'completion.json',result)


def main():
    def interrupted(sig,frame): raise KeyboardInterrupt('supervisor signal '+str(sig))
    signal.signal(signal.SIGTERM,interrupted)
    runtime_bound(); gate=read(OUT/'training_gate.json'); bound(gate)
    selection=read(OUT/'selection.json'); assert selection['passed']
    root=OUT/'confirm_schedule'; root.mkdir(exist_ok=True)
    fd=os.open(root/'owner.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    d=root/str(time.time_ns()); d.mkdir(); allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    jobs=[(c,True,False) for c in ['S','A','N']]+[(c,False,False) for c in ['S','A','N']]+[(selection['swap_condition'],False,True)]
    start=time.monotonic(); children=[]; logs=[]
    try:
        with (d/'resources.jsonl').open('x') as resource:
            for condition,base,swap in jobs:
                epoch=0 if base else selection['epoch']; stage=f'{condition}_epoch{epoch:02d}'+('_swap' if swap else '')
                children=[]; pending=[0,1]; done=set()
                while pending or any(c['process'].poll() is None for c in children):
                    rows=smi(); resource.write(json.dumps(dict(created_at=now(),stage=stage,gpu=rows))+'\n'); resource.flush()
                    occupied={c['gpu'] for c in children if c['process'].poll() is None}
                    for c in children:
                        rc=c['process'].poll()
                        if rc is None:
                            assert int(next(r for r in rows if r['index']==c['gpu'])['free'])>=2048,'실제 GPU 여유 부족'
                        elif c['shard'] not in done:
                            save(d/f'{stage}_shard{c["shard"]}_exit.json',dict(returncode=rc,created_at=now()))
                            assert rc==0,(stage,c['shard'],rc)
                            done.add(c['shard'])
                    candidates=sorted((r for r in rows if r['index'] in allowed and r['index'] not in occupied),key=lambda r:-int(r['free']))
                    for gpu in candidates:
                        if not pending: break
                        if int(gpu['free'])<gate['training_reserved_mib']+2048: continue
                        shard=pending.pop(0); log=(d/f'{stage}_shard{shard}.log').open('xb'); logs.append(log)
                        cmd=[sys.executable,'i143_confirm_shard.py','--condition',condition,'--shard',str(shard)]
                        if base: cmd.append('--base')
                        if swap: cmd.append('--swap')
                        env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu['index'],HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4')
                        cp=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,pass_fds=(fd,))
                        children.append(dict(process=cp,gpu=gpu['index'],shard=shard))
                        save(d/f'{stage}_shard{shard}_launch.json',dict(created_at=now(),pid=cp.pid,command=cmd,physical_gpu=gpu,
                             logical_gpu=0,runtime_sha256=sha(OUT/'confirm_runtime_protocol.json')))
                        print(stage,shard,gpu['index'],cp.pid,flush=True)
                    if pending and not any(c['process'].poll() is None for c in children): raise RuntimeError('GPU admission 미충족')
                    time.sleep(5)
                assert all(c['process'].wait()==0 for c in children)
                merge(stage,swap)
        save(d/'completion.json',dict(created_at=now(),stages=7,requests=112,seconds=time.monotonic()-start))
    finally:
        for c in children:
            if c['process'].poll() is None: c['process'].terminate()
        for c in children:
            try:c['process'].wait(timeout=30)
            except subprocess.TimeoutExpired:c['process'].kill();c['process'].wait()
        for log in logs: log.close()
        os.close(fd)


if __name__=='__main__': main()
