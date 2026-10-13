"""기술 2명을 각 2회 실행해 4-worker 처리량과 직접 SDK 출력 정합성을 비교한다."""
import signal
import subprocess
import time
from i142_common import *
from i142_launch import gpu_status

def main():
    direct=RES/'jobs/tech_equivalence_v2'
    baseline=read(direct/'completion.json')
    rows=[r for r in read(RES/'inference_inputs.json') if r['role']=='technical']
    previous=verify_protocol(RES/'protocol_technical_v2.json')
    measured=max(verify_result(direct/r['patient_id']/'result.json',previous,r)['peak_reserved_MiB'] for r in rows)
    gpus=[g for g in gpu_status() if g['index'] in os.environ['CUDA_VISIBLE_DEVICES'].split(',')]
    gpus.sort(key=lambda x:-x['free'])
    assert len(gpus)==2 and all(g['free']>=2*(measured+2048) for g in gpus)
    protocol={k:v for k,v in previous.items() if k not in ['digest','created_at']}
    protocol['created_at']=now()
    protocol['files'][str(ROOT/'i142_pilot.py')]=sha(__file__)
    protocol['digest']=digest(protocol)
    save(RES/'protocol_technical_4w_v2.json',protocol)
    job=RES/'jobs/tech_4w_v2'
    job.mkdir()
    children=[]
    logs=[]
    samples=[]
    started=time.perf_counter()
    try:
        for replica in range(2):
            for idx,row in enumerate(rows):
                g=gpus[idx]
                env=os.environ.copy()
                env.update(CUDA_VISIBLE_DEVICES=g['index'],PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
                    MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HOME=str(RES/'cache'),
                    XDG_CACHE_HOME=str(RES/'cache'),TMPDIR=str(RES/'tmp'),TOKENIZERS_PARALLELISM='false')
                out=job/(row['patient_id']+'_rep'+str(replica))
                log=open(job/(row['patient_id']+'_rep'+str(replica)+'.log'),'x')
                logs.append(log)
                cmd=[str(ENV),str(ROOT/'i142_worker.py'),'--patient',row['patient_id'],'--protocol',str(RES/'protocol_technical_4w_v2.json'),
                     '--out',str(out),'--max-length','300']
                child=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                children.append({'proc':child,'row':row,'gpu':g,'out':out,'command':cmd})
        while any(c['proc'].poll() is None for c in children):
            samples.append({'elapsed_s':time.perf_counter()-started,'gpus':gpu_status(),'loadavg':os.getloadavg()})
            assert not any(c['proc'].poll() not in (None,0) for c in children), 'pilot worker failed'
            time.sleep(1)
        assert all(c['proc'].returncode==0 for c in children)
    except BaseException:
        for c in children:
            if c['proc'].poll() is None:
                os.killpg(c['proc'].pid,signal.SIGTERM)
        for c in children:
            try:
                c['proc'].wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(c['proc'].pid,signal.SIGKILL)
                c['proc'].wait()
        raise
    finally:
        for log in logs:
            log.close()
        save(job/'resources.json',samples)
        save(job/'exits.json',{'wall_s':time.perf_counter()-started,'children':[{'row':c['row'],'gpu':c['gpu'],
            'pid':c['proc'].pid,'exit_code':c['proc'].returncode,'out':str(c['out']),'command':c['command']} for c in children]})
    checks=[]
    for c in children:
        r=verify_result(c['out']/'result.json',protocol,c['row'])
        b=verify_result(direct/c['row']['patient_id']/'result.json',previous,c['row'])
        checks.append({'patient_id':r['patient_id'],'out':str(c['out']),
            'segmentation_tensor_equal':r['observations']['segmentation_inputs']==b['observations']['segmentation_inputs'],
            'report_tensor_equal':r['observations']['report_inputs']==b['observations']['report_inputs'],
            'features_tokens_equal':r['observations']['generation']==b['observations']['generation'],
            'regions_equal':r['observations']['regions']==b['observations']['regions'],
            'final_report_equal':r['report']==b['report'],'complete':r['complete'],'cap_hit':r['cap_hit'],
            'peak_reserved_MiB':r['peak_reserved_MiB']})
    equal=all(all(c[k] for k in ('segmentation_tensor_equal','report_tensor_equal','features_tokens_equal','regions_equal','final_report_equal')) for c in checks)
    save(RES/'tests/technical_comparison_v2.json',{'created_at':now(),'checks':checks,'all_equal':equal,
        'direct_sdk':'공식 AutoRG_Brain.report 직접 호출','wrapper':'입력 allowlist wrapper; 같은 SDK',
        'hook_scope':'인자/반환을 바꾸지 않는 hash/token 관측 hook; direct에도 token 기록 hook 사용'})
    assert equal
    wall=read(job/'exits.json')['wall_s']
    save(RES/'tests/throughput_v2.json',{'baseline_2worker':{'n':4,'wall_s':baseline['wall_s'],'patients_per_min':240/baseline['wall_s']},
       'candidate_4worker':{'n':4,'wall_s':wall,'patients_per_min':240/wall},
       'admission_peak_MiB':measured,'admission':gpus,'checks':checks,
       'boundary':'subprocess 생성부터 전체 정상 종료까지; protocol 검증·loading·실제 segmentation·generation·저장 포함',
       'baseline_note':'GPU당 한 worker에서 직접 SDK+wrapper의 연속 2회 호출; 총 4 volume 처리. 4 worker는 같은 2명을 각 2회 독립 실행. loading·검사/저장 경계 차이를 포함한 탐색 측정.'})
    print({'all_equal':equal,'2w_patients_per_min':240/baseline['wall_s'],'4w_patients_per_min':240/wall})

if __name__=='__main__':
    main()
