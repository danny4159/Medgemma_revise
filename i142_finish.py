"""계획한 새 비교와 검증의 원본을 봉인하고 재사용 범위를 분리한다."""
from i142_common import *

def main():
    protocol=verify_protocol(RES/'protocol_main.json')
    rows=[r for r in read(RES/'inference_inputs.json') if r['role']=='main']
    completion=read(RES/'jobs/main/completion.json')
    assert set(completion['patients'])==set(r['patient_id'] for r in rows)
    for r in rows:
        verify_result(RES/'jobs/main'/r['patient_id']/'result.json',protocol,r)
    verification=read(RES/'eval/independent_verification.json')
    assert verification['all_pass']
    for path,h in verification['verified_files'].items():
        assert sha(path)==h
    assert read(RES/'tests/runtime_checks_v2.json')['all_pass']
    assert read(RES/'tests/technical_comparison_v2.json')['all_equal']
    for pid in ['sub-strokecase0001','sub-strokecase0003']:
        assert read(RES/'tests/hook_control'/pid/'check.json')['all_pass']
    safe=read(RES/'tests/safe_loader_clean/check.json')
    assert safe['all_pass']
    assert not list((MODELS/'autorg').rglob('training_log_2026_10_14_*.txt'))
    report=read(RES/'eval/report.json')
    incident=read(RES/'incident_sdk_logs/incident_korean.json')
    for r in incident['moved']:
        assert not Path(r['source']).exists() and sha(r['preserved'])==r['sha256']
    paths=[p for p in RES.rglob('*') if p.is_file() and not p.is_symlink() and 'cache' not in p.parts and '__pycache__' not in p.parts]
    sources=[p for p in ROOT.glob('i142_*.py')]+[ROOT/'test_i142.py',ROOT/'ar70_run.py',ROOT/'ar70_patch.py']
    outcome={'created_at':now(),'decision':report['decision'],'valid_comparison_completed':True,
       'main_patients':6,'main_reports':6,'main_internal_generations':read(RES/'eval/details.json')['actual_region_generations'],
       'training_executed':False,'independent_patient_confirmation':False,
       'method_contribution_confirmed':False,'goal_completed':False,
       'science_blocking_issues':[],
       'reuse_issues':['보존된 i142_worker.py/i142_launch.py 기본 진입점은 기존 checkpoint 폴더를 사용하는 당시 실행 기록이다. 다음 재사용은 새 i142_worker_safe.py 진입점을 선택하고 그 소스와 model_view 경로를 새 protocol에 잠가야 한다. 안전 로더의 실제 한 명 예측/생성과 safe worker의 완료 재진입은 검증했다. 기존 본출력의 입력·점수는 warning 로그에 의존하지 않는다.',
                       '새 의미 판정표는 6명 고정 출력 전용이며 범용 평가기로 사용하지 않는다.'],
       'corrected_incidents':['초기 비결정적 kernel tensor 불일치는 seed42·cuDNN deterministic/benchmark 설정으로 수정하고 기술 exact 대조를 통과했다.',
                              '이번에 생성된 SDK 경고 로그를 원본 보존 이동했다. 새 model_view와 safe_loader의 실제 기술 한 명 예측·생성은 token·mask·보고서 및 원 경로 불변 검사를 통과했다.',
                              '첫 safe_loader 보존 snapshot 검사는 같은 시간에 새 로그를 이동하여 실패했다. 이동 완료 뒤 직렬 검사로 해소했다.'],
       'self_check':'FAIL','self_check_reason':'본 비교·평가·안전 경로 검증은 완료했으나 원 실행에서 기존 모델 폴더에 새 로그를 쓰는 분리 조건 위반이 발생했다. 로그 보존 이동과 안전 진입점 보완은 완료했으며 원 실행의 일탈을 숨기지 않고 GPT 리뷰를 요청한다.',
       'next_question':'전체 DWI target을 한 번 부여하는 입력별 SFT의 학습 가능한 통합 지점을 정한다. 같은 frozen 6명·checkpoint 순회는 추가하지 않는다.'}
    save(RES/'implementation_outcome.json',outcome)
    paths.append(RES/'implementation_outcome.json')
    bundle={'created_at':now(),'files':{str(p):sha(p) for p in paths},'sources':{str(p):sha(p) for p in sources},
       'external_assets':read(RES/'asset_manifest.json')['weights'],
       'excluded_symlinks':{str(p):str(p.resolve()) for p in RES.rglob('*') if p.is_symlink()},
       'model_data_backed_up_here':False,'code_commit_owner':'orchestrator'}
    save(RES/'completion.json',bundle)
    assert all(sha(p)==h for p,h in bundle['files'].items())
    print({'decision':outcome['decision'],'main_patients':6,'files_sealed':len(bundle['files']),'sources':len(sources),'self_check':outcome['self_check']})

if __name__=='__main__':
    main()
