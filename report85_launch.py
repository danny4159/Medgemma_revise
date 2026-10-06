"""iter_085 보조 캐시까지 격리하는 관리형 실행 진입점.

기본 환경이나 기존 HF cache를 수정하지 않는다. 인증 파일 경로는 상속한다.
모델·검사 script는 기존 잠긴 버전을 그대로 사용하며 자식 종료를 수집한다.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from report84_preflight import ROOT, sha, save


def isolated_env():
    env=os.environ.copy()
    cache=ROOT/'results/iter_085/runtime_cache'
    for key, name in {'HF_HOME':'hf','HF_HUB_CACHE':'hf/hub','HF_XET_CACHE':'hf/xet',
            'XDG_CACHE_HOME':'xdg','TORCH_HOME':'torch','TORCHINDUCTOR_CACHE_DIR':'inductor',
            'TRITON_CACHE_DIR':'triton','CUDA_CACHE_PATH':'cuda','MPLCONFIGDIR':'matplotlib',
            'PIP_CACHE_DIR':'pip','TMPDIR':'tmp'}.items():
        p=cache/name; p.mkdir(parents=True,exist_ok=True); env[key]=str(p)
    env['HF_HUB_OFFLINE']='1'
    env['TOKENIZERS_PARALLELISM']='false'
    env['NO_ALBUMENTATIONS_UPDATE']='1'
    return env


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--check-env',action='store_true')
    p.add_argument('--system',choices=['M15','B0','M1','M1G','C'])
    p.add_argument('--gpu')
    p.add_argument('--out')
    p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    env=isolated_env()
    logs=ROOT/'results/iter_085/launches'; logs.mkdir(exist_ok=True)
    attempt=logs/str(time.time_ns()); attempt.mkdir()
    py=str(ROOT/'results/environments/cure085/bin/python') if a.system in ['M1G','C'] else sys.executable
    if a.check_env:
        cmd=[py,'-c',"import json,os,huggingface_hub.constants as c; from pathlib import Path; root=Path('results/iter_085/runtime_cache').resolve(); paths={'HF_HOME':c.HF_HOME,'HF_HUB_CACHE':c.HF_HUB_CACHE,'HF_XET_CACHE':c.HF_XET_CACHE}; assert all(Path(v).is_relative_to(root) for v in paths.values()); print(json.dumps({'paths':paths,'token_path_inherited':bool(os.environ.get('HF_TOKEN_PATH')),'pass':True}))"]
    else:
        assert a.system and a.gpu and a.out
        assert a.gpu in env['CUDA_VISIBLE_DEVICES'].split(',')
        Path(a.out).resolve().relative_to(ROOT/'results/iter_085')
        smi=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True)
        free={x.split(',')[0].strip():int(x.split(',')[1]) for x in smi.splitlines()}
        assert free[a.gpu]>=12288, '측정 peak 10GiB + worker 여유 2GiB 미확보'
        cmd=[py,str(ROOT/'report85_d8.py'),'--system',a.system,'--gpu',a.gpu,'--out',a.out]+(['--resume'] if a.resume else [])
    save(attempt/'launch.json',{'command':cmd,'source_sha256':sha(__file__),'runner_sha256':sha(ROOT/'report85_d8.py'),'credential_values_recorded':False})
    start=time.monotonic()
    with (attempt/'stdout.log').open('x') as stdout,(attempt/'stderr.log').open('x') as stderr:
        child=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr)
        try:
            rc=child.wait()
        finally:
            if child.poll() is None:
                child.terminate(); child.wait()
    save(attempt/'exit.json',{'returncode':rc,'wall_s':time.monotonic()-start,'stdout_sha256':sha(attempt/'stdout.log'),'stderr_sha256':sha(attempt/'stderr.log')})
    print(json.dumps({'returncode':rc,'logs':str(attempt)}))
    return rc


if __name__=='__main__':
    raise SystemExit(main())
