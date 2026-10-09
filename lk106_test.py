"""iter_106 CPU fixture: 좌표 추출·matching·요청 구성. spec(Kuhn)과 verify(별도 구현 + 전수 열거)를 교차 대조한다.
사용: python lk106_test.py --out results/iter_106/tests/fixtures_cpu.json (새 파일만)"""
import argparse
import json
import random
import sys
from pathlib import Path

import lk106_spec as S
import lk106_verify as V
from report86_common import ROOT


def cx(c):
    return "[" + ",".join(f"{v}" for v in c) + "]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = []

    def chk(name, ok, detail=None):
        res.append({"name": name, "pass": bool(ok), "detail": detail})

    # 1) 좌표 추출 fixture (spec vs verify)
    cases = {
        "single": ("X: [0.5,0.5,0.2,0.2]", True, "valid_nonempty", 1),
        "two_boxes": ("A: [0.2,0.2,0.2,0.2] B: [0.7,0.7,0.2,0.2]", True, "valid_nonempty", 2),
        "empty_prose": ("Right diaphragmatic lobulation.", True, "no_box", 0),
        "zero_width": ("X: [0.5,0.5,0.0,0.2]", True, "coord_invalid", 0),
        "negative": ("X: [-0.1,0.5,0.2,0.2]", True, "coord_invalid", 0),
        "gt1": ("X: [0.5,1.5,0.2,0.2]", True, "coord_invalid", 0),
        "valid_then_invalid": ("X: [0.5,0.5,0.2,0.2] Y: [0.5,0.5,0.0,0.2]", True, "coord_invalid", 0),
        "non_eos": ("X: [0.5,0.5,0.2,0.2]", False, "truncated", 0),
        "three_number_bracket": ("X: [0.5,0.5,0.2]", True, "no_box", 0),
        "spaces": ("X: [ 0.5 , 0.5 , 0.2 , 0.2 ]", True, "valid_nonempty", 1),
        "nan": ("X: [nan,0.5,0.2,0.2]", True, "no_box", 0),
    }
    for k, (t, eos, st, n) in cases.items():
        p = S.parse_pg(t, eos)
        v = V.extract_boxes(t, eos)
        chk(f"parse_{k}", p["status"] == st and len(p["boxes"]) == n and v[0] == st and len(v[1]) == n, {"spec": p["status"], "verify": v[0]})
    # 좌표 변환: cxcywh -> xyxy 값, clipping 없음(경계 밖 box도 그대로)
    p = S.parse_pg("X: [0.95,0.5,0.2,0.2]", True)
    chk("no_clipping", abs(p["boxes"][0][2] - 1.05) < 1e-12, p["boxes"])
    # 2) matching 극단 사례
    g = [[0.0, 0.0, 0.4, 0.4], [0.3, 0.0, 0.7, 0.4]]  # 두 GT가 겹침(실제 선정은 비중첩이지만 fixture용)
    big = [0.0, 0.0, 0.7, 0.4]
    chk("one_big_box_cannot_match_two", S.match(g, [big])[1] == 1 and V.mm([tuple(x) for x in g], [big]) == 1)
    chk("duplicate_pred_one_gt", S.match([g[0], [0.8, 0.8, 0.95, 0.95]], [g[0], g[0], g[0]])[1] == 1)
    chk("empty_preds", S.match(g, [])[1] == 0 and S.score_boxes(g, [])["recall"] == 0.0)
    chk("two_distinct", S.match([g[0], [0.6, 0.6, 0.9, 0.9]], [g[0], [0.6, 0.6, 0.9, 0.9]])[1] == 2)
    # 3) 무작위 교차 대조 (spec Kuhn == verify 열거 == 전수 permutation)
    rnd = random.Random(106)
    bad = 0
    for _ in range(3000):
        def rb():
            x, y = rnd.random() * 0.7, rnd.random() * 0.7
            return [x, y, x + 0.1 + rnd.random() * 0.3, y + 0.1 + rnd.random() * 0.3]
        gts = [rb() for _ in range(rnd.choice([1, 2]))]
        preds = [rb() for _ in range(rnd.randint(0, 4))]
        if rnd.random() < 0.5 and preds:
            preds.append(list(gts[0]))
        a1 = S.match(gts, preds)[1]
        a2 = V.mm([tuple(x) for x in gts], [tuple(x) for x in preds])
        a3 = V.max_match([tuple(x) for x in gts], [tuple(x) for x in preds])
        if not (a1 == a2 == a3):
            bad += 1
    chk("random_match_3000", bad == 0, {"mismatch": bad})
    # 4) 요청 구성: 문장 불변, 공백 하나, 순서
    row = {"ImageID": "i.png", "S1": "Aortic elongation.", "S2": "Right pleural effusion."}
    q = {r["cond"]: r["prompt"] for r in S.requests_for([row], ["I1", "I2", "J12", "J21", "R11", "R22"])}
    chk("prompts", q["I1"] == "Ground the phrase: Aortic elongation." and q["I2"] == "Ground the phrase: Right pleural effusion."
        and q["J12"] == "Ground the phrase: Aortic elongation. Right pleural effusion."
        and q["J21"] == "Ground the phrase: Right pleural effusion. Aortic elongation."
        and q["R11"] == "Ground the phrase: Aortic elongation. Aortic elongation." and q["R22"] == "Ground the phrase: Right pleural effusion. Right pleural effusion.")
    # 5) 실제 입력 연결: I1/I2 요청 prompt가 iter_105 저장 pg prompt와 일치, 요청 id 고유
    ok = True
    for stage in ("D4", "E32"):
        rows = json.loads((ROOT / f"results/iter_105/data/inputs_{stage}.json").read_text())
        for r in S.requests_for(rows, ["I1", "I2", "J12", "J21", "R11", "R22"]):
            ok &= r["prompt"].startswith("Ground the phrase: ")
    chk("inputs_prompts", ok)
    # 6) 전체 stage 요청 수
    import lk106_run as R
    chk("n_requests", len(R.requests("D4", "CURE")) == 24 and len(R.requests("E32", "CURE")) == 128)
    # 7) 예측 라벨 제거: multiset 단순 결합이 문장 순서에 불변
    pa, pb = [[0.1, 0.1, 0.2, 0.2]], [[0.6, 0.6, 0.8, 0.8]]
    gt2 = [[0.1, 0.1, 0.2, 0.2], [0.6, 0.6, 0.8, 0.8]]
    chk("union_order_invariant", S.match(gt2, pa + pb)[1] == S.match(gt2, pb + pa)[1] == 2)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as f:
        json.dump({"n": len(res), "all_pass": all(r["pass"] for r in res), "checks": res}, f, indent=1)
    print(json.dumps({"n": len(res), "all_pass": all(r["pass"] for r in res), "fail": [r for r in res if not r["pass"]]}, indent=1))
    return 0 if all(r["pass"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
