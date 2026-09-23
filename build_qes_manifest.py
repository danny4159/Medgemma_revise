"""iter_004 request manifest (CPU, label-free).

실행: python research/build_qes_manifest.py --out research/results/iter_004
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qes.data import build_config, build_requests, config_hash, fixed_subsets  # noqa: E402
from qes.store import write_json_atomic  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    cfg = build_config()
    reqs, info = build_requests(cfg=cfg)
    subsets = fixed_subsets(reqs)
    req_path = os.path.join(args.out, "requests.jsonl")
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reqs)
    if os.path.exists(req_path) and open(req_path).read() != body:
        raise SystemExit(f"{req_path} exists with different content; refusing to overwrite")
    with open(req_path, "w") as f:
        f.write(body)
    write_json_atomic(os.path.join(args.out, "config.json"), {**cfg, "config_sha256": config_hash(cfg)})
    write_json_atomic(os.path.join(args.out, "image_info.json"), info)
    write_json_atomic(os.path.join(args.out, "subsets.json"), subsets)
    kinds = {}
    for r in reqs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"requests={len(reqs)} images={len(info)} kinds={kinds} config={config_hash(cfg)[:12]}")
    print("calibration:", subsets["calibration"])
    print("verification:", subsets["verification"])


if __name__ == "__main__":
    main()
