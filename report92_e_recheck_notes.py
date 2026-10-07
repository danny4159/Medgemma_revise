"""E 재점검(고정 24명 + 결정 관련 1명, 98개 판독) 기록 작성. 각 판독의 원문·reference·기존 판정을 모델명 없이 대조한 결과다.
재점검에서 수정한 판정만 amend로 기록하고 나머지는 retain으로 기록한다. 임상 정답 검증이 아니다."""
import copy
import glob
import json
from report86_common import save,sha
from report90_numeric import OUT as ORIGINAL
OUT=ORIGINAL/'recovery'

AMEND={'060bce':dict(note='Normal chest X-ray 계열 문장에서 "The lungs are clear"를 reference의 음성 consolidation atom으로 supported 처리했으나, reference는 우측 기저부 nodule을 확정 양성으로 기술한다. clear lungs 전체를 지지하는 근거가 아니므로 pulmonary opacity claim을 unknown으로 수정한다(consolidation 음성만 별도 지지).',
                     finding='pulmonary opacity')}

def main():
    stage=OUT/'semantic/E';review=OUT/'semantic/E_recheck';sel=json.loads((review/'selection.json').read_text())
    judg={}
    for f in sorted(glob.glob(str(stage/'judgments/part_*.json'))):
        for j in json.loads(open(f).read())['judgments']:judg[j['blind_id']]=j
    rows=[]
    for b in sel['expected_blind_ids']:
        key=next((k for k in AMEND if b.startswith(k)),None)
        if key:
            new=copy.deepcopy(judg[b]);hit=[c for c in new['claims'] if c['finding']==AMEND[key]['finding'] and c['status']=='supported']
            assert hit,b
            for c in hit:c.update(status='unknown',refs=[],note='재점검: clear lungs는 reference의 우측 기저부 nodule 양성과 함께 지지되지 않음')
            rows.append(dict(blind_id=b,reviewed=True,decision='amend',evidence_note=AMEND[key]['note'],replacement=new))
        else:
            rows.append(dict(blind_id=b,reviewed=True,decision='retain',evidence_note='원문·reference atom·기존 match/claim을 재대조했고 위치·속성 일치 여부, 반박 방향, 반복 주장 통합에 오류가 없어 유지'))
    save(review/'notes.json',dict(selection_sha=sha(review/'selection.json'),reviews=rows,source_sha=sha(__file__),
        scope='assistant 재점검(출력 문체로 조건이 일부 드러날 수 있음). 전문의 또는 독립 평가자 합의가 아님.'))
    print('recheck notes',len(rows),'amend',sum(r['decision']=='amend' for r in rows))

if __name__=='__main__':main()
