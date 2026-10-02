"""원본·공식 객체·전체 영상·고정 대표 및 감사 gate의 별도 재집계."""
import hashlib
import json
from collections import Counter
from PIL import Image
from mt52_prepare import ROOT,OUT,save,sha256_file,verify_object,safe

def main():
    rawpath=ROOT/'results/iter_049/raw/train.jsonl'
    assert sha256_file(rawpath)=='7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a'
    raw=[json.loads(s) for s in rawpath.read_text().splitlines()]
    selected={r['title']:r for r in raw if r['image_count']>=2 and r['timepoint_count']==1 and r['is_longitudinal'] is False
        and all(r[f'image_{i:02d}_modality']=='CT' for i in range(1,r['image_count']+1))}
    assert len(selected)==607
    manifest=json.loads((OUT/'data/image_manifest.json').read_text());assert {r['case_key'] for r in manifest}==set(selected)
    n=0;alpha=[]
    for case in manifest:
        key=case['case_key'];r=selected[key];cid=key.replace('Case number ','c')
        listing=json.loads((OUT/'acq'/f'{cid}.json').read_text());entries={e['path']:e for e in listing['entries'] if e['type']=='file'}
        assert len(case['images'])==r['image_count']
        for i,x in enumerate(case['images'],1):
            assert x['id']==r[f'image_{i:02d}_id'] and x['original_path']==r[f'image_{i:02d}_path']
            p=safe(ROOT/x['path']);verify_object(p,entries[x['original_path']]);assert sha256_file(p)==x['sha256']
            with Image.open(p) as im:
                if 'A' in im.getbands() and im.getchannel('A').getextrema()!=(255,255):alpha.append(x['path'])
                rgb=im.convert('RGB');assert hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()==x['rgb_sha256']
            n+=1
    groups=json.loads((OUT/'data/clusters.json').read_text())['clusters'];reps=[];members=[]
    for g in groups:
        members.extend(g['members']);rep=min(g['members'],key=lambda k:hashlib.sha256(('5201|'+k).encode()).hexdigest())
        assert rep==g['representative'];reps.append(rep)
    assert len(members)==len(set(members))==607 and set(members)==set(selected)
    ds=[]
    for p in sorted((OUT/'audit/decisions').glob('*.json')):ds.extend(json.loads(p.read_text()))
    assert len(ds)==len({d['case_key'] for d in ds})==606 and {d['case_key'] for d in ds}==set(reps)
    good={d['case_key'] for d in ds if d['visual']=='keep' and d['history']=='keep'}
    d={c['case_key'] for c in json.loads((OUT/'data/D_inference.json').read_text())};assert len(d)==24 and d<=good
    e=good-d;gate=json.loads((OUT/'audit/data_gate.json').read_text())
    assert gate['eligible']==len(good)==287 and gate['E_available']==len(e)==263 and gate['run_E'] is False
    ret=json.loads((OUT/'provenance/all_image_returns_v2.json').read_text());assert set(reps)<=set(ret['returns']) and not ret['missing']
    assert sha256_file(ROOT/ret['snapshot'])==ret['snapshot_sha256']
    save(OUT/'tests/data_verify_final.json',{'status':'PASS','cases':607,'images':n,'representatives':606,'eligible':len(good),
        'D':len(d),'E':len(e),'E_gate':False,'nonopaque_alpha':alpha,'source_sha256':sha256_file(__file__),
        'gate_sha256':sha256_file(OUT/'audit/data_gate.json'),'returns_sha256':sha256_file(OUT/'provenance/all_image_returns_v2.json')})
    print('PASS',607,n,606,len(good),len(e))

if __name__=='__main__':main()
