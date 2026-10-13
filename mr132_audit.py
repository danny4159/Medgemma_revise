"""현재 원 영상·PNG·정답·요청의 독립 연결 감사 (모델 출력 미사용)."""
import hashlib,itertools,numpy as np,nibabel as nib
from PIL import Image
from mr132_common import RES,read,save,sha,now

def main():
    split=read(RES/'split_lock.json'); scores={r['bids_name']:r for r in read(RES/'metadata_audit.json')['objects']}
    groups=split['splits']; ss=[s for v in groups.values() for s in v]; assert len(ss)==len(set(ss))==126
    sources=[]; pngs={}; labels={};checks=[]
    for stage in ['technical','development']:
        m=read(RES/'data'/f'{stage}_manifest.json'); lab=read(RES/'data'/f'{stage}_labels.json'); req=read(RES/'requests'/f'{stage}.json')
        assert m['subjects']==groups[stage] and len(req)==len(lab)*9
        for v in m['volumes']:
            f=v['source']; assert sha(f['path'])==f['sha256']; im=nib.load(f['path']); can=nib.as_closest_canonical(im);a=np.asarray(can.dataobj,dtype=np.float32)
            assert nib.aff2axcodes(can.affine)==('R','A','S') and np.isfinite(a).all()
            assert np.allclose(can.affine,v['canonical_affine']) and tuple(a.shape)==tuple(v['canonical_shape'])
            idx=np.rint(np.linspace(.15*(a.shape[2]-1),.85*(a.shape[2]-1),8)).astype(int).tolist();assert idx==v['indices']
            lo,hi=float(np.min(a)),float(np.max(a));assert v['window']==[lo,hi] and hi>lo
            h=hashlib.sha256(a.tobytes()).hexdigest();sources.append(dict(subject=v['subject'],bids_name=v['bids_name'],file_sha256=f['sha256'],decoded_sha256=h))
            for p in v['pngs']:
                assert sha(p['path'])==p['sha256'];pix=hashlib.sha256(np.asarray(Image.open(p['path'])).tobytes()).hexdigest();assert pix==p['pixel_sha256'];pngs[p['path']]=dict(file_sha256=p['sha256'],pixel_sha256=pix)
        for patient in lab:
            labels[patient['id']]=patient
            assert patient['subject'] in groups[stage]
            assert patient['grades']==[scores[k]['score'] for k in patient['bids_names']]
        vol={v['bids_name']:v for v in m['volumes']}
        for r in req:
            indices=[int(x) for x in r['id'].split('_')[-1]];labrec=labels[r['patient']]
            for index,g in zip(indices,r['groups']):
                expected=[p['path'] for p in vol[labrec['bids_names'][index]]['pngs']];assert expected==[p['path'] for p in g]
            assert all(p['sha256']==pngs[p['path']]['file_sha256'] for g in r['groups'] for p in g)
        checks.append(dict(stage=stage,n_subjects=len(m['subjects']),n_volumes=len(m['volumes']),n_requests=len(req),request_image_label_link=True,source_voxel_affine_slice_window_verified=True))
    duplicate_files={h:[x['bids_name'] for x in sources if x['file_sha256']==h] for h in {x['file_sha256'] for x in sources} if sum(x['file_sha256']==h for x in sources)>1}
    duplicate_pixels={h:[x['bids_name'] for x in sources if x['decoded_sha256']==h] for h in {x['decoded_sha256'] for x in sources} if sum(x['decoded_sha256']==h for x in sources)>1}
    # 같은 사람 반복 촬영의 정확 중복은 별도 공개; 환자 간 중복은 독립성 실패다.
    byname={x['bids_name']:x['subject'] for x in sources}
    assert not any(len({byname[k] for k in group})>1 for group in duplicate_pixels.values())
    save(RES/'input_integrity_audit.json',dict(created_at=now(),all_pass=True,source_sha256=sha(__file__),checks=checks,n_unique_subjects=46,n_volumes=len(sources),n_pngs=len(pngs),file_duplicates=duplicate_files,decoded_duplicates=duplicate_pixels,holdout_not_opened=True,sources=sources,pngs=pngs,inputs={str(p):sha(p) for p in [RES/'split_lock.json',RES/'metadata_audit.json',RES/'baseline/selection_lock.json']}))
    print('입력 독립 감사:',len(sources),'volume,',len(pngs),'PNG, 환자 중복0')

if __name__=='__main__':main()
