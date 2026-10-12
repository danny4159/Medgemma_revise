"""실제 입력 및 extraction/CSV 보호 경로의 필요한 회귀 검사."""
import csv
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

import nibabel as nib
import numpy as np
import mr128_data as D
from mr128_seg import csv_values, QC


def main():
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
    def rejects(name,fn):
        try: fn()
        except (ValueError,RuntimeError,FileNotFoundError,BlockingIOError): check(name,True)
        else: check(name,False)
    inp=D.read(D.OUT/'tech_inputs.json'); candidates=D.read(D.OUT/'tech_candidates.json')
    for study,c in inp['inputs'].items():
        im=nib.load(c['files']['img.nii.gz']['path']); bm=nib.load(c['files']['brain.nii.gz']['path'])
        check(study+':grid',im.shape==bm.shape and np.allclose(im.affine,bm.affine,atol=1e-3))
        can=nib.as_closest_canonical(im); bcan=nib.as_closest_canonical(bm)
        check(study+':RAS',nib.aff2axcodes(can.affine)==('R','A','S'))
        areas=np.sum(np.asarray(bcan.dataobj)>0,axis=(0,1)); valid=areas>=areas.max()*0.05
        runs=[]; start=None
        for k,ok in enumerate(list(valid)+[False]):
            if ok and start is None:start=k
            if not ok and start is not None:runs.append((start,k-1));start=None
        lo,hi=max(runs,key=lambda r:r[1]-r[0])
        expected=np.rint(np.linspace(lo+(hi-lo)*0.05,lo+(hi-lo)*0.95,8)).astype(int).tolist()
        check(study+':U8_independent',c['U_idx']==expected and len(set(expected))==8)
        z_world=[float((can.affine@np.array([0,0,k,1]))[2]) for k in expected]
        check(study+':inferior_superior',all(b>a for a,b in zip(z_world,z_world[1:])))
        xyz=np.array([[0,0,0,1],[im.shape[0]-1,im.shape[1]-1,im.shape[2]-1,1],[3,7,11,1]],float).T
        check(study+':world_roundtrip',np.allclose(np.linalg.inv(im.affine)@(im.affine@xyz),xyz,atol=1e-8))
    # 실제 입력과 분리한 소유 fixture 경로에서 부분 추출 재개와 cache 변조를 검사한다.
    with tempfile.TemporaryDirectory(dir=D.OUT,prefix='fixture_') as t:
        root=Path(t); original=D.ROOT; D.ROOT=root/'external'; D.ROOT.mkdir()
        try:
            images=[]
            for name,a in [('img.nii.gz',np.ones((8,9,10),np.float32)),('brain.nii.gz',np.ones((8,9,10),np.uint8))]:
                p=root/name; nib.save(nib.Nifti1Image(a,np.diag([1,1,4,1])),p); images.append(p)
            archive=root/'study.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.write(images[0],'s/img/s_t2.nii.gz');z.write(images[1],'s/seg/s_t2_brain-mask.nii.gz')
            dest=D.ROOT/'inputs/s/t2'; dest.mkdir(parents=True)
            shutil.copyfile(images[0],dest/'img.nii.gz')
            c=D.extract(archive,'s','t2'); check('partial_extraction_resume',len(c['files'])==2)
            check('completed_extraction_identical',D.extract(archive,'s','t2')==c)
            (dest/'img.nii.gz').write_bytes(b'tamper')
            rejects('completed_cache_tamper_rejected',lambda:D.extract(archive,'s','t2'))
            with zipfile.ZipFile(archive,'a') as z:z.writestr('extra',b'changed')
            rejects('changed_zip_rejected',lambda:D.extract(archive,'s','t2'))
        finally:D.ROOT=original
        p=root/'immutable.json';D.save(p,{'a':1});D.save(p,{'a':1})
        rejects('output_overwrite_rejected',lambda:D.save(p,{'a':2}))
        p.write_text('{"a":1,"a":2}')
        rejects('duplicate_json_rejected',lambda:D.read(p))
        p=root/'qc.csv'
        def qc(header,values,subject='img'):
            with p.open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['subject']+header);w.writerow([subject]+values)
        qc(QC,[0.8]*8);check('complete_qc_schema',len(csv_values(p,QC))==8)
        qc([],[]);rejects('empty_qc_rejected',lambda:csv_values(p,QC))
        qc(QC[:-1],[0.8]*7);rejects('missing_qc_rejected',lambda:csv_values(p,QC))
        qc(QC+[QC[0]],[0.8]*9);rejects('duplicate_qc_rejected',lambda:csv_values(p,QC))
        qc(QC,['nan']+[0.8]*7);rejects('nonfinite_qc_rejected',lambda:csv_values(p,QC))
        qc(QC,[0.8]*8,'other');rejects('wrong_subject_rejected',lambda:csv_values(p,QC))
    D.verify_files(D.read(D.OUT/'protocol.json')['preserved_results'])
    check('past_results_unchanged',True)
    out=dict(created_utc=D.utc(),checks=checks,all_pass=all(c['passed'] for c in checks),
             inputs_sha256=D.sha(D.OUT/'tech_inputs.json'),code_sha256=D.sha(__file__))
    D.save(D.OUT/'tests.json',out)
    print('checks',sum(c['passed'] for c in checks),'/',len(checks))
    return 0 if out['all_pass'] else 2


if __name__=='__main__':raise SystemExit(main())
