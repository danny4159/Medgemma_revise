"""iter_042 stage driver. pg41_run의 protocol/launch/verify_completion을 쓰되 completion 존재만으로 건너뛰지 않는다.

python pg42_driver.py --kind E_C --name E_C --workers 4 [--peak-gb 9] [--gpus 0,1]
- 호출자가 요구한 모델(kind의 _M0/_C)과 protocol의 adapter digest를 대조한다 (M0는 adapter 없음, C는 고정 digest).
- protocol이 이미 있으면 새로 만들지 않고 요청 hash·잠금 파일과 대조한다(verify_protocol). completion이 있으면 launch하지 않고 verify_completion(현재 영상 hash 포함)만 수행한다.
- 평가 GT manifest·selection lock·평가/스펙 소스를 protocol 잠금에 넣는다.
"""
import argparse
import json
import os
import subprocess
import sys

import pg41_run as R

C_ADAPTER = "results/iter_040/train2/C_s17/epoch_03"
C_DIGEST = "419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8"
OUT = "results/iter_042"
LOCK = [f"{OUT}/data/manifest_private.jsonl", f"{OUT}/data/selection_lock.json", f"{OUT}/data/review_private.json",
        "pg42_spec.py", "pg42_data.py", "pg42_build.py", "pg42_driver.py"]  # 평가 소스는 결과 digest에 기록(pg42_eval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, help="D_M0 D_C E_M0 E_C")
    ap.add_argument("--name", required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--peak-gb", type=float, default=9.0)
    ap.add_argument("--gpus", default=None)
    ap.add_argument("--max-requests", type=int, default=None)
    a = ap.parse_args()
    model = a.kind.split("_")[1]
    if model not in ("M0", "C"):
        sys.exit("bad kind")
    req = f"{OUT}/requests/requests_{a.kind}.jsonl"
    out_dir = f"{OUT}/gen/{a.name}"
    proto = f"{OUT}/protocol/protocol_{a.name}.json"
    os.makedirs(f"{OUT}/protocol", exist_ok=True)
    lock = json.load(open(f"{OUT}/data/selection_lock.json"))
    if R.file_sha(req) != lock["request_files_sha256"][a.kind]:
        sys.exit("requests file != selection_lock")
    if not os.path.exists(proto):
        R.make_protocol(req, proto, adapter=C_ADAPTER if model == "C" else None, lock=LOCK)
    pdig, p = R.verify_protocol(proto, req)
    ad = (p.get("adapter") or {}).get("digest")
    if (model == "C" and ad != C_DIGEST) or (model == "M0" and ad is not None):
        sys.exit(f"protocol adapter {ad} does not match requested model {model}")
    if os.path.exists(os.path.join(out_dir, "completion.json")):
        recs = R.verify_completion(out_dir, req, proto)
        print(f"existing completion re-verified: {len(recs)} records")
        return
    cmd = [sys.executable, "pg41_run.py", "launch", "--requests", req, "--protocol", proto, "--out-dir", out_dir,
           "--workers", str(a.workers), "--peak-gb", str(a.peak_gb)]
    if a.gpus:
        cmd += ["--gpus", a.gpus]
    if a.max_requests is not None:
        cmd += ["--max-requests", str(a.max_requests)]
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit(f"launch rc={rc}")
    recs = R.verify_completion(out_dir, req, proto)
    print(f"completion verified: {len(recs)} records")


if __name__ == "__main__":
    main()
