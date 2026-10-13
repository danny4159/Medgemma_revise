"""같은 atom 규약의 후처리 전후·항목별 회복과 실제 비용을 요약한다."""
from i142_common import *
from i142_eval import score
from collections import Counter
import numpy as np

def main():
    protocol=verify_protocol(RES/'protocol_main.json')
    inputs=[r for r in read(RES/'inference_inputs.json') if r['role']=='main']
    refs={r['patient_id']:r for r in read(OLD/'reference_locked.json')['rows']}
    jj=read(RES/'eval/judgments.json')
    final=read(RES/'eval/per_patient.json')
    before=[]
    records=[]
    for r in inputs:
        rec=verify_result(RES/'jobs/main'/r['patient_id']/'result.json',protocol,r)
        rec['raw_report']=' '.join(se for g in rec['observations']['generation'] for se in g['decoded'])
        before.append(score(rec,refs[r['patient_id']],jj[r['patient_id']]['raw'],'raw_report'))
        records.append(rec)
    by_type={}
    for name,rows in [('raw_all_regions_and_global',before),('final_region_segtool',final)]:
        out={}
        for typ in ('finding','signal','location','morphology','distribution'):
            values=[]
            counts=Counter()
            for r in rows:
                cc=r['types'].get(typ,{})
                if cc:
                    counts.update(cc)
                    values.append(cc.get('matched',0)/sum(cc.values()))
            out[typ]={'patients':len(values),'states':dict(counts),'patient_mean_recall':float(np.mean(values)) if values else None}
        by_type[name]=out
    rawmean=float(np.mean([r['recall'] for r in before]))
    finalmean=float(np.mean([r['recall'] for r in final]))
    launch=read(RES/'jobs/main/completion.json')
    resources=read(Path(launch['launch_path']).parent/'resource_samples.json')
    peaks={i:max(g['used'] for sample in resources for g in sample['gpus'] if g['index']==i) for i in os.environ['CUDA_VISIBLE_DEVICES'].split(',')}
    metrics={'n_volumes':6,'raw_recall':rawmean,'final_recall':finalmean,'final_minus_raw':finalmean-rawmean,
      'by_type':by_type,'main_supervisor_wall_s':launch['wall_s'],
      'end_to_end_case_s':[read(next((RES/'jobs/main'/r['patient_id']).glob('attempt_*/timing.json')))['end_to_end_s'] for r in inputs],
      'actual_region_generations':sum(len(g['tokens']) for r in records for g in r['observations']['generation']),
      'non_eos_generations':sum(not e for r in records for g in r['observations']['generation'] for e in g['eos']),
      'gpu_global_peak_used_MiB':peaks,'model_worker_peak_reserved_MiB':[r['peak_reserved_MiB'] for r in records],
      'cost_comparison':'MedGemma 원 NIfTI부터 전체 최종 답 저장까지의 공통 경계 비용이 없으므로 비용 우위 비율 미판정',
      'raw_comparison_scope':'후처리 전 모든 영역+global 문장의 연결. 최종 시스템은 global에서 일부 문장만 선택하므로 동일 텍스트 집합의 위치 수정만 비교하는 것이 아님'}
    save(RES/'eval/pre_post_rows.json',before)
    save(RES/'eval/details.json',metrics)
    print(metrics)

if __name__=='__main__':
    main()
