"""생산 gate를 호출하지 않는 범위 제한 독립 재집계 및 digest 봉인."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/iter_051'

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def read(p): return json.loads(Path(p).read_text())

def save(p,obj):
    if p.exists(): raise FileExistsError(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f: json.dump(obj,f,ensure_ascii=False,indent=2)

def verify():
    paths=[OUT/'audit/source_check.json',OUT/'audit/history_linked.json',OUT/'audit/visual_resolutions.json',OUT/'audit/gate.json',OUT/'audit/case_decisions.json',OUT/'audit/duplicate_candidates.json',OUT/'data/inference_candidates.json',OUT/'data/evaluation_private.json',OUT/'tests/fixtures.json']
    paths += [OUT/'audit/visual'/f'b{i:02}.json' for i in range(1,40)]
    paths += [ROOT/n for n in ('mt51_audit.py','mt51_finish.py','test_mt51.py','mt51_verify.py','mt50_common.py','mt50_prep.py')]
    before={str(p):sha(p) for p in paths}
    src=read(OUT/'audit/source_check.json'); expected={r['case_id']:r for r in src['cases']}
    vis={}
    for i in range(1,40):
        for r in read(OUT/'audit/visual'/f'b{i:02}.json'):
            assert r['case_id'] not in vis
            assert r['ordered_images']==expected[r['case_id']]['ordered_images']
            assert sha(ROOT/r['sheet'])==r['sheet_sha256']
            vis[r['case_id']]=r['visual_status']
    assert set(vis)==set(expected) and len(vis)==254
    for r in read(OUT/'audit/visual_resolutions.json'):
        assert vis[r['case_id']]=='pending';vis[r['case_id']]=r['visual_status']
    assert 'pending' not in vis.values()
    hist=read(OUT/'audit/history_linked.json')
    hr={r['case_id']:r['history_status'] for r in hist['records']}
    assert set(hr)==set(vis) and len(hist['records'])==254
    eligible={c for c in vis if vis[c]=='keep' and hr[c]=='keep'}
    inp=read(OUT/'data/inference_candidates.json'); labs=read(OUT/'data/evaluation_private.json')
    assert len(inp)==len(labs)==len(eligible)==169
    assert {r['id'] for r in inp}=={r['id'] for r in labs}==eligible
    raw={}
    rawpath=ROOT/'results/iter_049/raw/train.jsonl'
    for line in rawpath.open():
        r=json.loads(line);cid=r['title'].replace('Case number ','c')
        if cid in expected:
            assert cid not in raw;raw[cid]=r
    assert set(raw)==set(expected)
    labels={r['id']:r for r in labs}
    images=0
    for r in inp:
        rr=raw[r['id']];lab=labels[r['id']]
        assert set(r)=={'id','history','options','images'}
        assert r['history']==rr['CLINICAL_HISTORY'] and r['options']==rr['options']
        assert lab['correct_answer']==rr['correct_answer'] and lab['correct_answer_text']==rr['correct_answer_text']
        assert r['options'][lab['correct_answer']]==lab['correct_answer_text']
        assert len(r['images'])==rr['image_count']
        for i,im in enumerate(r['images']):
            assert set(im)=={'index','path','file_sha256','rgb_pixel_sha256'} and im['index']==i
            assert im['path']=='results/iter_049/'+rr[f'image_{i+1:02}_path']
            assert sha(ROOT/im['path'])==im['file_sha256'];images+=1
    gate=read(OUT/'audit/gate.json');fixtures=read(OUT/'tests/fixtures.json')
    assert fixtures['status']=='PASS' and all(r['passed'] for r in fixtures['checks'])
    for n,h in fixtures['code_sha256'].items(): assert sha(ROOT/n)==h
    assert fixtures['gate_sha256']==sha(OUT/'audit/gate.json')
    assert gate['eligible_cases']==len(eligible) and gate['eligible_images']==images==559
    assert gate['visual_counts']==dict(Counter(vis.values()))
    assert gate['history_counts']==dict(Counter(hr.values()))
    upper=len(eligible)-24
    assert upper==145<156 and gate['evaluation_cluster_upper_bound']==upper
    assert gate['run_gpu'] is False and gate['hypothesis_tested'] is False
    assert all(sha(p)==h for p,h in before.items())
    # 검증 대상과 출처 전체를 completion에 연결한다. stream은 상위 읽기 전용 자산이다.
    dependencies={str(rawpath):sha(rawpath),hist['stream']:sha(hist['stream'])}
    for r in src['cases']:
        dependencies[str(ROOT/r['sheet'])]=r['sheet_sha256']
        for im in r['ordered_images']: dependencies[str(ROOT/'results/iter_049'/im['path'])]=im['file_sha256']
    for r in src['previous_audits']: dependencies[str(ROOT/r['path'])]=r['sha256']
    for p in [ROOT.parent/'agent/runs/iter_051/plan.md',ROOT.parent/'agent/runs/iter_051/plan.json',ROOT.parent/'agent/runs/iter_050/plan.md',ROOT.parent/'agent/runs/iter_050/plan.json',ROOT/'results/iter_049/audit_v2/eligible_cases.jsonl',ROOT/'results/iter_049/image_manifest.json']:
        dependencies[str(p)]=sha(p)
    assert all(sha(p)==h for p,h in dependencies.items())
    result={'status':'PASS','verified_files':before,'source_files':dependencies,'eligible_cases':len(eligible),'eligible_images':images,'evaluation_cluster_upper_bound':upper,'scope':'원본 연결·감사 집계·불충분 표본 상한만 검증. 영상 판정의 독립 임상 재판독이나 모델 실험 승인 아님.'}
    save(OUT/'verification/independent.json',result)
    save(OUT/'completion.json',{'status':'COMPLETE_DATA_GATE_FAIL','run_gpu':False,'hypothesis_tested':False,'self_check':'FAIL','verifier_sha256':sha(OUT/'verification/independent.json'),'verified_files':before,'source_files':dependencies,'unperformed':['near-duplicate 후보 수동 확정/실제 cluster split','모델·processor·실제 출력·실행기 재개 검증','T/D/C/R/X 비교'],'reason':'E cluster 상한145<156. 사전 자료 종료 조건 적용.'})
    print('PASS: independent data gate verification; E clusters <=145 <156')

def check():
    c=read(OUT/'completion.json');v=read(OUT/'verification/independent.json')
    assert c['verifier_sha256']==sha(OUT/'verification/independent.json')
    assert v['status']=='PASS'
    for k in ('verified_files','source_files'):
        assert c[k]==v[k]
        for p,h in c[k].items(): assert sha(p)==h,p
    print('PASS: sealed files and sources unchanged')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','check']);a=p.parse_args();globals()[a.action]()
