"""선택된 T/V의 temporal 규칙 충돌만 한정 확인한다. E reference는 열지 않는다."""
from collections import Counter
import json
import re

import report89_data as B
from report86_common import sha, save


def main():
    reports, _, links=B.D.load_inputs();by={r['ImageID']:r for r in reports}
    selected=B.read(B.OUT/'data/selection.json')
    records=[];summary={}
    for subset in ('T512','V64'):
        stats=Counter()
        for row in selected[subset]:
            r=by[row['ImageID']];keep,excluded=B.current_findings(r)
            stats['patients']+=1
            stats['original_sentences']+=len(r['findings'])
            stats['retained_sentences']+=len(keep)
            stats['original_abnormal_but_no_retained_abnormal']+=int(row['original_abnormal'] and not row['retained_abnormal'])
            for i,reason in excluded:
                f=r['findings'][i]
                matches=[m.group() for m in B.D.TEMPORAL_RE.finditer(f.get('sentence_en',''))]
                rec=dict(subset=subset,ImageID=row['ImageID'],PatientID=row['PatientID'],source_index=i,
                         finding=f,reason=reason,regex_matches=matches,retained_report=[x['sentence_en'] for x in keep])
                records.append(rec)
                stats['excluded_sentences']+=1
                if f.get('progression') is None and any(x.lower().startswith('chang') for x in matches):
                    stats['progression_none_change_regex_sentences']+=1
        summary[subset]=dict(stats)
    # 직접 대조한 현재 상태 문구. 전체 제외 문장을 자동 임상 판정하지 않는다.
    current_examples={
        'Degenerative changes of dorsal spondylosis with prominent osteophyte formations.':
            '퇴행성 척추 상태와 골극을 기술하며 과거 영상 비교 표현이 없다.',
        'Chronic pulmonary changes in the middle lobe and lingula.':
            '중엽·설상엽의 만성 상태를 기술하며 변화량 비교가 아니다.',
        'COPD changes with air trapping.':
            '공기 포획을 동반한 COPD 상태를 기술한다.',
        'Mechanical changes in intersomatic spaces.':
            '추체간 공간의 상태를 기술하며 비교 시점이 없다.',
    }
    manual=[]
    for text,why in current_examples.items():
        hits=[r for r in records if r['finding']['sentence_en']==text and r['finding'].get('progression') is None]
        assert hits
        manual.append(dict(sentence_en=text,assessment=why,n_matches=len(hits),
                           examples=[dict(ImageID=x['ImageID'],source_index=x['source_index'],
                                          sentence_es=x['finding'].get('sentence_es')) for x in hits]))
    d8=B.read(B.OUT/'data/D8/manifest.json')
    fixture=[]
    for row in d8:
        h,w=row['shape'];top,left,side=row['pad']
        for f in row['findings']:
            for box,canvas in zip(f.get('boxes',[]),f['canvas_boxes']):
                y0,x0,y1,x1=canvas
                back=[(x0*side/1000-left)/w,(y0*side/1000-top)/h,
                      (x1*side/1000-left)/w,(y1*side/1000-top)/h]
                fixture.append(max(abs(a-b) for a,b in zip(box,back))<1e-12)
    ids={s:{r['PatientID'] for r in selected[s]} for s in ('T512','V64','E128')}
    assert not ids['T512']&ids['V64'] and not ids['T512']&ids['E128'] and not ids['V64']&ids['E128']
    assert all(fixture)
    save(B.OUT/'data/temporal_audit.json',dict(summary=summary,excluded_TV=records,manual_examples=manual,
         data_gate_pass=False,reason='현재 상태 문장이 broad temporal regex로 제거되어 판독/위치 supervision이 누락된다.',
         original_abnormal_flags_preserved=True,
         scope='선택된 T512/V64만; E reference·영상·출력 미열람. 88문장 전부를 오제외로 확정한 것은 아니다.',
         source={str(B.ROOT/'pg39_data.py'):sha(B.ROOT/'pg39_data.py'),str(B.OUT/'data/selection.json'):sha(B.OUT/'data/selection.json')},
         proposed_action='원본과 첫 selection 보존. 명시적 시간 비교와 현재 상태를 구분하는 규칙을 계획 보완으로 고정한 뒤 새 manifest로 재검증. 현재는 규칙·표본을 임의 변경하지 않음.'))
    save(B.OUT/'data/D8/visual_review.json',dict(
         reviewer='assistant; 전문의 검증 아님',image_returned_by='functions tools.view_image, overlay_0.png through overlay_7.png',
         overlays={str(B.OUT/f'data/D8/overlay_{i}.png'):sha(B.OUT/f'data/D8/overlay_{i}.png') for i in range(8)},
         observations=[
             '0: frontal 영상의 화면 오른쪽 상완 고정물에 box가 연결된다. 제거된 만성 폐 문장이 따로 존재한다.',
             '1: 실제 frontal 영상 확인. 제외된 spondylosis 뒤의 No other 문장만 남아 target 의미가 불완전하다.',
             '2: 실제 frontal 영상 확인. 정상 annotation의 임상 정확성은 이 도구 점검으로 확정하지 않는다.',
             '3: 화면 왼쪽 상부 흉곽·상부 종격동과 화면 오른쪽 폐문 위 box 연결. nodule box가 넓은 원주석 한계는 유지.',
             '4: 다중 box는 화면 오른쪽 폐에 위치. locations 필드의 right/posterior rib와의 불일치는 원 metadata 수준이며 좌표를 임의 보정하지 않음.',
             '5: 하부 심장 뒤 영역 box와 원문 hiatal hernia 연결을 확인; 임상 확진 아님.',
             '6: 양측 기저부 box 및 넓은 보조 소견 box 연결.',
             '7: 대동맥 영역·척추 box 및 정상 범위 문장의 원문 연결.'],
         geometry_roundtrip_checks=len(fixture),geometry_roundtrip_pass=all(fixture),patient_split_disjoint=True))
    print(json.dumps(summary,ensure_ascii=False));print('DATA_GATE_FAIL: temporal target semantics')


if __name__=='__main__':main()
