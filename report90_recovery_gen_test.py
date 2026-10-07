"""첫 행 저장 뒤 실제 SIGKILL·torn tail 복구·sealed output 변조 거부 검사."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import copy
from report86_common import save,sha,sha_obj,record_digest
from report90_numeric import OUT
import report90_recovery_gen as S

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);a=p.parse_args();assert a.gpu in os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    root=OUT/'recovery/tests/gen_resume';root.mkdir(parents=True,exist_ok=False)
    allreq=json.loads((OUT/'tech/requests_D8.json').read_text());requests=[allreq[1],allreq[3]]
    req=root/'requests.json';save(req,requests);out=root/'run';out.mkdir()
    proto=S.protocol(req,None);save(out/'protocol.json',proto);save(out/'mapping.json',dict(workers=1))
    mem=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],text=True)
    assert int(next(x.split(',')[-1] for x in mem.splitlines() if x.split(',')[0].strip()==a.gpu))>=14048
    save(root/'admission.json',dict(nvidia_smi=mem,gpu=a.gpu,required_mib=14048))
    cmd=[sys.executable,'report90_recovery_gen.py','worker','--gpu',a.gpu,'--requests',str(req),'--out',str(out),'--workers','1','--shard','0']
    start=time.monotonic();target=out/'worker_0.jsonl'
    with (root/'interrupted.stdout.log').open('x') as so,(root/'interrupted.stderr.log').open('x') as se:
        proc=subprocess.Popen(cmd,stdout=so,stderr=se)
        try:
            while proc.poll() is None:
                if target.exists() and target.read_bytes().count(b'\n')>=1:break
                time.sleep(.1)
            assert proc.poll() is None,'worker finished before interruption'
            proc.kill();rc=proc.wait();assert rc==-9
        finally:
            if proc.poll() is None:proc.terminate();proc.wait()
    prefix=target.read_bytes();assert len(prefix.splitlines())==1
    with target.open('ab') as f:f.write(b'{"interrupted":')
    started=time.monotonic()
    cmd=[sys.executable,'report90_recovery_gen.py','launch','--requests',str(req),'--out',str(out),'--workers','1']
    with (root/'resume.stdout.log').open('x') as so,(root/'resume.stderr.log').open('x') as se:
        rc=subprocess.run(cmd,stdout=so,stderr=se).returncode
    assert rc==0
    records,expected=S.verify(out,req,proto,1);assert len(records)==2 and target.read_bytes().startswith(prefix)
    # 기존 두-worker 출력은 immutable scientific protocol·행 digest를 별도 확인한다.
    oldroot=OUT/'tech/gen2';oldproto=json.loads((oldroot/'protocol.json').read_text())
    for path,digest in oldproto['code'].items():assert sha(path)==digest
    old={r['id']:r for r in map(json.loads,(oldroot/'worker_1.jsonl').read_text().splitlines())}
    matches=[]
    for rec in records:
        prior=old[rec['id']];assert prior['record_digest']==record_digest(prior) and prior['protocol_digest']==sha_obj(oldproto)
        request=next(r for r in requests if r['id']==rec['id']);assert prior['request_digest']==sha_obj(request)
        matches.append(rec['attempts'][-1]['suffix_ids']==prior['attempts'][-1]['suffix_ids'] and rec['input_ids']==prior['input_ids'])
    checks=[]
    for name,mutation in [('record_tamper','text'),('duplicate','duplicate'),('missing','missing')]:
        dest=root/name;dest.mkdir();rows=copy.deepcopy(records)
        if mutation=='text':rows[0]['text']+=' changed'
        elif mutation=='duplicate':rows.append(rows[0])
        else:rows.pop()
        file=dest/'worker_0.jsonl';file.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        # 별도 검사 경로에서도 원래 예상 개수를 유지해 실제 입력 검증의 변조 거부를 확인한다.
        save(dest/'completion.json',dict(n=2,protocol_digest=sha_obj(proto),files={str(file):sha(file)}))
        try:S.verify(dest,req,proto,1)
        except (AssertionError,ValueError) as e:checks.append(dict(name=name,rejected=True,error=repr(e)))
        else:checks.append(dict(name=name,rejected=False))
    result=dict(passed=all(matches) and all(c['rejected'] for c in checks),token_matches=matches,prefix_preserved=True,
        sigkill_rc=-9,resume_rc=rc,checks=checks,wall_s=time.monotonic()-start,resume_wall_s=time.monotonic()-started,
        source_sha256=sha(__file__),completion_sha256=sha(out/'completion.json'),baseline_sha256=sha(oldroot/'worker_1.jsonl'))
    save(root/'result.json',result);print(json.dumps(result),flush=True)
    raise SystemExit(0 if result['passed'] else 2)

if __name__=='__main__':main()
