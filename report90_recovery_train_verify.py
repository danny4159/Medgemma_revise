"""수정 경로 완료 검증: 기존 수치·노출 검사에 실제 config/source 연결을 더한다."""
import argparse
import json
from pathlib import Path
import torch
import report90_train_verify as C
from report90_numeric import OUT
from report86_common import sha,sha_obj
from rsna_diag.lora import state_digest

def main(run,epoch):
    run=Path(run);cfg=json.loads((run/'config.json').read_text());comp=json.loads((run/f'complete_{epoch:02}.json').read_text())
    assert sha_obj(cfg)==comp['config_digest']
    for p,h in cfg['code'].items():assert sha(p)==h,p
    assert cfg['train_sha']==sha(OUT/'data/T512/manifest.json') and cfg['val_sha']==sha(OUT/'data/V64/manifest.json')
    ckfile=run/f'checkpoint_{epoch*64:06}.pt';assert sha(ckfile)==comp['checkpoint_sha']
    ck=torch.load(ckfile,map_location='cpu',weights_only=False)
    assert state_digest(ck['adapter'])==ck['digests']['adapter']
    events=[json.loads(l) for f in sorted(run.glob('events_*.jsonl')) for l in f.read_text().splitlines()]
    event=next(x for x in events if x['step']==epoch*64);assert event['digests']==ck['digests']
    original_save=C.save
    C.save=lambda p,d:original_save(p,dict(d,current_source_and_inputs=True,adapter_digest_checked=True,wrapper_sha=sha(__file__)))
    C.main(run,epoch)
    print('PASS',run.name,epoch)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--epoch',type=int,required=True);a=p.parse_args();main(a.run,a.epoch)
