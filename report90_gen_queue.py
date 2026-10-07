"""완료된 epoch의 고정 validation 요청을 두 GPU에 독립 배정한다."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from report90_numeric import OUT
from report86_common import save,sha

def main(epoch,skip_base=False,external_base_gpu=None):
    root=OUT/f'validation/epoch{epoch}';root.mkdir(parents=True,exist_ok=True)
    jobs=[]
    if epoch==2 and not skip_base:jobs.append(dict(name='base_report',requests=str(OUT/'data/V32/requests.json'),checkpoint=None))
    for lr in (0.0001,0.0002):
        for mode in ('R','G'):
            name=f'{mode}_lr{lr:g}';run=OUT/'train'/name;comp=json.loads((run/f'complete_{epoch:02}.json').read_text())
            ck=run/f'checkpoint_{epoch*64:06}.pt';assert sha(ck)==comp['checkpoint_sha']
            for subset,kind in [('V32','report'),('V16','ground')]:jobs.append(dict(name=f'{name}_{kind}',requests=str(OUT/f'data/{subset}/requests.json'),checkpoint=str(ck)))
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert external_base_gpu is None or (skip_base and epoch==2 and external_base_gpu in allowed)
    with (root/'queue.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        attempt=len(list(root.glob('queue_result_*.json')));active={};done=[];logs=[];start=time.monotonic()
        save(root/f'queue_protocol_{attempt}.json',dict(jobs=jobs,epoch=epoch,source_sha=sha(__file__),workers_per_gpu=1,external_base_gpu=external_base_gpu,reason='D8 long generation peak11232MiB plus worker2GiB forbids two/GPU'))
        def stop(*args):raise KeyboardInterrupt('stopping owned generation supervisors')
        signal.signal(signal.SIGTERM,stop)
        try:
            while jobs or active:
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,memory.used','--format=csv,noheader,nounits'],text=True)
                free={r.split(',')[0].strip():int(r.split(',')[1]) for r in raw.splitlines()}
                if external_base_gpu is not None and (root/'base_report/completion.json').exists():
                    import report90_gen_safe as safe
                    stage=root/'base_report';proto=json.loads((stage/'protocol.json').read_text())
                    rr,ee=safe.verify(stage,OUT/'data/V32/requests.json',proto,1);assert len(rr)==len(ee)==32
                    external_base_gpu=None
                for g in sorted(allowed,key=lambda x:free[x],reverse=True):
                    if g==external_base_gpu or g in active or not jobs or free[g]<12000+2048:continue
                    job=jobs.pop(0);out=root/job['name']
                    cmd=[sys.executable,'report90_gen_safe.py','launch','--requests',job['requests'],'--out',str(out),'--workers','1','--peak-mib','12000']
                    if job['checkpoint']:cmd+=['--checkpoint',job['checkpoint']]
                    env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=g
                    so=(root/f'{job["name"]}_{attempt}.stdout.log').open('x');se=(root/f'{job["name"]}_{attempt}.stderr.log').open('x');logs.extend([so,se])
                    p=subprocess.Popen(cmd,env=env,stdout=so,stderr=se);active[g]=(dict(job,gpu=g,cmd=cmd,start=time.time()),p)
                    print(json.dumps(dict(start=job['name'],gpu=g,pid=p.pid)),flush=True)
                for g,(info,p) in list(active.items()):
                    if p.poll() is not None:
                        done.append(dict(info,rc=p.returncode,end=time.time()));del active[g];assert p.returncode==0,(info,p.returncode)
                if jobs or active:time.sleep(10)
        finally:
            for _,p in active.values():
                if p.poll() is None:p.terminate()
            for info,p in active.values():done.append(dict(info,rc=p.wait(),end=time.time()))
            for f in logs:f.close()
            save(root/f'queue_result_{attempt:03}.json',dict(done=done,pending=jobs,wall_s=time.monotonic()-start))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,choices=[2,6],required=True);p.add_argument('--skip-base',action='store_true');p.add_argument('--external-base-gpu');a=p.parse_args();main(a.epoch,a.skip_base,a.external_base_gpu)
