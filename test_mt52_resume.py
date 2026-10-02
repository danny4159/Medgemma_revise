"""실제 중단·worker 수 변경·부분 파일 보존 및 greedy token 회귀."""
import json
import os
import subprocess
import sys
import time
from mt52_prepare import ROOT,OUT,save,sha256_file
from mt52_verify import verify

def main():
    job=OUT/'tests/resume_current';job.mkdir(parents=True,exist_ok=False)
    prefix=[sys.executable,str(ROOT/'mt52_run.py'),'--job',str(job.relative_to(ROOT)),
        '--inference','results/iter_052/data/P4_inference.json','--images','results/iter_052/data/D_images.json',
        '--only','T,D','--peak-gib','9']
    children=[]
    try:
        with (job/'initial.log').open('x') as log:
            proc=subprocess.Popen(prefix+['--workers','1'],stdout=log,stderr=log);children.append(proc)
            while len(list((job/'records').glob('*/*.json')))<3:
                assert proc.poll() is None,'initial process ended early'
                time.sleep(1)
            proc.terminate();rc=proc.wait(timeout=60);assert rc!=0
        before={str(p.relative_to(job)):sha256_file(p) for p in (job/'records').glob('*/*.json')}
        assert 0<len(before)<8
        partial=job/'records/c445/D.json.partial.interrupted_fixture'
        partial.parent.mkdir(parents=True,exist_ok=True);partial.write_bytes(b'{"interrupted":')
        partial_hash=sha256_file(partial)
        with (job/'resume.log').open('x') as log:
            proc=subprocess.Popen(prefix+['--workers','2'],stdout=log,stderr=log);children.append(proc)
            assert proc.wait()==0
        result=verify(job);assert result['requests']==8
        assert all(sha256_file(job/p)==h for p,h in before.items()) and sha256_file(partial)==partial_hash
        base=OUT/'pilot/P4_2w';compared=[]
        for p in sorted((job/'records').glob('*/*.json')):
            q=base/'records'/p.parent.name/p.name;a=json.loads(p.read_text());b=json.loads(q.read_text())
            assert a['tokens']==b['tokens'] and a['input_tokens']==b['input_tokens']
            for field in ['case','stage','prompt','images','parents','cap']:assert a['spec'][field]==b['spec'][field]
            compared.append({'new':str(p.relative_to(ROOT)),'base':str(q.relative_to(ROOT)),
                'new_sha256':sha256_file(p),'base_sha256':sha256_file(q)})
        cfg=subprocess.run(prefix+['--workers','1','--double-caps','D'],capture_output=True,text=True)
        assert cfg.returncode!=0 and 'requested configuration mismatch' in cfg.stderr
        save(OUT/'tests/resume_current_result.json',{'status':'PASS','interrupted_exit':rc,'committed_before':len(before),
            'worker_change':[1,2],'requests':8,'tokens_equal':8,'partial_preserved':True,'wrong_config_rejected':True,
            'integrity':result,'comparisons':compared,'source_sha256':sha256_file(__file__)})
        print('PASS interrupted',len(before),'resumed 8 tokens equal')
    finally:
        for proc in children:
            if proc.poll() is None:proc.terminate()
        for proc in children:
            try:proc.wait(timeout=60)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

if __name__=='__main__':main()
