"""iter_042 요청 조건·parser·평가 함수 (CPU only). prompt/parser는 E 출력 전에 고정한다.

GT/집단명은 요청에 넣지 않는다. 평가 함수만 GT를 인자로 받는다.
- G_short: pg39_spec.prompt_I_short('Pleural effusion.', 'qA') 그대로.
- G_neutral: 존재 전제를 뺀 중립 질의 (+ 기존 _SHORT_TAIL).
- P: presence yes/no.
"""
import hashlib
import math
import re

import numpy as np

import pg39_spec as S
from rsna_diag import parse

TARGET_ID = "qA"
CONDS = ["G_short", "G_neutral", "P"]
CAPS = [1000, 2000, 4000]
SPEC_VERSION = "pg42_v1"

NEUTRAL_STEM = ("Identify all visible regions of pleural effusion in this chest radiograph. Pleural effusion may be present or absent. "
                "If it is absent, return []. Otherwise, return one entry per separate visible region.")
P_PROMPT = "Is pleural effusion present in this chest radiograph? Answer only yes or no."


def prompt_G_short():
    return S.prompt_I_short("Pleural effusion.", TARGET_ID)


def prompt_G_neutral():
    return NEUTRAL_STEM + " " + S._SHORT_TAIL + f"Use {TARGET_ID} as the label of every entry."


def build_prompts():
    return {"G_short": prompt_G_short(), "G_neutral": prompt_G_neutral(), "P": P_PROMPT}


def request_id(kind, patient, cond, prompt_sha, image_sha):
    return hashlib.sha256(f"{SPEC_VERSION}|{kind}|{patient}|{cond}|{prompt_sha}|{image_sha}".encode()).hexdigest()[:32]


# ---------------- parsers ----------------
def parse_G(raw_suffix, ended_eos):
    """returns dict(cls, boxes, status). cls in {'nonempty','empty','invalid'}.
    기존 parse_ids(ID 규칙 포함)를 그대로 쓴다. qA 이외 ID의 box가 섞이면 invalid(형식 오류)로 분류한다."""
    r = S.parse_ids(raw_suffix, ended_eos, {TARGET_ID})
    st = r["status"]
    lenient = parse.parse_response(raw_suffix, ended_eos)  # 라벨 무시 보조 판정
    out = {"status": st, "boxes": [], "lenient_nonempty": lenient["status"] == "valid_nonempty", "flags": r["flags"]}
    if st not in parse.VALID or r["other_id_boxes"] > 0:
        out["cls"] = "invalid"
        return out
    boxes = r["groups"][TARGET_ID]
    out["boxes"] = boxes
    out["cls"] = "nonempty" if boxes else "empty"
    return out


def parse_P(raw_suffix, ended_eos):
    """공백·대소문자·종결부호만 정규화. returns 'yes'/'no'/'invalid'."""
    if not ended_eos:
        return "invalid"
    t = raw_suffix
    if t.endswith(parse.EOT):
        t = t[:-len(parse.EOT)]
    n = re.sub(r"[\s.!]+$", "", t.strip()).lower()
    n = n.lstrip()
    return n if n in ("yes", "no") else "invalid"


# ---------------- scoring ----------------
def score_pos(cls, boxes, gt_canvas):
    """양성 영상 한 요청. invalid는 F1=0 (invalid 별도 집계). boxes/gt: canvas 0-1000 yxyx."""
    pred = boxes if cls != "invalid" else []
    m3 = S.sent_metrics(pred, gt_canvas, 0.3)
    m5 = S.sent_metrics(pred, gt_canvas, 0.5)
    return {"f1_03": m3["f1"], "f1_05": m5["f1"], "recall_03": m3["recall"], "fp_03": m3["fp"], "tp_03": m3["tp"],
            "n_pred": len(pred), "n_gt": len(gt_canvas), "invalid": cls == "invalid", "empty": cls == "empty"}


def gate_output(p_label, c_cls, c_boxes):
    """두 단계: P yes -> C G_neutral 출력, no -> [] (valid-empty), P invalid -> invalid."""
    if p_label == "invalid":
        return "invalid", []
    if p_label == "no":
        return "empty", []
    return c_cls, c_boxes


def score_neg(cls):
    return {"false_box": cls == "nonempty", "valid_empty": cls == "empty", "invalid": cls == "invalid",
            "conservative_fail": cls in ("nonempty", "invalid")}


# ---------------- statistics ----------------
def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [float("nan")] * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [p, max(0.0, c - h), min(1.0, c + h)]


def boot_diff(a, b, level, B=10000, seed=20261001):
    """paired patient bootstrap of mean(a-b). returns [mean, lo, hi]. 표본 수가 1이거나 차이 분산 0이면 degenerate=True를 함께 반환."""
    d = np.asarray(a, float) - np.asarray(b, float)
    idx = np.random.default_rng(seed).integers(0, len(d), size=(B, len(d)), dtype=np.int32)
    m = d[idx].mean(axis=1)
    al = (1 - level) / 2 * 100
    return {"mean": float(d.mean()), "lo": float(np.percentile(m, al)), "hi": float(np.percentile(m, 100 - al)),
            "degenerate": bool(d.std() == 0), "level": level, "n": int(len(d))}


def boot_mean(a, level, B=10000, seed=20261001):
    return boot_diff(a, np.zeros(len(a)), level, B, seed)
