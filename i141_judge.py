"""생성 후 원문을 읽어 고정한 12개 package의 한정 대응표.

이 파일은 임상 정답 생성기나 범용 의미 parser가 아니다. 기준은 생성 전
i141_spec.py/reference_locked.json에 고정됐다. 아래는 사후 assistant 텍스트 판정이며
독립 전문의 평가가 아니다. 조건명을 사용하지 않고 공개 문장과 실제 출력 span을 연결한다.
"""
from i141_common import RES, read, save, sha, now

# atom 번호 → 원문 문장 번호. 정확한 복합 위치·좌우·속성만 matched로 둔다.
MATCHED = {
    'Q00': {0:[0], 1:[2], 5:[6]},
    'Q01': {0:[58], 1:[59], 4:[58]},
    'Q02': {0:[25], 1:[27], 4:[25]},
    'Q03': {0:[45], 1:[47], 2:[45], 4:[56], 5:[3]},
    'Q04': {0:[0], 1:[2]},
    'Q05': {0:[3], 1:[5]},
    'Q06': {0:[0], 1:[1]},
    'Q07': {0:[0], 1:[2]},
    'Q08': {0:[0], 1:[2]},
    'Q09': {0:[10], 1:[12]},
    'Q10': {0:[53], 1:[68], 4:[66], 7:[70]},
    'Q11': {0:[8], 1:[9], 2:[44]},
}
UNRESOLVED = {
    'Q00': {2:([0],'multiple foci만으로 scattered 분포를 확정하지 않음'),
            3:([6,31],'round/spherical 형상이 patchy 기술과 같은지 미판정')},
    'Q01': {2:([33,35],'bilateral/periventricular 분포가 scattered와 같은지 미판정'),
            3:([61],'small focus가 punctate와 같은지 미판정'),
            6:([68],'left thalamus를 basal ganglia region으로 옮기는 해부학 추론을 하지 않음')},
    'Q02': {2:([33,34],'여러 lobe의 multiple foci와 scattered 대응은 미판정'),
            3:([0],'ovoid 형상이 patchy와 같은지 미판정'),
            7:([15,17],'periventricular에 lateral ventricle이 명시되지 않음')},
    'Q03': {3:([4],'irregular 형상이 patchy와 같은지 미판정')},
    'Q04': {},
    'Q05': {},
    'Q06': {2:([0,13],'여러 영역/symmetric hyperintensities를 scattered로 추정하지 않음'),
            3:([83],'irregular 형상이 plaque-like와 같은지 미판정'),
            5:([85,86],'right posterior hemisphere만으로 right occipital lobe를 추정하지 않음')},
    'Q07': {3:([1],'irregular 형상이 patchy와 같은지 미판정')},
    'Q08': {2:([0,1],'multiple foci를 scattered로 확정하지 않음'),
            3:([11],'small foci를 punctate로 확정하지 않음')},
    'Q09': {2:([10],'multiple foci를 scattered로 확정하지 않음'),
            3:([11,38],'rounded/ill-defined 형상과 patchy 대응 미판정')},
    'Q10': {2:([79,80],'several focal areas를 scattered로 확정하지 않음'),
            3:([13,81],'irregular/rounded 형상과 patchy 대응 미판정')},
    'Q11': {3:([62],'roughly circular 형상이 patchy와 같은지 미판정')},
}
PARTIAL = {
    'Q03': {6:([64],'right thalamus만 기술됨. bilateral의 왼쪽 회복은 미언급'),
            7:([140,141],'posterior/likely parietal만 기술됨. left+occipital 연결은 미언급')},
    'Q09': {5:([13,15],'frontal/parietal만 기술됨. temporal을 포함한 전체 복합 위치는 미언급')},
    'Q10': {5:([80],'두 lobe의 별도 병변을 frontoparietal border로 만들지 않음')},
    'Q11': {5:([74,79],'frontal/parietal만 기술됨. temporal 포함 전체 복합 위치는 미언급')},
}
EXTRAS = {
    'Q00': [0,7,25,37,49,55,56],
    'Q01': [0,2,27,33,35,37,68],
    'Q02': [0,1,15,32,34,42,46],
    'Q03': [6,8,25,70,71,81,92,100,114,117],
    'Q04': [0,22,36],
    'Q05': [3,5,25,31],
    'Q06': [0,2,9,13,14,33,80,82,85],
    'Q07': [0,12,14,45,91,92],
    'Q08': [0,1,11,22,34,35],
    'Q09': [0,10,11,23,27,28,37,39],
    'Q10': [4,8,9,15,16,50,58,69,76,82,114],
    'Q11': [5,6,9,54,57,62,73,74,79,87,116,118,133,135],
}
INTERNAL = {
    'Q00': [('unresolved',[25,26,28],'increased/hyperintense와 dark가 같은 묶음에서 나옴. dark의 상대 기준이 없어 확정 반대 신호로 해석하지 않음')],
    'Q01': [('unresolved',[19,20,21],'같은 slice의 high/dark 기술. dark의 상대 기준 미확인')],
    'Q02': [('confirmed',[0,3],'같은 5장 묶음에서 병변 존재와 brain parenchyma에 visible abnormality 없음이 함께 기술됨')],
    'Q03': [('unresolved',[23],'dark를 high signal의 근거로 기술. 상대 밝기 기준 미확인'),
            ('unresolved',[145],'increased signal과 appearing dark를 같은 영역에 기술. 상대 기준 미확인')],
    'Q10': [('unresolved',[114],'increased signal과 appearing dark를 같은 영역에 기술. 상대 기준 미확인'),
            ('unresolved',[116,118],'동일 slice에서 no abnormality와 likely lesion이 함께 있으나 양성이 hedge되어 확정 모순으로 세지 않음')],
    'Q11': [('unresolved',[121,122,123],'동일 slice의 high/dark 기술. 상대 기준 미확인')],
}


def main():
    path=RES/'eval/blinded_packages.json'
    packages=read(path)
    assert {x['id'] for x in packages}==set(MATCHED)==set(UNRESOLVED)
    result={}
    review=[]
    for p in packages:
        q=p['id']
        def quotes(indices):
            return [p['package']['sentences'][i]['text'] for i in indices]
        row={'atoms':{},'reference_contradictions':[], 'internal_contradictions':[],
             'report_unverified_claims':[], 'review_note':'일반 finding/signal과 구체 위치·속성을 분리한 텍스트 일치도다. 같은 실제 병변의 시각적 회복이나 임상 정확도를 인증하지 않음.'}
        for i,atom in enumerate(p['reference']['positive_atoms']):
            if i in MATCHED[q]:
                value={'state':'matched','output_quotes':quotes(MATCHED[q][i]),
                       'reason':'공개 항목을 명시적으로 기술. 위치의 요구 범위/좌우가 충족됨. generic 항목은 위치 회복과 별도.'}
            elif i in UNRESOLVED[q]:
                inds,reason=UNRESOLVED[q][i]
                value={'state':'unresolved','output_quotes':quotes(inds),'reason':reason}
            elif i in PARTIAL.get(q,{}):
                inds,reason=PARTIAL[q][i]
                value={'state':'unmentioned','output_quotes':quotes(inds),'reason':reason}
            else:
                value={'state':'unmentioned','output_quotes':[],'reason':'해당 완전한 소견/위치/속성이 기술되지 않음. 미언급을 임상 부재로 바꾸지 않음.'}
            value['reference_span']={k:atom[k] for k in ['quote','start','end']}
            row['atoms'][atom['id']]=value
        for status,indices,reason in INTERNAL.get(q,[]):
            qs=quotes(indices)
            same=[r for r in p['outputs'] if all(s in r['final_text'] for s in qs)]
            assert same,'서로 다른 slice 범위를 내부 모순으로 합치지 않는다: '+q
            row['internal_contradictions'].append({'status':status,'quotes':qs,'reason':reason,
                'scopes':[{'id':r['id'],'slice_indices':r['slice_indices']} for r in same]})
        for i in EXTRAS[q]:
            text=quotes([i])[0]
            row['report_unverified_claims'].append({'quote':text,'sentence_index':i,
                'status':'report_unverified_or_input_unsupported',
                'reason':'reference에 없는 위치/형상·원인/병기·확산 제한·제공되지 않은 sequence 관찰 또는 비판독 문구의 원문 예시. 임상 허위 판정 아님.'})
        # 위 예시는 독특한 추가 위치·속성·원인 기술을 묶은 것이다. 전체 임상 FP 수가 아니다.
        row['extra_claim_coverage']='원문 기반 대표 추가 기술 목록. 반복과 동의어를 임상 FP로 전수 계산하지 않음.'
        row['reference_contradiction_note']='각 출력의 정상/부재 기술은 해당 slice/묶음 범위. 다른 범위의 양성 reference와 자동 충돌로 세지 않음. 추가 위치를 reference 미언급만으로 반박하지 않음.'
        result[q]=row
        review.append({'package':q,'reviewed_exact_deduplicated_sentences':len(p['package']['sentences']),
                       'same_scope_conflicts_checked':len(row['internal_contradictions']),
                       'reference_atoms':len(row['atoms']),'conditional_clinical_truth_invented':False})
    for q,row in result.items():
        package=next(p for p in packages if p['id']==q)
        text=package['package']['raw_concatenation']
        assert all(v['quote'] in text for v in row['report_unverified_claims'])
    save(RES/'eval/judgments.json',result)
    save(RES/'eval/assistant_review_record.json',{'created_at':now(),'packages_sha256':sha(path),
         'reference_sha256':sha(RES/'reference_locked.json'),'adjudication_source_sha256':sha(__file__),
         'post_generation':True,'independent_clinician':False,'rules_changed_after_generation':False,
         'scope':'고정 reference atom과 소견 집합 대응. unclear 동의어/범위는 unresolved. 추가 임상 정답 생성 없음.',
         'reviews':review})
    print({'judged_packages':len(result),'source_span_quotes_checked':True})


if __name__=='__main__':
    main()
