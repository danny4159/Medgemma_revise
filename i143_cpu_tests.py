"""실제 저장 경합·입력 변경 및 사전 판정 경계를 검사한다."""
import copy
import json
import subprocess
import sys
from i143_runtime import save,validate_record
from i143_decision import extension,swap_condition,ge
from i143_assess import score,compare
from i143_data import OUT
from i141_common import sha,digest,now


def main():
    d=OUT/'tests/cpu_final'; d.mkdir(parents=True,exist_ok=False); checks={}
    image=d/'input.txt'; image.write_text('fixture')
    row=dict(patient_id='p',images=[dict(path=str(image),sha256=sha(image))])
    r=dict(patient_id='p',condition='S',epoch=0,provenance={},input_hashes=[sha(image)],tokens=[1],n_tokens=1)
    r['digest']=digest(r); checks['valid']=validate_record(r,row,'S',0,{})
    for key in ['condition','epoch','patient_id','provenance','input_hashes','tokens','image_source_patient']:
        changed=copy.deepcopy(r); changed[key]='changed'
        try: validate_record(changed,row,'S',0,{}); checks[key]=False
        except (AssertionError,TypeError): checks[key]=True
    image.write_text('changed')
    try: validate_record(r,row,'S',0,{}); checks['input_change']=False
    except AssertionError: checks['input_change']=True
    script='import sys; from i143_runtime import save; save(sys.argv[1], {"winner":sys.argv[2]})'
    children=[subprocess.Popen([sys.executable,'-c',script,str(d/'race.json'),str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(2)]
    returns=[]
    for i,p in enumerate(children):
        stdout,stderr=p.communicate(); (d/f'child{i}.log').write_bytes(stdout+stderr); returns.append(p.returncode)
    checks['exclusive_race']=sorted(returns)==[0,1]
    checks['race_valid_json']=json.loads((d/'race.json').read_text())['winner'] in ['0','1']
    baseline={c:{'4':dict(recall=.5,target_nll=2.,contradiction_count=1),'8':dict(recall=.5,target_nll=2.,contradiction_count=1)} for c in ['S','A','N']}
    checks['no_extension']=not extension(baseline)['extend']
    x=copy.deepcopy(baseline); x['S']['8']['recall']=.52; checks['recall_extension']=extension(x)['extend']
    x=copy.deepcopy(baseline); x['A']['8']['target_nll']=1.9; checks['nll_extension']=extension(x)['extend']
    x['A']['8']['recall']=.49; checks['loss_only_reject']=not extension(x)['extend']
    x['A']['8']['recall']=.5; x['A']['8']['contradiction_count']=2; checks['contra_reject']=not extension(x)['extend']
    checks['tie_N']=swap_condition({c:v['8'] for c,v in baseline.items()})=='N'
    checks['roundoff_boundary']=ge(.05-1e-16,.05) and not ge(.049999,.05)
    p=dict(package_id='x',patient_id='p',text='high signal',eos=True,boundary='no_marker',atoms=[dict(id='a',type='signal'),dict(id='b',type='location')])
    j=dict(package_id='x',atoms={'a':dict(status='matched',quotes=['high signal']),'b':dict(status='unmatched')},
           contradictions=[],internal_contradictions=[],contradiction_unresolved=False,internal_unresolved=False)
    s=score(p,j); checks['complete_score']=s['recall']==s['recall_upper']==.5
    p['eos']=False; t=score(p,j); checks['truncation_bounds']=t['recall']==.5 and t['recall_upper']==1 and t['contradiction_upper']==1
    c=compare([t],[s]); checks['paired_bounds']=c['semantic_difference']==[0.,.5] and c['contradiction_difference']==[0.,1.]
    files={name:sha(name) for name in ['i143_runtime.py','i143_decision.py','i143_assess.py','i143_eval.py',__file__]}
    save(d/'checks.json',dict(created_at=now(),checks=checks,files=files,passed=all(checks.values())))
    print(checks); assert all(checks.values())


if __name__=='__main__':main()
