"""조건별 작업을 허용된 두 GPU에 배치하며 실패/종료를 감독한다."""
import argparse
import fcntl
import os
import json
import sys
import subprocess
import time
import signal
from i143_data import OUT
from i143_launch import smi
from i141_common import save,now,read,sha


def main():
    def interrupted(signum,frame): raise KeyboardInterrupt('supervisor signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    p=argparse.ArgumentParser(); p.add_argument('--epoch',type=int,choices=[8,16],default=8); a=p.parse_args()
    gate=read(OUT/'training_gate.json'); assert gate['passed'] is True
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(','); assert len(set(allowed))==len(allowed)
    d=OUT/'schedule'/f'epoch{a.epoch}_{time.time_ns()}'; d.mkdir(parents=True)
    fd=os.open(OUT/'schedule/owner.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    pending=['S','A','N']; children=[]; logs=[]; done=[]; start=time.monotonic()
    try:
        with (d/'resources.jsonl').open('x') as resource:
            while pending or any(c['process'].poll() is None for c in children):
                rows=smi(); occupied={c['gpu'] for c in children if c['process'].poll() is None}
                resource.write(json.dumps(dict(time=now(),gpu=rows,cpu_load=os.getloadavg()))+'\n'); resource.flush()
                for c in children:
                    if c['process'].poll() is None:
                        current=next(r for r in rows if r['index']==c['gpu'])
                        if int(current['free'])<2048:
                            save(d/(c['condition']+'_memory_stop.json'),dict(created_at=now(),gpu=current,
                                 owned_child=c['process'].pid,reason='실제 GPU 여유 2GiB 미만'))
                            raise RuntimeError('GPU 안전 여유 미달: '+c['condition'])
                for c in children:
                    rc=c['process'].poll()
                    if rc is not None and c['condition'] not in done:
                        save(d/(c['condition']+'_exit.json'),dict(returncode=rc,created_at=now(),seconds=time.monotonic()-c['start']))
                        if rc: raise RuntimeError('조건 실패: '+c['condition'])
                        done.append(c['condition'])
                candidates=sorted([r for r in rows if r['index'] in allowed and r['index'] not in occupied],key=lambda r:-int(r['free']))
                for r in candidates:
                    if not pending: break
                    if int(r['free'])<gate['training_reserved_mib']+2048: continue
                    cond=pending.pop(0); log=(d/(cond+'.log')).open('xb'); logs.append(log)
                    cmd=[sys.executable,'i143_train.py','--condition',cond,'--end-epoch',str(a.epoch)]
                    env=dict(os.environ,CUDA_VISIBLE_DEVICES=r['index'],HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4')
                    cp=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,pass_fds=(fd,))
                    children.append(dict(condition=cond,process=cp,gpu=r['index'],start=time.monotonic()))
                    save(d/(cond+'_launch.json'),dict(created_at=now(),command=cmd,physical_gpu=r,logical_gpu=0,pid=cp.pid,gate_sha256=sha(OUT/'training_gate.json')))
                    print('학습 배정',cond,r['index'],cp.pid,flush=True)
                if pending and not any(c['process'].poll() is None for c in children):
                    raise RuntimeError('현재 GPU 메모리 admission 미충족; 기존 작업 보존')
                time.sleep(5)
        assert all(c['process'].wait()==0 for c in children)
        save(d/'completion.json',dict(created_at=now(),conditions=done,seconds=time.monotonic()-start))
    finally:
        for c in children:
            if c['process'].poll() is None: c['process'].terminate()
        for c in children:
            try:c['process'].wait(timeout=30)
            except subprocess.TimeoutExpired:c['process'].kill();c['process'].wait()
        for log in logs:log.close()
        os.close(fd)

if __name__=='__main__':main()
