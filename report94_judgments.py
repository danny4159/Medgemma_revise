"""iter_094: 신규 epoch1 64건에 대한 사례별 의미 판정 기록(assistant 검토, 모델·epoch 가림 상태에서 작성).
판정은 report94_show.py 출력의 reference atom과 실제 문장을 읽고 정했으며, 규약은 저장된 epoch2/6 판정과 같은 문장(Pacemaker, Tracheostomy tube,
Aortic elongation, Chronic changes)에서 일치하는지 report94_precedent.py로 대조했다. 전문의 판독이 아니다."""
import json
from pathlib import Path
from report86_common import sha,save

ROOT=Path(__file__).resolve().parent
D=ROOT/'results/iter_094/semantic/epoch1'
refs=json.loads((ROOT/'results/iter_090/semantic/V32_reference_v3.json').read_text())['rows']
blinded=json.loads((D/'blinded.json').read_text())

# 일반 정상문: reference에 해당 환자의 명시적 'no significant finding' atom이 있으면 supported, 없으면 unknown(저장 규약과 동일).
GENERIC_SUPPORT={2:'V02A00',3:'V03A00',4:'V04A00',5:'V05A01',6:'V06A00',7:'V07A00',8:'V08A00',10:'V10A00',11:'V11A00',12:'V12A00',14:'V14A02',26:'V26A01'}

# 비일반 문장: (환자 index, 문장) -> 판정
SPECIFIC={
 (13,'Central line through the right internal jugular vein.'):dict(
    matches=[dict(ref='V13A02',status='strict',location='match',attributes='na',ambiguous=True)],
    claims=[dict(finding='central venous catheter',polarity='positive',certainty='definite',status='supported',refs=['V13A02'],
                 note='우측 내경정맥 경로는 reference와 일치. reference의 tip 위치(right atrium 시작부)는 문장에 없어 위치 일치를 모호로 표시')]),
 (16,'Pulmonary infiltrates.'):dict(
    matches=[dict(ref='V16A00',status='type_only',location='missing',attributes='missing',ambiguous=True)],
    claims=[dict(finding='alveolar interstitial infiltrate',polarity='positive',certainty='definite',status='supported',refs=['V16A00'],note='종류만 일치, 위치·속성 없음')]),
 (21,'Pacemaker.'):dict(
    matches=[dict(ref='V21A00',status='type_only',location='na',attributes='missing',ambiguous=False)],
    claims=[dict(finding='pacemaker',polarity='positive',certainty='definite',status='supported',refs=['V21A00'],note='reference의 dual chamber 속성 없음')]),
 (22,'Aortic elongation.'):dict(
    matches=[],claims=[dict(finding='aortic elongation',polarity='positive',certainty='definite',status='unknown',refs=[],note='reference에 없음(hiatal hernia만). 미표기를 오류로 단정하지 않음')]),
 (23,'Pacemaker.'):dict(
    matches=[dict(ref='V23A00',status='strict',location='na',attributes='na',ambiguous=False)],
    claims=[dict(finding='pacemaker',polarity='positive',certainty='definite',status='supported',refs=['V23A00'],note='')]),
 (25,'Chronic changes in lung parenchyma.'):dict(
    matches=[],claims=[dict(finding='chronic pulmonary change',polarity='positive',certainty='definite',status='unknown',refs=[],note='reference의 left lower lobe atelectasis와 별개 문장, 대응 불인정')]),
 (30,'Tracheostomy tube.'):dict(
    matches=[dict(ref='V30A00',status='strict',location='na',attributes='na',ambiguous=False)],
    claims=[dict(finding='tracheostomy tube',polarity='positive',certainty='definite',status='supported',refs=['V30A00'],note='NG tube는 미언급')]),
}

def judge(rec,idx):
    text=rec['text']
    if text.startswith('No significant'):
        ref=GENERIC_SUPPORT.get(idx)
        return dict(matches=[],claims=[dict(finding='significant abnormality',polarity='negative',certainty='definite',status='supported' if ref else 'unknown',
            refs=[ref] if ref else [],quote=text,note='명시적 일반 정상 reference 있음' if ref else 'reference에 명시적 일반 정상 근거 없음 → unknown(오류·정확으로 계산하지 않음)')],
            internal_conflicts=[],format_failure=False)
    s=SPECIFIC[(idx,text)]
    claims=[dict(c,quote=text) for c in s['claims']];matches=[dict(m,quote=text) for m in s['matches']]
    return dict(matches=matches,claims=claims,internal_conflicts=[],format_failure=False)

def main():
    byimg={r['id']:i for i,r in enumerate(refs)};bsha=sha(D/'blinded.json')
    out=[]
    for rec in blinded['records']:
        j=judge(rec,byimg[rec['image_id']]);j['blind_id']=rec['blind_id'];out.append(j)
    assert len(out)==64
    for k in range(0,32,4):
        ids={r['id'] for r in refs[k:k+4]}
        part=[j for j,rec in zip(out,blinded['records']) if rec['image_id'] in ids]
        save(D/f'judgments/part_{k//4:02}.json',dict(blinded_sha=bsha,judgments=part))

if __name__=='__main__':
    main()
