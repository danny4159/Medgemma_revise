"""iter_143 신규 환자 원영상–mask 검사와 원문 target 확정. i141 렌더 규약 계승."""
from pathlib import Path
import json
import re
import numpy as np
import nibabel as nib
from PIL import Image, ImageOps
from i143_data import OUT, OLD, SOURCE, SPLIT
from i141_common import read, save, sha, now


def main():
    selected=read(OUT/'selection_candidates.json')
    download=read(OUT/'download_complete.json')
    for r in download['files']: assert sha(r['path'])==r['sha256']
    refs=[]; rows=[]
    for r in selected['selected']:
        pid=r['patient_id']; key=r['key']; gkey=r['source_key']
        p=OUT/'data_selected/ISLES-2022'/pid/'ses-0001/dwi'/(key+'.nii.gz')
        mp=OUT/'data_selected/ISLES-2022/derivatives'/pid/'ses-0001'/(gkey+'_msk.nii.gz')
        img=nib.load(p); mask=nib.load(mp)
        assert img.ndim==3 and img.shape==mask.shape and np.allclose(img.affine,mask.affine,atol=1e-5)
        can=nib.as_closest_canonical(img); arr=np.asanyarray(can.dataobj)
        assert np.isfinite(arr).all() and nib.aff2axcodes(can.affine)==('R','A','S')
        transform=nib.orientations.inv_ornt_aff(nib.orientations.ornt_transform(nib.orientations.io_orientation(img.affine),nib.orientations.io_orientation(can.affine)),img.shape)
        orig=np.asanyarray(img.dataobj); checks=[]
        for q in [(0,0,0),tuple(x-1 for x in arr.shape),tuple(x//2 for x in arr.shape)]:
            n=transform@np.array([*q,1.]); err=float(np.max(np.abs(img.affine@n-can.affine@np.array([*q,1.]))))
            assert err<1e-5 and orig[tuple(np.rint(n[:3]).astype(int))]==arr[q]
            checks.append(dict(canonical=list(q),native=n.tolist(),error_mm=err))
        znon=np.where(np.any(arr!=0,axis=(0,1)))[0]; zs=list(range(int(znon[0]),int(znon[-1])+1))
        lo,hi=float(arr.min()),float(arr.max()); assert hi>lo
        ims=[]
        for z in zs:
            a=np.flip(np.round(np.clip((arr[:,:,z]-lo)/(hi-lo),0,1)*255).astype(np.uint8).T,axis=(0,1))
            im=Image.fromarray(a).convert('RGB'); zoom=can.header.get_zooms()
            im=im.resize((max(1,round(a.shape[1]*zoom[0])),max(1,round(a.shape[0]*zoom[1]))),Image.Resampling.BILINEAR)
            im=ImageOps.pad(im,(256,256),method=Image.Resampling.BILINEAR,color=0)
            ip=OUT/'png'/pid/f'z{z:04d}.png'; ip.parent.mkdir(parents=True,exist_ok=True)
            assert not ip.exists(); im.save(ip)
            xyz=can.affine@np.array([(arr.shape[0]-1)/2,(arr.shape[1]-1)/2,z,1])
            ims.append(dict(path=str(ip),sha256=sha(ip),z=z,physical_RAS_mm=xyz[:3].tolist()))
        # 오탈자만 원문 삭제 span을 한 글자도 추가하지 않는 방식으로 바로잡는다.
        spans=r['retained_spans']
        if pid=='sub-strokecase0053':
            spans=[dict(s) for s in spans]
            assert ''.join(s['quote'] for s in spans).endswith('a a high signal on DWI')
            s=spans[0]; assert s['quote'].endswith('a ')
            s['end']-=2; s['quote']=s['quote'][:-2]
        target=''.join(s['quote'] for s in spans).strip()
        assert all(r['original_text'][s['start']:s['end']]==s['quote'] for s in spans)
        assert not re.search(r'ADC|midline|infarct|acute|chronic|restriction',target,re.I)
        refs.append(dict(patient_id=pid,split=r['split'],source_key=gkey,original_text=r['original_text'],
                         target=target,retained_spans=spans,supervision_unit='whole_DWI_sequence',
                         source_sha256=sha(SOURCE),semantic_review='원문 삭제만 사용. 위치의 생략된 좌우/병인/ADC 의미를 보충하지 않음.'))
        rows.append(dict(patient_id=pid,split=r['split'],key=key,source_path=str(p),source_sha256=sha(p),
                         mask_path=str(mp),mask_sha256=sha(mp),mask_input=False,shape=list(img.shape),
                         native_affine=img.affine.tolist(),canonical_affine=can.affine.tolist(),
                         physical_checks=checks,images=ims,spacing_mm=list(map(float,can.header.get_zooms())),
                         intensity_range=[lo,hi],n_slices=len(ims)))
    assert len(set(r['source_sha256'] for r in rows))==48
    old={r['patient_id'] for r in read(OLD/'data_manifest.json')['rows']}
    assert not old.intersection(r['patient_id'] for r in rows)
    save(OUT/'reference_locked.json',dict(created_at=now(),rows=refs,source_sha256=sha(SOURCE),
         selection_sha256=sha(OUT/'selection_candidates.json'),note='추론 입력에는 target/원문/mask를 전달하지 않는다.'))
    save(OUT/'data_manifest.json',dict(created_at=now(),rows=rows,source_release='ISLES2022 v2.3.1 record7960856',
         selection_sha256=sha(OUT/'selection_candidates.json'),download_sha256=sha(OUT/'download_complete.json'),
         prior_patient_overlap=0,source_duplicates=0,mask_geometry_passed=48,
         use_basis_inherited='iter141 official CC-BY-4.0 MRI / RadGenome MIT card; same pinned release'))
    print(json.dumps(dict(patients=len(rows),slices=sum(r['n_slices'] for r in rows),range=[min(r['n_slices'] for r in rows),max(r['n_slices'] for r in rows)])))

if __name__=='__main__': main()
