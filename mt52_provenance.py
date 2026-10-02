"""iter_051 실제 이미지 반환 원본을 보존하고 case별 call_id에 연결한다."""
import base64
import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from PIL import Image
from mt52_prepare import ROOT, OUT, save, safe, sha256_file

SOURCE=Path('/home/test/.codex/sessions/2026/10/03/rollout-2026-10-03T02-56-55-01a0fdc3-130f-7b50-ad7d-d61d231a1e7f.jsonl')

def pixels(im):
    im.load()
    return hashlib.sha256(im.mode.encode()+str(im.size).encode()+im.tobytes()).hexdigest()

def main():
    dest=safe(OUT/'provenance/iter051_rollout.jsonl',True)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        with SOURCE.open('rb') as s, dest.open('xb') as d: shutil.copyfileobj(s,d)
    digest=sha256_file(SOURCE)
    assert sha256_file(dest)==digest
    rows=[json.loads(x) for x in dest.read_text().splitlines()]
    calls={x['payload']['call_id']:x['payload'] for x in rows
           if x.get('payload',{}).get('type')=='custom_tool_call'}
    source=ROOT/'results/iter_051/audit/source_check.json'
    cases=json.loads(source.read_text())['cases']
    expected={}; originals={}
    for c in cases:
        p=safe(ROOT/c['sheet'])
        assert sha256_file(p)==c['sheet_sha256']
        with Image.open(p) as im: expected[pixels(im)]=c
        for imrec in c['ordered_images']:
            original=safe(ROOT/'results/iter_049'/imrec['path'])
            assert sha256_file(original)==imrec['file_sha256']
            with Image.open(original) as im:
                for rendered in (im,im.convert('RGB')):
                    originals[pixels(rendered)]={'case_id':c['case_id'],'original_path':imrec['path'],
                                                'file_sha256':imrec['file_sha256']}
    matches={}; extra=[]
    for n,row in enumerate(rows):
        p=row.get('payload',{})
        if p.get('type')!='custom_tool_call_output': continue
        call=calls.get(p['call_id'],{})
        for k,item in enumerate(p.get('output',[])):
            if item.get('type')!='input_image': continue
            raw=base64.b64decode(item['image_url'].split(',',1)[1])
            with Image.open(io.BytesIO(raw)) as im: pix=pixels(im)
            ev={'call_id':p['call_id'],'rollout_line':n+1,'output_index':k,
                'returned_image_sha256':hashlib.sha256(raw).hexdigest(),
                'returned_pixel_sha256':pix,'call_input_sha256':hashlib.sha256(call.get('input','').encode()).hexdigest()}
            if pix in expected:
                c=expected[pix]
                matches.setdefault(c['case_id'],[]).append(ev)
            else: extra.append({**ev,'original':originals.get(pix)})
    missing=[c['case_id'] for c in cases if c['case_id'] not in matches]
    result={'status':'PASS' if not missing else 'FAIL','rollout':str(dest.relative_to(ROOT)),
        'rollout_sha256':digest,'source_rollout':str(SOURCE),'source_check_sha256':sha256_file(source),
        'cases':[{'case_id':c['case_id'],'sheet_sha256':c['sheet_sha256'],
                  'ordered_images':c['ordered_images'],'returns':matches.get(c['case_id'],[])} for c in cases],
        'missing':missing,'other_image_returns':extra,
        'scope':'실제 반환 sheet 픽셀과 원본 sheet 동일성 연결. 재판독·판정 변경 없음.'}
    save(OUT/'provenance/iter051_return_links_v2.json',result)
    print('linked',len(matches),'missing',len(missing),'other image returns',len(extra))
    if missing or any(e['original'] is None for e in extra): raise RuntimeError('unlinked images')

if __name__=='__main__': main()
