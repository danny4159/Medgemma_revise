"""iter_094: 오류 비용(c)의 해석 민감도와 영향 사례의 원문 검토 기록. 신규 학습·생성 없음.
사례 판정은 report94_cases.py 출력(원문 문장과 reference atom)을 읽고 정한 assistant 검토이며 전문의 판독이 아니다."""
import json
from pathlib import Path
import report94_analyze as A

# 명시 모순 후보 검토(LR2e-4 R/G): 구체적 reference atom과 출력 문장을 대조한 결과
CONTRA_REVIEW={
 ('R_lr0.0002@2',20):dict(verdict='valid_conflict',why='reference는 subclavian vein 경유 중심정맥관, 출력은 right jugular 경로 — 위치 충돌'),
 ('G_lr0.0002@2',20):dict(verdict='valid_conflict',why='동일 문장, 동일 reference'),
 ('R_lr0.0002@6',20):dict(verdict='valid_conflict',why='right jugular to SVC vs subclavian vein — 위치 충돌'),
 ('G_lr0.0002@6',20):dict(verdict='valid_conflict',why='동일 문장 계열'),
 ('R_lr0.0002@6',28):dict(verdict='valid_conflict',why='출력 left humeral head prosthesis, reference right humerus metallic prosthesis — 좌우 충돌'),
 ('R_lr0.0002@6',29):dict(verdict='ambiguous',why='"No definitive images of ... nodules or masses"는 완곡한 부정이며 reference의 확정 결절 2개와는 충돌하나 문구가 hedged'),
 ('G_lr0.0002@6',21):dict(verdict='ambiguous',why='biventricular vs dual chamber는 장치 명칭 차이이며 reference는 dual chamber 속성만 명시. 존재 자체의 충돌은 아님'),
}

def alt_counts(per,order,key):
    """해석 민감도: (1) 저장 판정, (2) 모호 후보 제외, (3) 확정 양성 reference가 있는 환자에 대한 일반 정상 단독 출력을 모순으로 계산."""
    refs=A.jl(A.R/'iter_090/semantic/V32_reference_v3.json')['rows'];rows=[per[(key,i)] for i in order]
    name=f'{key[0]}@{key[1]}'
    stored=[bool(r['contradiction']) for r in rows]
    excl=[]
    for idx,r in enumerate(rows):
        v=r['contradiction']
        if v and CONTRA_REVIEW.get((name,idx),dict(verdict='valid_conflict'))['verdict']=='ambiguous':
            # 같은 출력에 다른 명시 모순이 없을 때만 제외
            v=sum(c['status']=='contradicted' for c in r['claims'])>1
        excl.append(bool(v))
    generic=[]
    for idx,(r,ref) in enumerate(zip(rows,refs)):
        pos=any(a['polarity']=='positive' and a['certainty']=='definite' for a in ref['atoms'])
        only_neg=not any(c['polarity']=='positive' for c in r['claims']) and any(c['polarity']=='negative' for c in r['claims'])
        generic.append(bool(r['contradiction'] or (pos and only_neg)))
    abn=[r['abnormal'] for r in rows]
    f=lambda v:dict(all=sum(v),abnormal=sum(x for x,a in zip(v,abn) if a))
    return dict(stored=f(stored),ambiguous_excluded=f(excl),generic_normal_as_contradiction=f(generic))

def main():
    refs,order,per,texts=A.load()
    LR=A.LR
    keys=[('base',0)]+[(f'{m}_lr{LR}',e) for m in 'RG' for e in (1,2,6)]
    counts={f'{k[0]}@{k[1]}':alt_counts(per,order,k) for k in keys}
    verdict={}
    for name,a,b in [('R_epoch6_vs_epoch1',(f'R_lr{LR}',6),(f'R_lr{LR}',1)),('R_epoch2_vs_epoch1',(f'R_lr{LR}',2),(f'R_lr{LR}',1)),
                     ('G_epoch6_vs_epoch1',(f'G_lr{LR}',6),(f'G_lr{LR}',1)),('G_epoch2_vs_epoch1',(f'G_lr{LR}',2),(f'G_lr{LR}',1))]:
        ca,cb=counts[f'{a[0]}@{a[1]}'],counts[f'{b[0]}@{b[1]}']
        ok=lambda kind:all(ca[kind][s]<=cb[kind][s] for s in ('all','abnormal'))
        verdict[name]={k:dict(a=ca[k],b=cb[k],not_increased=ok(k)) for k in ca}
    # epoch1 V13 모호 일치를 type_only로 바꿀 때의 R6−R1: 별도 계산(저장 판정 불변, 한 환자 값만 대체)
    R1=(f'R_lr{LR}',1);R6=(f'R_lr{LR}',6);import numpy as np
    d=[]
    for idx,i in enumerate(order):
        x,y=per[(R6,i)]['strict_recall'],per[(R1,i)]['strict_recall']
        if x is None:continue
        if idx==13:y=0.0
        d.append(x-y)
    d=np.array(d)
    v13=dict(mean=float(d.mean()),up=int((d>0).sum()),down=int((d<0).sum()),loo_min=min(float(np.delete(d,j).mean()) for j in range(len(d))))
    A.OUT.mkdir(parents=True,exist_ok=True)
    A.save('sensitivity.json',dict(contradiction_review={f'{k[0]}|{k[1]}':v for k,v in CONTRA_REVIEW.items()},counts=counts,error_not_increased_under_interpretations=verdict,
        R6_vs_R1_if_epoch1_V13_type_only=v13,
        note='(3)은 일반 정상문 단독 출력을 확정 양성 reference 환자에서 모순으로 세는 해석이다. 저장 규약(unknown)과 다르며 임상 판단이 아니다. base의 Normal chest X-ray 문장은 저장 판정에서 모순으로 계산돼 있어 규약 간 불일치가 있다.'))
    print(json.dumps(dict(counts=counts,verdict={k:{kk:vv['not_increased'] for kk,vv in v.items()} for k,v in verdict.items()},v13=v13),indent=1))

if __name__=='__main__':
    main()
