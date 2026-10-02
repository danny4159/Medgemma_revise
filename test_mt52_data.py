"""자료 재사용 경계·공식 객체 검증 및 추론 manifest 분리 회귀 검사."""
import copy
import hashlib
import json
import os
from pathlib import Path
from mt52_prepare import ROOT, OUT, safe, save, candidates, verify_object, sha256_file
from mt49_audit import infer_view, schema_problems, answer_problems

def main():
    t=OUT/'tests/data';t.mkdir(parents=True,exist_ok=True)
    results=[]
    def check(name,condition):
        assert condition,name
        results.append({'name':name,'pass':True})
    def reject(name,fn):
        try:fn()
        except (ValueError,AssertionError):results.append({'name':name,'pass':True});return
        raise AssertionError(name)
    reject('old output forbidden',lambda:safe(ROOT/'results/iter_051/new.json',True))
    reject('path traversal',lambda:safe(OUT/'x/../z',True))
    sy=t/'symlink';sy.symlink_to(t,target_is_directory=True)
    reject('ancestor symlink',lambda:safe(sy/'child',True))
    p=t/'object.bin';p.write_bytes(b'abc')
    sha=hashlib.sha256(b'abc').hexdigest()
    ent={'size':3,'lfs':{'oid':sha}}
    verify_object(p,ent);check('official LFS object',True)
    reject('existing size mismatch',lambda:verify_object(p,{**ent,'size':4}))
    reject('existing hash mismatch',lambda:verify_object(p,{'size':3,'lfs':{'oid':'0'*64}}))
    blob=hashlib.sha1(b'blob 3\0abc').hexdigest()
    verify_object(p,{'size':3,'oid':blob});check('git blob object',True)
    q=t/'exclusive.json';save(q,{'a':1});save(q,{'a':1})
    reject('changed result cannot overwrite',lambda:save(q,{'a':2}))
    cs=candidates();check('607 cases 2909 images',len(cs)==607 and sum(r['image_count'] for r in cs)==2909)
    for r in cs:
        v=infer_view(r)
        assert set(v)=={'case_key','CLINICAL_HISTORY','options','images'}
        assert all(set(im)=={'id','path'} for im in v['images'])
    check('nested inference allowlist all candidates',True)
    c=copy.deepcopy(cs[0]);c['image_01_path']='../x.jpg'
    check('bad image path refused',bool(schema_problems(c)))
    c=copy.deepcopy(cs[0]);c['correct_answer_text']='wrong'
    check('answer mismatch refused',bool(answer_problems(c)))
    save(OUT/'tests/data_fixtures.json',{'status':'PASS','checks':results,
        'sources':{p:sha256_file(ROOT/p) for p in ['mt52_prepare.py','test_mt52_data.py','mt49_audit.py']}})
    print('PASS',len(results))

if __name__=='__main__':main()
