"""iter_136 기술 gate 재계산 (technical 출력 생성 후 작성: 사후 구현 수정, 과학 기준 불변).
i136_tech.gate의 'resume_had_two_results'(result_*.json 2개 이상)는 SIGKILL된 시도가 result 파일을 남기지 않는 설계와 모순되는 구현 오류였다.
(원 gate 결과 results/iter_136/tests/technical_gate_technical.json: passed=False, 보존.) 여기서는 같은 계약(재개 후 완료·동일 출력)을 실제 kill 기록으로 검사한다.
다른 모든 검사와 문턱(EOS 100%·유효율≥95%·tensor·negative·boundary·w4·memory)은 i136_tech.gate와 동일하다. 이 파일은 main 잠금 code에 포함된다."""
import sys
from i136_common import RES, read, save, now
from i136_spec import parse
import i136_run as R

T = RES / 'tests'


def gate(stage='technical', tag='tb1024'):
    old = read(T / ('technical_gate_%s.json' % stage))
    t = read(T / 'tensor_check.json'); n = read(T / 'negative_tests_v2.json'); b = read(T / 'boundary_check.json')
    names = [tag + '_w2', tag + '_w4', tag + '_resume']; cfgs = read(T / ('compare_%s.json' % names[0]))['configs']
    rec = R.verify_job(RES / 'jobs' / names[0], stage)
    parsed = [parse(r['final_text'], r['eos'], r['boundary_status']) for r in rec]
    valid = sum(p is not None for p in parsed) / len(rec)
    kills = sorted((RES / 'jobs' / names[2]).glob('kill_record_*.json')); assert len(kills) == 1; kr = read(kills[0])
    resume_ok = bool(kr['killed_while_running'] and 0 < kr['lines_at_kill'] < kr['expected'] and not kr['completion_exists'] and cfgs[names[2]]['identical_tokens_to_first'] and cfgs[names[2]]['n'] == kr['expected'])
    checks = {k: v for k, v in old['checks'].items() if k != 'resume_had_two_results'}
    checks['resume_real_sigkill_midrun_then_complete'] = resume_ok
    passed = all(checks.values()) and checks['all_eos_all_conditions'] and valid >= 0.95
    save(T / ('technical_gate_v2_%s.json' % stage), dict(created_at=now(), final_stage=stage, passed=passed, checks=checks, valid_rate_all_conditions=valid, n_invalid=sum(p is None for p in parsed),
                                                         n_non_eos=sum(not r['eos'] for r in rec), main_max_new_tokens=R.config_for(stage)['max_new_tokens'], kill_record=kr, supersedes_check='resume_had_two_results',
                                                         original_gate=str(T / ('technical_gate_%s.json' % stage)),
                                                         note='사후 구현 수정: 원 gate 검사기의 resume 조건 오류만 교체. 기술 출력을 본 뒤 작성했으므로 사전 잠금 평가기가 아니다. 문턱·분모 변경 없음.'))
    print(checks, 'valid', valid, 'passed', passed)
    if passed:
        save(T / 'technical_gate.json', dict(read(T / ('technical_gate_v2_%s.json' % stage)), source=str(T / ('technical_gate_v2_%s.json' % stage))))
        print('gate finalized', stage)


if __name__ == '__main__':
    gate(*sys.argv[1:])
