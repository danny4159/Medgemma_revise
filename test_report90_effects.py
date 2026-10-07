"""수작업 기대값으로 층·모순 비용·회복 분산 조건을 확인한다."""
from copy import deepcopy
from report90_effects import compare
from report90_numeric import OUT
from report86_common import save,sha

def main():
    rows=[];definite=set()
    for condition in ['R','G']:
        for i in range(8):
            abnormal=i<6;ref=f'A{i}';definite.add(ref)
            hit=condition=='G' and i<5
            rows.append(dict(patient=str(i),condition=condition,abnormal=abnormal,
                strict_recall=float(hit) if abnormal else None,type_recall=float(hit) if abnormal else None,
                possible_only=0. if abnormal else None,no_ambiguous_reference=float(hit) if abnormal else None,
                no_ambiguous_match=float(hit) if abnormal else None,contradiction=False,internal_contradiction=False,
                non_eos=False,format_failure=False,matches=[dict(ref=ref,status='strict')] if hit else []))
    good=compare(rows,'G','R',definite)
    assert abs(good['metrics']['strict_recall_abnormal']['difference']-5/6)<1e-12
    assert abs(good['leave_one_out_min']-.8)<1e-12 and good['all_criteria_met']
    bad=deepcopy(rows);next(r for r in bad if r['condition']=='G' and r['patient']=='7')['contradiction']=True
    cost=compare(bad,'G','R',definite)
    assert cost['metrics']['contradiction_all']['difference']==1/8
    assert cost['metrics']['contradiction_abnormal']['difference']==0 and not cost['all_criteria_met']
    same=compare(rows,'R','R',definite)
    assert same['metrics']['strict_recall_abnormal']['ci95']==[0.,0.]
    assert same['metrics']['strict_recall_abnormal']['observed_zero_variation'] and not same['all_criteria_met']
    save(OUT/'tests/effects_fixtures.json',dict(passed=True,strict_expected=5/6,loo_expected=.8,cost_expected=1/8,
        all_strata_cost_rejected=True,zero_variation_reported=True,sources={p:sha(p) for p in [__file__,'report90_effects.py']}))
    print('PASS stratified effects, cost guardrail, LOO, observed degenerate interval')

if __name__=='__main__':main()
