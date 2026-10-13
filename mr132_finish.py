"""실제 종료·검증·비용 기록 연결; 연구 판정은 독립 GPT 리뷰에 맡긴다."""
import json,time,os
from pathlib import Path
import numpy as np
from mr132_common import RES,read,save,sha,now
from mr132_run import verify_protocol,verify_job,load_records

def main():
    proto=verify_protocol(); control=read(RES/'control/completion.json'); assert control['all_commands_pass']
    reports=read(RES/'eval/development_report.json'); v=read(RES/'eval/development_independent_verify.json'); assert v['all_pass'] and v['report_sha256']==sha(RES/'eval/development_report.json')
    assert read(RES/'input_integrity_audit.json')['all_pass'] and read(RES/'baseline/independent_audit.json')['all_pass']
    assert read(RES/'resource_profile/summary.json')['all_pass']
    stages=['pilot_b1','pilot_b2','resume','technical','development','io_profile']+(['holdout'] if control['holdout_executed'] else [])
    ledger={}; all_records=[]; resource={}
    for stage in stages:
        req='pilot' if stage in ['pilot_b1','pilot_b2','resume'] else stage
        rr=verify_job(RES/'gen'/stage,RES/'requests'/f'{req}.json'); all_records.extend(rr)
        expected=dict(pilot_b1=12,pilot_b2=12,resume=12,technical=54,development=360,holdout=180,io_profile=6)[stage];assert len(rr)==expected
        job=RES/'gen'/stage; attempts=[read(p) for p in job.glob('result_*.json')]
        samples=[json.loads(line) for p in job.glob('resources_*.jsonl') for line in p.read_text().splitlines()]
        gpu={g:dict(sampled_peak_used_mib=max(int(r['used']) for x in samples for r in x['gpu'] if r['index']==g),sampled_min_free_mib=min(int(r['free']) for x in samples for r in x['gpu'] if r['index']==g)) for g in ['0','1']}
        assert all(z['sampled_min_free_mib']>=2048 for z in gpu.values()),'실측 안전 여유 부족'
        ledger[stage]=dict(n_requests=len(rr),n_unique=len({r['id'] for r in rr}),n_eos=sum(r['eos'] for r in rr),n_non_eos=sum(not r['eos'] for r in rr),n_tokens=sum(r['n_tokens'] for r in rr),max_tokens=max(r['n_tokens'] for r in rr),supervisor_wall_s=sum(a['wall_s'] for a in attempts),request_wall_sum_s=sum(r['wall_s'] for r in rr),peak_allocated_mib=max(r['peak_allocated_mib'] for r in rr),peak_reserved_mib=max(r['peak_reserved_mib'] for r in rr),gpu=gpu,by_kind={k:dict(n=sum(r['kind']==k for r in rr),mean_latency_s=float(np.mean([r['batch_wall_s'] for r in rr if r['kind']==k])),p95_latency_s=float(np.quantile([r['batch_wall_s'] for r in rr if r['kind']==k],.95)),amortized_mean_request_cost_s=float(np.mean([r['wall_s'] for r in rr if r['kind']==k]))) for k in ['single','pair']},completion_sha256=sha(job/'completion.json'))
    chosen=read(RES/'execution_choice.json')
    issues=dict(blocking_issues=[],reuse_issues=['고정 iter_132 입력·경로 전용이다. 새 자료에 대한 임상 정답·관측 충분성과 범용 재개를 승인하지 않는다.','직접 worker/launch CLI의 개발 단계 진입 gate는 감독기 mr132_control.py에 의존한다. 새 진입점 재사용 전 동일 gate 연결이 필요하다.','조건부 holdout 경로는 미실행이면 재사용 검증 범위 밖이다.','batch2는 원시 token 7/12 불일치로 출력 정합성 기준을 미충족했다. 새 batch 설정은 재측정해야 한다.'],deferred_issues=['8장 부분 관측에서 전체 volume 등급을 평가했으며 임상 재촬영·다른 sequence·다른 모델·직접 적응은 미검증이다.','IQM 생성 전체 서비스 비용을 측정하지 않았다. 기록한 요청·supervisor 시간은 IQM 생성 대비 비용 우월성의 근거가 아니다.'])
    used_volumes=[x for stage in ['technical','development']+(['holdout'] if control['holdout_executed'] else []) for x in read(RES/'data'/f'{stage}_manifest.json')['volumes']]
    save(RES/'execution_ledger.json',dict(created_at=now(),stages=ledger,total_model_requests=sum(x['n_requests'] for x in ledger.values()),scientific_requests=54+360+(180 if control['holdout_executed'] else 0),technical_comparison_resume_requests=42,holdout_executed=control['holdout_executed'],two_gpu_mapping=read(RES/'gpu_mapping_check.json'),download_bytes=sum(v['source']['bytes'] for v in used_volumes),png_bytes=sum(Path(p['path']).stat().st_size for v in used_volumes for p in v['pngs']),n_volumes=len(used_volumes),n_pngs=sum(len(v['pngs']) for v in used_volumes),estimated_vs_actual_development_wall_s=dict(estimate=chosen['estimated_development_wall_s'],actual=read(RES/'control/development_generation.json')['wall_s']),cost_note='supervisor 시간은 모델 로딩 포함, protocol·모델 SHA 검사는 밖이다. control의 각 명령 wall은 해당 검사를 포함한다. 요청 latency는 PNG 읽기·processor·생성 포함, 원 NIfTI 반입·렌더링·답 저장 시간 제외. pilot 비교표의 batch2 p95_s는 배치 시간을2요청으로 나눈 amortized 비용이다. 본 ledger p95_latency_s는 배치 전체 시간으로 계산한 실제 지연이다. CPU/RAM/I/O 압력의 보완6요청은 본생성 후 사후 계측이며 구성 선택에는 미사용. IQM 생성 비용 미측정. 개별/직접 공동 비교는 시각 token 노출이4배 다르다.',issues=issues))
    save(RES/'engineer_findings.json',dict(created_at=now(),valid_model_comparison=True,protocol_sha256=proto,development_report_sha256=sha(RES/'eval/development_report.json'),development_verification_sha256=sha(RES/'eval/development_independent_verify.json'),reused_assets=dict(mr123_data=dict(source_commit='4682b4bacadbaf12cf0f379f41a5a4fb1b9cb983',blob='c9e673cbb6e495adcfe2d1d264097c2a3d72ee45',used_functions=['normalization_window','render_slice'],checks=[str(RES/'tests/cpu.json'),str(RES/'tests/tensors.json'),str(RES/'input_integrity_audit.json')])),method_developed=False,vlm_training=False,holdout_executed=control['holdout_executed'],problems=issues,scientific_scope='실제 움직임 촬영 MR-ART T1w의 고정 frozen MedGemma·8 axial slice 조건. 질병 진단·해부학 보존·일반 MRI 인식 또는 내부 원인 미판정.'))
    files=[p for p in RES.rglob('*') if p.is_file() and p.name!='completion.json' and 'gen/' not in str(p.relative_to(RES)) and p.suffix not in ['.png','.html']]
    files += [RES/'gen'/stage/'completion.json' for stage in stages]
    save(RES/'completion.json',dict(completed_at=now(),all_current_scope_checks_pass=True,files={str(p):sha(p) for p in files},code={str(p.resolve()):sha(p) for p in Path('.').glob('mr132_*.py')},renderer_sha256=sha('mr123_data.py'),n_requests=sum(x['n_requests'] for x in ledger.values()),holdout_executed=control['holdout_executed'],source_preservation='Git checkpoint는 orchestrator 담당; 구현자는 commit·branch 작업 미실행'))
    print('최종 연결 봉인:',sum(x['n_requests'] for x in ledger.values()),'모델 요청; holdout',control['holdout_executed'])
if __name__=='__main__':main()
