"""iter128: 고정 환자의 출력 독립 뇌 series 감사와 안전한 입력 추출."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid
import zipfile

import nibabel as nib
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
import mr123_data as D

OUT = Path('results/iter_128')
ROOT = Path('/home/test/.local/share/medgemma/mr_rate/iter128')
META = ROOT.parent / 'meta'
REV = 'f6e39794e7820c96c18465231a30da424e6d1c69'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''): h.update(b)
    return h.hexdigest()


def read(p):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d: raise ValueError(f'duplicate key: {k}')
            d[k] = v
        return d
    return json.loads(Path(p).read_text(), object_pairs_hook=pairs)


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def save(p, value):
    """원자적 배타 생성. 기존 동일 내용만 재사용, 다른 내용은 거부."""
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode()
    if p.exists():
        if p.read_bytes() != data: raise ValueError(f'existing output differs: {p}')
        return
    tmp = p.with_name(p.name + '.' + uuid.uuid4().hex + '.part')
    with tmp.open('xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    os.link(tmp, p)
    tmp.unlink()


def verify_files(d):
    for p, h in d.items():
        if sha(p) != h: raise ValueError(f'digest mismatch: {p}')


def init():
    if (OUT/'protocol.json').exists():
        p = read(OUT/'protocol.json'); verify_files(p['inputs']); verify_files(p['source_before']); return
    before = {}
    for directory in ['results/iter_125','results/iter_126','results/iter_127']:
        before.update({str(p):sha(p) for p in Path(directory).rglob('*') if p.is_file()})
    prov = read('results/iter_127/data/provenance.json')
    verify_files(prov['inputs'])
    comp = read('results/iter_127/completion.json')
    # 원 completion의 schema를 그대로 보존하며 모든 과거 결과도 별도 잠금한다.
    files = dict(prov['inputs'])
    for i in [125,126,127,128]:
        for name in ['plan.md','plan.json']:
            p = f'../agent/runs/iter_{i}/'+name; files[p] = sha(p)
    for p in ['results/iter_127/data/selection_lock.json','results/iter_127/data/budget_lock.json',
              'results/iter_127/fs_assets.json','results/iter_127/environment_record.json',
              '../agent/runs/iter_125/reuse_manifest.json']:
        files[p] = sha(p)
    fs = read('results/iter_127/fs_assets.json'); verify_files(fs['files'])
    save(OUT/'protocol.json', dict(created_utc=utc(), revision=REV, inputs=files,
         preserved_results=before, source_before={p:sha(p) for p in ['mr123_data.py','mr125_build.py','mr127_seg.py','mr127_seg_entry.py','mr127_verify_selection.py']},
         source_current={__file__:sha(__file__)}, rules=dict(
         eligible='두개 내 양측 대뇌, 하부 뇌부터 상부 대뇌까지 연속 coverage. 3D/finite/affine/brain-grid 검증.',
         excluded='몸통/경부/척수 중심, localizer, 뇌 일부만 포함한 명백한 제한 coverage, 파일/격자 오류.',
         uncertain='부위 또는 coverage 판정 불확실. 적격 승격 금지.',
         ranking=['slice_spacing','in_plane_voxel_area','series_id'],
         blind_fields=['report','label','role','prior_segmentation','performance'],
         no_clinical_ground_truth=True),
         stage_order=['tech_anatomy','tech_synthseg','all_anatomy','tech_generation','calibration','explore'],
         fixed_patient_count=60, fixed_roles={'tech':8,'calibration':12,'explore':40},
         seg_version='FreeSurfer SynthSeg2.0 default --vol --qc --noaddctab',
         calibration_rule={'candidates':'0, adjacent distinct score midpoints, nextafter(max,+inf)',
                           'positive_operator':'>=', 'tie_break':['BA','specificity','larger_threshold']},
         stop_rule='적격 입력 또는 공식 기술 조건이 성립하지 않으면 현재 설계를 보류. 추가 환자·환경·prompt 탐색 없음.'))
    print('protocol locked', sha(OUT/'protocol.json'), flush=True)


def extract(zip_path, study, series):
    directory = ROOT/'inputs'/study/series
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory/'extract.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        digest = sha(zip_path)
        expected = {f'{study}/img/{study}_{series}.nii.gz':'img.nii.gz',
                    f'{study}/seg/{study}_{series}_brain-mask.nii.gz':'brain.nii.gz'}
        key = dict(zip_sha256=digest, revision=REV, study_uid=study, series_id=series, members=expected)
        if (directory/'complete.json').exists():
            c = read(directory/'complete.json')
            if c['key'] != key: raise ValueError('stale extraction cache')
            verify_files({v['path']:v['sha256'] for v in c['files'].values()}); return c
        files = {}
        with zipfile.ZipFile(zip_path) as z:
            for member, name in expected.items():
                found = [i for i in z.infolist() if i.filename == member]
                if len(found) != 1: raise ValueError(f'missing/duplicate ZIP member: {member}')
                info = found[0]
                if '..' in Path(member).parts or Path(member).is_absolute() or (info.external_attr>>16)&0o170000 == 0o120000:
                    raise ValueError('unsafe ZIP member')
                dst = directory/name
                tmp = directory/(name+'.'+uuid.uuid4().hex+'.part')
                with z.open(info) as s, tmp.open('xb') as f: shutil.copyfileobj(s, f); f.flush(); os.fsync(f.fileno())
                if tmp.stat().st_size != info.file_size: raise ValueError('size mismatch')
                h = sha(tmp)
                if dst.exists():
                    if dst.is_symlink() or sha(dst) != h: raise ValueError('partial extraction conflicts')
                    tmp.unlink()
                else: os.link(tmp, dst); tmp.unlink()
                files[name] = dict(path=str(dst),sha256=h,size=info.file_size,member=member,crc=info.CRC)
        image = nib.load(files['img.nii.gz']['path']); brain = nib.load(files['brain.nii.gz']['path'])
        if len(image.shape)!=3 or image.shape!=brain.shape or not np.allclose(image.affine,brain.affine,atol=1e-3): raise ValueError('image/mask grid')
        if not np.isfinite(image.get_fdata()).all() or not np.isfinite(brain.get_fdata()).all(): raise ValueError('nonfinite')
        if not np.isfinite(image.affine).all() or abs(np.linalg.det(image.affine[:3,:3]))<1e-8: raise ValueError('affine')
        c = dict(key=key,files=files,shape=list(image.shape),affine=image.affine.tolist(),
                 spacing=list(map(float,image.header.get_zooms()[:3])),axcodes=''.join(nib.aff2axcodes(image.affine)))
        save(directory/'complete.json', c); return c


def prepare_tech():
    init()
    selection = read('results/iter_127/data/selection_lock.json')['manifest']
    budget = read('results/iter_127/data/budget_lock.json')
    from huggingface_hub import HfApi
    os.environ['HF_TOKEN_PATH']='/home/test/.cache/huggingface/token'
    objects = budget['official_objects']
    infos = HfApi().get_paths_info('Forithmus/MR-RATE',sorted(objects),repo_type='dataset',revision=REV)
    if {i.path:(i.size,i.lfs.sha256) for i in infos} != {p:(v['size'],v['sha256']) for p,v in objects.items()}: raise ValueError('official budget changed')
    if sum(v['size'] for v in objects.values()) != 15552030509: raise ValueError('budget mismatch')
    existing = budget['verified_existing']
    for rel,v in existing.items():
        if Path(v['path']).stat().st_size!=objects[rel]['size'] or sha(v['path'])!=objects[rel]['sha256']: raise ValueError('ZIP bytes')
    save(OUT/'budget_verified.json',dict(prior_budget_sha256=sha('results/iter_127/data/budget_lock.json'),
         official_objects=objects,total_zip_count=len(objects),total_bytes=sum(v['size'] for v in objects.values()),
         existing_verified=len(existing),new_zip_count=budget['new_zip_count'],new_bytes=budget['new_bytes'],
         free_external=shutil.disk_usage(ROOT.parent).free,free_ssd=shutil.disk_usage('.').free))
    records = []
    for batch in ['batch04','batch23']:
        ids = {m['study_uid'] for m in selection if m['role']=='tech' and m['batch_id']==batch}
        cols=['study_uid','series_id','classified_modality','acquisition_plane','is_derived','is_localizer','array_shape','array_spacing_mm']
        df=pd.read_csv(META/'metadata'/f'{batch}_metadata.csv',usecols=cols,low_memory=False)
        df=df[df.study_uid.isin(ids)&(df.classified_modality=='T2w')&(df.acquisition_plane=='AXIAL')&(~df.is_derived)&(~df.is_localizer)]
        for m in df.to_dict('records'):
            study=m['study_uid']; series=m['series_id']; rel=f'mri/{batch}/{study}.zip'
            c=extract(existing[rel]['path'],study,series)
            if not np.allclose(c['spacing'],json.loads(m['array_spacing_mm']),atol=1e-3): raise ValueError('metadata spacing')
            bid=hashlib.sha256((study+'|'+series+'|128').encode()).hexdigest()[:12]
            im=nib.as_closest_canonical(nib.load(c['files']['img.nii.gz']['path']))
            a=np.asarray(im.dataobj,dtype=np.float32)
            v=a[a>0]; lo,hi=np.percentile(v,[1,99])
            nz=a.shape[2]; tile=144; rows=(nz+7)//8
            path=OUT/'anatomy'/f'{bid}.png'; path.parent.mkdir(parents=True,exist_ok=True)
            canvas=Image.new('RGB',(8*tile,rows*(tile+20))); draw=ImageDraw.Draw(canvas)
            for k in range(nz):
                s=np.uint8(np.clip((a[:,:,k]-lo)/max(hi-lo,1e-6),0,1)*255).T[::-1,::-1]
                img=Image.fromarray(s).convert('RGB'); img.thumbnail((tile,tile))
                x=k%8*tile; y=k//8*(tile+20)
                canvas.paste(img,(x+(tile-img.width)//2,y)); draw.text((x+4,y+tile),str(k),fill='white')
            if path.exists(): raise ValueError('existing montage requires completed manifest')
            canvas.save(path)
            records.append(dict(blind_id=bid,metadata=m,batch_id=batch,input=c,montage=str(path),montage_sha256=sha(path),
                                shown_slices=list(range(nz)),canonical_shape=list(a.shape),canonical_affine=im.affine.tolist()))
    save(OUT/'tech_candidates.json',dict(protocol_sha256=sha(OUT/'protocol.json'),records=records))
    print('blind anatomy sheets',len(records),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('action',choices=['init','tech']); args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True); ROOT.mkdir(parents=True,exist_ok=True)
    with (OUT/'data.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        init() if args.action=='init' else prepare_tech()
