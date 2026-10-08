"""iter_101 실행 경로 검사: 실제 사용하는 report101_cure / report101_gen 진입점에서 거부·재개 동작을 확인한다.

CPU 검사(--cpu): 완료 파일 변조 거부, 동시 launcher 거부, 허용 GPU 밖 worker 거부, protocol/소스 digest 변경 거부, 요청 변경 거부.
GPU 검사(--gpu): 통제된 중단(--limit) 후 재개 + torn tail 복구 → 기존 완료 출력과 token 일치(CURE 12건, 교정 6건).
모든 사본은 results/iter_101/tests 아래에 만든다. 원 결과 디렉터리는 읽기만 한다.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import fcntl
from pathlib import Path

from report86_common import ROOT, save, sha, read_jsonl_complete

R101 = ROOT / 'results/iter_101'
T = R101 / 'tests'
PY = sys.executable
CURE_PY = ROOT / 'results/environments/cure085/bin/python'


def run(cmd, env=None, timeout=3600):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stderr or '')[-600:]


def fresh(src, name, ignore=()):
    dst = T / name
    assert not dst.exists(), f'{dst} exists'
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*ignore))
    return dst


def cpu_tests():
    res = {}
    cure_src, gen_src = R101 / 'cure/D4_w2', R101 / 'gen/D4_w2'
    reqD4 = str(R101 / 'data/corr_D4/requests.json')
    # CURE: 정상 재검증(변조 없는 사본 → 성공해야 함)
    d = fresh(cure_src, 'cure_ok_copy')
    rc, err = run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2'])
    res['cure_untouched_copy_accepted'] = {'rc': rc, 'pass': rc == 0, 'err': err}
    # CURE: outputs.jsonl 변조 → 거부
    d = fresh(cure_src, 'cure_tamper_output')
    f = d / 'shard0/outputs.jsonl'
    f.write_bytes(f.read_bytes().replace(b'effusion', b'effusioN', 1))
    rc, err = run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2'])
    res['cure_tampered_output_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    # CURE: completion 파일 hash 변조 → 거부
    d = fresh(cure_src, 'cure_tamper_completion')
    c = json.loads((d / 'shard1/completion.json').read_text())
    c['files']['outputs.jsonl'] = '0' * 64
    (d / 'shard1/completion.json').write_text(json.dumps(c))
    rc, err = run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2'])
    res['cure_tampered_completion_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    # CURE: mapping digest(소스/입력 변경 모사) 변경 → 거부
    d = fresh(cure_src, 'cure_changed_mapping')
    m = json.loads((d / 'mapping.json').read_text())
    m['scientific_digest'] = '1' * 64
    (d / 'mapping.json').write_text(json.dumps(m))
    rc, err = run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2'])
    res['cure_changed_protocol_digest_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    # CURE: 동시 launcher 거부
    d = fresh(cure_src, 'cure_lock_copy')
    with (d / 'launcher.lock').open('a') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rc, err = run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2'])
    res['cure_second_launcher_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    # CURE: 허용 GPU 밖 worker 거부(모델 로딩 전)
    d = fresh(cure_src, 'cure_gpu_copy')
    rc, err = run([str(CURE_PY), 'report101_cure.py', 'worker', '--stage', 'D4', '--out', str(d), '--gpu', '7', '--shard', '0', '--nshards', '2'],
                  env={'CUDA_VISIBLE_DEVICES': '0,1'})
    res['cure_worker_gpu_outside_allowed_rejected'] = {'rc': rc, 'pass': rc != 0 and 'not in inherited' in err, 'err': err}
    # GEN: 정상 사본 수용 / 변조 거부 / 요청 변경 / protocol 소스 변경 / 동시 launcher / GPU
    d = fresh(gen_src, 'gen_ok_copy')
    rc, err = run([PY, 'report101_gen.py', 'launch', '--requests', reqD4, '--out', str(d), '--workers', '2'])
    res['gen_untouched_copy_accepted'] = {'rc': rc, 'pass': rc == 0, 'err': err}
    d = fresh(gen_src, 'gen_tamper_output')
    f = d / 'worker_0.jsonl'
    f.write_bytes(f.read_bytes().replace(b'effusion', b'effusioN', 1))
    rc, err = run([PY, 'report101_gen.py', 'launch', '--requests', reqD4, '--out', str(d), '--workers', '2'])
    res['gen_tampered_output_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    d = fresh(gen_src, 'gen_tamper_completion')
    c = json.loads((d / 'completion.json').read_text())
    c['files']['worker_1.jsonl'] = '0' * 64
    (d / 'completion.json').write_text(json.dumps(c))
    rc, err = run([PY, 'report101_gen.py', 'launch', '--requests', reqD4, '--out', str(d), '--workers', '2'])
    res['gen_tampered_completion_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    d = fresh(gen_src, 'gen_changed_request')
    rq = json.loads(Path(reqD4).read_text())
    rq[0]['prompt'] += ' '
    save(T / 'requests_changed_prompt.json', rq)
    rc, err = run([PY, 'report101_gen.py', 'launch', '--requests', str(T / 'requests_changed_prompt.json'), '--out', str(d), '--workers', '2'])
    res['gen_changed_request_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    d = fresh(gen_src, 'gen_changed_source_hash')
    p = json.loads((d / 'protocol.json').read_text())
    p['source_sha256']['report101_gen.py'] = '2' * 64
    (d / 'protocol.json').write_text(json.dumps(p))
    rc, err = run([PY, 'report101_gen.py', 'launch', '--requests', reqD4, '--out', str(d), '--workers', '2'])
    res['gen_changed_source_digest_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    d = fresh(gen_src, 'gen_lock_copy')
    with (d / 'launcher.lock').open('a') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rc, err = run([PY, 'report101_gen.py', 'launch', '--requests', reqD4, '--out', str(d), '--workers', '2'])
    res['gen_second_launcher_rejected'] = {'rc': rc, 'pass': rc != 0, 'err': err}
    d = fresh(gen_src, 'gen_gpu_copy')
    rc, err = run([PY, 'report101_gen.py', 'worker', '--requests', reqD4, '--out', str(d), '--gpu', '7', '--shard', '0', '--workers', '2'],
                  env={'CUDA_VISIBLE_DEVICES': '0,1'})
    res['gen_worker_gpu_outside_allowed_rejected'] = {'rc': rc, 'pass': rc != 0 and 'not in inherited' in err, 'err': err}
    res['all_pass'] = all(v['pass'] for v in res.values())
    save(T / 'runtime_cpu_tests.json', res)
    print(json.dumps({k: v['pass'] if isinstance(v, dict) else v for k, v in res.items()}, indent=1))


def tokens(recs):
    return {r['id']: [a['suffix_ids'] for a in r['attempts']] for r in recs}


def gpu_tests():
    res = {}
    # CURE 재개: 2 worker, 각 3건 저장 후 중단(--limit 3, limit 도달 시 worker 정상 종료) → 재개 → 원 D4와 token 일치
    d = T / 'cure_resume'
    assert not d.exists()
    rc1 = subprocess.run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2', '--limit', '3', '--stagger', '5'],
                         cwd=ROOT, capture_output=True, text=True).returncode
    n_part = sum(len(read_jsonl_complete(d / f'shard{s}/outputs.jsonl')) for s in range(2))
    # torn tail 삽입(소유 worker가 없는 상태에서만)
    with (d / 'shard0/outputs.jsonl').open('ab') as f:
        f.write(b'{"id": "partial-row-no-newline')
    rc2 = subprocess.run([PY, 'report101_cure.py', 'launch', '--stage', 'D4', '--out', str(d), '--workers', '2', '--stagger', '5'],
                         cwd=ROOT, capture_output=True, text=True).returncode
    base = {}
    for s in range(2):
        base.update(tokens(read_jsonl_complete(R101 / f'cure/D4_w2/shard{s}/outputs.jsonl')))
    got = {}
    for s in range(2):
        got.update(tokens(read_jsonl_complete(d / f'shard{s}/outputs.jsonl')))
    res['cure_resume'] = {'rc_limit_run': rc1, 'records_after_limit_run': n_part, 'rc_resume': rc2, 'n_final': len(got), 'tokens_equal_original': got == base,
                          'completion_exists': (d / 'completion.json').exists(), 'pass': rc1 == 0 and n_part == 6 and rc2 == 0 and got == base and (d / 'completion.json').exists()}
    # 교정 재개: 비폭주 6건 subset, 2 worker, 각 1건 저장 후 중단 → torn tail → 재개 → 원 D4와 token 일치
    allr = json.loads((R101 / 'data/corr_D4/requests.json').read_text())
    done = {}
    for s in range(2):
        for r in read_jsonl_complete(R101 / f'gen/D4_w2/worker_{s}.jsonl'):
            done[r['id']] = r
    sub = [q for q in allr if len(done[q['id']]['attempts']) == 1][:6]
    save(T / 'requests_resume6.json', sub)
    g = T / 'gen_resume'
    assert not g.exists()
    rcg1 = subprocess.run([PY, 'report101_gen.py', 'launch', '--requests', str(T / 'requests_resume6.json'), '--out', str(g), '--workers', '2', '--limit', '1',
                           '--stagger', '5', '--peak-mib', '9000'], cwd=ROOT, capture_output=True, text=True).returncode
    n1 = sum(len(read_jsonl_complete(g / f'worker_{s}.jsonl')) for s in range(2))
    with (g / 'worker_1.jsonl').open('ab') as f:
        f.write(b'{"id": "partial-row-no-newline')
    rcg2 = subprocess.run([PY, 'report101_gen.py', 'launch', '--requests', str(T / 'requests_resume6.json'), '--out', str(g), '--workers', '2', '--stagger', '5',
                           '--peak-mib', '9000'], cwd=ROOT, capture_output=True, text=True).returncode
    gt = {}
    for s in range(2):
        gt.update(tokens(read_jsonl_complete(g / f'worker_{s}.jsonl')))
    bt = {k: [a['suffix_ids'] for a in done[k]['attempts']] for k in gt}
    res['gen_resume'] = {'rc_limit_run': rcg1, 'records_after_limit_run': n1, 'rc_resume': rcg2, 'n_final': len(gt), 'tokens_equal_original_D4_w2': gt == bt,
                         'completion_exists': (g / 'completion.json').exists(), 'pass': rcg1 == 0 and n1 == 2 and rcg2 == 0 and len(gt) == 6 and gt == bt and (g / 'completion.json').exists()}
    res['all_pass'] = all(v['pass'] for v in res.values())
    save(T / 'runtime_gpu_tests.json', res)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    T.mkdir(parents=True, exist_ok=True)
    {'--cpu': cpu_tests, '--gpu': gpu_tests}[sys.argv[1]]()
