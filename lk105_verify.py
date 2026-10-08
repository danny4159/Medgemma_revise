"""iter_105 독립 재계산: lk105_spec/lk105_eval을 import하지 않고 원시 outputs.jsonl + inputs_*.json에서 주요 수치를 다시 계산해 report와 대조한다.

사용: python lk105_verify.py REPORT.json OUT.json WORKERS STAGE:GENDIR [STAGE:GENDIR ...]
검증 대상: 모델×parser별 8개 조건 정확도, 주요 paired 차이·CI(같은 seed/절차의 bootstrap), N→W 전환 수, PG 정확도, 요청 수/중복.
"""
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "results/iter_105/data"


def strip_think(t):
    if "<unused94>" in t or "<unused95>" in t:
        if "<unused95>" not in t:
            return None
        return t.rsplit("<unused95>", 1)[1]
    return t


def strict(text, eos):
    if not eos:
        return None
    t = strip_think(text)
    if t is None:
        return None
    t = t.strip()
    for tok in ("<end_of_turn>", "<eos>"):
        if t.endswith(tok):
            t = t[:-len(tok)].strip()
    if t.endswith("."):
        t = t[:-1].strip()
    return t if t in ("A", "B") else None


def lenient(text, eos):
    a = strict(text, eos)
    if a or not eos:
        return a
    t = strip_think(text)
    if t is None:
        return None
    t = t.strip()
    for tok in ("<end_of_turn>", "<eos>"):
        if t.endswith(tok):
            t = t[:-len(tok)].strip()
    t1 = t[:-1].strip() if t.endswith(".") else t
    if t1 == "A: S1 is in R1 and S2 is in R2":
        return "A"
    if t1 == "B: S1 is in R2 and S2 is in R1":
        return "B"
    found = set(m.upper() for m in re.findall(r"answer\s+is\s*[:*$\\\s]*(?:boxed\{)?\s*([ABab])\b", t))
    return found.pop() if len(found) == 1 else None


def iou(a, b):
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = w * h
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def pg_boxes(system, text, eos, size):
    if not eos:
        return []
    if system == "CURE":
        out = []
        for m in re.finditer(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", text):
            cx, cy, w, h = [float(x) for x in m.groups()]
            if w <= 0 or h <= 0 or not all(0 <= v <= 1 for v in (cx, cy, w, h)):
                return []
            out.append([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
        return out
    t = strip_think(text)
    if t is None:
        return []
    t = t.replace("<end_of_turn>", "")
    t = re.sub(r"```(?:json)?", " ", t)
    i = t.find("[")
    if i < 0:
        return []
    try:
        val, _ = json.JSONDecoder().raw_decode(t[i:])
    except Exception:
        return []
    W, H = size
    side = max(W, H)
    top = (side - H) // 2 if H < W else 0
    left = (side - W) // 2 if W < H else 0
    boxes = []
    for e in val if isinstance(val, list) else []:
        b = e.get("box_2d") if isinstance(e, dict) else None
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)):
            return []
        if any(v < 0 or v > 1000 for v in b) or not (b[0] < b[2] and b[1] < b[3]):
            return []
        px0, py0 = b[1] * side / 1000 - left, b[0] * side / 1000 - top
        px1, py1 = b[3] * side / 1000 - left, b[2] * side / 1000 - top
        boxes.append([px0 / W, py0 / H, px1 / W, py1 / H])
    return boxes


def boot(x, n=10000, seed=105017):
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    v = x[idx].mean(axis=1)
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def recompute(stages_dirs, workers):
    wk = (lambda system: workers[system]) if isinstance(workers, dict) else (lambda system: workers)
    rows = []
    for st, gd in stages_dirs:
        for r in json.loads((DATA / f"inputs_{st}.json").read_text()):
            rows.append((st, gd, r))
    res = {}
    for system, tag in (("CURE", "cure"), ("M15", "m15")):
        recs = {}
        n_lines = 0
        for st, gd in stages_dirs:
            for k in range(wk(system)):
                for ln in open(Path(gd) / tag / f"shard{k}" / "outputs.jsonl"):
                    if ln.strip():
                        r = json.loads(ln)
                        n_lines += 1
                        assert r["id"] not in recs, "duplicate id"
                        recs[r["id"]] = r
        assert len(recs) == n_lines == 14 * len(rows)
        out = {}
        for pname, parser in (("strict", strict), ("lenient_v1", lenient)):
            acc = {}
            for mod in ("img", "txt"):
                for c in "NCW":
                    v = []
                    for st, gd, r in rows:
                        s = 0
                        for o in (0, 1):
                            rec = recs[f"{r['ImageID']}|{system}|{mod}-{c}-o{o}"]
                            ans = parser(rec["text"], rec["attempts"][-1]["ended_eos"])
                            s += ans == ("A" if o == 0 else "B")
                        v.append(s / 2)
                    acc[f"{mod}_{c}"] = np.array(v)
            pg = []
            for st, gd, r in rows:
                bx = []
                for k in ("S1", "S2"):
                    rec = recs[f"{r['ImageID']}|{system}|pg-{k}"]
                    bx.append(pg_boxes(system, rec["text"], rec["attempts"][-1]["ended_eos"], r["size"]))
                sa = max([iou(b, r["box1"]) for b in bx[0]] or [0]) + max([iou(b, r["box2"]) for b in bx[1]] or [0])
                sb = max([iou(b, r["box2"]) for b in bx[0]] or [0]) + max([iou(b, r["box1"]) for b in bx[1]] or [0])
                pg.append(1.0 if sa > sb else 0.0)
            acc["PG"] = np.array(pg)
            tr = 0
            for st, gd, r in rows:
                for o in (0, 1):
                    rn = recs[f"{r['ImageID']}|{system}|img-N-o{o}"]
                    rw = recs[f"{r['ImageID']}|{system}|img-W-o{o}"]
                    g = "A" if o == 0 else "B"
                    if parser(rn["text"], rn["attempts"][-1]["ended_eos"]) == g and parser(rw["text"], rw["attempts"][-1]["ended_eos"]) != g:
                        tr += 1
            d = acc["img_N"] - acc["img_W"]
            out[pname] = {"acc_mean": {k: float(v.mean()) for k, v in acc.items()},
                          "N_minus_W": {"mean": float(d.mean()), "ci95": boot(d)},
                          "N_minus_TextN": {"mean": float((acc["img_N"] - acc["txt_N"]).mean()), "ci95": boot(acc["img_N"] - acc["txt_N"])},
                          "C_minus_N": {"mean": float((acc["img_C"] - acc["img_N"]).mean()), "ci95": boot(acc["img_C"] - acc["img_N"])},
                          "N_right_to_W_wrong_requests": tr}
        res[system] = out
    return res


def main():
    report = json.load(open(sys.argv[1]))
    out = Path(sys.argv[2])
    workers = {x.split('=')[0]: int(x.split('=')[1]) for x in sys.argv[3].split(',')} if '=' in sys.argv[3] else int(sys.argv[3])
    sd = [tuple(x.split(":")) for x in sys.argv[4:]]
    rc = recompute(sd, workers)
    checks = []
    for system, o in rc.items():
        for pname, v in o.items():
            rep = report["summary"][system][pname]
            for k, x in v["acc_mean"].items():
                key = {"PG": "PG"}.get(k, k)
                checks.append((f"{system}/{pname}/acc/{k}", abs(rep["acc"][key]["mean"] - x) < 1e-9))
            for k in ("N_minus_W", "N_minus_TextN", "C_minus_N"):
                checks.append((f"{system}/{pname}/{k}/mean", abs(rep["paired"][k]["mean"] - v[k]["mean"]) < 1e-9))
                checks.append((f"{system}/{pname}/{k}/ci", all(abs(a - b) < 1e-9 for a, b in zip(rep["paired"][k]["ci95"], v[k]["ci95"]))))
            checks.append((f"{system}/{pname}/transition_requests", rep["transitions"]["N_right_to_W_wrong"]["requests"] == v["N_right_to_W_wrong_requests"]))
    ok = all(c for _, c in checks)
    with out.open("x") as f:
        json.dump({"all_pass": ok, "n_checks": len(checks), "checks": [{"name": n, "pass": bool(c)} for n, c in checks], "recomputed": rc}, f, indent=1)
    print(len(checks), "all_pass" if ok else "FAIL", [n for n, c in checks if not c][:10])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
