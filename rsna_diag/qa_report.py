"""iter_015 stage 결과 요약: D36 형식 gate 서술(개발 자료), D12 evidence 구현 확인, E180 concise bbox 비교(M0/B0 재사용 + C 신규).

사용: python -m rsna_diag.qa_report --protocol results/iter_015/protocols/protocol_stage2.json --out results/iter_015/e180/report.json
- D36의 lenient 매핑('Normal'/'Abnormal' 단어를 yes/no로 옮김)은 사후 서술이며 primary 지표가 아니다. 결과 선택·확대 판단에 쓰지 않는다.
"""
import argparse
import collections
import json
import os

import numpy as np

from . import parse as PA, qa_eval as E, qa_requests as Q, qa_spec as S, sft_eval

OUT = Q.OUT


def raw_breakdown(protocol):
    """D36 direct 요청의 정규화된 원문(형식 실패의 실제 내용)."""
    out = {}
    for fmt in ("plain", "json"):
        for ck in ("M0", "B0", "C"):
            c = {"O": collections.Counter(), "A": collections.Counter()}
            for row, rec in E.load_stage(f"d36_{fmt}", ck, protocol):
                t = rec["suffix_text_raw"].replace("<end_of_turn>", "").strip().lower()
                c[row["target"]][t[:40]] += 1
            out[f"{fmt}/{ck}"] = {t: dict(c[t].most_common(8)) for t in c}
    return out


def lenient_post_hoc(protocol):
    """사후 서술: Q_A의 'normal'->no, 'abnormal'->yes, JSON 지시를 무시한 bare yes/no와 {"answer":..}를 허용. primary 아님. D36은 12명/category라 추정이 아니다."""
    sets = json.load(open(f"{OUT}/manifests/sets.json"))
    cats = {c: sets["D36"][c] for c in S.CATEGORIES}
    res = {}
    import re
    for fmt in ("plain", "json"):
        for ck in ("M0", "B0", "C"):
            ans = {}
            for row, rec in E.load_stage(f"d36_{fmt}", ck, protocol):
                if not rec["ended_eos"]:
                    a = None
                else:
                    t = rec["suffix_text_raw"].replace("<end_of_turn>", "").strip().lower()
                    m = re.fullmatch(r'[{"\s:]*(?:answer[":\s]*)?(yes|no|normal|abnormal)[\s."}]*', t)
                    w = m.group(1) if m else None
                    a = {"yes": "yes", "no": "no", "abnormal": "yes", "normal": "no"}.get(w)
                ans[(row["id"], row["target"])] = a
            per = {}
            for c, ids in cats.items():
                want = S.GT_PAIR[c]
                per[c] = float(np.mean([ans[(i, "O")] == want[0] and ans[(i, "A")] == want[1] for i in ids]))
            res[f"{fmt}/{ck}"] = {"S_scope_lenient_posthoc": float(np.mean(list(per.values()))), "per_category": per,
                                  "n_per_category": 12, "n_none": sum(v is None for v in ans.values())}
    return res


def d12_evidence(protocol):
    """D12 evidence 구현 확인 (M0 plain). accuracy는 일반화 근거가 아니다. 유효 rate와 evidence 문장 연결만 본다."""
    pairs = E.load_stage("d12_evidence", "M0", protocol)
    tab = E.answer_table(pairs)
    st = collections.defaultdict(collections.Counter)
    src = collections.Counter()
    for row, rec in pairs:
        s_, _ = S.parse_answer(row["fmt"], rec["suffix_text_raw"], rec["ended_eos"])
        st[row["condition"] + "/" + row["target"]][s_] += 1
        if row["condition"] == "ev_predicted":
            src[row["extra"].get("source_status")] += 1
    return {"status_by_condition_target": {k: dict(v) for k, v in st.items()}, "predicted_source_status": dict(src),
            "n_requests": len(pairs),
            "note": "구현·연결 확인용(12명). format gate 실패 상태이므로 정확도를 해석하지 않는다."}


def boot_f1(pa, pb, ids, labels, n=E.BOOT_N, seed=E.BOOT_SEED):
    gt = {i: {"category": labels[i]["category"], "boxes": labels[i]["boxes"]} for i in ids}
    pos, A = sft_eval.per_patient(pa, gt, ids)
    _, B = sft_eval.per_patient(pb, gt, ids)
    res = {}
    for k in ("f1@0.3", "f1@0.5"):
        d = A[k] - B[k]
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(d), size=(n, len(d)))
        bs = d[idx].mean(1)
        res[k] = {"point": float(d.mean()), "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], "n_positive": len(d)}
    return res


def e180_bbox(protocol):
    sets = json.load(open(f"{OUT}/manifests/sets.json"))
    labels = json.load(open(f"{OUT}/manifests/labels.json"))
    ids = [i for c in S.CATEGORIES for i in sets["E180"][c]]
    ids_by_cat = {c: sets["E180"][c] for c in S.CATEGORIES}
    E.load_stage("e180_bbox", "C", protocol)  # 완료·provenance 검증
    out = {"n_patients": len(ids)}
    preds = {}
    for ck in ("M0", "B0", "C"):
        preds[ck] = E.bbox_preds(ck, ids)
        s = E.bbox_summary(ck, ids, labels)
        keep = ("n_positive", "f1@0.3", "f1@0.5", "precision@0.3", "recall@0.3", "valid_rate_all", "positive_valid_empty", "status_all", "truncated_all",
                "neg_Normal", "neg_NoOpacity/NotNormal", "by_n_gt", "utility")
        out[ck] = {k: s[k] for k in keep}
    out["C_minus_B0"] = boot_f1(preds["C"], preds["B0"], ids, labels)
    out["B0_minus_M0"] = boot_f1(preds["B0"], preds["M0"], ids, labels)
    rule = {}
    for ck in ("M0", "B0", "C"):
        rule[ck], _ = E.detector_rule(ck, ids_by_cat)
    out["detector_rule"] = rule
    out["constant_pair_baselines"] = E.constant_baselines(ids_by_cat)
    out["provenance"] = {"M0/B0": "results/iter_015/reuse/reuse_report.json (iter_012 confirm, 검증 후 재사용)", "C": "gen/e180_bbox__C (이번 반복 신규, protocol_stage2)"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--protocol-d36", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    rep = {"d36_raw_breakdown": raw_breakdown(a.protocol_d36), "d36_lenient_posthoc_not_primary": lenient_post_hoc(a.protocol_d36),
           "d12_evidence_impl_check": d12_evidence(a.protocol), "e180_bbox": e180_bbox(a.protocol)}
    json.dump(rep, open(a.out, "w"), indent=1)
    print(json.dumps({k: (v if k != "d36_raw_breakdown" else "...") for k, v in rep.items() if k in ("d36_lenient_posthoc_not_primary", "d12_evidence_impl_check")}, indent=0)[:3500])
    b = rep["e180_bbox"]
    for ck in ("M0", "B0", "C"):
        print(ck, {k: (round(b[ck][k], 4) if isinstance(b[ck][k], float) else None) for k in ("f1@0.3", "f1@0.5", "utility")},
              "valid_all", b[ck]["valid_rate_all"]["rate"], "posEmpty", b[ck]["positive_valid_empty"]["rate"])
    print("C-B0", b["C_minus_B0"], "B0-M0", b["B0_minus_M0"])
    print("rule", json.dumps(b["detector_rule"]["B0"]))


if __name__ == "__main__":
    main()
