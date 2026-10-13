"""실제 기술 산출물의 완료 재사용과 오류·변조·누락 거부를 검사한다."""
import copy
import subprocess
import time
from i142_common import *

def main():
    proto=verify_protocol(RES/'protocol_technical_v2.json')
    row=next(r for r in read(RES/'inference_inputs.json') if r['role']=='technical')
    result=RES/'jobs/tech_equivalence_v2'/row['patient_id']/'result.json'
    original=verify_result(result,proto,row)
    root=RES/'tests'/('runtime_'+str(time.time_ns()))
    root.mkdir()
    checks={}
    for label,change in [('error_status',lambda r:r.update(status='error')),
                          ('wrong_protocol',lambda r:r.update(protocol_digest='wrong')),
                          ('wrong_input',lambda r:r['input'].update(image_sha256='wrong')),
                          ('wrong_output',lambda r:r['outputs'].update({next(iter(r['outputs'])):'wrong'}))]:
        r=copy.deepcopy(original)
        change(r)
        r['record_digest']=digest({k:v for k,v in r.items() if k!='record_digest'})
        p=root/(label+'.json')
        save(p,r)
        try:
            verify_result(p,proto,row)
        except AssertionError:
            checks[label+'_rejected']=True
    p=root/'corrupt.json'
    p.write_text('{"truncated":')
    try:
        verify_result(p,proto,row)
    except ValueError:
        checks['corruption_rejected']=True
    try:
        verify_result(root/'missing.json',proto,row)
    except FileNotFoundError:
        checks['missing_rejected']=True
    before=sha(result)
    # 실제 worker 진입에서 같은 완료 작업을 재사용하며 새 GPU forward는 없다.
    command=[str(ENV),str(ROOT/'i142_worker.py'),'--patient',row['patient_id'],'--protocol',str(RES/'protocol_technical_v2.json'),
             '--out',str(result.parent),'--max-length','300','--direct','--equivalence']
    r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    save(root/'completed_reentry.json',{'command':command,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    checks['completed_reentry_immutable']=r.returncode==0 and before==sha(result) and '완료 출력 재사용' in r.stdout
    # 같은 출력 소유권을 다른 실제 worker가 인계받을 수 없어야 한다.
    with ownership(result.parent/'owner.lock'):
        r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    checks['concurrent_worker_rejected']=r.returncode!=0 and 'BlockingIOError' in r.stderr and before==sha(result)
    save(root/'concurrent_reentry.json',{'command':command,'exit_code':r.returncode,'stderr':r.stderr})
    save(RES/'tests/runtime_checks_v2.json',{'created_at':now(),'checks':checks,'all_pass':all(checks.values()),'source_sha256':sha(__file__)})
    assert len(checks)==8 and all(checks.values())
    print(checks)

if __name__=='__main__':
    main()
