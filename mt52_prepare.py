"""CT 후보 확보. 과거 자산 읽기 전용, 새 결과만 배타적으로 기록한다."""
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.parse
import fcntl
import PIL
from PIL import Image, ImageOps, ImageDraw
from mt49_audit import modalities, schema_problems, answer_problems, infer_view, norm_text
from mt49_fetch import HF, HF_REV, get_json, sha256_file
from mt49_images import git_blob_sha1, safe_rel

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'results/iter_052'
TRAIN_SHA = '7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a'

def safe(path, write=False):
    p = Path(path).absolute()
    if '..' in p.parts or any(q.is_symlink() for q in [p, *p.parents]):
        raise ValueError('path traversal or symlink')
    if not p.is_relative_to(OUT if write else ROOT):
        raise ValueError('output outside iteration' if write else 'input outside research')
    return p

def save(path, obj):
    p = safe(path, True)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if p.exists():
        if p.read_text() != text:
            raise ValueError('existing content mismatch: '+str(p))
        return
    with p.open('x') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())

def candidates():
    p = safe(ROOT/'results/iter_049/raw/train.jsonl')
    assert sha256_file(p) == TRAIN_SHA
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    assert len(rows) == 7347 and len({r['title'] for r in rows}) == 7347
    cs = [r for r in rows if set(modalities(r)) == {'CT'} and r['is_longitudinal'] is False
          and r['timepoint_count'] == 1 and r['image_count'] >= 2]
    assert (len(cs),sum(r['image_count'] for r in cs)) == (607,2909)
    for r in cs:
        assert not schema_problems(r) and not answer_problems(r), r['title']
        v = infer_view(r)
        assert all(set(i)=={'id','path'} for i in v['images'])
        for i in v['images']:
            safe_rel(i['path'])
    return sorted(cs,key=lambda r:hashlib.sha256(('5201|'+r['title']).encode()).hexdigest())

def verify_object(p, ent):
    safe(p)
    if p.stat().st_size != ent['size']:
        raise ValueError('object size mismatch')
    expected = ent.get('lfs',{}).get('oid')
    actual = sha256_file(p) if expected else git_blob_sha1(p)
    if actual != (expected or ent['oid']):
        raise ValueError('official object digest mismatch')

def case_download(r):
    cid = r['title'].replace('Case number ','c')
    images = infer_view(r)['images']
    listing_path = OUT/'acq'/f'{cid}.json'
    directory = str(Path(images[0]['path']).parent)
    url = f'https://huggingface.co/api/datasets/{HF}/tree/{HF_REV}/'+directory
    if listing_path.exists():
        listing = json.loads(safe(listing_path).read_text())
        assert listing['url'] == url
    else:
        listing = {'url':url,'entries':get_json(url)}
        save(listing_path,listing)
    ents = {e['path']:e for e in listing['entries'] if e['type']=='file'}
    records=[]
    for im in images:
        ent = ents[im['path']]
        p = safe(OUT/im['path'],True)
        p.parent.mkdir(parents=True,exist_ok=True)
        u = f'https://huggingface.co/datasets/{HF}/resolve/{HF_REV}/'+urllib.parse.quote(im['path'])
        provenance = p.with_suffix('.acquisition.json')
        if p.exists():
            verify_object(p,ent)
            if not provenance.exists():
                raise ValueError('missing acquisition provenance')
            prior=json.loads(provenance.read_text())
            assert prior['url']==u and prior['sha256']==sha256_file(p)
        else:
            last=None
            for attempt in range(3):
                part=p.with_suffix(f'.part.{os.getpid()}.{attempt}')
                try:
                    with urllib.request.urlopen(u,timeout=60) as res, part.open('xb') as f:
                        final=res.geturl()
                        while b:=res.read(1<<20):
                            f.write(b)
                        f.flush(); os.fsync(f.fileno())
                    verify_object(part,ent)
                    os.link(part,p)
                    save(provenance,{'url':u,'final_url':final,'sha256':sha256_file(p),
                                     'size':p.stat().st_size,'revision':HF_REV})
                    last=None
                    break
                except Exception as e:
                    last=repr(e)
                    time.sleep(1)
            if last:
                raise RuntimeError(last)
        with Image.open(p) as img:
            img.load()
            alpha=img.getchannel('A').getextrema() if 'A' in img.getbands() else None
            rgb=img.convert('RGB')
            alpha_identical=True
            if alpha and alpha!=(255,255):
                # 검정 투명 경계는 검정 배경 합성과 RGB 변환이 정확히 같다.
                black=Image.new('RGBA',img.size,(0,0,0,255))
                composed=Image.alpha_composite(black,img.convert('RGBA')).convert('RGB')
                alpha_identical=composed.tobytes()==rgb.tobytes()
            # dHash 후보만 생성한다. 동일 환자 판정으로 사용하지 않는다.
            small=list(rgb.convert('L').resize((9,8)).getdata())
            bits=''.join('1' if small[y*9+x]>small[y*9+x+1] else '0' for y in range(8) for x in range(8))
            records.append({'path':str(p.relative_to(ROOT)),'original_path':im['path'],'id':im['id'],
                'sha256':sha256_file(p),'size':p.stat().st_size,'mode':img.mode,'wh':list(img.size),
                'rgb_sha256':hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest(),
                'dhash':format(int(bits,2),'016x'),'alpha':alpha,
                'alpha_black_composite_identical':alpha_identical})
    rec={'case_key':r['title'],'images':records,'decoder':PIL.__version__,
         'listing_sha256':sha256_file(listing_path)}
    save(OUT/'acq'/f'{cid}_verified.json',rec)
    return rec

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'prepare.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cs=candidates()
        save(OUT/'data/inference_candidates.json',[infer_view(r) for r in cs])
        save(OUT/'audit/candidates_private.json',cs)
        save(OUT/'data/source_lock.json',{'train_sha256':TRAIN_SHA,'revision':HF_REV,
             'code_sha256':{p:sha256_file(ROOT/p) for p in ['mt52_prepare.py','mt49_audit.py','mt49_fetch.py','mt49_images.py']},
             'plan_sha256':sha256_file(ROOT.parent/'agent/runs/iter_052/plan.json'),
             'python':sys.executable,'decoder':PIL.__version__,'cases':607,'images':2909})
        t=time.time(); recs=[]; errors=[]
        with cf.ThreadPoolExecutor(8) as ex:
            futures={ex.submit(case_download,r):r['title'] for r in cs}
            for n,f in enumerate(cf.as_completed(futures),1):
                try: recs.append(f.result())
                except Exception as e: errors.append({'case_key':futures[f],'error':repr(e)})
                if n%25==0: print(n,len(errors),round(time.time()-t),flush=True)
        save(OUT/'acq/summary.json',{'seconds':time.time()-t,'cases':len(recs),
             'images':sum(len(r['images']) for r in recs),'errors':errors})
        if errors: raise RuntimeError('acquisition incomplete')
        save(OUT/'data/image_manifest.json',sorted(recs,key=lambda r:r['case_key']))
        print('acquisition complete',len(recs),flush=True)

if __name__=='__main__': main()
