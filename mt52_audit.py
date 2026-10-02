"""CT 의미 감사 순서·명시적 판정·고정 D/E 집합. 미확인은 자동 유지하지 않는다."""
import argparse
import json
from mt52_prepare import ROOT, OUT, save, safe, sha256_file
from mt52_cluster import rank

def load():
    order=json.loads((OUT/'audit/representative_order.json').read_text())
    raw={r['title']:r for r in json.loads((OUT/'audit/candidates_private.json').read_text())}
    decisions={}
    for p in sorted((OUT/'audit/decisions').glob('*.json')):
        for r in json.loads(p.read_text()):
            if r['case_key'] in decisions: raise ValueError('duplicate decision')
            decisions[r['case_key']]=r
    return order,raw,decisions

def choose(order,dec):
    def good(r):
        d=dec.get(r['case_key'],{})
        return d.get('visual')=='keep' and d.get('history')=='keep'
    def pending(r): return r['case_key'] not in dec
    selected=[]
    # 최장 적격을 먼저 확정하며 동률은 고정 hash 순서다.
    longest=sorted(order,key=lambda r:(-r['n_images'],r['rank']))
    for r in longest:
        if pending(r): return selected,[r],'D_longest'
        if good(r): selected.append(r);break
    strata={ (r['subtype'],0 if r['n_images']<=3 else 1 if r['n_images']<=7 else 2) for r in order}
    for st in sorted(strata):
        pool=[r for r in order if (r['subtype'],0 if r['n_images']<=3 else 1 if r['n_images']<=7 else 2)==st]
        if any(r in selected for r in pool):continue
        for r in pool:
            if pending(r): return selected,[r],'D_stratum'
            if good(r): selected.append(r);break
    for r in order:
        if len(selected)>=24:break
        if r in selected:continue
        if pending(r):return selected,[r],'D_fill'
        if good(r):selected.append(r)
    if len(selected)<24:return selected,[],'D_insufficient'
    e=[]
    for r in order:
        if r in selected:continue
        if len(e)==280:break
        if pending(r):return selected+e,[r],'E'
        if good(r):e.append(r)
    return selected+e,[],'ready' if len(e)==280 else 'E_insufficient'

def next_batch(n):
    order,raw,dec=load(); selected,_,stage=choose(order,dec)
    batch=[]
    # pending 예측을 keep으로 두어 조회 후보만 선택한다. 실제 판정/선택에는 저장하지 않는다.
    temporary=dict(dec)
    for _ in range(n):
        _,pending,s=choose(order,temporary)
        if not pending:break
        r=pending[0];batch.append(r)
        temporary[r['case_key']]={'visual':'keep','history':'keep'}
    for r in batch:
        c=raw[r['case_key']]
        print(json.dumps({**r,'history':c['CLINICAL_HISTORY'],'answer':c['correct_answer_text'],
                          'options':c['options']},ensure_ascii=False))
    print('STATUS',stage,'audited',len(dec),'selected',len(selected))

def record(name,entries,call_id):
    order,raw,dec=load(); by={r['case_key']:r for r in order}
    result=[]
    for cid,visual,history,note in entries:
        key='Case number '+cid.removeprefix('c')
        assert key not in dec and visual in ('keep','exclude','pending') and history in ('keep','exclude','pending')
        r=by[key];assert sha256_file(safe(ROOT/r['sheet']))==r['sheet_sha256']
        result.append({'case_key':key,'visual':visual,'history':history,'note':note,
                       'image_return_call_id':call_id,'sheet':r['sheet'],'sheet_sha256':r['sheet_sha256'],
                       'raw_source_sha256':sha256_file(OUT/'audit/candidates_private.json')})
    save(OUT/'audit/decisions'/f'{name}.json',result)
    print('recorded',len(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--next',type=int,default=6);a=p.parse_args();next_batch(a.next)
