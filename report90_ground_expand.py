"""사전 OR 조건의 grounding 분기로 확대한다. 남은 V32 평가 의무는 유지한다."""
import json
from pathlib import Path
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
OUT=ORIGINAL/'recovery'

def main():
    inputs={}
    def read(p):
        p=Path(p);inputs[str(p)]=sha(p);return json.loads(p.read_text())
    read(OUT/'stage_decision_rules.json')
    base=read(ORIGINAL/'validation/base_ground_eval.json')['scores']['0.3']
    jobs=[(m,lr) for lr in (.0001,.0002) for m in ('R','G')];details=[]
    for m,lr in jobs:
        name=f'{m}_lr{lr:g}';run=OUT/'train'/name
        v=read(run/'verified_02.json');assert v['passed']
        complete=read(run/'complete_02.json');assert sha(run/'checkpoint_000128.pt')==complete['checkpoint_sha']
        result=read(OUT/f'validation/epoch2/{name}_ground_eval.json')
        stage=OUT/f'validation/epoch2/{name}_ground'
        import report90_recovery_gen as S
        proto=read(stage/'protocol.json');rows,expected=S.verify(stage,ORIGINAL/'data/V16/requests.json',proto,1)
        assert len(rows)==len(expected)==16 and (stage/'completion.json').exists()
        inputs[str(stage/'completion.json')]=sha(stage/'completion.json')
        score=result['scores']['0.3']
        details.append(dict(mode=m,lr=lr,grounding_f1=score,branches=dict(grounding=m=='G' and score>base)))
    assert any(d['branches']['grounding'] for d in details)
    save(OUT/'decisions/expand_epoch6.json',dict(expand=True,jobs=jobs,details=details,inputs=inputs,source_sha=sha(__file__),
        basis='원 계획 OR 조건 중 G grounding 개선 충족',base_grounding_f1=base,
        semantic_V32_pending=True,obligation='epoch2 V32 160개 판독 의미 평가·독립 검증을 완료하며 확대 이후에도 생략하지 않음',
        scheduling='남은 epoch2 생성과 신규 학습의 실제 점유를 확인해 빈 GPU부터 시작; 요청·가설·문턱 변경 없음'))
    print('epoch6 authorized by prespecified grounding OR branch; V32 semantic evaluation remains required')

if __name__=='__main__':main()
