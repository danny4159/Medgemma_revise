"""iter_015 처리량 pilot 보조: D36 요청에서 대표 48개(M0 QA 24[plain 12+json 12], B0 bbox 12, C bbox 12)를 고르고, 두 실행 구성의 출력을 대조한다.

사용: python -m rsna_diag.qa_pilot build | compare A_DIR B_DIR STAGE
- 선택은 D36 category 균형(4/4/4)의 앞쪽 요청 순서(hash 순 patient)로 고정한다. 정확도를 보고 고르지 않는다.
"""
import glob
import json
import os
import sys

from . import qa_gen, qa_requests as Q

OUT = Q.OUT


def load(stage_dir):
    recs = {}
    for f in glob.glob(f"{stage_dir}/gen_worker*.jsonl"):
        for r in qa_gen.read_strict(f):
            recs[r["request_id"]] = r
    return recs


def build():
    sets = json.load(open(f"{OUT}/manifests/sets.json"))
    d12 = {i for c in sets["D12"] for i in sets["D12"][c]}
    order = {i: k for k, i in enumerate([i for c in sets["D36"] for i in sets["D36"][c]])}
    sel = {"M0": [], "B0": [], "C": []}
    for fmt in ("plain", "json"):
        rows = [json.loads(ln) for ln in open(f"{OUT}/requests/d36_{fmt}__M0.jsonl")]
        rows = [r for r in rows if r["id"] in d12]  # D12 (category당 4명) x 2 target = 24 -> 12개씩
        rows.sort(key=lambda r: (order[r["id"]], r["target"]))
        sel["M0"] += rows[:12]
    for c in ("B0", "C"):
        sel[c] = [json.loads(ln) for ln in open(f"{OUT}/requests/d12_bbox__{c}.jsonl")]
    for c, rows in sel.items():
        p = f"{OUT}/requests/pilot48__{c}.jsonl"
        if os.path.exists(p):
            raise SystemExit(f"{p} exists")
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    print({c: len(r) for c, r in sel.items()}, "total", sum(len(r) for r in sel.values()))


def compare(a_dir, b_dir, stage):
    out = {"stage": stage, "ckpts": {}}
    ok = True
    for c in ("M0", "B0", "C"):
        A, B = load(f"{a_dir}/{stage}__{c}"), load(f"{b_dir}/{stage}__{c}")
        same_keys = set(A) == set(B)
        same_tokens = same_keys and all(A[k]["suffix_ids"] == B[k]["suffix_ids"] for k in A)
        out["ckpts"][c] = {"n_A": len(A), "n_B": len(B), "same_request_set": same_keys, "identical_greedy_tokens": same_tokens,
                           "n_token_mismatch": sum(A[k]["suffix_ids"] != B[k]["suffix_ids"] for k in A if k in B),
                           "wall_A": json.load(open(f"{a_dir}/{stage}__{c}/last_run.json"))["wall_s"],
                           "wall_B": json.load(open(f"{b_dir}/{stage}__{c}/last_run.json"))["wall_s"],
                           "peak_alloc_gb_max_A": max(r["peak_mem_alloc_gb_max"] for r in A.values()),
                           "peak_alloc_gb_max_B": max(r["peak_mem_alloc_gb_max"] for r in B.values()),
                           "max_runtime_s_A": max(r["runtime_s_total"] for r in A.values()),
                           "max_runtime_s_B": max(r["runtime_s_total"] for r in B.values())}
        ok &= same_tokens
    out["all_identical"] = ok
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        compare(*sys.argv[2:5])
