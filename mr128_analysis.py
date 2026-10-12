"""calibration12 잠금과 탐색40의 원 계획 지표·비용·종료 판정."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
from mr128_data import OUT,read,save,sha,verify_files,utc
from mr128_eval import calibrate,metrics,paired_ci,auroc,decision,states
from mr128_gen import verify


def calibrate_stage():
    manifest=read(OUT/'evaluation_manifest.json')['records'];rows=[];builds={};missing=[]
    for m in manifest:
        if m['role']!='calib':continue
        p=OUT/'build/remaining'/(m['study_uid']+'.json');b=read(p);builds[str(p)]=sha(p)
        if b['S'] is None:missing.append(m['study_uid'])
        else:rows.append(dict(**m,S=b['S']))
    if len(rows)+len(missing)!=12:raise ValueError('calibration12 set')
    result=calibrate(rows) if not missing else None
    # 누락 calibration을 이용한 새로운 보조 threshold를 임의로 적합하지 않는다.
    candidate=dict(result=result,missing=missing,complete=not missing,
         manifest_sha256=sha(OUT/'evaluation_manifest.json'),builds=builds,
         evaluation_lock_sha256=sha(OUT/'evaluation_lock_v2.json'),source_sha256=sha(__file__),
         before_main_VLM_generation=True,VLM_calibration_requests=0)
    if (OUT/'calibration_lock.json').exists():
        previous=read(OUT/'calibration_lock.json')
        if {k:previous[k] for k in candidate}!=candidate:raise ValueError('calibration reuse differs')
    else:save(OUT/'calibration_lock.json',dict(created_utc=utc(),**candidate))
    print('calibration complete',not missing,'threshold',None if result is None else result['chosen']['threshold'])


def analyze():
    cal=read(OUT/'calibration_lock.json');verify_files(cal['builds'])
    verify_files(read(OUT/'evaluation_lock_v2.json')['code'])
    comp=read(OUT/'gen/main/completion.json');verify_files(comp['artifacts'])
    requests,outputs=verify(OUT/'gen/main');lookup={r['id']:r for r in outputs}
    if len(outputs)!=len(requests) or len(requests)!=80:raise ValueError('main expected80')
    if len(outputs)!=80 or len({r['id'] for r in outputs})!=80:raise ValueError('main incomplete')
    bykey={(r['study_uid'],r['cond']):lookup[r['id']] for r in requests}
    manifest=[m for m in read(OUT/'evaluation_manifest.json')['records'] if m['role']=='explore'];rows=[];builds={}
    threshold=cal['result']['chosen']['threshold'] if cal['complete'] else None
    for m in manifest:
        study=m['study_uid'];p=OUT/'build/remaining'/(study+'.json');b=read(p);builds[str(p)]=sha(p)
        U,uc=states(bykey[(study,'U')]['text'],bykey[(study,'U')]['eos'])
        A,ac=states(bykey[(study,'A')]['text'],bykey[(study,'A')]['eos'])
        S=b['S'];sp='PRESENT' if S is not None and threshold is not None and S>=threshold else 'ABSENT' if S is not None and threshold is not None else None
        rows.append(dict(**m,U=U,A=A,U_parse_code=uc,A_parse_code=ac,S=S,S_state=sp,
             A_fallback=b['A_fallback'],A_idx=b['A_idx'],U_idx=b['U_idx'],
             U_request=bykey[(study,'U')]['id'],A_request=bykey[(study,'A')]['id']))
    if len(rows)!=40 or len({r['patient_uid'] for r in rows})!=40:raise ValueError('explore40')
    y=[int(r['label']=='positive') for r in rows]
    U=metrics(y,[r['U'] for r in rows]);A=metrics(y,[r['A'] for r in rows]);delta=paired_ci(rows,'A','U')
    avail=[r for r in rows if r['S'] is not None];S_complete=len(avail)==40 and cal['complete']
    S=metrics(y,[r['S_state'] for r in rows]) if S_complete else None
    Savailable=metrics([int(r['label']=='positive') for r in avail],[r['S_state'] for r in avail]) if threshold is not None and avail else None
    roc=auroc([int(r['label']=='positive') for r in avail],[r['S'] for r in avail]) if avail else None
    Sdiff={k:paired_ci(rows,'S_state',k) for k in ['U','A']} if S_complete else None
    available_diff={k:paired_ci(avail,'S_state',k) for k in ['U','A']} if threshold is not None and avail and len({r['label'] for r in avail})==2 else None
    # 실행한 warm 구간은 원 NIfTI 읽기→마지막 답 저장을 포함한다.
    events=[read(p) for p in (OUT/'gen/main').glob('*.worker*.events.json')]
    groups=[g for e in events for g in e['groups']];group_lookup={i:g for g in groups for i in g['ids']}
    if set(group_lookup)!={r['id'] for r in requests}:raise ValueError('cost sidecar missing/extra requests')
    costs=[]
    for r in rows:
        study=r['study_uid'];b=read(OUT/'build/remaining'/(study+'.json'))
        tpath=OUT/'seg/remaining'/(study+'.timing.json');timing=read(tpath) if tpath.exists() else None
        warmS=timing['warm_raw_read_to_S_answer_saved_s'] if timing else None
        coldS=timing['cold_subprocess_to_S_answer_saved_s'] if timing else None
        ug=group_lookup[r['U_request']];ag=group_lookup[r['A_request']]
        u=ug['end_after_saved']-ug['start'];a=ag['end_after_saved']-ag['start']
        warmA=warmS+b['warm_read_to_saved_s']+a if warmS is not None else None
        costs.append(dict(study_uid=study,U_warm_raw_to_answer_s=u,A_VLM_warm_raw_to_answer_s=a,
             S_warm_raw_to_score_answer_s=warmS,S_cold_to_score_answer_s=coldS,
             A_mask_restore_render_s=b['warm_read_to_saved_s'],A_independent_warm_component_sum_s=warmA,
             A_extra_after_shared_S_s=b['warm_read_to_saved_s']+a,
             shared_S_once_s=warmS,A_fallback=r['A_fallback']))
    measured=[c for c in costs if c['S_warm_raw_to_score_answer_s'] is not None]
    cost_complete=len(measured)==40
    S_cost=float(np.mean([c['S_warm_raw_to_score_answer_s'] for c in measured])) if cost_complete else None
    A_cost=float(np.mean([c['A_independent_warm_component_sum_s'] for c in measured])) if cost_complete else None
    investment=decision(U,A,S,delta,S_complete,A_cost,S_cost)
    report=dict(created_utc=utc(),n=40,positive_n=sum(y),negative_n=40-sum(y),U=U,A=A,
         A_minus_U=delta,S_complete=S_complete,S=S,S_available_n=len(avail),S_available_metrics=Savailable,
         S_AUROC_available=roc,S_minus= Sdiff,calibration=cal,decision=investment,
         S_available_minus=available_diff,S_available_comparison_scope='available-case supplementary; not primary40 or alternative sufficiency',
         fallback_n=sum(r['A_fallback'] is not None for r in rows),selector_success_n=sum(r['A_fallback'] is None for r in rows),
         transitions=dict(Counter(r['U']+' -> '+r['A'] for r in rows)),
         format_counts={k:dict(Counter(r[k+'_parse_code'] for r in rows)) for k in ['U','A']},
         costs=dict(complete=cost_complete,S_warm_mean_s=S_cost,A_independent_warm_component_sum_mean_s=A_cost,
              U_warm_mean_s=float(np.mean([c['U_warm_raw_to_answer_s'] for c in costs])),
              A_extra_after_shared_S_mean_s=float(np.mean([c['A_extra_after_shared_S_s'] for c in costs])),
              note_ko='A 독립 비용은 실제 측정한 S warm+mask 복원/render+VLM 구간의 합이다. 연속 단일 프로세스 latency나 steady-state로 측정한 값은 아니다. 검증·중복 원영상 읽기 비용을 포함한다. S/A를 함께 서비스하면 S 전처리는 한 번 공유한다.',
              model_load_s=[e['load_s'] for e in events]),
         provenance=dict(main_completion_sha256=sha(OUT/'gen/main/completion.json'),
              calibration_sha256=sha(OUT/'calibration_lock.json'),evaluation_lock_sha256=sha(OUT/'evaluation_lock_v2.json'),
              main_requests_sha256=sha(OUT/'explore_requests.json'),builds=builds,
              all_inputs_sha256=sha(OUT/'all_inputs.json'),source_sha256=sha(__file__)),
         scope_ko='공식 train 개발40명의 보고서 일치도. 임상 진단 정확도, 외부 일반화, 내부 원인이나 신규 기여를 증명하지 않는다.')
    save(OUT/'eval/per_patient.json',rows);save(OUT/'eval/per_patient_costs.json',costs);save(OUT/'eval/report.json',report)
    print('report',U['BA'],A['BA'],None if S is None else S['BA'],investment['investment'])


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['calibrate','analyze']);a=ap.parse_args()
    calibrate_stage() if a.action=='calibrate' else analyze()
