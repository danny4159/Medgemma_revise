"""완료된 paired 출력의 독립 산술·위치/속성 분해·측정 비용과 보존 manifest를 기록한다."""
from collections import Counter, defaultdict
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from i141_common import HERE,RES,read,save,sha,now
import i141_run as run


def main():
    records=run.verify_job(RES/'jobs/main','main')
    report=read(RES/'eval/report.json')
    refs={r['patient_id']:r for r in read(RES/'reference_locked.json')['rows']}
    mapping=read(RES/'eval/condition_mapping.json')
    judgments=read(RES/'eval/judgments.json')
    patient_values={}
    breakdown={c:defaultdict(Counter) for c in ['S','A']}
    for qid,j in judgments.items():
        pid,c=mapping[qid]['patient_id'],mapping[qid]['condition']
        atoms=refs[pid]['positive_atoms']
        count=sum(j['atoms'][a['id']]['state']=='matched' for a in atoms)
        patient_values[(pid,c)]=count/len(atoms)
        for a in atoms:
            breakdown[c][a['type']][j['atoms'][a['id']]['state']]+=1
    delta=np.mean([patient_values[(p,'A')]-patient_values[(p,'S')] for p in sorted(refs) if (p,'S') in patient_values])
    checks={'independent_mean_delta':abs(float(delta)-report['delta_recall_A_minus_S'])<1e-12,
            'main_request_count':len(records)==len(read(RES/'requests/main.json')),
            'all_6_patients':len(set(r['patient_id'] for r in records))==6,
            'source_baseline_unchanged':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()=='9157bb31ca641fe720bd2d5203780df82635d53d'}
    original=read(RES/'derivation_manifest.json')
    for p,h in original['sources'].items():
        checks['source_unchanged_'+p]=sha(HERE/p)==h
    row=read(RES/'protocol_lock_main.json')
    for p,h in {**row['inputs'],**row['code'],**row['gates']}.items():
        checks['locked_'+p]=sha(p)==h
    assert all(checks.values())
    save(RES/'eval/independent_verify.json',{'created_at':now(),'all_pass':True,'checks':checks,
         'delta':float(delta),'scope':'판정표에서 독립 산술·현재 입력/소스 hash 검증. 독립 임상 의미 검증이 아님.'})
    save(RES/'eval/attribute_breakdown.json',{c:{t:dict(v) for t,v in types.items()} for c,types in breakdown.items()})
    cost={}
    for c in ['S','A']:
        rr=[r for r in records if r['condition']==c]
        cost[c]={'requests':len(rr),'tokens':sum(r['n_tokens'] for r in rr),'eos':sum(r['eos'] for r in rr),
                 'truncated':sum(not r['eos'] for r in rr),'invalid_boundary':sum(r['boundary_status']=='invalid_boundary' for r in rr),
                 'request_processing_seconds_sum':sum(r['wall_s'] for r in rr),
                 'request_latency_p50_s':float(np.median([r['wall_s'] for r in rr])),
                 'request_latency_p95_s':float(np.quantile([r['wall_s'] for r in rr],.95)),
                 'peak_worker_reserved_mib':max(r['peak_reserved_mib'] for r in rr)}
    completion=read(RES/'jobs/main/completion.json')
    attempt=completion['attempt']
    result=read(RES/'jobs/main'/('result_'+attempt+'.json'))
    resources=[]
    for path in (RES/'jobs/main').glob('resources_*.jsonl'):
        resources += [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    peaks={g:max(int(r['used']) for event in resources for r in event['gpu'] if r['index']==g) for g in run.allowed()}
    minfree={g:min(int(r['free']) for event in resources for r in event['gpu'] if r['index']==g) for g in run.allowed()}
    per_worker=[read(p) for p in (RES/'jobs/main').glob('worker*_exit.json')]
    save(RES/'eval/cost.json',{'created_at':now(),'conditions':cost,
         'main_supervisor_wall_s':result['wall_s'],'includes_model_loading':True,
         'worker_loading_seconds_sum':sum(x['load_s'] for x in per_worker),
         'gpu_peak_total_used_mib':peaks,'gpu_min_free_mib':minfree,'cpu_load_max':max(e['cpu_load'][0] for e in resources),
         'workers':len(result['returncodes']),'returncodes':result['returncodes'],
         'resource_samples':len(resources),'scope':'이미 준비한 PNG 읽기→tensor→생성→raw 저장 및 supervisor loading. 겹치는 요청 시간 합은 GPU device-seconds가 아님.',
         'unmeasured':'원 NIfTI 반입/전체 전처리와 내용 평가를 포함한 end-to-end latency는 직접 계측하지 않았다.',
         'request_save_timings':{str(p):sha(p) for p in (RES/'jobs/main').glob('timing*.jsonl')}})
    save(RES/'environment.json',{'created_at':now(),'python':sys.executable,'CUDA_VISIBLE_DEVICES':__import__('os').environ.get('CUDA_VISIBLE_DEVICES'),
         'packages':{p:importlib.metadata.version(p) for p in ['torch','transformers','nibabel','numpy','Pillow','requests']},
         'model_revision':'91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b','environment_changed':False})
    files={str(p):sha(p) for p in RES.rglob('*') if p.is_file() and p.name not in ['supervisor.lock','records.lock']}
    save(RES/'completion.json',{'created_at':now(),'status':'paired_generation_and_text_evaluation_completed',
         'valid_experiment':True,'decision':report['decision'],'new_model_requests_main':len(records),
         'new_training_updates':0,'new_3d_outputs':0,'files':files,
         'checks':'actual model outputs/protocol/runtime/token equality/independent arithmetic; clinical truth outside public text unresolved',
         'code':{str(p):sha(p) for p in HERE.glob('i141_*.py')}})
    print({'completion_files':len(files),'main_requests':len(records),'delta':float(delta),'decision':report['decision']})


if __name__=='__main__':
    main()
