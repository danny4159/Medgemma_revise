"""실측 검사가 모두 존재할 때만 본학습을 여는 사전 봉인."""
from pathlib import Path
from i141_common import read,sha,now
from i143_runtime import save
from i143_data import OUT


def main():
    required=['tech_a2_checks.json','training_checks_a3.json','additional_graph_checks.json',
              'assessment_fixtures.json','cpu_final/checks.json','nocache_source_continuity.json']
    for name in required: assert read(OUT/'tests'/name)['passed'] is True,name
    cache=read(OUT/'tests/cache_checks_a1_cache.json'); assert cache['cache_enabled'] is False
    first=[p for p in (OUT/'tests').glob('cap_*_512.json')]
    assert first
    cap=1024 if any(not read(p)['eos'] for p in first) else 512
    caps=[]
    for cond in ['S','A','N']:
        resume=OUT/'tests'/f'cap_{cond}_resume_checks.json'
        check=read(resume)
        assert check['passed'] and len(check['checks'])==3
        assert all(r['equal'] and r['full']==r['resumed'] for r in check['checks'])
        assert check['source_sha256']==sha('i143_nocache.py')
        caps.append(resume)
        p=OUT/'tests'/f'cap_{cond}_{cap}.json'; r=read(p)
        assert r['condition']==cond and r['cap']==cap and r['cache_enabled'] is False
        assert len(r['tokens'])==r['n_tokens'] and 0<r['n_tokens']<=cap
        caps.append(p)
    data=read(OUT/'data_manifest.json'); refs=read(OUT/'reference_locked.json')
    assert data['mask_geometry_passed']==48 and data['prior_patient_overlap']==0 and data['source_duplicates']==0
    assert len({r['patient_id'] for r in data['rows']})==48
    assert {s:sum(r['split']==s for r in data['rows']) for s in ['T','V','E']}==dict(T=24,V=8,E=16)
    assert {r['patient_id'] for r in data['rows']}=={r['patient_id'] for r in refs['rows']}
    inputs=[]
    for r in data['rows']:
        for kind in ['source','mask']:
            assert sha(r[kind+'_path'])==r[kind+'_sha256']; inputs.append(Path(r[kind+'_path']))
        for im in r['images']:
            assert sha(im['path'])==im['sha256']; inputs.append(Path(im['path']))
    paths=list(Path('.').glob('i143_*.py'))+[Path(n) for n in ['i141_common.py','i141_spec.py','i141_preflight.py','i141_select_download.py']]
    paths+=[OUT/n for n in ['data_manifest.json','reference_locked.json','eval_contract.json','selection_candidates.json']]
    paths+=[OUT/'tests'/n for n in required]+caps+[OUT/'tests/cache_checks_a1_cache.json',OUT/'tests/throughput_choice_pre_generation.json']
    train_check=read(OUT/'tests/training_checks_a3.json')
    assert train_check['source_sha256']==sha('i143_training_checks.py')
    assert train_check['model_source_sha256']==sha('i143_model.py')
    assert read(OUT/'tests/nocache_source_continuity.json')['new_sha256']==sha('i143_model.py')
    assert all(r['optimizer_restore_exact'] and r['passed'] for r in train_check['rows'])
    assert {r['condition'] for r in train_check['rows']}=={'S','A','N'}
    resource_path=OUT/'tests/training_a3_resource_summary.json'
    resource=read(resource_path)
    assert resource['minimum_device_free_mib']>=2048
    paths.append(resource_path)
    files={str(p.resolve()):sha(p) for p in paths+inputs}
    save(OUT/'training_gate.json',dict(created_at=now(),passed=True,files=files,cap=cap,cache_enabled=False,
         training_reserved_mib=resource['peak_device_used_mib'],precision='bf16',microbatch=1,workers_per_gpu=1,
         memory_field_note='training_reserved_mib는 admission용 보수적 GPU 전체 used peak이며 torch reserved와 구분한다.',
         cache_note='cache 수치 gate 실패를 보존하고 계획의 no-cache fallback 사용',
         resume_note='a3의 optimizer/RNG 복원 및 독립 uninterrupted/resumed 반복 대조를 사용한다. bitwise adapter resume 주장이 아님.',
         technical_nll_field_note='a3의 first_patient_nll_after_two_updates는 두 update 후 첫 환자의 NLL이다.'))
    print('본학습 사전 gate 고정',cap,len(files))


if __name__=='__main__': main()
