"""iter_142 새 출력의 사례별 텍스트 판정표. 범용 의미 평가기로 재사용하지 않는다."""
import re
from i142_common import *

def sentence(text,fragment):
    hits=[s.strip() for s in re.split(r'(?<=\.)\s+',text) if fragment in s]
    assert hits, fragment
    return hits[0]

def main():
    refs={r['patient_id']:r for r in read(OLD/'reference_locked.json')['rows']}
    records={r['patient_id']:r for r in [read(p) for p in sorted((RES/'jobs/main').glob('*/result.json'))]}
    assert len(records)==6
    all_j={}
    for pid,rec in records.items():
        ref=refs[pid]
        modes={'final':rec['report'],'raw':' '.join(s for g in rec['observations']['generation'] for s in g['decoded'])}
        all_j[pid]={}
        for mode,text in modes.items():
            judgments={a['id']:{'state':'unmentioned','quotes':[],
                       'reason':'필요한 소견/위치/속성 전체가 명시되지 않음. 미언급은 임상 부재 정답이 아님.'} for a in ref['positive_atoms']}
            def set_atom(index,state,fragments,reason):
                key=pid+'__atom'+str(index).zfill(2)
                judgments[key]={'state':state,'quotes':[sentence(text,f) for f in fragments],'reason':reason}
            first=next(s.strip() for s in re.split(r'(?<=\.)\s+',text) if 'high signal intensity' in s and 'DWI' in s)
            set_atom(0,'matched',[first],'병변과 고신호를 명시하여 공개 abnormal signal 항목에 대응함.')
            set_atom(1,'matched',[first],'같은 DWI sequence의 high signal intensity를 명시함.')
            extras=[]
            if pid.endswith('0004'):
                set_atom(4,'matched',['right frontal lobe'],'공개 right frontal lobe 위치를 명시함.')
                fragment='right frontal-parietal lobe' if mode=='final' else 'left frontal-parietal lobe'
                set_atom(5,'unresolved',[fragment],
                    'frontal-parietal lobe 기술이 원문의 두 엽 경계(border)를 지칭하는지 미확정. 경계 위치를 임상 추론으로 채우지 않음.')
                extras=[('acute or subacute infarction','원인·시기는 현재 DWI 정답 범위 밖이며 공개 항목으로 검증하지 않음.'),
                        ('no observed abnormalities in the midline structures, sulci, gyri, ventricles, or cisterns','midline 이외의 주변 구조 정상 진술은 제공 reference로 검증하지 못함.')]
                if mode=='raw':
                    extras.append(('left frontal lobe','추가 좌측 위치의 임상 참/거짓은 공개 양성 목록만으로 판정하지 않음.'))
            elif pid.endswith('0006'):
                set_atom(4,'unresolved',['brainstem'],
                    'brainstem은 넓은 부위명이다. cerebral peduncles와 같은 위치라고 임상 추론으로 확정하지 않음.')
                extras=[('cerebellum','reference의 cerebral peduncles 이외 cerebellum/occipital 위치 기술은 미검증.'),
                        ('right frontal lobe','추가 frontal 위치는 미검증. reference 미언급을 음성 정답으로 만들지 않음.')]
            elif pid.endswith('0007'):
                set_atom(2,'matched',['scattered lesions'],'분산된(scattered) 병변을 명시함.')
                set_atom(4,'matched',['bilateral cerebellum'],'bilateral은 좌우를 명시하므로 공개 left cerebellum 양성도 포함함. 추가 우측의 진위는 별도 미검증.')
                if mode=='final':
                    set_atom(5,'matched',['right occipital lobe'],'최종 문장에 공개 right occipital 위치가 명시됨. 공식 좌우 후처리의 영향이 있음.')
                else:
                    set_atom(6,'matched',['brainstem'],'후처리 전 global 생성문에는 공개 brainstem 위치가 명시됨.')
                extras=[('right frontal lobe, bilateral cerebellum, and right thalamus','right frontal/right thalamus 및 추가 우측 cerebellum은 공개 목록 밖의 미검증 위치.'),
                        ('no mention of abnormalities in sulci','원문에 대한 메타 문구이며 임상 정상 정답으로 점수화하지 않음.')]
            elif pid.endswith('0008'):
                set_atom(4,'matched',['left frontal lobe'],'공개 left frontal lobe 위치를 명시함.')
                extras=[('right frontal lobe','추가 우측 frontal 위치는 공개 정답으로 임상 진위를 판정할 수 없음.')]
                if mode=='raw':
                    extras.append(('bilateral cerebellum','추가 cerebellum 위치는 미검증.'))
            elif pid.endswith('0009'):
                if mode=='final':
                    set_atom(5,'matched',['left frontal-parietal-occipital lobes and the left temporal lobe'],
                        '최종 출력이 좌측 frontal/parietal과 좌측 temporal을 함께 명시해 공개 복합 위치에 대응함. 추가 occipital은 별도 미검증.')
                else:
                    set_atom(5,'unresolved',['left frontal-parietal-occipital lobes and the right temporal lobe'],
                        '공개 문장의 left basal ganglia와 이어진 frontal/parietal/temporal 위치에 대해, 좌측 두 엽과 우측 temporal의 조합은 동일 복합 위치 대응이 모호함. 임의로 좌우 의미를 확정하지 않음.')
                extras=[('acute or chronic infarction','병인·시기 표현은 이번 공개 DWI 평가 범위에서 미검증.'),
                        ('surrounding brain edema','추가 brain edema는 공개 reference로 검증하지 못함.'),
                        ('right frontal lobe','추가 우측 frontal 위치는 미검증.'),
                        ('no evidence of abnormalities in nearby sulci','midline 외 구조 정상 진술은 미검증.')]
            elif pid.endswith('0010'):
                if mode=='final':
                    set_atom(5,'matched',['right cerebellum'],'최종 출력의 right cerebellum을 명시적으로 회복함. 원시 left cerebellum에 대한 공식 좌우 수정의 영향임.')
                # 부분 위치는 원 iter_141 규약대로 전체 위치 회복으로 세지 않는다.
                judgments[pid+'__atom06']['reason']='right thalamus만 명시됨. bilateral의 왼쪽은 미언급.'
                judgments[pid+'__atom07']['reason']='최종 left occipital만 있고 left parietal 연결이 없음. 원시 right occipital 역시 전체 left parieto-occipital을 회복하지 않음.'
                extras=[('right frontal lobe','추가 우측 frontal/parietal 소견은 미검증.'),
                        ('basal ganglia region','추가 basal ganglia 위치는 공개 정답으로 검증하지 못함.'),
                        ('no observed alterations in the sulci','주변 구조 정상 기술은 midline 이외 공개 음성 항목이 없어 미검증.')]
            else:
                raise AssertionError(pid)
            all_j[pid][mode]={'atoms':judgments,'reference_contradictions':[], 'internal_contradictions':[],
                 'report_unverified':[{'quote':sentence(text,f),'reason':why} for f,why in extras],
                 'review_note':'전체 새 원문을 확인했다. 공개 양성 목록 밖 위치를 음성으로 만들지 않았다. 명시적인 저신호/병변 부재/위치 배타성 주장 또는 동일 scope의 양립 불가 문장은 확인하지 못했다.',
                 'extra_coverage':'원문 기반 미검증 추가 소견의 대표 목록. 임상 FP 전수 집계가 아님.'}
    save(RES/'eval/judgments.json',all_j)
    save(RES/'eval/judgment_provenance.json',{'created_at':now(),'source_sha256':sha(__file__),
        'reference_sha256':sha(OLD/'reference_locked.json'),
        'outputs':{str(RES/'jobs/main'/p/'result.json'):sha(RES/'jobs/main'/p/'result.json') for p in records},
        'judgments_sha256':sha(RES/'eval/judgments.json'),
        'judgment_timing':'새 생성 이후 제한된 assistant 텍스트 판정. 사건 정의·집계 코드는 본 생성 전에 잠금.',
        'independent_clinician':False})
    print({'patients':len(all_j),'modes':2})

if __name__=='__main__':
    main()
