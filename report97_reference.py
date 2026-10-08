"""iter_097: V32 reference 사례표 고정(새 출력 생성 전)과 대조 사례 fixture.
reference는 iter_090 V32_reference_v3(생성 출력 비열람 상태에서 고정)을 원문 인용과 함께 읽기 전용으로 계승한다.
새 평가기는 만들지 않고 report90_semantic_eval.score의 strict/type_only 규칙만 대조 사례로 검사한다."""
import json
import re
from pathlib import Path
from report86_common import save,sha
import report90_semantic_eval as E
from report97_train import OUT,ORIGINAL

REF=ORIGINAL/'semantic/V32_reference_v3.json'

def classify(a,row):
    """사례표 분류. 판정 규칙은 protocol.md(iter_090)와 동일하며 출력 결과를 보지 않고 정한다."""
    if a['polarity']=='positive' and a['certainty']=='definite':klass='recall_target'
    elif a['polarity']=='positive':klass='possible_only_not_in_denominator'
    elif a['finding']=='no significant finding':klass='general_normal'
    else:klass='negative_fact'
    text=(a['source']+' '+(a['attributes'] or '')).lower()
    return dict(id=a['id'],image_id=row['id'],patient=row['patient'],class_=klass,
        quote=a['source'],start=a['start'],end=a['end'],finding=a['finding'],polarity=a['polarity'],certainty=a['certainty'],
        location=a['location'],attributes=a['attributes'],ambiguous=a['ambiguous'],
        lateral_view_dependent=bool(re.search(r'(?<![a-z])lateral (view|projection|radiograph)',text)),
        bilateral_or_multisite=any(w in (a['location'] or '').lower() for w in ['bilateral','right','left'])
            and 'bilateral' in (a['location'] or '').lower(),
        cause_or_hedge_in_text=any(w in text for w in ['secondary','could be','probable','apparent','doubtful','context']),
        strict_requires_location=bool(a['location']),strict_requires_attributes=bool(a['attributes']))

def contrast_fixtures():
    """score()의 strict 판정 규칙을 사전 대조 사례로 검사한다. 합성 판정이며 모델 출력이 아니다."""
    atom=dict(id='X0',finding='atelectasis',polarity='positive',certainty='definite',location='left lower lobe',attributes='segmental',ambiguous=False)
    other=dict(id='X1',finding='pleural effusion',polarity='positive',certainty='definite',location='',attributes='',ambiguous=False)
    ref=dict(id='img',patient='p',abnormal=True,atoms=[atom,other])
    def run(text,matches,claims=(),conflicts=()):
        out=dict(blind_id='b',text=text,non_eos=False)
        if not claims:claims=[dict(finding='fixture',polarity='positive',certainty='definite',status='unknown',quote=text,refs=[],note='')]
        return E.score(ref,out,dict(matches=matches,claims=list(claims),internal_conflicts=list(conflicts)))
    res={}
    m=lambda q,ref_id,status,loc,att:dict(ref=ref_id,status=status,quote=q,location=loc,attributes=att,ambiguous=False)
    # 1) 위치 누락: strict 아님, type-only 로만 인정
    r=run('Atelectasis.',[m('Atelectasis','X0','type_only','missing','missing')],[]);res['location_missing_is_type_only']=r['strict_recall']==0 and r['type_recall']==.5
    # 2) 위치·속성 일치: strict
    r=run('Segmental atelectasis in the left lower lobe.',[m('Segmental atelectasis in the left lower lobe','X0','strict','match','match')],[]);res['full_match_is_strict']=r['strict_recall']==.5
    # 3) 위치가 명시된 reference에 위치 'na' 로 strict 부여 시 거부(평가기 assertion)
    try:run('Atelectasis.',[m('Atelectasis','X0','strict','na','na')],[]);res['strict_without_required_location_rejected']=False
    except AssertionError:res['strict_without_required_location_rejected']=True
    # 4) 한 소견 한쪽만 대응(양측/한쪽): 위치 conflict → strict 아님
    r=run('Atelectasis in the right lower lobe.',[m('Atelectasis in the right lower lobe','X0','type_only','conflict','missing')],[]);res['laterality_conflict_not_strict']=r['strict_recall']==0
    # 5) 일반 정상문은 recall 분모에 영향 없고 자동 모순도 아님(claim unknown)
    c=dict(finding='significant abnormality',polarity='negative',certainty='definite',status='unknown',quote='No significant findings.',refs=[],note='')
    r=run('No significant findings.',[],[c]);res['general_normal_unknown_not_contradiction']=(not r['contradiction']) and r['strict_recall']==0
    # 6) 근거 없는 quote 거부
    try:run('Atelectasis.',[m('Pneumonia','X0','type_only','missing','missing')],[]);res['unlinked_quote_rejected']=False
    except AssertionError:res['unlinked_quote_rejected']=True
    # 7) possible-only 는 strict 에 불포함
    r=run('Possible atelectasis.',[m('Possible atelectasis','X0','possible_only','missing','missing')],[]);res['possible_only_not_strict']=r['strict_recall']==0 and r['possible_only']==.5
    # 8) 환자 내부 모순 span 쌍
    r=run('Atelectasis. No atelectasis.',[],[],[['Atelectasis.','No atelectasis.']]);res['internal_conflict_needs_two_spans']=r['internal_contradiction']
    return res

def main():
    ref=json.loads(REF.read_text());rows=ref['rows']
    table=[classify(a,row) for row in rows for a in row['atoms']]
    positives=[t for t in table if t['class_']=='recall_target']
    patients={t['image_id'] for t in positives}
    fixtures=contrast_fixtures();assert all(fixtures.values()),fixtures
    save(OUT/'reference/case_table_v2.json',dict(
        reference=str(REF),reference_sha=sha(REF),reference_scope=ref['scope'],
        n_images=len(rows),n_atoms=len(table),n_recall_target_atoms=len(positives),n_recall_patients=len(patients),
        n_abnormal_without_definite_positive=len([r for r in rows if r['abnormal'] and r['id'] not in patients]),
        lateral_view_dependent_recall_targets=[t['id'] for t in positives if t['lateral_view_dependent']],
        rules=dict(
            denominator='확정 양성 reference 원자(certainty=definite, polarity=positive)를 가진 환자; 환자별 비율의 macro 평균',
            strict='소견 + reference에 명시된 위치·속성 모두 대응; 위치 누락은 type_only',
            possible_only='possible reference/대응은 strict 분모·분자에서 제외',
            bilateral='양측 reference에 한쪽만 대응하면 위치 불충족(type_only); 한쪽 대응을 양측 회복으로 처리하지 않음',
            general_normal='no significant findings 류는 강한 부정 주장으로 자동 승인·자동 모순 처리하지 않고 unknown',
            hedge='원인 hedge(예 secondary to)와 소견 존재 hedge를 구분: 소견 존재가 확정이면 원인 불확실성만으로 possible 처리하지 않음',
            lateral_view='lateral 근거 의존 원자는 단일 frontal 입력에서 판정불가 사전 표시; 환자 전체를 제거하지 않음',
            contradiction='reference가 명시적으로 반박하는 주장만 contradicted; reference에 없는 주장은 unknown(미지원·판단불가)'),
        contrast_fixtures=fixtures,atoms=table,
        source_sha=sha(__file__),scoring_sha=sha(E.__file__),
        note='assistant 해석; 전문의 gold 아님. 생성 V32 출력 비열람 상태의 reference_v3을 그대로 계승.'))
    print(json.dumps(dict(n_atoms=len(table),recall_atoms=len(positives),recall_patients=len(patients),fixtures=fixtures,
        lateral=[t['id'] for t in positives if t['lateral_view_dependent']]),ensure_ascii=False))

if __name__=='__main__':main()
