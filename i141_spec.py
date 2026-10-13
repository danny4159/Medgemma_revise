"""출력 전 고정할 DWI 질문·통합·내용 대응 규약. presence parser를 재사용하지 않는다."""
import re

BASE_CONFIG = dict(model_id='google/medgemma-1.5-4b-it', revision='91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b',
                   dtype='bfloat16', attention='sdpa', do_sample=False, seed=141, batch=1, image_labels=False)
TOKENS = dict(technical=1024, technical2048=2048)
STAGES = ['technical', 'technical2048', 'main']
START_TOKEN, END_TOKEN = '<unused94>', '<unused95>'
QUESTION = ('Describe the visible findings in the provided axial DWI MRI image(s) of one brain in at most three short sentences. '
            'Mention the location and signal appearance of visible abnormalities. '
            'The slices are ordered from inferior to superior and displayed in radiological convention: '
            'image left is patient right, image top is anterior. '
            'Use only the provided images. Do not infer unprovided sequences, disease cause, or timing. '
            'If a finding cannot be determined, state that uncertainty.')
FORBIDDEN_IN_PROMPT = ['RadGenome', 'ISLES', 'sub-stroke', 'stroke', 'infarct', 'ADC', 'mask', 'annotation']
RENDER = dict(orientation='closest_canonical_RAS_no_resampling', convention='radiological_axial',
              normalization='volume_minmax', side=256, interpolation='bilinear',
              selection='all axial slices; trim only exact-zero exterior padding',
              grouping='nonoverlapping consecutive at most five')
SEMANTIC_CONTRACT = {
    'primary': '환자별 명시 양성 atom의 명확한 일치 수 / 양성 atom 수; 환자 평균',
    'matching': '같은 소견·위치·속성을 명시한 원문만 matched. 위치는 명시 좌우를 요구하며 임상 추론·애매한 동의어는 unresolved.',
    'states': ['matched', 'contradicted', 'unmentioned', 'unresolved'],
    'contradiction': '같은 관측 범위의 명시적 반대 주장만 reference contradiction. 다른 slice에 부재라는 설명은 volume 전체 부재로 일반화하지 않음.',
    'internal_contradiction': '동일 slice/중첩 scope 안의 명확한 양립 불가 주장 또는 volume 전체 주장이 국소 주장과 충돌할 때만 확정.',
    'extra': 'reference 미언급 추가 소견은 report_unverified, 임상 허위가 아님.',
    'incomplete': 'invalid boundary는 내용 미판정. 비EOS 출력은 미완결로 분리하고 관측 텍스트 및 unresolved 범위를 보존.',
    'ranges': '환자별 unresolved atom을 모두 실패/성공으로 두어 recall 범위; 모순 불확실성도 최선/최악 환자율로 유지.',
    'positive': 'A-S 최소 recall 차이 >=0.05이고 최대 명시 모순 환자율 증가 <=0.05.',
    'inconclusive': '미판정·절단·환자 변동에 따라 다음 판단이 달라지면 inconclusive. 원문 한정 보완 후 종료.',
    'negative': '유효 비교에서 사전 양성 기준 미달. frozen 인접 우위 미확보에만 한정.',
    'clinical_scope': '공식 공개 텍스트와 출력의 근거 정리. 새로운 임상 정답을 생성하지 않음.',
    'supervision': 'global/sequence 전체 범위만 검증되면 전체 sequence target. 각 slice에 전체 report 복제 금지.',
}


def split_final(tokens, start_id, end_id):
    # i136_spec.py와 같은 tokenizer 표식 경계; 평가 내용 규약은 새로 고정한다.
    ns, ne = tokens.count(start_id), tokens.count(end_id)
    if ns == 0 and ne == 0:
        return 'no_marker', list(tokens)
    if ns == 1 and ne == 1 and tokens[0] == start_id and tokens.index(end_id) > 0:
        return 'thought_final', list(tokens[tokens.index(end_id) + 1:])
    return 'invalid_boundary', []


def sentences(text):
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+|\n+', text) if x.strip()]


def integrate(records):
    ordered = sorted(records, key=lambda r: r['slice_indices'][0])
    full = '\n'.join(r['final_text'] for r in ordered)
    seen, unique = set(), []
    for r in ordered:
        for sent in sentences(r['final_text']):
            if sent not in seen:
                unique.append({'text': sent, 'request_id': r['id'], 'slice_indices': r['slice_indices']})
                seen.add(sent)
    return {'raw_concatenation': full, 'exact_sentence_deduplication': '\n'.join(x['text'] for x in unique),
            'sentences': unique, 'deduplication': 'exact string only; no contradiction deletion'}
