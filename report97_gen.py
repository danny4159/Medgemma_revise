"""iter_097: 기존 recovery 생성 연산(report90_recovery_gen)을 유지하고 출력·cache 경로만 iter_097로 격리한다.
parent와 worker subprocess 모두 이 파일을 진입점으로 쓰므로 OUT이 일관된다. (report94_gen.py와 동일 구조)"""
import argparse
from pathlib import Path
import report90_gen as C
import report90_gen_safe as S
import report90_recovery_gen as RG  # noqa: F401  load_model·SOURCES 패치 적용

OUT=Path(__file__).resolve().parent/'results/iter_097'
C.OUT=OUT
C.SOURCES=C.SOURCES+['report97_gen.py']
C.__file__=__file__

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','launch']);p.add_argument('--requests',required=True);p.add_argument('--out',required=True)
    p.add_argument('--checkpoint');p.add_argument('--workers',type=int,default=1);p.add_argument('--shard',type=int,default=0);p.add_argument('--gpu');p.add_argument('--limit',type=int,default=0);p.add_argument('--peak-mib',type=int,default=12000)
    a=p.parse_args();raise SystemExit(C.worker(a) if a.command=='worker' else S.launch(a))
