"""실제 완료 pilot의 provenance/누락/중복/동시 실행 거부 회귀 검사."""
import copy
import json
import shutil
import subprocess
import sys
from mt52_prepare import ROOT,OUT,save
from mt52_verify import verify
from mt52_run import atomic
from mt52_spec import digest,check_case,parse

def main():
    base=OUT/'pilot/P4_2w';dest=OUT/'tests/run_fixtures';dest.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,fn,needle):
        try:fn()
        except Exception as e:
            assert needle in str(e),(name,str(e));checks.append({'name':name,'pass':True,'error':str(e)})
        else:raise AssertionError('accepted '+name)
    verify(base);checks.append({'name':'complete_real_pilot','pass':True})
    for name,change,needle in [
        ('wrong_prompt',lambda x:x['spec'].__setitem__('prompt','changed'),'request mismatch'),
        ('wrong_parent',lambda x:x['spec'].__setitem__('parents',['wrong']),'request mismatch'),
        ('image_order',lambda x:x['spec'].__setitem__('images',list(reversed(x['spec']['images']))),'request mismatch')]:
        job=dest/name;shutil.copytree(base,job)
        p=job/'records/c2924/D.json';r=json.loads(p.read_text());r.pop('record_digest');change(r);r['record_digest']=digest(r);p.write_text(json.dumps(r))
        check(name,lambda:verify(job),needle)
    job=dest/'missing';job.mkdir();shutil.copyfile(base/'protocol.json',job/'protocol.json')
    check('missing_records',lambda:verify(job),'No such file')
    job=dest/'extra';shutil.copytree(base,job);shutil.copyfile(job/'records/c2924/D.json',job/'records/c2924/extra.json')
    check('extra_record',lambda:verify(job),'missing/extra')
    check('overwrite',lambda:atomic(dest/'extra/protocol.json',{}),'File exists')
    cs=json.loads((OUT/'data/P4_inference.json').read_text());bad=copy.deepcopy(cs[0]);bad['images'][0]['caption']='answer'
    check('nested_answer_leak',lambda:check_case(bad),'image fields')
    assert parse('Answer: A\nAnswer: B') is None and parse('Answer: A or B') is None and parse('Answer: C')=='C'
    checks.append({'name':'ambiguous_parser','pass':True})
    cmd=[sys.executable,'mt52_run.py','--job','results/iter_052/pilot/D8_graph','--inference','results/iter_052/data/D8_inference.json']
    r=subprocess.run(cmd,capture_output=True,text=True)
    assert r.returncode!=0 and 'launcher already running' in r.stderr
    checks.append({'name':'live_launcher_refused','pass':True,'returncode':r.returncode,'stderr':r.stderr})
    save(OUT/'tests/run_fixtures_result.json',{'checks':checks,'n':len(checks),'status':'PASS'})
    print('PASS',len(checks))

if __name__=='__main__':main()
