"""동일 기술 입력의 사후 자원 계측: 설정·연구 판정 변경 없음."""
import json,os,sys,time,subprocess
from pathlib import Path
from mr132_common import RES,read,save,sha,now

def main():
    # 모델 출력과 무관한 기술 첫 환자의3개 single·3개 정방향 pair를 사용한다.
    rr=[r for r in read(RES/'requests/technical.json') if r['patient']=='technical_p000' and (r['kind']=='single' or r['id'].endswith(('pair_01','pair_02','pair_12')))]
    assert len(rr)==6
    req=RES/'requests/io_profile.json';save(req,rr)
    cmd=[sys.executable,'mr132_run.py','launch','--job',str(RES/'gen/io_profile'),'--requests',str(req),'--workers','2','--batch','1','--peak','13000']
    out=RES/'resource_profile';out.mkdir(exist_ok=False)
    samples=[];start=time.monotonic()
    with open(out/'generation.log','xb') as log:
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                workers=[]
                for p in Path('/proc').glob('[0-9]*'):
                    try:
                        command=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode()
                        if 'mr132_run.py worker' not in command or str(RES/'gen/io_profile') not in command:continue
                        workers.append(dict(pid=int(p.name),io=(p/'io').read_text(),stat=(p/'stat').read_text()))
                    except (OSError,UnicodeError):pass
                samples.append(dict(time=now(),cpu_count=os.cpu_count(),loadavg=os.getloadavg(),meminfo=Path('/proc/meminfo').read_text(),cpu_pressure=Path('/proc/pressure/cpu').read_text(),io_pressure=Path('/proc/pressure/io').read_text(),memory_pressure=Path('/proc/pressure/memory').read_text(),workers=workers))
                time.sleep(2)
            rc=child.wait()
        finally:
            if child.poll() is None:child.terminate();child.wait()
    assert rc==0
    from mr132_run import verify_job
    actual=verify_job(RES/'gen/io_profile',req); baseline={r['id']:r for r in verify_job(RES/'gen/pilot_b1',RES/'requests/pilot.json')}
    mismatch=[r['id'] for r in actual if r['tokens']!=baseline[r['id']]['tokens']]
    save(out/'samples.json',samples)
    def psi(x):return float(x.splitlines()[0].split('avg10=')[1].split()[0])
    save(out/'summary.json',dict(created_at=now(),post_generation_resource_audit=True,selection_changed=False,hypothesis_or_metrics_changed=False,n_requests=6,n_samples=len(samples),max_cpu_load1=max(x['loadavg'][0] for x in samples),cpu_count=os.cpu_count(),max_io_some_avg10_percent=max(psi(x['io_pressure']) for x in samples),max_cpu_some_avg10_percent=max(psi(x['cpu_pressure']) for x in samples),max_memory_some_avg10_percent=max(psi(x['memory_pressure']) for x in samples),min_mem_available_kib=min(int(next(l for l in x['meminfo'].splitlines() if l.startswith('MemAvailable:')).split()[1]) for x in samples),wall_s=time.monotonic()-start,exit_code=rc,suffix_mismatch_ids=mismatch,all_pass=not mismatch,source_sha256=sha(__file__),samples_sha256=sha(out/'samples.json'),note='본실험 후 같은 기술 입력·batch1 구성의 CPU/RAM/I/O 압력을 보완 계측했다. 원 처리량 pilot의 사전 측정으로 보고하지 않으며 실행 구성이나 연구 분기에 반영하지 않는다.'))
    print('자원 사후 계측',len(actual),'요청, token mismatches',mismatch,flush=True)
    if mismatch:raise RuntimeError('resource profile regression mismatch')

if __name__=='__main__':main()
