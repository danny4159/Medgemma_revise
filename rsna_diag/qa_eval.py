"""iter_015/016 QA/target-scope 평가. 점수는 검증을 통과한(완료·요청 집합 일치) stage에서만 계산한다 (qa_run.verify_job).

- 답 표: (checkpoint, condition, fmt, id) -> {target: (status, answer)}. invalid/truncated는 전체 분모에서 실패로 센다.
- S_scope: 환자에서 두 target을 모두 맞힘. category별 비율 후 3 category 균등 평균.
- paired bootstrap: category 내 환자를 재표집하고 한 환자의 모든 질문·형식·조건을 함께 유지한다 (10,000회, seed 20260927).
사용: python -m rsna_diag.qa_eval d36 --out results/iter_015/d36
      python -m rsna_diag.qa_eval e --set E180 ... (analysis는 아래 함수 사용)
"""
import argparse
import glob
import json
import os

import numpy as np

from . import metrics as M, parse as PA, qa_gen, qa_requests as Q, qa_run, qa_spec as S, sft_eval

OUT = Q.OUT
BOOT_N, BOOT_SEED = 10000, 20260927


ALLOW_CHANGED = ()  # 분석 진입점(qa_scope)이 설정: 결과를 보기 전에 고친 분석 코드 오류(기록됨)만 허용


def load_stage(stage, ckpt, protocol, gen_root="gen"):
    """완료된 stage/ckpt를 검증하고 record를 반환한다. 미완료·불일치면 예외."""
    from . import qa_protocol
    pdig = qa_protocol.verify(protocol, ALLOW_CHANGED)
    rp, rows, cfg = qa_run.load_job(stage, ckpt, protocol)
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    d = f"{OUT}/{gen_root}/{stage}__{ckpt}"
    if not os.path.exists(f"{d}/completion.json"):
        raise qa_gen.QAError(f"completion.json missing in {d}")
    done, missing = qa_run.verify_job(d, rows, cfg, pdig, tab[ckpt]["dir"])
    if missing:
        raise qa_gen.QAError(f"{len(missing)} requests missing in {d}")
    by = {r["request_id"]: r for r in rows}
    return [(by[k], v) for k, v in done.items()]


def load_reused(stage_dir, requests, ckpt, old_protocol, tab):
    """iter_015에서 완료된 stage를 원래 protocol과 별도 호환성 검증 후 [(row, record)]로 반환 (qa_reuse.verify_old_stage)."""
    from . import qa_reuse
    qa_reuse.verify_old_stage(stage_dir, requests, ckpt, old_protocol, tab)
    from . import qa_protocol
    cfg, _ = qa_protocol.static_cfg()
    rows = {r["request_id"]: r for r in Q.load_rows(requests, cfg)}
    recs = [r for f in sorted(glob.glob(f"{stage_dir}/gen_worker*.jsonl")) for r in qa_gen.read_strict(f)]
    return [(rows[r["request_id"]], r) for r in recs]


def answer_table(pairs, parser="strict"):
    """pairs: [(row, record)] -> {(ckpt, cond, fmt, id): {target: (status, answer, ended_eos, n_out)}}. parser: strict | semantic(semantic_v1).
    같은 (ckpt, cond, fmt, id, target)가 두 번 나오면 오류 (조용히 덮어쓰지 않는다)."""
    t = {}
    for row, rec in pairs:
        if row["target"] not in S.TARGETS:
            continue
        if parser == "semantic":
            st, ans, _conv = S.parse_semantic(row["target"], row["fmt"], rec["suffix_text_raw"], rec["ended_eos"])
        else:
            st, ans = S.parse_answer(row["fmt"], rec["suffix_text_raw"], rec["ended_eos"])
        key = (row["checkpoint"], row["condition"], row["fmt"], row["id"])
        if row["target"] in t.get(key, {}):
            raise qa_gen.QAError(f"duplicate answer for {key} target {row['target']}")
        t.setdefault((row["checkpoint"], row["condition"], row["fmt"], row["id"]), {})[row["target"]] = (st, ans, rec["ended_eos"], rec["n_output_tokens"])
    return t


def require_complete(tab, ckpts, conds, fmts, ids):
    """기대 (ckpt, cond, fmt, id) 집합이 표와 정확히 일치하고 각 항목에 두 target이 모두 있는지 검사한다. 누락·잉여는 예외."""
    want = {(c, d, f, i) for c in ckpts for d in conds for f in fmts for i in ids}
    have = {k for k in tab if k[0] in set(ckpts) and k[1] in set(conds) and k[2] in set(fmts)}
    miss, extra = want - have, have - want
    bad = [k for k in have if set(tab[k]) != set(S.TARGETS)]
    if miss or extra or bad:
        raise qa_gen.QAError(f"answer table incomplete: missing {len(miss)} extra {len(extra)} bad-targets {len(bad)} e.g. {sorted(miss)[:2]}")
    return True


def patient_correct(tab, key, cat):
    """(Q_O 정답, Q_A 정답, 둘 다 정답)  -- 요청 누락은 예외, invalid는 False."""
    r = tab[key]
    want = S.GT_PAIR[cat]
    ok = {t: (r[t][0] == "valid" and r[t][1] == want[k]) for k, t in enumerate(S.TARGETS)}
    return ok["O"], ok["A"], ok["O"] and ok["A"]


def cat_ids(sets, name):
    return {c: list(sets[name][c]) for c in S.CATEGORIES}


def score_vectors(tab, ckpt, cond, fmt, ids_by_cat):
    """{cat: array of 0/1 (both correct)}."""
    return {c: np.array([patient_correct(tab, (ckpt, cond, fmt, i), c)[2] for i in ids], dtype=float) for c, ids in ids_by_cat.items()}


def s_scope(vec):
    per = {c: float(v.mean()) for c, v in vec.items()}
    return float(np.mean(list(per.values()))), per


def bootstrap_diff(vec_a, vec_b, n=BOOT_N, seed=BOOT_SEED, ci=0.95):
    """S_scope(a)-S_scope(b) 및 category별 차이의 paired 환자 bootstrap. returns dict with point, ci, per-category."""
    rng = np.random.default_rng(seed)
    cats = list(vec_a)
    diffs = {c: np.empty(n) for c in cats}
    for c in cats:
        m = len(vec_a[c])
        idx = rng.integers(0, m, size=(n, m))
        diffs[c] = vec_a[c][idx].mean(1) - vec_b[c][idx].mean(1)
    tot = np.mean([diffs[c] for c in cats], axis=0)
    lo, hi = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
    f = lambda x, p0: {"point": float(p0), "ci": [float(np.percentile(x, lo)), float(np.percentile(x, hi))], "level": ci}
    pa, pb = s_scope(vec_a)[0], s_scope(vec_b)[0]
    return {"S_scope": f(tot, pa - pb), "per_category": {c: f(diffs[c], vec_a[c].mean() - vec_b[c].mean()) for c in cats}}


def boot_ci(vec, n=BOOT_N, seed=BOOT_SEED, ci=0.95):
    rng = np.random.default_rng(seed)
    per = []
    for c, v in vec.items():
        idx = rng.integers(0, len(v), size=(n, len(v)))
        per.append(v[idx].mean(1))
    tot = np.mean(per, axis=0)
    return [float(np.percentile(tot, (1 - ci) / 2 * 100)), float(np.percentile(tot, (1 + ci) / 2 * 100))]


def format_stats(tab, ckpt, cond, fmt, ids):
    """valid rate, EOS/truncation, 상태 분포 (target별)."""
    out = {}
    for t in S.TARGETS:
        st = [tab[(ckpt, cond, fmt, i)][t][0] for i in ids]
        out[t] = {"n": len(st), "valid": sum(s == "valid" for s in st), "valid_rate": sum(s == "valid" for s in st) / len(st),
                  "truncated": sum(s == "truncated" for s in st),
                  "status": {s: st.count(s) for s in sorted(set(st))}}
    return out


def balanced_accuracy(tab, ckpt, cond, fmt, target, gt_cat):
    """target별 balanced accuracy (invalid=오답). 양성 정답: O=opacity만 yes, A=opacity+NoOpacity/NotNormal이 yes."""
    k = S.TARGETS.index(target)
    pos, neg = [], []
    for i, c in gt_cat.items():
        r = tab[(ckpt, cond, fmt, i)]  # 누락 환자는 KeyError (조용히 건너뛰지 않는다)
        ok = r[target][0] == "valid" and r[target][1] == S.GT_PAIR[c][k]
        (pos if S.GT_PAIR[c][k] == "yes" else neg).append(ok)
    return {"sensitivity": float(np.mean(pos)), "specificity": float(np.mean(neg)), "balanced_accuracy": float((np.mean(pos) + np.mean(neg)) / 2),
            "n_pos": len(pos), "n_neg": len(neg)}


def pair_confusion(tab, ckpt, cond, fmt, gt_cat):
    """category별 (Q_O,Q_A) 답 쌍 분포. invalid는 'invalid'."""
    out = {c: {} for c in S.CATEGORIES}
    for i, c in gt_cat.items():
        r = tab[(ckpt, cond, fmt, i)]
        k = tuple((r[t][1] if r[t][0] == "valid" else "invalid") for t in S.TARGETS)
        out[c]["/".join(k)] = out[c].get("/".join(k), 0) + 1
    return out


def agreement(tab, ckpt, cond, ids):
    """plain·json 두 형식에서 유효한 답이 일치하는 비율 (양쪽 모두 유효한 (환자,target)만)."""
    n = k = nb = 0
    for i in ids:
        a, b = tab[(ckpt, cond, "plain", i)], tab[(ckpt, cond, "json", i)]
        for t in S.TARGETS:
            nb += 1
            if a[t][0] == "valid" and b[t][0] == "valid":
                n += 1
                k += a[t][1] == b[t][1]
    return {"n_both_valid": n, "agree": k, "rate": k / n if n else None, "n_pairs": nb}


def constant_baselines(gt_cat_ids):
    """category와 무관한 고정 답 쌍의 S_scope (질문 prior). gt_cat_ids: {cat: [ids]}."""
    out = {}
    for pair in [("yes", "yes"), ("yes", "no"), ("no", "yes"), ("no", "no")]:
        per = {c: float(S.GT_PAIR[c] == pair) for c in S.CATEGORIES}
        out["/".join(pair)] = {"S_scope": float(np.mean(list(per.values()))), "per_category": per}
    return out


def bbox_preds(ckpt, ids):
    recs = Q.bbox_records(ckpt)
    miss = [i for i in ids if i not in recs]
    if miss:
        raise KeyError(f"{ckpt} bbox missing for {len(miss)} ids e.g. {miss[:2]}")
    return {i: PA.parse_response(recs[i]["suffix_text_raw"], recs[i]["ended_eos"]) for i in ids}


def bbox_summary(ckpt, ids, labels):
    gt = {i: {"category": labels[i]["category"], "boxes": labels[i]["boxes"]} for i in ids}
    return sft_eval.summarize(bbox_preds(ckpt, ids), gt, ids)


def detector_rule(ckpt, ids_by_cat):
    """bbox+규칙: 유효 비어 있지 않은 bbox -> (yes,yes). 빈 유효 bbox -> Q_O=no, Q_A 판단 불가. invalid -> 실패.
    S_scope(fail): 판단 불가·invalid를 실패로. coverage/covered accuracy 별도."""
    allids = [i for v in ids_by_cat.values() for i in v]
    pr = bbox_preds(ckpt, allids)
    vec_fail, cov = {}, {}
    for c, ids in ids_by_cat.items():
        want = S.GT_PAIR[c]
        ok, decided, correct_dec = [], 0, 0
        qo = 0
        for i in ids:
            st = pr[i]["status"]
            if st == "valid_nonempty":
                pair = ("yes", "yes")
            elif st == "valid_empty":
                pair = ("no", None)
            else:
                pair = (None, None)
            qo += pair[0] == want[0]
            full = pair[0] == want[0] and pair[1] == want[1]
            ok.append(full)
            if pair[1] is not None:
                decided += 1
                correct_dec += full
        vec_fail[c] = np.array(ok, dtype=float)
        cov[c] = {"n": len(ids), "q_a_decided": decided, "coverage": decided / len(ids), "pair_correct_among_decided": (correct_dec / decided if decided else None),
                  "q_o_accuracy": qo / len(ids)}
    return {"S_scope_undecided_as_fail": s_scope(vec_fail)[0], "per_category_fail": {c: float(v.mean()) for c, v in vec_fail.items()},
            "coverage": cov}, vec_fail


def d36_format_gate(protocol, out):
    """D36 형식 gate: 모든 (ckpt,target)에서 valid rate >= 0.95면 plain. plain 실패 & json 통과면 json. 둘 다 실패면 format_problem.
    정답 정확도는 보지 않는다 (형식 준수만)."""
    sets = json.load(open(f"{OUT}/manifests/sets.json"))
    ids = [i for c in S.CATEGORIES for i in sets["D36"][c]]
    tabs = {}
    for fmt in ("plain", "json"):
        for ck in ("M0", "B0", "C"):
            tabs.update(answer_table(load_stage(f"d36_{fmt}", ck, protocol)))
    fs = {fmt: {ck: format_stats(tabs, ck, "direct", fmt, ids) for ck in ("M0", "B0", "C")} for fmt in ("plain", "json")}
    okf = {fmt: all(fs[fmt][ck][t]["valid_rate"] >= 0.95 for ck in fs[fmt] for t in S.TARGETS) for fmt in fs}
    primary = "plain" if okf["plain"] else ("json" if okf["json"] else None)
    d = {"format_stats": fs, "gate_pass": okf, "primary_format": primary,
         "alternate_format": None if primary is None else ("json" if primary == "plain" else "plain"),
         "rule": "valid rate >= 0.95 for every checkpoint x target; plain first; format compliance only, no accuracy used",
         "n_patients": len(ids)}
    json.dump(d, open(out, "w"), indent=1)
    return d


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("d36")
    g.add_argument("--protocol", required=True)
    g.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "d36":
        d = d36_format_gate(a.protocol, a.out)
        print(json.dumps({"gate_pass": d["gate_pass"], "primary_format": d["primary_format"]}))
        for fmt in d["format_stats"]:
            for ck, v in d["format_stats"][fmt].items():
                print(fmt, ck, {t: (round(x["valid_rate"], 3), x["status"]) for t, x in v.items()})


if __name__ == "__main__":
    main()
