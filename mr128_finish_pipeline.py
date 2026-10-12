"""고정 단계 완료를 프로그램이 기다린 뒤 calibration→80건→검산을 실행한다."""
import argparse
import fcntl
from pathlib import Path
import subprocess
import sys
import time
import psutil
from mr128_data import OUT,read,save,sha,verify_files,utc


def main(pid,prepare_pid):
    with (OUT/'finish_pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        print('pipeline supervisor',__import__('os').getpid(),flush=True)
        while not (OUT/'prepare_outputs_complete.json').exists() or (psutil.pid_exists(pid) and psutil.Process(pid).status()!=psutil.STATUS_ZOMBIE):
            if not (psutil.pid_exists(prepare_pid) and psutil.Process(prepare_pid).status()!=psutil.STATUS_ZOMBIE) and not (OUT/'prepare_outputs_complete.json').exists():
                raise RuntimeError('자료 변환 프로그램이 완료 없이 종료됨. 결과와 실패 로그를 검토해야 한다.')
            time.sleep(15)
        prepare=read(OUT/'prepare_outputs_complete.json');verify_files(prepare['builds'])
        if not prepare['complete'] or prepare['expected']!=52:raise ValueError('remaining build complete52')
        if not read(OUT/'all_input_independent_checks_v2.json')['all_pass'] or not read(OUT/'runtime_tests.json')['all_pass']:raise ValueError('required input/runtime checks')
        verification_lock=dict(created_utc=utc(),code={p:sha(p) for p in ['mr128_analysis.py','mr128_verify_results.py','mr128_finish_pipeline.py']},
             inputs={str(OUT/p):sha(OUT/p) for p in ['all_input_independent_checks_v2.json','runtime_tests.json','evaluation_lock_v2.json','prepare_outputs_complete.json']})
        if not (OUT/'main_analysis_lock.json').exists():save(OUT/'main_analysis_lock.json',verification_lock)
        else:verify_files(read(OUT/'main_analysis_lock.json')['code']);verify_files(read(OUT/'main_analysis_lock.json')['inputs'])
        jobs=[([sys.executable,'mr128_analysis.py','calibrate'],'calibration',OUT/'calibration_lock.json'),
              ([sys.executable,'mr128_gen.py','prepare','explore'],'prepare_requests',OUT/'explore_requests.json'),
              ([sys.executable,'mr128_gen.py','run','--stage','main','--requests',str(OUT/'explore_requests.json'),'--batch','1','--workers','2','--max-new','512'],'main_generation',OUT/'gen/main/completion.json'),
              ([sys.executable,'mr128_analysis.py','analyze'],'analysis',OUT/'eval/report.json'),
              ([sys.executable,'mr128_verify_results.py'],'independent_verify',OUT/'eval/independent_verify.json')]
        for command,name,artifact in jobs:
            if artifact.exists() and name in ['analysis','independent_verify']:
                if name=='analysis':
                    report=read(artifact);verify_files(report['provenance']['builds'])
                    if report['provenance']['main_completion_sha256']!=sha(OUT/'gen/main/completion.json') or report['provenance']['calibration_sha256']!=sha(OUT/'calibration_lock.json'):raise ValueError('stale analysis')
                else:
                    previous=read(artifact)
                    if not previous['all_pass'] or previous['report_sha256']!=sha(OUT/'eval/report.json'):raise ValueError('stale independent verification')
                print('verified existing stage',name,flush=True);continue
            print('stage',name,flush=True);t0=time.monotonic()
            p=subprocess.run(command)
            save(OUT/(name+'_execution_'+__import__('uuid').uuid4().hex+'.json'),dict(command=command,returncode=p.returncode,wall_s=time.monotonic()-t0,created_utc=utc()))
            if p.returncode!=0:return p.returncode
        verification=read(OUT/'eval/independent_verify.json')
        if not verification['all_pass']:raise ValueError('independent verification failed')
        save(OUT/'pipeline_complete.json',dict(created_utc=utc(),checks_passed=True,
            artifacts={str(OUT/p):sha(OUT/p) for p in ['calibration_lock.json','explore_requests.json','gen/main/completion.json','eval/report.json','eval/independent_verify.json']},
            source_sha256=sha(__file__)))
        print('pipeline complete',flush=True);return 0


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--pid',type=int,required=True);ap.add_argument('--prepare-pid',type=int,required=True);a=ap.parse_args()
    raise SystemExit(main(a.pid,a.prepare_pid))
