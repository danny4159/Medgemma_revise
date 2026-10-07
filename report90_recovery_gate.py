"""불변 자료 검사는 계승하고 수치 경로·재개·생성 변경 근거를 새로 연결한다."""
import json
from report90_numeric import OUT
from report86_common import save,sha

def main():
    historical=json.loads((OUT/'training_gate.json').read_text())
    for p,h in historical['evidence'].items():assert sha(p)==h
    required=['tests/target_fixtures_v2.json','data/selection_verify.json','data/pixel_check.json',
        'tech/trained_G_e2_v2_forward/result.json','tech/trained_G_e2_v2_gradient/result.json',
        'tech/recovery_training_gate/result.json','recovery/tech/regression_batch/result.json',
        'recovery/tests/resume/result.json','recovery/tests/gen_resume/result.json','tests/runtime_tamper/result.json']
    evidence={}
    for rel in required:
        p=OUT/rel;d=json.loads(p.read_text());assert d['passed'],rel;evidence[str(p)]=sha(p)
    batch=json.loads((OUT/'recovery/tech/regression_batch/result.json').read_text());assert batch['chosen_mb']==1
    for p in [OUT/'data/selection_lock.json',OUT/'data/D8/visual_review.json',OUT/'recovery/amendment.json',
              OUT/'validation/base_nll.json',OUT/'recovery/tech/regression_batch/protocol.json',
              OUT/'tech/recovery_training_gate/protocol.json',OUT/'tech/trained_G_e2_v2_forward/trained_protocol.json']:
        evidence[str(p)]=sha(p)
    for p in ['report90_recovery_train.py','report90_stable_v2.py','report90_recovery_gen.py','report90_recovery_launch.py']:
        evidence[p]=sha(p)
    save(OUT/'recovery/training_gate.json',dict(passed=True,evidence=evidence,chosen_mb=1,source_sha=sha(__file__),
        scope='새 base 초기화 epoch2 네 trajectory 진입. 종전266 updates는 수치 gate 실패로 성능 비교에서 제외.',
        inherited=str(OUT/'training_gate.json'),inherited_sha=sha(OUT/'training_gate.json'),
        reason='불변 자료·입력·생성 상태 검사는 계승. 비영 LoRA와 초기 CE/gradient/update, 실제 재개·생성 연결은 수정 경로에서 재검증.'))

if __name__=='__main__':main()
