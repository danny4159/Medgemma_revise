"""iter_137: 출력 전에 고정한 두 인터페이스(A=원 질문, B=마지막 설명 요구 문장만 삭제)·상태 parser·thought/final 경계 규칙.
상태 parser·audit·repetition·thought 경계는 i134/i136 규칙을 그대로 쓴다(결과를 보고 바꾸지 않는다)."""
from i134_spec import QUESTION, FORBIDDEN_IN_PROMPT, VALID, parse as _parse, audit, repetition, first_line  # noqa: F401

EXPL = ' Then give one short sentence of visible evidence.'
QUESTION_A = QUESTION
QUESTION_B = QUESTION[:-len(EXPL)] if QUESTION.endswith(EXPL) else None
assert QUESTION_B is not None and QUESTION_A == QUESTION_B + EXPL and QUESTION_B.endswith('provided images.') and 'Then give' not in QUESTION_B
PROMPTS = dict(A=QUESTION_A, B=QUESTION_B)
IFACES = ('A', 'B')
ROLES = dict(P=['P'], N1=['N1'])   # P=annotation 최대 면적 slice, N1=annotation 면적 0 slice
TRUTH = dict(P='PRESENT', N1='ABSENT')

BASE_CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', dtype='bfloat16',
                   attention='sdpa', do_sample=False, seed=136, batch=1, image_labels=False)
TOKENS = dict(technical=1024, technical2048=2048)   # main은 tests/technical_gate.json의 main_max_new_tokens
STAGES = ['technical', 'technical2048', 'main']
START_TOKEN, END_TOKEN = '<unused94>', '<unused95>'


def split_final(tokens, start_id, end_id):
    """생성 token에서 final 구간 분리 (i136과 동일 규칙). no_marker / thought_final / invalid_boundary."""
    ns, ne = tokens.count(start_id), tokens.count(end_id)
    if ns == 0 and ne == 0: return 'no_marker', list(tokens)
    if ns == 1 and ne == 1 and tokens[0] == start_id and tokens.index(end_id) > 0:
        return 'thought_final', list(tokens[tokens.index(end_id) + 1:])
    return 'invalid_boundary', []


def parse(final_text, eos, status):
    """EOS + 경계 유효 + final 비어있지 않음 + i134 세 상태 규칙(첫 줄)."""
    if status == 'invalid_boundary' or not (final_text or '').strip(): return None
    return _parse(final_text, eos)


def extra_text(final_text):
    """첫 줄 이후 설명 텍스트가 있는가 (B의 추가 설명 발생률 보고용)."""
    lines = (final_text or '').strip().splitlines()
    return any(l.strip() for l in lines[1:])
