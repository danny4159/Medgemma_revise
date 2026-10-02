"""실행과 독립적으로 전체 요청 그래프·원시 기록·입력/상위 소견을 재구성한다."""
import argparse
import json
from mt52_prepare import ROOT,OUT,save,safe,sha256_file
from mt52_spec import digest,prompt,parse
from mt52_run import verify_protocol,stages
from mt52_sanity import images

def verify(job):
    p,pdig=verify_protocol(job/'protocol.json')
    cs=json.loads((ROOT/p['inference']).read_text())
    manifest={r['case_key']:r for r in json.loads((ROOT/p['images']).read_text())}
    expected={};non_eos=[];invalid=[];records=[]
    for c in cs:
        ims=images(c,manifest);cid=c['case_key'].replace('Case number ','c');parent={}
        for stage,index in stages(c,p['only']):
            name=stage if index is None else f'F{index:02d}'
            needed=[parent[f'F{i:02d}'] for i in range(len(ims))] if stage=='U' else [parent['U']] if stage in ('C','R') else [parent['H']] if stage=='X' else []
            text=prompt(c,stage,[r['text'] for r in needed],index)
            indices=[index] if stage=='F' else list(range(len(ims))) if stage in ('D','R','H','X') else []
            cap=len(ims)*p['caps']['F']+p['caps']['U'] if stage=='H' else p['caps'][stage]
            spec={'case':c['case_key'],'stage':name,'prompt':text,'images':[manifest[c['case_key']]['images'][i] for i in indices],
                  'parents':[r['record_digest'] for r in needed],'cap':cap,'protocol':pdig}
            path=job/'records'/cid/f'{name}.json';r=json.loads(safe(path).read_text())
            rd=r.pop('record_digest');assert digest(r)==rd,'record modified';r['record_digest']=rd
            assert r['spec']==spec and r['request_id']==digest(spec),'request mismatch'
            assert r['t_end']>=r['t_start'] and abs(r['runtime']-(r['t_end']-r['t_start']))<1e-6
            assert len(r['tokens'])<=cap
            if not r['eos']:non_eos.append((cid,name))
            if stage in ['T','D','C','R','X'] and parse(r['text']) is None:invalid.append((cid,name))
            expected[str(path.relative_to(ROOT))]=sha256_file(path);parent[name]=r;records.append(r)
    actual={str(f.relative_to(ROOT)) for f in (job/'records').glob('*/*.json')}
    assert actual==set(expected),'missing/extra record'
    return {'integrity':'PASS','requests':len(records),'non_eos':non_eos,'invalid_final':invalid,'raw_digests':expected,
            'protocol_sha256':pdig,'generation_runtime_sum':sum(r['runtime'] for r in records),
            'max_reserved_GiB':max(r['peak_reserved_GiB'] for r in records)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=verify(safe(ROOT/a.job));save(safe(ROOT/a.out,True),r);print({k:v for k,v in r.items() if k!='raw_digests'})
