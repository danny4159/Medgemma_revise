"""iter_097 LR2e-5 경로의 동작 확인: 연속/중간step/epoch 경계 재개 대조 + R 모드 1 update.
기술 checkpoint는 results/iter_097/tests에만 두며 본학습에 섞지 않는다."""
import argparse
import json
import subprocess
import sys
import time
import torch
from report86_common import save,sha
from report97_train import OUT,ORIGINAL,LR

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);a=p.parse_args()
    root=OUT/'tests/resume';root.mkdir(parents=True,exist_ok=True);runs=[]
    def cmd_for(name,mode):
        return [sys.executable,'report97_train.py','--gpu',a.gpu,'--run-dir',str(root/name),'--train',str(ORIGINAL/'data/T512/manifest.json'),
            '--validation',str(ORIGINAL/'data/D8/manifest.json'),'--mode',mode,'--lr',str(LR),'--epochs','2','--test-patients','16']
    plan=[('ref','G',[('full',[],0)]),('middle','G',[('stop',['--stop-step','1'],75),('resume',[],0)]),
          ('epoch','G',[('stop',['--stop-step','2'],75),('resume',[],0)]),('rmode','R',[('stop',['--stop-step','1'],75)])]
    for name,mode,phases in plan:
        cmd=cmd_for(name,mode)
        for phase,extra,want in phases:
            record=root/f'attempt_{name}_{phase}.json'
            if record.exists():
                old=json.loads(record.read_text());assert old['command']==cmd+extra and old['rc']==want;runs.append(old);continue
            t=time.monotonic()
            with (root/f'{name}_{phase}.stdout.log').open('x') as so,(root/f'{name}_{phase}.stderr.log').open('x') as se:
                rc=subprocess.run(cmd+extra,stdout=so,stderr=se).returncode
            item=dict(name=name,phase=phase,rc=rc,wall_s=time.monotonic()-t,command=cmd+extra);runs.append(item);save(record,item);assert rc==want,(name,phase,rc)
        print(json.dumps(dict(completed=name)),flush=True)
    def read(name,step):
        d=root/name;ck=torch.load(d/f'checkpoint_{step:06}.pt',map_location='cpu',weights_only=False)
        rows=[json.loads(x) for f in sorted(d.glob('events_*.jsonl')) for x in f.read_text().splitlines()]
        return ck,rows
    base,expected=read('ref',4);checks=[]
    for name in ['middle','epoch']:
        ck,rows=read(name,4);assert len(rows)==len(expected)==4
        aligned=all(all(x[k]==y[k] for k in ('step','epoch','pos','ids','loss','report_nll','ground_nll','grad_norm','digests')) for x,y in zip(expected,rows))
        preserved=all(json.loads((root/name/f'validation_{e:02}.json').read_text())['state_preserved'] for e in (1,2))
        state=ck['digests']==base['digests'] and ck['epoch']==base['epoch'] and ck['pos']==base['pos']
        checks.append(dict(name=name,passed=aligned and preserved and state,events_equal=aligned,state_equal=state,validation_preserved=preserved))
    lr_ok=all(g['lr']==LR for g in base['optimizer']['param_groups'])
    cfg=json.loads((root/'ref/config.json').read_text());lr_ok=lr_ok and cfg['lr']==LR and cfg['mb']==1
    rck,rrows=read('rmode',1)
    r_ok=len(rrows)==1 and abs(rrows[0]['loss']-rrows[0]['report_nll'])<1e-9 and rrows[0]['ground_nll']==rrows[0]['ground_nll'] and all(g['lr']==LR for g in rck['optimizer']['param_groups'])
    checks.append(dict(name='lr_and_config',passed=lr_ok));checks.append(dict(name='R_mode_loss_is_report_only',passed=r_ok,event=rrows[0]))
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,attempts=runs,technical_optimizer_updates=13,lr=LR,source_sha=sha(__file__))
    save(root/'result.json',result);print(json.dumps(result)[:800],flush=True);return 0 if result['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
