"""기술 근거를 연결한 본학습 진입 판정. 내용 정답률을 gate로 쓰지 않는다."""
import json
from pathlib import Path
from report90_numeric import OUT
from report86_common import sha,save
import report90_gen as G

def main():
    required=['tests/target_fixtures_v2.json','data/selection_verify.json','data/pixel_check.json',
        'tech/stable_training_v2/result.json','tech/regression_batch/result.json',
        'tests/resume/result.json','tests/gen_resume/result.json','tests/runtime_tamper/result.json']
    evidence={}
    for rel in required:
        p=OUT/rel;d=json.loads(p.read_text());assert d['passed'],rel;evidence[str(p)]=sha(p)
    visual=OUT/'data/D8/visual_review.json';d=json.loads(visual.read_text());assert d['geometry_pass'] and d['pixel_checks']==8
    for p,h in d['overlays'].items():assert sha(p)==h
    evidence[str(visual)]=sha(visual)
    out=OUT/'tech/gen2';req=OUT/'tech/requests_D8.json';proto=json.loads((out/'protocol.json').read_text())
    recs,expected=G.verify(out,req,proto,2);assert len(recs)==len(expected)==8
    completion=json.loads((out/'completion.json').read_text());assert completion['n']==8
    for p,h in completion['files'].items():assert sha(p)==h
    for p in [out/'completion.json',req,out/'protocol.json',OUT/'data/selection_lock.json',OUT/'validation/base_nll.json']:
        evidence[str(p)]=sha(p)
    resources=dict(allocated_gib=max(a['peak_mem_alloc_gb'] for r in recs for a in r['attempts']),
        reserved_gib=max(a['peak_mem_reserved_gb'] for r in recs for a in r['attempts']),
        generation_seconds=sum(a['runtime_s'] for r in recs for a in r['attempts']),
        non_eos=sum(not r['attempts'][-1]['ended_eos'] for r in recs),requests=8)
    save(OUT/'training_gate.json',dict(passed=True,evidence=evidence,source_sha=sha(__file__),chosen_mb=1,
        train_workers_per_gpu=1,gen_workers_per_gpu=1,generation=resources,
        reason='원 수치 문턱·입력·동결·재개·상태 보존·생성 provenance 통과. mb2 update 차이로 미채택. 긴 출력 실측상 생성2 worker/GPU의 여유 미충족.',
        scope='epoch2 네 trajectory 진입만 승인; 내용 오답/비EOS는 별도 평가하며 epoch6 자동 확대하지 않음'))

if __name__=='__main__':main()
