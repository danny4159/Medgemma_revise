"""iter_116 오류 혼합 근거의 선택적 교정 진단: 표본 선택, 입력 문구, 근거 packet, 정책 정의 (생성 전에 잠근다).

- 표적은 기존 Q_O 'pulmonary opacity suspicious for pneumonia' 하나. 정답(GT)은 이 모듈에서 읽지 않는다.
- 답 추출은 ev109_extract_v1 (resolve, target O)을 그대로 쓴다. unresolved/비EOS를 Yes/No로 바꾸지 않는다.
- packet은 detector17 epoch18 score>=0.70 후보만 포함하며 GT로 제거·정렬하지 않는다.
"""
import hashlib
import json

import ev108_spec as S
import ev109_extract as X
from rsna_diag import qa_spec

SPEC_VERSION = "ed116_spec_v1"
THR = 0.70
SEED_BOOT = 11617
N_BOOT = 10000
CAPS = [1000, 2000, 4000]
N_TECH = 12
N_CTRL = 87
COND_ORDER = ("N", "E", "R", "T")
IMAGE_CONDS = ("N", "E", "R")
Q = qa_spec.Q_O
FMT = qa_spec.FORMATS["plain"]  # "Answer only yes or no."


def sha(s):
    return hashlib.sha256(s if isinstance(s, bytes) else s.encode()).hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


# ---------------- 선택 ----------------
def sel_key(patient):
    return sha("iter116|" + patient)


def det_boxes(row, thr=THR):
    """score>=thr 후보를 score 내림차순, 동률은 좌표 오름차순으로. returns list of (score, [x0,y0,x1,y1] 원본 pixel)."""
    d = row["det"]
    c = [(s, list(b)) for s, b in zip(d["scores"], d["boxes_xyxy_px"]) if s >= thr]
    c.sort(key=lambda t: (-t[0], t[1]))
    return c


def answer_K(row):
    r = X.resolve("O", row["O"]["raw"], row["O"]["ended_eos"])
    return r["answer"]


def answer_B(row):
    return "yes" if det_boxes(row) else "no"


def answer_G(row):
    st, _ = S.parse_saved_bbox(row["SFT"]["raw"], row["SFT"]["ended_eos"])
    return {"ok": "yes", "empty": "no"}.get(st)  # invalid/truncated → None(unresolved)


def select(rows):
    """returns dict. 일치/불일치 판정은 K(저장 직접 답, 초안 없는 원 Q_O 응답)와 B(detector)만 쓴다. GT는 사용하지 않는다."""
    unresolved, mismatch, agree = [], [], []
    for r in rows:
        k = answer_K(r)
        if k is None:
            unresolved.append(r["id"])
        elif k != answer_B(r):
            mismatch.append(r["id"])
        else:
            agree.append(r["id"])
    byid = {r["id"]: r for r in rows}
    order = sorted(agree, key=lambda i: sel_key(byid[i]["patient"]))
    tech, ctrl = order[:N_TECH], order[N_TECH:N_TECH + N_CTRL]
    mismatch = sorted(mismatch, key=lambda i: sel_key(byid[i]["patient"]))
    return dict(mismatch=mismatch, agree_all=sorted(agree), tech=tech, control=ctrl, unresolved=sorted(unresolved),
                rule="agree sorted by sha256('iter116|'+patient) asc: first 12 tech, next 87 control; mismatch=resolved K != B, all 87",
                n=dict(mismatch=len(mismatch), agree=len(agree), unresolved=len(unresolved), tech=len(tech), control=len(ctrl)))


# ---------------- 입력 문구 ----------------
def draft_text(ans):
    return f"An automatic first-pass answer to this question was: {ans.capitalize()}."


def packet_text(row):
    h, w = row["size_hw"]
    c = det_boxes(row)
    if not c:
        return "No candidate met the detector threshold; this does not establish absence."
    lines = [f"An automatic detector (score threshold {THR:.2f}) proposed {len(c)} candidate region(s) for pulmonary opacity. "
             "Boxes are [x0, y0, x1, y1] as fractions of the original image width and height (x to the right, y downward)."]
    for n, (s, b) in enumerate(c, 1):
        x0, y0, x1, y1 = b
        lines.append(f"Candidate {n}: score {s:.3f}, box [{x0 / w:.3f}, {y0 / h:.3f}, {x1 / w:.3f}, {y1 / h:.3f}]")
    return "\n".join(lines)


INSTR = {"N": "The first-pass answer may be wrong.", "E": "The detector output may be wrong.",
         "R": "The first-pass answer and the detector output may each be wrong.",
         "T": "The first-pass answer and the detector output may each be wrong."}
LEAD = "Use the information available to you to answer the question about this chest radiograph."


def build_prompt(cond, row, draft):
    parts = [f"Question: {Q}"]
    if cond in ("N", "R", "T"):
        parts.append(draft_text(draft))
    if cond in ("E", "R", "T"):
        parts.append(packet_text(row))
    parts.append(INSTR[cond])
    parts.append(f"{LEAD} {FMT}")
    return "\n\n".join(parts)


def request_id(patient, cond, prompt_sha, pixel_sha, revision):
    return sha(canon(dict(patient=patient, cond=cond, prompt_sha256=prompt_sha, input_pixel_sha256=pixel_sha, caps=CAPS,
                          model_revision=revision, spec=SPEC_VERSION)))[:32]


# ---------------- 정책 ----------------
def majority(k, b, g):
    """K/B/G 다수결. G unresolved이면 K 유지."""
    if g is None:
        return k
    return max((k, b, g), key=[k, b, g].count)


def policy_answers(row, model_ans):
    """model_ans: dict cond→answer|None (N/E/R/T). returns dict policy→answer|None."""
    k, b, g = answer_K(row), answer_B(row), answer_G(row)
    e = model_ans.get("E")
    s = e if (e is not None and e == b) else k
    return dict(K=k, B=b, G=g, M=majority(k, b, g), N=model_ans.get("N"), E=e, R=model_ans.get("R"), T=model_ans.get("T"), S=s)


def rules_digest():
    import inspect
    import sys
    return sha(inspect.getsource(sys.modules[__name__]))
