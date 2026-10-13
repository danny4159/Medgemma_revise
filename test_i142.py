"""현재 실행에 필요한 잠금·완료·평가 분기만 검사한다."""
import copy
import subprocess
from i142_common import *
from i142_eval import score,decision

def main():
    checks={}
    root=RES/'tests'/('cpu_'+str(time.time_ns()))
    root.mkdir(parents=True)
    p=root/'atomic.json'
    save(p,{'a':1})
    try:
        save(p,{'a':2})
    except FileExistsError:
        checks['overwrite_rejected']=read(p)=={'a':1}
    with ownership(root/'lock'):
        command=[str(ENV),'-c',"from i142_common import ownership;\nwith ownership("+repr(str(root/'lock'))+"):\n print('wrong')"]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        checks['concurrent_owner_rejected']=result.returncode!=0 and 'BlockingIOError' in result.stderr
    (root/'duplicate.json').write_text('{"a":1,"a":2}')
    try:
        read(root/'duplicate.json')
    except ValueError:
        checks['duplicate_key_rejected']=True
    (root/'broken.json').write_text('{"unfinished":')
    try:
        read(root/'broken.json')
    except ValueError:
        checks['corrupt_json_rejected']=True
    protocol=verify_protocol(RES/'protocol_technical_v2.json')
    bad=copy.deepcopy(protocol)
    bad['seed']=99
    save(root/'bad_protocol.json',bad)
    try:
        verify_protocol(root/'bad_protocol.json')
    except AssertionError:
        checks['wrong_protocol_rejected']=True
    ref={'positive_atoms':[{'id':'x','type':'signal'}]}
    j={'atoms':{'x':{'state':'unmentioned','quotes':[]}},'reference_contradictions':[],
       'internal_contradictions':[],'report_unverified':[]}
    r={'report':'','complete':False,'patient_id':'fixture'}
    s=score(r,ref,j)
    checks['incomplete_recall_upper']=s['recall_min']==0 and s['recall_max']==1
    checks['incomplete_contra_upper']=s['reference_contradiction_min']==0 and s['reference_contradiction_max']==1
    checks['positive_boundary']=decision({'recall_range':[.05,.1],'contradiction_range':[0,.05]},True)=='positive_development_recovery'
    checks['inconclusive_bounds']=decision({'recall_range':[-.1,.2],'contradiction_range':[0,0]},True)=='inconclusive'
    checks['negative_completed']=decision({'recall_range':[-.1,.04],'contradiction_range':[0,0]},True)=='negative_current_RGv2_DWI'
    checks['incomplete_not_negative']=decision({'recall_range':[-.1,.04],'contradiction_range':[0,1]},False)=='inconclusive'
    j['atoms']['x']={'state':'matched','quotes':['not present']}
    try:
        score(r,ref,j)
    except AssertionError:
        checks['false_quote_rejected']=True
    result={'created_at':now(),'checks':checks,'all_pass':all(checks.values()),'source_sha256':sha(__file__)}
    save(root/'checks.json',result)
    print(result)
    assert len(checks)==12 and result['all_pass']

if __name__=='__main__':
    import time
    main()
