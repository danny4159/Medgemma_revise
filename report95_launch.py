"""iter_095 병렬 실행기. worker 수와 GPU 수를 분리하고, 각 worker 시작 직전에 실제 점유와 예약 합산을 다시 확인한다.

plan.json: {"name", "jobs": [{"stage","shard","nshards","gpu"("auto"=허용 GPU 중 여유 최대),"out","resume"?,"extra"?}]}
admission: (실제 사용 MiB, 시작 시점 외부 점유+실행 중 worker 예약 합) 중 큰 쪽 + worker peak + 2 GiB <= 장치 용량.
 - 예약은 실행 중인 worker만 합산한다(끝난 worker 제외). 시작 직전 매번 nvidia-smi를 읽는다.
 - 거부되면 해당 job은 시작하지 않고 기록한다(실행 중 worker는 건드리지 않는다).
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from report95_common import ROOT, R95, CURE_PY, isolated_env, save, sha

PEAK_MIB = 10100      # C worker 실측 nvidia-smi 점유(iter_086 D8 처리량 시험). Describe 출력 길이는 D8에서 재확인한다.
MARGIN_MIB = 2048


def smi():
    q = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'], text=True)
    return {x.split(',')[0].strip(): (int(x.split(',')[1]), int(x.split(',')[2])) for x in q.splitlines()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--stagger', type=float, default=20.0)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    launch_dir = R95 / 'launches' / f"{plan['name']}_{time.time_ns()}"
    launch_dir.mkdir(parents=True)
    save(launch_dir / 'plan.json', plan)
    env = isolated_env()
    procs, log = [], []
    t_launch = time.monotonic()
    base = {g: v[0] for g, v in smi().items()}  # launcher 시작 시점의 외부 점유
    for i, j in enumerate(plan['jobs']):
        Path(j['out']).resolve().relative_to(R95)
        s = smi()
        live = [(k, jj, pp, t0) for k, jj, pp, t0, _ in procs if pp.poll() is None]

        cand = allowed if j['gpu'] == 'auto' else [j['gpu']]
        assert all(g in allowed for g in cand), f'gpu {cand} outside inherited allowed set {allowed}'
        best = None
        for g in cand:
            used, total = s[g]
            # 실행 중 worker는 적재 중이면 실제 점유에 아직 덜 반영돼 있다: 시작 시점 외부 점유(base)+실행 중 worker 예약합과 실측 중 큰 값.
            young = sum(PEAK_MIB for _, jj, _, t0 in live if jj['_gpu'] == g)
            commit = max(used, base[g] + young)
            free = total - commit
            if best is None or free > best[1]:
                best = (g, free, used, total, young)
        g, free, used, total, young = best
        ok = free >= PEAK_MIB + MARGIN_MIB
        log.append({'job': i, 'gpu': g, 'used_mib': used, 'live_reserved_mib': young, 'total_mib': total, 'need_mib': PEAK_MIB + MARGIN_MIB,
                    'free_after_commit_mib': free, 'admit': ok})
        if not ok:
            save(launch_dir / f'admission_refused_job{i}.json', {'log': log})
            print(json.dumps({'refused': j, 'log': log[-1]}))
            continue
        j = {**j, '_gpu': g}
        cmd = [str(CURE_PY), str(ROOT / 'report95_gen.py'), '--stage', j['stage'], '--gpu', g, '--out', j['out'],
               '--shard', str(j['shard']), '--nshards', str(j['nshards'])] + (['--resume'] if j.get('resume') else []) + j.get('extra', [])
        so = (launch_dir / f'job{i}.stdout.log').open('x')
        se = (launch_dir / f'job{i}.stderr.log').open('x')
        procs.append((i, j, subprocess.Popen(cmd, cwd=ROOT, env=dict(env), stdout=so, stderr=se), time.monotonic(), cmd))
        time.sleep(a.stagger)
    with (launch_dir / 'resource.jsonl').open('x') as rf:
        while any(p.poll() is None for _, _, p, _, _ in procs):
            rf.write(json.dumps({'t': time.time(), 'smi': smi()}) + '\n')
            rf.flush()
            time.sleep(15)
    rcs = {i: p.returncode for i, _, p, _, _ in procs}
    res = {'plan': a.plan, 'plan_sha256': sha(a.plan), 'admission': log, 'returncodes': rcs, 'cmds': {i: c for i, _, _, _, c in procs},
           'wall_s': time.monotonic() - t_launch, 'script_sha256': sha(__file__), 'n_jobs_planned': len(plan['jobs']),
           'n_jobs_started': len(procs)}
    save(launch_dir / 'launch_result.json', res)
    print(json.dumps({'launch_dir': str(launch_dir), 'returncodes': rcs, 'wall_s': res['wall_s']}))
    return 0 if all(v == 0 for v in rcs.values()) and len(rcs) == len(plan['jobs']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
