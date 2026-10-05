"""고정 a81 실행: 실제 시작 직전 GPU 여유 확인, 예약, 자식 수명 관리."""
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import a81_common as C
import a81_run as R
from rf78_launch import smi
from rsna_diag import queue_lock


def launch(protocol, out, workers=2, est_gb=9.8, tech=False, kill_after=None):
    p, reqs = R.load_protocol(protocol)
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    initial = smi()
    if not allowed or any(g not in initial for g in allowed):
        raise ValueError('physical GPU mapping not supported/allowed')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    lk, _, _ = queue_lock.try_lock(str(out / 'launcher.lock'), queue_lock.my_info(worker='launcher'))
    if lk is None:
        raise ValueError('launcher already owned')
    procs = []; logs = []; events = []; peak = {}; attempt = f'{time.time_ns()}'
    before = time.monotonic(); killed = False
    old_handlers = {}
    def stop(sig, frame):
        raise KeyboardInterrupt(f'signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        old_handlers[sig] = signal.signal(sig, stop)
    try:
        R.records(out, p, reqs)
        # 각 장치별 최초 점유+새 예약과 시작 직전 실제 점유 중 큰 값으로 admission.
        reserved = {g: 0 for g in allowed}
        need = (est_gb + 2) * 1024
        for w in range(workers):
            now = smi()
            remaining = {g: now[g]['total_mib'] - max(now[g]['used_mib'], initial[g]['used_mib'] + reserved[g]) for g in allowed}
            g = max(allowed, key=lambda x: remaining[x])
            if remaining[g] < need:
                raise RuntimeError(f'admission failed need={need} remaining={remaining}')
            reserved[g] += need
            events.append({'worker': w, 'physical_gpu': g, 'logical_gpu': 0, 'smi': now, 'remaining_before': remaining, 'need_mib': need})
            cmd = [sys.executable, 'a81_run.py', '--protocol', str(protocol), '--out', str(out), '--worker', str(w), '--gpu', g]
            if tech:
                cmd.append('--tech')
            lf = open(out / f'worker{w}_{attempt}.log', 'xb'); logs.append(lf)
            procs.append(subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=dict(os.environ)))
        while any(x.poll() is None for x in procs):
            now = smi()
            for g, v in now.items():
                peak[g] = max(peak.get(g, 0), v['used_mib'])
            if kill_after is not None and not killed and len(list(out.glob('worker*/records/*.json'))) >= kill_after:
                for x in procs:
                    if x.poll() is None:
                        x.kill()
                killed = True
            if any(x.poll() not in (None, 0) for x in procs) and not killed:
                for x in procs:
                    if x.poll() is None:
                        x.terminate()
            time.sleep(0.5)
        codes = [x.wait() for x in procs]
        result = {'protocol': str(protocol), 'protocol_digest': C.digest(p), 'workers': workers, 'events': events,
                  'exit_codes': codes, 'wall_s': time.monotonic() - before, 'peak_used_mib': peak, 'killed_for_test': killed}
        C.save(out / f'launch_{attempt}.json', result)
        if any(codes) and not killed:
            raise RuntimeError(f'child failure: {codes}; logs: {out}')
        if not killed:
            done = R.verify(protocol, out)
            files = {str(f): C.sha(f) for f in sorted(out.glob('worker*/records/*.json'))}
            for x in done.values():
                assert C.sha(x['env_path']) == x['env_digest']
                files[x['env_path']] = x['env_digest']
            C.save(out / f'completion_{attempt}.json', {'passed': True, 'n': len(done), 'protocol_digest': C.digest(p), 'files': files,
                                                      'launch_file': str(out / f'launch_{attempt}.json'), 'launch_sha256': C.sha(out / f'launch_{attempt}.json')})
        print(result, flush=True)
        return result
    finally:
        for x in procs:
            if x.poll() is None:
                x.terminate()
        for x in procs:
            try:
                x.wait(timeout=30)
            except subprocess.TimeoutExpired:
                x.kill(); x.wait()
        for f in logs:
            f.close()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        lk.release()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--protocol', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--workers', type=int, default=2); ap.add_argument('--est-gb', type=float, default=9.8)
    ap.add_argument('--tech', action='store_true'); ap.add_argument('--kill-after', type=int)
    a = ap.parse_args()
    launch(a.protocol, a.out, a.workers, a.est_gb, a.tech, a.kill_after)
