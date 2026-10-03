"""iter_062 GPU 재개 검사: D3에서 worker를 SIGKILL로 강제 중단 + 손상 tail 주입 → launcher 재시작 → 중복/누락 0, 기준 실행과 token 일치.
결과: results/iter_062/tests/resume_test.json
"""
import glob, json, os, signal, subprocess, sys, time
import q62_run as Q

D = 'results/iter_062/gen_D3_resume'
REQ, LAB, PROT = 'results/iter_062/data/D3_requests.jsonl', 'results/iter_062/data/D3_labels.json', 'results/iter_062/D3_protocol.json'
assert not os.path.exists(D)
os.makedirs(D)
env = dict(os.environ, CUDA_VISIBLE_DEVICES='0')
p = subprocess.Popen([sys.executable, 'q62_run.py', 'worker', '--requests', REQ, '--labels', LAB, '--protocol', PROT,
                      '--out-dir', D, '--worker', '0'], env=env, stdout=open(f'{D}/worker0.stdout.log', 'a'), stderr=subprocess.STDOUT)
t0 = time.time()
while time.time() - t0 < 300:
    n = len(Q.read_jsonl(f'{D}/worker0.jsonl'))
    if n >= 8:
        break
    time.sleep(0.5)
p.send_signal(signal.SIGKILL)
p.wait()
n_before = len(Q.read_jsonl(f'{D}/worker0.jsonl'))
with open(f'{D}/worker0.jsonl', 'a') as f:
    f.write('{"rid": "torn", "attempts": [')  # 손상된 tail
claims = len(glob.glob(f'{D}/claims/*.claim'))
# worker 수 변경(1→2)으로 재개
r = subprocess.run([sys.executable, 'q62_run.py', 'launch', '--requests', REQ, '--labels', LAB, '--protocol', PROT,
                    '--tech', 'results/iter_062/D3_tech.json', '--gpus', '0,1', '--workers-per-gpu', '1', '--out-dir', D],
                   capture_output=True, text=True)
v = subprocess.run([sys.executable, 'q62_run.py', 'verify', '--requests', REQ, '--labels', LAB, '--protocol', PROT, '--out-dir', D],
                   capture_output=True, text=True)


def recs(d):
    o = {}
    for f in glob.glob(f'{d}/worker[0-9].jsonl'):
        for x in Q.read_jsonl(f):
            assert x['rid'] not in o
            o[x['rid']] = x
    return o


A, B = recs('results/iter_062/gen_D3_qwen'), recs(D)
mism = [k for k in A if A[k]['attempts'][-1]['suffix_ids'] != B[k]['attempts'][-1]['suffix_ids']]
res = {'records_before_kill': n_before, 'stale_claims_after_kill': claims, 'launch_rc': r.returncode, 'verify_rc': v.returncode,
       'n_records_final': len(B), 'duplicates': 0, 'missing': len(set(A) - set(B)),
       'corrupt_copies': [os.path.basename(f) for f in glob.glob(f'{D}/worker0.jsonl.corrupt_*')],
       'suffix_token_mismatch_vs_baseline': len(mism), 'n_compared': len(A),
       'resumed_workers': 2, 'baseline_workers': 2}
res['pass'] = (res['launch_rc'] == 0 and res['verify_rc'] == 0 and res['n_records_final'] == 34 and res['missing'] == 0
               and len(res['corrupt_copies']) == 1 and n_before < 34)
json.dump(res, open('results/iter_062/tests/resume_test.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
print(r.stdout[-300:], r.stderr[-300:], v.stdout[-300:], v.stderr[-300:])
