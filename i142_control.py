"""기술 경계에서만 본실험 길이·병렬 배치를 결정하고 실행 잠금을 만든다."""
from i142_common import *

def main():
    protocol=verify_protocol(RES/'protocol_technical_4w_v2.json')
    comp=read(RES/'tests/technical_comparison_v2.json')
    throughput=read(RES/'tests/throughput_v2.json')
    assert comp['all_equal'] and all(c['complete'] and not c['cap_hit'] for c in comp['checks'])
    inputs=read(RES/'inference_inputs.json')
    tech=[r for r in inputs if r['role']=='technical']
    for r in tech:
        direct=read(RES/'jobs/tech_equivalence_v2'/r['patient_id']/'result.json')
        eq=read(direct['equivalence_path'])
        assert eq['all_pass'] and direct['complete'] and not direct['cap_hit']
    resources=read(RES/'jobs/tech_4w_v2/resources.json')
    baseline=throughput['baseline_2worker']['patients_per_min']
    candidate=throughput['candidate_4worker']['patients_per_min']
    safe=all(g['free']>=4096 for row in resources for g in row['gpus'])
    per_gpu=2 if safe and candidate>baseline else 1
    choice={'created_at':now(),'technical_pass':True,'max_length':300,'per_gpu':per_gpu,
            'workers':per_gpu*2,'measured_peak_reserved_MiB':max(c['peak_reserved_MiB'] for c in comp['checks']),
            'admission_peak_MiB':7000,'worker_margin_MiB':2048,
            'baseline_patients_per_min':baseline,'candidate_patients_per_min':candidate,
            'four_worker_gpu_margin_ok':safe,'cpu_ram_io':str(RES/'tests/pilot_cpu_ram_io_v2.json'),
            'reason':'결정적 실행의 동일 tensor·feature·token·최종 보고서와 메모리 여유를 검증하고 전체 처리량으로 선택',
            'expected_main_wall_s':6/(candidate if per_gpu==2 else baseline)*60,
            'estimate_scope':'기술 volume 평균의 단순 예상. 실제 영역 수·전처리 크기·warm 상태가 달라질 수 있음',
            'checks':{str(p):sha(p) for p in [RES/'tests/technical_comparison_v2.json',RES/'tests/throughput_v2.json',RES/'tests/runtime_checks_v2.json']}}
    assert read(RES/'tests/runtime_checks_v2.json')['all_pass']
    save(RES/'execution_choice.json',choice)
    main={k:v for k,v in protocol.items() if k not in ('digest','created_at')}
    main['created_at']=now()
    main['main_max_length']=300
    main['files'][str(RES/'execution_choice.json')]=sha(RES/'execution_choice.json')
    main['files'][str(ROOT/'i142_control.py')]=sha(__file__)
    main['files'][str(ROOT/'i142_details.py')]=sha(ROOT/'i142_details.py')
    main['files'][str(RES/'evaluation_contract.json')]=sha(RES/'evaluation_contract.json')
    main['digest']=digest(main)
    save(RES/'protocol_main.json',main)
    print(choice)

if __name__=='__main__':
    main()
