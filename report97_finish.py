"""iter_097 분기 결정 기록과 산출물 봉인. 사전 기준(plan.md)을 바꾸지 않고 저장된 판정/검증만 읽는다."""
import json
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

def main():
    dec=json.loads((OUT/'decisions/R_vs_comparators_epoch6.json').read_text());ver=json.loads((OUT/'decisions/verify.json').read_text());assert ver['passed']
    sens=json.loads((OUT/'decisions/R_vs_comparators_epoch6_sensitivity_inherited.json').read_text())
    nll=lambda p:[json.loads((p/f'validation_{e:02}.json').read_text())['report_nll'] for e in (1,2,4,6)]
    e2=json.loads((OUT/'semantic/epoch2/eval/report.json').read_text())['conditions']['R_lr2e-05_report']
    e6=json.loads((OUT/'semantic/epoch6/eval/report.json').read_text())['conditions']
    ground={n:json.loads(Path_(p).read_text()) for n,p in dict(R2e5=OUT/'validation/epoch6/R_lr2e-05_ground_eval.json',base=ORIGINAL/'validation/base_ground_eval.json',
        R1e4=ORIGINAL/'recovery/validation/epoch6/R_lr0.0001_ground_eval.json',R2e4=ORIGINAL/'recovery/validation/epoch6/R_lr0.0002_ground_eval.json').items()}
    out=dict(
        branch=dict(r_passes_possibility_criterion=dec['r_passes_possibility_criterion'],g_executed=False,
            reason='R(LR2e-5) 가능성 기준 미충족 -> 사전 분기에 따라 G 미실행. 판정은 조건명 가림 재판정 기준이며 상속 판정 민감도에서도 동일(net>=3 미충족).',
            per_comparator={k:dict(diff=v['diff'],ci95=v['ci95'],increased=v['increased'],decreased=v['decreased'],net=v['net'],loo_min=v['loo_min'],checks=v['checks']) for k,v in dec['results'].items()},
            sensitivity_inherited={k:dict(diff=v['diff'],net=v['net'],checks=v['checks']) for k,v in sens['results'].items()}),
        trend=dict(nll_R_lr2e5={'epoch1,2,4,6':nll(OUT/'train/R_lr2e-05')},nll_R_lr1e4={'epoch1,2,4,6':nll(ORIGINAL/'recovery/train/R_lr0.0001')},nll_R_lr2e4={'epoch1,2,4,6':nll(ORIGINAL/'recovery/train/R_lr0.0002')},
            nll_base=json.loads((ORIGINAL/'validation/base_nll.json').read_text())['report_nll'],
            strict_recall_R_lr2e5_epoch2=e2['strict_recall'],strict_recall_R_lr2e5_epoch6=e6['R_lr2e-05_report']['strict_recall']),
        ground_V16_f1_0p3={k:v['scores']['0.3'] for k,v in ground.items()},ground_V16_invalid={k:v['invalid'] for k,v in ground.items()},
        epoch6_conditions={k:{a:b for a,b in v.items() if a in ('strict_recall','type_recall','no_ambiguous_match','contradiction','contradiction_abnormal','non_eos')} for k,v in e6.items()},
        verify_passed=ver['passed'],
        files={str(p.relative_to(OUT)):sha(p) for p in [OUT/'training_gate.json',OUT/'tests/resume/result.json',OUT/'tests/gen/result.json',OUT/'reference/case_table_v2.json',
            OUT/'train/R_lr2e-05/complete_06.json',OUT/'train/R_lr2e-05/verified_06.json',OUT/'semantic/epoch2/eval/report.json',OUT/'semantic/epoch6/eval/report.json',OUT/'semantic/epoch6/eval/per_output.json',
            OUT/'decisions/R_vs_comparators_epoch6.json',OUT/'decisions/R_vs_comparators_epoch6_sensitivity_inherited.json',OUT/'decisions/rejudge_agreement.json',OUT/'decisions/verify.json']},
        source_sha=sha(__file__))
    save(OUT/'decisions/branch_decision.json',out);print(json.dumps(out['branch']['per_comparator'],indent=1)[:1500])

def Path_(p):
    from pathlib import Path
    return Path(p)

if __name__=='__main__':main()
