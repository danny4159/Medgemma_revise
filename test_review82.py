"""순위·표본·저장 실패 경로를 포함한 iter_082 fixture."""
import copy
from pathlib import Path
import tempfile
import numpy as np
import review82_analysis as a
from sp75_metrics import abs_err,class_std_mae


def main():
    checks={}
    def check(name,condition):
        checks[name]=bool(condition)
        assert condition,name
    def rejected(fn):
        try: fn()
        except (AssertionError,FileExistsError): return True
        return False
    def row(i,p,c=1,q=1,g=1,patient=None):
        return dict(id=str(i),patient=str(patient or i),probs=p,C=c,Q=q,grade=g,ordinal=1)
    certain=row(1,[1,0,0,0,0]); uncertain=row(2,[.2]*5,q=5,g=5)
    check('zero_probability_finite',all(np.isfinite(list(a.scores(certain).values()))))
    check('risk_direction',all(a.scores(uncertain)[n]>a.scores(certain)[n] for n in a.NAMES))
    check('argmax_tie_first',a.scores(row(3,[.5,.5,0,0,0]))['one_minus_max']==.5)
    check('argmax_mismatch_rejected',rejected(lambda:a.scores(row(3,[.5,.5,0,0,0],c=2))))
    check('invalid_probability_rejected',rejected(lambda:a.scores(row(3,[1.1,-.1,0,0,0]))))
    rr=[row(i,[1,0,0,0,0],g=5 if i<2 else 1) for i in range(1,6)]
    t=a.table(rr,'entropy','entropy',.25)
    check('ceil_5',t['k']==2)
    check('ceil_47',a.table([row(i,[1,0,0,0,0]) for i in range(47)],'entropy','entropy',.25)['k']==12)
    check('boundary_ties',t['e2']['tie_min']==0 and t['e2']['tie_max']==1)
    mutated=copy.deepcopy(rr)
    for r in mutated: r['grade']=6-r['grade']
    check('rank_label_independent',a.rank(rr,'D','entropy')==sorted(rr,key=lambda r:a.key(r,'D','entropy')) and [r['id'] for r in a.rank(rr,'D','entropy')]==[r['id'] for r in a.rank(mutated,'D','entropy')])
    check('E_selection_rejected',rejected(lambda:a.select(rr,'E24')))
    check('zero_event_recall',a.table([certain],'D','entropy',.25)['e2']['recall'] is None)
    check('single_class_metrics',a.discrimination([certain],'D','entropy',2)['auroc'] is None)
    check('perfect_auc_ap',a.discrimination([certain,uncertain],'D','entropy',2)==dict(auroc=1.,average_precision=1.))
    check('invalid_four',abs_err([1],[None])[0]==4)
    check('present_class_mean',class_std_mae([1,1,5],[1,3,1])==(2.5,2))
    copies=[dict(certain,occurrence=2),dict(certain,occurrence=1)]
    check('occurrence_final_key',[r['occurrence'] for r in a.rank(copies,'D','entropy')]==[1,2])
    boot=a.bootstrap([certain,dict(certain,id='other',ordinal=3)],'entropy',n=10)
    check('patient_cluster_duplicates',all(s['n']==2 and s['k']==1 for s in boot['samples']) and boot['undefined_recall']==10)
    with tempfile.TemporaryDirectory(dir='results') as d:
        p=Path(d)/'saved.json'; a.save(p,dict(ok=1))
        check('overwrite_rejected',rejected(lambda:a.save(p,dict(ok=2))))
        check('original_preserved',a.read(p)==dict(ok=1))
    a.save(a.ROOT/'tests.json',dict(passed=all(checks.values()),checks=checks,code={p:a.sha(p) for p in ['review82_analysis.py','review82_verify.py','test_review82.py','sp75_metrics.py']}))
    print(f'{len(checks)}/{len(checks)} PASS')

if __name__=='__main__': main()
