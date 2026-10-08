"""iter_100: 기존 생성 연산(report90_gen/report90_gen_safe/report90_recovery_gen)을 유지하고 출력·cache를 iter_100으로 격리한다.

report97_gen.py와 같은 구조이며 launch만 다음을 보강한다(생성 수식·protocol은 그대로).
- attempt 번호를 기존 로그 파일 이름에서 정해 비정상 종료 후 재시작 시 로그 충돌을 피한다.
- worker는 report90_gen.worker의 허용 GPU 집합 검사(--gpu in CUDA_VISIBLE_DEVICES)를 그대로 쓰고, launch의 장치 선택도 허용 집합 안으로 한정한다.
- worker 시작 직전 매번 nvidia-smi로 실제 free를 다시 읽고, 이미 시작한 살아 있는 worker마다 (peak - 현재 점유 + 2GiB)를 예약으로 차감한다.
"""
import argparse
import fcntl
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import report90_gen as C
import report90_gen_safe as S
import report90_recovery_gen as RG  # noqa: F401  load_model·SOURCES 패치 적용
from report86_common import save, sha, sha_obj

OUT = Path(__file__).resolve().parent / 'results/iter_100'
C.OUT = OUT
C.SOURCES = C.SOURCES + ['report100_gen.py']
C.__file__ = __file__


def next_attempt(out):
    nums = [int(m.group(1)) for p in Path(out).glob('launch*_worker*.stdout.log') for m in [re.match(r'launch(\d+)_worker', p.name)] if m]
    return max(nums) + 1 if nums else 0


def launch(a):
    out = Path(a.out).resolve()
    out.relative_to(C.OUT)
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proto = C.protocol(a.requests, a.checkpoint)
        for path, value in [(out / 'protocol.json', proto), (out / 'mapping.json', dict(workers=a.workers))]:
            if path.exists():
                import json
                assert json.loads(path.read_text()) == value, ('protocol/mapping changed', path)
            else:
                save(path, value)
        # 부분 행 복구는 worker lock을 소유한 상태에서만 한다.
        for s in range(a.workers):
            with (out / f'worker_{s}.lock').open('a') as wl:
                fcntl.flock(wl, fcntl.LOCK_EX | fcntl.LOCK_NB)
                from pg43_run import repair_tail
                repair_tail(str(out / f'worker_{s}.jsonl'))
        existing, expected = C.verify(out, a.requests, proto, a.workers)
        if len(existing) == len(expected):
            cp = out / 'completion.json'
            completion = dict(n=len(existing), protocol_digest=sha_obj(proto),
                              files={str(out / f'worker_{s}.jsonl'): sha(out / f'worker_{s}.jsonl') for s in range(a.workers)})
            if cp.exists():
                import json
                assert json.loads(cp.read_text()) == completion
            else:
                save(cp, completion)
            return 0
        allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
        procs, logs = [], []
        attempt = next_attempt(out)
        start = time.monotonic()

        def stop(*args):
            raise KeyboardInterrupt('supervisor stopped; terminating owned children')
        signal.signal(signal.SIGTERM, stop)
        try:
            for s in range(a.workers):
                raw = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], text=True)
                free = {x.split(',')[0].strip(): int(x.split(',')[1]) for x in raw.splitlines()}
                usage = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'], text=True)
                actual = {int(x.split(',')[0]): int(x.split(',')[1]) for x in usage.splitlines() if x.strip()}
                choices = {g: free[g] - sum(max(0, a.peak_mib - actual.get(p.pid, 0)) + 2048 for _, p, gg in procs if gg == g and p.poll() is None)
                           for g in allowed}
                gpu = max(choices, key=choices.get)
                assert choices[gpu] >= a.peak_mib + 2048, ('memory admission', choices)
                cmd = [sys.executable, __file__, 'worker', '--requests', a.requests, '--out', str(out), '--gpu', gpu, '--shard', str(s),
                       '--workers', str(a.workers)]
                if a.checkpoint:
                    cmd += ['--checkpoint', a.checkpoint]
                if a.limit:
                    cmd += ['--limit', str(a.limit)]
                so = (out / f'launch{attempt}_worker{s}.stdout.log').open('x')
                se = (out / f'launch{attempt}_worker{s}.stderr.log').open('x')
                logs.extend([so, se])
                procs.append((s, subprocess.Popen(cmd, stdout=so, stderr=se), gpu))
                time.sleep(a.stagger)
            codes = {s: p.wait() for s, p, _ in procs}
        finally:
            for _, p, _ in procs:
                if p.poll() is None:
                    p.terminate()
            for _, p, _ in procs:
                p.wait()
            for f in logs:
                f.close()
        save(out / f'launch_{attempt:03}.json', dict(codes=codes, wall_s=time.monotonic() - start, mapping={s: g for s, _, g in procs},
                                                      protocol_digest=sha_obj(proto), allowed=allowed))
        assert all(c == 0 for c in codes.values())
        recs, expected = C.verify(out, a.requests, proto, a.workers)
        if len(recs) == len(expected):
            save(out / 'completion.json', dict(n=len(recs), protocol_digest=sha_obj(proto),
                                               files={str(out / f'worker_{s}.jsonl'): sha(out / f'worker_{s}.jsonl') for s in range(a.workers)}))
        return 0 if len(recs) == len(expected) or a.limit else 2


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['worker', 'launch'])
    p.add_argument('--requests', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--checkpoint')
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--gpu')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--peak-mib', type=int, default=12000)
    p.add_argument('--stagger', type=float, default=20.0)
    a = p.parse_args()
    raise SystemExit(C.worker(a) if a.command == 'worker' else launch(a))
