"""iter_053 CheXpert 교정·보존 진단: 고정 상수·prompt·평가 규칙 (CPU only).

rr47_spec의 상태 parser·finding 문장·R1/R2/BJ/BI prompt를 그대로 재사용한다(승인 범위: 상태 parser). 이 파일이 바꾸는 것:
(1) T는 R2 텍스트와 byte-identical (영상만 제거; 영상 부재 안내·uncertain 유도 없음), (2) BT = BJ 텍스트 byte-identical 영상 제거,
(3) oracle O2 = 기존 O + 출처 우선순위 문장, (4) 새 version/seed. GT/truth는 평가 함수에만 인자로 들어간다.
"""
import rr47_spec as B

VERSION = "rr53_v1"
SEED = 5301
BOOT_SEED = 5302
BOOT_B = 10000
CAPS = B.CAPS
IDS = B.IDS
STATES = B.STATES
DRAFT_CODES = B.DRAFT_CODES
FINDING_PAIR = {"qA": "cardiomegaly", "qB": "effusion"}   # CheXpert 고정 두 finding (cardiomegaly / pleural effusion)
FINDINGS = B.FINDINGS
sha = B.sha
canon = B.canon
flip = B.flip
code_states = B.code_states
draft_code = B.draft_code
draft_text = B.draft_text
parse_state = B.parse_state
final_state = B.final_state
render_final = B.render_final

AUTH_SENTENCE = ("For this consistency check, the verified final status is authoritative. Copy it exactly; "
                 "do not infer a different status from the draft or image.")

prompt_R1 = B.prompt_R1
prompt_R2 = B.prompt_R2
prompt_BJ = B.prompt_BJ
prompt_BI = B.prompt_BI


def prompt_T(items):
    """R2와 byte-identical (영상만 요청에서 제거)."""
    return B.prompt_R2(items)


def prompt_BT(finding_pair):
    """BJ와 byte-identical (영상만 요청에서 제거)."""
    return B.prompt_BJ(finding_pair)


def prompt_O2(items, truth_pair):
    """기존 O prompt + 출처 우선순위 문장(사전 고정). 같은 텍스트를 image/text 두 modality에 쓴다."""
    base = B.prompt_O(items, truth_pair)
    marker = "Return the verified final status of each finding."
    assert base.count(marker) == 1
    return base.replace(marker, marker + " " + AUTH_SENTENCE)


def request_id(kind, patient, cond, targets, prompt_sha, image_sha):
    return sha(f"{VERSION}|{kind}|{patient}|{cond}|{','.join(targets)}|{prompt_sha}|{image_sha}")[:32]


def code_of_category(cat):
    """'present_absent' -> '10' (qA=cardiomegaly, qB=pleural effusion)."""
    cm, pe = cat.split("_")
    return f"{int(cm == 'present')}{int(pe == 'present')}"


CATEGORY_OF_CODE = {"00": "absent_absent", "01": "absent_present", "10": "present_absent", "11": "present_present"}
