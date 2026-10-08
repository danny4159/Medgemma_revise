"""iter_097: 완료된 epoch checkpoint의 고정 V32(report)/V16(ground) 요청을 지정 GPU 하나에서 순차 생성한다.
checkpoint가 해당 epoch validation 기록(checkpoint_sha)과 일치할 때만 실행한다."""
import argparse
import json
import os
import subprocess
import sys
import time
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['R','G'],required=True);p.add_argument('--epoch',type=int,required=True)
    p.add_argument('--gpu',required=True);p.add_argument('--subsets',default='V32')
    a=p.parse_args()
    run=OUT/'train'/f'{a.mode}_lr2e-05';ck=run/f'checkpoint_{a.epoch*64:06}.pt';val=json.loads((run/f'validation_{a.epoch:02}.json').read_text())
    assert sha(ck)==val['checkpoint_sha']==json.loads(ck.with_suffix('.json').read_text())['sha256']
    root=OUT/f'validation/epoch{a.epoch}';root.mkdir(parents=True,exist_ok=True);results=[]
    for subset in a.subsets.split(','):
        kind={'V32':'report','V16':'ground'}[subset];name=f'{a.mode}_lr2e-05_{kind}';out=root/name
        cmd=[sys.executable,'report97_gen.py','launch','--requests',str(ORIGINAL/f'data/{subset}/requests.json'),'--out',str(out),'--workers','1','--peak-mib','12000','--checkpoint',str(ck)]
        env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=a.gpu;t=time.monotonic()
        with (root/f'{name}_{int(time.time())}.stdout.log').open('x') as so,(root/f'{name}_{int(time.time())}.stderr.log').open('x') as se:
            rc=subprocess.run(cmd,env=env,stdout=so,stderr=se).returncode
        results.append(dict(name=name,rc=rc,wall_s=time.monotonic()-t,gpu=a.gpu,cmd=cmd))
        print(json.dumps(results[-1]),flush=True);assert rc==0
    save(root/f'genq_{a.mode}_{int(time.time())}.json',dict(results=results,source_sha=sha(__file__)))

if __name__=='__main__':main()
