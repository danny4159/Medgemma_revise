"""생성 전에 고정하는 사건·calibration·평가·판정 경계 검증."""
import numpy as np
from mr128_eval import metrics,auroc,calibrate,paired_ci,decision,states
from mr128_data import OUT,save,sha,utc


def main(suffix):
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    y=[1,1,0,0];m=metrics(y,['PRESENT','UNCERTAIN','ABSENT','INVALID'])
    check('uncertain_invalid_denominators',m['BA']==0.5 and m['sensitivity']==0.5 and m['specificity']==0.5 and m['uncertain_n']==1 and m['invalid_n']==1)
    check('truncated_invalid',states('PRESENT',False)==('INVALID','truncated'))
    check('ambiguous_first_line',states('PRESENT or ABSENT',True)[0]=='INVALID')
    check('uncertain_not_correct',metrics([0,1],['UNCERTAIN','UNCERTAIN'])['BA']==0)
    check('auroc_perfect',auroc(y,[4,3,2,1])==1)
    check('auroc_all_ties',auroc(y,[1,1,1,1])==0.5)
    rows=[dict(study_uid=str(i),role='calib',label='positive' if a else 'negative',S=float(b)) for i,(a,b) in enumerate(zip(y,[4,3,2,1]))]
    c=calibrate(rows)
    check('calibration_midpoint_operator',c['chosen']['threshold']==2.5 and c['operator']=='>=' and c['chosen']['BA']==1)
    ties=[dict(r,S=1.0) for r in rows];c=calibrate(ties)
    check('calibration_tie_specificity_larger_threshold',c['chosen']['specificity']==1 and c['chosen']['threshold']>1)
    try:calibrate([dict(rows[0],role='explore')]+rows[1:])
    except ValueError:check('explore_calibration_rejected',True)
    else:check('explore_calibration_rejected',False)
    rs=[dict(batch_id='b'+str(i%2),label='positive' if a else 'negative',A='PRESENT' if a else 'ABSENT',U='ABSENT' if a else 'PRESENT') for i,a in enumerate(y)]
    ci=paired_ci(rs,'A','U');check('paired_all_correct_vs_wrong',ci['mean']==1 and ci['CI95']==[1,1])
    rs=[dict(r,U=r['A']) for r in rs];ci=paired_ci(rs,'A','U');check('paired_identical_degenerate',ci['mean']==0 and ci['CI95']==[0,0])
    U=dict(BA=0.60,sensitivity=0.60,specificity=0.60);A=dict(BA=0.75,sensitivity=0.65,specificity=0.85)
    delta=dict(mean=0.15,CI95=[0.001,0.3]);d=decision(U,A,None,delta,False,2,1)
    check('positive_exact_boundaries',d['positive_sampling_observation'])
    check('CI_zero_fails_positive',not decision(U,A,None,dict(mean=0.15,CI95=[0,0.3]),False,2,1)['positive_sampling_observation'])
    check('both_BA_060_negative',decision(U,U,None,dict(mean=0,CI95=[0,0]),False,2,1)['negative_frozen_design'])
    S=dict(BA=0.80,sensitivity=0.8,specificity=0.8)
    check('simple_sufficient',decision(U,A,S,delta,True,2,1)['simple_alternative_sufficient'])
    check('missing_S_no_sufficiency',not decision(U,A,S,delta,False,2,1)['simple_alternative_sufficient'])
    check('unknown_cost_no_sufficiency',not decision(U,A,S,delta,True,None,1)['simple_alternative_sufficient'])
    check('cheaper_A_no_cost_sufficiency',not decision(U,A,S,delta,True,1,2)['simple_alternative_sufficient'])
    A85=dict(BA=0.85,sensitivity=0.85,specificity=0.85,BA_fraction=[17,20]);S80=dict(S,BA_fraction=[4,5])
    check('exact_005_gain_not_insufficient',not decision(U,A85,S80,delta,True,2,1)['simple_alternative_sufficient'])
    A95=dict(BA=0.95,sensitivity=0.95,specificity=0.95,BA_fraction=[19,20])
    check('exact_015_gain_positive',decision(S80,A95,None,dict(mean=0.95-0.80,mean_fraction=[3,20],CI95=[0.01,0.3]),False,2,1)['positive_sampling_observation'])
    ok=all(c['passed'] for c in checks)
    fixtures=OUT/('evaluation_fixtures'+suffix+'.json');lock=OUT/('evaluation_lock'+suffix+'.json')
    save(fixtures,dict(all_pass=ok,checks=checks,created_utc=utc(),
         source_sha256=sha(__file__),evaluation_sha256=sha('mr128_eval.py')))
    save(lock,dict(created_utc=utc(),code={p:sha(p) for p in ['mr128_eval.py','test_mr128_eval.py','mr123_run.py']},
         fixtures_sha256=sha(fixtures),before_any_VLM_generation=True,
         note_ko='현재 기술8명의 segmentation만 실행. VLM 출력은 아직 없음. 판정 코드와 사건을 실제 시점에 잠금.'))
    print('evaluation fixtures',sum(c['passed'] for c in checks),'/',len(checks))
    return 0 if ok else 2


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--suffix',default='_v2');a=ap.parse_args()
    raise SystemExit(main(a.suffix))
