"""비영 LoRA 수치 경로 수정 뒤 별도 config/결과에서 동일 trainer를 실행한다."""
import argparse
import report90_train as C
from report90_stable_v2 import apply
ORIGINAL=C.OUT
C.OUT=ORIGINAL/'recovery'
C.apply=apply
C.SOURCES=C.SOURCES+['report90_stable_v2.py','report90_recovery_train.py']

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);p.add_argument('--run-dir',required=True)
    p.add_argument('--train',default=str(ORIGINAL/'data/T512/manifest.json'));p.add_argument('--validation',default=str(ORIGINAL/'data/V64/manifest.json'))
    p.add_argument('--mode',choices=['R','G'],required=True);p.add_argument('--lr',type=float,choices=[1e-4,2e-4],required=True)
    p.add_argument('--mb',type=int,choices=[1,2],default=1);p.add_argument('--epochs',type=int,required=True)
    p.add_argument('--test-patients',type=int,default=0);p.add_argument('--stop-step',type=int,default=-1)
    return C.run(p.parse_args())

if __name__=='__main__':raise SystemExit(main())
