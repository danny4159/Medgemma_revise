"""새 결과 경로·허용 GPU·완료 산출물 무결성의 실제 CLI 회귀 검사."""
import json
import os
from pathlib import Path
import subprocess
import sys
from report84_preflight import ROOT, sha, save


def main():
    out = ROOT/'results/iter_085/tests'
    out.mkdir(exist_ok=False)
    checks = []
    old = ROOT/'results/iter_085/D8/M15/completion.json'
    before = sha(old)
    for name,args,expected in [
        ('gpu_outside_allowed',['--gpu','999','--out',str(out/'forbidden_gpu')],'AssertionError'),
        ('existing_output',['--gpu','0','--out',str(old.parent)],'FileExistsError'),
        ('outside_result',['--gpu','0','--out',str(ROOT/'outside_iter085')],'ValueError'),
    ]:
        cmd=[sys.executable,str(ROOT/'report85_d8.py'),'--system','M15']+args
        r=subprocess.run(cmd,capture_output=True,text=True)
        checks.append({'name':name,'pass':r.returncode!=0 and expected in r.stderr,'returncode':r.returncode,'expected_exception':expected})
    checks.append({'name':'existing_completion_preserved','pass':sha(old)==before})
    for name in ['M15','B0','M15_concurrent_a','M15_concurrent_b']:
        d=old.parent.parent/name
        c=json.loads((d/'completion.json').read_text())
        records=[json.loads(s) for s in (d/'outputs.jsonl').read_text().splitlines()]
        checks.append({'name':name+'_sealed_unique_16','pass':all(sha(d/p)==h for p,h in c['files'].items()) and len(records)==len({r['id'] for r in records})==16})
    save(out/'cli_regression.json',{'checks':checks,'pass':all(c['pass'] for c in checks),
         'scope':'경로·허용 GPU·완료 파일 회귀. 중단 재개·E gate·의미 평가 검사를 대신하지 않음'})
    print(json.dumps(checks,ensure_ascii=False))
    return 0 if all(c['pass'] for c in checks) else 1


if __name__=='__main__':
    raise SystemExit(main())
