"""기술 실측 뒤 admission 추정만 갱신. 잠긴 생성·평가 코드/조건은 그대로 사용."""
import argparse
import math
from pathlib import Path
import mr129_control as C
import mr129_tests as T
from mr128_data import read,save,sha,utc


def execute(action):
    C.verify_lock()
    results=[read(p) for p in (C.OUT/'gen/tech').glob('*.result.json')]
    maximum=max(v for r in results for v in r['peak_gpu_total_mib'].values())
    estimate=math.ceil(maximum/100)*100+100
    protocol=dict(created_utc=utc(),source_sha256=sha(__file__),technical_peak_total_mib=maximum,
        peak_estimate_mib=estimate,rounding_rule='ceil(observed GPU total peak/100)*100+100MiB',
        per_worker_safety_mib=2048,scientific_conditions_changed=False,
        initial_admission_failure_ko='10,000MiB 추정+worker별2GiB 합계가 현재 GPU0 여유를 57MiB 초과해 child 없이 거부됐다.',
        initial_source_lock_sha256=sha(C.OUT/'evaluation_lock_v2.json'))
    if not (C.OUT/'memory_pilot_protocol.json').exists():
        save(C.OUT/'memory_pilot_protocol.json',protocol)
        save(C.OUT/'memory_pilot_source.json',dict(source=Path(__file__).read_text(),sha256=sha(__file__)))
    else:
        old=read(C.OUT/'memory_pilot_protocol.json')
        if old['source_sha256']!=sha(__file__) or old['peak_estimate_mib']!=estimate:raise ValueError('memory pilot config changed')
    original=C.run
    # 동일 공개 run API의 resource 인자만 연결한다. 원 runtime 검사와 생성 함수를 모두 실행한다.
    def run(stage,req,pause=None,workers=2,peak=10000,max_new=512):
        return original(stage,req,pause=pause,workers=workers,peak=estimate if workers==4 else peak,max_new=max_new)
    C.run=run
    try:
        if action=='runtime':T.runtime()
        elif action=='main':C.main_generation()
    finally:C.run=original


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['runtime','main']);a=ap.parse_args();execute(a.action)
