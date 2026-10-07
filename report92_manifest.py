"""iter_092 인계 manifest: iter_090 recovery 경로의 신규 attempt·산출물과 digest를 새 경로에 연결한다."""
import json
from pathlib import Path
from report86_common import save,sha
R=Path('results/iter_090/recovery');N=Path('results/iter_092')

def main():
    files={}
    for p in [R/'selection/final.json',R/'decisions/expand_epoch6.json',R/'decisions/expand_epoch6_semantic_confirmation.json',R/'decisions/expand_epoch12.json',R/'stage_decision_rules.json',
              R/'launch/epoch6/result_002.json',R/'validation/epoch6/queue_result_000.json',R/'semantic/epoch6/eval/report.json',R/'semantic/epoch6/eval/verification.json',
              R/'data/E128/manifest.json',R/'data/E128/completion.json',R/'semantic/E_definitions.json',R/'semantic/E_reference.json',R/'final_generation/contract.json',R/'final_generation/result_000.json',
              R/'semantic/E/eval/report.json',R/'semantic/E_recheck/notes.json',R/'semantic/E_adjudicated/eval/report.json',R/'semantic/E_adjudicated/eval/verification.json',
              N/'effects_E128.json',N/'effects_E128_verify.json',N/'ground_E32/R_ground_eval.json',N/'ground_E32/G_ground_eval.json']:
        files[str(p)]=sha(p)
    runs={}
    for name in ['R_lr0.0001','G_lr0.0001','R_lr0.0002','G_lr0.0002']:
        d=R/'train'/name;ev=[json.loads(l) for f in sorted(d.glob('events_*.jsonl')) for l in f.read_text().splitlines()]
        steps=sorted({e['step'] for e in ev});runs[name]=dict(final_step=steps[-1],unique_event_steps=len(steps),attempts=len(list(d.glob('attempt_*.json'))),
            complete_06=sha(d/'complete_06.json'),validation_nll={e:json.loads((d/f'validation_{e:02}.json').read_text())['report_nll'] for e in (1,2,4,6)})
    save(N/'handoff_manifest.json',dict(base_plan='agent/runs/iter_092/plan.md',resumed_from=dict(R_lr0001=305,G_lr0001=285,R_lr0002=128,G_lr0002=128),
        updates_added=dict(R_lr0001=384-305,G_lr0001=384-285,R_lr0002=384-128,G_lr0002=384-128),runs=runs,files=files,
        superseded_not_deleted=['results/iter_090/recovery/semantic/epoch6/eval_superseded_relative_paths','results/iter_090/recovery/semantic/E/judgments_superseded_duplicate_match',
                                'results/iter_090/recovery/semantic/E/judgments_superseded_cardiomegaly_negation'],
        scope='iter_090 원 계획의 epoch6 완료·확대 판정·E128 평가 이관 기록. 새 가설·기준 변경 없음.'))
    print('manifest',len(files),'files')

if __name__=='__main__':main()
