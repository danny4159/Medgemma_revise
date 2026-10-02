"""현재 D24와 실제 감사 이미지 반환의 불변 snapshot을 연결한다."""
import base64
import hashlib
import io
import json
import numpy as np
from pathlib import Path
from PIL import Image
from mt52_prepare import ROOT,OUT,save,sha256_file
from mt52_audit import load,choose
from mt52_provenance import pixels

def main():
    order,raw,dec=load()
    selected,_,stage=choose(order,dec)
    assert stage=='E' and len(selected)>=24
    selected=selected[:24]
    src=Path('/home/test/.codex/sessions/2026/10/03/rollout-2026-10-03T03-55-07-01a0fdf8-5e99-7c83-a778-8e11764ea36f.jsonl')
    dst=OUT/'provenance/iter052_D_audit_rollout.jsonl'
    if not dst.exists():
        data=src.read_bytes();data=data[:data.rfind(b'\n')+1]
        with dst.open('xb') as f:f.write(data)
    expected={}
    for r in selected:
        with Image.open(ROOT/r['sheet']) as im:expected[pixels(im)]=r['case_key']
    found={};calls={}
    for n,line in enumerate(dst.open()):
        p=json.loads(line).get('payload',{})
        if p.get('type')=='custom_tool_call':calls[p['call_id']]=p
        if p.get('type')!='custom_tool_call_output':continue
        for i,item in enumerate(p.get('output',[])):
            if item.get('type')!='input_image':continue
            data=base64.b64decode(item['image_url'].split(',',1)[1])
            with Image.open(io.BytesIO(data)) as im:
                key=pixels(im)
                # 도구가 2048px로 축소한 최장 sheet. 호출 경로와 실제 픽셀을 함께 검사한다.
                if key not in expected and im.size==(1170,2048):
                    call=calls.get(p['call_id'],{}).get('input','')
                    if 'c11994' in call:
                        with Image.open(ROOT/'results/iter_052/audit/sheets/c11994.png') as source:
                            err=float(np.abs(np.asarray(source.convert('RGB').resize(im.size,Image.Resampling.BILINEAR)).astype(float)-np.asarray(im.convert('RGB'))).mean())
                        if err<0.1:expected[key]='Case number 11994'
            if key in expected:
                found.setdefault(expected[key],[]).append({'call_id':p['call_id'],'line':n+1,'output_index':i,
                    'returned_sha256':hashlib.sha256(data).hexdigest(),'pixels_sha256':key,
                    'call_input':calls.get(p['call_id'],{}).get('input')})
    missing=[r['case_key'] for r in selected if r['case_key'] not in found]
    save(OUT/'provenance/D_image_returns_v2.json',{'snapshot_sha256':sha256_file(dst),'returns':found,'missing':missing,
        'longest_resize':'c11994: 1536x2688→1170x2048; call path + bilinear RGB MAE<0.1/255. Other sheets exact pixels.'})
    assert not missing,missing
    inf={c['case_key']:c for c in json.loads((OUT/'data/inference_candidates.json').read_text())}
    ims={c['case_key']:c for c in json.loads((OUT/'data/image_manifest.json').read_text())}
    save(OUT/'data/D_inference.json',[inf[r['case_key']] for r in selected])
    save(OUT/'data/D_images.json',[ims[r['case_key']] for r in selected])
    save(OUT/'audit/D_private.json',[raw[r['case_key']] for r in selected])
    save(OUT/'data/D_selection.json',{'cases':selected,'decisions':[dec[r['case_key']] for r in selected],
        'returns_sha256':sha256_file(OUT/'provenance/D_image_returns_v2.json'),
        'code_sha256':{p:sha256_file(ROOT/p) for p in ['mt52_audit.py','mt52_cluster.py','mt52_freeze_d.py']},
        'input_sha256':{p:sha256_file(OUT/p) for p in ['data/clusters.json','data/D_inference.json','data/D_images.json','audit/D_private.json']}})
    print('D24 frozen; images',sum(r['n_images'] for r in selected))

if __name__=='__main__':main()
