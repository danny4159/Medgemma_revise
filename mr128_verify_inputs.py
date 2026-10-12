"""전체 고정 환자·원 metadata·split·decoded volume·U8의 독립 읽기 전용 검산."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import nibabel as nib
import numpy as np
import pandas as pd
from mr128_data import OUT,META,read,save,sha,utc


def patients(obj):
    result=set()
    if isinstance(obj,dict):
        if 'patient_uid' in obj:result.add(int(obj['patient_uid']))
        for v in obj.values():result|=patients(v)
    elif isinstance(obj,list):
        for v in obj:result|=patients(v)
    return result


def main(suffix):
    manifest=read(OUT/'evaluation_manifest.json')['records'];inputs=read(OUT/'all_inputs.json')['inputs']
    original=read('results/iter_127/data/selection_lock.json')['manifest'];old=set()
    for p in ['results/iter_123/data/selection_lock.json','results/iter_124/data/eligibility_lock.json','results/iter_124/data/candidates.json']:
        if Path(p).exists():old|=patients(read(p))
    metadata={b:pd.read_csv(META/'metadata'/f'{b}_metadata.csv',low_memory=False,
        usecols=['study_uid','series_id','patient_uid','array_shape','array_spacing_mm','classified_modality','acquisition_plane','is_derived','is_localizer']) for b in ['batch04','batch23']}
    splits=pd.read_csv(META/'splits.csv');checks=[];volumes={}
    def check(name,condition):checks.append(dict(name=name,passed=bool(condition)))
    check('fixed_records',manifest==[{k:m[k] for k in ['patient_uid','study_uid','batch_id','label','role']} for m in original])
    check('patient_unique60',len({m['patient_uid'] for m in manifest})==60)
    check('old_patients_excluded',not ({m['patient_uid'] for m in manifest}&old))
    check('roles',Counter(m['role'] for m in manifest)=={'tech':8,'calib':12,'explore':40})
    for m in manifest:
        study=m['study_uid'];c=inputs[study];series=c['key']['series_id'];df=metadata[m['batch_id']]
        matched=df[(df.study_uid==study)&(df.series_id==series)]
        check(study+':unique_metadata',len(matched)==1)
        if len(matched)!=1:continue
        r=matched.iloc[0]
        check(study+':patient_link',int(r.patient_uid)==m['patient_uid'])
        check(study+':T2_axial_nonderived',r.classified_modality=='T2w' and r.acquisition_plane=='AXIAL' and not r.is_derived and not r.is_localizer)
        split=splits[(splits.batch_id==m['batch_id'])&(splits.study_uid==study)]
        check(study+':official_train',len(split)==1 and split.iloc[0].split=='train')
        image=nib.load(c['files']['img.nii.gz']['path']);mask=nib.load(c['files']['brain.nii.gz']['path'])
        check(study+':metadata_shape',list(image.shape)==json.loads(r.array_shape))
        check(study+':metadata_spacing',np.allclose(image.header.get_zooms()[:3],json.loads(r.array_spacing_mm),atol=1e-3))
        check(study+':mask_grid',image.shape==mask.shape and np.allclose(image.affine,mask.affine,atol=1e-3))
        can=nib.as_closest_canonical(image);bm=nib.as_closest_canonical(mask)
        a=np.asarray(can.dataobj,dtype=np.float32);b=np.asarray(bm.dataobj)>0
        check(study+':finite_RAS',np.isfinite(a).all() and nib.aff2axcodes(can.affine)==('R','A','S'))
        area=b.sum(axis=(0,1));valid=area>=area.max()*0.05;runs=[];start=None
        for i,v in enumerate(list(valid)+[False]):
            if v and start is None:start=i
            if not v and start is not None:runs.append((start,i-1));start=None
        lo,hi=max(runs,key=lambda r:r[1]-r[0])
        # 유지할 원 U의 IEEE-754 계산 순서와 Python ties-to-even round를 독립 재구성한다.
        positions=[lo+(hi-lo)*(0.05+(0.95-0.05)*i/7) for i in range(8)]
        indices=[round(p) for p in positions]
        check(study+':U8',indices==c['U_idx'] and len(set(indices))==8)
        z=[(can.affine@np.array([0,0,k,1]))[2] for k in indices]
        check(study+':inferior_superior',all(bb>aa for aa,bb in zip(z,z[1:])))
        h=hashlib.sha256();h.update(str(a.shape).encode());h.update(a.tobytes());volumes[study]=h.hexdigest()
    check('decoded_volume_unique60',len(volumes)==len(set(volumes.values()))==60)
    ok=all(c['passed'] for c in checks)
    save(OUT/('all_input_independent_checks'+suffix+'.json'),dict(created_utc=utc(),all_pass=ok,checks=checks,
         source_sha256=sha(__file__),all_inputs_sha256=sha(OUT/'all_inputs.json'),decoded_float32_volume_sha256=volumes,
         scope_ko='원 metadata의 환자·series·shape·spacing, train, 기존 환자 제외, decoded volume 중복, 독립 U8·방향 검산. 임상 판독이나 보고서 정답을 새로 만들지 않음.'))
    print('independent inputs',sum(c['passed'] for c in checks),'/',len(checks))
    return 0 if ok else 2


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--suffix',default='_v2');a=ap.parse_args()
    raise SystemExit(main(a.suffix))
