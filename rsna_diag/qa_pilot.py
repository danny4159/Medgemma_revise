"""iter_016 처리량 pilot 보조. 표본은 category별로 먼저 고정한 뒤(qa_requests build --set D12 = category별 4명) 요청을 구성하므로 세 category가 빠지지 않는다.

사용: python -m rsna_diag.qa_pilot compare A_GEN_ROOT B_GEN_ROOT STAGE OUT_JSON
- 두 실행 구성(A, B)의 요청 집합·greedy token·parser 결과를 대조하고, 전체 wall-clock(모델 로딩 포함)과 생성 구간(요청별 runtime 합)을 분리해 보고한다.
"""
import glob
import json
import sys

from . import qa_gen, qa_requests as Q, qa_spec as S


def load(stage_dir):
    recs = {}
    for f in sorted(glob.glob(f"{stage_dir}/gen_worker*.jsonl")):
        for r in qa_gen.read_strict(f):
            if r["request_id"] in recs:
                raise qa_gen.QAError(f"duplicate request {r['request_id']} in {stage_dir}")
            recs[r["request_id"]] = r
    return recs


def category_coverage(stage_requests, labels):
    """요청 파일의 환자 category 분포 (평가용 label은 여기서만 읽는다)."""
    rows = [json.loads(ln) for ln in open(stage_requests) if ln.strip()]
    cnt = {}
    for r in rows:
        c = labels[r["id"]]["category"]
        cnt[c] = cnt.get(c, 0) + 1
    return cnt


def parse_map(recs, rows_by_id=None):
    return {k: S.parse_semantic(r["target"], r["fmt"], r["suffix_text_raw"], r["ended_eos"]) for k, r in recs.items()}


def compare(a_dir, b_dir, stage, ckpts=("M0", "B0", "C")):
    out = {"stage": stage, "ckpts": {}}
    ok = True
    tot = {"A": [0.0, 0.0, 0], "B": [0.0, 0.0, 0]}
    for c in ckpts:
        A, B = load(f"{a_dir}/{stage}__{c}"), load(f"{b_dir}/{stage}__{c}")
        same_keys = set(A) == set(B)
        same_tokens = same_keys and all(A[k]["suffix_ids"] == B[k]["suffix_ids"] for k in A)
        same_parse = same_keys and parse_map(A) == parse_map(B)
        wa = json.load(open(f"{a_dir}/{stage}__{c}/last_run.json"))["wall_s"]
        wb = json.load(open(f"{b_dir}/{stage}__{c}/last_run.json"))["wall_s"]
        ga, gb = sum(r["runtime_s_total"] for r in A.values()), sum(r["runtime_s_total"] for r in B.values())
        tot["A"][0] += wa
        tot["A"][1] += ga
        tot["A"][2] += len(A)
        tot["B"][0] += wb
        tot["B"][1] += gb
        tot["B"][2] += len(B)
        out["ckpts"][c] = {"n_A": len(A), "n_B": len(B), "same_request_set": same_keys, "identical_greedy_tokens": same_tokens,
                           "identical_parse": same_parse, "wall_A": wa, "wall_B": wb, "gen_sum_A": ga, "gen_sum_B": gb,
                           "peak_alloc_gb_max_A": max(r["peak_mem_alloc_gb_max"] for r in A.values()),
                           "peak_alloc_gb_max_B": max(r["peak_mem_alloc_gb_max"] for r in B.values()),
                           "max_runtime_s_A": max(r["runtime_s_total"] for r in A.values()),
                           "max_runtime_s_B": max(r["runtime_s_total"] for r in B.values())}
        ok &= same_tokens and same_parse
    out["all_identical"] = ok
    out["totals"] = {k: {"wall_s_sum": v[0], "gen_s_sum": v[1], "n": v[2], "req_per_min_by_wall": v[2] / v[0] * 60} for k, v in tot.items()}
    return out


if __name__ == "__main__":
    a, b, stage, out = sys.argv[2:6]
    r = compare(a, b, stage)
    json.dump(r, open(out, "w"), indent=1)
    print(json.dumps(r["totals"], indent=1), "identical:", r["all_identical"])
