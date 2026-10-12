"""iter_112 평가 코드·규칙 잠금. 잠금 시점에 scores 출력이 하나도 없음을 함께 기록한다. 덮어쓰기 금지."""
import hashlib
import json
import os
import sys
import time

FILES = ["mr112_spec.py", "mr112_data.py", "mr112_model.py", "mr112_run.py", "mr112_checks.py", "mr112_eval.py", "mr112_verify.py",
         "mr112_test_cpu.py", "results/iter_112/data/manifest.json", "results/iter_112/data/gt.json",
         "rsna_diag/metrics.py", "rsna_diag/geometry.py"]
OUT = "results/iter_112/lock/" + (sys.argv[1] if len(sys.argv) > 1 else "eval_lock.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT):
    sys.exit("exists")
sc = [p for p in (os.listdir("results/iter_112/scores") if os.path.isdir("results/iter_112/scores") else []) if p.endswith(".jsonl")]
lock = dict(locked_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"), epoch_s=time.time(), model_score_files_existing=sc,
            files={f: hashlib.sha256(open(f, "rb").read()).hexdigest() for f in FILES},
            rules=dict(error="max IoU(box, patient GT boxes) < 0.3 (GT 없으면 0)", K="ceil(0.25 N)", order="낮은 값부터; 동률 confidence↑, patient id, det_index",
                       positive="region−conf ≥ 5pp AND region−full ≥ 5pp AND confidence 대비 순이득 환자 ≥ 3", bootstrap="환자 cluster 10000, seed 112017, percentile 95%"))
json.dump(lock, open(OUT, "w"), indent=1)
print(lock["locked_at"], sc)
