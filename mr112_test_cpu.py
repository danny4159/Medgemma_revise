"""iter_112 CPU fixture: 좌표 변환(비정사각 포함), pixel-mask 독립 IoU 대조, 평가 규칙 toy 사례, 반입 blob 확인."""
import hashlib
import json
import subprocess
import sys

import numpy as np

import mr112_spec as S
from rsna_diag import metrics as M
import mr112_eval as E

res = []


def chk(name, ok, info=""):
    res.append(dict(name=name, ok=bool(ok), info=str(info)))
    print("PASS" if ok else "FAIL", name, info)


# 1) 반입 blob
exp = {"rsna_diag/__init__.py": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
       "rsna_diag/geometry.py": "3d6521177f2ed3a081bf27be743597ac8750b836",
       "rsna_diag/metrics.py": "33c5131f7696fe9b0a1cb4266ecfc8b48f2e1fb8"}
for p, b in exp.items():
    got = subprocess.check_output(["git", "hash-object", "--", p]).decode().strip()
    chk(f"blob {p}", got == b, got)

# 2) 좌표 변환: 정사각/비정사각, 반올림, 범위
rng = np.random.default_rng(112)
bad = 0
for (w, h) in [(1024, 1024), (512, 512), (1000, 700), (333, 1024), (2048, 1500)]:
    for _ in range(300):
        x1, y1 = rng.uniform(0, w - 20), rng.uniform(0, h - 20)
        x2, y2 = rng.uniform(x1 + 5, w), rng.uniform(y1 + 5, h)
        m = S.box_to_medrega((x1, y1, x2, y2), w, h)
        assert all(0 <= v <= 999 for v in m)
        back = (m[0] / 1000 * w, m[1] / 1000 * h, m[2] / 1000 * w, m[3] / 1000 * h)
        # 왕복 오차는 반 픽셀 격자(size/1000/2) 이내, 단 999 clip 경계는 한 격자
        tol = [w / 1000 * 0.51, h / 1000 * 0.51, w / 1000 * 0.51, h / 1000 * 0.51]
        if x2 / w * 1000 > 999.5 or y2 / h * 1000 > 999.5:
            tol = [t * 2.1 for t in tol]
        if any(abs(a - b) > t for a, b, t in zip(back, (x1, y1, x2, y2), tol)):
            bad += 1
chk("roundtrip tolerance (5 sizes x 300)", bad == 0, bad)
chk("full box", S.FULL_BOX == (0, 0, 999, 999))
chk("axis order x,y (비정사각)", S.box_to_medrega((100, 10, 200, 20), 1000, 500) == (100, 20, 200, 40), S.box_to_medrega((100, 10, 200, 20), 1000, 500))

# 3) pixel-mask 독립 IoU 대조 (정수 격자 box 에서 정확히 일치)
bad = 0
for _ in range(500):
    def rb():
        x1, y1 = rng.integers(0, 80, 2)
        return [int(x1), int(y1), int(x1 + rng.integers(1, 20)), int(y1 + rng.integers(1, 20))]
    a, b = rb(), rb()
    ma, mb = np.zeros((100, 100), bool), np.zeros((100, 100), bool)
    ma[a[1]:a[3], a[0]:a[2]] = True
    mb[b[1]:b[3], b[0]:b[2]] = True
    u = (ma | mb).sum()
    iou = (ma & mb).sum() / u
    if abs(iou - M.iou(a, b)) > 1e-12:
        bad += 1
chk("M.iou == pixel mask IoU (xyxy 정수 격자)", bad == 0, bad)
chk("max_iou_all 빈 GT -> 0", M.max_iou_all([[0, 0, 5, 5]], []) == 0.0)

# 4) 평가 규칙 toy: 동률, K, 오류 정의
T = [dict(id=f"p{i}", det_index=0, conf=0.7 + 0.01 * i, region=-i * 1.0, full=-0.5, max_iou=0.1 if i >= 4 else 0.9,
          err3=i >= 4, err5=i >= 4, gt_pos=True) for i in range(8)]
chk("K=ceil(.25N)", S.n_review(8) == 2 and S.n_review(240) == 60 and S.n_review(9) == 3)
o = E.order(T, "region")
chk("region 순위: 낮은 likelihood 먼저", [T[i]["id"] for i in o[:2]] == ["p7", "p6"])
o = E.order(T, "full")  # 전부 동률 -> 낮은 confidence 먼저
chk("full 동률 -> confidence 오름차순", [T[i]["id"] for i in o[:3]] == ["p0", "p1", "p2"])
s = E.summary(T)
chk("toy summary", s["captured_region"] == 2 and s["captured_conf"] == 0 and abs(s["diff_region_conf"] - 0.25) < 1e-12, s["diff_region_conf"])
chk("decide toy: 기여 환자 2명 -> inconclusive", E.decide(s).startswith("inconclusive"), E.decide(s))

# 5) request/manifest 구조: 요청에 GT 키가 없다
man = json.load(open("results/iter_112/data/manifest.json"))
bad = [q for q in man["requests"] if set(q) - {"group", "id", "det_index", "kind", "box", "prompt", "target", "request_id"}]
chk("요청 필드에 GT/confidence 없음", not bad)
chk("prompt에 'lung opacity' 정답/score 문자열 없음", all(("opacity" not in q["prompt"]) for q in man["requests"]))
chk("main 요청 수", man["counts"]["main_region_requests"] == 240 and man["counts"]["main_full_requests"] == 140)
json.dump(res, open("results/iter_112/tests_cpu.json", "w"), indent=1)
print(sum(r["ok"] for r in res), "/", len(res))
sys.exit(0 if all(r["ok"] for r in res) else 1)
