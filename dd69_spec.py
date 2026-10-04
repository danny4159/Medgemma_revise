"""iter_069 고정 명세: 영상 확인 후 적격 20 case, 중립 대상 문구, 7개 조건 prompt, 엄격 parser.

추론 입력은 sequence 이름·중립 위치/표식 참조만 포함한다. caption/IMAGING_FINDINGS/진단/선택지는 일반 추론 입력에 넣지 않는다.
parser는 전체 문자열의 대소문자·공백·끝 문장부호만 정규화한다 (내용 정확도에 맞춘 수정 금지).
"""
import re

SPEC_VERSION = "dd69_spec_v1"

# (case, DWI idx, ADC idx, ADC label, 중립 대상 문구). label: LOW=ADC 감소, NOT_LOW=ADC 비감소.
# 영상 확인(2026-10-04, results/iter_069/cand/sheet_*.png 직접 열람)을 통과한 20 case. 출력 전에 고정.
ELIGIBLE = [
    (7006, 9, 8, "LOW", "the vertebral bodies of the spine"),
    (7529, 10, 11, "LOW", "the focal lesion in the breast"),
    (8511, 7, 8, "LOW", "the lesion in the posterior fossa"),
    (12899, 2, 1, "LOW", "the mass in the left pelvic region"),
    (13776, 5, 6, "LOW", "the bilateral putamina"),
    (14583, 7, 8, "LOW", "the lesion indicated by the small blue marker"),
    (14665, 5, 6, "LOW", "the right lacrimal fossa lesion"),
    (14955, 7, 8, "NOT_LOW", "the lesion in the cerebellum"),
    (15611, 17, 18, "NOT_LOW", "the regions indicated by the arrows along the optic pathway and hypothalamic region"),
    (16138, 4, 5, "LOW", "the lesion indicated by the arrow or asterisk"),
    (16818, 6, 7, "LOW", "the intestinal wall region indicated by the yellow arrow"),
    (17812, 4, 5, "LOW", "the lesion marked by the star"),
    (17999, 5, 7, "LOW", "the cortical regions indicated by the black arrows"),
    (18326, 7, 8, "LOW", "the structure indicated by the green arrow"),
    (18487, 3, 4, "NOT_LOW", "the bilateral thalami"),
    (18529, 3, 4, "LOW", "the lesion marked by the star"),
    (18569, 3, 4, "LOW", "the lesion in the prostate region"),
    (18862, 10, 11, "LOW", "the lesion indicated by the green arrow"),
    (18963, 7, 8, "NOT_LOW", "the frontal lesions indicated by the arrows or triangles"),
    (19278, 6, 7, "NOT_LOW", "the lesion in the spleen"),
]

# 영상 확인 후 제외(후보 26 중 6): 사유는 sheet 열람 기반
VISUAL_EXCLUDED = {
    1017: "ADC에 pixel value 수치 overlay, 대상 표식·위치 불명",
    5324: "대상 영상 근거 불명 (DWI에서 고신호 확인 불가, 표식 없음)",
    17136: "DWI/ADC 확대·시야 달라 동일 대상 연결 불명",
    18805: "DWI·ADC 단면 level 불일치",
    18876: "대상 위치 표식 없음, 병변 연결 불명",
    18942: "ADC가 color map이며 ROI 수치 overlay",
}

CONDS = ["SD", "SA", "A", "J_DA", "J_AD", "T", "O"]
COND_ORDER = {c: i for i, c in enumerate(CONDS)}
# 조건별 입력 영상 종류 순서
COND_IMAGES = {"SD": ["DWI"], "SA": ["ADC"], "A": ["ADC"], "J_DA": ["DWI", "ADC"], "J_AD": ["ADC", "DWI"], "T": [], "O": []}
R_COND = "R"  # ADC 동일 영상 두 장 복제 (조건부)

QUESTION = "Does {t} show restricted diffusion? Answer with exactly one word: YES, NO, or UNCERTAIN."


def prompt(cond, target, label=None):
    """label은 O(oracle)에서만 사용. 다른 조건은 label=None이어야 한다."""
    if cond != "O" and label is not None:
        raise ValueError("label allowed only for O")
    if cond == "SD":
        return (f"This is a diffusion-weighted image (DWI) of a patient. Look at {target}. "
                "Is its signal intensity HIGH compared with the surrounding tissue? "
                "Answer with exactly one word: HIGH, NOT_HIGH, or UNCERTAIN.")
    if cond == "SA":
        return (f"This is an apparent diffusion coefficient (ADC) map of a patient. Look at {target}. "
                "Is its signal intensity LOW compared with the surrounding tissue? "
                "Answer with exactly one word: LOW, NOT_LOW, or UNCERTAIN.")
    if cond == "A":
        return f"This is an apparent diffusion coefficient (ADC) map of a patient. " + QUESTION.format(t=target)
    if cond == "J_DA":
        return ("The first image is a diffusion-weighted image (DWI) and the second image is the corresponding ADC map of the same patient. "
                + QUESTION.format(t=target))
    if cond == "J_AD":
        return ("The first image is an ADC map and the second image is the corresponding diffusion-weighted image (DWI) of the same patient. "
                + QUESTION.format(t=target))
    if cond == "R":
        return ("The two images are duplicate copies of the same apparent diffusion coefficient (ADC) map of a patient. " + QUESTION.format(t=target))
    if cond == "T":
        return "No image is provided. A patient had a diffusion-weighted MRI examination. " + QUESTION.format(t=target)
    if cond == "O":
        if label not in ("LOW", "NOT_LOW"):
            raise ValueError("O needs label")
        adc = "low" if label == "LOW" else "not low (not reduced)"
        return (f"No image is provided. In a diffusion-weighted MRI examination, the signal of {target} is high on the DWI image "
                f"and {adc} on the ADC map. " + QUESTION.format(t=target))
    raise ValueError(cond)


ANSWER_SETS = {"SD": ("HIGH", "NOT_HIGH", "UNCERTAIN"), "SA": ("LOW", "NOT_LOW", "UNCERTAIN"),
               "A": ("YES", "NO", "UNCERTAIN"), "J_DA": ("YES", "NO", "UNCERTAIN"), "J_AD": ("YES", "NO", "UNCERTAIN"),
               "T": ("YES", "NO", "UNCERTAIN"), "O": ("YES", "NO", "UNCERTAIN"), "R": ("YES", "NO", "UNCERTAIN")}


def parse(cond, text):
    """전체 문자열 정규화만. 허용 집합 밖이면 None(invalid)."""
    t = text.replace("<end_of_turn>", "").strip()
    t = re.sub(r"[\s.!?,;:]+$", "", t).strip().upper()
    return t if t in ANSWER_SETS[cond] else None


def gt(cond, label):
    """조건별 정답 문자열. SD는 선택 집단 전체가 HIGH."""
    if cond == "SD":
        return "HIGH"
    if cond == "SA":
        return "LOW" if label == "LOW" else "NOT_LOW"
    return "YES" if label == "LOW" else "NO"
