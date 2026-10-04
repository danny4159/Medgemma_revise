"""iter_054 고정 명세: prompt, parser, 순수 점수 함수. GPU·파일 의존 없음 (단위 검사 가능)."""
import hashlib
import math
import re

MC_TEMPLATE = ("Based on the image, choose the correct option for the following question.\nQuestion: {q}\nA: {a}\nB: {b}\n"
               "Answer with the option's letter from the given choices directly. Your answer should be just one letter.\nAnswer:")
CAPS_MC = [128, 512, 2048]
ORDERS = ("orig", "swap")
SEED = 54
SPEC_VERSION = "mc54_spec_v1"


def sha(s):
    return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()


def mc_prompt(question, opt_a, opt_b, order):
    """order=swap이면 표시되는 A/B 위치에 원래 option_B/option_A를 둔다."""
    if order == "orig":
        return MC_TEMPLATE.format(q=question, a=opt_a, b=opt_b)
    if order == "swap":
        return MC_TEMPLATE.format(q=question, a=opt_b, b=opt_a)
    raise ValueError(order)


def to_canonical_letter(shown, order):
    """표시된 문자(A/B)를 원래(canonical) option 문자로. swap이면 뒤집는다. None/'-'은 그대로."""
    if shown not in ("A", "B"):
        return shown
    return shown if order == "orig" else ("B" if shown == "A" else "A")


def canonical_margin(shown_margin, order):
    """표시 A−B margin → canonical(option_A − option_B) margin. swap은 부호를 되돌린다."""
    return shown_margin if order == "orig" else -shown_margin


# ---------------- parsers ----------------
SPECIAL = ("<end_of_turn>", "<eos>", "<pad>")


def clean_decoded(text):
    """skip_special_tokens=True 디코딩과 같게 종료·패딩 special token 문자열을 제거한다 (공식 LLaVA 경로는 special token을 제거해 parser에 전달)."""
    if text is None:
        return None
    for t in SPECIAL:
        text = text.replace(t, "")
    return text


def parse_official_manual(answer):
    """공식 clean_up_manual 이식: 개행→공백, 공백 split 후 valid_list 토큰과 정확히 일치하는 항목 탐색. 둘 다 맞으면 무효.
    returns 'A'|'B'|'-'."""
    scores = {"A": 0, "B": 0}
    answer = clean_decoded(answer)
    if answer is not None:
        tmp = answer.replace("\n", " ").split(" ")
        for la in ("A", "B"):
            valid = [f"{la}", f"{la}:", f".{la}", f".{la}:", f"{la}.", f'{la}")', f"{la}\n", f"\n{la}", f'("{la}":',
                     f'("{la}")', f'("{la}").']
            if any(x in tmp for x in valid):
                scores[la] = 10
    if sum(1 for v in scores.values() if v == 10) > 1:
        scores = {"A": 0, "B": 0}
    # 공식 check_answer(tr=3): 한쪽만 10이면 선택
    if scores["A"] >= scores["B"] + 3:
        return "A"
    if scores["B"] >= scores["A"] + 3:
        return "B"
    return "-"


_STRICT = re.compile(r"^\s*(?:\*\*)?\(?\s*([AB])\s*\)?(?:\*\*)?\s*[.:)]?\s*$")


def parse_strict(text):
    """whole-string 전체가 공백·괄호·굵은 표시·문장부호를 제외하고 A 또는 B 한 글자일 때만 인정한다. 설명 속 문자는 찾지 않는다."""
    if text is None:
        return "-"
    t = clean_decoded(text).strip()
    m = _STRICT.match(t)
    return m.group(1) if m else "-"


# ---------------- 점수 ----------------
def mean_ll(logps):
    return sum(logps) / len(logps)


def pick_from_margin(m, tol=0.0):
    """margin>0 → A, <0 → B, 정확한 동점(|m|<=tol, 기본 0) → abstain('-')."""
    if m is None or (isinstance(m, float) and math.isnan(m)):
        return "-"
    if m > tol:
        return "A"
    if m < -tol:
        return "B"
    return "-"


def set_outcome(ans1, ans2, truth1, truth2):
    """공식 get_score: returns (correct1, invalid1, correct2, invalid2, confused)."""
    return (int(ans1 == truth1), ans1 == "-", int(ans2 == truth2), ans2 == "-", int(ans1 == ans2 and ans1 != "-"))


def orientation(margin_correctA_image, margin_correctB_image):
    """정답 A 영상의 canonical margin이 정답 B 영상보다 크면 1, 작으면 0, 동점 0.5. (평가 코드 전용)"""
    if margin_correctA_image > margin_correctB_image:
        return 1.0
    if margin_correctA_image < margin_correctB_image:
        return 0.0
    return 0.5
