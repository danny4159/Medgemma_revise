"""실행 종료 후 원 기록 불변성과 결과·소스 연결을 확인해 보존한다."""
import ast
from collections import Counter
from pathlib import Path
import subprocess
import psutil
from mr128_data import OUT,read,save,sha,verify_files,utc


def main():
    completed=read(OUT/'pipeline_complete.json');verify_files(completed['artifacts'])
    verification=read(OUT/'eval/independent_verify.json')
    if not completed['checks_passed'] or not verification['all_pass']:raise ValueError('final numerical verification incomplete')
    protocol=read(OUT/'protocol.json')
    for key in ['inputs','preserved_results','source_before']:verify_files(protocol[key])
    baseline=read('../agent/runs/iter_128/code_baseline.json')
    changed=[p for p,v in baseline['files'].items() if not Path(p).is_file() or sha(p)!=v['hash']]
    if changed:raise ValueError('existing code changed: '+str(changed))
    current_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if current_sha!=baseline['sha']:raise ValueError('unexpected Git history mutation')
    locks=['evaluation_lock_v2.json','main_analysis_lock.json']
    for p in locks:
        lock=read(OUT/p);verify_files(lock['code'])
        if 'inputs' in lock:verify_files(lock['inputs'])
    inputs=read(OUT/'all_inputs.json')
    input_files={v['path']:v['sha256'] for r in inputs['inputs'].values() for v in r['files'].values()}
    verify_files(input_files)
    builds=[read(p) for stage in ['tech','remaining'] for p in (OUT/'build'/stage).glob('*.json')]
    pngs={v['path']:v['sha256'] for b in builds for v in b['pngs'].values()};verify_files(pngs)
    for b in builds:
        if b.get('seg_completion'):verify_files(b['seg_completion']['result']['artifacts'])
    sources={str(p):sha(p) for p in sorted(Path('.').glob('*mr128*.py'))}
    for p in sources:ast.parse(Path(p).read_text())
    main_config=read(OUT/'gen/main/config.json')
    owned_pids=[]
    for p in (OUT/'gen/main').glob('*.launch.json'):
        launch=read(p);owned_pids.extend(launch['pids']+[launch['supervisor_pid']])
    if any(psutil.pid_exists(pid) and psutil.Process(pid).status()!=psutil.STATUS_ZOMBIE for pid in owned_pids):raise ValueError('owned generation process still active')
    failures=[dict(study_uid=p.name.split('.')[0],**read(p)) for p in sorted((OUT/'seg/remaining').glob('*.failure.json'))]
    manifest=read(OUT/'evaluation_manifest.json')['records']
    report=read(OUT/'eval/report.json')
    limitations=[]
    if failures:limitations.append('남은52명 공식 SynthSeg 중 개별 cuDNN scratch allocation 실패. 사전 U fallback과 S 누락을 적용했으며 전문 대안 충분성은 미판정.')
    pilot=read(OUT/'pilot_comparison.json')
    pilot_unmeasured='별도 수집하지 않았다' in pilot['b1']['CPU_RAM_IO_note_ko']
    if pilot_unmeasured:limitations.append('기술 batch 비교의 시스템 CPU/RAM/I/O 세부 peak 미계측. 본80건의 telemetry로 소급 대체하지 않음.')
    limitations.append('현재40명은 공식 train 개발 자료의 보고서 일치도이며 독립 영상 진단 정답·외부 환자·새 모델·학습 방법은 미검증.')
    artifacts={str(p):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and not p.name.endswith('.lock') and not p.name.startswith('.')}
    self_check='FAIL' if failures or pilot_unmeasured else 'PASS'
    save(OUT/'completion.json',dict(created_utc=utc(),status='completed_with_documented_failures' if failures else 'completed',
         plan_scope_completed=True,valid_U_A_report_agreement_comparison=True,independent_verification_passed=True,
         self_check=self_check,limitations=limitations,
         reached_stage='possibility_exploration_40',roles=dict(Counter(r['role'] for r in manifest)),
         patients=len(manifest),fixed_selection_preserved=True,series_changes=read(OUT/'all_anatomy_gate.json').get('series_diff'),
         main_requests=80,pilot_requests=32,training_updates=0,official_segmentation_attempts=len(builds),
         official_segmentation_failure_n=len(failures),failures=failures,
         results=report['decision'],artifacts=artifacts,sources=sources,
         external_input_files=input_files,external_png_files=pngs,
         preserved_previous_results=protocol['preserved_results'],code_baseline_sha=baseline['sha'],existing_source_files_unchanged=len(baseline['files']),
         source_sha256=sha(__file__),git_commit_push_performed=False,owned_generation_pids_exited=owned_pids))
    print('archived',len(artifacts),'artifacts;',len(sources),'sources; SELF_CHECK',self_check)


if __name__=='__main__':main()
