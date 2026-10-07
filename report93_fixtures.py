"""iter_093 의미 민감도 규칙의 사전 고정 fixture (구현 전에 정답·근거를 고정한다).
각 항목은 출력 문장 하나와 reference atom 일부로 expected(supported/contradicted/undecidable)와 이유를 갖는다.
다섯 규칙군: generic_normal / other_scope / acute_negation / specific_negation / location_attribute."""

def atom(finding, polarity='positive', certainty='definite', location='', attributes=''):
    return dict(finding=finding, polarity=polarity, certainty=certainty, location=location, attributes=attributes)

FIXTURES = [
    # 1 일반 정상문: reference의 명시적 무소견 atom만 지지; 중요 소견은 반박; 만성/부수 소견은 중요도 범위 모호
    dict(id='G1_support', group='generic_normal', quote='No significant findings.', finding='significant abnormality',
         refs=[atom('no significant finding', 'negative')], expected='supported',
         why='reference가 무소견을 명시'),
    dict(id='G1_contra', group='generic_normal', quote='Normal chest X-ray.', finding='chest abnormality',
         refs=[atom('pleural effusion', location='left posterior costophrenic angle', attributes='small')], expected='contradicted',
         why='확정 흉막삼출은 중요 소견이며 전체 정상 주장과 양립 불가'),
    dict(id='G1_undec', group='generic_normal', quote='Normal chest X-ray.', finding='chest abnormality',
         refs=[atom('scoliosis', location='dorsolumbar', attributes='right convexity'), atom('no significant finding', 'negative')],
         expected='undecidable', why='구조적 척추 변형만 있고 reference도 other 무소견이므로 중요도 범위가 모호'),
    # 2 other 범위: other는 이미 기술된 소견을 제외한 나머지만 주장
    dict(id='G2_support', group='other_scope', quote='No other significant findings.', finding='significant abnormality', stated_findings=['hilar prominence'],
         refs=[atom('hilar prominence', location='left'), atom('other relevant finding', 'negative', location='outside described findings')],
         expected='supported', why='reference도 기술 소견 밖 other relevant finding을 음성으로 명시'),
    dict(id='G2_contra', group='other_scope', quote='No other findings.', finding='significant abnormality', stated_findings=['cardiomegaly'],
         refs=[atom('cardiomegaly'), atom('pulmonary nodule', location='right lower lobe')], expected='contradicted',
         why='출력이 기술한 소견 밖에 확정 결절이 있다'),
    dict(id='G2_undec', group='other_scope', quote='No other significant findings.', finding='significant abnormality', stated_findings=['cardiomegaly'],
         refs=[atom('cardiomegaly')], expected='undecidable', why='reference에 other 음성도 추가 양성도 없다'),
    # 3 급성 부정: 급성 가능 소견만 반박, 만성 소견은 반박 불가
    dict(id='G3_support', group='acute_negation', quote='No acute cardiopulmonary process.', finding='acute cardiopulmonary process',
         refs=[atom('chronic pulmonary change', location='lung parenchyma', attributes='chronic'), atom('no significant finding', 'negative')],
         expected='supported', why='만성 변화만 있으며 급성 소견이 reference에 없고 무소견 문장이 있다'),
    dict(id='G3_contra', group='acute_negation', quote='No acute cardiopulmonary process.', finding='acute cardiopulmonary process',
         refs=[atom('alveolar infiltrate', location='perihilar')], expected='contradicted', why='확정 폐포 침윤은 급성 가능 소견'),
    dict(id='G3_undec', group='acute_negation', quote='No acute cardiopulmonary process.', finding='acute cardiopulmonary process',
         refs=[atom('interstitial infiltrate', certainty='possible', location='right lung base')], expected='undecidable',
         why='가능 소견만 있고 급성 여부 근거 없음'),
    # 4 구체적 부정: 같은 소견의 확정 양성만 반박, 같은 소견 음성은 지지, 미언급은 판단불가
    dict(id='G4_support', group='specific_negation', quote='There is no pleural effusion.', finding='pleural effusion',
         refs=[atom('pleural effusion', 'negative', location='costophrenic sinuses')], expected='supported', why='같은 소견의 명시 음성'),
    dict(id='G4_contra', group='specific_negation', quote='No definitive images of pulmonary nodules or masses are observed.', finding='pulmonary nodule/mass',
         refs=[atom('pulmonary nodule', location='right lower lobe', attributes='2cm')], expected='contradicted', why='같은 소견의 확정 양성'),
    dict(id='G4_undec', group='specific_negation', quote='There is no pneumothorax.', finding='pneumothorax',
         refs=[atom('pleural effusion', location='left')], expected='undecidable', why='reference가 기흉을 언급하지 않는다(미표기는 음성이 아님)'),
    # 5 위치·속성: 명시 laterality/site/type이 충돌하면 반박, 같으면 지지, reference에 값이 없으면 판단불가; substring 일치 금지
    dict(id='G5_support', group='location_attribute', quote='Right humeral prosthesis.', finding='humeral prosthesis',
         refs=[atom('metallic prosthesis', location='right humerus')], expected='supported', why='laterality와 부위 일치'),
    dict(id='G5_contra', group='location_attribute', quote='Left humeral head prosthesis.', finding='humeral prosthesis',
         refs=[atom('metallic prosthesis', location='right humerus')], expected='contradicted', why='명시 laterality 충돌'),
    dict(id='G5_undec', group='location_attribute', quote='Left pleural effusion.', finding='pleural effusion',
         refs=[atom('pleural effusion')], expected='undecidable', why='reference에 laterality 정보 없음'),
    dict(id='G5_contra_site', group='location_attribute', quote='Central route through the right jugular.', finding='central venous catheter',
         refs=[atom('central venous catheter', location='subclavian vein')], expected='contradicted', why='명시 삽입 경로 충돌'),
    dict(id='G5_contra_type', group='location_attribute', quote='Biventricular pacemaker.', finding='pacemaker',
         refs=[atom('pacemaker', attributes='dual chamber')], expected='contradicted', why='명시 유형 충돌(biventricular≠dual chamber)'),
    dict(id='G5_trap_substring', group='location_attribute', quote='Pleural effusion in the left lower lobe.', finding='pleural effusion',
         refs=[atom('pleural effusion', location='right lower lobe')], expected='contradicted',
         why='left/right 단어 일부 겹침이 있어도 laterality는 충돌(공통 token lower lobe로 승인하면 오류)'),
]
