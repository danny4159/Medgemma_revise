"""iter_071 작업 launcher: jobs.json의 각 job을 GPU slot에 배정해 subprocess로 실행하고 모두 끝날 때까지 기다린다.

jobs.json: {"gpus": [0,1], "per_gpu": 2, "jobs": [{"name":..., "cmd": [...argv after python...], "gpu": 0|null, "min_free_mib": 12000}]}
- gpu는 상속된 CUDA_VISIBLE_DEVICES(논리 index) 범위 안에서만 쓴다. job의 gpu가 null이면 여유 메모리가 큰 slot에 배정한다.
- 시작 직전 nvidia-smi로 실제 여유 메모리를 확인(min_free_mib 미만이면 대기). job별 stdout/stderr 로그와 rc를 launch_result.json에 기록한다.
- 이미 끝난 job의 완료 판정은 각 도구의 재개 검증에 맡긴다(존재만으로 skip하지 않음): 재실행해도 각 도구가 검증 후 no-op.
사용: python g71_launch.py jobs.json out_dir
"""
import json, os, subprocess, sys, time

jobs_path, out_dir = sys.argv[1], sys.argv[2]
spec = json.load(open(jobs_path))
os.makedirs(out_dir, exist_ok=True)
vis = os.environ.get('CUDA_VISIBLE_DEVICES')
allowed = [int(x) for x in vis.split(',')] if vis else [0, 1]


def free_mib():
    out = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.total,memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
    res = {}
    for ln in out.strip().splitlines():
        i, t, u = [int(x) for x in ln.split(',')]
        res[i] = t - u
    return res


gpus = [g for g in spec.get('gpus', allowed) if g in allowed]
per = spec.get('per_gpu', 1)
pending = list(spec['jobs'])
running = {}  # name -> (proc, gpu, t0, logfile)
results = {}
while pending or running:
    for n in list(running):
        p, g, t0, lf = running[n]
        if p.poll() is not None:
            lf.close()
            results[n] = {'rc': p.returncode, 'gpu': g, 'wall_s': time.time() - t0}
            del running[n]
            print('finished', n, results[n], flush=True)
    started = False
    for j in list(pending):
        cands = [j['gpu']] if j.get('gpu') is not None else gpus
        fm = free_mib()
        cands = [g for g in cands if sum(1 for v in running.values() if v[1] == g) < per and fm.get(g, 0) >= j.get('min_free_mib', 12000)]
        if not cands:
            continue
        g = max(cands, key=lambda x: fm.get(x, 0))
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), TORCH_HOME='results/environments/torch_home071')
        lf = open(os.path.join(out_dir, j['name'] + '.log'), 'a')
        p = subprocess.Popen([sys.executable] + j['cmd'], env=env, stdout=lf, stderr=subprocess.STDOUT)
        running[j['name']] = (p, g, time.time(), lf)
        pending.remove(j)
        print('started', j['name'], 'gpu', g, flush=True)
        started = True
        time.sleep(30)  # 모델 적재가 끝나 점유가 반영된 뒤 다음 job의 여유 메모리 확인
    if not started:
        time.sleep(10)
json.dump(results, open(os.path.join(out_dir, 'launch_result.json'), 'w'), indent=1)
bad = {k: v for k, v in results.items() if v['rc'] != 0}
print('done; failures:', bad, flush=True)
sys.exit(1 if bad else 0)
