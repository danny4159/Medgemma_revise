"""iter_094: 선택 epoch1 R/G의 V32 판독 32건씩을 GPU 하나씩에 배정해 생성한다(supervisor)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from report86_common import sha,save

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/iter_094'
REQ=ROOT/'results/iter_090/data/V32/requests.json'
FINAL=json.loads((ROOT/'results/iter_090/recovery/selection/final.json').read_text())

def main():
    (OUT/'gen').mkdir(parents=True,exist_ok=True)
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],text=True)
    free={x.split(',')[0].strip():int(x.split(',')[2]) for x in raw.splitlines()}
    order=sorted(allowed,key=lambda g:free[g],reverse=True);assert len(order)>=2 and all(free[g]>=14048 for g in order[:2])
    procs=[];start=time.monotonic()
    for mode,g in zip(['R','G'],order):
        sel=FINAL['selected'][mode];assert sha(sel['checkpoint'])==sel['checkpoint_sha']
        out=OUT/'gen'/f'{mode}_epoch1';out.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=g
        cmd=[sys.executable,'report94_gen.py','launch','--requests',str(REQ),'--out',str(out),'--workers','1','--peak-mib','12000','--checkpoint',sel['checkpoint']]
        so=(OUT/'gen'/f'{mode}_epoch1_{int(time.time())}.stdout.log').open('x');se=(OUT/'gen'/f'{mode}_epoch1_{int(time.time())}.stderr.log').open('x')
        procs.append((mode,g,subprocess.Popen(cmd,env=env,stdout=so,stderr=se,cwd=ROOT)))
        print(json.dumps(dict(start=mode,gpu=g,free=free[g])),flush=True)
    codes={m:p.wait() for m,_,p in procs}
    save(OUT/f'gen/supervisor_{int(time.time())}.json',dict(codes=codes,gpus={m:g for m,g,_ in procs},wall_s=time.monotonic()-start))
    print(json.dumps(codes),flush=True)
    return 0 if all(c==0 for c in codes.values()) else 1

if __name__=='__main__':
    raise SystemExit(main())
