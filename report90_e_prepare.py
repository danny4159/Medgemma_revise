"""V 선택 잠금 후에만 E를 추출하고 기존 노출·보호·T/V pixel과 대조한다."""
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image
import report89_data as B
import report90_data as N
import report89_model as M
from report86_common import save,sha
from rsna_diag.geometry import pad_offsets,canvas_to_norm
OUT=N.OUT/'recovery'

def main():
    choice=OUT/'selection/final.json';lock=B.read(choice);assert lock['passed'] and not lock['E_opened']
    for p,h in lock['sources'].items():assert sha(p)==h
    for item in lock['selected'].values():assert sha(item['checkpoint'])==item['checkpoint_sha']
    selection=B.read(N.OUT/'data/selection.json');assert sha(N.OUT/'data/selection.json')==B.read(N.OUT/'data/selection_lock.json')['selection_sha256']
    original=selection['E128'];assert len(original)==128
    root=OUT/'data/E128';assert not root.exists(), '기존 E 추출 보존'
    reports,_,links=B.D.load_inputs();byid={r['ImageID']:r for r in reports}
    prior=B.read(B.OUT/'data/selection_lock.json')
    forbidden_pat=set(prior['exposed_patients'])|set(prior['protected_patients'])
    tv=[r for s in ['T512','V64'] for r in B.read(N.OUT/f'data/{s}/manifest.json')]
    old_ids={r['ImageID'] for p in B.EXPOSED for r in B.walk(B.read(B.ROOT/p)) if r.get('ImageID') in links['img2patient']}
    banned_ids=old_ids|{r['ImageID'] for r in tv}
    banned_studies={byid[i]['StudyID'] for i in banned_ids}
    forbidden_pat|={r['PatientID'] for r in tv}
    z=B.D.open_image_zip();index=B.D.zip_index(z)
    def pixels(iid):
        raw=z.read(index[iid]);a=np.asarray(Image.open(io.BytesIO(raw)));assert a.ndim==2 and a.dtype==np.uint16
        u8=(a//256).astype(np.uint8)
        return raw,a,u8,hashlib.sha256(a.tobytes()).hexdigest(),hashlib.sha256(u8.tobytes()).hexdigest()
    banned_raw=set();banned_u8=set()
    for iid in sorted(banned_ids):
        _,_,_,rh,uh=pixels(iid);banned_raw.add(rh);banned_u8.add(uh)
    candidates={}
    for source in reports:
        iid=source['ImageID'];pid=links['img2patient'][iid]
        if links['img2split'][iid]!='test' or pid in forbidden_pat or source['StudyID'] in banned_studies:continue
        fs,ex=N.current_findings(source)
        if not fs:continue
        abnormal=any(f.get('abnormal') is True for f in source['findings'])
        row=dict(ImageID=iid,PatientID=pid,StudyID=source['StudyID'],split='test',
                 original_abnormal=abnormal,retained_abnormal=any(f.get('abnormal') is True for f in fs),
                 stratum=B.stratum(fs,abnormal),excluded_sentences=ex)
        if pid not in candidates or B.key(row)<B.key(candidates[pid]):candidates[pid]=row
    pool=sorted(candidates.values(),key=B.key)
    reserved={r['PatientID'] for r in original};used_pat=set();used_study=set();seen_raw=set();seen_u8=set();replacements=[];manifest=[]
    root.mkdir(parents=True,exist_ok=False)
    def inspect(row):
        assert row['split']=='test' and links['img2patient'][row['ImageID']]==row['PatientID']
        data=pixels(row['ImageID']);rh,uh=data[-2:]
        valid=row['PatientID'] not in forbidden_pat|used_pat and row['StudyID'] not in banned_studies|used_study
        valid=valid and rh not in banned_raw|seen_raw and uh not in banned_u8|seen_u8
        return valid,data
    for initial in original:
        row=initial;valid,data=inspect(row)
        if not valid:
            replacement=None
            for candidate in pool:
                if candidate['PatientID'] in reserved or candidate['stratum']!=initial['stratum'] or candidate['retained_abnormal']!=initial['retained_abnormal']:continue
                ok,newdata=inspect(candidate)
                if ok:replacement=candidate;data=newdata;break
            assert replacement is not None, '동일 split/층의 중복 없는 대체 표본 부족'
            row=replacement;reserved.add(row['PatientID']);replacements.append(dict(before=initial,after=row,reason='ID/study/pixel leakage gate; model outputs unopened'))
        raw,a,u8,rh,uh=data;fs,ex=N.current_findings(byid[row['ImageID']]);assert fs and ex==row['excluded_sentences']
        h,w=a.shape;top,left,side=pad_offsets(h,w)
        fs=[dict(f,canvas_boxes=[canvas_to_norm([x0*w,y0*h,x1*w,y1*h],top,left,side) for x0,y0,x1,y1 in f.get('boxes',[])]) for f in fs]
        rawpath=root/(row['ImageID']+'.raw.png');image=root/row['ImageID'];assert not rawpath.exists() and not image.exists()
        rawpath.write_bytes(raw);Image.fromarray(u8).save(image)
        assert np.array_equal(np.asarray(Image.open(rawpath)),a) and np.array_equal(np.asarray(Image.open(image)),u8)
        manifest.append(dict(row,findings=fs,report=' '.join(f['sentence_en'].strip() for f in fs),image=str(image),raw_path=str(rawpath),
            file_sha256=sha(image),raw_sha256=sha(rawpath),raw_pixel_sha256=rh,u8_pixel_sha256=uh,shape=[h,w],pad=[top,left,side],
            zip_member=index[row['ImageID']].filename,zip_crc=index[row['ImageID']].CRC))
        used_pat.add(row['PatientID']);used_study.add(row['StudyID']);seen_raw.add(rh);seen_u8.add(uh)
    assert len(manifest)==len(used_pat)==len(seen_raw)==len(seen_u8)==128
    assert sum(r['retained_abnormal'] for r in manifest)==96 and sum(not r['original_abnormal'] for r in manifest)==32
    save(root/'manifest.json',manifest);save(root/'replacements.json',replacements)
    report_req=[dict(id=r['ImageID']+'|report',image=r['image'],file_sha256=r['file_sha256'],prompt=M.CFG['report_prompt']) for r in manifest]
    cure_req=[dict(id=r['ImageID']+'|report',image=r['raw_path'],file_sha256=r['raw_sha256'],prompt='Generate a grounded report.') for r in manifest]
    box=sorted([r for r in manifest if r['stratum']=='abnormal_box'],key=B.key)[:32];assert len(box)==32
    ground_req=[dict(id=r['ImageID']+'|ground',image=r['image'],file_sha256=r['file_sha256'],prompt=M.ground_target(r,0)[0]) for r in box]
    save(root/'report_requests.json',report_req);save(root/'cure_requests.json',cure_req)
    save(root/'box32_manifest.json',box);save(root/'ground_requests.json',ground_req)
    save(root/'recheck24.json',[dict(id=r['ImageID'],patient=r['PatientID']) for r in sorted(manifest,key=B.key)[:24]])
    save(root/'completion.json',dict(passed=True,n=128,reference_written=False,selection_sha=sha(choice),
        excluded_existing_images=len(banned_ids),excluded_patients=len(forbidden_pat),replacements=len(replacements),
        patient_study_image_raw_u8_overlap=0,
        sources={str(p):sha(p) for p in [choice,N.OUT/'data/selection.json',N.OUT/'data/selection_lock.json',Path(__file__),Path('report90_data.py'),Path('report89_model.py')]},
        files={str(p):sha(p) for p in root.iterdir() if p.is_file()}))
    print('E128 자료·노출 분리 검사 PASS; reference 작성 뒤 생성 가능; replacement',len(replacements))

if __name__=='__main__':main()
