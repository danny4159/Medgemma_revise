"""iter_134: GPU 출력 전에 고정한 prompt·상태 parser·명시 모순 규약·렌더 설정·조건표.
질문: 제공된 영상 전체 중 어느 하나에 종양성 병변이 보이는가 (PRESENT/ABSENT/UNKNOWN). annotation-defined 정답이며 임상 진단이 아니다."""
import re
from pathlib import Path

BASE_CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', dtype='bfloat16',
                   attention='sdpa', do_sample=False, seed=134, batch=1, image_labels=False)   # image_labels=False: v1 기술 실행(라벨 있음, T_w2)과 구분
TOKENS = dict(technical=1024, technical2048=2048)   # main은 technical_gate.json의 main_max_new_tokens
STAGES = ['technical', 'technical2048', 'main']

QUESTION = ('The following FLAIR MRI image(s) of one brain are provided. '
            'Question: is a tumor-like lesion visible in at least one of the provided images? '
            'On the first line output only one word: PRESENT, ABSENT, or UNKNOWN. '
            'PRESENT means a lesion is visible in at least one provided image. '
            'ABSENT means no lesion is visible in any provided image. '
            'UNKNOWN means this cannot be judged from the provided images. '
            'Then give one short sentence of visible evidence.')
NOIMG = ' In this input no MRI image is provided.'
LABEL = 'Image %d:\n'
FORBIDDEN_IN_PROMPT = ['BraTS', 'GLI', 't2f', 'glioma', 'edema', 'RadGenome', 'sub-', 'report', 'annotation', 'mask']

# 조건: id -> 관측 구성(P=최대 종양 면적 axial slice, N1/N2=종양 annotation 0인 뇌 slice, 물리 거리 순)
CONDS = dict(P=['P'], N1=['N1'], N2=['N2'], PN1=['P', 'N1'], N1P=['N1', 'P'], N1N2=['N1', 'N2'], N2N1=['N2', 'N1'],
             PP=['P', 'P'], N1N1=['N1', 'N1'], NONE=[])
RENDER = dict(side=896, normalization='volume_minmax', orientation='closest_canonical_RAS', mask_rule='seg>0 (whole tumor)',
              N_min_brain_area_frac=0.5, P_rule='max whole-tumor area axial slice, tie lowest z', N_rule='tumor area 0, brain area>=0.5*max, nearest |dz|*zoom, tie lowest z')

VALID = ('PRESENT', 'ABSENT', 'UNKNOWN')


def first_line(text):
    if not text or not text.strip():
        return None
    return text.strip().splitlines()[0].strip()


def parse(text, eos=True):
    """엄격 parser: EOS 종료, 첫 줄이 (양끝 ** 와 끝 마침표만 제거한 뒤) 세 상태 중 정확히 하나."""
    if not eos:
        return None
    ln = first_line(text)
    if ln is None:
        return None
    ln = ln.strip('*').strip().rstrip('.').strip('*').strip()
    return ln if ln in VALID else None


NEG = re.compile(r'\b(no|without|not|absence of|free of)\b(?:(?!\b(?:but|and|with|however|while)\b)[^.\n,;]){0,30}?\b(lesion|tumou?r|mass|abnormal\w*|hyperintens\w*)', re.I)
POS = re.compile(r'\b(hyperintens\w*|abnormal signal|lesion (is|are) (visible|seen|present)|visible (lesion|mass)|a (lesion|mass|tumou?r) (is|in|at|within|located))\b', re.I)
NOIMG_PHRASE = re.compile(r'\b(no (mri )?images? (is|are|was|were)? ?(provided|available)|cannot (assess|judge)|unable to (assess|judge))\b', re.I)


def audit(text, state):
    """첫 줄 상태와 설명문의 명시 모순 감사. 반환: 'consistent' | 'contradiction' | 'unresolved' | 'na'. 모호하면 unresolved. 원 답은 바꾸지 않는다."""
    if state is None:
        return 'na'
    lines = (text or '').strip().splitlines()[1:]
    body = ' '.join(l.strip() for l in lines if l.strip())
    if not body:
        return 'unresolved'
    neg = bool(NEG.search(body)); pos = bool(POS.search(NEG.sub(' ', body)))   # 부정 구절을 제거한 뒤 양성 표현을 찾는다
    if state == 'PRESENT':
        if neg and not pos: return 'contradiction'
        return 'consistent' if pos and not neg else 'unresolved'
    if state == 'ABSENT':
        if pos and not neg: return 'contradiction'
        return 'consistent' if neg and not pos else 'unresolved'
    return 'unresolved'


def repetition(text, n_tokens=None, cap=None):
    """동일 문장이 3회 이상 반복되거나 동일 줄 연속 반복."""
    sents = [s.strip().lower() for s in re.split(r'(?<=[.!?])\s+|\n+', text or '') if len(s.strip()) > 8]
    from collections import Counter
    return bool(sents) and max(Counter(sents).values()) >= 3
