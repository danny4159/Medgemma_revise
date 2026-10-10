"""iter_107 독립 재계산: production 함수(nr107_geom/nr107_spec/nr107_eval)를 호출하지 않고 원시 출력·manifest에서
(1) 정규식 parser, (2) 2400x2400 래스터 기하(셀 중심 샘플링)로 coverage·union IoU·사건·분기를 다시 계산해 report.json과 대조한다.
래스터 근사 허용오차 3e-3, 사건/분기 판정은 정확히 일치해야 한다. 불일치가 있으면 비정상 종료한다."""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
N = 2400


def mask(boxes):
    m = np.zeros((N, N), bool)
    for b in boxes:
        x0, x1 = int(np.ceil(b[0] * N - 0.5)), int(np.ceil(b[2] * N - 0.5))
        y0, y1 = int(np.ceil(b[1] * N - 0.5)), int(np.ceil(b[3] * N - 0.5))
        m[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = True
    return m


def cov(pred, g, n=800):
    """GT box 내부를 n x n 셀 중심으로 샘플링(작은 GT box도 상대 오차 ~1/n)해 예측 합집합에 속하는 비율."""
    xs = g[0] + (np.arange(n) + 0.5) / n * (g[2] - g[0])
    ys = g[1] + (np.arange(n) + 0.5) / n * (g[3] - g[1])
    X, Y = np.meshgrid(xs, ys)
    hit = np.zeros_like(X, bool)
    for b in pred:
        hit |= (X >= b[0]) & (X < b[2]) & (Y >= b[1]) & (Y < b[3])
    return float(hit.mean())


def uiou(pred, gts):
    a, b = mask(pred), mask(gts)
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def parse(text, eos):
    if not eos:
        return "truncated", []
    groups = re.findall(r"\[([^\[\]]*)\]", text)
    rest = re.sub(r"\[[^\[\]]*\]", "", text)
    bad_m = bad_c = 0
    out = []
    for g in groups:
        parts = [p.strip() for p in g.split(",")]
        try:
            if len(parts) != 4:
                raise ValueError
            c = [float(p) for p in parts]
        except ValueError:
            bad_m += 1
            continue
        if not all(np.isfinite(c)) or c[2] <= 0 or c[3] <= 0 or min(c) < 0 or max(c) > 1:
            bad_c += 1
            continue
        xy = [c[0] - c[2] / 2, c[1] - c[3] / 2, c[0] + c[2] / 2, c[1] + c[3] / 2]
        if xy[0] < 0 or xy[1] < 0 or xy[2] > 1 or xy[3] > 1:
            bad_c += 1
            continue
        out.append(xy)
    if bad_m or "[" in rest or "]" in rest:
        return "malformed", []
    if bad_c:
        return "coord_invalid", []
    return ("valid_nonempty", out) if out else ("no_box", [])


def main():
    rep = json.loads((ROOT / "results/iter_107/eval/report.json").read_text())
    items = {it["item_key"]: it for it in json.loads((ROOT / "results/iter_107/data/items.json").read_text())}
    recs = {}
    for k in (0, 1):
        for l in (ROOT / f"results/iter_107/gen/M47/cure/shard{k}/outputs.jsonl").read_text().splitlines():
            r = json.loads(l)
            recs[r["item_key"]] = r
    assert len(recs) == 47
    # manifest 대조: 문장·GT·extra
    man = {}
    for l in (ROOT / "results/iter_039/data/manifest_private.jsonl").read_text().splitlines():
        m = json.loads(l)
        man[m["PatientID"]] = m
    maxdiff, problems = 0.0, []
    ev_pred = {s: {} for s in ("CURE", "MG_0.8", "MG_0.4")}
    for row in rep["rows"]:
        it = items[row["item_key"]]
        m = man[it["PatientID"]]
        t = it["target"]
        if not (m["sentences"][t] == it["sentence"] and m["gt_boxes_xyxy_norm"][t] == it["gt"] and m["extra_boxes_xyxy_norm"][t] == it["extra"]
                and m["finding_index"][t] == it["finding_index"]):
            problems.append(("manifest link", it["item_key"]))
        r = recs[it["item_key"]]
        assert r["prompt"] == "Ground the phrase: " + it["sentence"]
        st, cure_boxes = parse(r["text"], r["attempts"][-1]["ended_eos"])
        preds = {"CURE": cure_boxes, "MG_0.8": it["mg"]["0.8"]["boxes"], "MG_0.4": it["mg"]["0.4"]["boxes"]}
        if st != row["sys"]["CURE"]["status"]:
            problems.append(("status", it["item_key"], st))
        for s, pb in preds.items():
            o = row["sys"][s]
            for i, g in enumerate(it["gt"]):
                d = abs(cov(pb, g) - o["official"]["cov"][i])
                maxdiff = max(maxdiff, d)
                if d > 3e-3:
                    problems.append(("cov", it["item_key"], s, i, d))
            d = abs(uiou(pb, it["gt"]) - o["official"]["union_iou"])
            maxdiff = max(maxdiff, d)
            if d > 3e-3:
                problems.append(("uiou", it["item_key"], s, d))
            if it["extra"]:
                d = abs(uiou(pb, it["extra"]) - o["alt"]["union_iou"])
                maxdiff = max(maxdiff, d)
                if d > 3e-3:
                    problems.append(("uiou_alt", it["item_key"], s, d))
        if it["core"]:
            pair = it["pairing"]
            # 독립 핵심 규칙 재확인: 래스터 IoU >= 0.5 대응, 집합 내부 겹침 없음
            def rI(a, b):
                A, B = mask([a]), mask([b])
                return (A & B).sum() / max((A | B).sum(), 1)
            ok = (not (mask([it["gt"][0]]) & mask([it["gt"][1]])).any() and not (mask([it["extra"][0]]) & mask([it["extra"][1]])).any()
                  and all(rI(it["gt"][k], it["extra"][pair[k]]) >= 0.5 for k in (0, 1)))
            if not ok:
                problems.append(("core rule", it["item_key"]))
            for s, pb in preds.items():
                dirs = []
                for k in (0, 1):
                    cg, ce = cov(pb, it["gt"][k]), cov(pb, it["extra"][pair[k]])
                    dirs.append("R" if (cg >= 0.5 and ce >= 0.5) else ("M" if (cg <= 0.1 and ce <= 0.1) else "A"))
                ev = "ambiguous" if "A" in dirs else ("both_retained" if dirs == ["R", "R"] else ("both_missing" if dirs == ["M", "M"] else "partial_omission"))
                ev_pred[s][it["item_key"]] = ev
                if ev != o_ev(row, s):
                    problems.append(("event", it["item_key"], s, ev, o_ev(row, s)))
    # 비핵심 소견이 핵심 규칙에 해당하는지(누락 확인): 독립 규칙으로 core 집합 일치
    n_core = sum(1 for it in items.values() if it["core"])
    N_cure = sum(1 for v in ev_pred["CURE"].values() if v == "partial_omission")
    persist = sum(1 for k, v in ev_pred["CURE"].items() if v == "partial_omission" and ev_pred["MG_0.8"][k] == "partial_omission" and ev_pred["MG_0.4"][k] == "partial_omission")
    resolved = sum(1 for k, v in ev_pred["CURE"].items() if v == "partial_omission" and ev_pred["MG_0.4"][k] == "both_retained")
    branch = "negative" if N_cure == 0 else ("inconclusive" if N_cure <= 2 else ("positive_exploratory" if persist >= 3 else
                                                                                ("simple_alternative_explains" if resolved * 2 > N_cure else "inconclusive")))
    if branch != rep["branch"]:
        problems.append(("branch", branch, rep["branch"]))
    # 환자 평균 요약 대조(점추정만)
    pats = sorted({r["PatientID"] for r in rep["rows"]})
    chk_means = {}
    for s in ("CURE", "MG_0.8", "MG_0.4"):
        v = []
        for p in pats:
            xs = [r["sys"][s]["official"]["union_iou"] for r in rep["rows"] if r["PatientID"] == p]
            v.append(np.mean(xs))
        chk_means[s] = abs(float(np.mean(v)) - rep["all47_descriptive_patient_bootstrap"][s]["union_iou_official"]["mean"])
    out = {"n_rows": len(rep["rows"]), "n_core": n_core, "max_abs_raster_diff": maxdiff, "problems": problems, "branch_independent": branch,
           "events_independent": {s: {k[-6:]: v for k, v in d.items()} for s, d in ev_pred.items()}, "union_iou_patient_mean_diff": chk_means,
           "report_sha256": __import__("hashlib").sha256((ROOT / "results/iter_107/eval/report.json").read_bytes()).hexdigest(), "pass": not problems}
    p = ROOT / "results/iter_107/eval/verify_v2.json"
    with p.open("x") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in ("n_rows", "n_core", "max_abs_raster_diff", "problems", "branch_independent", "pass")}))
    return 0 if out["pass"] else 1


def o_ev(row, s):
    return row["sys"][s]["event"]


if __name__ == "__main__":
    sys.exit(main())
