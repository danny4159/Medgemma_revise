"""iter_087 reference 보완(모델 출력·원 지표를 보지 않고 reference 문장만 읽어 작성, 사후 보완임을 명시).
python report87_refamend.py   -> results/iter_087/reference_amend_E96.json (새 파일만)

원 reference ID·원 class(v1)를 보존하고 다음만 추가한다:
  loc_req   문장이 명시한 위치(없으면 None). 문장에 없는 annotation 위치는 쓰지 않는다.
  attr_req  문장이 명시한 속성 목록. '?' 접두는 reference 자체가 불확실하게 쓴 속성(생략해도 strict 실패 아님, 충돌은 충돌).
  targets   neg_specific / normal_scoped의 부정 대상 개념.
  v2_class  v1과 같되 (a) 대상·속성이 명시된 정상 사실은 normal_scoped, (b) P041 F2 한 건을 정정(pos_temporal -> pos_def).
  weak      범위가 약한 normal_scoped(민감도에서 제외 가능).
포괄 문구(generic_normal: 'no relevant findings', 'within normal limits' 단독 등)와 rest-of 범위 문구는 평가에 쓰지 않는다.
"""
from report86_common import R86, ROOT, save, sha

R87 = ROOT / 'results/iter_087'
LUNG = 'lung_parenchyma'

# 양성 사실의 위치·속성 요구: {환자 index: {fact: (loc_req, [attr...])}}
POS = {
    0: {'F2': ('nipple', ['nodular']), 'F3': ('right lower third of hemithorax', ['nodular'])},
    2: {'F1': ('region of left atrium', ['punctiform', 'metallic']), 'F3': (None, ['chronic', 'COPD etiology'])},
    3: {'F1': (None, ['left cavities'])},
    5: {'F1': ('lingula and middle lobe', ['laminar'])},
    8: {'F1': ('left', [])},
    12: {'F1': (None, ['chronic']), 'F2': (None, ['calcified']),
         'F3': ('both acromioclavicular joints', ['hypertrophic/mechanical'])},
    15: {'F1': (None, ['dorsal', 'left concavity'])},
    21: {'F1': ('bilateral', ['interstitial'])},
    23: {'F1': (None, ['chronic'])},
    24: {'F1': ('left first costochondral junction', ['pseudonodular'])},
    25: {'F1': (None, ['dorsolumbar'])},
    30: {'F1': (None, ['vascular origin'])},
    31: {'F1': ('bilateral hila', ['?vascular origin'])},
    32: {'F1': ('bilateral apical', ['pleuroparenchymal']), 'F2': (None, ['?vascular etiology'])},
    33: {'F1': (None, ['marked'])},
    36: {'F5': (None, ['slight', 'dorsal'])},
    38: {'F1': (None, ['chronic'])},
    40: {'F1': (None, ['chronic']), 'F2': (None, ['calcified'])},
    41: {'F1': (None, ['dorsal']), 'F3': ('bilateral ribs', ['callus'])},
    42: {'F1': ('left cardiac border', ['small', 'poorly defined'])},
    45: {'F1': (None, ['chronic']), 'F2': ('left humeral head', ['degenerative'])},
    47: {'F1': (None, ['chronic', 'pleuroparenchymal'])},
    48: {'F1': ('retrocardiac', ['slight'])},
    49: {'F2': ('descending thoracic aorta', [])},
    50: {'F2': ('right hypochondrium', ['metal sutures'])},
    52: {'F1': (None, ['marked', 'dorsolumbar'])},
    53: {'F3': (None, ['small', 'parapneumonic'])},
    56: {'F2': ('right humeral head', ['metallic'])},
    58: {'F1': (None, ['chronic'])},
    59: {'F1': (None, ['calcified']), 'F2': ('left mid lung field', ['well-defined', 'soft tissue density', '1.5 cm'])},
    62: {'F5': (None, ['intense']), 'F6': ('right axilla', ['increased density'])},
    65: {'F1': (None, ['chronic']), 'F2': ('right upper lobe', ['calcified'])},
    66: {'F1': ('right base', ['chronic', 'inflammatory'])},
    67: {'F1': ('right hemidiaphragm', ['anterior', 'lobulation'])},
    69: {'F1': ('bilateral', [])},
    70: {'F1': ('right humerus', ['?old', 'subcapital'])},
    76: {'F1': ('right lung base', ['increased']), 'F2': ('right costophrenic angle', [])},
    78: {'F2': (None, ['dorsal']), 'F3': (None, ['dorsal'])},
    80: {'F1': ('left hilum', ['?vascular origin']), 'F3': ('dorsal spine', ['mechanical/degenerative'])},
    82: {'F1': (None, ['chronic', 'pleuroparenchymal'])},
    84: {'F1': ('left humerus', [])},
    85: {'F1': ('right basal', ['?infectious-inflammatory'])},
    86: {'F2': (None, ['chronic', 'pleuroparenchymal']), 'F3': (None, ['calcified']), 'F5': (None, ['degenerative'])},
    90: {'F2': ('dorsal spine', ['mechanical/degenerative']), 'F3': ('right hemidiaphragm', [])},
    93: {'F2': (None, ['dorsal'])},
}
# 명시적 특정 소견 부정(v1 neg_specific 유지) 대상 개념
NEG = {
    4: {'F2': ['consolidation', 'nodule', 'mass'], 'F3': ['effusion']},
    26: {'F2': ['infiltrate', 'consolidation']},
    33: {'F3': ['effusion']},
    36: {'F4': ['costophrenic sinus blunting/effusion']},
    37: {'F4': ['effusion']},
    51: {'F2': ['costophrenic sinus blunting/effusion']},
    52: {'F3': ['pulmonary tuberculosis']},
    56: {'F1': ['consolidation']},
    62: {'F4': ['effusion']},
    63: {'F1': ['infiltrate', 'consolidation']},
    72: {'F1': ['infiltrate', 'consolidation']},
    73: {'F2': ['nodule', 'consolidation'], 'F3': ['costophrenic angle blunting/effusion']},
    90: {'F1': ['consolidation', 'significant opacity']},
}
# 대상·속성이 명시된 정상 사실(v1 generic_normal -> v2 normal_scoped): (대상, weak)
NORM = {
    4: {'F1': (['cardiac_silhouette'], True)},
    10: {'F2': ([LUNG, 'cardiomediastinal_silhouette'], False)},
    14: {'F1': ([LUNG], False), 'F2': (['cardiomediastinal_silhouette'], False)},
    15: {'F2': ([LUNG], False), 'F3': (['cardiothoracic_index'], False)},
    16: {'F3': ([LUNG], False)},
    26: {'F1': ([LUNG], False)},
    36: {'F3': (['cardiomediastinal_silhouette'], False)},
    37: {'F1': (['cardiothoracic_index'], False), 'F2': (['mediastinal_contour'], False), 'F3': ([LUNG], False), 'F5': (['bones'], False)},
    49: {'F1': (['cardiothoracic_index'], False), 'F3': ([LUNG], False)},
    51: {'F1': (['cardiomediastinal_silhouette'], False)},
    53: {'F1': (['cardiothoracic_index'], False), 'F2': (['mediastinal_contour'], False)},
    62: {'F1': (['cardiothoracic_index'], False), 'F2': (['mediastinal_contour'], False), 'F3': ([LUNG], False)},
    67: {'F2': ([LUNG], False)},
    73: {'F1': (['mediastinum', 'cardiac_silhouette'], False)},
}
# 원 분모 정정: (환자 index, fact) -> (new_class, 이유)
CORRECT = {(41, 'F2'): ('pos_def', "'decreased height of vertebral bodies'는 설명적 기술이며 시간 비교가 아니다(v1 TEMPORAL 정규식의 decreas* 일치 오분류)")}
# 중복 가능성(자동 병합하지 않음): 환자 index -> [[facts]]
DUP_UNCERTAIN = {0: [['F2', 'F3']]}
# 정정 분모 민감도에서 병합해 보는 해석
KEPT = ('pos_def', 'pos_hedged', 'pos_temporal', 'pos_ambiguous')


def build():
    import json
    rows = json.loads((R86 / 'E/inputs_E96.json').read_text())
    refs = json.loads((R86 / 'E/reference_facts_E_private.json').read_text())
    out, changes = {}, []
    for i, r in enumerate(rows):
        img = r['ImageID']
        facts = []
        for x in refs[img]['facts']:
            fid, c1 = x['fact_id'], x['fact_class']
            c2, targets, weak, note = c1, [], False, ''
            loc, attr = None, []
            if fid in POS.get(i, {}):
                assert c1 in KEPT, (i, fid, c1)
                loc, attr = POS[i][fid]
            if fid in NEG.get(i, {}):
                assert c1 == 'neg_specific', (i, fid, c1)
                targets = NEG[i][fid]
            if fid in NORM.get(i, {}):
                assert c1 == 'generic_normal', (i, fid, c1)
                targets, weak = NORM[i][fid]
                c2 = 'normal_scoped'
            if (i, fid) in CORRECT:
                assert c1 == 'pos_temporal'
                c2, note = CORRECT[(i, fid)]
                changes.append({'patient_index': i, 'ImageID': img, 'fact_id': fid, 'v1_class': c1, 'v2_class': c2, 'reason': note})
            facts.append({'fact_id': fid, 'sentence_en': x['sentence_en'], 'v1_class': c1, 'v2_class': c2, 'loc_req': loc, 'attr_req': attr,
                          'targets': targets, 'weak': weak, 'note': note})
        # 모든 NEG/NORM/POS 키가 실제 사실과 연결됐는지(오타 방지)
        ids = {f['fact_id'] for f in facts}
        for tbl in (POS, NEG, NORM):
            assert set(tbl.get(i, {})) <= ids, (i, tbl.get(i))
        out[img] = {'patient_index': i, 'stratum': r['stratum'], 'facts': facts,
                    'dup_uncertain': DUP_UNCERTAIN.get(i, [])}
    n_pos = sum(f['v1_class'] == 'pos_def' for v in out.values() for f in v['facts'])
    n_pos2 = sum(f['v2_class'] == 'pos_def' for v in out.values() for f in v['facts'])
    summ = {'n_patients': len(out), 'n_pos_def_v1': n_pos, 'n_pos_def_v2': n_pos2, 'denominator_changes': changes,
            'n_normal_scoped': sum(f['v2_class'] == 'normal_scoped' for v in out.values() for f in v['facts']),
            'n_normal_scoped_weak': sum(f['weak'] for v in out.values() for f in v['facts']),
            'n_neg_specific': sum(f['v2_class'] == 'neg_specific' for v in out.values() for f in v['facts']),
            'patients_with_normal_scoped': sum(any(f['v2_class'] == 'normal_scoped' for f in v['facts']) for v in out.values()),
            'dup_uncertain': {str(k): v for k, v in DUP_UNCERTAIN.items()},
            'blind_note': '작성 전에 형식 확인을 위해 P000·P002·P062 출력 일부를 보았다(계획이 이미 지목한 사례). 나머지 환자는 출력·원 지표를 보기 전에 reference 문장만으로 작성했다. 어떤 규칙도 모델 조건별로 다르지 않다.',
            'note': '이미 본 E96의 오류에 대한 사후 보완이다. 모델·조건별로 다른 규칙을 쓰지 않는다.'}
    save(R87 / 'reference_amend_E96.json', {'summary': summ, 'patients': out, 'code_sha256': sha(__file__)})
    print(json.dumps(summ, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    build()
