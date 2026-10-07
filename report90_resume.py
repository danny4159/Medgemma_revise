"""실제 trainer의 중간/epoch 경계 중단·재개를 연속 실행과 비교한다."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import torch
from report90_numeric import OUT
from report86_common import save,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);a=p.parse_args();root=OUT/'tests/resume'
    ref=root/'ref';assert (ref/'complete_02.json').exists()
    baseline=torch.load(ref/'checkpoint_000004.pt',map_location='cpu',weights_only=False)
    expected=[json.loads(x) for f in sorted(ref.glob('events_*.jsonl')) for x in f.read_text().splitlines()]
    results=[]
    for name,stop in [('middle',1),('epoch',2)]:
        out=root/name
        cmd=[sys.executable,'report90_train.py','--gpu',a.gpu,'--run-dir',str(out),'--train',str(OUT/'data/T512/manifest.json'),
            '--validation',str(OUT/'data/D8/manifest.json'),'--mode','G','--lr','0.0001','--epochs','2','--test-patients','16']
        attempts=[]
        for phase,extra,expected_rc in [('stop',['--stop-step',str(stop)],75),('resume',[],0)]:
            started=time.monotonic()
            with (root/f'{name}_{phase}.stdout.log').open('x') as so,(root/f'{name}_{phase}.stderr.log').open('x') as se:
                rc=subprocess.run(cmd+extra,stdout=so,stderr=se).returncode
            attempts.append(dict(phase=phase,rc=rc,wall_s=time.monotonic()-started,command=cmd+extra));assert rc==expected_rc
        ck=torch.load(out/'checkpoint_000004.pt',map_location='cpu',weights_only=False)
        events=[json.loads(x) for f in sorted(out.glob('events_*.jsonl')) for x in f.read_text().splitlines()]
        assert len(events)==len(expected)==4
        aligned=all(all(x[k]==y[k] for k in ('step','epoch','pos','ids','loss','report_nll','ground_nll','grad_norm','digests')) for x,y in zip(events,expected))
        state=ck['digests']==baseline['digests'] and ck['epoch']==baseline['epoch'] and ck['pos']==baseline['pos']
        validation=all(json.loads((out/f'validation_{e:02}.json').read_text())['state_preserved'] for e in (1,2))
        result=dict(name=name,passed=aligned and state and validation,events_equal=aligned,final_adapter_optimizer_rng_equal=state,validation_state_preserved=validation,attempts=attempts,
            final_checkpoint_sha=sha(out/'checkpoint_000004.pt'))
        results.append(result);save(root/f'{name}_comparison.json',result);print(json.dumps(result),flush=True)
    save(root/'result.json',dict(passed=all(r['passed'] for r in results),comparisons=results,source_sha256=sha(__file__),
        reference_checkpoint_sha=sha(ref/'checkpoint_000004.pt'),technical_optimizer_steps=12,main_training_updates=0))
    raise SystemExit(0 if all(r['passed'] for r in results) else 2)

if __name__=='__main__':main()
