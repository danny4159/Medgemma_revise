"""수정 수치 경로의 실제 연속·중간·epoch 재개 대조."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
import torch
from report86_common import save,sha
from report90_numeric import OUT

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);a=p.parse_args()
    root=OUT/'recovery/tests/resume';root.mkdir(parents=True,exist_ok=True);runs=[]
    for name,phases in [('ref',[('full',[],0)]),('middle',[('stop',['--stop-step','1'],75),('resume',[],0)]),('epoch',[('stop',['--stop-step','2'],75),('resume',[],0)])]:
        cmd=[sys.executable,'report90_recovery_train.py','--gpu',a.gpu,'--run-dir',str(root/name),'--train',str(OUT/'data/T512/manifest.json'),
             '--validation',str(OUT/'data/D8/manifest.json'),'--mode','G','--lr','0.0001','--epochs','2','--test-patients','16']
        for phase,extra,want in phases:
            record=root/f'attempt_{name}_{phase}.json'
            if record.exists():
                old=json.loads(record.read_text());assert old['command']==cmd+extra and old['rc']==want;runs.append(old);continue
            # v1 기록 실패 전 완료된 두 phase만 checkpoint와 기존 stdout으로 인계한다.
            inherited=(name,phase) in [('ref','full'),('middle','stop')] and (root/'harness_issue.json').exists()
            if inherited:
                d=root/name;step=4 if name=='ref' else 1;ck=d/f'checkpoint_{step:06}.pt';marker=json.loads(ck.with_suffix('.json').read_text());assert sha(ck)==marker['sha256']
                if name=='ref':assert json.loads((d/'complete_02.json').read_text())['step']==4
                else:assert marker['step']==1 and not (d/'complete_02.json').exists()
                old=dict(name=name,phase=phase,rc=want,command=cmd+extra,inherited=True,checkpoint_sha=sha(ck),scope='기존 trainer checkpoint/완료 파일로 확인; v1 harness가 phase 기록 전에 실패')
                save(record,old);runs.append(old);continue
            t=time.monotonic()
            with (root/f'{name}_{phase}.stdout.log').open('x') as so,(root/f'{name}_{phase}.stderr.log').open('x') as se:
                rc=subprocess.run(cmd+extra,stdout=so,stderr=se).returncode
            item=dict(name=name,phase=phase,rc=rc,wall_s=time.monotonic()-t,command=cmd+extra);runs.append(item);save(record,item);assert rc==want
        print(json.dumps(dict(completed=name)),flush=True)
    def read(name):
        d=root/name;ck=torch.load(d/'checkpoint_000004.pt',map_location='cpu',weights_only=False)
        rows=[json.loads(x) for f in sorted(d.glob('events_*.jsonl')) for x in f.read_text().splitlines()]
        return ck,rows
    base,expected=read('ref');checks=[]
    for name in ['middle','epoch']:
        ck,rows=read(name);assert len(rows)==len(expected)==4
        aligned=all(all(x[k]==y[k] for k in ('step','epoch','pos','ids','loss','report_nll','ground_nll','grad_norm','digests')) for x,y in zip(expected,rows))
        preserved=all(json.loads((root/name/f'validation_{e:02}.json').read_text())['state_preserved'] for e in (1,2))
        state=ck['digests']==base['digests'] and ck['epoch']==base['epoch'] and ck['pos']==base['pos']
        checks.append(dict(name=name,passed=aligned and preserved and state,events_equal=aligned,state_equal=state,validation_preserved=preserved))
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,attempts=runs,technical_optimizer_updates=12,source_sha=sha(__file__))
    save(root/'result.json',result);print(json.dumps(result),flush=True);return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
