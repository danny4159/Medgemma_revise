"""사전 고정한 epoch2/6 확대와 최종 공통 checkpoint 선택. E는 읽지 않는다."""
import argparse
import json
from pathlib import Path
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
OUT=ORIGINAL/'recovery'

def read(p,inputs):
    p=Path(p);inputs[str(p)]=sha(p);return json.loads(p.read_text())

def main(epoch):
    inputs={};rules=read(OUT/'stage_decision_rules.json',inputs)
    refs=read(ORIGINAL/'semantic/V32_reference_v3.json',inputs)['rows']
    definite={a['id'] for r in refs for a in r['atoms'] if a['polarity']=='positive' and a['certainty']=='definite'}
    rows=read(OUT/f'semantic/epoch{epoch}/eval/per_output.json',inputs)
    summary=read(OUT/f'semantic/epoch{epoch}/eval/report.json',inputs)
    verification=read(OUT/f'semantic/epoch{epoch}/eval/verification.json',inputs)
    assert verification['passed'] and not verification['differences']
    for p,h in verification['sources'].items():assert sha(p)==h
    for name in ('report.json','per_output.json'):
        p=OUT/f'semantic/epoch{epoch}/eval'/name
        assert verification['sources'][str(p)]==sha(p)
    for p,h in summary['provenance'].items():assert sha(p)==h
    by={c:{r['patient']:r for r in rows if r['condition']==c} for c in {r['condition'] for r in rows}}
    strict=lambda r:{m['ref'] for m in r['matches'] if m['status']=='strict'}&definite
    jobs=[(m,lr) for lr in (.0001,.0002) for m in ('R','G')]
    nll={}
    for m,lr in jobs:
        run=OUT/'train'/f'{m}_lr{lr:g}'
        verified=read(run/f'verified_{epoch:02}.json',inputs);assert verified['passed']
        nll[m,lr]=read(run/f'validation_{epoch:02}.json',inputs)['report_nll']
    if epoch==2:
        base=by['base_report'];initial=read(ORIGINAL/'validation/base_nll.json',inputs)['report_nll']
        base_ground=read(ORIGINAL/'validation/base_ground_eval.json',inputs)['scores']['0.3'];details=[]
        for m,lr in jobs:
            name=f'{m}_lr{lr:g}';current=by[name+'_report'];assert set(current)==set(base)
            eligible=[p for p in base if base[p]['abnormal'] and base[p]['positive_n']]
            gain=[p for p in eligible if strict(current[p])-strict(base[p])]
            loss=[p for p in eligible if strict(base[p])-strict(current[p])]
            ground=read(OUT/f'validation/epoch2/{name}_ground_eval.json',inputs)['scores']['0.3']
            branches=dict(multiple_recovery=len(gain)>=2,grounding=m=='G' and ground>base_ground,
                          nll_and_mixed=nll[m,lr]<=.95*initial and bool(gain) and bool(loss))
            details.append(dict(mode=m,lr=lr,gain_patients=gain,loss_patients=loss,nll=nll[m,lr],grounding_f1=ground,branches=branches))
        expand=any(any(d['branches'].values()) for d in details)
        target=OUT/'decisions/expand_epoch6.json'
        previous=None
        if target.exists():
            prior=read(target,inputs)
            assert prior.get('semantic_V32_pending') and prior['expand']==expand
            for p,h in prior['inputs'].items():assert sha(p)==h
            previous=sha(target);target=OUT/'decisions/expand_epoch6_semantic_confirmation.json'
        save(target,dict(expand=expand,jobs=jobs if expand else [],details=details,inputs=inputs,source_sha=sha(__file__),
                         previous_decision_sha=previous,semantic_V32_pending=False))
    else:
        assert epoch==6
        selected={m:min((.0001,.0002),key=lambda lr:(nll[m,lr],lr)) for m in ('R','G')}
        prior=read(OUT/'semantic/epoch2/eval/report.json',inputs)['conditions'];conditions=summary['conditions'];details=[]
        for m,lr in selected.items():
            name=f'{m}_lr{lr:g}';n4=read(OUT/'train'/name/'validation_04.json',inputs)['report_nll']
            diff=conditions[name+'_report']['strict_recall']-prior[name+'_report']['strict_recall']
            details.append(dict(mode=m,lr=lr,nll4=n4,nll6=nll[m,lr],strict_recall_change=diff,extend=nll[m,lr]<=.98*n4 and diff>=-.05))
        expand=any(d['extend'] for d in details)
        save(OUT/'decisions/expand_epoch12.json',dict(expand=expand,jobs=list(selected.items()) if expand else [],selected_lrs=selected,details=details,inputs=inputs,source_sha=sha(__file__)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,choices=[2,6],required=True);main(p.parse_args().epoch)
