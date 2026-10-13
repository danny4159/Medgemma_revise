"""새 1–5장 DWI 입력의 공식 tensor·재개·경합·처리량을 검사한다."""
import argparse
from collections import Counter
import copy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import numpy as np
from i141_common import HERE, RES, read, save, sha, digest, now
from i141_spec import BASE_CONFIG, split_final, integrate, SEMANTIC_CONTRACT
import i141_run as run


def tensors():
    import torch
    from transformers import AutoProcessor
    from PIL import Image
    p=AutoProcessor.from_pretrained(run.MODEL,local_files_only=True)
    rr=read(RES/'requests/technical_pilot.json')
    checks=[]
    for r in rr:
        actual=run.input_tensor(p,r)
        text=p.apply_chat_template(run.messages(r),add_generation_prompt=True,tokenize=False)
        official=p(text=text,images=[Image.open(x['path']).convert('RGB') for x in r['images']],return_tensors='pt',add_special_tokens=False)
        equal=set(actual)==set(official) and all(torch.equal(actual[k],official[k]) for k in actual)
        # processor의 영상 tensor가 같은 순서에서 1장 처리와 동일한지 검사한다.
        value=actual['pixel_values']
        single_values=[]
        for image in r['images']:
            q=dict(r,images=[image])
            single_values.append(run.input_tensor(p,q)['pixel_values'])
        allpixels=torch.cat(single_values,dim=0)
        target_equal=torch.equal(value,allpixels)
        checks.append({'id':r['id'],'images':len(r['images']),'keys':list(actual),
                       'shapes':{k:list(v.shape) for k,v in actual.items()},
                       'image_token_count':int((actual['input_ids']==p.tokenizer.convert_tokens_to_ids('<image_soft_token>')).sum()),
                       'official_tensor_equal':equal,'single_joint_pixels_equal':target_equal})
    toy={'id':'x','slice_indices':[1],'final_text':'A. B.'}
    integration=integrate([toy,dict(toy,id='y',slice_indices=[2],final_text='A. C.')])
    pure_checks={'no_marker':split_final([1,2],94,95)==('no_marker',[1,2]),
                 'thought_final':split_final([94,3,95,5],94,95)==('thought_final',[5]),
                 'bad_boundary':split_final([94,3],94,95)==('invalid_boundary',[]),
                 'integration_exact':integration['exact_sentence_deduplication']=='A.\nB.\nC.'}
    result={'created_at':now(),'checks':checks,'pure_checks':pure_checks,
            'all_pass':all(c['official_tensor_equal'] and c['single_joint_pixels_equal'] for c in checks) and all(pure_checks.values())}
    save(RES/'tests/tensors_v2.json',result)
    assert result['all_pass']
    print({'tensors':len(checks),'all_pass':True})


def call(job,workers,peak,limit=0):
    cmd=[sys.executable,str(HERE/'i141_run.py'),'launch','--stage','technical',
         '--job',str(job),'--workers',str(workers),'--peak',str(peak),'--limit',str(limit)]
    with (RES/'tests'/('launch_'+job.name+'_'+str(time.time_ns())+'.log')).open('xb') as f:
        process=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        print(json.dumps({'supervisor_pid':process.pid,'job':str(job)}),flush=True)
        rc=process.wait()
    assert rc==0,'launch failed: '+str(job)
    return run.verify_job(job,'technical',complete=not limit)


def runtime():
    rr=run.requests('technical')
    reference=run.verify_job(RES/'jobs/tech_w2','technical')
    baseline={r['id']:r for r in reference}
    peak=int(np.ceil(max(r['peak_reserved_mib'] for r in reference)))+256
    checks=[]
    job=RES/'jobs/tech_resume'
    partial=call(job,2,peak,limit=1)
    assert 0<len(partial)<len(rr)
    preserved={str(p):p.read_bytes() for p in job.glob('worker*.jsonl')}
    tail=next(job.glob('worker*.jsonl'))
    with tail.open('ab') as f:
        f.write(b'{"interrupted":')
    resumed=call(job,2,peak)
    checks.append({'name':'partial_resume_tokens','pass':all(r['tokens']==baseline[r['id']]['tokens'] for r in resumed),
                   'partial_records':len(partial),'final_records':len(resumed)})
    checks.append({'name':'preserve_committed_prefix','pass':all(Path(p).read_bytes().startswith(b) for p,b in preserved.items())})
    before={str(p):sha(p) for p in job.glob('worker*.jsonl')}
    # 완료 재실행은 source/input/completion 검증 후 불변으로 끝나야 한다.
    call(job,2,peak)
    checks.append({'name':'complete_relaunch_immutable','pass':all(sha(p)==h for p,h in before.items())})
    # 동시 감독기와 직접 worker의 실제 동일 검증 함수 경로를 검사한다.
    held=os.open(job/'supervisor.lock',os.O_RDWR)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with (RES/'tests/duplicate_launch.log').open('xb') as f:
        rc=subprocess.run([sys.executable,str(HERE/'i141_run.py'),'launch','--stage','technical','--job',str(job)],stdout=f,stderr=subprocess.STDOUT).returncode
    os.close(held)
    checks.append({'name':'duplicate_supervisor_refused','pass':rc!=0})
    cases=[('request_duplicate',rr+[rr[0]]),('request_digest_changed',[dict(rr[0],prompt='changed')]),
           ('image_hash_changed',[dict(rr[0],images=[dict(rr[0]['images'][0],sha256='0'*64)])])]
    for name,values in cases:
        if name=='image_hash_changed':
            values[0]['request_digest']=digest({k:v for k,v in values[0].items() if k!='request_digest'})
        path=RES/'tests'/(name+'.json')
        save(path,values)
        try:
            run.requests('technical',path)
            ok=False
        except (AssertionError,ValueError):
            ok=True
        checks.append({'name':name,'pass':ok})
    bad=copy.deepcopy(read(run.protocol_path('technical')))
    bad['code'][str(HERE/'i141_spec.py')]='0'*64
    badpath=RES/'tests/protocol_corrupted.json'
    save(badpath,bad)
    old=run.protocol_path
    run.protocol_path=lambda stage:badpath
    direct=RES/'tests/direct_worker'
    direct.mkdir()
    fd=os.open(direct/'supervisor.lock',os.O_CREAT|os.O_RDWR,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        run.worker(SimpleNamespace(lock_fd=fd,job=str(direct),stage='technical'))
        ok=False
    except ValueError as e:
        ok='protocol mismatch' in str(e)
    finally:
        os.close(fd)
        run.protocol_path=old
    checks.append({'name':'direct_worker_source_hash_refused_before_model_load','pass':ok})
    badrecord=copy.deepcopy(reference)
    badrecord[0]['protocol_sha256']='0'*64
    try:
        run.check_records(badrecord,rr,run.verify_protocol('technical'),run.config_for('technical'))
        ok=False
    except AssertionError:
        ok=True
    checks.append({'name':'record_provenance_tamper_refused','pass':ok})
    try:
        run._load_records(RES/'jobs/tech_w2')
        complete_ids={r['id'] for r in reference}=={r['id'] for r in rr}
    except Exception:
        complete_ids=False
    checks.append({'name':'no_duplicate_missing_extra','pass':complete_ids})
    result={'created_at':now(),'checks':checks,'all_pass':all(c['pass'] for c in checks),'peak_admission_mib':peak}
    save(RES/'tests/runtime_checks.json',result)
    assert result['all_pass']
    print({'runtime_checks':len(checks),'all_pass':True})


def throughput():
    baseline=run.verify_job(RES/'jobs/tech_w2','technical')
    peak=int(np.ceil(max(r['peak_reserved_mib'] for r in baseline)))+256
    free={r['index']:int(r['free']) for r in run.smi()}
    fits=all(free[g]>=2*(peak+2048) for g in run.allowed())
    report={'created_at':now(),'measured_worker_peak_mib':peak-256,'admission_peak_mib':peak,
            'two_workers_per_gpu_need_mib':2*(peak+2048),'gpu_free_before':free,'worker_margin_mib':2048}
    if fits:
        result=call(RES/'jobs/tech_w4',4,peak)
        same=all(r['tokens']==next(b['tokens'] for b in baseline if b['id']==r['id']) for r in result)
        def generation_wall(job):
            starts=list(job.glob('start_*.json'))
            start=read(starts[-1])['created_at']
            from datetime import datetime
            end=max(datetime.fromisoformat(r['completed_at']).timestamp() for r in run.load_records(job))
            return end-datetime.fromisoformat(start).timestamp()
        wall2=generation_wall(RES/'jobs/tech_w2')
        wall4=generation_wall(RES/'jobs/tech_w4')
        report.update({'w2_generation_wall_s':wall2,'w4_generation_wall_s':wall4,
                       'w2_requests_per_min':len(baseline)*60/wall2,'w4_requests_per_min':len(result)*60/wall4,
                       'tokens_equal':same,'selected_workers':4 if same and wall4<wall2 else 2,
                       'reason':'개발 요청의 전체 생성 처리량과 token 정합성으로 선택'})
        assert same
    else:
        # 메모리가 두 worker를 허용하지 않으면 같은 개발 입력의 batch2를 직접 비교한다.
        raise RuntimeError('w4 unsafe; batch expansion pilot required before main')
    save(RES/'tests/throughput_choice.json',report)
    print(report)


def gate():
    jobs=[RES/'jobs/tech_w2',RES/'jobs/tech_resume',RES/'jobs/tech_w4']
    allrecords=[r for j in jobs for r in run.verify_job(j,'technical')]
    capped=any(r['n_tokens']>=1024 and not r['eos'] for r in allrecords)
    result={'created_at':now(),'passed':read(RES/'tests/tensors_v2.json')['all_pass'] and read(RES/'tests/runtime_checks.json')['all_pass'],
            'main_max_new_tokens':2048 if capped else 1024,'cap_reached':capped,
            'n_technical_records':len(allrecords),'boundary_invalid':sum(r['boundary_status']=='invalid_boundary' for r in allrecords),
            'eos':sum(r['eos'] for r in allrecords), 'requires_2048_technical_recheck':capped,
            'evidence':{str(RES/'tests'/p):sha(RES/'tests'/p) for p in ['tensors_v2.json','runtime_checks.json','throughput_choice.json']}}
    if capped:
        result['passed']=False
    save(RES/'tests/technical_gate.json',result)
    print(result)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['tensors','runtime','throughput','gate'])
    args=p.parse_args()
    globals()[args.command]()
