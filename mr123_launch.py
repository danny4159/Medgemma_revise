"""iter_123: worker 감독. usage: python mr123_launch.py <stage> <max_new> <gpu_list e.g. 0,1,0,1> [--batch B] [--tag name]
worker 수는 GPU 수와 분리(같은 GPU에 복수 worker 가능). 상속 CUDA_VISIBLE_DEVICES 안의 장치만 허용.
"""
import json, os, subprocess, sys, time
import mr123_run as R

stage, mx, gpus = sys.argv[1], sys.argv[2], sys.argv[3].split(',')
batch = sys.argv[sys.argv.index('--batch') + 1] if '--batch' in sys.argv else '1'
tag = sys.argv[sys.argv.index('--tag') + 1] if '--tag' in sys.argv else 'main'
allowed = os.environ.get('CUDA_VISIBLE_DEVICES', '0,1').split(',')
assert all(g in allowed for g in gpus), (gpus, allowed)

def smi():
    o = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
    return {l.split(',')[0].strip(): (int(l.split(',')[1]), int(l.split(',')[2])) for l in o.strip().split('\n')}

# 시작 전 메모리 확인: worker당 예상 peak(MiB) + 2GiB 여유
PEAK = int(sys.argv[sys.argv.index('--peak') + 1]) if '--peak' in sys.argv else 16000
st = smi()
for g in set(gpus):
    n = gpus.count(g)
    used, tot = st[g]
    assert used + n * (PEAK + 2048) <= tot, f'GPU{g} 메모리 부족: used={used} workers={n}'
cd = R.GEN + stage + '/claims'
done = R.done_ids(stage)
if os.path.isdir(cd):
    for fn in os.listdir(cd):  # 실행 중 worker가 없으므로 미완료 claim 회수
        if fn.endswith('.claim') and fn[:-6] not in done:
            os.remove(os.path.join(cd, fn))
for fn in os.listdir(R.GEN + stage):  # 이전 강제 종료의 torn tail 복구 (실행 중 worker 없음)
    if fn.startswith('worker_') and fn.endswith('.jsonl'):
        R.repair_tail(os.path.join(R.GEN + stage, fn))
procs = []
t0 = time.time()
logd = R.GEN + stage + f'/logs_{tag}_{int(t0)}/'
os.makedirs(logd)
for i, g in enumerate(gpus):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=g)
    lf = open(logd + f'w{i}.log', 'w')
    procs.append((i, g, subprocess.Popen([sys.executable, 'mr123_run.py', 'worker', stage, f'{tag}{i}', mx, '--batch', batch], env=env, stdout=lf, stderr=subprocess.STDOUT)))
peak = {g: 0 for g in set(gpus)}
while any(p.poll() is None for _, _, p in procs):
    time.sleep(15)
    s = smi()
    for g in peak:
        peak[g] = max(peak[g], s[g][0])
rc = [p.returncode for _, _, p in procs]
res = dict(stage=stage, tag=tag, gpus=gpus, batch=batch, max_new=mx, wall_s=time.time() - t0, returncodes=rc, peak_gpu_mem_mib=peak,
           n_done=len(R.done_ids(stage)), n_req=len(R.read_jsonl(R.GEN + stage + '/requests.jsonl')))
json.dump(res, open(logd + 'launch_result.json', 'w'), indent=1)
print(json.dumps(res))
sys.exit(0 if all(c == 0 for c in rc) else 1)
