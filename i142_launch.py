"""허용 장치에서 worker를 분산하고 실제 자원과 종료·완료를 기록한다."""
import argparse
import signal
import subprocess
import time
from i142_common import *

def gpu_status():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,pci.bus_id,memory.total,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    result=[]
    for line in raw.splitlines():
        i,uuid,bus,total,used,free,util=[v.strip() for v in line.split(',')]
        result.append(dict(index=i,uuid=uuid,bus=bus,total=int(total),used=int(used),free=int(free),util=int(util)))
    return result

def process_memory():
    raw=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_gpu_memory','--format=csv,noheader,nounits'],text=True)
    return {int(line.split(',')[0]):int(line.split(',')[1].strip()) for line in raw.splitlines() if line.strip() and 'N/A' not in line}

def launch(a):
    protocol=verify_protocol(a.protocol)
    allow=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    assert allow and all(allow)
    gpus=[x for x in gpu_status() if x['index'] in allow or x['uuid'] in allow]
    assert len(gpus)==len(allow)
    gpus.sort(key=lambda x:-x['free'])
    rows=read(RES/'inference_inputs.json')
    selected=[x for x in rows if x['role']==('main' if a.stage=='main' else 'technical')]
    if a.stage=='main':
        choice=read(RES/'execution_choice.json')
        assert choice['technical_pass'] and choice['max_length']==a.max_length
    job=RES/'jobs'/a.name
    job.mkdir(parents=True,exist_ok=True)
    with ownership(job/'launch.lock'):
        if (job/'completion.json').exists():
            c=read(job/'completion.json')
            assert c['protocol_digest']==protocol['digest'] and c['max_length']==a.max_length and c['direct']==a.direct
            assert set(c['patients'])==set(x['patient_id'] for x in selected)
            for r in selected:
                verify_result(job/r['patient_id']/'result.json',protocol,r)
            for path,h in c['files'].items():
                assert sha(path)==h
            print('검증된 job 완료 재사용',a.name)
            return
        attempt=job/('launch_'+str(time.time_ns()))
        attempt.mkdir()
        active=[]
        started=time.perf_counter()
        samples=[]
        handles=[]
        launch_meta={'created_at':now(),'inherited_cuda_visible':allow,'gpus':gpus,'commands':[],'results':[]}
        pending=list(selected)
        try:
            while pending or active:
                status=gpu_status()
                # 실행 직전 실제 외부 점유와 아직 loading 중인 worker의 예약량을 합산한다.
                for g in gpus:
                    current=next(x for x in status if x['uuid']==g['uuid'])
                    n=sum(x['gpu']==g['index'] for x in active)
                    own_memory=process_memory()
                    unallocated_reservation=sum(max(0,a.peak_mib-own_memory.get(x['proc'].pid,0)) for x in active if x['gpu']==g['index'])
                    if pending and n<a.per_gpu and current['free']-unallocated_reservation >= a.peak_mib+2048*(n+1):
                        row=pending.pop(0)
                        env=os.environ.copy()
                        env.update(CUDA_VISIBLE_DEVICES=g['index'],PYTHONDONTWRITEBYTECODE='1',
                            OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
                            HF_HOME=str(RES/'cache'),XDG_CACHE_HOME=str(RES/'cache'),TMPDIR=str(RES/'tmp'),
                            TOKENIZERS_PARALLELISM='false')
                        (RES/'tmp').mkdir(exist_ok=True)
                        command=[str(ENV),str(ROOT/'i142_worker.py'),'--patient',row['patient_id'],
                            '--protocol',str(Path(a.protocol).resolve()),'--out',str(job/row['patient_id']),
                            '--max-length',str(a.max_length)]
                        if a.direct:
                            command.append('--direct')
                        if a.equivalence:
                            command.append('--equivalence')
                        log=open(attempt/(row['patient_id']+'.log'),'x')
                        handles.append(log)
                        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                        active.append({'proc':child,'gpu':g['index'],'row':row})
                        launch_meta['commands'].append({'patient_id':row['patient_id'],'pid':child.pid,
                            'physical_gpu':g,'child_logical_gpu':0,'command':command,'admission':current,'live_workers_same_gpu_before':n})
                samples.append({'elapsed_s':time.perf_counter()-started,'gpus':status,
                                'loadavg':os.getloadavg(),'active_pids':[x['proc'].pid for x in active]})
                for item in list(active):
                    rc=item['proc'].poll()
                    if rc is not None:
                        launch_meta['results'].append({'patient_id':item['row']['patient_id'],'exit_code':rc})
                        active.remove(item)
                        if rc!=0:
                            raise RuntimeError('worker failed: '+item['row']['patient_id'])
                        verify_result(job/item['row']['patient_id']/'result.json',protocol,item['row'])
                if pending and not active and all(g['free']<a.peak_mib+2048 for g in status if g['index'] in allow):
                    raise RuntimeError('가용 GPU 메모리 부족')
                if pending or active:
                    time.sleep(1)
            launch_meta['status']='ok'
        except BaseException:
            launch_meta['status']='error'
            for item in active:
                os.killpg(item['proc'].pid,signal.SIGTERM)
            for item in active:
                try:
                    item['proc'].wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(item['proc'].pid,signal.SIGKILL)
                    item['proc'].wait()
            raise
        finally:
            for f in handles:
                f.close()
            launch_meta['wall_s']=time.perf_counter()-started
            save(attempt/'launch.json',launch_meta)
            save(attempt/'resource_samples.json',samples)
        paths=[job/r['patient_id']/'result.json' for r in selected]
        save(job/'completion.json',{'created_at':now(),'protocol_digest':protocol['digest'],
            'patients':[r['patient_id'] for r in selected],'files':{str(p):sha(p) for p in paths},
            'launch_sha256':sha(attempt/'launch.json'),'launch_path':str(attempt/'launch.json'),
            'wall_s':launch_meta['wall_s'],'max_length':a.max_length,'direct':a.direct,
            'per_gpu':a.per_gpu,'peak_mib_admission':a.peak_mib})
        print({'job':a.name,'patients':len(paths),'wall_s':launch_meta['wall_s']},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--stage',choices=['tech','main'],required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--protocol',required=True)
    p.add_argument('--max-length',type=int,default=300)
    p.add_argument('--per-gpu',type=int,default=1)
    p.add_argument('--peak-mib',type=int,default=20000)
    p.add_argument('--direct',action='store_true')
    p.add_argument('--equivalence',action='store_true')
    launch(p.parse_args())
