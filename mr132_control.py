"""고정 단계의 감독기: 자체 대기, 기술 검증 후 개발, 사전 분기만 확대."""
import os,sys,subprocess,time,json,signal
from pathlib import Path
from mr132_common import RES,read,save,sha,now

def main():
    out=RES/'control';out.mkdir(exist_ok=False)
    save(out/'config.json',dict(started_at=now(),source_sha256=sha(__file__),batch=1,workers=2,peak_admission_mib=13000,estimated_development_wall_s=read(RES/'tests/throughput.json')['estimated_development_wall_s'],reason='batch2 token 불일치로 batch1; 동시 두 worker/장 메모리 부족; 검증 실패시 중단'))
    assert read(RES/'tests/throughput.json')['chosen_batch']==1
    start=time.monotonic();current=None
    def run(name,cmd):
        nonlocal current
        t=time.monotonic()
        with open(out/(name+'.log'),'xb') as f:
            current=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT)
            rc=current.wait();current=None
        save(out/(name+'.json'),dict(command=cmd,exit_code=rc,wall_s=time.monotonic()-t,ended_at=now()))
        print(name,'rc',rc,'wall',round(time.monotonic()-t,2),flush=True)
        if rc:raise RuntimeError(name+' failed')
    def launch(name,stage,limit=0):
        requests='pilot' if stage=='resume' else stage
        run(name,[sys.executable,'mr132_run.py','launch','--job',str(RES/'gen'/stage),'--requests',str(RES/'requests'/f'{requests}.json'),'--workers','2','--batch','1','--peak','13000','--limit',str(limit)])
    try:
        launch('resume_partial','resume',2)
        launch('resume_finish','resume')
        run('runtime_tests',[sys.executable,'mr132_tests.py','runtime'])
        launch('technical_generation','technical')
        from mr132_run import verify_job
        rr=verify_job(RES/'gen/technical',RES/'requests/technical.json')
        assert len(rr)==54 and all(r['eos'] for r in rr),'기술 생성 절단을 먼저 해소해야 함'
        save(RES/'tests/technical_gate.json',dict(created_at=now(),passed=True,n_requests=54,n_eos=sum(r['eos'] for r in rr),evidence={str(p):sha(p) for p in [RES/'tests/cpu.json',RES/'tests/tensors.json',RES/'tests/runtime.json',RES/'tests/throughput.json',RES/'gen/technical/completion.json']},input_manifest_sha256=sha(RES/'data/technical_manifest.json'),protocol_sha256=sha(RES/'protocol_lock_v2.json'),accuracy_not_a_gate=True))
        launch('development_generation','development')
        run('development_evaluation',[sys.executable,'mr132_eval.py','development'])
        run('development_independent',[sys.executable,'mr132_verify.py','development'])
        decision=read(RES/'eval/development_decision.json')
        if decision['expand']:
            run('holdout_data',[sys.executable,'mr132_data.py','holdout'])
            run('holdout_requests',[sys.executable,'mr132_build.py','holdout'])
            launch('holdout_generation','holdout')
            run('holdout_evaluation',[sys.executable,'mr132_eval.py','holdout'])
            run('holdout_independent',[sys.executable,'mr132_verify.py','holdout'])
        save(out/'completion.json',dict(completed_at=now(),wall_s=time.monotonic()-start,holdout_executed=decision['expand'],development_decision_sha256=sha(RES/'eval/development_decision.json'),all_commands_pass=True))
    finally:
        if current and current.poll() is None:
            current.terminate()
            try:current.wait(timeout=30)
            except subprocess.TimeoutExpired:current.kill();current.wait()

if __name__=='__main__':main()
