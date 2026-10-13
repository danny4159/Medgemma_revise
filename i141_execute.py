"""기술 판단 경계 후 고정 6명의 paired 본생성을 실행하고 완료까지 소유한다."""
from collections import Counter
import signal
import subprocess
import sys
import time
from i141_common import HERE,RES,read,save,now
import i141_prepare as prep
import i141_run as run


def main():
    gate=read(RES/'tests/technical_gate.json')
    choice=read(RES/'tests/throughput_choice.json')
    assert gate['passed'] is True
    assert gate['main_max_new_tokens']==2048
    rr=read(RES/'requests/main.json')
    assert len(set(r['patient_id'] for r in rr))==6
    count=Counter(r['condition'] for r in rr)
    tech=run.verify_job(RES/'jobs/tech2048_w2','technical2048')
    means={c:sum(r['wall_s'] for r in tech if r['condition']==c)/sum(r['condition']==c for r in tech) for c in count}
    workers=choice['selected_workers']
    wall_ratio=choice['w4_generation_wall_s']/choice['w2_generation_wall_s'] if workers==4 else 1.
    weighted_wall=sum(count[c]*means[c] for c in count)/2*wall_ratio
    save(RES/'pre_main_decision.json',{'created_at':now(),'patients':6,'requests':dict(count),'total_requests':len(rr),
         'workers':workers,'GPU_permitted':run.allowed(),'admission_peak_mib':choice['admission_peak_mib'],
         'max_new_tokens':2048,'estimated_generation_wall_s':weighted_wall,'estimate':True,
         'estimated_basis':'2048 기술 출력의 조건별 평균 처리시간과 개발 병렬 처리량 비율. 대기/로딩/평가 별도.',
         'stop_conditions':'자식 오류/OOM/입력 또는 source hash 불일치 시 중단. 고정 요청 미완료는 완료 아님.',
         'scope_changes':'없음; 고정6명/385개 slice multiset/동일 prompt·metric 유지',
         'resume':'동일 protocol 아래 고유 claim과 worker JSONL에 저장된 완료 요청 재생성 안 함'})
    prep.CODE=prep.CODE+['i141_cap_control.py','i141_execute.py','i141_finish.py']
    prep.lock('main')
    cmd=[sys.executable,str(HERE/'i141_run.py'),'launch','--stage','main','--job',str(RES/'jobs/main'),
         '--workers',str(workers),'--peak',str(choice['admission_peak_mib'])]
    with (RES/'main_supervisor.log').open('xb') as f:
        proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
        print({'main_supervisor_pid':proc.pid,'requests':len(rr),'workers':workers,
               'estimated_generation_minutes':weighted_wall/60},flush=True)
        try:
            rc=proc.wait()
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    proc.wait()
    save(RES/'main_exit.json',{'created_at':now(),'returncode':rc,'supervisor_pid':proc.pid})
    assert rc==0,'본생성 오류: main_supervisor.log 확인'
    result=run.verify_job(RES/'jobs/main','main')
    assert len(result)==len(rr)
    print({'generation_complete':len(result),'exit_code':rc},flush=True)


if __name__=='__main__':
    main()
