"""평가·분기 코드와 입력을 본생성 전에 잠근다 (실제 시각·digest 기록). 새 파일만 쓴다.
python ev108_lock.py results/iter_108/protocol/eval_lock.json"""
import json
import sys
import time
from pathlib import Path

import ev108_data as D

FILES = ["ev108_spec.py", "ev108_eval.py", "ev108_report.py", "ev108_data.py", "ev108_build.py",
         "test_ev108.py", "test_ev108_proc.py", "test_ev108_report_dry.py",
         "rsna_diag/qa_spec.py", "rsna_diag/generate.py", "rsna_diag/geometry.py",
         "results/iter_108/data/audit.json", "results/iter_108/data/geometry.json", "results/iter_108/data/stage_patients.json",
         "results/iter_108/data/requests_FREPRO.jsonl", "results/iter_108/data/requests_TECH.jsonl", "results/iter_108/data/requests_P180R.jsonl",
         "results/iter_108/data/requests_E600R.jsonl", "results/iter_108/tests/fixtures_cpu_v2.json", "results/iter_108/tests/proc_check.json",
         "results/iter_108/tests/dry_eval/report_P180.json"]


def main():
    out = Path(sys.argv[1])
    if out.exists():
        sys.exit(f"exists {out}")
    lock = {"locked_at_unix": time.time(), "locked_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "note": "평가·확대 분기·policy 계산·요청·입력을 multi-image 생성(D/T/C/L) 전에 잠금. 이 시점 이전 multi-image 출력은 없다.",
            "files": {f: D.file_sha(D.ROOT / f) for f in FILES},
            "inputs": {str(p.relative_to(D.ROOT)): D.file_sha(p) for p in D.LOCKED_INPUTS}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, indent=1))
    print(lock["locked_at"], len(lock["files"]))


if __name__ == "__main__":
    main()
