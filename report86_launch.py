"""iter_086 병렬 실행기. worker 수와 GPU 수를 분리해 같은 허용 GPU에 여러 worker를 배치한다.

plan.json: {"name": ..., "jobs": [{"stage","system","shard","nshards","gpu","out", "resume":bool, "extra":[...]}]}
- 시작 직전 nvidia-smi 여유(다른 프로세스 포함)가 (추정 peak + worker당 2 GiB)를 만족해야 시작한다. 같은 GPU에 이미 이번
  launcher가 띄운 worker는 아직 메모리가 올라오지 않았을 수 있으므로 그 worker의 예상 peak를 선점치로 합산한다.
- 자식 환경은 results/iter_086/runtime_cache로 격리하며 system에 맞는 Python을 사용한다. 종료 코드를 수집해 기록한다.
- 실패한 worker가 있어도 다른 worker를 임의로 죽이지 않는다(각 shard는 독립 재개 가능).
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from report86_common import ROOT, R86, CURE_PY, isolated_env, save, sha

# worker 1개의 nvidia-smi 실측 점유(MiB). C·M1G는 iter_086 D8 처리량 시험(resource.jsonl)에서 실측했다.
# M15/B0/M1은 iter_085 reserved peak 8.3-8.4 GiB + CUDA context 추정치이며 E 실행의 resource log로 확인한다.
PEAK_MIB = {'M15': 9000, 'B0': 9100, 'M1': 9000, 'M1G': 4700, 'C': 10100}
MARGIN_MIB = 2048


def smi():
    q = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'], text=True)
    return {x.split(',')[0].strip(): (int(x.split(',')[1]), int(x.split(',')[2])) for x in q.splitlines()}


def need_mib(system):
    return PEAK_MIB[system] + MARGIN_MIB


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', required=True)
    ap.add_argument('--stagger', type=float, default=25.0)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    launch_dir = R86 / 'launches' / f"{plan['name']}_{time.time_ns()}"
    launch_dir.mkdir(parents=True)
    save(launch_dir / 'plan.json', plan)
    env = isolated_env()
    procs = []
    log = []
    for i, j in enumerate(plan['jobs']):
        g = j['gpu']
        assert g in allowed, f'gpu {g} outside inherited allowed set {allowed}'
        py = str(CURE_PY) if j['system'] in ('M1G', 'C') else sys.executable
        Path(j['out']).resolve().relative_to(R86)
        # 이미 올라온 이번 worker의 실제 사용량은 smi에 포함되므로, 선점치 중 실제 반영분은 중복될 수 있어 보수적이다.
        s = smi()
        used, total = s[g]
        need = need_mib(j['system'])
        # 직전 worker가 아직 적재 중일 수 있어 선점치(이번 launcher가 앞서 띄운 worker의 추정 요구량)와 실측 중 큰 값을 쓴다.
        prior_planned = sum(need_mib(jj['system']) for jj in plan['jobs'][:i] if jj['gpu'] == g)
        ok = max(used, prior_planned) + need <= total
        log.append({'job': i, 'gpu': g, 'used_mib': used, 'total_mib': total, 'need_mib': need, 'prior_planned_mib': prior_planned, 'admit': ok})
        if not ok:
            save(launch_dir / 'admission_refused.json', {'log': log})
            print(json.dumps({'refused': j, 'log': log[-1]}))
            break
        cmd = [py, str(ROOT / 'report86_gen.py'), '--stage', j['stage'], '--system', j['system'], '--gpu', g, '--out', j['out'],
               '--shard', str(j['shard']), '--nshards', str(j['nshards'])] + (['--resume'] if j.get('resume') else []) + j.get('extra', [])
        so = (launch_dir / f'job{i}.stdout.log').open('x')
        se = (launch_dir / f'job{i}.stderr.log').open('x')
        e = dict(env)
        procs.append((i, j, subprocess.Popen(cmd, cwd=ROOT, env=e, stdout=so, stderr=se), time.monotonic(), cmd))
        time.sleep(a.stagger)
    rcs = {}
    # 완료 대기 중 GPU 점유를 주기적으로 기록한다.
    with (launch_dir / 'resource.jsonl').open('x') as rf:
        while any(p.poll() is None for _, _, p, _, _ in procs):
            rf.write(json.dumps({'t': time.time(), 'smi': smi()}) + '\n')
            rf.flush()
            time.sleep(30)
    for i, j, p, t0, cmd in procs:
        rcs[i] = p.returncode
    res = {'plan': a.plan, 'plan_sha256': sha(a.plan), 'admission': log, 'returncodes': rcs, 'cmds': {i: c for i, _, _, _, c in procs},
           'script_sha256': sha(__file__)}
    save(launch_dir / 'launch_result.json', res)
    print(json.dumps({'launch_dir': str(launch_dir), 'returncodes': rcs}))
    return 0 if all(v == 0 for v in rcs.values()) and len(rcs) == len(plan['jobs']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
