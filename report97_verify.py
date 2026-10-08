"""iter_097 독립 재집계: score()/decide()를 호출하지 않고 judgments 원문에서 recall·반박·분기 수치를 다시 계산해 저장값과 대조.
학습 로그(384 updates, LR, 유한값)와 새 생성 stage 완료 검증도 포함한다. 연결·산술 검사이며 의미 타당성의 증명이 아니다."""
import glob
import json
import math
from pathlib import Path
import numpy as np
import report90_gen as C
import report97_gen  # noqa: F401  SOURCES 패치
import report90_recovery_gen as S
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

def recompute():
    root=OUT/'semantic/epoch6';blind=json.loads((root/'blinded.json').read_text());mapping=json.loads((root/'private_mapping.json').read_text())
    refs=json.loads((ORIGINAL/'semantic/V32_reference_v3.json').read_text())['rows'];byref={r['id']:r for r in refs}
    J={}
    for f in sorted(glob.glob(str(root/'judgments/part_*.json'))):
        d=json.loads(Path(f).read_text());assert d['blinded_sha']==sha(root/'blinded.json')
        for j in d['judgments']:assert j['blind_id'] not in J;J[j['blind_id']]=j
    assert set(J)=={r['blind_id'] for r in blind['records']}
    per={}
    for r in blind['records']:
        cond=Path(mapping[r['blind_id']]['stage']).name;ref=byref[r['image_id']];j=J[r['blind_id']]
        targets=[a['id'] for a in ref['atoms'] if a['polarity']=='positive' and a['certainty']=='definite']
        strict=[m['ref'] for m in j['matches'] if m['status']=='strict'];sure=[m['ref'] for m in j['matches'] if m['status']=='strict' and not m['ambiguous']]
        kinds=[m['ref'] for m in j['matches'] if m['status'] in ('strict','type_only')]
        for m in j['matches']:assert m['quote'] in r['text']
        for c in j['claims']:assert c['quote'] in r['text']
        contra=any(c['status']=='contradicted' for c in j['claims'])
        per.setdefault(cond,{})[r['image_id']]=dict(abnormal=ref['abnormal'],n=len(targets),
            strict=len(set(strict)&set(targets))/len(targets) if targets else None,
            sure=len(set(sure)&set(targets))/len(targets) if targets else None,
            kinds=len(set(kinds)&set(targets))/len(targets) if targets else None,contra=contra)
    return per

def main():
    per=recompute();stored=json.loads((OUT/'semantic/epoch6/eval/report.json').read_text())['conditions']
    checks={};summary={}
    for cond,rows in per.items():
        ids=[k for k,v in rows.items() if v['abnormal'] and v['strict'] is not None]
        s=float(np.mean([rows[k]['strict'] for k in ids]));t=float(np.mean([rows[k]['kinds'] for k in ids]));u=float(np.mean([rows[k]['sure'] for k in ids]))
        con=float(np.mean([v['contra'] for v in rows.values()]))
        summary[cond]=dict(recall_patients=len(ids),strict=s,type_only_or_strict=t,strict_unambiguous=u,contradiction_patients=int(sum(v['contra'] for v in rows.values())))
        checks[f'{cond}_strict']=abs(s-stored[cond]['strict_recall'])<1e-12
        checks[f'{cond}_type']=abs(t-stored[cond]['type_recall'])<1e-12
        checks[f'{cond}_contra']=abs(con-stored[cond]['contradiction'])<1e-12
    # 분기 수치 독립 재계산
    new='R_lr2e-05_report';dec=json.loads((OUT/'decisions/R_vs_comparators_epoch6.json').read_text())['results']
    for comp in ['base_V32','R_lr0.0001_report','R_lr0.0002_report']:
        ids=sorted(k for k,v in per[new].items() if v['abnormal'] and v['strict'] is not None)
        d=np.array([per[new][k]['strict']-per[comp][k]['strict'] for k in ids])
        net=int((d>1e-12).sum())-int((d<-1e-12).sum());loo=min(float(np.delete(d,i).mean()) for i in range(len(d)))
        rng=np.random.default_rng(97017);b=[float(d[rng.integers(0,len(d),len(d))].mean()) for _ in range(10000)]
        checks[f'decide_{comp}']=abs(d.mean()-dec[comp]['diff'])<1e-12 and net==dec[comp]['net'] and abs(loo-dec[comp]['loo_min'])<1e-12 and abs(np.percentile(b,2.5)-dec[comp]['ci95'][0])<1e-12
        summary[f'{new}_minus_{comp}']=dict(diff=float(d.mean()),net_patients=net,loo_min=loo,ci95=[float(np.percentile(b,2.5)),float(np.percentile(b,97.5))])
    # 학습 검증
    run=OUT/'train/R_lr2e-05';cfg=json.loads((run/'config.json').read_text())
    events=[json.loads(l) for f in sorted(run.glob('events_*.jsonl')) for l in f.read_text().splitlines()]
    checks['train_384_unique_updates']=[e['step'] for e in events]==list(range(1,385))
    checks['train_finite']=all(math.isfinite(e[k]) for e in events for k in ('loss','report_nll','ground_nll','grad_norm'))
    checks['train_cfg_lr_mode']=cfg['lr']==2e-5 and cfg['mode']=='R' and cfg['mb']==1 and len(cfg['patient_ids'])==512
    checks['train_report_only_loss']=all(abs(e['loss']-e['report_nll'])<1e-5 for e in events)
    checks['train_verified_file']=json.loads((run/'verified_06.json').read_text())['passed'] if (run/'verified_06.json').exists() else False
    nll={e:json.loads((run/f'validation_{e:02}.json').read_text())['report_nll'] for e in (1,2,4,6)}
    # 새 생성 stage 완료 검증 + record 수
    req32=ORIGINAL/'data/V32/requests.json';req16=ORIGINAL/'data/V16/requests.json'
    gen={}
    for rel,req,n in [('validation/epoch2/R_lr2e-05_report',req32,32),('validation/epoch6/R_lr2e-05_report',req32,32),('validation/epoch6/R_lr2e-05_ground',req16,16),('gen_tests/base_V32',req32,32)]:
        stage=(OUT/rel).resolve();C.SOURCES=C.SOURCES if 'report97_gen.py' in C.SOURCES else C.SOURCES+['report97_gen.py']
        proto=json.loads((stage/'protocol.json').read_text());w=json.loads((stage/'mapping.json').read_text())['workers']
        rows,expected=S.verify(stage,req,proto,w);checks[f'gen_{rel}']=len(rows)==len(expected)==n and (stage/'completion.json').exists()
        gen[rel]=dict(n=len(rows),non_eos=sum(not r['attempts'][-1]['ended_eos'] for r in rows))
    checks={k:bool(v) for k,v in checks.items()}
    save(OUT/'decisions/verify.json',dict(passed=all(checks.values()),checks=checks,summary=summary,validation_nll_R_lr2e5=nll,generation=gen,
        sources={f:sha(f) for f in [__file__,'report97_train.py','report97_decide.py','report97_judge_epoch6.py']},
        scope='연결·산술 재계산. 의미 판정은 assistant 해석이며 이 검사가 임상 타당성을 보증하지 않음.'))
    print(json.dumps(dict(passed=all(checks.values()),failed=[k for k,v in checks.items() if not v]),ensure_ascii=False))

if __name__=='__main__':main()
