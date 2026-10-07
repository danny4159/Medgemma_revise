"""직접 읽고 판정한 문구를 저장하는 보조 함수. 임상/자동 의미 평가기가 아니다."""
import json
from pathlib import Path
from report86_common import save,sha

def claim(f,q,status='unknown',refs=(),polarity='positive',certainty='definite',note=''):
    return dict(finding=f,quote=q,status=status,refs=list(refs),polarity=polarity,certainty=certainty,note=note)

def match(ref,q,status='strict',location='na',attributes='na',ambiguous=False):
    return dict(ref=ref,quote=q,status=status,location=location,attributes=attributes,ambiguous=ambiguous)

PHRASES={
 'significant abnormality':['No significant findings.','No other significant findings.','No other relevant findings.','No relevant findings.'],
 'cardiomegaly':['The heart size is normal.'],
 'mediastinal abnormality':['The mediastinal contours are unremarkable.','The mediastinal contours are normal.','The mediastinal and hilar contours are normal.','The mediastinal and hilar contours are unremarkable.'],
 'hilar abnormality':['The mediastinal and hilar contours are normal.','The mediastinal and hilar contours are unremarkable.'],
 'pulmonary opacity':['The lungs are clear.'],
 'consolidation':['The lungs are clear without focal consolidation, pleural effusion, or pneumothorax.','The lungs are clear with no focal consolidation, pleural effusion, or pneumothorax.'],
 'pleural effusion':['There is no pleural effusion or pneumothorax.','The lungs are clear without focal consolidation, pleural effusion, or pneumothorax.','The lungs are clear with no focal consolidation, pleural effusion, or pneumothorax.'],
 'pneumothorax':['There is no pleural effusion or pneumothorax.','The lungs are clear without focal consolidation, pleural effusion, or pneumothorax.','The lungs are clear with no focal consolidation, pleural effusion, or pneumothorax.'],
 'osseous abnormality':['The visualized osseous structures are unremarkable.'],
 'osseous disruption':['The visualized osseous structures are intact.'],
 'pulmonary edema':['There is no evidence of pulmonary edema.'],
 'acute cardiopulmonary abnormality':['No acute cardiopulmonary process.'],
 'chest abnormality':['Normal chest X-ray.']}

def normal_claims(text,status='unknown',refs=(),overrides=None):
    output=[];overrides=overrides or {}
    for finding,phrases in PHRASES.items():
        for quote in phrases:
            if quote in text:
                st,rs=overrides.get(finding,(status,refs))
                output.append(claim(finding,quote,st,rs,polarity='negative'))
    return output

def judgment(bid,claims,matches=(),conflicts=(),format_failure=False,note=''):
    return dict(blind_id=bid,claims=claims,matches=list(matches),internal_conflicts=list(conflicts),format_failure=format_failure,note=note)

def write_part(stage,part,judgments):
    root=Path(stage);source=root/f'part_{part:02}.json';items=json.loads(source.read_text())['outputs'];by={o['blind_id']:o for o in items}
    assert len(judgments)==len(by) and {j['blind_id'] for j in judgments}==set(by)
    for j in judgments:
        assert j['claims'] or j['format_failure'] or not by[j['blind_id']]['text'].strip()
        for item in j['claims']+j['matches']:assert item['quote'] and item['quote'] in by[j['blind_id']]['text']
    save(root/f'judgments/part_{part:02}.json',dict(blinded_sha=sha(root/'blinded.json'),judgments=judgments,
        reviewed_part_sha=sha(source),helper_sha=sha(__file__),scope='이 고정 원문을 읽은 assistant 판정. 전문의 평가 또는 범용 자동 평가 아님.'))
