"""iter_097 epoch2 (R LR2e-5) V32 출력의 assistant 판정. 조건명을 가린 blinded.json의 원문 span에 연결한다.
일반 정상문은 iter_090 관례(reference에 'no significant finding' 원자가 있으면 supported, 아니면 unknown; 자동 모순 처리 안 함)를 그대로 따른다.
비정상(비일반) 출력은 아래에 출력별 사유를 직접 적었다. 전문의 검토가 아니다."""
import json
from pathlib import Path
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

GENERIC=('No significant findings.','Within normal limits.')

def generic(ref,text):
    atoms=[a['id'] for a in ref['atoms'] if a['finding']=='no significant finding' and a['polarity']=='negative']
    return dict(matches=[],claims=[dict(finding='significant abnormality',polarity='negative',certainty='definite',
        status='supported' if atoms else 'unknown',quote=text,refs=atoms[:1],
        note='일반 정상문; reference에 같은 전반 정상 원자 있음' if atoms else '일반 정상문; 자동 모순·자동 승인 안 함')],internal_conflicts=[],format_failure=False)

def M(ref,quote,status,loc,att,amb=False):return dict(ref=ref,quote=quote,status=status,location=loc,attributes=att,ambiguous=amb)
def C(finding,quote,status,refs,pol='positive',cert='definite',note=''):return dict(finding=finding,polarity=pol,certainty=cert,status=status,quote=quote,refs=refs,note=note)

# image index -> 판정 (비일반 출력)
SPECIAL={
 13:dict(matches=[M('V13A02','Central venous catheter.','type_only','missing','na')],
   claims=[C('central venous catheter','Central venous catheter.','supported',['V13A02'])],note='위치(right jugular, tip) 누락 -> type_only'),
 16:dict(matches=[M('V16A00','Pulmonary infiltrates.','type_only','missing','missing',True)],
   claims=[C('pulmonary infiltrate','Pulmonary infiltrates.','supported',['V16A00'])],note='perihilar/right 위치·alveolar 속성 누락; reference 자체 ambiguous'),
 20:dict(matches=[M('V20A01','Central venous catheter.','type_only','missing','na')],
   claims=[C('central venous catheter','Central venous catheter.','supported',['V20A01']),
           C('nasogastric tube','Nasogastric tube.','unknown',[],note='reference에 언급 없음; 미지원/판단 불가')],note='subclavian 경로 누락'),
 21:dict(matches=[M('V21A00','Pacemaker in situ.','type_only','na','missing')],
   claims=[C('pacemaker','Pacemaker in situ.','supported',['V21A00'])],note='dual chamber 속성 누락 -> type_only'),
 22:dict(matches=[],claims=[C('aortic elongation','Aortic elongation.','unknown',[],note='reference는 hiatal hernia만; 미지원')],note='정답 소견 hiatal hernia 미대응'),
 23:dict(matches=[M('V23A00','Pacemaker with leads in the right atrium and right ventricle.','strict','na','na')],
   claims=[C('pacemaker','Pacemaker with leads in the right atrium and right ventricle.','supported',['V23A00']),
           C('pacemaker lead position','Pacemaker with leads in the right atrium and right ventricle.','unknown',[],note='lead 위치 reference 없음'),
           C('cardiomegaly','Cardiomegaly.','unknown',[],note='reference에 없음')],note='V23A00 pacemaker에는 위치·속성이 없어 strict'),
 25:dict(matches=[],claims=[C('chronic pulmonary change','Chronic changes in lung parenchyma.','unknown',[],note='reference는 left lower lobe segmental atelectasis만')],note='정답 소견 미대응'),
 30:dict(matches=[M('V30A00','Tracheostomy tube.','strict','na','na')],
   claims=[C('tracheostomy tube','Tracheostomy tube.','supported',['V30A00'])],note='nasogastric tube는 누락(V30A01 미대응)'),
 31:dict(matches=[],claims=[C('chronic pulmonary change','Chronic changes in lung parenchyma.','unknown',[],note='reference는 bilateral apical pleural thickening')],note='정답 소견 미대응; 유사 표현이나 같은 소견 아님'),
}

def main(name='epoch2'):
    root=OUT/f'semantic/{name}';blinded=json.loads((root/'blinded.json').read_text())
    refs=json.loads((ORIGINAL/'semantic/V32_reference_v3.json').read_text())['rows'];ix={r['id']:i for i,r in enumerate(refs)}
    judgments=[];used=set()
    for rec in blinded['records']:
        i=ix[rec['image_id']];ref=refs[i]
        if rec['text'] in GENERIC:j=generic(ref,rec['text'])
        else:
            assert i in SPECIAL,(i,rec['text']);s=SPECIAL[i];used.add(i)
            j=dict(matches=s['matches'],claims=s['claims'],internal_conflicts=[],format_failure=False,note=s['note'])
        judgments.append(dict(blind_id=rec['blind_id'],**j))
    assert used==set(SPECIAL)
    for k in range(0,32,4):
        ids={refs[x]['id'] for x in range(k,k+4)};blind={r['blind_id'] for r in blinded['records'] if r['image_id'] in ids}
        save(root/f'judgments/part_{k//4:02}.json',dict(blinded_sha=sha(root/'blinded.json'),judgments=[j for j in judgments if j['blind_id'] in blind],
            helper_sha=sha(__file__),scope='assistant 판정; 일반 정상문은 관례 자동 처리, 비일반 출력은 출력별 수작업 사유'))
    print(len(judgments))

if __name__=='__main__':main()
