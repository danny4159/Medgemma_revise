"""iter_097 V16 정답 문장 제공 grounding 보조 평가. 기존 recovery 평가기(report90_recovery_ground_eval)를 그대로 쓰되
iter_097 생성 stage의 protocol 코드 목록(report97_gen.py 포함)으로 검증한다."""
import argparse
import report90_gen as C
import report97_gen  # noqa: F401  SOURCES 패치
import report90_recovery_ground_eval as G
from report90_numeric import OUT as ORIGINAL

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--requests',default=str(ORIGINAL/'data/V16/requests.json'))
    p.add_argument('--manifest',default=str(ORIGINAL/'data/V16/manifest.json'));p.add_argument('--output',required=True)
    G.run(p.parse_args())
