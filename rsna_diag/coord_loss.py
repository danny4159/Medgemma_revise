"""iter_013: 좌표 숫자 token 연결과 H/D 추가 loss.

- number_spans: JSON 문자열을 작은 scanner로 읽어 모든 숫자 literal의 (경로, 문자 구간)을 얻는다. `box_2d`의 네 정수만 좌표로 인정한다
  (key의 `2`, label, 괄호, 공백, <end_of_turn>은 절대 잡지 않는다). 값은 sft_data.target_boxes와 대조한다.
- coord_weights: assistant 본문 token의 offset으로 좌표 숫자 문자 -> 실제 chat sequence token 위치를 연결한다. 각 좌표 숫자는 정확히 한 자리
  숫자 token(id가 DIGIT_IDS)이어야 하며 아니면 예외 (조용히 제외하지 않는다). 자리 가중 = 숫자 오른쪽부터 1,2,3,4.
- loss_sums: 한 microbatch의 (CE 합, 추가 항 합). L_H = CE + alpha*sum_E w*CE_t, L_D = CE + alpha*sum_E w*KL(q_t || p_t),
  q_t(v) = softmax_v(-(v-g_t)^2/tau) (v=0..9), p_t는 전체 vocabulary softmax에서 숫자 10개 열의 확률 (재정규화 안 함).
  분모는 호출자가 effective-batch assistant token 수 N으로 나눈다. 이 loss는 39<->40 같은 자릿수 올림·내림 관계를 표현하지 않는다.
"""
import json
import re

PLAN_DIGIT_IDS = [236771, 236770, 236778, 236800, 236812, 236810, 236825, 236832, 236828, 236819]
ALPHA = 0.1
TAU = 1.0
_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_WS = " \t\n\r"


class SpanError(RuntimeError):
    pass


def number_spans(text):
    """returns [(path tuple, start, end, literal)] for every number literal (경로: 리스트 index / dict key)."""
    out = []

    def ws(i):
        while i < len(text) and text[i] in _WS:
            i += 1
        return i

    def value(i, path):
        i = ws(i)
        c = text[i]
        if c == "[":
            i = ws(i + 1)
            k = 0
            if text[i] == "]":
                return i + 1
            while True:
                i = value(i, path + (k,))
                i = ws(i)
                k += 1
                if text[i] == ",":
                    i += 1
                    continue
                if text[i] == "]":
                    return i + 1
                raise SpanError(f"bad list at {i}")
        if c == "{":
            i = ws(i + 1)
            if text[i] == "}":
                return i + 1
            while True:
                key, i = json.decoder.scanstring(text, i + 1)
                i = ws(i)
                if text[i] != ":":
                    raise SpanError(f"bad dict at {i}")
                i = value(i + 1, path + (key,))
                i = ws(i)
                if text[i] == ",":
                    i = ws(i + 1)
                    continue
                if text[i] == "}":
                    return i + 1
                raise SpanError(f"bad dict at {i}")
        if c == '"':
            return json.decoder.scanstring(text, i + 1)[1]
        m = _NUM.match(text, i)
        if m:
            out.append((path, m.start(), m.end(), m.group()))
            return m.end()
        for lit in ("true", "false", "null"):
            if text.startswith(lit, i):
                return i + len(lit)
        raise SpanError(f"bad value at {i}")

    end = ws(value(0, ()))
    if end != len(text):
        raise SpanError("trailing text")
    return out


def coord_spans(target):
    """box_2d의 정수 literal 구간 [(start, end, int)] (문서 순서). 값은 target_boxes와 같아야 한다 (호출자가 대조)."""
    res = []
    for path, s, e, lit in number_spans(target):
        if len(path) == 3 and path[1] == "box_2d" and isinstance(path[0], int) and isinstance(path[2], int):
            if not lit.isdigit():
                raise SpanError(f"non-integer coordinate literal {lit!r}")
            res.append((s, e, int(lit)))
    return res


def digit_ids(tok):
    ids = [tok.convert_tokens_to_ids(str(d)) for d in range(10)]
    if ids != PLAN_DIGIT_IDS:
        raise SpanError(f"digit token ids {ids} != plan {PLAN_DIGIT_IDS}")
    return ids


def coord_weights(tok, target, full_ids, n_prefix, dig_ids):
    """full_ids: 실제 chat sequence 1-D list(int). returns list[float] (len(full_ids)): 좌표 숫자 token 위치에 자리 가중, 나머지 0."""
    enc = tok(target + "<end_of_turn>", add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    if list(full_ids[n_prefix:n_prefix + len(ids)]) != list(ids):
        raise SpanError("assistant tokens in chat sequence != standalone tokenization of target")
    spans = coord_spans(target)
    want = [v for e in json.loads(target) for v in e["box_2d"]]
    if [v for _, _, v in spans] != want:
        raise SpanError("scanned coordinate values != json.loads box_2d values")
    w = [0.0] * len(full_ids)
    char_to_tok = {}
    for t, (s, e) in enumerate(offs):
        for c in range(s, e):
            char_to_tok[c] = t
    dset = {d: i for i, d in enumerate(dig_ids)}
    for s, e, val in spans:
        nd = e - s
        for c in range(s, e):
            t = char_to_tok.get(c)
            if t is None or tuple(offs[t]) != (c, c + 1):
                raise SpanError(f"coordinate digit at char {c} of {target[:60]!r} is not a single-character token")
            if ids[t] not in dset or str(dset[ids[t]]) != target[c]:
                raise SpanError(f"token {ids[t]} at char {c} is not digit {target[c]!r}")
            w[n_prefix + t] = float(e - c)  # 오른쪽 자리부터 1,2,3,4
    return w


def loss_sums(torch, logits, y, w, mode, dig_ids, alpha=ALPHA, tau=TAU):
    """logits [M,V] float32(softcap 이후), y [M] long, w [M] float(좌표 자리 가중, 그 외 0).
    returns (ce_sum, extra_sum). extra_sum은 alpha를 곱하기 전 sum_E w * (CE 또는 KL). C는 0."""
    lse = torch.logsumexp(logits, dim=-1)
    ce = lse - logits.gather(1, y[:, None]).squeeze(1)
    ce_sum = ce.sum()
    zero = ce_sum.new_zeros(())
    if mode == "C":
        return ce_sum, zero
    E = w > 0
    if not bool(E.any()):
        return ce_sum, zero
    if mode == "H":
        return ce_sum, (w[E] * ce[E]).sum()
    if mode == "D":
        di = torch.as_tensor(dig_ids, device=logits.device)
        lp = logits[E][:, di] - lse[E][:, None]  # 전체 vocabulary 정규화 log p (숫자 10개 열)
        inv = torch.full((int(logits.shape[1]),), -1, dtype=torch.long, device=logits.device)
        inv[di] = torch.arange(10, device=logits.device)
        g = inv[y[E]]
        if bool((g < 0).any()):
            raise SpanError("coordinate label token is not a digit")
        v = torch.arange(10, device=logits.device, dtype=logits.dtype)
        logq = torch.log_softmax(-((v[None, :] - g[:, None].to(logits.dtype)) ** 2) / tau, dim=-1)
        kl = (logq.exp() * (logq - lp)).sum(-1)
        return ce_sum, (w[E] * kl).sum()
    raise ValueError(mode)
