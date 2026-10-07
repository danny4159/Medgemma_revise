"""실제 생성 검증 진입점의 실행 설정·요청·봉인 변조 거부 회귀."""
import copy
import json
from pathlib import Path
from report90_numeric import OUT
from report86_common import save,sha
import report90_gen_safe as S

def main():
    root=OUT/'tests/runtime_tamper';root.mkdir(parents=True,exist_ok=False)
    prior=OUT/'tests/gen_resume';out=prior/'run';req=prior/'requests.json';proto=S.protocol(req,None)
    checks=[]
    def check(name,fn):
        try:fn()
        except (AssertionError,ValueError,FileNotFoundError) as e:checks.append(dict(name=name,rejected=True,error=repr(e)))
        else:checks.append(dict(name=name,rejected=False))
    wrong=copy.deepcopy(proto);wrong['seed']=29;check('seed_config_changed',lambda:S.verify(out,req,wrong,1))
    wrong=copy.deepcopy(proto);wrong['caps']=[32];check('cap_config_changed',lambda:S.verify(out,req,wrong,1))
    changed=json.loads(req.read_text());changed[0]['prompt']+=' altered';path=root/'changed_requests.json';save(path,changed)
    check('request_changed',lambda:S.verify(out,path,proto,1))
    dest=root/'seal_changed';dest.mkdir();(dest/'worker_0.jsonl').write_bytes((out/'worker_0.jsonl').read_bytes())
    seal=json.loads((out/'completion.json').read_text());seal['files']={str(dest/'worker_0.jsonl'):'0'*64};save(dest/'completion.json',seal)
    check('sealed_hash_changed',lambda:S.verify(dest,req,proto,1))
    check('wrong_worker_partition',lambda:S.verify(out,req,proto,2))
    # 고정 rows를 먼저 읽고 검증하므로 checkpoint/입력 조건 변조는 모델 적재 전에 거부된다.
    original,_=S.verify(out,req,proto,1);assert len(original)==2
    save(root/'result.json',dict(passed=all(x['rejected'] for x in checks),checks=checks,source_sha256=sha(__file__),positive_complete_rows=len(original)))
    print(json.dumps(checks),flush=True)
    assert all(x['rejected'] for x in checks)

if __name__=='__main__':main()
