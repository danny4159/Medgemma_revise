"""iter_061 parser v2 (D에서 관찰한 형식 변이로만 결정, E 결과 미사용).

D 관찰: MedGemma가 'ANSWER: X' 대신 'Final Answer: The final answer is $\\boxed{X}$' 형식을 자주 사용.
v2 = 마지막 비공백 줄이 (a) 정확히 'ANSWER: X' 또는 (b) 'Final Answer: ...\\boxed{X}' (X는 A–E 한 글자, 줄 내 boxed 하나)일 때 유효.
strict(v1)는 mri61_spec.parse_answer로 별도 보고한다.
"""
import re
import mri61_spec as S

BOX = re.compile(r'^(?:\*\*)?Final Answer:?(?:\*\*)?.*\\boxed\{\s*([A-E])\s*\}.*$', re.I)


def parse_v2(text):
    a = S.parse_answer(text)
    if a:
        return a
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None
    last = lines[-1].strip()
    if len(re.findall(r'\\boxed\{', last)) != 1:
        return None
    m = BOX.match(last)
    return m.group(1) if m else None
