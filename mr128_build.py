"""공식 부피/ICV와 native 격자 nearest-neighbor에 연결한 고정 U/A 입력."""
import argparse
from pathlib import Path
import time

import nibabel as nib
from nibabel.processing import resample_from_to
import numpy as np
from PIL import Image
import mr123_data as D
from mr128_data import OUT, ROOT, read, save, sha, verify_files

PROMPT = 'You are shown 8 axial T2-weighted slices from one brain MRI examination, ordered from inferior to superior. Is there evidence of enlargement of both lateral ventricles in the images shown? Answer on the first line with exactly one word: PRESENT, ABSENT, or UNCERTAIN. Then give a brief justification in at most two sentences.'


def independent_nn(data, affine, shape, target_affine):
    """scipy를 호출하지 않는 world 좌표 기준 독립 nearest-neighbor 검산."""
    transform=np.linalg.solve(affine,target_affine)
    output=np.zeros(shape,dtype=data.dtype)
    xy=np.indices(shape[:2],dtype=float).reshape(2,-1)
    for k in range(shape[2]):
        points=np.vstack([xy,np.full(xy.shape[1],k),np.ones(xy.shape[1])])
        coords=(transform@points)[:3]
        inside=np.all((coords>=0)&(coords<=np.array(data.shape)[:,None]-1),axis=0)
        q=np.floor(coords[:,inside]+0.5).astype(int)
        plane=np.zeros(xy.shape[1],dtype=data.dtype)
        plane[inside]=data[q[0],q[1],q[2]]
        output[:,:,k]=plane.reshape(shape[:2])
    return output


def build(study,inputs,completion,stage):
    t0=time.monotonic(); c=inputs['inputs'][study]
    verify_files({v['path']:v['sha256'] for v in c['files'].values()})
    verify_files(completion['result']['artifacts'])
    result_path=OUT/'build'/stage/(study+'.json')
    if result_path.exists():
        previous=read(result_path)
        if previous['source_input']!=c or previous['seg_completion']!=completion:raise ValueError('stale build input/config')
        verify_files({v['path']:v['sha256'] for v in previous['pngs'].values()})
        verify_files({previous['overlay']:previous['overlay_sha256']})
        return previous
    im=nib.load(c['files']['img.nii.gz']['path']); bm=nib.load(c['files']['brain.nii.gz']['path'])
    seg=nib.load(Path(completion['directory'])/'seg.nii.gz')
    native=np.asarray(resample_from_to(seg,(im.shape,im.affine),order=0,mode='constant',cval=0).dataobj)
    reference=independent_nn(np.asarray(seg.dataobj),seg.affine,im.shape,im.affine)
    mismatch=int(np.count_nonzero(native!=reference))
    if mismatch: raise ValueError(f'independent nearest neighbor mismatch {study}: {mismatch}')
    ic=nib.as_closest_canonical(im); bc=nib.as_closest_canonical(bm)
    sc=nib.as_closest_canonical(nib.Nifti1Image(native,im.affine))
    a=np.asarray(ic.dataobj,dtype=np.float32); b=np.asarray(bc.dataobj)>0; s=np.asarray(sc.dataobj)
    if nib.aff2axcodes(ic.affine)!=('R','A','S') or not np.isfinite(a).all():raise ValueError('RAS/finite')
    br=D.brain_range(b); U=D.pick(*br,0.05,0.95)
    if U!=c['U_idx'] or len(set(U))!=8:raise ValueError('U changed/lacks 8 slices')
    area=np.sum(np.isin(s,[4,43]),axis=(0,1)); fallback=None; A=None; arange=None
    if area.max()>0:
        keep=np.flatnonzero(area>=0.05*area.max()); arange=[int(keep.min()),int(keep.max())]
        A=np.rint(np.linspace(*arange,8)).astype(int).tolist()
        if len(set(A))!=8:A=None;fallback='lt8_unique'
    else:fallback='no_ventricle_voxels'
    if A is None:A=U.copy()
    lo,hi=D.intensity_window(a,b)
    if not np.isfinite([lo,hi]).all() or hi<=lo:raise ValueError('window')
    pngs={}; path=ROOT/'png'/stage/study;path.mkdir(parents=True,exist_ok=True)
    for k in sorted(set(U+A)):
        p=path/f's{k:03d}.png'; image=D.render_slice(a,k,lo,hi,ic.header.get_zooms()[:3])
        if p.exists():
            with Image.open(p) as old:
                if not np.array_equal(np.asarray(old.convert('RGB')),np.asarray(image)):raise ValueError('stale render')
        else:
            tmp=p.with_name(p.stem+'.part.png');image.save(tmp)
            __import__('os').link(tmp,p);tmp.unlink()
        pngs[str(k)]=dict(path=str(p),sha256=sha(p))
    overlay_path=OUT/'overlays'/stage/f'{study}.png';overlay_path.parent.mkdir(parents=True,exist_ok=True)
    canvas=Image.new('RGB',(896,448))
    for i,k in enumerate(A):
        base=np.array(D.render_slice(a,k,lo,hi,ic.header.get_zooms()[:3]))
        mask=np.array(D.render_slice(np.isin(s,[4,43]).astype(np.float32),k,0,1,ic.header.get_zooms()[:3]))[:,:,0]>127
        base[mask]=[255,80,20];canvas.paste(Image.fromarray(base).resize((224,224)),(i%4*224,i//4*224))
    if not overlay_path.exists():canvas.save(overlay_path)
    vol=completion['result']['volumes_mm3'];vent=vol['left lateral ventricle']+vol['right lateral ventricle'];icv=vol['total intracranial']
    result=dict(study_uid=study,series_id=c['key']['series_id'],U_idx=U,A_idx=A,A_range=arange,A_fallback=fallback,
       S=vent/icv,vent_mm3=vent,icv_mm3=icv,icv_source='official soft posterior volume CSV',
       window_p1_p99=[lo,hi],pngs=pngs,canonical_affine=ic.affine.tolist(),canonical_shape=list(a.shape),
       source_input=c,seg_completion=completion,nn_mismatches=mismatch,
       overlay=str(overlay_path),overlay_sha256=sha(overlay_path),warm_read_to_saved_s=time.monotonic()-t0)
    result['code_sha256']=sha(__file__)
    save(result_path,result);print('built',study,'fallback',fallback,flush=True)
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--stage',default='tech');ap.add_argument('--inputs',default=str(OUT/'tech_inputs.json'));a=ap.parse_args()
    inp=read(a.inputs)
    for study in sorted(inp['inputs']):
        p=OUT/'seg'/a.stage/(study+'.complete.json')
        if not p.exists():raise ValueError(f'incomplete official output: {study}')
        build(study,inp,read(p),a.stage)
