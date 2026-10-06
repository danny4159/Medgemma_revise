"""iter_039 요청 조건·prompt·parser·평가 (CPU only). GT는 평가 함수에만 인자로 들어간다."""
import hashlib
import json
import math
import re

import numpy as np

from rsna_diag import geometry, metrics, parse, prompts

COND_ORDER = ["I-long", "J-long", "J-reverse", "C-long", "I-short", "J-short"]
CAPS_IC = [1000, 2000, 4000]
CAPS_J = [2000, 4000, 8000]
SHORT_VERSION = "short_v1"
ID_RE = re.compile(r"^\s*(q[ab])\s*$", re.I)


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------- prompts ----------------
def _long(obj):
    return prompts.official_long(obj)


# long_v2 (D 형식 수정 1회): v1에서 C-long 13/48이 ID 대신 소견명을 label로 써 unknown_id가 됐다. label 지시를 모든 long 조건에서 동일하게 명확화.
LABEL_V2 = ' — the label must be exactly the ID string, not the name of the finding'


def prompt_I_long(sent, pid):
    return _long(f'finding described by the sentence "{sent}" (label every box of this finding with the literal ID "{pid}"'
                 f'{LABEL_V2}; use one box per separate region of the finding)')


def prompt_J_long(sents_in_order):
    (i1, s1), (i2, s2) = sents_in_order
    return _long(f'two findings described by the sentences {i1}: "{s1}" and {i2}: "{s2}" (for each finding output one box '
                 f'per separate region, and label every box with the literal ID of its sentence, "{i1}" or "{i2}"{LABEL_V2})')


def prompt_C_long(target, sents):
    other = "qB" if target == "qA" else "qA"
    return _long(f'finding {target} described by the sentence {target}: "{sents[target]}", while the report also contains '
                 f'the sentence {other}: "{sents[other]}" that must NOT be localized (label every box with the literal ID "{target}"{LABEL_V2}; '
                 f'output boxes only for {target})')


_SHORT_TAIL = ('Return only a JSON list. Each entry must contain "box_2d": [y_min, x_min, y_max, x_max] and "label". '
               'Coordinates must be between 0 and 1000 relative to the entire square-padded image, with y before x. ')


def prompt_I_short(sent, pid):
    return (f'Localize the finding described by this sentence in the chest radiograph: "{sent}". ' + _SHORT_TAIL +
            f'Use "{pid}" as the label of every entry and one entry per separate region of the finding. '
            'Return [] if the finding is not visible.')


def prompt_J_short(sents_in_order):
    (i1, s1), (i2, s2) = sents_in_order
    return (f'Localize the two findings described by these sentences in the chest radiograph. {i1}: "{s1}" {i2}: "{s2}" ' +
            _SHORT_TAIL + f'Use the sentence ID ("{i1}" or "{i2}") as the label of each entry and one entry per separate '
            'region of a finding. Omit a finding that is not visible.')


def build_prompts(sents):
    """sents: {'qA': text, 'qB': text}. returns list of (cond, target_ids, prompt, caps)."""
    out = []
    for pid in ("qA", "qB"):
        out.append(("I-long", [pid], prompt_I_long(sents[pid], pid), CAPS_IC))
    out.append(("J-long", ["qA", "qB"], prompt_J_long([("qA", sents["qA"]), ("qB", sents["qB"])]), CAPS_J))
    out.append(("J-reverse", ["qA", "qB"], prompt_J_long([("qB", sents["qB"]), ("qA", sents["qA"])]), CAPS_J))
    for pid in ("qA", "qB"):
        out.append(("C-long", [pid], prompt_C_long(pid, sents), CAPS_IC))
    for pid in ("qA", "qB"):
        out.append(("I-short", [pid], prompt_I_short(sents[pid], pid), CAPS_IC))
    out.append(("J-short", ["qA", "qB"], prompt_J_short([("qA", sents["qA"]), ("qB", sents["qB"])]), CAPS_J))
    return out


def request_id(kind, patient, cond, targets, prompt_sha, image_sha):
    return sha(f"{kind}|{patient}|{cond}|{','.join(targets)}|{prompt_sha}|{image_sha}")[:32]


# ---------------- parser ----------------
def _dup_key_check(raw):
    def hook(pairs):
        seen = set()
        for k, _ in pairs:
            if k in seen:
                raise ValueError("dup")
            seen.add(k)
        return dict(pairs)
    try:
        json.loads(raw, object_pairs_hook=hook)
        return False
    except ValueError as e:
        return str(e) == "dup"
    except Exception:
        return False


def _candidate_raws(raw_suffix):
    text = raw_suffix
    if text.endswith(parse.EOT):
        text = text[:-len(parse.EOT)]
    region = text
    if parse.THINK_CLOSE in text:
        region = text.split(parse.THINK_CLOSE, 1)[1]
    markers = list(parse.FINAL_RE.finditer(region))
    segs = ([region[markers[i].end(): markers[i + 1].start() if i + 1 < len(markers) else len(region)]
             for i in range(len(markers))] if markers else [region])
    return [c["raw"] for s in segs for c in parse._candidates(s) if c["kind"] == "list"]


def parse_ids(raw_suffix, ended_eos, allowed_ids):
    """공통 parser + ID 규칙. returns dict(status, groups{ID:[boxes]}, other_id_boxes, flags).
    status: valid_nonempty/valid_empty/truncated/format 실패 + dup_key/unknown_id."""
    r = parse.parse_response(raw_suffix, ended_eos)
    res = {"status": r["status"], "groups": {i: [] for i in ("qA", "qB")}, "other_id_boxes": 0,
           "flags": list(r["flags"]), "n_boxes_total": len(r["boxes"])}
    if r["status"] not in parse.VALID:
        return res
    if any(_dup_key_check(c) for c in _candidate_raws(raw_suffix)):
        res["status"] = "dup_key"
        return res
    for b, lab in zip(r["boxes"], r["labels"]):
        m = ID_RE.match(lab)
        if not m:
            res["status"] = "unknown_id"
            res["groups"] = {i: [] for i in ("qA", "qB")}
            return res
        pid = "q" + m.group(1)[1].upper()
        if pid not in allowed_ids:
            res["other_id_boxes"] += 1
            continue
        res["groups"][pid].append(b)
    if res["status"] == "valid_nonempty" and not any(res["groups"].values()) and res["other_id_boxes"] == 0:
        res["status"] = "valid_empty"
    return res


# ---------------- matching / scoring ----------------
def match_fast(pred, gt, thr):
    """최대 cardinality one-to-one matching, 동률은 총 IoU 최대 (정확한 DP: 작은 쪽 집합의 bitmask). returns [(gi, pi)]."""
    if not pred or not gt:
        return []
    swap = len(gt) > len(pred)
    A = pred if swap else gt  # bitmask 쪽(작은 집합)
    Bs = gt if swap else pred
    if len(A) > 20:
        raise ValueError("matching side too large for exact DP")
    w = [[(metrics.iou(Bs[j], A[i]) if swap else metrics.iou(A[i], Bs[j])) for j in range(len(Bs))] for i in range(len(A))]
    # w[i][j]: IoU(A_i, B_j) (iou는 대칭)
    dp = {0: (0, 0.0, ())}
    for j in range(len(Bs)):
        new = dict(dp)
        for mask, (c, t, pairs) in dp.items():
            for i in range(len(A)):
                if not (mask >> i) & 1 and w[i][j] >= thr:
                    key = mask | (1 << i)
                    cand = (c + 1, t + w[i][j], pairs + ((i, j),))
                    cur = new.get(key)
                    if cur is None or (cand[0], cand[1]) > (cur[0], cur[1] + 1e-12):
                        new[key] = cand
        dp = new
    best = max(dp.values(), key=lambda v: (v[0], v[1]))
    return [(j, i) if swap else (i, j) for i, j in best[2]]


def sent_metrics(pred, gt, thr):
    pairs = match_fast(pred, gt, thr)
    tp = len(pairs)
    prec = tp / len(pred) if pred else 0.0
    rec = tp / len(gt) if gt else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0.0
    return {"tp": tp, "n_pred": len(pred), "n_gt": len(gt), "f1": f1, "recall": rec,
            "fp": len(pred) - tp, "union_iou": metrics.union_iou(pred, gt)}


def gt_to_canvas(boxes_xyxy_norm, orig_h, orig_w):
    top, left, side = geometry.pad_offsets(orig_h, orig_w)
    out = []
    for x0, y0, x1, y1 in boxes_xyxy_norm:
        out.append(geometry.canvas_to_norm([x0 * orig_w, y0 * orig_h, x1 * orig_w, y1 * orig_h], top, left, side))
    return out


def score_request(rec_status, groups, targets, gt):
    """targets: 채점할 ID 목록. gt: {ID: canvas boxes}. invalid는 f1=0 (내용 오류와 별도 집계)."""
    valid = rec_status in parse.VALID
    out = {}
    for t in targets:
        pred = groups.get(t, []) if valid else []
        m5 = sent_metrics(pred, gt[t], 0.5)
        m3 = sent_metrics(pred, gt[t], 0.3)
        out[t] = {"f1_03": m3["f1"], "f1_05": m5["f1"], "recall_03": m3["recall"], "fp_03": m3["fp"],
                  "tp_03": m3["tp"], "n_pred": len(pred), "n_gt": len(gt[t]), "union_iou": m3["union_iou"],
                  "empty": valid and len(pred) == 0}
    return out


def swap_score(groups, gt):
    """공동 출력 qA/qB 그룹 교환 후 F1@0.3 평균 (box 재분할 없음)."""
    a = sent_metrics(groups.get("qB", []), gt["qA"], 0.3)["f1"]
    b = sent_metrics(groups.get("qA", []), gt["qB"], 0.3)["f1"]
    return (a + b) / 2


def cross_iou_max(gtA, gtB):
    return max((metrics.iou(a, b) for a in gtA for b in gtB), default=0.0)
