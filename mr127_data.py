"""iter127 고정 표본의 공식 ZIP 예산/bytes 검증과 원자적 기술 입력 추출."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import zipfile
import numpy as np
import nibabel as nib
from mr127_select import read,save,sha,OUT

ROOT=Path('/home/test/.local/share/medgemma/mr_rate/iter127')
REV='f6e39794e7820c96c18465231a30da424e6d1c69'


def budget():
    os.environ['HF_TOKEN_PATH']='/home/test/.cache/huggingface/token'
    from huggingface_hub import HfApi
    manifest=read(OUT/'selection_lock.json')['manifest']
    existing={}
    for p in ['results/iter_123/data/fetch_ledger.json','results/iter_125/data/fetch_ledger.json']:
        for study,v in read(p).items():
            rel=v['path'].split('/raw/')[-1]
            assert rel not in existing
            existing[rel]=v
    paths={f"mri/{m['batch_id']}/{m['study_uid']}.zip" for m in manifest}|set(existing)
    infos={i.path:i for i in HfApi().get_paths_info('Forithmus/MR-RATE',sorted(paths),repo_type='dataset',revision=REV)}
    assert set(infos)==paths
    verified={}
    for rel,v in existing.items():
        i=infos[rel]
        assert v['revision']==REV
        assert Path(v['path']).stat().st_size==i.size==v['size']
        digest=sha(v['path'])
        assert digest==i.lfs.sha256==v['sha256']
        verified[rel]=dict(**v,verified_actual_sha256=digest)
    original=read('results/iter_125/handoff_codex/audit.json')['budget']
    objects={p:dict(size=i.size,sha256=i.lfs.sha256) for p,i in infos.items()}
    total=sum(i.size for i in infos.values())
    need=paths-set(existing)
    free=shutil.disk_usage(ROOT.parent).free
    assert free>sum(infos[p].size for p in need)*3
    save(OUT/'budget_lock.json',dict(revision=REV,selection_sha256=sha(OUT/'selection_lock.json'),
         official_objects=objects,verified_existing=verified,
         total_zip_count=len(paths),total_bytes=total,limit_bytes=total,
         existing_zip_count=len(existing),existing_bytes=sum(infos[p].size for p in existing),
         new_zip_count=len(need),new_bytes=sum(infos[p].size for p in need),
         delta_bytes_vs_old_plan=total-original['planned_cumulative_bytes'],
         added_paths=sorted(paths-set(original['official_objects'])),
         removed_undownloaded_paths=sorted(set(original['official_objects'])-paths),
         free_bytes_external=free,free_bytes_ssd=shutil.disk_usage('.').free,
         estimate_note_ko='기존62 ZIP 보존과 새60명 필요 객체의 합집합. 모든 실제 객체 bytes와 SHA 검증. 이후 필요한 T2/brain member만 추출.',
         source_sha256=sha(__file__),created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    print('budget',len(paths),total,'new',len(need),sum(infos[p].size for p in need))


def extract_tech():
    manifest=read(OUT/'selection_lock.json')['manifest']
    b=read(OUT/'budget_lock.json')
    assert b['selection_sha256']==sha(OUT/'selection_lock.json')
    inputs={}
    for m in manifest:
        if m['role']!='tech': continue
        rel=f"mri/{m['batch_id']}/{m['study_uid']}.zip"
        v=b['verified_existing'][rel]
        assert sha(v['path'])==b['official_objects'][rel]['sha256']
        directory=ROOT/'inputs'/m['study_uid']/m['series_id']
        directory.mkdir(parents=True,exist_ok=False)
        expected={f"{m['study_uid']}/img/{m['study_uid']}_{m['series_id']}.nii.gz":'img.nii.gz',
                  f"{m['study_uid']}/seg/{m['study_uid']}_{m['series_id']}_brain-mask.nii.gz":'brain.nii.gz'}
        files={}
        with zipfile.ZipFile(v['path']) as z:
            for member,name in expected.items():
                matches=[i for i in z.infolist() if i.filename==member]
                assert len(matches)==1
                i=matches[0]
                assert '..' not in Path(member).parts and not Path(member).is_absolute()
                assert (i.external_attr>>16)&0o170000!=0o120000
                dst=directory/name
                with z.open(i) as s,dst.open('xb') as d: shutil.copyfileobj(s,d)
                assert dst.stat().st_size==i.file_size
                files[name]=dict(path=str(dst),sha256=sha(dst),member=member,crc=i.CRC,size=i.file_size)
        image=nib.load(files['img.nii.gz']['path']); brain=nib.load(files['brain.nii.gz']['path'])
        assert len(image.shape)==3 and image.shape==brain.shape and np.allclose(image.affine,brain.affine,atol=1e-3)
        assert np.isfinite(image.get_fdata()).all() and np.isfinite(brain.get_fdata()).all()
        assert np.isfinite(image.affine).all() and abs(np.linalg.det(image.affine[:3,:3]))>0
        assert np.allclose(image.header.get_zooms()[:3],json.loads(m['array_spacing_mm']),atol=1e-3)
        inputs[m['study_uid']]=dict(files=files,patient_uid=m['patient_uid'],series_id=m['series_id'],
             zip_sha256=b['official_objects'][rel]['sha256'],revision=REV,
             shape=list(image.shape),affine=image.affine.tolist(),native_spacing=[float(x) for x in image.header.get_zooms()[:3]],
             axcodes=''.join(nib.aff2axcodes(image.affine)))
    assert len(inputs)==8
    save(OUT/'tech_inputs.json',dict(selection_sha256=sha(OUT/'selection_lock.json'),inputs=inputs,
         budget_sha256=sha(OUT/'budget_lock.json'),source_sha256=sha(__file__)))
    print('tech extracted',len(inputs))


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('action',choices=['budget','tech']); a=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'data.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        budget() if a.action=='budget' else extract_tech()
