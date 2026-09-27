"""iter_018 실행 진입점: qa_run.OUT(=qa_requests.OUT)이 모듈 import 시 QA_RUN_ROOT 환경변수로 정해지므로,
그 값을 이번 실행 경로(results/iter_018)로 고정한 뒤 qa_run.main()에 위임한다. qa_run/qa_gen 자체는 수정하지 않는다.
사용: python -m rsna_diag.cx18_run --stage d16_plain --ckpts M0 --protocol P --workers 1 --gpus 0 --peak-gb 12 ...
     (인자는 qa_run과 동일하게 그대로 전달된다)
"""
import os

os.environ["QA_RUN_ROOT"] = "results/iter_018"

from . import qa_run  # noqa: E402  (환경변수 설정 이후에 import해야 qa_requests.OUT이 올바르게 바인딩된다)

if __name__ == "__main__":
    qa_run.main()
