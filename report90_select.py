"""V만으로 LR와 공통 epoch를 선택·봉인한다. E 내용은 읽지 않는다."""
import json
from pathlib import Path
from report86_common import save,sha
from report90_numeric import OUT as ORIGINAL
OUT=ORIGINAL/'recovery'

def main():
    sources={}
    def read(p):
        p=Path(p);sources[str(p)]=sha(p);return json.loads(p.read_text())
    d6=read(OUT/'decisions/expand_epoch6.json');assert d6['expand']
    if d6.get('semantic_V32_pending'):
        confirmation=read(OUT/'decisions/expand_epoch6_semantic_confirmation.json')
        assert confirmation['expand'] and not confirmation['semantic_V32_pending']
        assert confirmation['previous_decision_sha']==sha(OUT/'decisions/expand_epoch6.json')
        for p,h in confirmation['inputs'].items():assert sha(p)==h
    d12=read(OUT/'decisions/expand_epoch12.json')
    for d in (d6,d12):
        for p,h in d['inputs'].items():assert sha(p)==h
    final_epoch=12 if d12['expand'] else 6
    actual_epochs=[2,6]+([8,12] if final_epoch==12 else [])
    for ep in actual_epochs:
        root=OUT/f'semantic/epoch{ep}/eval'
        v=read(root/'verification.json');assert v['passed'] and not v['differences']
        for p,h in v['sources'].items():assert sha(p)==h
        assert v['sources'][str(root/'per_output.json')]==sha(root/'per_output.json')
    epochs=[1,2,4,6]+([8,12] if final_epoch==12 else [])
    table={};selected={}
    for mode,lr in d12['selected_lrs'].items():
        run=OUT/'train'/f'{mode}_lr{lr:g}'
        verified=read(run/f'verified_{final_epoch:02}.json');assert verified['passed']
        assert verified['config_sha']==sha(run/'config.json') and verified['completion_sha']==sha(run/f'complete_{final_epoch:02}.json')
        completion=read(run/f'complete_{final_epoch:02}.json');table[mode]={}
        for e in epochs:
            value=read(run/f'validation_{e:02}.json')
            assert value['checkpoint_sha']==sha(run/f'checkpoint_{e*64:06}.pt') and value['config_digest']==completion['config_digest']
            assert value['n']==64 and value['state_preserved'];table[mode][e]=value['report_nll']
        selected[mode]=dict(lr=lr,run=str(run))
    assert set(selected)=={'R','G'}
    chosen=min(epochs,key=lambda e:(table['R'][e]+table['G'][e],e))
    for mode,item in selected.items():
        ck=Path(item['run'])/f'checkpoint_{chosen*64:06}.pt'
        item.update(epoch=chosen,updates=chosen*64,checkpoint=str(ck),checkpoint_sha=sha(ck))
    for p in [Path(__file__),ORIGINAL/'semantic/protocol.md',ORIGINAL/'semantic/reference_amendment.json',OUT/'semantic/epoch2/annotation_notes.json',
              ORIGINAL/'semantic/decision_details.json',ORIGINAL/'data/selection_lock.json',
              ORIGINAL/'data/selection.json',Path('report89_model.py').resolve()]:sources[str(p)]=sha(p)
    save(OUT/'selection/final.json',dict(passed=True,selected=selected,validation_nll=table,
        common_epoch=chosen,final_trained_epoch=final_epoch,sources=sources,
        rule='조건별 LR=epoch6 V64 NLL 최소, 공통 epoch=선택한 두 LR의 V64 NLL 합 최소; 동률 이른 epoch',
        E_opened=False,reference_before_E_generation=True))
    print('선택 봉인',chosen,selected)

if __name__=='__main__':main()
