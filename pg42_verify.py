"""iter_042 독립 재계산 (pg42_spec/pg39_spec/rsna_diag.parse 미사용; pg41_verify의 canvas·iou·max_matching·f1만 재사용).
원시 record의 suffix_text_raw에서 코드펜스만 제거한 뒤 전체 문자열을 JSON으로 해석(요청 라벨 qA 필수)하고 P는 yes/no 정규화.
report_E_per_patient.json의 환자별 값과 대조하고 주 CI를 별도 난수 경로로 재계산한다.
python pg42_verify.py --report results/iter_042/eval/report_E.json --out results/iter_042/eval/verify_E.json
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

import pg41_verify as V

OUT = "results/iter_042"
EOT = "<end_of_turn>"
TOLERANT = False


def read(name):
    out = {}
    for fn in sorted(glob.glob(f"{OUT}/gen/{name}/gen_worker*.jsonl")):
        for ln in open(fn):
            if ln.strip():
                r = json.loads(ln)
                assert (r["patient"], r["cond"]) not in out
                out[(r["patient"], r["cond"])] = r
    return out


def g_parse(r):
    """returns 'invalid' | list of boxes (empty list = valid empty)."""
    if not r["ended_eos"]:
        return "invalid"
    t = r["suffix_text_raw"]
    t = t[:-len(EOT)] if t.endswith(EOT) else t
    t = re.sub(r"```(?:json)?", "", t).strip()
    try:
        arr = json.loads(t)
    except Exception:
        if not TOLERANT:
            return "invalid"
        try:  # 관대 변형: 첫 완결 JSON 값만 취하고 뒤 잔여 문자열(예: 여분의 ']')은 무시 (pipeline parser의 완결 목록 추출과 같은 규칙)
            arr, _ = json.JSONDecoder().raw_decode(t)
        except Exception:
            return "invalid"
    if not isinstance(arr, list):
        return "invalid"
    boxes = []
    for e in arr:
        if not (isinstance(e, dict) and set(e) == {"box_2d", "label"} and e["label"] == "qA"):
            return "invalid"
        b = e["box_2d"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b)
                and 0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000):
            return "invalid"
        boxes.append([float(v) for v in b])
    return boxes


def p_parse(r):
    if not r["ended_eos"]:
        return "invalid"
    t = r["suffix_text_raw"]
    t = t[:-len(EOT)] if t.endswith(EOT) else t
    t = t.strip().rstrip(".!").strip().lower()
    return t if t in ("yes", "no") else "invalid"


def boot(d, level, B=10000, seed=777):
    d = np.asarray(d, float)
    idx = np.random.default_rng(seed).integers(0, len(d), size=(B, len(d)))
    m = d[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return [float(d.mean()), float(np.percentile(m, a)), float(np.percentile(m, 100 - a))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tolerant", action="store_true")
    a = ap.parse_args()
    global TOLERANT
    TOLERANT = a.tolerant
    res_mode = "tolerant" if a.tolerant else "strict"
    if os.path.exists(a.out):
        sys.exit("output exists")
    rep = json.load(open(a.report))
    pp = json.load(open(a.report.replace(".json", "_per_patient.json")))
    man = {}
    for l in open(f"{OUT}/data/manifest_private.jsonl"):
        r = json.loads(l)
        if r["set"] == "E":
            man[r["PatientID"]] = r
    R = {"M0": read("E_M0"), "C": read("E_C")}
    pos_ids, neg_ids = pp["pos_ids"], pp["neg_ids"]
    assert set(pos_ids) | set(neg_ids) == set(man) and len(man) == len(pos_ids) + len(neg_ids)

    def out(pid, name):
        if name.startswith("gate_"):
            pl = p_parse(R["M0" if name == "gate_P0" else "C"][(pid, "P")])
            if pl == "invalid":
                return "invalid"
            return [] if pl == "no" else g_parse(R["C"][(pid, "G_neutral")])
        mod, c = name.split("_")
        return g_parse(R[mod][(pid, "G_" + c)])
    names = ["M0_short", "M0_neutral", "C_short", "C_neutral", "gate_P0", "gate_PC"]
    f1 = {n: [] for n in names}
    fb = {n: [] for n in names}
    inv_neg = {n: 0 for n in names}
    for pid in pos_ids:
        m = man[pid]
        h, w = m["image_meta"]["h"], m["image_meta"]["w"]
        gt = [V.canvas(b, h, w) for b in m["gt_boxes_xyxy_norm"]["qA"]]
        for n in names:
            o = out(pid, n)
            f1[n].append(0.0 if o == "invalid" else V.f1(o, gt, 0.3))
    for pid in neg_ids:
        for n in names:
            o = out(pid, n)
            fb[n].append(float(o != "invalid" and len(o) > 0))
            inv_neg[n] += o == "invalid"
    res = {"mode": res_mode, "max_abs_diff_pos_f1_vs_report": max(max(abs(x - y["f1_03"]) for x, y in zip(f1[n], pp["per_patient"][n]["pos"])) for n in names),
           "max_abs_diff_neg_false_box_vs_report": max(max(abs(x - float(y["false_box"])) for x, y in zip(fb[n], pp["per_patient"][n]["neg"]))
                                                        for n in names),
           "invalid_neg_match": all(inv_neg[n] == sum(y["invalid"] for y in pp["per_patient"][n]["neg"]) for n in names),
           "pos_f1_mean": {n: float(np.mean(f1[n])) for n in names}, "neg_false_box_count": {n: int(sum(fb[n])) for n in names},
           "C_minus_M0_short": {"pos_f1_ci975": boot(np.array(f1["C_short"]) - np.array(f1["M0_short"]), 0.975),
                                "neg_fb_ci975": boot(np.array(fb["C_short"]) - np.array(fb["M0_short"]), 0.975)},
           "C_minus_M0_neutral": {"pos_f1_ci975": boot(np.array(f1["C_neutral"]) - np.array(f1["M0_neutral"]), 0.975),
                                  "neg_fb_ci975": boot(np.array(fb["C_neutral"]) - np.array(fb["M0_neutral"]), 0.975)},
           "presence": {m: {"sens": sum(p_parse(R[m][(p, "P")]) == "yes" for p in pos_ids),
                            "spec": sum(p_parse(R[m][(p, "P")]) == "no" for p in neg_ids)} for m in ("M0", "C")}}
    res["report_presence_match"] = all(res["presence"][m]["sens"] == rep["presence"][m]["sensitivity"][0] and
                                       res["presence"][m]["spec"] == rep["presence"][m]["specificity"][0] for m in ("M0", "C"))
    res["report_outcome"] = rep["decision"]["outcome"]
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
