"""iter_100: 수동 의미 판정(judgments.json, 조건명 눈가림)에서 환자·조건별 지표와 원 분기를 계산한다.

판정 스키마(blind_id별):
  P: {atom_id: {status: preserved|deleted|negated|damaged, quote}}      (보존 대상: 초안의 reference-supported atom)
  Q: {atom_id: {status: recovered|absent, quote, ambiguous?: bool}}      (회복 대상)
  explicit: [{key, quote, fact, why}]     reference가 명시적으로 반박하는 주장
  internal: [{key, quotes:[..], why}]     출력 내부의 명확한 충돌
  unverifiable: [{key, quote, why}]       reference에 없는 검증 불가 주장
'새' 오류 = K(초안 유지)에 없는 key. quote는 해당 출력 원문에 있어야 한다(없으면 거부). 모든 출력이 판정되어야 한다.
안전한 회복 환자: Q 하나 이상 recovered + P 전체 preserved + K 대비 새 explicit/internal 없음.
"""
import json
import sys
from pathlib import Path

import numpy as np

from report86_common import save, sha

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "iter_100"
CONDS = ["K", "A", "N", "T", "L"]


def load(dest=OUT / "eval"):
    blind = json.loads((dest / "blind" / "review_input.json").read_text())
    mapping = json.loads((dest / "blind" / "private_mapping.json").read_text())
    judg = json.loads((dest / "judgments.json").read_text())
    return blind, mapping, judg


def validate(blind, mapping, judg):
    problems = []
    texts = dict((o["blind_id"], o["text"]) for r in blind["review"] for o in r["outputs"])
    atoms = dict((r["patient"], (set(a["id"] for a in r["atoms_P"]), set(a["id"] for a in r["atoms_Q"]))) for r in blind["review"])
    jb = dict((j["blind_id"], j) for j in judg["judgments"])
    if len(jb) != len(judg["judgments"]) or set(jb) != set(texts):
        problems.append("judgment_set_mismatch")
    for b, j in jb.items():
        if b not in texts:
            continue
        pi = mapping[b]["patient"]
        t = texts[b].lower()
        pids, qids = atoms[pi]
        if set(j["P"]) != pids or set(j["Q"]) != qids:
            problems.append("atom_set:%s" % b)
        for d in list(j["P"].values()) + list(j["Q"].values()):
            if d["status"] not in ("preserved", "deleted", "negated", "damaged", "recovered", "absent"):
                problems.append("status:%s" % b)
            if d["status"] in ("preserved", "recovered", "damaged", "negated") and d.get("quote", "").lower() not in t:
                problems.append("quote_missing:%s" % b)
        for k in j["explicit"] + j["unverifiable"]:
            if k["quote"].lower() not in t:
                problems.append("quote_missing:%s:%s" % (b, k["key"]))
        for k in j["internal"]:
            if not all(q.lower() in t for q in k["quotes"]):
                problems.append("quote_missing:%s:%s" % (b, k["key"]))
    return problems


def per_patient(blind, mapping, judg, drop_ambiguous=False, ignore_internal=False):
    cond = dict((b, m["condition"]) for b, m in mapping.items())
    jb = dict((j["blind_id"], j) for j in judg["judgments"])
    # 회복 집계는 ledger에서 clear로 잠근 Q atom만 센다. unknown/partial atom은 판정을 기록하되 회복 수에 넣지 않는다.
    clear_q = dict((r["patient"], set(a["id"] for a in r["atoms_Q"] if a["status"] == "clear")) for r in blind["review"])
    rows = {}
    for b, j in jb.items():
        pi, c = mapping[b]["patient"], cond[b]
        rows.setdefault(pi, {})[c] = j
    out = {}
    for pi, byc in rows.items():
        k = byc["K"]
        kexp = set(x["key"] for x in k["explicit"])
        kint = set(x["key"] for x in k["internal"])
        kunv = set(x["key"] for x in k["unverifiable"])
        res = {}
        for c in CONDS:
            j = byc[c]
            q = [d for a, d in j["Q"].items() if a in clear_q[pi] and not (drop_ambiguous and d.get("ambiguous"))]
            rec = sum(d["status"] == "recovered" for d in q)
            pdam = sum(d["status"] != "preserved" for d in j["P"].values())
            nexp = len(set(x["key"] for x in j["explicit"]) - kexp)
            nint = 0 if ignore_internal else len(set(x["key"] for x in j["internal"]) - kint)
            nunv = len(set(x["key"] for x in j["unverifiable"]) - kunv)
            res[c] = dict(Q_recovered=rec, Q_total=len(q), P_damaged=pdam, P_total=len(j["P"]), new_explicit=nexp, new_internal=nint,
                          new_unverifiable=nunv, safe_recovery=bool(rec >= 1 and pdam == 0 and nexp == 0 and nint == 0),
                          harm=bool(pdam > 0 or nexp > 0 or nint > 0))
        out[pi] = res
    return out


def decide(role, table):
    """원 계획의 분기. recovery 환자 수 N이 작으면 양성 기준(최소 3명/순증가 2명)은 충족 불가능으로 기록한다."""
    rec = [p for p in table if role[p] == "recovery"]
    n = len(rec)

    def net(a, b):
        return sum(table[p][a]["safe_recovery"] for p in rec) - sum(table[p][b]["safe_recovery"] for p in rec)

    def harm(c):
        return sum(table[p][c]["harm"] for p in table)
    safe_T = sum(table[p]["T"]["safe_recovery"] for p in rec)
    safe_L = sum(table[p]["L"]["safe_recovery"] for p in rec)
    d = dict(n_recovery=n, n_total=len(table),
             safe_recovery_patients=dict((c, sum(table[p][c]["safe_recovery"] for p in rec)) for c in CONDS),
             harm_patients=dict((c, harm(c)) for c in CONDS),
             net_T_vs_N=net("T", "N"), net_T_vs_A=net("T", "A"), net_L_vs_N=net("L", "N"), net_L_vs_A=net("L", "A"), net_L_vs_T=net("L", "T"),
             positive_criterion_satisfiable=n >= 3)
    t_or_l = max(safe_T, safe_L)
    d["positive"] = bool(t_or_l >= 3 and max(net("T", "N"), net("L", "N")) >= 2 and max(net("T", "A"), net("L", "A")) >= 2)
    d["source_effect"] = bool(d["positive"] and net("L", "T") >= 2)
    d["outcome"] = ("insufficient_sample: 원 양성 기준(최소 3명)을 충족할 수 없는 사례 관찰" if n < 3
                    else ("positive_exploration" if d["positive"] else "no_gain_or_uncertain"))
    return d


def boot(role, table, seed=98017, B=10000):
    """환자 bootstrap(조건별 safe_recovery 평균 차이). 환자 수가 작으면 퇴화 구간이며 확증이 아니다."""
    pats = sorted(table)
    rng = np.random.default_rng(seed)
    res = {}
    for a, b in (("T", "K"), ("L", "K"), ("T", "N"), ("L", "N"), ("T", "A"), ("L", "A"), ("L", "T")):
        v = np.array([int(table[p][a]["safe_recovery"]) - int(table[p][b]["safe_recovery"]) for p in pats], float)
        idx = rng.integers(0, len(pats), (B, len(pats)))
        m = v[idx].mean(1)
        res["%s-%s" % (a, b)] = dict(mean=float(v.mean()), lo=float(np.percentile(m, 2.5)), hi=float(np.percentile(m, 97.5)),
                                     degenerate=bool(len(set(v.tolist())) == 1))
    return res


def loo(role, table):
    out = {}
    for drop in sorted(table):
        sub = dict((p, v) for p, v in table.items() if p != drop)
        sub_role = dict((p, role[p]) for p in sub)
        out[str(drop)] = decide(sub_role, sub) if sub else None
    return out


def main():
    dest = OUT / "eval"
    blind, mapping, judg = load(dest)
    probs = validate(blind, mapping, judg)
    assert not probs, probs
    dec = json.loads((OUT / "data" / "eligibility_decision.json").read_text())
    role = dict((s["patient"], s["role"]) for s in dec["selected_patients"])
    table = per_patient(blind, mapping, judg)
    table_na = per_patient(blind, mapping, judg, drop_ambiguous=True)
    table_ni = per_patient(blind, mapping, judg, ignore_internal=True)
    # 검증 불가 증가 환자 제외 분석
    excl = dict((p, v) for p, v in table.items() if all(v[c]["new_unverifiable"] == 0 for c in ("T", "L", "N", "A")))
    report = dict(table=table, decision=decide(role, table),
                  sensitivity_exclude_ambiguous=decide(role, table_na),
                  sensitivity_ignore_internal_conflicts=dict(decision=decide(role, table_ni), table=table_ni,
                                                             note="사후 민감도: 내부 충돌 판정이 결과를 가르는지 보기 위한 것이며 원 기준이 아니다"),
                  sensitivity_exclude_unverifiable_increase=decide({p: role[p] for p in excl}, excl) if excl else None,
                  excluded_for_unverifiable=sorted(set(table) - set(excl)),
                  bootstrap_seed98017=boot(role, table), leave_one_patient_out=loo(role, table),
                  provenance=dict(judgments_sha=sha(dest / "judgments.json"), review_input_sha=sha(dest / "blind" / "review_input.json"),
                                  mapping_sha=sha(dest / "blind" / "private_mapping.json"), eval_sha=sha(__file__)),
                  note="assistant 단일 수동 검토이며 전문의/독립 임상 평가가 아니다. 눈가림은 조건명 제거 수준이다.")
    save(dest / "report_v2.json", report)
    print(json.dumps(report["decision"], ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
