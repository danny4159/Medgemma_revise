"""iter_086 실행 경로 회귀 검사(모델 로딩 없이 실패해야 하는 경로 + 작은 재개 경로). 결과: results/iter_086/tests/regression.json
python test_report86.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from report86_common import ROOT, R86, CURE_PY, isolated_env, save, sha, read_jsonl_complete

T = R86 / 'tests'
SRC = R86 / 'D8/regress/C_killresume_a'  # 완료된 C 재개 시험 디렉터리(8개 행)
results = []


def run_gen(out, extra, expect_rc_zero, py=str(CURE_PY)):
    cmd = [py, str(ROOT / 'report86_gen.py'), '--stage', 'D8', '--system', 'C', '--gpu', '0', '--out', str(out), '--resume'] + extra
    p = subprocess.run(cmd, cwd=ROOT, env=isolated_env(), capture_output=True, text=True)
    return p.returncode, p.stdout[-400:], p.stderr[-600:]


def copy_case(name):
    d = T / name
    shutil.copytree(SRC, d)
    for f in d.glob('regress_result_*.json'):
        pass
    return d


def check(name, ok, detail=''):
    results.append({'name': name, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name, detail[:200])


def n_starts(d):
    return sum(1 for l in (d / 'executions.jsonl').read_text().splitlines() if json.loads(l)['event'] in ('start',))


def main():
    T.mkdir(exist_ok=True)
    # 1. torn tail 복구: 부분 행을 보존하고 완결 행은 그대로, 모델 로딩 없이 nothing_to_do
    d = copy_case('torn')
    before = (d / 'outputs.jsonl').read_bytes()
    with (d / 'outputs.jsonl').open('ab') as f:
        f.write(b'{"id": "partial-row-without-newline')
    rc, so, se = run_gen(d, ['--regress', '8'], True)
    after = (d / 'outputs.jsonl').read_bytes()
    kept = list(d.glob('outputs.jsonl.partial.*.bin'))
    check('torn_tail_repaired_preserved', rc == 0 and after == before and len(kept) == 1 and kept[0].read_bytes().startswith(b'{"id": "partial'),
          f'rc={rc} kept={len(kept)} same_complete_rows={after == before}')
    # 2. 과학적 protocol 불일치(seed) -> 로딩 전 거부
    d = copy_case('proto_mismatch')
    m = json.loads((d / 'scientific_protocol.json').read_text())
    m['scientific']['seed'] = 18
    (d / 'scientific_protocol.json').write_text(json.dumps(m))
    n0 = n_starts(d)
    rc, so, se = run_gen(d, ['--regress', '8'], False)
    check('protocol_mismatch_refused_before_load', rc != 0 and 'mismatch' in se and n_starts(d) == n0, f'rc={rc}')
    # 3. shard 수 변경 거부
    d = copy_case('shard_mismatch')
    rc, so, se = run_gen(d, ['--regress', '8', '--nshards', '2'], False)
    check('nshards_change_refused', rc != 0 and 'mismatch' in se, f'rc={rc}')
    # 4. 자기 행 변조 거부
    d = copy_case('row_tamper')
    rows = (d / 'outputs.jsonl').read_text().splitlines()
    r = json.loads(rows[0]); r['text'] = r['text'] + ' tampered'
    rows[0] = json.dumps(r, ensure_ascii=False)
    (d / 'outputs.jsonl').write_text('\n'.join(rows) + '\n')
    rc, so, se = run_gen(d, ['--regress', '8'], False)
    check('own_row_tamper_refused', rc != 0 and 'own record invalid' in se, f'rc={rc}')
    # 5. 중복 행 거부
    d = copy_case('dup_row')
    rows = (d / 'outputs.jsonl').read_text().splitlines()
    (d / 'outputs.jsonl').write_text('\n'.join(rows + [rows[0]]) + '\n')
    rc, so, se = run_gen(d, ['--regress', '8'], False)
    check('duplicate_row_refused', rc != 0 and 'duplicate' in se, f'rc={rc}')
    # 6. 동시 worker 소유권(flock): 같은 out에 두 번째 프로세스는 거부
    d = copy_case('lock_owner')
    import fcntl
    lock = (d / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rc, so, se = run_gen(d, ['--regress', '8'], False)
    check('second_worker_same_out_refused', rc != 0 and ('BlockingIOError' in se or 'Resource temporarily' in se), f'rc={rc}')
    lock.close()
    # 7. 계승 원본 변조 거부(manifest 사본의 hash를 바꿔 load_verified가 거부하는지)
    import report86_inherit as I
    man = json.loads(I.MANIFEST.read_text())
    man['systems']['C']['outputs_sha256'] = '0' * 64
    alt = T / 'inherit_tampered_manifest.json'
    alt.write_text(json.dumps(man))
    old = I.MANIFEST
    I.MANIFEST = alt
    try:
        I.load_verified('C')
        ok = False
    except RuntimeError as e:
        ok = 'hash mismatch' in str(e)
    I.MANIFEST = old
    check('inherited_tamper_refused', ok)
    # 8. 계승 prefix 이후 원본이 커져도(다른 프로세스 추가 기록) prefix hash가 맞으면 수용
    recs, v = I.load_verified('C')
    check('inherited_prefix_accepted', len(recs) == 34 and v['outputs_bytes'] > 0, f'n={len(recs)}')
    # 9. 원자적 저장: 이미 있는 파일 덮어쓰기 거부
    try:
        save(T / 'inherit_tampered_manifest.json', {})
        ok = False
    except FileExistsError:
        ok = True
    check('save_refuses_overwrite', ok)
    # 10. GPU admission: C worker 3개를 한 GPU에 선점하면 거부, 2개는 허용(측정 점유 기준)
    import report86_launch as L
    cap = 24576
    need = L.need_mib('C')
    check('admission_two_C_fit_three_refused', 2 * need <= cap < 3 * need, f'need={need} 2x={2 * need} 3x={3 * need} cap={cap}')
    save(T / 'regression.json', {'results': results, 'n_pass': sum(r['pass'] for r in results), 'n': len(results),
                                 'sources': {f: sha(ROOT / f) for f in ['report86_gen.py', 'report86_inherit.py', 'report86_common.py', 'report86_launch.py', 'report86_merge.py']}})
    return 0 if all(r['pass'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
