"""전체 대표 감사와 실제 이미지 반환을 연결하고 자료 gate를 봉인한다."""
import base64
import hashlib
import io
import json
import re
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image
from mt52_prepare import ROOT, OUT, save, sha256_file
from mt52_audit import load, choose
from mt52_provenance import pixels

ROLLOUT=Path('/home/test/.codex/sessions/2026/10/03/rollout-2026-10-03T03-55-07-01a0fdf8-5e99-7c83-a778-8e11764ea36f.jsonl')

def bind(snapshot, order):
    by={r['case_key']:r for r in order}; expected={}; found={}; calls={}
    for r in order:
        assert sha256_file(ROOT/r['sheet'])==r['sheet_sha256']
        with Image.open(ROOT/r['sheet']) as im:expected[pixels(im)]=r['case_key']
    for ln,line in enumerate(snapshot.open()):
        p=json.loads(line).get('payload',{})
        if p.get('type')=='custom_tool_call':calls[p['call_id']]=p.get('input','')
        if p.get('type')!='custom_tool_call_output':continue
        for i,item in enumerate(p.get('output',[])):
            if item.get('type')!='input_image':continue
            data=base64.b64decode(item['image_url'].split(',',1)[1]); call=calls.get(p['call_id'],'')
            with Image.open(io.BytesIO(data)) as im:
                ph=pixels(im); key=expected.get(ph); mode='exact_rgb'; error=0.
                if key is None:
                    for cid in re.findall(r'/sheets/c(\d+)\.png',call):
                        ck='Case number '+cid
                        if ck not in by:continue
                        with Image.open(ROOT/by[ck]['sheet']) as src:
                            if src.size==im.size:continue
                            if abs(src.width/src.height-im.width/im.height)>.002:continue
                            error=float(np.abs(np.asarray(src.convert('RGB').resize(im.size,Image.Resampling.BILINEAR)).astype(float)-np.asarray(im.convert('RGB'))).mean())
                        if error<.1:key=ck;mode='tool_resize_bilinear_mae_lt_0.1';break
                if key is None:continue
                # Match both the actual returned pixels and the requested path.
                assert call,('missing call',key,p['call_id'])
                found.setdefault(key,[]).append({'call_id':p['call_id'],'line':ln+1,'output_index':i,
                    'returned_sha256':hashlib.sha256(data).hexdigest(),'pixels_sha256':ph,
                    'mode':mode,'rgb_mae':error,'literal_path_in_call':by[key]['sheet'] in call,'call_input':call})
    return found

def validate(order,dec,found):
    keys={r['case_key'] for r in order}
    assert keys==set(dec),'missing/extra audit decision'
    assert keys<=set(found),'missing actual image return'
    for r in order:
        d=dec[r['case_key']]
        assert d['sheet_sha256']==r['sheet_sha256'],'audit sheet mismatch'
        assert d['raw_source_sha256']==sha256_file(OUT/'audit/candidates_private.json'),'audit source mismatch'

def main():
    order,raw,dec=load();snap=OUT/'provenance/iter052_complete_audit_rollout_v2.jsonl'
    if not snap.exists():
        data=ROLLOUT.read_bytes();data=data[:data.rfind(b'\n')+1]
        with snap.open('xb') as f:f.write(data)
    found=bind(snap,order)
    save(OUT/'provenance/all_image_returns_v2.json',{'snapshot':str(snap.relative_to(ROOT)),
        'snapshot_sha256':sha256_file(snap),'returns':found,'missing':sorted(set(dec)-set(found))})
    validate(order,dec,found)
    selected,pending,stage=choose(order,dec);assert not pending
    d=json.loads((OUT/'data/D_inference.json').read_text())
    assert [r['case_key'] for r in selected[:24]]==[r['case_key'] for r in d]
    e=selected[24:];assert not ({r['case_key'] for r in e}&{r['case_key'] for r in d})
    sources=['mt52_audit_finish.py','mt52_audit.py','mt52_cluster.py','mt52_prepare.py']
    inputs=['audit/representative_order.json','audit/candidates_private.json','data/clusters.json',
        'data/image_manifest.json','data/D_selection.json','provenance/all_image_returns_v2.json']
    files=[ROOT/p for p in sources]+[OUT/p for p in inputs]+sorted((OUT/'audit/decisions').glob('*.json'))
    result={'status':stage,'run_E':stage=='ready','candidates':607,'representatives':len(order),
        'audited':len(dec),'eligible':len(selected),'D':24,'E_available':len(e),'E_required':280,
        'shortfall':max(0,280-len(e)),'eligible_images':sum(r['n_images'] for r in selected),
        'E_images':sum(r['n_images'] for r in e),'visual':dict(Counter(r['visual'] for r in dec.values())),
        'history':dict(Counter(r['history'] for r in dec.values())),
        'selected':selected,'source_digests':{str(p.relative_to(ROOT)):sha256_file(p) for p in files},
        'scope':'CT-only fixed representative primary audit. No model hypothesis judgment; E not shortened.'}
    save(OUT/'audit/data_gate.json',result)
    print({k:v for k,v in result.items() if k not in ('selected','source_digests')})

if __name__=='__main__':main()
