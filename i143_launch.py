"""허용 GPU 안에서 여유순 배정하고 자식의 수명과 자원 로그를 보존한다."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
import json
import signal
from i143_data import OUT
from i141_common import save,now


def smi():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,memory.used','--format=csv,noheader,nounits'],text=True)
    return [dict(zip(['index','uuid','free','used'],[x.strip() for x in line.split(',')])) for line in raw.strip().splitlines()]


def main():
    def interrupted(signum,frame):
        raise KeyboardInterrupt('supervisor signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    p=argparse.ArgumentParser(); p.add_argument('--name',required=True); p.add_argument('command',nargs=argparse.REMAINDER); a=p.parse_args()
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(','); rows=[r for r in smi() if r['index'] in allowed]
    assert len(rows)==len(allowed); gpu=max(rows,key=lambda r:int(r['free']))
    assert int(gpu['free'])>22000,'기술 실측 전 충분한 메모리 필요'
    d=OUT/'launch'/a.name; d.mkdir(parents=True,exist_ok=False)
    fd=os.open(d/'owner.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu['index'],HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4')
    save(d/'start.json',dict(created_at=now(),command=a.command,allowed=allowed,physical_gpu=gpu,logical_gpu=0,python=sys.executable))
    child=None; start=time.monotonic()
    try:
        with (d/'output.log').open('xb') as log,(d/'resources.jsonl').open('x') as res:
            child=subprocess.Popen([sys.executable,*a.command],env=env,stdout=log,stderr=subprocess.STDOUT,pass_fds=(fd,))
            print(json.dumps(dict(pid=child.pid,supervisor=os.getpid(),gpu=gpu['index'],log=str(d/'output.log'))),flush=True)
            while child.poll() is None:
                current=smi()
                res.write(json.dumps(dict(time=now(),gpu=current,cpu_load=os.getloadavg()))+'\n'); res.flush()
                own=next(r for r in current if r['index']==gpu['index'])
                if int(own['free'])<2048:
                    save(d/'memory_stop.json',dict(created_at=now(),gpu=own,owned_child=child.pid,
                         reason='실제 GPU 여유 2GiB 미만. 현재 감독기의 자식만 중단.'))
                    child.terminate()
                    try: child.wait(timeout=30)
                    except subprocess.TimeoutExpired: child.kill(); child.wait()
                    break
                time.sleep(5)
            rc=child.wait()
        save(d/'result.json',dict(created_at=now(),returncode=rc,wall_s=time.monotonic()-start))
        sys.exit(rc)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=30)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        os.close(fd)

if __name__=='__main__': main()
