"""iter_094: 선택 epoch1(신규 생성)과 저장 epoch2/6·base의 동일 V32 비교. 신규 학습·생성 없음, 결과는 results/iter_094/analysis 새 경로.
사전 기준(plan.md Evaluation)을 그대로 코드화한다. 의미 판정은 per_output(assistant 검토)을 읽기만 한다."""
import hashlib,json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
R=ROOT/'results'
I90=R/'iter_090/recovery'
OUT=R/'iter_094/analysis'
SEED=94017;NB=10000
LR='0.0002'

def jl(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(name,obj):
    p=OUT/name;assert not p.exists(),f'refuse overwrite {p}';p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=1,ensure_ascii=False));tmp.rename(p)

def load():
    refs=jl(R/'iter_090/semantic/V32_reference_v3.json')['rows'];order=[r['id'] for r in refs]
    per={};texts={}
    sources=[(I90/'semantic/epoch2/eval/per_output.json',I90/'semantic/epoch2/blinded.json',2),(I90/'semantic/epoch6/eval/per_output.json',I90/'semantic/epoch6/blinded.json',6),
             (R/'iter_094/semantic/epoch1/eval/per_output.json',R/'iter_094/semantic/epoch1/blinded.json',1)]
    for po,bl,e in sources:
        t={r['blind_id']:r['text'] for r in jl(bl)['records']}
        for x in jl(po):
            c=x['condition'];key=('base',0) if c=='base_report' else (c.replace('_report','').replace('_epoch1','_lr'+LR),e)
            if key[0] not in ('base',f'R_lr{LR}',f'G_lr{LR}'):continue
            assert (key,x['image_id']) not in per;per[(key,x['image_id'])]=x;texts[(key,x['image_id'])]=t[x['blind_id']]
    return refs,order,per,texts

def vec(per,order,key,field='strict_recall'):
    return [per[(key,i)][field] for i in order]

def boot(d,rng):
    d=np.asarray(d,float);n=len(d)
    bs=np.array([d[rng.integers(0,n,n)].mean() for _ in range(NB)])
    loo=[float(np.delete(d,i).mean()) for i in range(n)]
    return dict(n=n,mean=float(d.mean()),ci95=[float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5))],loo_min=min(loo),loo_max=max(loo),
                n_up=int((d>0).sum()),n_down=int((d<0).sum()),n_zero=int((d==0).sum()))

def contrast(per,order,a,b,field,rng):
    va,vb=vec(per,order,a,field),vec(per,order,b,field)
    d=[x-y for x,y in zip(va,vb) if x is not None and y is not None]
    return boot(d,rng)

def atoms(per,order,key,kinds):
    return [sorted({m['ref'] for m in per[(key,i)]['matches'] if m['status'] in kinds}) for i in order]

def condition_summary(per,order,texts,key):
    rows=[per[(key,i)] for i in order];el=[r for r in rows if r['positive_n']]
    generic_abn=sum(1 for i in order if per[(key,i)]['abnormal'] and not any(c['polarity']=='positive' for c in per[(key,i)]['claims']))
    return dict(n=len(rows),abnormal_n=sum(r['abnormal'] for r in rows),recall_eligible_n=len(el),
        strict_recall=float(np.mean([r['strict_recall'] for r in el])),type_recall=float(np.mean([r['type_recall'] for r in el])),
        strict_atoms_total=int(sum(len(a) for a in atoms(per,order,key,['strict']))),
        patients_with_strict=sum(r['strict_recall']>0 for r in el),
        normal_only_output_in_abnormal=generic_abn,
        contradiction_patients=sum(r['contradiction'] for r in rows),contradiction_patients_abnormal=sum(r['contradiction'] for r in rows if r['abnormal']),
        internal_contradiction_patients=sum(r['internal_contradiction'] for r in rows),internal_contradiction_patients_abnormal=sum(r['internal_contradiction'] for r in rows if r['abnormal']),
        unknown_claims=sum(r['claim_counts']['unknown'] for r in rows),supported_claims=sum(r['claim_counts']['supported'] for r in rows),
        contradicted_claims=sum(r['claim_counts']['contradicted'] for r in rows),non_eos=sum(r['non_eos'] for r in rows),format_failure=sum(r['format_failure'] for r in rows),
        mean_words=float(np.mean([len(texts[(key,i)].split()) for i in order])))

def criterion(per,order,a,b,rng):
    """a가 b(epoch1)보다 나은지: 사전 기준 (a)(b)(c)."""
    main=contrast(per,order,a,b,'strict_recall',rng)
    sens_ref=contrast(per,order,a,b,'no_ambiguous_reference',rng);sens_match=contrast(per,order,a,b,'no_ambiguous_match',rng)
    ca=condition_summary(per,order,None,a) if False else None
    ra=[per[(a,i)] for i in order];rb=[per[(b,i)] for i in order]
    cnt=lambda rows,f,abn=False:sum(r[f] for r in rows if (r['abnormal'] or not abn))
    err={f:dict(a=cnt(ra,f),b=cnt(rb,f),a_abn=cnt(ra,f,True),b_abn=cnt(rb,f,True)) for f in ('contradiction','internal_contradiction')}
    ca_=main['n_up']>=2 and main['n_up']>main['n_down']
    cb=main['mean']>0 and main['loo_min']>0 and sens_ref['mean']>0 and sens_match['mean']>0
    cc=all(v['a']<=v['b'] and v['a_abn']<=v['b_abn'] for v in err.values())
    return dict(main=main,sens_no_ambiguous_reference=sens_ref,sens_no_ambiguous_match=sens_match,errors=err,
        criteria=dict(a_two_or_more_patients_up_and_up_gt_down=ca_,b_positive_mean_loo_and_sensitivities=cb,c_errors_not_increased=cc),passes=bool(ca_ and cb and cc))

def main():
    refs,order,per,texts=load()
    assert len(order)==32 and len(per)==32*7,(len(per))
    keys=[('base',0)]+[(f'{m}_lr{LR}',e) for m in 'RG' for e in (1,2,6)]
    rng=np.random.default_rng(SEED)
    conds={f'{k[0]}@{k[1]}':condition_summary(per,order,texts,k) for k in keys}
    R1,R2,R6=[(f'R_lr{LR}',e) for e in (1,2,6)];G1,G2,G6=[(f'G_lr{LR}',e) for e in (1,2,6)]
    crit=dict(R_epoch6_vs_epoch1=criterion(per,order,R6,R1,rng),R_epoch2_vs_epoch1=criterion(per,order,R2,R1,rng),
              G_epoch6_vs_epoch1=criterion(per,order,G6,G1,rng),G_epoch2_vs_epoch1=criterion(per,order,G2,G1,rng))
    contr={}
    for name,a,b in [('G1-R1',G1,R1),('G2-R2',G2,R2),('G6-R6',G6,R6),('R1-base',R1,('base',0)),('R2-base',R2,('base',0)),('R6-base',R6,('base',0)),
                     ('G1-base',G1,('base',0)),('G2-base',G2,('base',0)),('G6-base',G6,('base',0)),('R6-R2',R6,R2),('G6-G2',G6,G2)]:
        c=contrast(per,order,a,b,'strict_recall',rng)
        ea,eb=atoms(per,order,a,['strict']),atoms(per,order,b,['strict'])
        c.update(atoms_gained=sum(len(set(x)-set(y)) for x,y in zip(ea,eb)),atoms_lost=sum(len(set(y)-set(x)) for x,y in zip(ea,eb)),
                 patients_with_gain=sum(bool(set(x)-set(y)) for x,y in zip(ea,eb)),patients_with_loss=sum(bool(set(y)-set(x)) for x,y in zip(ea,eb)))
        contr[name]=c
    # 변경 사례 목록(원문 span 검토 대상): strict 회복·소실, 모든 명시 모순, 일반 정상문 환자
    cases=[]
    for name,a,b in [('R6 vs R1',R6,R1),('R2 vs R1',R2,R1),('G6 vs G1',G6,G1),('G2 vs G1',G2,G1),('R1 vs base',R1,('base',0)),('G1 vs base',G1,('base',0))]:
        for i,idx in zip(order,range(32)):
            sa,sb=set(atoms(per,order,a,['strict'])[idx]),set(atoms(per,order,b,['strict'])[idx])
            if sa!=sb:cases.append(dict(comparison=name,index=idx,gained=sorted(sa-sb),lost=sorted(sb-sa),text_a=texts[(a,i)],text_b=texts[(b,i)]))
    contras=[dict(cond=f'{k[0]}@{k[1]}',index=idx,text=texts[(k,i)],claims=[(c['finding'],c['polarity'],c['status'],c['quote']) for c in per[(k,i)]['claims'] if c['status']=='contradicted'],
                  internal=per[(k,i)]['internal_conflicts'] and [[x['quote'] for x in p] for p in per[(k,i)]['internal_conflicts']])
             for k in keys for idx,i in enumerate(order) if per[(k,i)]['contradiction'] or per[(k,i)]['internal_contradiction']]
    save('summary.json',dict(seed=SEED,bootstrap=NB,conditions=conds,criteria=crit,contrasts=contr,changed_strict_cases=cases,contradiction_cases=contras,
        denominators=dict(all=32,abnormal=21,recall_eligible=20),
        note='V32는 반복 개발 자료이며 독립 확인이 아니다. 판정은 assistant 검토이며 전문의 판독이 아니다. LR1e-4 결과는 사용하지 않는다.'))
    print(json.dumps(dict(conditions={k:{x:v[x] for x in ('strict_recall','type_recall','patients_with_strict','normal_only_output_in_abnormal','contradiction_patients','internal_contradiction_patients')} for k,v in conds.items()},
        crit={k:dict(main=dict(mean=v['main']['mean'],up=v['main']['n_up'],down=v['main']['n_down'],loo=[v['main']['loo_min'],v['main']['loo_max']],ci=v['main']['ci95']),
            sens=[v['sens_no_ambiguous_reference']['mean'],v['sens_no_ambiguous_match']['mean']],crit=v['criteria'],passes=v['passes'],err=v['errors']) for k,v in crit.items()}),indent=1))
    print('n_changed_cases',len(cases),'n_contra_cases',len(contras))

if __name__=='__main__':
    main()
