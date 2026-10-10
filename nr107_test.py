"""iter_107 CPU fixture: parser·기하·사건 규칙 (모델 미사용). 결과는 새 JSON으로만 저장하며 실패 시 비정상 종료한다."""
import json
import random
import sys

import nr107_geom as G
import nr107_spec as S
from report86_common import save, ROOT

R = []


def chk(name, cond, detail=None):
    R.append({"name": name, "pass": bool(cond), "detail": detail})


def grid_union(boxes, n=400):
    c = 0
    for i in range(n):
        x = (i + 0.5) / n
        for j in range(n):
            y = (j + 0.5) / n
            if any(b[0] <= x < b[2] and b[1] <= y < b[3] for b in boxes):
                c += 1
    return c / (n * n)


def main():
    P = S.parse_pg
    chk("parse valid single", P("Pleural effusion: [0.5,0.5,0.2,0.2]", True)["status"] == "valid_nonempty")
    r = P("Effusion: [0.30,0.40,0.2,0.2] and [0.7,0.6,0.2,0.2]", True)
    chk("parse valid two", r["status"] == "valid_nonempty" and len(r["boxes"]) == 2)
    chk("parse no_box prose", P("No finding visible.", True)["status"] == "no_box")
    chk("parse empty", P("", True)["status"] == "no_box")
    chk("parse truncated", P("Effusion: [0.3,0.4", False)["status"] == "truncated")
    chk("parse three numbers malformed", P("x: [0.3,0.4,0.2]", True)["status"] == "malformed")
    chk("parse five numbers malformed", P("x: [0.3,0.4,0.2,0.1,0.1]", True)["status"] == "malformed")
    chk("parse unclosed bracket malformed", P("x: [0.3,0.4,0.2,0.2", True)["status"] == "malformed")
    chk("parse nan coord_invalid", P("x: [nan,0.4,0.2,0.2]", True)["status"] == "coord_invalid")
    chk("parse inf coord_invalid", P("x: [0.3,inf,0.2,0.2]", True)["status"] == "coord_invalid")
    chk("parse nonpositive width", P("x: [0.3,0.4,0.0,0.2]", True)["status"] == "coord_invalid")
    chk("parse negative height", P("x: [0.3,0.4,0.2,-0.2]", True)["status"] == "coord_invalid")
    chk("parse >1 value", P("x: [1.3,0.4,0.2,0.2]", True)["status"] == "coord_invalid")
    chk("parse xyxy out of range not clipped", P("x: [0.98,0.5,0.1,0.1]", True)["status"] == "coord_invalid")
    chk("parse text non-number", P("x: [a,b,c,d]", True)["status"] == "malformed")
    m = P("x: [0.3,0.4,0.2,0.2] [0.3,0.4,0.2]", True)
    chk("parse partial valid -> malformed, boxes empty, valid kept", m["status"] == "malformed" and m["boxes"] == [] and len(m["valid_boxes"]) == 1)
    b = P("x: [0.5,0.5,0.2,0.4]", True)["boxes"][0]
    chk("cxcywh->xyxy", all(abs(u - v) < 1e-12 for u, v in zip(b, [0.4, 0.3, 0.6, 0.7])))

    chk("union of disjoint", abs(G.union_area([[0, 0, .2, .2], [.5, .5, .7, .7]]) - 0.08) < 1e-12)
    chk("union of overlapping", abs(G.union_area([[0, 0, .5, .5], [.25, .25, .75, .75]]) - (0.25 + 0.25 - 0.0625)) < 1e-12)
    chk("union duplicate", abs(G.union_area([[0, 0, .5, .5]] * 3) - 0.25) < 1e-12)
    chk("union nested", abs(G.union_area([[0, 0, 1, 1], [.2, .2, .4, .4]]) - 1.0) < 1e-12)
    rng = random.Random(107)
    ok = True
    for _ in range(25):
        bs = []
        for _ in range(rng.randint(1, 5)):
            x0, y0 = rng.random() * .8, rng.random() * .8
            bs.append([x0, y0, x0 + .05 + rng.random() * .2, y0 + .05 + rng.random() * .2])
        bs = [[min(v, 1) for v in b] for b in bs]
        ok &= abs(G.union_area(bs) - grid_union(bs, 300)) < 4e-3
    chk("union vs grid (25 random)", ok)
    g = [0.1, 0.1, 0.3, 0.3]
    chk("coverage full", abs(G.coverage([[0, 0, 1, 1]], g) - 1) < 1e-12)
    chk("coverage split pred", abs(G.coverage([[0.1, 0.1, 0.2, 0.3], [0.2, 0.1, 0.3, 0.3]], g) - 1) < 1e-12)
    chk("coverage half", abs(G.coverage([[0.1, 0.1, 0.2, 0.3]], g) - 0.5) < 1e-12)
    chk("coverage empty pred", G.coverage([], g) == 0.0)
    chk("outside frac empty pred None", G.outside_fraction([], [g]) is None)
    chk("outside frac big box", abs(G.outside_fraction([[0, 0, 1, 1]], [g]) - (1 - 0.04)) < 1e-12)
    chk("union iou identical", abs(G.union_iou([g], [g]) - 1) < 1e-12)
    chk("union iou split vs whole", abs(G.union_iou([[0.1, 0.1, 0.2, 0.3], [0.2, 0.1, 0.3, 0.3]], [g]) - 1) < 1e-12)
    chk("match recall one-to-one: one big box cannot match two", G.match_recall([[0, 0, 1, 1]], [[0, 0, .6, 1], [.4, 0, 1, 1]], 0.3)[0] == 1)

    gt = [[0.1, 0.1, 0.3, 0.3], [0.6, 0.1, 0.8, 0.3]]
    ex = [[0.12, 0.1, 0.32, 0.3], [0.58, 0.1, 0.78, 0.3]]
    chk("core ok identity", S.core_status(gt, ex) == (True, [0, 1]))
    chk("core ok swapped", S.core_status(gt, ex[::-1]) == (True, [1, 0]))
    chk("core fails: 3 gt", S.core_status(gt + [[0.4, 0.5, 0.5, 0.6]], ex)[0] is False)
    chk("core fails: low IoU", S.core_status(gt, [[0.2, 0.2, 0.4, 0.4], ex[1]])[0] is False)
    chk("core fails: overlapping gt", S.core_status([[0.1, 0.1, 0.3, 0.3], [0.2, 0.1, 0.4, 0.3]], ex)[0] is False)
    chk("core fails: extra missing", S.core_status(gt, [])[0] is False)
    pair = [0, 1]
    ev, _ = S.classify_event([gt[0]], gt, ex, pair)
    chk("event partial_omission", ev == "partial_omission")
    ev, _ = S.classify_event([[0, 0, 1, 1]], gt, ex, pair)
    chk("event both_retained for big box", ev == "both_retained")
    ev, _ = S.classify_event([], gt, ex, pair)
    chk("event both_missing for empty", ev == "both_missing")
    ev, _ = S.classify_event([[0.1, 0.1, 0.2, 0.3]], gt, ex, pair)  # coverage .5 vs official, ~.45 vs alt -> 모호
    chk("event ambiguous when between thresholds", ev == "ambiguous")
    # 주석 방향 불일치: 두 번째 근거에서 official은 missing, alt는 recovered
    gt2 = [[0.1, 0.1, 0.3, 0.3], [0.6, 0.1, 0.8, 0.3]]
    ex2 = [[0.1, 0.1, 0.3, 0.3], [0.2, 0.1, 0.8, 0.3]]
    ev, cov = S.classify_event([gt2[0], [0.4, 0.1, 0.6, 0.3]], gt2, ex2, pair)
    chk("event disagreement ambiguous", ev == "ambiguous" and cov[1]["dir"] == "ambiguous", cov)
    ok = all(r_["pass"] for r_ in R)
    out = ROOT / "results/iter_107/tests/fixtures_cpu.json"
    save(out, {"n": len(R), "n_pass": sum(r_["pass"] for r_ in R), "all_pass": ok, "checks": R})
    print(len(R), sum(r_["pass"] for r_ in R), [r_["name"] for r_ in R if not r_["pass"]])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
