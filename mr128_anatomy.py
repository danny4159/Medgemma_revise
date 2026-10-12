"""실제 반환된 11개 전체-slice 영상의 해부학 감사 기록과 기술 입력 고정."""
from collections import defaultdict
from pathlib import Path
import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw
import mr123_data as D
from mr128_data import OUT, read, save, sha, verify_files, utc

# 영상 전체를 view_image로 반환받아 확인한 뒤 기록. 확장 여부는 판정하지 않음.
JUDGMENTS = {
 '44dc9047ce42':('eligible',[4,12,20,24],'하부 소뇌/뇌간에서 양측 대뇌와 vertex까지 연속 관측.'),
 'd2e39b0f5ab4':('excluded',[0,16,32,39],'경부·척수 중심. 마지막 일부 하부 뇌만 포함하며 양측 대뇌 coverage 없음.'),
 '05fe486e02c0':('eligible',[2,12,24,29],'소뇌/뇌간, 양측 대뇌, 상부 대뇌·vertex의 연속 coverage.'),
 '658bd95b7afd':('eligible',[4,16,28,35],'하부 뇌부터 양측 대뇌와 vertex까지 연속 coverage.'),
 'e1a69a01f472':('excluded',[0,16,32,42],'몸통·척추 중심. 두개 내 양측 대뇌가 없음.'),
 '71eff20b8cb9':('eligible',[6,18,30,38],'소뇌/뇌간에서 양측 대뇌와 vertex까지 연속 coverage.'),
 '20fac58bfd0e':('eligible',[4,12,20,25],'하부 뇌부터 양측 대뇌와 vertex까지 연속 coverage.'),
 '152f28de2ab5':('excluded',[0,16,32,39],'몸통·척추 중심. 두개 내 양측 대뇌가 없음.'),
 'b076ca298c46':('eligible',[5,12,18,23],'하부 뇌부터 양측 대뇌와 상부 vertex까지 연속 coverage.'),
 '5a75100453b2':('eligible',[4,14,24,31],'하부 뇌부터 양측 대뇌와 vertex까지 연속 coverage.'),
 'ad7188716419':('eligible',[4,12,20,24],'하부 뇌부터 양측 대뇌와 vertex까지 연속 coverage.'),
}


def main():
    candidates=read(OUT/'tech_candidates.json')
    if candidates['protocol_sha256']!=sha(OUT/'protocol.json'): raise ValueError('protocol')
    if set(JUDGMENTS)!={r['blind_id'] for r in candidates['records']}: raise ValueError('judgment completeness')
    groups=defaultdict(list); reviewed=[]
    for r in candidates['records']:
        verify_files({r['montage']:r['montage_sha256']})
        verify_files({v['path']:v['sha256'] for v in r['input']['files'].values()})
        decision,indices,reason=JUDGMENTS[r['blind_id']]
        reviewed.append(dict(blind_id=r['blind_id'],decision=decision,evidence_indices=indices,
           reason_ko=reason,reviewed_utc=utc(),evidence_image=r['montage'],evidence_sha256=r['montage_sha256'],
           actual_image_returned=True,tool='functions.exec -> tools.view_image -> image(image_url)',
           scope='해부학 및 coverage 입력 감사. 측뇌실 확장 여부나 임상 정답 판정 아님.'))
        groups[r['metadata']['study_uid']].append(r)
    save(OUT/'anatomy_judgments.json',dict(candidates_sha256=sha(OUT/'tech_candidates.json'),judgments=reviewed))
    prior=read('results/iter_127/data/selection_lock.json')['manifest']; inputs={}; changes=[]
    for study,rows in groups.items():
        rank=lambda r:(r['input']['spacing'][2],r['input']['spacing'][0]*r['input']['spacing'][1],r['metadata']['series_id'])
        ordered=sorted(rows,key=rank)
        eligible=[r for r in ordered if JUDGMENTS[r['blind_id']][0]=='eligible']
        if not eligible: raise ValueError(f'no eligible series: {study}')
        r=eligible[0]; c=r['input']; m=next(m for m in prior if m['study_uid']==study)
        a,b,info=D.load_case(c['files']['img.nii.gz']['path'],c['files']['brain.nii.gz']['path'])
        br=D.brain_range(b)
        if br is None: raise ValueError('brain mask range')
        u=D.pick(*br,0.05,0.95)
        if len(set(u))!=8: raise ValueError('U lacks unique 8 slices')
        if info['canon_axcodes']!='RAS' or not info['affine_match']: raise ValueError('canonical grid')
        inputs[study]=dict(**c,brain_range=list(br),U_idx=u,blind_id=r['blind_id'])
        changes.append(dict(study_uid=study,previous_series=m['series_id'],selected_series=r['metadata']['series_id'],
             changed=m['series_id']!=r['metadata']['series_id'],ranked_candidates=[dict(series=v['metadata']['series_id'],
             blind_id=v['blind_id'],decision=JUDGMENTS[v['blind_id']][0],reason=JUDGMENTS[v['blind_id']][2]) for v in ordered]))
    if len(inputs)!=8: raise ValueError('expected technical8')
    save(OUT/'tech_inputs.json',dict(protocol_sha256=sha(OUT/'protocol.json'),
         selection_sha256=sha('results/iter_127/data/selection_lock.json'),
         judgment_sha256=sha(OUT/'anatomy_judgments.json'),inputs=inputs,series_diff=changes))
    print('tech anatomy: eligible8; excluded candidate series3; series corrections',sum(c['changed'] for c in changes))


if __name__=='__main__': main()
