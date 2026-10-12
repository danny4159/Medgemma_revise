"""전체60명의 같은 규칙 적용·고정 선정 불변·U8 무결성·분리 manifest 봉인."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import nibabel as nib
import numpy as np
import mr123_data as D
from mr128_data import OUT,read,save,sha,verify_files,utc
from mr128_remaining import tech_gate


def main():
    tech_gate();parts=sorted(OUT.glob('anatomy_remaining_review_part*.json'))
    cand=read(OUT/'remaining_candidates.json');judgments={}
    for p in parts:
        v=read(p)
        if v['candidates_sha256']!=sha(OUT/'remaining_candidates.json'):raise ValueError('review source')
        for j in v['judgments']:
            if j['blind_id'] in judgments:raise ValueError('duplicate judgment')
            if not j['actual_image_returned']:raise ValueError('no actual image')
            judgments[j['blind_id']]=j
    if set(judgments)!={r['blind_id'] for r in cand['records']}:raise ValueError('review completeness')
    groups=defaultdict(list)
    for r in cand['records']:
        verify_files({r['montage']:r['montage_sha256']})
        if judgments[r['blind_id']]['montage_sha256']!=r['montage_sha256']:raise ValueError('visual evidence')
        groups[r['metadata']['study_uid']].append(r)
    original=read('results/iter_127/data/selection_lock.json')['manifest']
    tech=read(OUT/'tech_inputs.json');inputs=dict(tech['inputs']);diff=list(tech['series_diff']);failures=[]
    for study,rows in groups.items():
        rank=lambda r:(json.loads(r['metadata']['array_spacing_mm'])[2],
             np.prod(json.loads(r['metadata']['array_spacing_mm'])[:2]),r['metadata']['series_id'])
        ordered=sorted(rows,key=rank);eligible=[r for r in ordered if judgments[r['blind_id']]['decision']=='eligible']
        if not eligible:failures.append(dict(study_uid=study,error='no eligible brain T2'));continue
        r=eligible[0];c=r['input'];m=next(m for m in original if m['study_uid']==study)
        verify_files({v['path']:v['sha256'] for v in c['files'].values()})
        a,b,info=D.load_case(c['files']['img.nii.gz']['path'],c['files']['brain.nii.gz']['path'])
        br=D.brain_range(b)
        if br is None:failures.append(dict(study_uid=study,error='no valid brain-mask range'));continue
        u=D.pick(*br,0.05,0.95)
        if len(set(u))!=8 or info['canon_axcodes']!='RAS' or not info['affine_match']:
            failures.append(dict(study_uid=study,error='U8/canonical grid'));continue
        inputs[study]=dict(**c,brain_range=list(br),U_idx=u,blind_id=r['blind_id'])
        diff.append(dict(study_uid=study,previous_series=m['series_id'],selected_series=r['metadata']['series_id'],
             changed=m['series_id']!=r['metadata']['series_id'],ranked_candidates=[dict(series=v['metadata']['series_id'],
             blind_id=v['blind_id'],decision=judgments[v['blind_id']]['decision'],reason=judgments[v['blind_id']]['reason_ko']) for v in ordered]))
    save(OUT/'all_anatomy_gate.json',dict(created_utc=utc(),passed=not failures and len(inputs)==60,
         expected=60,verified=len(inputs),failures=failures,review_parts={str(p):sha(p) for p in parts},
         candidates_sha256=sha(OUT/'remaining_candidates.json'),judgment_counts=dict(Counter(j['decision'] for j in judgments.values())),
         series_diff=diff,original_selection_sha256=sha('results/iter_127/data/selection_lock.json'),
         source_sha256=sha(__file__)))
    if failures:print('STOP fixed input conditions failed',failures);return 2
    if set(inputs)!={m['study_uid'] for m in original}:raise ValueError('fixed studies')
    if len({m['patient_uid'] for m in original})!=60:raise ValueError('patient duplicate')
    roles=Counter(m['role'] for m in original)
    if roles!={'tech':8,'calib':12,'explore':40}:raise ValueError('fixed roles')
    body=dict(protocol_sha256=sha(OUT/'protocol.json'),original_selection_sha256=sha('results/iter_127/data/selection_lock.json'),
              anatomy_gate_sha256=sha(OUT/'all_anatomy_gate.json'),inputs=inputs)
    save(OUT/'all_inputs.json',body)
    save(OUT/'remaining_inputs.json',dict(**{k:v for k,v in body.items() if k!='inputs'},
         inputs={s:c for s,c in inputs.items() if s not in tech['inputs']}))
    # 평가 전용 정보는 추론 request와 이미지 message에서 분리한다.
    save(OUT/'evaluation_manifest.json',dict(original_selection_sha256=sha('results/iter_127/data/selection_lock.json'),
         records=[{k:m[k] for k in ['patient_uid','study_uid','batch_id','label','role']} for m in original],
         input_sha256=sha(OUT/'all_inputs.json')))
    print('all inputs locked60; series corrections',sum(d['changed'] for d in diff));return 0


if __name__=='__main__':raise SystemExit(main())
