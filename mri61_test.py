"""iter_061 실행 경로 검사: 변조 차단, 중단(torn tail)·재개, 기술 gate 실패 시 nonzero. GPU 0 한 장 사용."""
import json, os, subprocess, sys, shutil
from mri61_run import read_jsonl

R = 'results/iter_061/tests'
os.makedirs(R, exist_ok=True)
D = read_jsonl('results/iter_061/D_requests.jsonl')
Dgen = {}
for f in ('worker0', 'worker1'):
    for r in read_jsonl(f'results/iter_061/gen_D_2w/{f}.jsonl'):
        Dgen[r['rid']] = r
# 짧은 입력 6개(단일 영상 S 조건 위주, 서로 다른 cluster)
pick, seen = [], set()
for r in D:
    if r['cond'].startswith('S') and r['order'] == 'F' and r['cluster_id'] not in seen and Dgen[r['rid']]['n_input_tokens'] < 600:
        pick.append(r); seen.add(r['cluster_id'])
pick = pick[:4] + [r for r in D if r['cond'] == 'J' and r['K'] == 3][:2]
req = f'{R}/mini_requests.jsonl'
with open(req, 'w') as f:
    for r in pick:
        f.write(json.dumps(r) + '\n')
out = {}


def run(args, **kw):
    return subprocess.run([sys.executable, 'mri61_run.py'] + args, capture_output=True, text=True, **kw)


assert run(['lock', '--requests', req, '--out', f'{R}/mini_protocol.json']).returncode == 0
env = dict(os.environ, CUDA_VISIBLE_DEVICES='0')
gdir = f'{R}/mini_gen'
if os.path.exists(gdir):
    sys.exit('mini_gen exists; use new path')
base = ['--requests', req, '--protocol', f'{R}/mini_protocol.json', '--out-dir', gdir]
# 1) 일부만 처리 후 torn tail 추가
r1 = subprocess.run([sys.executable, 'mri61_run.py', 'worker'] + base + ['--worker', '0', '--nworkers', '1', '--limit', '3'], env=env, capture_output=True, text=True)
n1 = len(read_jsonl(f'{gdir}/worker0.jsonl'))
with open(f'{gdir}/worker0.jsonl', 'a') as f:
    f.write('{"rid": "torn", "attem')
# 2) 재개
r2 = subprocess.run([sys.executable, 'mri61_run.py', 'worker'] + base + ['--worker', '0', '--nworkers', '1'], env=env, capture_output=True, text=True)
recs = read_jsonl(f'{gdir}/worker0.jsonl')
ids = [r['rid'] for r in recs]
same = {r['rid']: r['attempts'][-1]['suffix_ids'] == Dgen[r['rid']]['attempts'][-1]['suffix_ids'] for r in recs}
vr = run(['verify'] + base)
out['resume'] = {'rc_first': r1.returncode, 'n_after_first': n1, 'rc_resume': r2.returncode, 'n_final': len(recs),
                 'n_unique': len(set(ids)), 'expected': len(pick), 'only_missing_rerun': n1 == 3 and len(recs) == len(pick),
                 'torn_removed': all(r['rid'] != 'torn' for r in recs), 'token_identical_to_D': same,
                 'verify_rc': vr.returncode}
# 3) 변조 차단: requests 한 줄의 prompt 수정
bad = f'{R}/mini_requests_tampered.jsonl'
rows = read_jsonl(req)
rows[0]['prompt'] += ' '
open(bad, 'w').write('\n'.join(json.dumps(x) for x in rows) + '\n')
t = subprocess.run([sys.executable, 'mri61_run.py', 'worker', '--requests', bad, '--protocol', f'{R}/mini_protocol.json',
                    '--out-dir', f'{R}/mini_gen_tamper', '--worker', '0', '--nworkers', '1'], env=env, capture_output=True, text=True)
out['tamper_requests'] = {'rc': t.returncode, 'blocked': t.returncode != 0 and 'PROTOCOL MISMATCH' in (t.stdout + t.stderr)}
# 4) 기술 gate 실패 시 launch nonzero (GPU 사용 전에 종료)
bt = f'{R}/bad_tech.json'
json.dump({'fails': 3, 'requests_sha256': 'x'}, open(bt, 'w'))
g = run(['launch'] + base[:4] + ['--out-dir', f'{R}/mini_gen_gate', '--tech', bt, '--gpus', '0'])
out['tech_gate_fail'] = {'rc': g.returncode, 'blocked': g.returncode == 2 and not os.path.exists(f'{R}/mini_gen_gate')}
# 5) 누락 record verify 실패
shutil.copytree(gdir, f'{R}/mini_gen_missing')
lines = open(f'{R}/mini_gen_missing/worker0.jsonl').read().splitlines()[:-1]
open(f'{R}/mini_gen_missing/worker0.jsonl', 'w').write('\n'.join(lines) + '\n')
m = run(['verify', '--requests', req, '--protocol', f'{R}/mini_protocol.json', '--out-dir', f'{R}/mini_gen_missing'])
out['missing_detected'] = {'rc': m.returncode, 'blocked': m.returncode != 0}
out['pass'] = bool(out['resume']['only_missing_rerun'] and out['resume']['torn_removed'] and all(same.values()) and
                   out['resume']['verify_rc'] == 0 and out['tamper_requests']['blocked'] and out['tech_gate_fail']['blocked'] and
                   out['missing_detected']['blocked'])
json.dump(out, open(f'{R}/run_path_tests.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
sys.exit(0 if out['pass'] else 1)
