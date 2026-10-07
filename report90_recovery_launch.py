"""두 허용 GPU에서 고정 R/G trajectory를 관리하고 모든 자식을 회수한다."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from report90_numeric import OUT as ORIGINAL
OUT=ORIGINAL/'recovery'
from report86_common import save,sha

def launch(epochs):
    root=OUT/f'launch/epoch{epochs}';root.mkdir(parents=True,exist_ok=True)
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert len(set(allowed))==len(allowed)
    jobs=[(mode,lr) for lr in (0.0001,0.0002) for mode in ('R','G')]
    if epochs>2:
        decision=json.loads((OUT/f'decisions/expand_epoch{epochs}.json').read_text());assert decision['expand']
        jobs=[tuple(x) for x in decision['jobs']]
    with (root/'owner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        attempt=len(list(root.glob('result_*.json')));active={};done=[];logs=[];started=time.monotonic()
        def stop(*args):raise KeyboardInterrupt('terminating owned training processes after current update')
        signal.signal(signal.SIGTERM,stop)
        try:
            while jobs or active:
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
                free={s.split(',')[0].strip():int(s.split(',')[2]) for s in raw.splitlines()}
                with (root/f'resources_{attempt}.jsonl').open('a') as f:f.write(json.dumps(dict(time=time.time(),smi=raw,pids={g:p.pid for g,(_,p) in active.items()}))+'\n')
                for g in sorted(allowed,key=lambda g:free[g],reverse=True):
                    if not jobs or g in active or free[g]<14.19*1024+2048+1024:continue
                    mode,lr=jobs.pop(0);name=f'{mode}_lr{lr:g}';run=OUT/'train'/name
                    cmd=[sys.executable,'report90_recovery_train.py','--gpu',g,'--run-dir',str(run),'--mode',mode,'--lr',str(lr),'--epochs',str(epochs)]
                    so=(root/f'{name}_{attempt}.stdout.log').open('x');se=(root/f'{name}_{attempt}.stderr.log').open('x');logs.extend([so,se])
                    p=subprocess.Popen(cmd,stdout=so,stderr=se);active[g]=(dict(name=name,gpu=g,cmd=cmd,start=time.time()),p)
                    print(json.dumps(dict(start=name,gpu=g,pid=p.pid)),flush=True)
                for g,(info,p) in list(active.items()):
                    rc=p.poll()
                    if rc is not None:
                        done.append(dict(info,rc=rc,end=time.time()));del active[g]
                        save(root/f'progress_{attempt}_{len(done)}.json',dict(done=done,pending=jobs))
                        assert rc==0,(info,rc)
                if jobs or active:time.sleep(15)
        finally:
            for _,p in active.values():
                if p.poll() is None:p.terminate()
            for info,p in active.values():done.append(dict(info,rc=p.wait(),end=time.time()))
            for f in logs:f.close()
            save(root/f'result_{attempt:03}.json',dict(done=done,pending=jobs,wall_s=time.monotonic()-started,source_sha=sha(__file__)))
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,choices=[2,6,12],required=True)
    raise SystemExit(launch(p.parse_args().epochs))
