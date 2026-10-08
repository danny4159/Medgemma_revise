"""iter_097: LR 2e-5 직접 판독(R)/조건부 위치 보조(G) 학습. 기존 report90 trainer의 연산은 그대로 두고
결과·cache·gate 경로와 허용 LR만 iter_097로 격리한다. 기존 trainer/config/결과는 수정하지 않는다."""
import argparse
import os
import subprocess
import report89_model as M
import report90_train as C
import report90_numeric as N
from report90_stable_v2 import apply

ORIGINAL=N.OUT
OUT=M.ROOT/'results/iter_097'
LR=2e-5

def environment(gpu):
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert gpu in allowed
    # report90_numeric.environment는 M.OUT을 iter_090으로 되돌리므로 cache 격리를 iter_097로 직접 지정한다.
    smi=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,memory.free','--format=csv,noheader,nounits'],text=True)
    row=next(x.split(', ') for x in smi.splitlines() if x.split(', ')[0]==gpu)
    assert float(row[-1])>=14.19*1024+2048+1024
    M.OUT=OUT
    mapping=M.environment(gpu);mapping.update(peak_basis_gib=14.19,worker_margin_mib=2048,context_margin_mib=1024)
    return mapping

C.OUT=OUT
C.environment=environment
C.apply=apply
C.SOURCES=C.SOURCES+['report90_stable_v2.py','report97_train.py']

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);p.add_argument('--run-dir',required=True)
    p.add_argument('--train',default=str(ORIGINAL/'data/T512/manifest.json'));p.add_argument('--validation',default=str(ORIGINAL/'data/V64/manifest.json'))
    p.add_argument('--mode',choices=['R','G'],required=True);p.add_argument('--lr',type=float,choices=[LR],required=True)
    p.add_argument('--mb',type=int,choices=[1],default=1);p.add_argument('--epochs',type=int,required=True)
    p.add_argument('--test-patients',type=int,default=0);p.add_argument('--stop-step',type=int,default=-1)
    return C.run(p.parse_args())

if __name__=='__main__':raise SystemExit(main())
