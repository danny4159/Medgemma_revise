"""사전 계획의 1024→2048 기술 재실행을 관리한다. prompt·관측·metric을 변경하지 않는다."""
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from i141_common import HERE,RES,read,save,sha,now
import i141_run as run
import i141_prepare as prep


def call(job,workers,peak):
    with (RES/'tests'/('launch_'+job.name+'_'+str(time.time_ns())+'.log')).open('xb') as f:
        cmd=[sys.executable,str(HERE/'i141_run.py'),'launch','--stage','technical2048','--job',str(job),
             '--workers',str(workers),'--peak',str(peak)]
        process=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        print({'supervisor_pid':process.pid,'job':str(job)},flush=True)
        rc=process.wait()
    assert rc==0,'기술 재실행 실패: '+str(job)
    return run.verify_job(job,'technical2048')


def wall(job):
    c=read(job/'completion.json')
    start=read(job/('start_'+c['attempt']+'.json'))['created_at']
    records=run.verify_job(job,'technical2048')
    end=max(datetime.fromisoformat(r['completed_at']).timestamp() for r in records)
    return end-datetime.fromisoformat(start).timestamp()


def main():
    initial=run.verify_job(RES/'jobs/tech_w2','technical')
    assert any(r['n_tokens']>=1024 and not r['eos'] for r in initial)
    assert read(RES/'tests/runtime_checks.json')['all_pass']
    # 이전 잠금·출력을 유지하고 새 stage의 정확한 2048 설정을 본출력 전에 잠근다.
    prep.CODE=prep.CODE+['i141_cap_control.py']
    prep.lock('technical2048')
    a=call(RES/'jobs/tech2048_w2',2,12000)
    peak=int(np.ceil(max(r['peak_reserved_mib'] for r in a)))+256
    free={r['index']:int(r['free']) for r in run.smi()}
    assert all(free[g]>=2*(peak+2048) for g in run.allowed()), '4 worker 메모리 불충분; 본실행은 보류'
    b=call(RES/'jobs/tech2048_w4',4,peak)
    same=all(r['tokens']==next(x['tokens'] for x in a if x['id']==r['id']) for r in b)
    w2,w4=wall(RES/'jobs/tech2048_w2'),wall(RES/'jobs/tech2048_w4')
    chosen=4 if same and w4<w2 else 2
    throughput={'created_at':now(),'stage':'technical2048','measured_worker_peak_mib':peak-256,
                'admission_peak_mib':peak,'worker_margin_mib':2048,'two_workers_per_gpu_need_mib':2*(peak+2048),
                'gpu_free_before':free,'w2_generation_wall_s':w2,'w4_generation_wall_s':w4,
                'w2_requests_per_min':len(a)*60/w2,'w4_requests_per_min':len(b)*60/w4,
                'tokens_equal':same,'selected_workers':chosen,
                'reason':'같은 개발 요청의 생성 처리량과 greedy token 정합성. 로딩 비용은 별도 기록.',
                'truncated_w2':sum(not r['eos'] for r in a),'truncated_w4':sum(not r['eos'] for r in b),
                'output_max_tokens':2048,
                'main_requests':len(read(RES/'requests/main.json')),
                'estimated_main_generation_wall_s':len(read(RES/'requests/main.json'))*(w4 if chosen==4 else w2)/len(a),
                'estimate_limit':'개발 8건의 단순 처리량 외삽. 본요청 길이·S/A 비율 차이로 불확실.'}
    save(RES/'tests/throughput_choice.json',throughput)
    valid=read(RES/'tests/tensors_v2.json')['all_pass'] and read(RES/'tests/runtime_checks.json')['all_pass']
    valid=valid and all(r['boundary_status']!='invalid_boundary' for r in a)
    gate={'created_at':now(),'passed':valid,'main_max_new_tokens':2048,
          'initial_1024_cap_reached':True,'2048_recheck_done_both_conditions':True,
          'n_2048_records':len(a)+len(b),'cap_reached_again':any(not r['eos'] and r['n_tokens']>=2048 for r in a),
          'boundary_invalid':sum(r['boundary_status']=='invalid_boundary' for r in a),
          'EOS_100_percent_not_required_by_plan':True,
          'truncation_policy':'본출력 재생성 없음; 미완결·미판정 범위 별도. 반복문을 정답으로 정리하지 않음.',
          'evidence':{str(RES/'tests'/p):sha(RES/'tests'/p) for p in ['tensors_v2.json','runtime_checks.json','throughput_choice.json']}}
    save(RES/'tests/technical_gate.json',gate)
    assert valid
    print({'gate':gate,'throughput':throughput},flush=True)


if __name__=='__main__':
    main()
