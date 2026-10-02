"""자료 gate의 실제 실패 분기와 결과 보존 회귀 검사. GPU 경로 검사가 아님."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import mt51_finish as F
import mt51_audit as A


def main():
    checks=[]
    def good(name, fn):
        fn(); checks.append({'name':name,'passed':True})
    def bad(name, fn, expected):
        try: fn()
        except (ValueError,FileExistsError) as e:
            assert expected in str(e),(name,str(e)); checks.append({'name':name,'passed':True,'expected_branch':expected,'observed':str(e)})
        else: raise AssertionError(name+' accepted')
    inp=F.load(F.OUT/'data/inference_candidates.json')[0]
    lab=F.load(F.OUT/'data/evaluation_private.json')[0]
    good('valid_allowlisted_input',lambda:F.validate_input(inp))
    good('valid_answer',lambda:F.validate_eval(lab,inp))
    for key in ('_eval','_audit','caption','findings','correct_answer','unknown'):
        row=copy.deepcopy(inp);row[key]='injected'
        bad('top_'+key,lambda row=row:F.validate_input(row),'input top-level allowlist')
    for key in ('caption','answer','unknown'):
        row=copy.deepcopy(inp);row['images'][0][key]='injected'
        bad('image_'+key,lambda row=row:F.validate_input(row),'image allowlist')
    row=copy.deepcopy(inp);row['images'].reverse()
    bad('image_order_swap',lambda:F.validate_input(row),'image order')
    row=copy.deepcopy(inp);row['images']=row['images'][:1]
    bad('image_missing',lambda:F.validate_input(row),'image count')
    row=copy.deepcopy(inp);row['images'][0]['file_sha256']='0'*64
    bad('original_digest_tamper',lambda:F.validate_input(row),'input file digest')
    row=copy.deepcopy(inp);row['options']['B']=row['options']['A']
    bad('duplicate_options',lambda:F.validate_input(row),'duplicate options')
    row=copy.deepcopy(lab);row['correct_answer']='F'
    bad('wrong_answer_letter',lambda:F.validate_eval(row,inp),'answer letter')
    row=copy.deepcopy(lab);row['correct_answer_text']='altered'
    bad('wrong_answer_text',lambda:F.validate_eval(row,inp),'answer text')
    bad('parent_escape',lambda:A.safe(A.ROOT/'results/iter_051/../../../../escape'),'path traversal')
    bad('outside_root',lambda:A.safe('/outside/research'),'path escape')
    with patch.object(Path,'is_symlink',lambda p:p.name=='iter_049'):
        bad('ancestor_symlink',lambda:A.safe(Path(A.C.R49)/'images/x.jpg'),'symlink')
    old=A.OLD/'decisions/history_part1.json'; prior=A.sha(old)
    bad('old_output_write',lambda:A.write(old,{}),'old output path forbidden')
    assert A.sha(old)==prior
    current=F.OUT/'audit/gate.json'; prior=A.sha(current)
    bad('output_overwrite',lambda:A.write(current,{}),'File exists')
    assert A.sha(current)==prior
    real=F.load
    def alter_visual(mode):
        def injected(p):
            obj=real(p)
            if Path(p).name=='b01.json':
                if mode=='missing': return obj[1:]
                if mode=='duplicate': return obj+[obj[0]]
                if mode=='invalid': obj[0]['evidence']='image_redo_01 inherited'
                if mode=='sheet': obj[0]['sheet_sha256']='0'*64
                if mode=='order': obj[0]['ordered_images'].reverse()
            return obj
        return patch.object(F,'load',injected)
    for mode,reason in [('missing','missing visual case'),('duplicate','duplicate/unknown'),('invalid','unverified inherited'),('sheet','visual source/order'),('order','visual source/order')]:
        with alter_visual(mode): bad('visual_'+mode,F.visual,reason)
    good('current_complete_visual',F.visual)
    assert F.capacity(169)['evaluation_cluster_upper_bound']==145 and not F.capacity(169)['run']
    assert not F.capacity(179)['run'] and F.capacity(180)['run']
    checks.append({'name':'fixed_156_cluster_upper_bound_and_boundary','passed':True})
    bad('changed_gate_threshold',lambda:F.capacity(169,minimum=145),'fixed gate settings')
    result={'status':'PASS','checks':checks,'passed':len(checks),'scope':'CPU 자료 검증 경로만. 실제 GPU 생성·재개/동시성 검증 미실행.',
            'code_sha256':{n:A.sha(F.ROOT/n) for n in ('mt51_audit.py','mt51_finish.py','test_mt51.py')},
            'gate_sha256':A.sha(F.OUT/'audit/gate.json')}
    A.write(F.OUT/'tests/fixtures.json',result)
    print('PASS',len(checks))

if __name__=='__main__': main()
