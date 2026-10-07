"""선택·E reference 잠금 후 512개 판독과 64개 보조 요청을 관리한다."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
OUT=ORIGINAL/'recovery'

def main():
    selection=OUT/'selection/final.json';selected=json.loads(selection.read_text());assert selected['passed']
    for p,h in selected['sources'].items():assert sha(p)==h
    for item in selected['selected'].values():assert sha(item['checkpoint'])==item['checkpoint_sha']
    data=OUT/'data/E128';dc=json.loads((data/'completion.json').read_text());assert dc['passed'] and dc['selection_sha']==sha(selection)
    for p,h in dc['files'].items():assert sha(p)==h
    reference=OUT/'semantic/E_reference.json';refs=json.loads(reference.read_text())
    manifest=json.loads((data/'manifest.json').read_text());by={r['ImageID']:r for r in manifest}
    assert refs['manifest_sha']==sha(data/'manifest.json') and len(refs['rows'])==128
    assert {r['id'] for r in refs['rows']}==set(by) and len({r['patient'] for r in refs['rows']})==128
    for r in refs['rows']:
        assert r['patient']==by[r['id']]['PatientID'] and r['report']==by[r['id']]['report']
        assert r['abnormal']==by[r['id']]['retained_abnormal'] and r['atoms']
        assert len({a['id'] for a in r['atoms']})==len(r['atoms'])
        for a in r['atoms']:assert r['report'][a['start']:a['end']]==a['source']
    cure_python=str(ORIGINAL.parent/'environments/cure085/bin/python');assert Path(cure_python).is_file()
    # 공식 입력 회귀와 자산 불변성 확인을 그대로 연결한다.
    for filename,key in [('cure_regression.json','passed'),('cure_assets.json','passed')]:
        value=json.loads((ORIGINAL/'tech'/filename).read_text());assert value[key]
        for p,h in value.get('provenance',{}).items():assert sha(p)==h
    from report86_common import R85
    for p,h in json.loads((R85/'model_manifest.json').read_text())['files'].items():assert sha(p)==h
    jobs=[]
    for mode in ['R','G']:
        jobs.append(dict(name=mode+'_report',backend='med',python=sys.executable,requests=str(data/'report_requests.json'),n=128,checkpoint=selected['selected'][mode]['checkpoint']))
    jobs.extend([dict(name='base_report',backend='med',python=sys.executable,requests=str(data/'report_requests.json'),n=128,checkpoint=None),
                 dict(name='CURE_report',backend='cure',python=cure_python,requests=str(data/'cure_requests.json'),n=128,checkpoint=None)])
    for mode in ['R','G']:
        jobs.append(dict(name=mode+'_ground',backend='med',python=sys.executable,requests=str(data/'ground_requests.json'),n=32,checkpoint=selected['selected'][mode]['checkpoint']))
    root=OUT/'final_generation';root.mkdir(parents=True,exist_ok=True)
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert len(allowed)==len(set(allowed))
    with (root/'owner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        previous=[int(p.stem.rsplit('_',1)[1]) for pattern in ('result_*.json','resources_*.jsonl') for p in root.glob(pattern)]
        attempt=max(previous,default=-1)+1;active={};done=[];logs=[];start=time.monotonic()
        config=dict(jobs=jobs,selection_sha=sha(selection),reference_sha=sha(reference),data_completion_sha=sha(data/'completion.json'),
                    sources={p:sha(p) for p in [__file__,'report90_final_verify.py','report90_recovery_gen.py','report90_cure.py']},
                    caps=[1024,2048,4096],workers_per_gpu=1,peak_reservation_mib=12000,worker_margin_mib=2048)
        frozen=root/'contract.json'
        if frozen.exists():assert json.loads(frozen.read_text())==config
        else:save(frozen,config)
        def stop(*args):raise KeyboardInterrupt('owned final workers stopping')
        signal.signal(signal.SIGTERM,stop)
        try:
            while jobs or active:
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,memory.used','--format=csv,noheader,nounits'],text=True)
                free={x.split(',')[0].strip():int(x.split(',')[1]) for x in raw.splitlines()}
                with (root/f'resources_{attempt}.jsonl').open('a') as f:f.write(json.dumps(dict(time=time.time(),smi=raw))+'\n')
                for g in sorted(allowed,key=lambda g:free[g],reverse=True):
                    if not jobs or g in active or free[g]<14048:continue
                    job=jobs.pop(0);stage=root/job['name'];script='report90_cure.py' if job['backend']=='cure' else 'report90_recovery_gen.py'
                    cmd=[job['python'],script,'launch','--requests',job['requests'],'--out',str(stage),'--workers','1','--peak-mib','12000']
                    if job['checkpoint']:cmd+=['--checkpoint',job['checkpoint']]
                    so=(root/f'{job["name"]}_{attempt}.stdout.log').open('x');se=(root/f'{job["name"]}_{attempt}.stderr.log').open('x');logs.extend([so,se])
                    env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=g
                    p=subprocess.Popen(cmd,env=env,stdout=so,stderr=se);active[g]=(dict(job,gpu=g,start=time.time()),p)
                    print(json.dumps(dict(start=job['name'],gpu=g,pid=p.pid)),flush=True)
                for g,(job,p) in list(active.items()):
                    if p.poll() is None:continue
                    del active[g];done.append(dict(job,rc=p.returncode,end=time.time()));assert p.returncode==0,(job,p.returncode)
                    stage=root/job['name'];output=stage/f'verified_attempt{attempt}.json'
                    subprocess.run([job['python'],'report90_final_verify.py','--backend',job['backend'],'--stage',str(stage),'--requests',job['requests'],
                                    '--n',str(job['n']),'--output',str(output)],check=True)
                if jobs or active:time.sleep(10)
        finally:
            for _,p in active.values():
                if p.poll() is None:p.terminate()
            for job,p in active.values():done.append(dict(job,rc=p.wait(),end=time.time()))
            for f in logs:f.close()
            save(root/f'result_{attempt:03}.json',dict(done=done,pending=jobs,wall_s=time.monotonic()-start,contract_sha=sha(frozen)))

if __name__=='__main__':main()
