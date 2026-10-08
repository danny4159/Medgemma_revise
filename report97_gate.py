"""iter_097 본학습 진입 gate: iter_090 불변 증거(hash 재확인) + 이번 LR2e-5 경로의 동작 확인 + reference 사례표 고정."""
import json
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

def main():
    inherited=json.loads((ORIGINAL/'recovery/training_gate.json').read_text());assert inherited['passed']
    for p,h in inherited['evidence'].items():assert sha(p)==h,p
    resume=OUT/'tests/resume/result.json';r=json.loads(resume.read_text());assert r['passed'] and r['lr']==2e-5
    table=OUT/'reference/case_table_v2.json';t=json.loads(table.read_text());assert all(t['contrast_fixtures'].values()) and t['n_recall_patients']==20
    evidence={str(resume):sha(resume),str(table):sha(table),str(ORIGINAL/'recovery/training_gate.json'):sha(ORIGINAL/'recovery/training_gate.json')}
    evidence.update(inherited['evidence'])
    for p in ['report97_train.py','report90_train.py','report90_stable_v2.py','report90_stable.py','report90_numeric.py','report89_model.py',
              'rsna_diag/lora.py','rsna_diag/sft_data.py','rsna_diag/train.py']:evidence[p]=sha(p)
    save(OUT/'training_gate.json',dict(passed=True,evidence=evidence,chosen_mb=1,lr=2e-5,source_sha=sha(__file__),
        inherited=str(ORIGINAL/'recovery/training_gate.json'),inherited_sha=sha(ORIGINAL/'recovery/training_gate.json'),
        reason='수치 경로·자료·mb1은 iter_090 recovery gate의 불변 증거를 hash로 계승. 이번 변경(LR2e-5, 결과/cache 경로)의 재개·optimizer LR·R 모드 loss는 tests/resume에서 재검증.'))
    print('gate saved')

if __name__=='__main__':main()
