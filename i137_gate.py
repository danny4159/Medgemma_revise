"""iter_137 기술 gate 재계산 (생성 후 분리 도구). i137_tech.gate와 판정 기준은 동일하다. 차이: 빨리 끝난 w4의 resources 샘플이 비어 있어 원 코드가 max(빈 dict)로 중단했으므로
샘플 없음을 기록하고 record의 torch peak로 판정하는 보정만 적용했다. i137_tech.py는 protocol에 잠긴 원본 그대로 두었다. 모든 입력은 원시 job·kill_record·compare에서 읽는다."""
import sys, json
from i137_common import RES, read, save, now
from i137_spec import parse
import i137_run as R
from i137_tech import T, TAGS, compare as _unused  # noqa: F401


def gate(final_stage):
    """사전 기준: 최종 기술 집단 모든 조건(NONE 포함) EOS 100%, 첫 줄 형식 유효율>=95%, tensor·negative·boundary·w4 정합성·재개·메모리 검사 통과. 정확도는 사용하지 않는다."""
    tag = TAGS[final_stage]
    t = read(T / 'tensor_check.json'); n = read(T / 'negative_tests_v2.json'); b = read(T / 'boundary_check.json')
    names = [tag + '_w2', tag + '_w4', tag + '_resume']; cfgs = read(T / ('compare_%s.json' % names[0]))['configs']
    rec = R.verify_job(RES / 'jobs' / names[0], final_stage)   # 원시 record·completion을 요청 manifest(잠금)에서 재검증
    n_expected = len(R.requests(final_stage))
    parsed = [parse(r['final_text'], r['eos'], r['boundary_status']) for r in rec]
    ifc = {i: [p for r, p in zip(rec, parsed) if r['id'].endswith('__' + i)] for i in ('A', 'B')}
    valid_by_iface = {i: sum(p is not None for p in v) / len(v) for i, v in ifc.items()}; n_by_iface = {i: len(v) for i, v in ifc.items()}
    all_eos = all(r['eos'] for r in rec)
    cap = {g['index']: int(g['total']) for g in R.smi()}
    mem_ok = all(max(c['max_gpu_used_mib'].values(), default=0) <= min(cap.values()) for c in cfgs.values()) and all(c['max_peak_reserved_mib'] < min(cap.values()) for c in cfgs.values())
    mem_samples = {nm: bool(cfgs[nm]['max_gpu_used_mib']) for nm in names}
    kr = cfgs[names[2]]['kill_records']
    resume_valid = bool(kr) and all(k['killed_while_running'] and 0 < k['lines_at_kill'] < n_expected and not k['completion_exists'] for k in kr)
    for nm in names: R.verify_job(RES / 'jobs' / nm, final_stage)   # 세 구성 모두 원시 완료 검증
    checks = dict(boundary=b['passed'], tensor=t['passed'], negative=n['all_rejected'], w4_identical=cfgs[names[1]]['identical_tokens_to_first'], resume_identical=cfgs[names[2]]['identical_tokens_to_first'],
                  complete_expected=all(v['n'] == n_expected for v in cfgs.values()) and n_by_iface == {'A': n_expected // 2, 'B': n_expected // 2}, rc_zero=all(all(x == 0 for x in v['returncodes']) for v in cfgs.values()),
                  resume_was_interrupted_midrun=resume_valid, all_eos_all_requests=all_eos, first_line_valid_ge_95_each_iface=all(v >= 0.95 for v in valid_by_iface.values()), memory_no_oom_peak_below_capacity=mem_ok)
    passed = all(checks.values())
    thr = {nm: cfgs[nm]['req_per_min_incl_load'] for nm in names[:2]}
    ok_cfg = [nm for nm in names[:2] if cfgs[nm]['identical_tokens_to_first'] and all(x == 0 for x in cfgs[nm]['returncodes'])]
    main_workers = 4 if (names[1] in ok_cfg and thr[names[1]] > thr[names[0]]) else 2   # 정확도가 아닌 같은 token·오류 없음·loading 포함 처리량으로 선택
    save(T / ('technical_gate_%s.json' % final_stage), dict(created_at=now(), final_stage=final_stage, passed=passed, checks=checks, valid_rate_by_iface=valid_by_iface, n_by_iface=n_by_iface, n_expected=n_expected,
                                                              n_non_eos=sum(not r['eos'] for r in rec), n_invalid=sum(p is None for p in parsed),
                                                              boundary_status_counts={k: sum(r['boundary_status'] == k for r in rec) for k in ('no_marker', 'thought_final', 'invalid_boundary')},
                                                              main_max_new_tokens=R.config_for(final_stage)['max_new_tokens'], main_workers=main_workers, throughput_req_per_min_incl_load=thr, gpu_used_samples_present=mem_samples, invalid_ids=[r['id'] for r, p in zip(rec, parsed) if p is None],
                                                              note='기술 정확도는 gate에 쓰지 않음. 유효율은 인터페이스별(D 분모 각 12). 요청 수·재개 판정은 원시 완료·kill_record에서 계산.'))
    print(checks, 'valid', valid_by_iface, 'passed', passed, 'main_workers', main_workers)



if __name__ == '__main__':
    gate(sys.argv[1])
