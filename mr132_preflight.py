"""공식 MR-ART 점수·공개 IQM·원 영상 객체 연결 후 고정 환자 분할."""
import csv, io, re, requests, hashlib, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from mr132_common import RES, DATA, REV, IQREV, sha, save, now, digest

def fetch(url,path):
    r=requests.get(url,timeout=90); r.raise_for_status()
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'xb') as f: f.write(r.content)
    return dict(url=url,final_url=r.url,path=str(path),sha256=sha(path),bytes=len(r.content))

def rows(path):
    rr=list(csv.DictReader(path.open(),delimiter='\t'))
    keys=[r['bids_name'] for r in rr]
    if len(set(keys))!=len(keys): raise ValueError('duplicate bids_name:'+str(path))
    return {r['bids_name']:r for r in rr}

def order(subject): return hashlib.sha256(('132:'+subject).encode()).hexdigest()

def main():
    meta=RES/'metadata'; meta.mkdir(parents=True,exist_ok=False)
    official=f'https://raw.githubusercontent.com/OpenNeuroDatasets/ds004173/{REV}/'
    iq=f'https://raw.githubusercontent.com/brainhack-ch/interpret-iqms/{IQREV}/'
    sources={}
    for name,url in [('scores.tsv',official+'derivatives/scores.tsv'),('dataset_description.json',official+'dataset_description.json'),('README',official+'README'),('IQMs.tsv',iq+'data/IQMs.tsv'),('scores_replica.tsv',iq+'data/scores.tsv'),('iqm_README.md',iq+'README.md')]:
        sources[name]=fetch(url,meta/name)
    sources['tree.json']=fetch(f'https://api.github.com/repos/OpenNeuroDatasets/ds004173/git/trees/{REV}?recursive=1',meta/'tree.json')
    import json
    tree=json.loads((meta/'tree.json').read_text()); assert not tree['truncated']
    files={r['path']:r for r in tree['tree']}
    scores=rows(meta/'scores.tsv'); replica=rows(meta/'scores_replica.tsv'); iqms=rows(meta/'IQMs.tsv')
    score_diff={k:[scores.get(k),replica.get(k)] for k in set(scores)|set(replica) if scores.get(k)!=replica.get(k)}
    if score_diff: raise ValueError('official/replica mismatch')
    def link(item):
        k,r=item
        match=re.fullmatch(r'(sub-\d+)_acq-(standard|headmotion1|headmotion2)_T1w',k)
        if not match: raise ValueError('unrecognized BIDS key:'+k)
        sub,acq=match.groups(); path=f'{sub}/anat/{k}.nii.gz'
        score=int(r['score']); assert score in [1,2,3]
        rec=dict(bids_name=k,subject=sub,acq=acq,score=score,iqm_join=k in iqms,github_path=path)
        if path not in files: return dict(rec,error='missing_github_path')
        try:
            r=requests.get(official+path,timeout=60); r.raise_for_status()
            pointer=r.text.strip(); m=re.search(r'MD5E-s(\d+)--([a-f0-9]{32})\.nii\.gz',pointer)
            if not m: raise ValueError('not annex MD5E pointer')
            size,md5=int(m[1]),m[2]
            blob=hashlib.sha1(b'blob '+str(len(r.content)).encode()+b'\0'+r.content).hexdigest()
            assert blob==files[path]['sha']
            url='https://s3.amazonaws.com/openneuro.org/ds004173/'+path
            h=requests.head(url,timeout=60); h.raise_for_status()
            assert int(h.headers['Content-Length'])==size
            assert h.headers['ETag'].strip('"')==md5
            return dict(rec,annex_pointer=pointer,annex_blob=blob,bytes=size,md5=md5,url=url,final_url=h.url,version_id=h.headers.get('x-amz-version-id'),etag=h.headers['ETag'],error=None)
        except Exception as e: return dict(rec,error=repr(e))
    with ThreadPoolExecutor(max_workers=12) as pool: linked=list(pool.map(link,sorted(scores.items())))
    subjects=sorted({r['subject'] for r in linked},key=order)
    eligible=[]; excluded=[]
    for sub in subjects:
        rr=[r for r in linked if r['subject']==sub]
        issues=[]
        if {r['acq'] for r in rr}!={'standard','headmotion1','headmotion2'}: issues.append('incomplete_three_acquisitions')
        if any(not r['iqm_join'] for r in rr): issues.append('missing_iqm')
        if any(r.get('error') for r in rr): issues.append('object_link_failed')
        if issues: excluded.append(dict(subject=sub,issues=issues))
        else: eligible.append(sub)
    audit=dict(created_at=now(),sources=sources,revision=REV,iqm_revision=IQREV,license='CC0',score_rows=len(scores),iqm_rows=len(iqms),replica_mismatches=len(score_diff),subjects=len(subjects),eligible_subjects=len(eligible),excluded=excluded,score_distribution=dict(Counter(r['score'] for r in linked)),iqm_unmatched_keys=sorted(set(iqms)-set(scores)),iqm_missing_cells={c:sum(r[c].strip().lower() in ['','nan','n/a'] for r in iqms.values()) for c in next(iter(iqms.values())) if c!='bids_name'},objects=linked,source_code={__file__:sha(__file__)},conditions_met=len(eligible)>=126)
    save(RES/'metadata_audit.json',audit)
    return select(audit)

def select(audit):
    linked=audit['objects']; eligible=sorted({r['subject'] for r in linked}-{r['subject'] for r in audit['excluded']},key=order)
    if len(eligible)<126:
        print('자료 조건 실패:',len(eligible),'명; 규모 재설정 없이 종료'); return 2
    assert 'sub-000103' in eligible
    tech=['sub-000103']+[s for s in eligible if s!='sub-000103'][:5]
    available=[s for s in eligible if s not in tech]
    def tie(s):
        rr={r['acq']:r['score'] for r in linked if r['subject']==s}
        return rr['headmotion1']==rr['headmotion2']
    counts={str(v):sum(tie(s)==v for s in available) for v in [True,False]}
    def stratified_take(n):
        nonlocal available
        a=[s for s in available if tie(s)][:n//2]; b=[s for s in available if not tie(s)][:n//2]
        selected=a+b
        if len(selected)<n: selected += [s for s in available if s not in selected][:n-len(selected)]
        available=[s for s in available if s not in selected]
        return sorted(selected,key=order)
    # 평가·보존의 1:1 층화를 먼저 보장하고 잔여 hash 순서에서 IQM 학습60명을 선택한다.
    dev=stratified_take(40); hold=stratified_take(20); train=available[:60]
    assert len(train)==60
    splits=dict(technical=tech,iqm_train=train,development=dev,holdout=hold)
    selected=set(tech+dev+hold)
    max_objects=[r for r in linked if r['subject'] in selected]
    initial=[r for r in max_objects if r['subject'] in tech+dev]
    sizes=dict(initial_bytes=sum(r['bytes'] for r in initial),conditional_total_bytes=sum(r['bytes'] for r in max_objects),n_initial_volumes=len(initial),n_conditional_total_volumes=len(max_objects),external_free_bytes=shutil.disk_usage(DATA.parent.parent).free,estimated_uncompressed_bytes=198*256*256*256*4,estimated_png_upper_bytes=198*8*896*896*3)
    assert sizes['conditional_total_bytes']<=10*1024**3
    assert sizes['external_free_bytes']>sum([sizes['conditional_total_bytes'],sizes['estimated_uncompressed_bytes'],sizes['estimated_png_upper_bytes']])
    split=dict(created_at=now(),seed=132,hash_rule='sha256(132:subject)',allocation_order=['technical','development','holdout','iqm_train'],splits=splits,strata={stage:dict(Counter('headmotion_tie' if tie(s) else 'headmotion_nontie' for s in ss)) for stage,ss in splits.items()},sampling=dict(remaining_after_tech_counts=counts,development_inclusion_probability={str(v):sum(tie(s)==v for s in dev)/counts[str(v)] for v in [True,False]}),objects=max_objects,budget=sizes,metadata_audit_sha256=sha(RES/'metadata_audit.json'),holdout_note='계획 단계 점수는 열람됨; 영상과 모델 출력은 설정 선택에 사용하지 않음')
    save(RES/'split_lock.json',split)
    print('자료 조건 통과:',len(eligible),'명; 분할', {k:len(v) for k,v in splits.items()},'용량',sizes)
    return 0

if __name__=='__main__':
    if '--select-only' in sys.argv:
        from mr132_common import read
        audit=read(RES/'metadata_audit.json')
        assert all(sha(x['path'])==x['sha256'] for x in audit['sources'].values())
        sys.exit(select(audit))
    sys.exit(main())
