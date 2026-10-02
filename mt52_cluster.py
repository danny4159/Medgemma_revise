"""모델 실행 및 의미 감사 전 중복 후보와 대표 순서를 고정한다."""
import collections
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from mt52_prepare import ROOT, OUT, safe, save, candidates, norm_text, sha256_file

def rank(key): return hashlib.sha256(('5201|'+key).encode()).hexdigest()

def dctn(a, norm='ortho'):
    """32x32 orthonormal DCT-II. scipy 없는 기본 환경에서 NumPy 수식을 사용한다."""
    n=a.shape[0]
    basis=np.cos(np.pi*np.arange(n)[:,None]*(np.arange(n)[None,:]+0.5)/n)*np.sqrt(2/n)
    basis[0]/=np.sqrt(2)
    return basis@a@basis.T

def main():
    cs=candidates(); by={r['title']:r for r in cs}
    manifest=json.loads((OUT/'data/image_manifest.json').read_text())
    assert len(manifest)==607 and sum(len(c['images']) for c in manifest)==2909
    parent={k:k for k in by}; edges=[]
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def join(a,b,reason,detail):
        if a==b:return
        parent[find(a)]=find(b)
        edges.append({'a':a,'b':b,'reason':reason,'detail':detail})
    seen={}; allims=[]
    for r in manifest:
        key=r['case_key']; ims=[]
        c=by[key]
        sig=norm_text(c['CLINICAL_HISTORY'])+'|'+str(sorted(norm_text(x) for x in c['options'].values()))
        if sig in seen: join(key,seen[sig],'same_normalized_history_options',sig)
        seen[sig]=key
        for rec in r['images']:
            p=safe(ROOT/rec['path']); assert sha256_file(p)==rec['sha256']
            with Image.open(p) as im:
                rgb=im.convert('RGB'); ims.append(rgb.copy())
                assert hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()==rec['rgb_sha256']
                freq=dctn(np.asarray(rgb.convert('L').resize((32,32)),dtype=float),norm='ortho')[:8,:8]
                ph=int(''.join('1' if x>np.median(freq.flatten()[1:]) else '0' for x in freq.flat),2)
            for kind in ['sha256','rgb_sha256','id']:
                sig=kind+'|'+rec[kind]
                if sig in seen: join(key,seen[sig],'exact_'+kind,rec['path'])
                seen[sig]=key
            allims.append((key,rec['path'],ph,int(rec['dhash'],16)))
        # aspect ratio를 유지하며 감사용 사본에만 index를 표시한다.
        cols=min(4,len(ims)); tile=384
        sheet=Image.new('RGB',(cols*tile,((len(ims)+cols-1)//cols)*tile),(35,35,35))
        draw=ImageDraw.Draw(sheet)
        for i,im in enumerate(ims):
            thumb=ImageOps.contain(im,(tile,tile-22))
            x=(i%cols)*tile; y=(i//cols)*tile
            sheet.paste(thumb,(x+(tile-thumb.width)//2,y+22))
            draw.text((x+4,y+3),f'{key} / {i+1}',fill='yellow')
        dest=safe(OUT/'audit/sheets'/(key.replace('Case number ','c')+'.png'),True)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists(): raise ValueError('sheet exists')
        with dest.open('xb') as f: sheet.save(f,format='PNG')
    near=[]
    for i,(a,pa,ha,da) in enumerate(allims):
        for b,pb,hb,db in allims[i+1:]:
            if a!=b and (ha^hb).bit_count()<=4 and (da^db).bit_count()<=4:
                detail={'paths':[pa,pb],'phash_distance':(ha^hb).bit_count(),'dhash_distance':(da^db).bit_count()}
                near.append(detail)
                join(a,b,'unresolved_near_duplicate_conservative_cluster',detail)
    groups=collections.defaultdict(list)
    for k in by:groups[find(k)].append(k)
    clusters=[{'representative':min(v,key=rank),'members':sorted(v)} for v in groups.values()]
    clusters.sort(key=lambda r:rank(r['representative']))
    save(OUT/'data/clusters.json',{'clusters':clusters,'edges':edges,'near_pairs':near,
        'manifest_sha256':sha256_file(OUT/'data/image_manifest.json'),
        'rule':'exact bytes/RGB/id or history+options; unresolved pHash<=4 AND dHash<=4 conservatively merged; not patient identity',
        'code_sha256':sha256_file(__file__)})
    reps=[by[r['representative']] for r in clusters]
    save(OUT/'audit/representative_order.json',[{'case_key':r['title'],'rank':rank(r['title']),
        'n_images':r['image_count'],'subtype':r['image_01_sub_modality'],
        'sheet':str((OUT/'audit/sheets'/(r['title'].replace('Case number ','c')+'.png')).relative_to(ROOT)),
        'sheet_sha256':sha256_file(OUT/'audit/sheets'/(r['title'].replace('Case number ','c')+'.png'))} for r in reps])
    print('clusters',len(clusters),'near pairs',len(near),'edges',len(edges))

if __name__=='__main__':main()
