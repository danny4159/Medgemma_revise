"""iter_105 평가: 환자 단위 연결 정확도·paired 차이·전환·PG 대안·확대 규칙. 입력은 완료·검증된 shard 출력만.

분석 단위는 환자. 환자별 두 순서의 정확도를 평균한다. invalid/truncated/abstain은 오답으로 센다(별도 집계).
bootstrap: 환자 단위 10,000회, seed 105017, 95% percentile. 모델별로 분리 보고한다(합성 없음).
요청 구성에서 GT는 C/W 제안 문장에만 쓰였고, 평가에서 GT와 대조한다.
"""
import json
import sys
from pathlib import Path

import numpy as np

import lk105_run as R
import lk105_spec as S
from report86_common import sha, sha_obj, save

BOOT, BSEED = 10000, 105017


def load_stage(gen_dir, stage, workers, systems=("CURE", "M15")):
    """completion과 요청 집합을 전수 검증하고 {system: {id: record}}를 돌려준다."""
    out = {}
    for system in systems:
        nw = workers[system] if isinstance(workers, dict) else workers
        sd = sha_obj(R.scientific_protocol(stage, system, nw))
        recs = {}
        for k in range(nw):
            c, rs = R.verify_completion(R.shard_dir(gen_dir, system, k), stage, system, k, nw, sd)
            for r in rs:
                assert r["id"] not in recs
                recs[r["id"]] = r
        assert set(recs) == {q["id"] for q in R.requests(stage, system)}, "request set mismatch"
        out[system] = recs
    return out


def final_text(rec):
    a = rec["attempts"][-1]
    return rec["text"], a["ended_eos"]


PARSERS = {"strict": S.parse_choice, "lenient_v1": S.parse_choice_lenient}


def patient_table(stage, recs, system, parser=S.parse_choice):
    """returns list per patient: dict with per-condition arrays."""
    rows, _ = R.stage_rows(stage)
    tab = []
    for row in rows:
        iid = row["ImageID"]
        t = {"ImageID": iid, "sel": {}, "status": {}}
        for mod in ("img", "txt"):
            for cond in S.CONDS:
                for o in S.ORDERS:
                    rec = recs[f"{iid}|{system}|{mod}-{cond}-o{o}"]
                    text, eos = final_text(rec)
                    ans, status = parser(text, eos)
                    t["sel"][(mod, cond, o)] = ans
                    t["status"][(mod, cond, o)] = status
        # PG
        pgs = {}
        for k in ("S1", "S2"):
            rec = recs[f"{iid}|{system}|pg-{k}"]
            text, eos = final_text(rec)
            pgs[k] = S.parse_pg(system, text, eos, row)
        t["pg"] = pgs
        a, sa, sb = S.pg_connection(row, pgs["S1"]["boxes"], pgs["S2"]["boxes"])
        t["pg_choice"], t["pg_scores"] = a, (sa, sb)
        t["pg_iou"] = (S.best_iou(pgs["S1"]["boxes"], row["box1"]), S.best_iou(pgs["S2"]["boxes"], row["box2"]))
        # 민감도: 참조를 boxes ∪ extra_boxes로 확장
        ex1, ex2 = [row["box1"]] + row["extra1"], [row["box2"]] + row["extra2"]
        sa2 = max(S.best_iou(pgs["S1"]["boxes"], b) for b in ex1) + max(S.best_iou(pgs["S2"]["boxes"], b) for b in ex2)
        sb2 = max(S.best_iou(pgs["S1"]["boxes"], b) for b in ex2) + max(S.best_iou(pgs["S2"]["boxes"], b) for b in ex1)
        t["pg_choice_ext"] = None if (sa2 == sb2 or (sa2 == 0 and sb2 == 0)) else ("A" if sa2 > sb2 else "B")
        tab.append(t)
    return tab


def correct(t, mod, cond, o):
    return t["sel"][(mod, cond, o)] == S.gt_letter(o)


def acc_vec(tab, mod, cond, filt=None):
    """환자별 두 순서 평균 정확도."""
    return np.array([np.mean([correct(t, mod, cond, o) for o in S.ORDERS]) for t in tab], float)


def boot_ci(x, fn=np.mean, n=BOOT, seed=BSEED):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    vals = fn(x[idx], axis=1) if fn is np.mean else np.array([fn(x[i]) for i in idx])
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def mean_ci(x):
    x = np.asarray(x, float)
    return {"mean": float(x.mean()), "ci95": boot_ci(x), "n": int(len(x))}


def diff_ci(a, b):
    return mean_ci(np.asarray(a, float) - np.asarray(b, float))


def summarize_tab(tab, recs):
    n = len(tab)
    out = {"n_patients": n}
    acc = {f"{mod}_{c}": acc_vec(tab, mod, c) for mod in ("img", "txt") for c in S.CONDS}
    out["acc"] = {k: mean_ci(v) for k, v in acc.items()}
    pg = np.array([1.0 if t["pg_choice"] == "A" else 0.0 for t in tab])
    out["acc"]["PG"] = mean_ci(pg)
    out["acc"]["PG_ext_reference_sensitivity"] = mean_ci([1.0 if t["pg_choice_ext"] == "A" else 0.0 for t in tab])
    out["paired"] = {"N_minus_W": diff_ci(acc["img_N"], acc["img_W"]), "C_minus_N": diff_ci(acc["img_C"], acc["img_N"]),
                     "N_minus_TextN": diff_ci(acc["img_N"], acc["txt_N"]), "C_minus_W": diff_ci(acc["img_C"], acc["img_W"]),
                     "TextN_minus_TextW": diff_ci(acc["txt_N"], acc["txt_W"]), "C_minus_PG": diff_ci(acc["img_C"], pg),
                     "N_minus_PG": diff_ci(acc["img_N"], pg)}
    # 전환: 같은 order에서 N 정답→W 오답 (환자 수/요청 수), W 정답→N 오답 반대 방향도 보고
    def trans(c1, c2, mod="img"):
        pats, reqs = 0, 0
        for t in tab:
            k = sum(correct(t, mod, c1, o) and not correct(t, mod, c2, o) for o in S.ORDERS)
            pats += k > 0
            reqs += k
        return {"patients": int(pats), "requests": int(reqs)}
    out["transitions"] = {"N_right_to_W_wrong": trans("N", "W"), "W_right_to_N_wrong": trans("W", "N"), "N_right_to_C_wrong": trans("N", "C"),
                          "N_right_to_W_wrong_text": trans("N", "W", "txt"), "N_wrong_to_C_right": trans("C", "N")}
    # 양 순서 일치(같은 환자의 두 순서에서 선택한 문장-영역 연결이 동일; 둘 다 유효일 때)
    cons = {}
    for mod in ("img", "txt"):
        for c in S.CONDS:
            ok = [t for t in tab if t["sel"][(mod, c, 0)] and t["sel"][(mod, c, 1)]]
            # order1에서 같은 연결은 반대 글자: 연결 일치 = 글자가 다름
            same = [t["sel"][(mod, c, 0)] != t["sel"][(mod, c, 1)] for t in ok]
            cons[f"{mod}_{c}"] = {"n_both_valid": len(ok), "same_connection_rate": float(np.mean(same)) if same else None}
    out["order_consistency"] = cons
    # 제안 추종률 (유효 응답 중 제안 글자와 같은 비율) — Copy 규칙의 해석 기준
    follow = {}
    for mod in ("img", "txt"):
        for c in ("C", "W"):
            v = [t["sel"][(mod, c, o)] == S.proposal_letter(c, o) for t in tab for o in S.ORDERS]
            follow[f"{mod}_{c}"] = float(np.mean(v))
    out["follow_proposal_rate"] = follow
    # 형식/응답 상태
    st = {}
    for mod in ("img", "txt"):
        for c in S.CONDS:
            cnt = {}
            for t in tab:
                for o in S.ORDERS:
                    s = t["status"][(mod, c, o)]
                    cnt[s] = cnt.get(s, 0) + 1
            st[f"{mod}_{c}"] = cnt
    out["selection_status"] = st
    out["letter_prior"] = {f"{mod}_{c}": {"A_rate": float(np.mean([t["sel"][(mod, c, o)] == "A" for t in tab for o in S.ORDERS]))}
                           for mod in ("img", "txt") for c in S.CONDS}
    # valid-format only 환자 (두 순서 모두 N/W img 유효)
    ok = [t for t in tab if all(t["status"][("img", c, o)] == "valid" for c in ("N", "W") for o in S.ORDERS)]
    if ok:
        a_n = np.array([np.mean([correct(t, "img", "N", o) for o in S.ORDERS]) for t in ok])
        a_w = np.array([np.mean([correct(t, "img", "W", o) for o in S.ORDERS]) for t in ok])
        out["valid_only_N_minus_W"] = {**diff_ci(a_n, a_w), "n_patients": len(ok)}
    # 후보 순서별 N−W
    out["by_order_N_minus_W"] = {f"o{o}": float(np.mean([correct(t, "img", "N", o) for t in tab]) - np.mean([correct(t, "img", "W", o) for t in tab]))
                                 for o in S.ORDERS}
    # 조건부: N이 두 순서 모두 맞은 환자에서 W/C 정확도
    both = [t for t in tab if all(correct(t, "img", "N", o) for o in S.ORDERS)]
    out["conditional_on_N_both_orders_right"] = {"n": len(both),
                                                  "W_acc": float(np.mean([np.mean([correct(t, "img", "W", o) for o in S.ORDERS]) for t in both])) if both else None,
                                                  "C_acc": float(np.mean([np.mean([correct(t, "img", "C", o) for o in S.ORDERS]) for t in both])) if both else None}
    # PG 상세
    pgst = {}
    for k in ("S1", "S2"):
        for t in tab:
            s = t["pg"][k]["status"]
            pgst[s] = pgst.get(s, 0) + 1
    out["pg"] = {"status": pgst, "abstain": int(sum(t["pg_choice"] is None for t in tab)),
                 "grounding_iou_mean": mean_ci([np.mean(t["pg_iou"]) for t in tab]),
                 "grounding_iou_ge_0.3_sentence_rate": float(np.mean([v >= 0.3 for t in tab for v in t["pg_iou"]])),
                 "ext_reference_choice_differs": int(sum(t["pg_choice"] != t["pg_choice_ext"] for t in tab))}
    # 비용(생성 초 합, cap 재시도 포함)
    def cost(pred):
        v = [sum(x["runtime_s"] for x in r["attempts"]) for r in recs.values() if pred(r)]
        return {"n": len(v), "mean_s": float(np.mean(v)) if v else None, "sum_s": float(np.sum(v)) if v else None}
    out["cost_generation_s"] = {"select_img": cost(lambda r: r["kind"] == "select" and r["modality"] == "image"),
                                "select_txt": cost(lambda r: r["kind"] == "select" and r["modality"] == "text"),
                                "pg": cost(lambda r: r["kind"] == "pg")}
    out["final_not_eos"] = int(sum(not r["attempts"][-1]["ended_eos"] for r in recs.values()))
    out["cap_retries"] = int(sum(len(r["attempts"]) > 1 for r in recs.values()))
    out["max_new_tokens_select"] = int(max(r["attempts"][-1]["n_new"] for r in recs.values() if r["kind"] == "select"))
    return out


def expansion_rule(summ):
    """사전 확대 규칙(E32): 모델별 N≥0.70 & N−TextN≥0.10 & (N−W≥0.10 or N정답→W오답 ≥3명). 한 모델이라도 충족하면 두 모델 모두 확대."""
    per = {}
    for s, o in summ.items():
        n = o["acc"]["img_N"]["mean"]
        cond = {"N_ge_0.70": n >= 0.70, "N_minus_TextN_ge_0.10": o["paired"]["N_minus_TextN"]["mean"] >= 0.10,
                "N_minus_W_ge_0.10": o["paired"]["N_minus_W"]["mean"] >= 0.10,
                "transitions_ge_3_patients": o["transitions"]["N_right_to_W_wrong"]["patients"] >= 3}
        per[s] = {**cond, "meets": bool(cond["N_ge_0.70"] and cond["N_minus_TextN_ge_0.10"] and (cond["N_minus_W_ge_0.10"] or cond["transitions_ge_3_patients"]))}
    return {"per_model": per, "expand_to_E96": any(v["meets"] for v in per.values())}


def classify(summ):
    """E96 평가용 사전 분류(양성 관찰·단순 대안 충분성·후속 최소 개입 검토 조건). E32에서는 탐색 표시로만 쓴다."""
    out = {}
    for s, o in summ.items():
        p = o["paired"]
        pos = (o["acc"]["img_N"]["mean"] >= 0.70 and p["N_minus_TextN"]["mean"] >= 0.10 and p["N_minus_W"]["mean"] >= 0.10
               and p["N_minus_W"]["ci95"][0] > 0 and o["transitions"]["N_right_to_W_wrong"]["patients"] >= 3
               and o.get("valid_only_N_minus_W", {}).get("mean", 0) > 0 and all(v > 0 for v in o["by_order_N_minus_W"].values()))
        best_nc = max(o["acc"]["img_N"]["mean"], o["acc"]["img_C"]["mean"])
        pg_ok = o["acc"]["PG"]["mean"] >= 0.85 and o["acc"]["PG"]["mean"] >= best_nc - 0.05
        followup = (pos and not pg_ok and p["C_minus_N"]["mean"] >= 0.10 and p["C_minus_PG"]["mean"] >= 0.10)
        out[s] = {"positive_observation": bool(pos), "simple_alternative_PG_sufficient_on_this_sample": bool(pg_ok),
                  "followup_minimal_intervention_review_condition": bool(followup)}
    return out


def main(stage_names, gen_dirs, workers, tag, systems=("CURE", "M15")):
    """stage_names: 합칠 단계 목록(예: E32 또는 E32,R64). gen_dirs: 단계별 gen dir."""
    tabs, summ = {}, {}
    all_recs = {s: {} for s in systems}
    rows_all = []
    for st, gd in zip(stage_names, gen_dirs):
        recs = load_stage(gd, st, workers, systems)
        for s in systems:
            all_recs[s].update(recs[s])
        rows_all += R.stage_rows(st)[0]
    for s in systems:
        summ[s] = {}
        for pname, parser in PARSERS.items():
            tab_parts = []
            for st in stage_names:
                ids = {r["ImageID"] for r in R.stage_rows(st)[0]}
                part = {k: v for k, v in all_recs[s].items() if k.split("|")[0] in ids}
                tab_parts += patient_table(st, part, s, parser)
            summ[s][pname] = summarize_tab(tab_parts, all_recs[s])
    report = {"stages": stage_names, "n_patients": len(rows_all), "seed": BSEED, "bootstrap": BOOT, "summary": summ,
              "expansion": {p: expansion_rule({s: summ[s][p] for s in systems}) for p in PARSERS},
              "classification": {p: classify({s: summ[s][p] for s in systems}) for p in PARSERS},
              "provenance": {"code": {f: sha(R.ROOT / f) for f in ("lk105_eval.py", "lk105_spec.py", "lk105_run.py")},
                             "selection_lock": sha(R.DATA / "selection_lock.json"), "weights_lock": sha(R.LOCKFILE),
                             "label": "development material (PadChest-GR train); not an independent test; CURE training exposure unconfirmed"}}
    save(R.R105 / f"eval/report_{tag}.json", report)
    return report


if __name__ == "__main__":
    # 사용: python lk105_eval.py TAG WORKERS STAGE:GENDIR [STAGE:GENDIR ...]
    tag = sys.argv[1]
    workers = {x.split("=")[0]: int(x.split("=")[1]) for x in sys.argv[2].split(",")} if "=" in sys.argv[2] else int(sys.argv[2])
    pairs = [x.split(":") for x in sys.argv[3:]]
    rep = main([p[0] for p in pairs], [p[1] for p in pairs], workers, tag)
    print(json.dumps({"expansion": rep["expansion"], "classification": rep["classification"]}, indent=1))
