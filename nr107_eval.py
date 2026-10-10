"""iter_107 평가: CURE 단일 phrase 출력(M47)과 저장된 MedGrounder A_U_e5 (threshold 0.8 / 0.4)의 coverage·사건 비교.

결과를 보기 전에 고정한 분기 규칙(plan decision_contract + 아래 BRANCH_RULE):
  N = 핵심 10개 중 CURE 'partial_omission' 수, persist = 그 중 MG0.8과 MG0.4 모두 partial_omission인 수,
  resolved = 그 중 MG0.4가 both_retained 인 수.
  N==0 → negative / 1<=N<=2 → inconclusive / N>=3: persist>=3 → positive_exploratory, 아니면 resolved*2>N → simple_alternative_explains, 아니면 inconclusive.
이 분기는 탐색 기준이며 확증이 아니다. 47개 전체는 기술통계(환자 bootstrap 10,000회, seed 107).
"""
import json
import sys
from pathlib import Path

import numpy as np

import nr107_run as RUN
import nr107_spec as S
from report86_common import ROOT, sha, sha_obj, save, read_jsonl_complete

OUT = ROOT / "results/iter_107/eval"
GEN = ROOT / "results/iter_107/gen/M47"
SYSTEMS = ("CURE", "MG_0.8", "MG_0.4")
BRANCH_RULE = "N==0 negative; 1-2 inconclusive; N>=3: persist>=3 positive_exploratory; elif resolved*2>N simple_alternative_explains; else inconclusive"


def load_cure():
    sd = sha_obj(RUN.scientific_protocol("M47", 2))
    c = json.loads((GEN / "completion.json").read_text())
    for name, h in c["files"].items():
        assert sha(GEN / name) == h
    recs = {}
    for k in range(2):
        _, rs = RUN.verify_completion(GEN / "cure" / f"shard{k}", "M47", k, 2, sd)
        for r in rs:
            assert r["id"] not in recs
            recs[r["id"]] = r
    assert set(recs) == {q["id"] for q in RUN.requests("M47")} and len(recs) == 47
    return recs, sd, c


def system_boxes(it, system, recs):
    if system == "CURE":
        r = recs[S.request_id(it["ImageID"], it["finding_index"])]
        p = S.parse_pg(r["text"], r["attempts"][-1]["ended_eos"])
        return p["boxes"], {"status": p["status"], "n_groups": p["n_groups"], "n_bad": p["n_bad"], "n_attempts": len(r["attempts"]),
                            "final_eos": r["attempts"][-1]["ended_eos"]}
    thr = system.split("_")[1]
    b = it["mg"][thr]["boxes"]
    return b, {"status": "valid_nonempty" if b else "no_box", "n_groups": len(b), "n_bad": 0, "n_attempts": 1, "final_eos": True}


def boot_ci(vals_by_patient, rng, n=10000):
    v = np.asarray(vals_by_patient, float)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    means = v[idx].mean(1)
    return float(v.mean()), [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def main():
    recs, sd, comp = load_cure()
    items = RUN.all_items()
    rows = []
    for it in items:
        row = {"item_key": it["item_key"], "ImageID": it["ImageID"], "PatientID": it["PatientID"], "sentence": it["sentence"], "n_gt": it["n_gt"],
               "n_extra": it["n_extra"], "core": it["core"], "sys": {}}
        for system in SYSTEMS:
            boxes, st = system_boxes(it, system, recs)
            m = {"pred": boxes, **st, "n_pred": len(boxes), "official": S.item_metrics(boxes, it["gt"])}
            if it["extra"]:
                m["alt"] = S.item_metrics(boxes, it["extra"])
            if it["core"]:
                ev, cov = S.classify_event(boxes, it["gt"], it["extra"], it["pairing"])
                m["event"], m["event_cov"] = ev, cov
            row["sys"][system] = m
        rows.append(row)
    core = [r for r in rows if r["core"]]
    events = {s: {} for s in SYSTEMS}
    for s in SYSTEMS:
        for r in core:
            e = r["sys"][s]["event"]
            events[s][e] = events[s].get(e, 0) + 1
    cure_partial = [r for r in core if r["sys"]["CURE"]["event"] == "partial_omission"]
    N = len(cure_partial)
    persist = [r for r in cure_partial if r["sys"]["MG_0.8"]["event"] == "partial_omission" and r["sys"]["MG_0.4"]["event"] == "partial_omission"]
    resolved = [r for r in cure_partial if r["sys"]["MG_0.4"]["event"] == "both_retained"]
    resolved08 = [r for r in cure_partial if r["sys"]["MG_0.8"]["event"] == "both_retained"]
    if N == 0:
        branch = "negative"
    elif N <= 2:
        branch = "inconclusive"
    elif len(persist) >= 3:
        branch = "positive_exploratory"
    elif len(resolved) * 2 > N:
        branch = "simple_alternative_explains"
    else:
        branch = "inconclusive"
    # 47개 전체 기술통계 (환자 단위 평균 → 환자 bootstrap)
    rng = np.random.default_rng(107)
    pats = sorted({r["PatientID"] for r in rows})

    def per_patient(f):
        out = []
        for p in pats:
            v = [f(r) for r in rows if r["PatientID"] == p]
            v = [x for x in v if x is not None]
            out.append(np.mean(v) if v else np.nan)
        return np.array(out)

    desc = {}
    for s in SYSTEMS:
        d = {}
        for name, f in (("union_iou_official", lambda r, s=s: r["sys"][s]["official"]["union_iou"]),
                        ("union_iou_alt", lambda r, s=s: r["sys"][s]["alt"]["union_iou"] if "alt" in r["sys"][s] else None),
                        ("cov_mean_official", lambda r, s=s: r["sys"][s]["official"]["cov_mean"]),
                        ("cov_min_official", lambda r, s=s: r["sys"][s]["official"]["cov_min"]),
                        ("all_cov_ge_0.5_official", lambda r, s=s: float(r["sys"][s]["official"]["all_cov_ge_0.5"])),
                        ("recall03_official", lambda r, s=s: r["sys"][s]["official"]["match03"] / r["sys"][s]["official"]["n_gt"]),
                        ("outside_frac_official", lambda r, s=s: r["sys"][s]["official"]["outside_frac"]),
                        ("n_pred", lambda r, s=s: float(r["sys"][s]["n_pred"]))):
            v = per_patient(f)
            ok = ~np.isnan(v)
            mean, ci = boot_ci(v[ok], rng)
            d[name] = {"mean": mean, "ci95": ci, "n_patients": int(ok.sum())}
        d["status_counts"] = {}
        for r in rows:
            st = r["sys"][s]["status"]
            d["status_counts"][st] = d["status_counts"].get(st, 0) + 1
        desc[s] = d
    paired = {}
    for other in ("MG_0.8", "MG_0.4"):
        def metric(r, s, name):
            m = r["sys"][s]["official"]
            return {"union_iou_official": m["union_iou"], "cov_mean_official": m["cov_mean"], "recall03_official": m["match03"] / m["n_gt"]}[name]
        for name in ("union_iou_official", "cov_mean_official", "recall03_official"):
            a = per_patient(lambda r, n=name: metric(r, "CURE", n))
            b = per_patient(lambda r, n=name, o=other: metric(r, o, n))
            mean, ci = boot_ci(a - b, rng)
            paired["CURE-%s:%s" % (other, name)] = {"mean": mean, "ci95": ci}
    report = {
        "label": "repeated development material (PadChest-GR train V96); diagnostic descriptive, not confirmatory; pretraining exposure unconfirmed",
        "n_items": len(rows), "n_patients": len(pats), "n_core": len(core), "branch_rule": BRANCH_RULE, "branch": branch,
        "core": {"events": events, "cure_partial_n": N, "persist_both_mg_n": len(persist), "resolved_mg04_n": len(resolved), "resolved_mg08_n": len(resolved08),
                 "cure_partial_item_keys": [r["item_key"] for r in cure_partial], "persist_item_keys": [r["item_key"] for r in persist],
                 "ambiguous_cure_n": events["CURE"].get("ambiguous", 0)},
        "all47_descriptive_patient_bootstrap": desc, "paired_cure_minus_mg_patient_bootstrap": paired, "rows": rows,
        "provenance": {"items_sha256": sha(RUN.DATA / "items.json"), "raw_manifest_sha256": sha(RUN.DATA / "raw_manifest.json"),
                       "cure_scientific_digest": sd, "cure_completion_sha256": sha(GEN / "completion.json"),
                       "eval_sources": {f: sha(ROOT / f) for f in ("nr107_eval.py", "nr107_spec.py", "nr107_geom.py")},
                       "mg_raw_sha256": json.loads((RUN.DATA / "cohort_summary.json").read_text())["mg_raw_sha256"]}}
    save(OUT / "report.json", report)
    print(json.dumps({k: report[k] for k in ("n_items", "n_patients", "n_core", "branch", "core")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
