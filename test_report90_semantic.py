"""현재 의미 집계 규약의 최소 회귀 검사. 임상 의미의 자동 인증은 아니다."""
from copy import deepcopy
from report90_semantic_eval import score
from report90_numeric import OUT
from report86_common import save,sha

def main():
    ref=dict(id='x',patient='p',abnormal=True,atoms=[dict(id='a',polarity='positive',certainty='definite',ambiguous=False),dict(id='b',polarity='positive',certainty='possible',ambiguous=True)])
    out=dict(blind_id='b',text='Small left effusion. Possible mass.',non_eos=False)
    j=dict(matches=[dict(ref='a',status='strict',quote='Small left effusion.',location='match',attributes='match',ambiguous=False)],
        claims=[dict(finding='effusion',polarity='positive',certainty='definite',status='supported',quote='Small left effusion.',refs=['a']),
                dict(finding='mass',polarity='positive',certainty='possible',status='unknown',quote='Possible mass.',refs=[])],internal_conflicts=[])
    checks=[]
    def check(name,v):checks.append(dict(name=name,passed=bool(v)));assert v,name
    s=score(ref,out,j);check('strict_and_unknown_not_FP',s['strict_recall']==1 and not s['contradiction'] and s['claim_counts']['unknown']==1)
    q=deepcopy(j);q['matches'][0]['status']='possible_only';s=score(ref,out,q);check('possible_not_definite',s['strict_recall']==0 and s['possible_only']==1)
    q=deepcopy(j);q['matches'][0].update(status='type_only',location='missing');s=score(ref,out,q);check('location_required',s['strict_recall']==0 and s['type_recall']==1)
    q=deepcopy(j);q['matches'][0]['ambiguous']=True;s=score(ref,out,q);check('sensitivity',s['strict_recall']==1 and s['no_ambiguous_match']==0)
    for name,change in [('false_anchor',lambda q:q['matches'][0].update(quote='not in text')),('strict_missing_location',lambda q:q['matches'][0].update(location='missing')),('duplicate_match',lambda q:q['matches'].append(q['matches'][0].copy()))]:
        q=deepcopy(j);change(q)
        try:score(ref,out,q);ok=False
        except AssertionError:ok=True
        check(name,ok)
    specific=deepcopy(ref);specific['atoms'][0].update(location='left',attributes='small')
    for field in ['location','attributes']:
        q=deepcopy(j);q['matches'][0][field]='na'
        try:score(specific,out,q);ok=False
        except AssertionError:ok=True
        check('required_'+field,ok)
    save(OUT/'tests/semantic_fixtures_v2.json',dict(passed=all(c['passed'] for c in checks),checks=checks,source_sha={p:sha(p) for p in [__file__,'report90_semantic_eval.py']}))

if __name__=='__main__':main()
