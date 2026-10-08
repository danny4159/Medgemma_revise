"""iter_097 단일 trajectory supervisor: 가장 여유 있는 허용 GPU에 report97_train.py를 배정하고 자식을 회수한다.
SIGTERM이면 자식에게 전달해 현재 update 뒤 checkpoint를 저장하게 한다(exit75 = 정상 정지). 재실행하면 digest 검증 후 자동 재개."""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from report86_common import save,sha
from report97_train import OUT

def launch(mode,epochs,lr):
    name=f'{mode}_lr{lr:g}';root=OUT/'launch'/name;root.mkdir(parents=True,exist_ok=True)
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    with (root/'owner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        attempt=len(list(root.glob('result_*.json')));start=time.monotonic()
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,memory.used','--format=csv,noheader,nounits'],text=True)
        free={r.split(',')[0].strip():int(r.split(',')[1]) for r in raw.splitlines()}
        gpu=max(allowed,key=lambda g:free[g]);assert free[gpu]>=14.19*1024+2048+1024,('memory admission',free)
        run=OUT/'train'/name
        cmd=[sys.executable,'report97_train.py','--gpu',gpu,'--run-dir',str(run),'--mode',mode,'--lr',str(lr),'--epochs',str(epochs)]
        so=(root/f'stdout_{attempt}.log').open('x');se=(root/f'stderr_{attempt}.log').open('x')
        p=subprocess.Popen(cmd,stdout=so,stderr=se)
        save(root/f'start_{attempt}.json',dict(cmd=cmd,gpu=gpu,pid=p.pid,supervisor_pid=os.getpid(),free_mib=free,source_sha=sha(__file__)))
        print(json.dumps(dict(started=name,gpu=gpu,child_pid=p.pid,supervisor_pid=os.getpid())),flush=True)
        def stop(*a):
            if p.poll() is None:p.send_signal(signal.SIGTERM)
        signal.signal(signal.SIGTERM,stop)
        try:rc=p.wait()
        finally:
            if p.poll() is None:p.terminate();p.wait()
            so.close();se.close()
        save(root/f'result_{attempt:03}.json',dict(rc=rc,cmd=cmd,gpu=gpu,wall_s=time.monotonic()-start,source_sha=sha(__file__)))
        return rc

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['R','G'],required=True);p.add_argument('--epochs',type=int,default=6);p.add_argument('--lr',type=float,default=2e-5)
    a=p.parse_args();raise SystemExit(launch(a.mode,a.epochs,a.lr))
