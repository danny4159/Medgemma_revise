"""한 backend만 import하여 E 생성의 protocol·완료 봉인을 검사한다."""
import argparse
import json
from pathlib import Path
from report86_common import save,sha

def main(a):
    if a.backend=='cure':import report90_cure as module
    else:import report90_recovery_gen as module
    safe=module.S if a.backend=='cure' else module
    stage=Path(a.stage).resolve();requests=Path(a.requests).resolve()
    proto=json.loads((stage/'protocol.json').read_text());workers=json.loads((stage/'mapping.json').read_text())['workers']
    rows,expected=safe.verify(stage,requests,proto,workers)
    assert (stage/'completion.json').exists() and len(rows)==len(expected)==a.n
    result=dict(passed=True,n=len(rows),backend=a.backend,non_eos=sum(not r['attempts'][-1]['ended_eos'] for r in rows),
        attempts=sum(len(r['attempts']) for r in rows),
        sources={str(p):sha(p) for p in [requests,stage/'protocol.json',stage/'mapping.json',stage/'completion.json',
            *sorted(stage.glob('worker_*.jsonl')),Path(__file__)]})
    save(a.output,result);print('PASS final generation',a.backend,a.n)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=['med','cure'],required=True);p.add_argument('--stage',required=True)
    p.add_argument('--requests',required=True);p.add_argument('--n',type=int,choices=[32,128],required=True);p.add_argument('--output',required=True);main(p.parse_args())
