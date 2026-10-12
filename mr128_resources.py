"""완료한 실행의 실제 자원·비용 계측을 연구 결과와 별도로 요약한다."""
from collections import Counter
import json
import numpy as np
from mr128_data import OUT,read,save,sha,utc


def main():
    main_dir=OUT/'gen/main'
    if not (main_dir/'completion.json').exists():raise ValueError('main not complete')
    stages={}
    for stage in ['tech','remaining']:
        paths=sorted((OUT/'seg'/stage).glob('*.result.json'))
        stages['SynthSeg_'+stage]=[dict(path=str(p),**read(p)) for p in paths]
    for stage in ['tech_b1','tech_b2','main']:
        stages['MedGemma_'+stage]=[dict(path=str(p),**read(p)) for p in sorted((OUT/'gen'/stage).glob('*.result.json'))]
    samples=[json.loads(line) for p in sorted(main_dir.glob('*.resources.jsonl')) for line in p.read_text().splitlines()]
    events=[read(p) for p in sorted(main_dir.glob('*.worker*.events.json'))]
    groups=[g for e in events for g in e['groups']]
    raw=[json.loads(line) for p in sorted(main_dir.glob('worker*.jsonl')) for line in p.read_text().splitlines()]
    if len(raw)!=80 or len(groups)!=80:raise ValueError('batch1 main resource80')
    cost=read(OUT/'eval/per_patient_costs.json')
    complete_cost=[c for c in cost if c['S_warm_raw_to_score_answer_s'] is not None]
    def describe(values):
        return dict(n=len(values),mean=float(np.mean(values)),p95=float(np.quantile(values,.95)),maximum=float(max(values))) if values else dict(n=0)
    resource=dict(system_cpu_percent_peak=max(r['cpu_percent'] for r in samples),
         system_available_RAM_min_bytes=min(r['ram']['available'] for r in samples),
         observed_worker_RSS_max_bytes=max(g['rss_bytes'] for g in groups),
         worker_cpu_user_system_cumulative=[dict(user_s=e['groups'][-1]['process_cpu_user_s'],system_s=e['groups'][-1]['process_cpu_system_s']) for e in events],
         worker_IO_cumulative_bytes=[dict(read=e['groups'][-1]['process_read_bytes'],write=e['groups'][-1]['process_write_bytes']) for e in events],
         total_system_disk_read_delta_bytes=samples[-1]['disk_io']['read_bytes']-samples[0]['disk_io']['read_bytes'],
         total_system_disk_write_delta_bytes=samples[-1]['disk_io']['write_bytes']-samples[0]['disk_io']['write_bytes'],
         note_ko='공유 시스템 CPU/RAM/disk 수치는 다른 사용자 작업을 포함하며 우리 작업의 인과적 경합량이 아니다. worker RSS는 group 종료 시점 관측치이며 연속 최대값 보장은 없다. 페이지 cache hit는 read_bytes에 반영되지 않을 수 있다.')
    durations=[g['end_after_saved']-g['start'] for g in groups]
    paired_cost=dict(available_complete_S_cost_n=len(complete_cost),
         S_warm=describe([c['S_warm_raw_to_score_answer_s'] for c in complete_cost]),
         S_cold=describe([c['S_cold_to_score_answer_s'] for c in complete_cost]),
         A_independent_component_sum=describe([c['A_independent_warm_component_sum_s'] for c in complete_cost]),
         A_extra_after_shared_S=describe([c['A_extra_after_shared_S_s'] for c in cost]),
         U_warm=describe([c['U_warm_raw_to_answer_s'] for c in cost]),
         note_ko='누락 S 비용을 0으로 채우지 않는다. 비용 표본이 전체40명보다 작으면 available-case 보조 기록이며 전체 대안 충분성의 근거가 아니다. A 독립 값은 실제 구간들의 합이며 단일 uninterrupted service latency가 아니다.')
    save(OUT/'resource_summary.json',dict(created_utc=utc(),stages=stages,main_system=resource,
         main_raw_to_saved_s=describe(durations),paired_service_costs=paired_cost,
         main_EOS=sum(r['eos'] for r in raw),main_max_new_tokens=max(len(r['tokens']) for r in raw),
         states=dict(Counter(r['cond'] for r in raw)),source_sha256=sha(__file__),
         pilot_comparison_sha256=sha(OUT/'pilot_comparison.json'),
         pilot_system_peaks_measured=False,installation_and_anatomy_selection_wall_s=None,
         unmeasured_ko='기술 batch 비교의 CPU/RAM/I/O 세부 peak와 전체 설치·해부학 수동 선정·복구 wall-clock은 측정하지 않았다. 기록 시각 차이를 실제 작업 시간으로 환산하지 않는다.'))
    print('resources summarized; complete S cost',len(complete_cost),'/',len(cost))


if __name__=='__main__':main()
