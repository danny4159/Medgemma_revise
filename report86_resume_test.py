"""CURE 통제된 중단·재개 검사: 계승된 D8 C 요청 N개를 새 경로로 생성하다가 SIGKILL, --resume으로 마치고
계승 행(중단 없는 실행)과 token을 비교한다. 결과는 새 파일로 저장한다.
python report86_resume_test.py <system> <gpu> <n> <kill_after_rows> <tag>
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from report86_common import ROOT, R86, CURE_PY, isolated_env, save, read_jsonl_complete


def main():
    system, gpu, n, k, tag = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    out = R86 / 'D8/regress' / f'{system}_killresume_{tag}'
    py = str(CURE_PY) if system in ('M1G', 'C') else sys.executable
    env = isolated_env()
    base = [py, str(ROOT / 'report86_gen.py'), '--stage', 'D8', '--system', system, '--gpu', gpu, '--out', str(out), '--regress', str(n)]
    log1 = (R86 / 'D8/regress' / f'{system}_killresume_{tag}.run1.log').open('x')
    p = subprocess.Popen(base, cwd=ROOT, env=env, stdout=log1, stderr=subprocess.STDOUT)
    t0 = time.time()
    while True:
        rows = read_jsonl_complete(out / 'outputs.jsonl') if (out / 'outputs.jsonl').exists() else []
        if len(rows) >= k or p.poll() is not None:
            break
        time.sleep(0.2)
    p.send_signal(signal.SIGKILL)
    p.wait()
    rows1 = read_jsonl_complete(out / 'outputs.jsonl')
    raw1 = (out / 'outputs.jsonl').read_bytes()
    log2 = (R86 / 'D8/regress' / f'{system}_killresume_{tag}.run2.log').open('x')
    p2 = subprocess.run(base + ['--resume'], cwd=ROOT, env=env, stdout=log2, stderr=subprocess.STDOUT)
    res_files = sorted(out.glob('regress_result_*.json'))
    res = json.loads(res_files[-1].read_text()) if res_files else None
    raw2 = (out / 'outputs.jsonl').read_bytes()
    summary = {'system': system, 'gpu': gpu, 'n_requested': n, 'kill_after_rows_target': k, 'rows_complete_at_kill': len(rows1),
               'torn_tail_bytes_at_kill': len(raw1) - raw1.rfind(b'\n') - 1 if raw1 else 0,
               'prefix_preserved_after_resume': raw2.startswith(raw1[:raw1.rfind(b'\n') + 1]),
               'run1_rc': p.returncode, 'run2_rc': p2.returncode, 'executions': [json.loads(l)['event'] for l in (out / 'executions.jsonl').read_text().splitlines()],
               'repair_log': (out / 'outputs.jsonl.repair.log').read_text() if (out / 'outputs.jsonl.repair.log').exists() else None,
               'regress_n': res['n'] if res else None, 'regress_n_equal': res['n_equal'] if res else None,
               'complete': res['complete'] if res else None, 'wall_s': time.time() - t0}
    save(R86 / 'D8' / f'resume_equivalence_{system}_{tag}.json', summary)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
