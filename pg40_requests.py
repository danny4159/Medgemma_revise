"""iter_040 평가 요청 생성. iter_039 요청 행 중 cond==I-short만 그대로 재사용한다 (같은 prompt·영상·request_id).
V96/V48은 즉시 생성, H192는 decision artifact(run=true) 없이는 생성하지 않는다. 기존 파일은 덮어쓰지 않는다.

python pg40_requests.py val
python pg40_requests.py h192 --decision results/iter_040/decisions/h192_decision.json
"""
import argparse
import hashlib
import json
import os
import sys

import pg39_spec as S

OUT = "results/iter_040/requests"
EVAL_MANIFEST = "results/iter_040/data/manifest_eval_private.jsonl"
SRC = "results/iter_039/requests_v2/requests_{}.jsonl"


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def rows_for(kind, patients):
    rows = [json.loads(l) for l in open(SRC.format(kind))]
    out = [r for r in rows if r["cond"] == "I-short"]
    if {r["patient"] for r in out} != set(patients) or len(out) != 2 * len(patients):
        raise SystemExit("I-short request set != manifest patients x 2 sentences")
    for r in out:
        if r["targets"] not in (["qA"], ["qB"]) or S.sha(r["prompt"]) != r["prompt_sha256"]:
            raise SystemExit("row inconsistency")
    return out


def write(path, rows):
    if os.path.exists(path):
        sys.exit(f"exists: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)
    return sha_file(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["val", "h192"])
    ap.add_argument("--decision", default=None)
    a = ap.parse_args()
    man = [json.loads(l) for l in open(EVAL_MANIFEST)]
    if a.which == "val":
        v96 = [m for m in man if m["eval_set"] == "V96"]
        rows = rows_for("E96", [m["PatientID"] for m in v96])
        v48p = {m["PatientID"] for m in v96 if m["is_V48"]}
        print("V96", write(f"{OUT}/requests_V96.jsonl", rows), len(rows))
        r48 = [r for r in rows if r["patient"] in v48p]
        print("V48", write(f"{OUT}/requests_V48.jsonl", r48), len(r48))
    else:
        if not a.decision or json.load(open(a.decision)).get("run") is not True:
            sys.exit("H192 requests require a decision artifact with run=true")
        h = [m for m in man if m["eval_set"] == "H192"]
        rows = rows_for("E192", [m["PatientID"] for m in h])
        print("H192", write(f"{OUT}/requests_H192.jsonl", rows), len(rows))


if __name__ == "__main__":
    main()
