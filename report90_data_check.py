"""T/V 원영상·pixel·보호집단 누수 검사. E 영상/reference는 열지 않는다."""
import hashlib
import io
import json
import numpy as np
from PIL import Image
import report90_data as N
import report89_data as B
from report86_common import save,sha

def ph(a):return hashlib.sha256(a.tobytes()).hexdigest()

def main():
    rows={s:B.read(N.OUT/f'data/{s}/manifest.json') for s in ('T512','V64')}
    reports,_,links=B.D.load_inputs();original={r['ImageID']:r for r in reports}
    protected=[r for r in B.read(B.ROOT/B.EXPOSED[0]) if r.get('subset')=='F']
    protected += [r for r in B.read(B.ROOT/B.EXPOSED[2]) if r.get('eval_set')=='H192']
    assert len(protected)==312
    z=B.D.open_image_zip();index=B.D.zip_index(z);hashes={};checked=[]
    for split in ('T512','V64'):
        hashes[split]={'raw':set(),'u8':set()}
        for r in rows[split]:
            a=np.asarray(Image.open(io.BytesIO(z.read(index[r['ImageID']]))));b=np.asarray(Image.open(r['image']))
            assert sha(r['image'])==r['file_sha256'] and sha(r['raw_path'])==r['raw_sha256']
            assert ph(a)==r['raw_pixel_sha256'] and ph(b)==r['u8_pixel_sha256'] and np.array_equal(a//256,b)
            fs,ex=N.current_findings(original[r['ImageID']]);assert r['report']==' '.join(f['sentence_en'].strip() for f in fs)
            assert ex==r['excluded_sentences'] and r['PatientID']==links['img2patient'][r['ImageID']]
            assert r['split']=='train';hashes[split]['raw'].add(ph(a));hashes[split]['u8'].add(ph(b))
            checked.append(dict(split=split,ImageID=r['ImageID'],raw=ph(a),u8=ph(b)))
        assert all(len(v)==len(rows[split]) for v in hashes[split].values())
    hashes['protected']={'raw':set(),'u8':set()}
    for r in protected:
        a=np.asarray(Image.open(io.BytesIO(z.read(index[r['ImageID']]))));hashes['protected']['raw'].add(ph(a));hashes['protected']['u8'].add(ph((a//256).astype(np.uint8)))
    comparisons={}
    for a,b in [('T512','V64'),('T512','protected'),('V64','protected')]:
        for kind in ('raw','u8'):
            n=len(hashes[a][kind]&hashes[b][kind]);comparisons[f'{a}:{b}:{kind}']=n;assert n==0
        for kind in ('PatientID','StudyID','ImageID'):
            ra=rows[a];rb=rows[b] if b!='protected' else protected
            overlap={r[kind] for r in ra}&{r[kind] for r in rb};assert not overlap
    save(N.OUT/'data/pixel_check.json',dict(passed=True,checked=checked,protected_n=312,overlap=comparisons,
        E_pixels_checked=False,sources={f:sha(f) for f in ['report90_data_check.py','report90_data.py','results/iter_090/data/T512/manifest.json','results/iter_090/data/V64/manifest.json']},
        exposed_train_patients={s:sum(r['PatientID'] in B.read(B.OUT/'data/selection_lock.json')['exposed_patients'] for r in rs) for s,rs in rows.items()}))
    print('T/V 576명 원영상·raw/u8 pixel, 보호312명 대조 PASS',flush=True)

if __name__=='__main__':main()
