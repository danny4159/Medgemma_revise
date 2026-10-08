"""iter_101 교정 요청 구성: T(텍스트만) / V(올바른 영상 + 동일 텍스트) / W(반대 흉수 상태 환자 영상 + 동일 텍스트). K/A는 GPU 요청 없음.

모델 입력에는 reference 문장·상태·평가 라벨·충돌 판정을 넣지 않는다. 초안 = CURE 'Generate a grounded report.' 원출력에서 좌표 [a,b,c,d]만 제거(공백 정규화),
영역 설명 = 'Describe the left/right costophrenic angle.' 원출력에서 'Description of the ...:' 머리말만 제거. 두 영역 설명은 항상 같은 순서로 모두 제공한다.
T와 V/W 지시문은 영상 문구 외에는 동일하다. V/W는 prompt가 byte 동일하다.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from report86_common import ROOT, sha, sha_obj, save, read_jsonl_complete

R101 = ROOT / 'results/iter_101'
DATA = R101 / 'data'
COORD = re.compile(r"\[\s*-?\d*\.?\d+(?:\s*,\s*-?\d*\.?\d+){3}\s*\]")
HDR = re.compile(r"^Description of the (left|right) costophrenic angle:\s*(.*)$", re.S)

HEAD = ("Below is a draft chest X-ray report and two automatically generated notes about the left and right costophrenic angles. "
        "The draft and the notes were generated automatically and may be incorrect or may contradict each other.\n\n"
        "Draft report:\n%s\n\nLeft costophrenic angle note:\n%s\n\nRight costophrenic angle note:\n%s\n\n")
TASK_T = ("Task: Review the draft report and the notes, and resolve any contradictions between them. "
          "Keep every statement of the draft that is supported by the provided text. "
          "Change or remove a statement only when the provided text supports doing so, and do not state a finding as definite when it cannot be determined. "
          "Output only the final revised report text.")
TASK_IMG = ("Task: Review the draft report and the notes against the attached chest X-ray image, and resolve any contradictions between them. "
            "Keep every statement of the draft that is supported by the image or the notes. "
            "Change or remove a statement only when the image or the notes support doing so, and do not state a finding as definite when it cannot be determined. "
            "Output only the final revised report text.")


def norm_ws(s):
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+([.,;:])", r"\1", s)


def clean_draft(text):
    return norm_ws(COORD.sub("", text))


def clean_note(text, side):
    t = text.strip()
    m = HDR.match(t)
    assert m and m.group(1) == side, ("unexpected note header", t[:80])
    body = norm_ws(COORD.sub("", m.group(2)))
    return body


def load_cure(stage, path=None):
    """완료·변조 검증을 통과한 CURE 출력만 {ImageID: {G, CL, CR 원 record}}로 반환한다."""
    import report101_cure as C
    out = Path(path) if path else R101 / 'cure' / ('S24' if stage == 'S24' else 'D4_w2')
    mp = json.loads((out / 'mapping.json').read_text())
    reqs = C.requests(stage)
    reqmap = {r['id']: r for r in reqs}
    sd = C.sha_obj(C.scientific_protocol(stage, mp['workers']))
    assert mp['scientific_digest'] == sd, 'mapping digest differs from current protocol/sources'
    assert (out / 'completion.json').exists(), 'CURE stage not complete'
    recs = {}
    for s in range(mp['workers']):
        c, rr = C.verify_completion(out / f'shard{s}', reqmap, sd)
        for r in rr:
            recs.setdefault(r['ImageID'], {})[r['fmt']] = r
    assert sum(len(v) for v in recs.values()) == len(reqs)
    return recs


def package(img, recs):
    r = recs[img]
    return {'ImageID': img, 'draft': clean_draft(r['G']['text']), 'left': clean_note(r['CL']['text'], 'left'),
            'right': clean_note(r['CR']['text'], 'right'),
            'non_eos': [k for k, v in r.items() if not v['attempts'][-1]['ended_eos']]}


def prompt(pk, cond):
    return HEAD % (pk['draft'], pk['left'], pk['right']) + (TASK_T if cond == 'T' else TASK_IMG)


def build_requests(ids, recs, rows, donors):
    """ids: 선정 환자(순서 고정). rows: ImageID -> inputs row. donors: recipient -> donor ImageID. 요청은 환자 순서, 조건 T,V,W."""
    reqs, info = [], []
    for img in ids:
        pk = package(img, recs)
        d = donors[img]
        for c in ('T', 'V', 'W'):
            src = None if c == 'T' else (img if c == 'V' else d)
            reqs.append({'id': f'{img}|{c}', 'ImageID': img, 'cond': c, 'image': None if src is None else rows[src]['image'],
                         'file_sha256': None if src is None else rows[src]['file_sha256'],
                         'image_source_ImageID': src, 'prompt': prompt(pk, c)})
        info.append({'ImageID': img, 'donor': d, 'draft_chars': len(pk['draft']), 'non_eos_sources': pk['non_eos']})
    return reqs, info


def leak_check(reqs, refs, pks=None):
    """prompt에 reference 문장/평가 단어가 들어갔는지 검사한다(문장 전체 일치 + 금지어).
    CURE 원출력(초안·영역 설명)은 모델이 만든 입력이므로 그 구간을 제거한 나머지(지시문 틀)에서 검사한다."""
    bad = []
    for r in reqs:
        body = r['prompt']
        if pks:
            pk = pks[r['ImageID']]
            for t in (pk['draft'], pk['left'], pk['right']):
                body = body.replace(t, '')
        for s in refs.get(r['ImageID'], []):
            if len(s) > 12 and s.lower().strip('. ') in body.lower():
                bad.append({'id': r['id'], 'sentence': s})
        for w in ('reference', 'ground truth', 'conflict', 'donor'):
            if w in r['prompt'].lower():
                bad.append({'id': r['id'], 'word': w})
    return bad


def identity_check(reqs):
    """V/W prompt byte 동일, T/V/W 텍스트가 TASK 문구 외 동일, T는 image 없음, V는 자기 영상, W는 다른 환자 영상."""
    problems = []
    for img in sorted({r['ImageID'] for r in reqs}):
        by = {r['cond']: r for r in reqs if r['ImageID'] == img}
        if sorted(by) != ['T', 'V', 'W']:
            problems.append({'img': img, 'problem': 'conditions'})
            continue
        if by['V']['prompt'] != by['W']['prompt']:
            problems.append({'img': img, 'problem': 'V_W_prompt_differs'})
        if by['T']['prompt'].replace(TASK_T, '') != by['V']['prompt'].replace(TASK_IMG, '') or not by['T']['prompt'].endswith(TASK_T):
            problems.append({'img': img, 'problem': 'T_vs_V_head_differs'})
        if by['T']['image'] is not None or by['V']['image_source_ImageID'] != img or by['W']['image_source_ImageID'] in (None, img):
            problems.append({'img': img, 'problem': 'image_assignment'})
    return problems
