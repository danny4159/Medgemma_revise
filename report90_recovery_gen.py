"""고정 LoRA 행 연산을 학습과 생성에 공통 적용한다."""
import argparse
import report90_gen_safe as S
from report90_recovery_train import C as T
from report86_common import sha
C=S.C
C.load_model=T.load_model
C.SOURCES=C.SOURCES+["report90_stable_v2.py","report90_recovery_train.py","report90_recovery_gen.py"]
C.__file__=__file__
protocol=C.protocol
verify=S.verify
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("command",choices=["worker","launch"]);p.add_argument("--requests",required=True);p.add_argument("--out",required=True)
    p.add_argument("--checkpoint");p.add_argument("--workers",type=int,default=2);p.add_argument("--shard",type=int,default=0);p.add_argument("--gpu");p.add_argument("--limit",type=int,default=0);p.add_argument("--peak-mib",type=int,default=12000)
    a=p.parse_args();raise SystemExit(C.worker(a) if a.command=="worker" else S.launch(a))
