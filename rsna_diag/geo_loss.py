"""iter_014: R-VLM 계열 GIoU 가중 pseudo-box supervision(G), GT 질량을 맞춘 균등 대조(U), 직접 SFT(C)의 후보·span·가중치·branch 구성.

GT box b 하나마다 pseudo-box 4개(m=1..4)를 만들고, m=0은 GT다. 손실(모든 조건 공통):
    L = [ CE_outside_GT_spans + sum_b n_b * sum_m q_bm * ell_bm ] / N
  ell_bm = 후보 m의 `box_2d` 배열 span 평균 NLL(전체 vocabulary softmax, softcap 유지), n_b = GT span token 수, N = GT assistant token 수.
  r_b0 = 1, r_bm = 1 + 0.5 ln GIoU(cand, GT_b), Z_b = sum_m r_bm.  G: q = r/Z.  U: q_b0 = 1/Z, q_bm = (1 - q_b0)/4.  C: q_b0 = 1.
GT branch는 원래 GT 전체 sequence에 token별 가중치(span 밖 1, span b 안 q_b0)를 곱한 CE다 (n_b * q_b0 * mean = q_b0 * sum).
후보 branch는 [prompt + GT의 box b 이전 token prefix + 후보 span]까지의 sequence이고 span token에만 가중치 n_b*q_bm/n_bm을 준다.
후보 span 뒤 suffix는 loss에 쓰지 않으며 causal attention 때문에 span logit에 영향이 없으므로 잘라서 계산한다 (실제 모델로 검증: 테스트).

span 규약: `box_2d` 좌표 배열의 시작 `[`부터 끝 `]`까지. tokenizer가 앞 공백(" [")과 뒤 쉼표("],")를 같은 token으로 합치므로,
그 token들은 span에 포함하되 경계 걸침이 정확히 그 두 문자(앞 공백 최대 1, 뒤 쉼표 1)일 때만 허용하고 그 외는 예외다 (조용히 자르지 않는다).
"""
import hashlib
import json
import math

import numpy as np

SEED_TAG = "iter014-cand-v1"
K_CAND = 4
GIOU_MIN = 0.3
GAMMA = 0.5
SHIFT_FRAC = 0.3
SCALE_RANGE = (0.8, 1.2)
MAX_PROPOSALS = 10000


class GeoError(RuntimeError):
    pass


# ---------- 기하 ----------
def giou(a, b):
    """[y0,x0,y1,x1] 정수 box 두 개의 GIoU (float64, 정수 면적 계산)."""
    ay0, ax0, ay1, ax1 = a
    by0, bx0, by1, bx1 = b
    ia = max(0, min(ay1, by1) - max(ay0, by0)) * max(0, min(ax1, bx1) - max(ax0, bx0))
    aa, ab = (ay1 - ay0) * (ax1 - ax0), (by1 - by0) * (bx1 - bx0)
    u = aa + ab - ia
    c = (max(ay1, by1) - min(ay0, by0)) * (max(ax1, bx1) - min(ax0, bx0))
    if u <= 0 or c <= 0:
        raise GeoError(f"degenerate box {a} {b}")
    return ia / u - (c - u) / c


def _rng(pid, b):
    h = hashlib.sha256(f"{SEED_TAG}|{pid}|{b}".encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def gen_candidates(pid, b, gt_box, k=K_CAND):
    """GT box(정수 yxyx) 하나에 대한 결정적 후보 k개. returns (cands, n_proposals). 10,000 proposal 안에 k개가 안 나오면 GeoError (대체 금지).
    proposal: 폭·높이에 비례한 shift U(-0.3,0.3) 및 scale U(0.8,1.2)(축별 독립), [0,1000] clipping, 1/1000 격자 반올림 뒤 GIoU>=0.3, GT·중복 제외."""
    rng = _rng(pid, b)
    y0, x0, y1, x1 = gt_box
    cy, cx, h, w = (y0 + y1) / 2, (x0 + x1) / 2, y1 - y0, x1 - x0
    out, seen = [], {tuple(gt_box)}
    for n in range(1, MAX_PROPOSALS + 1):
        dy, dx = rng.uniform(-SHIFT_FRAC, SHIFT_FRAC, 2) * (h, w)
        sy, sx = rng.uniform(*SCALE_RANGE, 2)
        ny0, ny1 = cy + dy - sy * h / 2, cy + dy + sy * h / 2
        nx0, nx1 = cx + dx - sx * w / 2, cx + dx + sx * w / 2
        c = [int(min(1000, max(0, v)) + 0.5) for v in (ny0, nx0, ny1, nx1)]
        if not (c[0] < c[2] and c[1] < c[3]) or tuple(c) in seen:
            continue
        if giou(c, gt_box) < GIOU_MIN:
            continue
        seen.add(tuple(c))
        out.append(c)
        if len(out) == k:
            return out, n
    raise GeoError(f"could not obtain {k} candidates for {pid} box {b} {gt_box} within {MAX_PROPOSALS} proposals")


def cand_record(gt_box, cand):
    gi = giou(cand, gt_box)
    g_h, g_w = gt_box[2] - gt_box[0], gt_box[3] - gt_box[1]
    return {"box": cand, "giou": gi, "area_ratio": (cand[2] - cand[0]) * (cand[3] - cand[1]) / (g_h * g_w),
            "disp": math.hypot((cand[0] + cand[2] - gt_box[0] - gt_box[2]) / 2, (cand[1] + cand[3] - gt_box[1] - gt_box[3]) / 2)}


# ---------- 가중치 ----------
def r_weights(gious):
    """gious: 후보 GIoU 리스트 -> [1, r_1..r_k]. 각 r은 양수·유한이어야 한다."""
    r = [1.0] + [1.0 + GAMMA * math.log(g) for g in gious]
    if not all(math.isfinite(v) and v > 0 for v in r):
        raise GeoError(f"non-positive/non-finite weight {r} for giou {gious}")
    return r


def q_weights(mode, gious):
    r = r_weights(gious)
    if mode == "C":
        return [1.0] + [0.0] * len(gious)
    z = sum(r)
    if mode == "G":
        return [v / z for v in r]
    if mode == "U":
        q0 = 1.0 / z
        return [q0] + [(1 - q0) / len(gious)] * len(gious)
    raise ValueError(mode)


# ---------- token span ----------
def array_char_spans(text):
    """target JSON의 각 `box_2d` 배열의 (시작 '[' 위치, 끝 ']' 위치, 4개 정수)를 문서 순서로 반환. 값은 json.loads와 대조한다."""
    from . import coord_loss as CL
    sp = CL.coord_spans(text)
    if len(sp) % 4:
        raise GeoError("coordinate count not multiple of 4")
    want = [e["box_2d"] for e in json.loads(text)]
    res = []
    for b in range(len(sp) // 4):
        s0, e3 = sp[4 * b][0], sp[4 * b + 3][1]
        if text[s0 - 1] != "[" or text[e3] != "]":
            raise GeoError(f"box {b}: array brackets not adjacent to coordinates")
        vals = [v for _, _, v in sp[4 * b:4 * b + 4]]
        if vals != want[b]:
            raise GeoError(f"box {b}: scanned values {vals} != json {want[b]}")
        res.append((s0 - 1, e3, vals))
    return res


def encode(tok, text):
    enc = tok(text + "<end_of_turn>", add_special_tokens=False, return_offsets_mapping=True)
    return list(enc["input_ids"]), [tuple(o) for o in enc["offset_mapping"]]


def box_token_spans(tok, text, dig_ids):
    """returns (ids, [(t_start, t_end_inclusive)] per box). 경계 걸침은 앞 공백/뒤 쉼표만 허용하고 좌표 숫자는 모두 한 자리 digit token이어야 한다."""
    ids, offs = encode(tok, text)
    dset = set(dig_ids)
    res = []
    for (a, z, _vals) in array_char_spans(text):
        ts = [t for t, (s, e) in enumerate(offs) if s <= a < e]
        te = [t for t, (s, e) in enumerate(offs) if s <= z < e]
        if len(ts) != 1 or len(te) != 1:
            raise GeoError("bracket not covered by exactly one token")
        ts, te = ts[0], te[0]
        s_off, e_off = offs[ts]
        s2, e2 = offs[te]
        if e_off != a + 1 or text[s_off:a] not in ("", " "):
            raise GeoError(f"opening token straddles unexpected chars {text[s_off:e_off]!r}")
        if s2 != z or text[z + 1:e2] not in ("", ","):
            raise GeoError(f"closing token straddles unexpected chars {text[s2:e2]!r}")
        for t in range(ts + 1, te):
            s, e = offs[t]
            seg = text[s:e]
            if seg.isdigit():
                if ids[t] not in dset or e - s != 1:
                    raise GeoError(f"non single-digit token {seg!r} inside box span")
            elif seg not in (",", " ", ", "):
                raise GeoError(f"unexpected token {seg!r} inside box span")
        res.append((ts, te))
    return ids, res


def replace_box_text(text, b, new_box):
    """text의 b번째 box_2d 배열을 new_box(정수 4개)로 교체한 문자열 (json.dumps와 같은 서식 '[a, b, c, d]')."""
    a, z, _ = array_char_spans(text)[b]
    return text[:a] + "[" + ", ".join(str(int(v)) for v in new_box) + "]" + text[z + 1:]


def build_branches(tok, text, dig_ids, cand_lists, mode):
    """text: GT target. cand_lists: [[cand_record x4] per box] (GT box 순서). returns dict:
    gt_ids, gt_spans, gt_tokw_by_box(q_b0), branches=[{box, m, ids(assistant part), span=(ts,te), q, w_per_token, n_b, n_bm, giou}].
    C에서는 branch 없이 q_b0=1이다."""
    gt_ids, gt_spans = box_token_spans(tok, text, dig_ids)
    if len(cand_lists) != len(gt_spans):
        raise GeoError("candidate list count != box count")
    branches, q0s = [], []
    for b, cl in enumerate(cand_lists):
        q = q_weights(mode, [c["giou"] for c in cl])
        q0s.append(q[0])
        ts, te = gt_spans[b]
        n_b = te - ts + 1
        if mode == "C":
            continue
        for m, c in enumerate(cl, start=1):
            ctext = replace_box_text(text, b, c["box"])
            cids, cspans = box_token_spans(tok, ctext, dig_ids)
            cts, cte = cspans[b]
            if cts != ts or cids[:ts + 1] != gt_ids[:ts + 1]:
                raise GeoError(f"box {b} cand {m}: GT prefix (incl. opening bracket token) differs")
            n_bm = cte - cts + 1
            branches.append({"box": b, "m": m, "ids": cids[:cte + 1], "span": (cts, cte), "q": q[m], "n_b": n_b, "n_bm": n_bm,
                             "w_per_token": q[m] * n_b / n_bm, "giou": c["giou"], "cand": c["box"]})
    return {"gt_ids": gt_ids, "gt_spans": gt_spans, "q0": q0s, "branches": branches}


def gt_token_weights(gt_len, gt_spans, q0s):
    """assistant 부분(길이 gt_len) token별 가중치: span 밖 1, box b span 안 q_b0."""
    w = [1.0] * gt_len
    for (ts, te), q0 in zip(gt_spans, q0s):
        for t in range(ts, te + 1):
            w[t] = q0
    return w


def branch_digest(br):
    """branch 목록의 결정적 지문 (batch ID·후보 ID 대조용)."""
    h = hashlib.sha256()
    for b in br:
        h.update(json.dumps([b["box"], b["m"], b["ids"], b["span"], round(b["w_per_token"], 12)]).encode())
    return h.hexdigest()[:16]


# ---------- 독립 기준(테스트용, float64) ----------
def reference_loss(nll_gt, gt_spans, nll_cands, q):
    """FP64 기준 손실 합. nll_gt: GT assistant token별 NLL(list). nll_cands: {(b,m): span token별 NLL list}. q: {(b,m): q_bm}.
    returns sum (분모 N으로 나누기 전) = CE_outside + sum_b n_b * sum_m q_bm * mean(NLL_bm)."""
    inside = set()
    for ts, te in gt_spans:
        inside.update(range(ts, te + 1))
    total = sum(v for t, v in enumerate(nll_gt) if t not in inside)
    for b, (ts, te) in enumerate(gt_spans):
        n_b = te - ts + 1
        total += n_b * q[(b, 0)] * (sum(nll_gt[ts:te + 1]) / n_b)
    for (b, m), nll in nll_cands.items():
        n_b = gt_spans[b][1] - gt_spans[b][0] + 1
        total += n_b * q[(b, m)] * (sum(nll) / len(nll))
    return total
