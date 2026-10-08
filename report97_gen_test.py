"""iter_097 실제 생성 경로 검사: base V32 32건을 중단(limit)→재개로 생성하고 iter_090 기존 base 출력과 token 단위로 대조.
요청 변조·완료 후 재실행·protocol 불일치 거부도 확인한다. 학습 중인 GPU와 겹치지 않게 GPU 하나만 지정한다."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from report86_common import save,sha,read_jsonl_complete
from report97_train import OUT,ORIGINAL

def run(args,gpu,log):
    env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=gpu
    with open(log+'.out','x') as so,open(log+'.err','x') as se:
        return subprocess.run([sys.executable,'report97_gen.py',*args],env=env,stdout=so,stderr=se).returncode

def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);a=p.parse_args()
    root=OUT/'tests/gen';root.mkdir(parents=True,exist_ok=True);out=OUT/'gen_tests/base_V32'
    req=str(ORIGINAL/'data/V32/requests.json');base=['launch','--requests',req,'--out',str(out),'--workers','1','--peak-mib','12000']
    steps=[]
    t=time.monotonic();rc1=run(base+['--limit','3'],a.gpu,str(root/'partial'));n1=len(read_jsonl_complete(out/'worker_0.jsonl'))
    steps.append(dict(step='partial_limit3',rc=rc1,n_records=n1,wall_s=time.monotonic()-t))
    t=time.monotonic();rc2=run(base,a.gpu,str(root/'resume'));recs=read_jsonl_complete(out/'worker_0.jsonl')
    steps.append(dict(step='resume_to_complete',rc=rc2,n_records=len(recs),wall_s=time.monotonic()-t,completion=(out/'completion.json').exists()))
    old={r['id']:r for r in read_jsonl_complete(ORIGINAL/'recovery/validation/epoch2/base_report/worker_0.jsonl')}
    new={r['id']:r for r in recs}
    same=sum(old[k]['input_ids']==new[k]['input_ids'] and old[k]['text']==new[k]['text'] for k in new if k in old)
    token_same=sum([x['suffix_ids'] if 'suffix_ids' in x else None for x in old[k]['attempts']]==[x['suffix_ids'] if 'suffix_ids' in x else None for x in new[k]['attempts']] for k in new if k in old)
    # 변조: 다른 요청 파일로 같은 출력 경로 재실행 -> 거부(rc!=0)
    sub=OUT/'gen_tests/requests_subset.json';save(sub,json.loads(Path(req).read_text())[:31])
    rc3=run(['launch','--requests',str(sub),'--out',str(out),'--workers','1','--peak-mib','12000'],a.gpu,str(root/'tamper_requests'))
    # 완료 후 동일 재실행: rc 0 이고 record 수 불변
    rc4=run(base,a.gpu,str(root/'rerun_complete'));n4=len(read_jsonl_complete(out/'worker_0.jsonl'))
    ids=[r['id'] for r in recs]
    result=dict(passed=rc1==0 and n1==3 and rc2==0 and len(recs)==32 and len(set(ids))==32 and same==32 and token_same==32 and rc3!=0 and rc4==0 and n4==32,
        steps=steps,text_and_input_ids_equal_to_iter090_base=same,attempt_suffix_tokens_equal=token_same,tampered_request_rc=rc3,rerun_complete_rc=rc4,rerun_records=n4,
        all_eos=all(r['attempts'][-1]['ended_eos'] for r in recs),
        completion_sha=sha(out/'completion.json'),source_sha=sha(__file__))
    save(root/'result.json',result);print(json.dumps(result)[:700]);return 0 if result['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
