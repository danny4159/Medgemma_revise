"""iter_136: 출력 전에 고정한 prompt(i134와 동일 문구)·상태 parser·thought/final 경계 규칙·조건표.
질문: 제공된 영상 전체 중 어느 하나에 종양성 병변이 보이는가 (PRESENT/ABSENT/UNKNOWN). annotation-defined 정답이며 임상 진단이 아니다."""
from i134_spec import QUESTION, NOIMG, FORBIDDEN_IN_PROMPT, CONDS, VALID, parse as _parse, audit, repetition, first_line  # noqa: F401  (문구·세 상태 규칙을 그대로 사용)

BASE_CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', dtype='bfloat16',
                   attention='sdpa', do_sample=False, seed=136, batch=1, image_labels=False)
TOKENS = dict(technical=1024, technical2048=2048)   # main은 technical_gate.json의 main_max_new_tokens
STAGES = ['technical', 'technical2048', 'main']
START_TOKEN, END_TOKEN = '<unused94>', '<unused95>'   # 문자열만 고정. id는 실행 시 tokenizer에서 읽고 tests/boundary_check.json에 기록한다.


def split_final(tokens, start_id, end_id):
    """생성 token에서 final 구간을 token 구조로 분리. 반환 (status, final_tokens).
    no_marker: 두 표식 모두 없음 → 생성 전체. thought_final: 시작 1개가 맨 앞, 종료 1개가 그 뒤 → 종료 뒤 구간.
    invalid_boundary: 그 외(복수·종료 없는 시작·시작 없는 종료·순서 역전·시작이 맨 앞이 아님)."""
    ns, ne = tokens.count(start_id), tokens.count(end_id)
    if ns == 0 and ne == 0: return 'no_marker', list(tokens)
    if ns == 1 and ne == 1 and tokens[0] == start_id and tokens.index(end_id) > 0:
        return 'thought_final', list(tokens[tokens.index(end_id) + 1:])
    return 'invalid_boundary', []


def parse(final_text, eos, status):
    """상태 parser: EOS 종료 + 경계 유효 + final 비어있지 않음 + i134 세 상태 규칙."""
    if status == 'invalid_boundary' or not (final_text or '').strip(): return None
    return _parse(final_text, eos)
