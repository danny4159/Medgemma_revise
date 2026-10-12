"""잠긴 evaluator의 NumPy bool 저장만 Python scalar로 변환하는 한정 종료 경로."""
from pathlib import Path
import numpy as np
import mr129_control as C
from mr128_data import save,sha,utc


def scalar(value):
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:scalar(v) for k,v in value.items()}
    if isinstance(value,list):return [scalar(v) for v in value]
    if isinstance(value,tuple):return tuple(scalar(v) for v in value)
    return value


def main():
    C.verify_lock()
    save(C.OUT/'serialization_correction.json',dict(created_utc=utc(),source_sha256=sha(__file__),
         source=Path(__file__).read_text(),locked_evaluator_sha256=sha('mr129_eval.py'),
         original_error='TypeError: NumPy bool returned by independent() is not JSON serializable',
         correction='NumPy scalar.item()를 저장 직전에 적용. 산술·사건 정의·판정·잠긴 source는 변경 없음.',
         locked_code_unchanged=True,new_generation_requests=0,pre_generation_amendment=False))
    original=C.independent
    C.independent=lambda rows,report:scalar(original(rows,report))
    try:C.evaluate()
    finally:C.independent=original


if __name__=='__main__':main()
