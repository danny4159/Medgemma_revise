"""완료 trajectory의 실제 batch·LR·checkpoint·validation 연결 검증."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import torch
from report90_numeric import OUT
from report90_train import order
from report86_common import save,sha

def main(run,epoch):
    run=Path(run);cfg=json.loads((run/'config.json').read_text());complete=json.loads((run/f'complete_{epoch:02}.json').read_text())
    n=len(cfg['patient_ids']);assert n==512 and cfg['test_patients']==0 and cfg['mb']==1
    expected_steps=epoch*64;assert complete['step']==expected_steps
    checkpoint=run/f'checkpoint_{expected_steps:06}.pt';assert sha(checkpoint)==complete['checkpoint_sha']
    state=torch.load(checkpoint,map_location='cpu',weights_only=False)
    assert state['step']==expected_steps and state['epoch']==epoch and state['pos']==0
    assert state['config_digest']==complete['config_digest']
    for group in state['optimizer']['param_groups']:
        assert group['lr']==cfg['lr'] and group['weight_decay']==.01 and group['eps']==1e-8 and tuple(group['betas'])==(.9,.999)
    events=[json.loads(s) for p in sorted(run.glob('events_*.jsonl')) for s in p.read_text().splitlines()]
    events=[r for r in events if r['step']<=expected_steps];assert [r['step'] for r in events]==list(range(1,expected_steps+1))
    for r in events:
        e,pos=divmod(r['step']-1,64);ids=[cfg['patient_ids'][i] for i in order(17,e,n)[pos*8:pos*8+8]];assert r['ids']==ids
        assert all(math.isfinite(r[k]) for k in ['loss','report_nll','ground_nll','grad_norm'])
        assert abs(r['loss']-r['report_nll']-(r['ground_nll'] if cfg['mode']=='G' else 0))<1e-5
    counts=Counter(p for r in events for p in r['ids']);assert set(counts.values())=={epoch}
    for e in [x for x in (1,2,4,6,8,12) if x<=epoch]:
        val=json.loads((run/f'validation_{e:02}.json').read_text())
        assert val['n']==64 and val['state_preserved'] and math.isfinite(val['report_nll'])
        assert val['config_digest']==complete['config_digest'] and val['checkpoint_sha']==sha(run/f'checkpoint_{e*64:06}.pt')
    save(run/f'verified_{epoch:02}.json',dict(passed=True,updates=len(events),patient_exposures=sum(counts.values()),mode=cfg['mode'],lr=cfg['lr'],
        checkpoint_sha=sha(checkpoint),config_sha=sha(run/'config.json'),completion_sha=sha(run/f'complete_{epoch:02}.json'),source_sha=sha(__file__)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--epoch',type=int,required=True);a=p.parse_args();main(a.run,a.epoch)
