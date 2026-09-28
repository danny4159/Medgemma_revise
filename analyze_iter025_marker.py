"""iter_026 Implementation Task 10: iter_025 D768 원시 응답에 thinking marker(<unused94>...<unused95>) 이후의
최종 yes/no 답을 별도로 재파싱해, 원래 strict/semantic_v1 parser가 invalid 처리한 건 중 몇 건이 marker 보정으로
valid가 되는지, 그리고 GT와 paired 정확도가 어떻게 달라지는지 분석한다.

원본 report/decision/gate는 건드리지 않고 새 GPU 출력도 만들지 않는다. 이 분석은 새 실험의 진입 조건이 아니다.
"""
import glob
import json
import os
import re

from rsna_diag import roi23_spec as R23, roi25_requests as Q25, roi25_spec as R25

THINK_OPEN, THINK_CLOSE = "<unused94>", "<unused95>"
EOT = "<end_of_turn>"
_PUNCT = ".!"


def marker_aware_answer(raw, ended_eos):
    """thinking 블록이 닫혀 있으면 그 뒤 텍스트에서 bare yes/no 또는 {"answer":"yes|no"}를 찾는다."""
    if not ended_eos:
        return None, "truncated"
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    if THINK_OPEN in t:
        if THINK_CLOSE not in t:
            return None, "unclosed_thinking"
        t = t.split(THINK_CLOSE, 1)[1]
    t = t.strip()
    core = t.lower()
    if core and core[-1] in _PUNCT:
        core = core[:-1]
    if re.fullmatch(r"[a-z]+", core) and core in ("yes", "no"):
        return core, "bare_yes_no_after_marker"
    if t.startswith("{"):
        try:
            v = json.loads(t)
        except ValueError:
            v = None
        if isinstance(v, dict) and list(v) == ["answer"] and v["answer"] in ("yes", "no"):
            return v["answer"], "json_answer_after_marker"
    return None, "still_invalid"


def read_gen(gen_dir):
    recs = {}
    for f in sorted(glob.glob(os.path.join(gen_dir, "gen_worker*.jsonl"))):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                recs[r["request_id"]] = r
    return recs


def gt_answers_for(items_gt, pid):
    boxes = [b["yxyx_norm"] for b in items_gt[pid]["boxes"]]
    return R23.answers(boxes)


def main():
    from rsna_diag import roi23_data as D
    items, gts = D.load_val_pool()
    out = {"n_flipped": 0, "n_flipped_correct": 0, "n_flipped_incorrect": 0, "by_ckpt_cond": {}, "flips": []}
    for ckpt in ("M0", "B0"):
        rp = f"results/iter_025/requests/D__{ckpt}.jsonl"
        if not os.path.exists(rp):
            continue
        rows = Q25.load_rows(rp)
        gen_dir = f"results/iter_025/gen/D__{ckpt}"
        recs = read_gen(gen_dir)
        for row in rows:
            rec = recs.get(row["request_id"])
            if rec is None:
                continue
            st, ans, conv = R25.parse_semantic(row["target"], row["fmt"], rec["suffix_text_raw"], rec["ended_eos"])
            if st == "valid":
                continue
            new_ans, reason = marker_aware_answer(rec["suffix_text_raw"], rec["ended_eos"])
            key = f"{ckpt}_{row['condition']}"
            out["by_ckpt_cond"].setdefault(key, {"n_orig_invalid": 0, "n_flipped": 0})
            out["by_ckpt_cond"][key]["n_orig_invalid"] += 1
            if new_ans is not None:
                out["by_ckpt_cond"][key]["n_flipped"] += 1
                out["n_flipped"] += 1
                gt = gt_answers_for(gts, row["id"])[row["target"]]
                correct = new_ans == gt
                out["n_flipped_correct"] += int(correct)
                out["n_flipped_incorrect"] += int(not correct)
                out["flips"].append({"ckpt": ckpt, "condition": row["condition"], "id": row["id"],
                                      "target": row["target"], "orig_status": st, "new_answer": new_ans,
                                      "gt": gt, "correct": correct, "reason": reason})
    os.makedirs("results/iter_026/analysis", exist_ok=True)
    json.dump(out, open("results/iter_026/analysis/iter025_marker_reanalysis.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "flips"}, indent=1))


if __name__ == "__main__":
    main()
