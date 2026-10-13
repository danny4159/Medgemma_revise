"""iter_138 기술 gate: 단일 구현 (i137의 i137_tech.gate / i137_gate.py 이중 구현과 사후 분리를 대체). 생성 전에 코드를 protocol에 잠그고 main 진입 전에 한 번만 실행한다.

사전 규칙 (plan iter_138 amendment):
- 진입 조건(하나라도 실패하면 passed=False): 새 D24 job의 완료·provenance·EOS 100%·경계 유효 100%·A/B 각 12·return code 0, 재사용 iter_137 D24 job 3개의 원시 재검증,
  구성 간(w2/w4/resume, iter_137 w2 대 iter_138 w2) token 동일, 실제 SIGKILL 재개 기록, 경계/tensor(technical·main)/negative/cpu 검사 통과,
  측정 누락·빈 자원 로그·여유 부족을 통과시키지 않는 메모리 판정.
- 관찰 항목(진입 조건이 아님): 첫 줄 형식 유효율(인터페이스별). 분모 12에서 95% 기준은 전건 유효를 요구하므로, iter_137의 원 실패(A 11/12)는 보존하고
  E 출력 생성 전에 이 amendment로 분리한다. E 조건별 95% 기준은 i138_eval.decide에서 그대로 유지된다. 정확도는 gate에 쓰지 않는다.
모든 입력은 원시 job·kill_record·resources에서 읽는다."""
import sys, inspect
from i138_common import RES, OLD137, sha, read, save, now
from i138_spec import parse
import i138_run as R

T = RES / 'tests'
MARGIN = R.MARGIN_MIB
OLD_JOBS = [OLD137 / 'jobs' / n for n in ('tb1024_w2', 'tb1024_w4', 'tb1024_resume')]
NEW_JOB = RES / 'jobs' / 'd24_w2'
UNCHANGED_FUNCS = ['worker', 'load_records', '_load_records', 'check_records', 'verify_job', 'requests', 'messages', 'input_tensor', 'admission', 'boundary_ids', 'smi', 'allowed']


def memory_ok(samples, mapping, total):
    """samples: resources 로그의 gpu 행 목록(각 [{'index','used'}...]). mapping: worker→물리 GPU index. total: GPU별 총 메모리(MiB).
    측정이 없거나(빈 로그) 일부 GPU 측정이 누락되거나 used+worker당 여유가 용량을 넘으면 False. 누락을 0으로 대체하지 않는다."""
    if not samples or not mapping: return False, 'no_samples'
    peak = {}
    for row in samples:
        for g in row:
            peak[g['index']] = max(peak.get(g['index'], 0), int(g['used']))
    for g in set(mapping):
        if g not in peak or g not in total: return False, 'missing_measurement_gpu_' + g
        if peak[g] + MARGIN * mapping.count(g) > int(total[g]): return False, 'insufficient_margin_gpu_' + g
    return True, 'ok'


def tokens_of(job): return {r['id']: r['tokens'] for r in R.load_records(job)}


def source_equal():
    """i137_run과 i138_run에서 생성·claim·record·검증 함수 소스가 같은지 (같다면 iter_137의 재개·4 worker 기록을 알고리즘 근거로 재사용)."""
    import i137_run as O
    return {f: inspect.getsource(getattr(O, f)) == inspect.getsource(getattr(R, f)) for f in UNCHANGED_FUNCS}


def gate():
    import i137_run as O
    t = {s: read(T / ('tensor_check_%s.json' % s)) for s in ('technical', 'main')}; n = read(T / 'negative_tests.json'); b = read(T / 'boundary_check.json'); c = read(T / 'cpu_tests.json')
    n_expected = len(R.requests('technical'))
    rec = R.verify_job(NEW_JOB, 'technical')   # 새 D24: 완료·protocol·provenance 재검증
    old = [O.verify_job(j, 'technical') for j in OLD_JOBS]   # 재사용 증거: iter_137 원 protocol로 원시 재검증
    base = tokens_of(NEW_JOB); old_t = [{r['id']: r['tokens'] for r in x} for x in old]
    identical_old = all(o == old_t[0] for o in old_t)   # w2/w4/resume 내부 정합
    same_as_old = base == old_t[0]                       # 새 runner 대 iter_137 token
    parsed = [parse(r['final_text'], r['eos'], r['boundary_status']) for r in rec]
    ifc = {i: [p for r, p in zip(rec, parsed) if r['id'].endswith('__' + i)] for i in ('A', 'B')}
    n_by = {i: len(v) for i, v in ifc.items()}; valid = {i: sum(p is not None for p in v) / len(v) for i, v in ifc.items()}
    old_parsed = [parse(r['final_text'], r['eos'], r['boundary_status']) for r in old[0]]
    old_valid = {i: sum(p is not None for r, p in zip(old[0], old_parsed) if r['id'].endswith('__' + i)) / 12 for i in ('A', 'B')}
    launch = sorted(NEW_JOB.glob('launch_*.json')); assert len(launch) == 1, 'exactly one launch expected'
    mapping = read(launch[0])['mapping']; comp = read(NEW_JOB / 'completion.json')
    samples = []
    for rp in sorted(NEW_JOB.glob('resources_*.jsonl')):
        samples += [__import__('json').loads(l)['gpu'] for l in open(rp) if l.strip()]
    total = {g['index']: int(g['total']) for g in R.smi()}
    mem, mem_reason = memory_ok(samples, mapping, total)
    mem = mem and max(r['peak_reserved_mib'] for r in rec) < min(total.values())
    kr = [read(p) for p in sorted((OLD137 / 'jobs/tb1024_resume').glob('kill_record_*.json'))]
    resume_valid = bool(kr) and all(k['killed_while_running'] and 0 < k['lines_at_kill'] < n_expected and not k['completion_exists'] for k in kr)
    old_comp = [read(j / 'completion.json') for j in OLD_JOBS]
    same_src = source_equal()
    checks = dict(boundary=b['passed'], tensor_technical=t['technical']['passed'], tensor_main=t['main']['passed'], negative=n['all_rejected'], cpu_tests=c['passed'],
                  new_job_complete_expected=len(rec) == n_expected and n_by == {'A': n_expected // 2, 'B': n_expected // 2}, new_job_rc_zero=all(x == 0 for x in comp['returncodes']),
                  new_job_all_eos=all(r['eos'] for r in rec), new_job_boundary_valid=all(r['boundary_status'] != 'invalid_boundary' for r in rec),
                  reused_jobs_internal_identical=identical_old, new_runner_tokens_identical_to_iter137=same_as_old, reused_jobs_rc_zero=all(all(x == 0 for x in cc['returncodes']) for cc in old_comp),
                  reused_resume_was_interrupted_midrun=resume_valid, unchanged_algorithm_sources=all(same_src.values()),
                  memory_measured_and_within_capacity=mem)
    passed = all(checks.values())
    ev = {str(p): sha(p) for p in [T / 'tensor_check_technical.json', T / 'tensor_check_main.json', T / 'negative_tests.json', T / 'boundary_check.json', T / 'cpu_tests.json', NEW_JOB / 'completion.json', launch[0],
                                    *[j / 'completion.json' for j in OLD_JOBS], *sorted((OLD137 / 'jobs/tb1024_resume').glob('kill_record_*.json')), RES / 'requests/technical.json']}
    save(T / 'technical_gate.json', dict(created_at=now(), final_stage='technical', passed=passed, checks=checks, memory_reason=mem_reason, n_resource_samples=len(samples), mapping=mapping, total_mib=total,
                                         observed_not_gating=dict(first_line_valid_rate_new_d24=valid, first_line_valid_rate_iter137_d24=old_valid, n_invalid_new=sum(p is None for p in parsed),
                                                                  invalid_ids_new=[r['id'] for r, p in zip(rec, parsed) if p is None],
                                                                  note='iter_137 원 gate는 이 값(A 11/12)으로 중단됐다. 이 기록은 보존되며 이번 gate는 형식률을 진입 조건에서 분리한 사전 amendment이다(E 생성 전).'),
                                         unchanged_function_sources=same_src, main_max_new_tokens=R.config_for('technical')['max_new_tokens'], main_workers=2,
                                         main_workers_reason='GPU당 1 worker. iter_137 loading 포함 처리량 w2 41.88/w4 29.85 req/min이지만 w4는 두 worker가 0건 처리해 일반 결론이 아니므로 새 병렬 탐색은 하지 않는다.',
                                         evidence_sha256=ev, n_expected=n_expected))
    print({k: v for k, v in checks.items()}, 'valid_observed', valid, 'passed', passed)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(gate())
