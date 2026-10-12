"""공식 기술8명 통과 후에만 고정 나머지52 study의 다운로드·눈가림 입력표 준비."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import io
import os
from pathlib import Path
import time

import nibabel as nib
import numpy as np
import pandas as pd
from PIL import Image,ImageDraw
from mr128_data import OUT,ROOT,META,REV,read,save,sha,verify_files,extract,utc


def tech_gate():
    expected=read(OUT/'tech_inputs.json')['inputs']
    config=OUT/'seg/tech/config.json'
    if len(expected)!=8:raise ValueError('tech8')
    for study in expected:
        p=OUT/'seg/tech'/(study+'.complete.json');c=read(p)
        if c['config_sha256']!=sha(config) or c['returncode']!=0:raise ValueError('technical completion')
        verify_files(c['result']['artifacts'])
    return {str(OUT/'seg/tech'/(s+'.complete.json')):sha(OUT/'seg/tech'/(s+'.complete.json')) for s in expected}


def download():
    gate=tech_gate();budget=read(OUT/'budget_verified.json')
    from huggingface_hub import hf_hub_download
    os.environ['HF_TOKEN_PATH']='/home/test/.cache/huggingface/token'
    selected=read('results/iter_127/data/selection_lock.json')['manifest']
    records=[m for m in selected if m['role']!='tech']
    if len(records)!=52:raise ValueError('remaining52')
    authorization=dict(tech_gate=gate,budget_sha256=sha(OUT/'budget_verified.json'),
         selected_studies=[m['study_uid'] for m in records])
    if (OUT/'remaining_authorization.json').exists():
        previous=read(OUT/'remaining_authorization.json')
        if {k:previous[k] for k in authorization}!=authorization:raise ValueError('changed remaining authorization')
    else:save(OUT/'remaining_authorization.json',dict(**authorization,created_utc=utc()))
    prior=read('results/iter_127/data/budget_lock.json')['verified_existing']
    def fetch(m):
        study=m['study_uid'];rel=f"mri/{m['batch_id']}/{study}.zip";obj=budget['official_objects'][rel]
        target=OUT/'downloads'/(study+'.json')
        if target.exists():
            v=read(target)
            if v['revision']!=REV or v['sha256']!=obj['sha256'] or Path(v['path']).stat().st_size!=obj['size'] or sha(v['path'])!=v['sha256']:raise ValueError('stale download')
            return v
        t0=time.monotonic()
        if rel in prior:p=prior[rel]['path']
        else:p=hf_hub_download('Forithmus/MR-RATE',rel,repo_type='dataset',revision=REV,
              local_dir=str(ROOT/'raw'),cache_dir=str(ROOT/'cache'))
        if Path(p).stat().st_size!=obj['size'] or sha(p)!=obj['sha256']:raise ValueError('download digest')
        v=dict(path=p,size=obj['size'],sha256=obj['sha256'],revision=REV,study_uid=study,
               reused=rel in prior,wall_s=time.monotonic()-t0)
        save(target,v);print('download verified',study,obj['size'],flush=True);return v
    with ThreadPoolExecutor(max_workers=2) as pool:ledger=list(pool.map(fetch,records))
    save(OUT/'remaining_downloads.json',dict(records=ledger,authorization_sha256=sha(OUT/'remaining_authorization.json')))


def sheets():
    tech_gate()
    if (OUT/'remaining_candidates.json').exists():
        previous=read(OUT/'remaining_candidates.json')
        if previous['protocol_sha256']!=sha(OUT/'protocol.json'):raise ValueError('stale candidates')
        verify_files({r['montage']:r['montage_sha256'] for r in previous['records']})
        verify_files({v['path']:v['sha256'] for r in previous['records'] for v in r['input']['files'].values()})
        return
    downloads={v['study_uid']:v for v in read(OUT/'remaining_downloads.json')['records']}
    selected=read('results/iter_127/data/selection_lock.json')['manifest'];out=[]
    for batch in ['batch04','batch23']:
        ids={m['study_uid'] for m in selected if m['role']!='tech' and m['batch_id']==batch}
        cols=['study_uid','series_id','classified_modality','acquisition_plane','is_derived','is_localizer','array_shape','array_spacing_mm']
        df=pd.read_csv(META/'metadata'/f'{batch}_metadata.csv',usecols=cols,low_memory=False)
        df=df[df.study_uid.isin(ids)&(df.classified_modality=='T2w')&(df.acquisition_plane=='AXIAL')&(~df.is_derived)&(~df.is_localizer)]
        for m in df.to_dict('records'):
            study=m['study_uid'];series=m['series_id'];c=extract(downloads[study]['path'],study,series)
            if not np.allclose(c['spacing'],__import__('json').loads(m['array_spacing_mm']),atol=1e-3):raise ValueError('spacing')
            bid=hashlib.sha256((study+'|'+series+'|128').encode()).hexdigest()[:12]
            im=nib.as_closest_canonical(nib.load(c['files']['img.nii.gz']['path']));a=np.asarray(im.dataobj,dtype=np.float32)
            lo,hi=np.percentile(a[a>0],[1,99]);nz=a.shape[2];tile=144
            canvas=Image.new('RGB',(tile*8,((nz+7)//8)*(tile+20)));draw=ImageDraw.Draw(canvas)
            for k in range(nz):
                s=np.uint8(np.clip((a[:,:,k]-lo)/max(hi-lo,1e-6),0,1)*255).T[::-1,::-1]
                image=Image.fromarray(s).convert('RGB');image.thumbnail((tile,tile));x=k%8*tile;y=k//8*(tile+20)
                canvas.paste(image,(x+(tile-image.width)//2,y));draw.text((x+4,y+tile),str(k),fill='white')
            p=OUT/'anatomy_remaining'/(bid+'.png');p.parent.mkdir(parents=True,exist_ok=True)
            buffer=io.BytesIO();canvas.save(buffer,format='PNG');data=buffer.getvalue()
            if p.exists():
                if p.read_bytes()!=data:raise ValueError('existing montage differs')
            else:
                with p.open('xb') as f:f.write(data)
            out.append(dict(blind_id=bid,metadata=m,batch_id=batch,input=c,montage=str(p),montage_sha256=sha(p),
                            shown_slices=list(range(nz)),canonical_shape=list(a.shape),canonical_affine=im.affine.tolist()))
            print('sheet',bid,flush=True)
    if {r['metadata']['study_uid'] for r in out}!=set(downloads):raise ValueError('candidate completeness')
    save(OUT/'remaining_candidates.json',dict(protocol_sha256=sha(OUT/'protocol.json'),records=out))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['download','sheets']);a=ap.parse_args()
    with (OUT/'remaining.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        download() if a.action=='download' else sheets()
