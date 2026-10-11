"""iter_108 진단: 원본 + 예측 영역 영상 제공(frozen MedGemma 1.5)의 순수 규칙 모듈 (결과를 보기 전에 고정).

- 영상 조건: F(기존 원본 단일 영상 출력, 재사용), D(원본+원본 복제), T(원본+예측 enclosing crop), C(원본+크기 일치 중앙 crop),
  L(예측 crop 단독, O만). 질문 O/A는 별도 대화. 정답은 요청 구성에 쓰지 않는다.
- crop은 저장된 B0 bbox(yxyx/1000, square-padded 기준)에서만 만든다. GT는 crop 선택에 쓰지 않는다.
- 이 파일의 어떤 수치 문턱도 계획(plan.md Proposed Experiment §4, Evaluation)이 정한 값만 쓴다.
"""
import hashlib
import json
import math
import re

import numpy as np
from PIL import Image

from rsna_diag import geometry, qa_spec

SEED = 10817
N_BOOT = 10000
CATS = qa_spec.CATEGORIES
TARGETS = qa_spec.TARGETS
FMT = "plain"
CAPS = [1000, 2000, 4000]

GUIDE_DTC = ("Image 1 is the complete source chest radiograph. Image 2 is an auxiliary view of the same radiograph and may be a "
             "full image or a crop. It is not an independent examination or proof of an abnormality. "
             "Answer the question about Image 1 using the available evidence.")
GUIDE_L = ("This is an auxiliary crop from a source chest radiograph. Answer the following question about the source "
           "radiograph using this limited view.")
MULTI_CONDS = ("D", "T", "C")


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


def core_prompt(target):
    """iter_016 F(원본 단일 영상 direct plain)의 prompt와 동일."""
    return f"{qa_spec.QUESTIONS[target]} {qa_spec.FORMATS[FMT]}"


def prompt_for(cond, target):
    core = core_prompt(target)
    guide = GUIDE_L if cond == "L" else GUIDE_DTC
    return f"{guide}\n\n{core}"


# ---------------- bbox / crop ----------------
_BOX_ITEM = re.compile(r"\s*\{\s*\"box_2d\"\s*:\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]\s*,\s*\"label\"\s*:\s*\"[^\"]*\"\s*\}\s*")


def parse_saved_bbox(text, ended_eos):
    """저장된 B0 concise 출력의 엄격 해석. returns (status, boxes yxyx 정수 list).
    status: ok(boxes 1+) | empty([]) | truncated | invalid. invalid/truncated는 빈 예측으로 바꾸지 않는다."""
    if not ended_eos:
        return "truncated", []
    t = text[:-len(qa_spec.EOT)] if text.endswith(qa_spec.EOT) else text
    t = t.strip()
    if t == "[]":
        return "empty", []
    try:
        v = json.loads(t)
    except ValueError:
        return "invalid", []
    if not isinstance(v, list) or not v:
        return "invalid", []
    boxes = []
    for it in v:
        if not isinstance(it, dict) or "box_2d" not in it:
            return "invalid", []
        b = it["box_2d"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(x, int) and not isinstance(x, bool) for x in b)):
            return "invalid", []
        y0, x0, y1, x1 = b
        if not (0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
            return "invalid", []
        boxes.append([y0, x0, y1, x1])
    return "ok", boxes


def enclosing(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def crop_rect(yxyx, side):
    """yxyx/1000 -> pixel (x0,y0,x1,y1): 시작 floor, 끝 ceil, canvas에 clip. 퇴화(폭/높이 0)면 None."""
    y0, x0, y1, x1 = yxyx
    px0 = max(0, math.floor(x0 * side / 1000.0))
    py0 = max(0, math.floor(y0 * side / 1000.0))
    px1 = min(side, math.ceil(x1 * side / 1000.0))
    py1 = min(side, math.ceil(y1 * side / 1000.0))
    if px1 <= px0 or py1 <= py0:
        return None
    return px0, py0, px1, py1


def center_rect(h, w, side):
    """예측 crop과 같은 pixel 높이 h, 너비 w를 정사각 canvas 중앙에서 자른다 (floor 중심)."""
    y0 = (side - h) // 2
    x0 = (side - w) // 2
    return x0, y0, x0 + w, y0 + h


def crop_square_padded(canvas_rgb, rect):
    """canvas(정사각 padding된 RGB uint8)에서 rect를 자르고 값 보존 후 square padding한다. returns (padded uint8 RGB, affine)."""
    x0, y0, x1, y1 = rect
    sub = canvas_rgb[y0:y1, x0:x1]
    padded, aff = geometry.pad_square(sub)
    return padded, aff


def rect_area_ratio(rect, side):
    x0, y0, x1, y1 = rect
    return (x1 - x0) * (y1 - y0) / float(side * side)


# ---------------- parsing ----------------
def sem(target, raw, ended):
    """semantic_v1 (주평가). returns (status, answer)."""
    st, ans, _ = qa_spec.parse_semantic(target, FMT, raw, ended)
    return st, ans


def strict(target, raw, ended):
    return qa_spec.parse_plain(raw, ended)


def correct_answer(cat, target):
    return qa_spec.GT_PAIR[cat][0 if target == "O" else 1]


# ---------------- stats ----------------
def boot_diff(a, b, seed=SEED, n=N_BOOT):
    """환자 단위 paired 차이 a-b (0/1 벡터)의 bootstrap 95% 구간. 모든 분산이 0이면 퇴화 표시."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    d = a - b
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    m = d[idx].mean(axis=1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(d.mean()), float(lo), float(hi), bool(np.all(d == d[0]))


def exact_binom_ci(k, n, alpha=0.05):
    """Clopper-Pearson 구간 (scipy 없이 bisection)."""
    def cdf(x, n_, p):
        return sum(math.comb(n_, i) * p ** i * (1 - p) ** (n_ - i) for i in range(0, x + 1))
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0
    hi = 1.0
    if k > 0:
        a, b = 0.0, 1.0
        for _ in range(80):
            m = (a + b) / 2
            if 1 - cdf(k - 1, n, m) < alpha / 2:
                a = m
            else:
                b = m
        lo = (a + b) / 2
    if k < n:
        a, b = 0.0, 1.0
        for _ in range(80):
            m = (a + b) / 2
            if cdf(k, n, m) > alpha / 2:
                a = m
            else:
                b = m
        hi = (a + b) / 2
    return (lo, hi)
