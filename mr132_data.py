"""고정 MR-ART 객체의 선택 반입과 익명 RAS axial 입력 구성."""
import argparse, hashlib, os, time, requests, numpy as np, nibabel as nib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from mr132_common import RES,DATA,sha,save,read,digest,now
from mr123_data import normalization_window,render_slice

CFG=dict(orientation='RAS',slice_fraction=[.15,.85],n_slices=8,normalization='volume_minmax',side=896,registration=False)
def fetch_volume(rec):
    p=DATA/'volumes'/f'{rec["bids_name"]}.nii.gz'; p.parent.mkdir(parents=True,exist_ok=True)
    stamp=p.with_suffix('.source.json')
    if p.exists():
        s=read(stamp)
        assert s['object']==rec and s['sha256']==sha(p)
        return s
    partial=p.with_name(p.name+'.part.'+str(os.getpid()))
    # 기존 부분 파일은 덮어쓰지 않는다. GET은 고정 versionId와 일치해야 한다.
    h=hashlib.md5(); sh=hashlib.sha256(); total=0; start=time.monotonic()
    url=rec['url']+'?versionId='+rec['version_id']
    r=requests.get(url,stream=True,timeout=(30,120)); r.raise_for_status()
    assert r.headers.get('ETag')==rec['etag']
    with open(partial,'xb') as f:
        for b in r.iter_content(1<<20): f.write(b); h.update(b); sh.update(b); total+=len(b)
        f.flush(); os.fsync(f.fileno())
    assert total==rec['bytes'] and h.hexdigest()==rec['md5']
    if p.exists(): raise RuntimeError('output collision')
    os.rename(partial,p)
    s=dict(path=str(p),object=rec,sha256=sh.hexdigest(),md5=h.hexdigest(),bytes=total,final_url=r.url,wall_s=time.monotonic()-start)
    save(stamp,s); return s

def render(rec,index,stage):
    f=fetch_volume(rec); source=Path(f['path']); start=time.monotonic()
    im=nib.load(source); assert len(im.shape)==3 and np.isfinite(im.affine).all() and abs(np.linalg.det(im.affine[:3,:3]))>0
    ras=nib.as_closest_canonical(im); assert nib.aff2axcodes(ras.affine)==('R','A','S')
    a=np.asarray(ras.dataobj,dtype=np.float32); assert np.isfinite(a).all()
    zooms=list(map(float,ras.header.get_zooms()[:3])); assert min(zooms)>0
    idx=np.rint(np.linspace(.15*(a.shape[2]-1),.85*(a.shape[2]-1),8)).astype(int).tolist(); assert len(set(idx))==8
    lo,hi=normalization_window(a,normalization='volume_minmax')
    config=dict(CFG,renderer_sha256=sha('mr123_data.py'),adapter_sha256=sha(__file__),source_sha256=f['sha256'])
    out=DATA/'png'/stage/f'v{index:04d}'
    if out.exists():
        old=read(out/'manifest.json'); assert old['config']==config
        assert all(sha(x['path'])==x['sha256'] for x in old['pngs']); return old
    out.mkdir(parents=True,exist_ok=False)
    pngs=[]; thumbs=[]
    for i,k in enumerate(idx):
        pil=render_slice(a,k,lo,hi,zooms); p=out/f's{i:02d}.png'
        pil.save(p); pixel=hashlib.sha256(np.asarray(pil).tobytes()).hexdigest()
        again=render_slice(a,k,lo,hi,zooms)
        assert hashlib.sha256(np.asarray(again).tobytes()).hexdigest()==pixel
        pngs.append(dict(path=str(p),sha256=sha(p),pixel_sha256=pixel,slice_index=k))
        thumbs.append(pil.resize((224,224)))
    result=dict(anonymous_volume=f'v{index:04d}',bids_name=rec['bids_name'],subject=rec['subject'],acq=rec['acq'],source=f,config=config,original_shape=list(im.shape),original_affine=im.affine.tolist(),original_axcodes=nib.aff2axcodes(im.affine),canonical_shape=list(a.shape),canonical_affine=ras.affine.tolist(),canonical_zooms=zooms,canonical_axcodes='RAS',indices=idx,window=[lo,hi],pngs=pngs,wall_s=time.monotonic()-start)
    save(out/'manifest.json',result)
    if stage=='technical':
        sheet=Image.new('RGB',(896,448))
        for i,pil in enumerate(thumbs): sheet.paste(pil,((i%4)*224,(i//4)*224))
        sheet.save(RES/'data'/f'{result["anonymous_volume"]}_montage.png')
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('stage',choices=['technical','development','holdout']); args=ap.parse_args()
    lock=read(RES/'split_lock.json'); assert lock['metadata_audit_sha256']==sha(RES/'metadata_audit.json')
    if args.stage=='holdout': assert read(RES/'eval/development_decision.json')['expand']
    ss=lock['splits'][args.stage]; rr=[r for r in lock['objects'] if r['subject'] in ss]
    output=RES/'data'/f'{args.stage}_manifest.json'; assert not output.exists()
    (RES/'data').mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=6) as pool:
        result=list(pool.map(lambda x:render(x[1],x[0],args.stage),enumerate(rr)))
    for sub in ss:
        imgs=[r for r in result if r['subject']==sub]
        assert len(imgs)==3 and len({tuple(r['indices']) for r in imgs})==1
    save(output,dict(stage=args.stage,created_at=now(),subjects=ss,volumes=result,split_sha256=sha(RES/'split_lock.json'),config=CFG,code_sha256=sha(__file__),wall_s=time.monotonic()-start))
    print(args.stage,len(ss),len(result),'volume; wall',time.monotonic()-start)

if __name__=='__main__': main()
