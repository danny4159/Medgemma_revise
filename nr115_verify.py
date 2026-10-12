"""iter_115 독립 검산: nr107_geom/nr113/nr114/nr115_core 를 import 하지 않고 ledger_final.json 과 report.json 에서 직접
(1) 87/68/37/K22, 포착 16/15/13, 차별 7/6·공통 9·미포착 15, disagree 26/no_alt 16 을 재계산하고
(2) 좌표 격자(numpy 셀 마스크)로 면적·union IoU·u_j·유형을 다시 계산해 table87.json 과 대조한다.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
R114 = ROOT / "results/iter_114"
OUT = ROOT / "results/iter_115"


def grid_masks(sets):
    xs = sorted({v for s in sets for b in s for v in (b[0], b[2])})
    ys = sorted({v for s in sets for b in s for v in (b[1], b[3])})
    if len(xs) < 2 or len(ys) < 2:
        return None, None, [np.zeros((1, 1), bool) for _ in sets]
    xc, yc = np.array(xs), np.array(ys)
    cx0, cx1, cy0, cy1 = xc[:-1], xc[1:], yc[:-1], yc[1:]
    cell = (cx1 - cx0)[:, None] * (cy1 - cy0)[None, :]
    masks = []
    for s in sets:
        m = np.zeros(cell.shape, bool)
        for b in s:
            m |= ((cx0 >= b[0] - 1e-15) & (cx1 <= b[2] + 1e-15))[:, None] & ((cy0 >= b[1] - 1e-15) & (cy1 <= b[3] + 1e-15))[None, :]
        masks.append(m)
    return cell, None, masks


def areas(a, b):
    """a, b: box 리스트. 반환 (area a, area b, area a∩b), 빈 집합 허용."""
    cell, _, (ma, mb) = grid_masks([a, b])
    if cell is None:
        return 0.0, 0.0, 0.0
    return float((cell * ma).sum()), float((cell * mb).sum()), float((cell * (ma & mb)).sum())


def uiou(a, b):
    if not a or not b:
        return 0.0
    ua, ub, i = areas(a, b)
    return i / (ua + ub - i) if (ua + ub - i) > 0 else 0.0


def err(m, g):
    return 1 if (not m or uiou(m, g) < 0.3) else 0


def ufrac(m, g):
    if not m:
        return 0.0
    ua, ug, i = areas(m, [g])
    return i / ug


def gtype(m, gts):
    if not gts:
        return "NA"
    if not m:
        return "empty_pred"
    if uiou(m, gts) >= 0.3:
        return "iou_ok"
    ua, ug, i = areas(m, gts)
    if i <= 1e-15:
        return "no_overlap"
    u = [ufrac(m, g) for g in gts]
    if len(gts) >= 2 and any(x >= 0.3 for x in u) and any(x < 0.3 for x in u):
        return "partial_low_coverage"
    if all(x >= 0.3 for x in u):
        return "all_covered_area_mismatch"
    return "other_overlap"


def sha(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


def main():
    chk = {}
    L = json.loads((R114 / "analysis_r1/ledger_final.json").read_text())["ledger"]
    rep = json.loads((R114 / "analysis_r1/result_final/report.json").read_text())
    rows = {r["item_key"]: r for r in json.loads((OUT / "table87.json").read_text())}
    L = [l for l in L if not l.get("excluded_from_ranking")]
    N = len(L)
    chk["N=87"] = N == 87
    chk["patients=68"] = len({l["PatientID"] for l in L}) == 68
    Kk = math.ceil(N / 4)
    chk["K=22"] = Kk == 22

    def risk_d(m, c):
        if not m and not c:
            return 0.0
        if not m or not c:
            return 1.0
        return 1.0 - uiou(m, c)
    tk = lambda l: hashlib.sha256(f"iter114|{l['item_key']}".encode()).hexdigest()
    rk = {"cure": [risk_d(l["M"], l["C"]) for l in L], "mspc": [risk_d(l["M"], l["P"]) for l in L],
          "conf": [1.0 if not l["M_scores"] else 1.0 - min(l["M_scores"]) for l in L]}
    sel = {}
    for f, v in rk.items():
        order = sorted(range(N), key=lambda i: (-v[i], tk(L[i])))
        sel[f] = {L[i]["item_key"] for i in order[:Kk]}
    E = {l["item_key"]: err(l["M"], l["GT"]) for l in L}
    chk["errors_official=37"] = sum(E.values()) == 37
    cap = {f: sum(E[k] for k in s) for f, s in sel.items()}
    chk["capture 16/15/13"] = (cap["cure"], cap["mspc"], cap["conf"]) == (16, 15, 13)
    errs = [k for k in E if E[k]]
    a_only = [k for k in errs if k in sel["cure"] and k not in sel["mspc"]]
    b_only = [k for k in errs if k in sel["mspc"] and k not in sel["cure"]]
    both = [k for k in errs if k in sel["cure"] and k in sel["mspc"]]
    neither = [k for k in errs if k not in sel["cure"] and k not in sel["mspc"]]
    chk["7/6/9/15"] = (len(a_only), len(b_only), len(both), len(neither)) == (7, 6, 9, 15)
    comp = rep["complementarity_B"]
    chk["sets equal report"] = (set(a_only) == set(comp["a_only_errors"]) and set(b_only) == set(comp["b_only_errors"])
                                and set(both) == set(comp["both_errors"]) and set(neither) == set(comp["neither_errors"]))
    st = {"disagree": 0, "no_alt": 0}
    for l in L:
        if not l["ALT"]:
            st["no_alt"] += 1
        elif err(l["M"], l["ALT"]) != E[l["item_key"]]:
            st["disagree"] += 1
    chk["disagree=26,no_alt=16"] = (st["disagree"], st["no_alt"]) == (26, 16)
    # 표와의 행별 대조
    bad = []
    for l in L:
        r = rows[l["item_key"]]
        exp = {"type_GT": gtype(l["M"], l["GT"]), "type_ALT": gtype(l["M"], l["ALT"]), "iou_M_GT": uiou(l["M"], l["GT"]),
               "iou_C_GT": uiou(l["C"], l["GT"]), "iou_P_GT": uiou(l["P"], l["GT"]),
               "area_M": areas(l["M"], [])[0], "area_GT": areas(l["GT"], [])[0]}
        for k, v in exp.items():
            if isinstance(v, float):
                if abs(v - r[k]) > 1e-9:
                    bad.append((l["item_key"], k, v, r[k]))
            elif v != r[k]:
                bad.append((l["item_key"], k, v, r[k]))
        uu = [ufrac(l["M"], g) for g in l["GT"]]
        if max(abs(a - b) for a, b in zip(uu, r["u_GT"])) > 1e-9:
            bad.append((l["item_key"], "u_GT"))
        if r["error_official"] != E[l["item_key"]] or r["sel_cure"] != (l["item_key"] in sel["cure"]) or r["sel_mspc"] != (l["item_key"] in sel["mspc"]) or r["sel_conf"] != (l["item_key"] in sel["conf"]):
            bad.append((l["item_key"], "flags"))
    chk["table87 row-wise geometry match"] = not bad
    # 13개 사례표
    cases = json.loads((OUT / "cases13.json").read_text())
    chk["cases13 = a_only+b_only"] = {c["item_key"] for c in cases} == set(a_only) | set(b_only) and len(cases) == 13
    chk["overlays 13"] = len(list((OUT / "overlays").glob("*.png"))) == 13
    out = {"all_pass": all(chk.values()), "checks": chk, "mismatches": bad[:10], "independent_of": ["nr107_geom", "nr113_core", "nr114_core", "nr115_core"],
           "checked_digests": {n: sha(OUT / n) for n in ("table87.json", "groups.json", "cases13.json", "provenance.json", "protocol.json", "analysis_done.json")}}
    out["checked_digests"].update({c: sha(ROOT / c) for c in ("nr115_verify.py", "nr115_core.py", "nr115_run.py")})
    p = OUT / "verify.json"
    if "--write" in sys.argv:
        if p.exists():
            raise SystemExit("verify.json exists")
        p.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({"all_pass": out["all_pass"], "checks": chk}, indent=1))
    sys.exit(0 if out["all_pass"] else 1)


if __name__ == "__main__":
    main()
