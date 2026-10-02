"""현재 실행 소스의 실패 분기와 자료 gate 근거를 재검증한다."""
import copy
import json
import shutil
import subprocess
import sys
from mt52_prepare import ROOT,OUT,save,sha256_file
from mt52_verify import verify
from mt52_run import atomic
from mt52_spec import digest,check_case,parse
from mt52_audit import load,choose
from mt52_audit_finish import validate
from rsna_diag.queue_lock import try_lock,my_info

def main():
    dest=OUT/'tests/final_fixtures';dest.mkdir(parents=True,exist_ok=False);checks=[]
    def reject(name,fn,needle):
        try:fn()
        except Exception as e:
            assert needle in str(e),(name,str(e));checks.append({'name':name,'pass':True,'branch':str(e)})
        else:raise AssertionError('accepted '+name)
    base=OUT/'pilot/D8_graph_v2';verify(base);checks.append({'name':'current_complete_D8_graph','pass':True})
    for name,change,needle in [
        ('wrong_prompt',lambda x:x['spec'].__setitem__('prompt','changed'),'request mismatch'),
        ('wrong_parent',lambda x:x['spec'].__setitem__('parents',['wrong']),'request mismatch'),
        ('image_order',lambda x:x['spec'].__setitem__('images',list(reversed(x['spec']['images']))),'request mismatch')]:
        job=dest/name;shutil.copytree(base,job)
        p=job/'records/c2924/D.json';r=json.loads(p.read_text());r.pop('record_digest');change(r);r['record_digest']=digest(r);p.write_text(json.dumps(r))
        reject(name,lambda:verify(job),needle)
    job=dest/'missing';job.mkdir();shutil.copyfile(base/'protocol.json',job/'protocol.json')
    reject('missing_record',lambda:verify(job),'No such file')
    job=dest/'extra';shutil.copytree(base,job);shutil.copyfile(job/'records/c2924/D.json',job/'records/c2924/extra.json')
    reject('extra_record',lambda:verify(job),'missing/extra')
    reject('immutable_result',lambda:atomic(job/'protocol.json',{}),'File exists')
    bad=copy.deepcopy(json.loads((OUT/'data/D_inference.json').read_text())[0]);bad['images'][0]['caption']='answer'
    reject('nested_answer_leak',lambda:check_case(bad),'image fields')
    assert parse('Answer: A\nAnswer: B') is None and parse('Answer: A or B') is None and parse('Answer: C')=='C'
    checks.append({'name':'ambiguous_parser','pass':True})
    lk,_,_=try_lock(job/'launch.lock',my_info());assert lk
    try:
        r=subprocess.run([sys.executable,'mt52_run.py','--job',str(job.relative_to(ROOT))],capture_output=True,text=True)
        assert r.returncode!=0 and 'launcher already running' in r.stderr
        checks.append({'name':'live_launcher_rejected','pass':True})
    finally:lk.release()
    order,raw,dec=load();found=json.loads((OUT/'provenance/all_image_returns_v2.json').read_text())['returns'];validate(order,dec,found)
    missing=dict(found);missing.pop(order[0]['case_key'])
    reject('unreturned_image_rejected',lambda:validate(order,dec,missing),'missing actual image return')
    missing=dict(dec);missing.pop(order[0]['case_key'])
    reject('implicit_keep_rejected',lambda:validate(order,missing,found),'missing/extra audit decision')
    bad=copy.deepcopy(dec);bad[order[0]['case_key']]['sheet_sha256']='bad'
    reject('audit_tamper_rejected',lambda:validate(order,bad,found),'audit sheet mismatch')
    bad=copy.deepcopy(dec);bad[order[0]['case_key']]['raw_source_sha256']='bad'
    reject('audit_source_tamper',lambda:validate(order,bad,found),'audit source mismatch')
    gate=json.loads((OUT/'audit/data_gate.json').read_text())
    for p,h in gate['source_digests'].items():assert sha256_file(ROOT/p)==h
    selected,pending,stage=choose(order,dec);assert stage=='E_insufficient' and not pending and len(selected)==287
    clusters=json.loads((OUT/'data/clusters.json').read_text())['clusters']
    members=[k for c in clusters for k in c['members']];assert len(members)==len(set(members))==607
    assert len({r['case_key'] for r in selected})==len(selected)
    checks.append({'name':'all_source_cluster_split_gate','pass':True})
    save(OUT/'tests/final_fixtures.json',{'status':'PASS','checks':checks,'n':len(checks),'source':sha256_file(__file__)})
    print('PASS',len(checks))

if __name__=='__main__':main()
