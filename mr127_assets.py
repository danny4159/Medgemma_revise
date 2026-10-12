"""공식 FreeSurfer annex 가중치를 고정 SHA로 확보하고 UCL 공식 소스를 분리한다."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile
import requests
from mr127_select import save, sha

ROOT=Path('/home/test/.local/share/medgemma/mr_rate/iter127')
FS_REV='4f8728e5132e8d39a8f1bf3d24d15fed62f4fc9d'
UCL_REV='2a2aa3bbfccb83f8253a51ca8b329b9938a2646d'
SOURCE=ROOT/'SynthSeg'
ENVPY=Path('results/environments/synthseg125/bin/python').absolute()


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    attempts=[]
    # 먼저 원 README에 명시된 UCL 배포 링크의 실제 상태를 기록한다.
    urls=['https://liveuclac-my.sharepoint.com/:u:/g/personal/rmappmb_ucl_ac_uk/EctEe3hOP8dDh1hYHlFS_rUBo80yFg7MQY5WnagHlWcS6A?e=e8bK0f',
          'https://liveuclac-my.sharepoint.com/:f:/g/personal/rmappmb_ucl_ac_uk/EtlNnulBSUtAvOP6S99KcAIBYzze7jTPsmFk2_iHqKDjEw?e=rBP0RO']
    for u in urls:
        r=requests.get(u,stream=True,timeout=40)
        attempts.append(dict(url=u,final_url=r.url,status=r.status_code))
        r.close()
    assert not SOURCE.exists()
    SOURCE.mkdir()
    archive=Path('results/external/synthseg_2a2aa3b.zip')
    files={}
    with zipfile.ZipFile(archive) as z:
        prefix='SynthSeg-'+UCL_REV+'/'
        for info in z.infolist():
            assert info.filename.startswith(prefix)
            rel=Path(info.filename[len(prefix):])
            assert not rel.is_absolute() and '..' not in rel.parts
            assert (info.external_attr>>16)&0o170000 != 0o120000
            if info.is_dir() or not rel.parts or rel.parts[0]=='models': continue
            dest=SOURCE/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as a,dest.open('xb') as b: shutil.copyfileobj(a,b)
            files[str(dest)]=sha(dest)
    weights={}
    for name in ['synthseg_2.0.h5','synthseg_qc_2.0.h5']:
        pointer_url=f'https://raw.githubusercontent.com/freesurfer/freesurfer/{FS_REV}/mri_synthseg/{name}'
        r=requests.get(pointer_url,timeout=40)
        r.raise_for_status()
        pointer=r.text.strip()
        key=pointer.split('/')[-1]
        m=re.fullmatch(r'SHA256E-s(\d+)--([0-9a-f]{64})\.0\.h5',key)
        assert m, pointer
        size=int(m[1]); digest=m[2]
        h=hashlib.md5(key.encode()).hexdigest()
        u=f'https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/repo/annex.git/annex/objects/{h[:3]}/{h[3:6]}/{key}/{key}'
        dst=SOURCE/'models'/name
        dst.parent.mkdir(exist_ok=True)
        t=time.monotonic()
        with requests.get(u,stream=True,timeout=90) as response:
            response.raise_for_status()
            with dst.open('xb') as f:
                for chunk in response.iter_content(4<<20): f.write(chunk)
            assert dst.stat().st_size==size and sha(dst)==digest
            weights[name]=dict(path=str(dst),size=size,sha256=digest,url=u,final_url=response.url,
                 pointer_url=pointer_url,pointer=pointer,pointer_sha256=hashlib.sha256(r.content).hexdigest(),
                 seconds=time.monotonic()-t,etag=response.headers.get('ETag'))
        print('verified',name,size,flush=True)
    freeze=subprocess.run([str(ENVPY),'-m','pip','freeze'],capture_output=True,text=True,check=True)
    save('results/iter_127/assets.json',dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         ucl_revision=UCL_REV,freesurfer_revision=FS_REV,ucl_archive=str(archive),ucl_archive_sha256=sha(archive),
         source_files=files,weights=weights,access_attempts=attempts,environment_python=str(ENVPY),
         environment_reused_without_modification=True,pip_freeze=freeze.stdout,
         source_license=(SOURCE/'LICENSE.txt').read_text(),
         training_overlap='합성 입력으로 학습한 공개 모델. MR-RATE 환자별 학습·선택 노출은 미검증.',
         source_sha256=sha(__file__)))


if __name__=='__main__': main()
