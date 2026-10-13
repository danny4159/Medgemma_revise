"""필수 hook 대조 두 건을 허용 GPU에 분산하고 종료까지 소유한다."""
import signal
import subprocess
from i142_common import *
from i142_launch import gpu_status

def main():
    gpus=[g for g in gpu_status() if g['index'] in os.environ['CUDA_VISIBLE_DEVICES'].split(',')]
    gpus.sort(key=lambda x:-x['free'])
    assert len(gpus)==2 and all(g['free']>=7000+2048 for g in gpus)
    children=[]
    handles=[]
    out=RES/'tests/hook_control'
    out.mkdir()
    try:
        for patient,g in zip(['sub-strokecase0001','sub-strokecase0003'],gpus):
            env=os.environ.copy()
            env.update(CUDA_VISIBLE_DEVICES=g['index'],PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
                MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HOME=str(RES/'cache'),
                XDG_CACHE_HOME=str(RES/'cache'),TMPDIR=str(RES/'tmp'))
            cmd=[str(ENV),str(ROOT/'i142_hookcheck.py'),'--patient',patient]
            log=open(out/(patient+'.log'),'x')
            handles.append(log)
            children.append((subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True),patient,g,cmd))
        for proc,patient,g,cmd in children:
            assert proc.wait()==0,patient
    finally:
        for proc,patient,g,cmd in children:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL)
                    proc.wait()
        for f in handles:
            f.close()
        save(out/'exits.json',{'created_at':now(),'children':[{'patient_id':patient,'exit_code':proc.returncode,'gpu':g,'command':cmd} for proc,patient,g,cmd in children]})
    print('관측 hook 대조 2명 통과')

if __name__=='__main__':
    main()
