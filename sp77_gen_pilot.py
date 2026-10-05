"""iter_077 생성 worker 구성 pilot: 같은 V8 요청(F lr2e-4 epoch16 adapter)을 GPU0에서 worker 2개(claim 분할)로 실행해 기존 1-worker 출력과
suffix token·후보 log-likelihood가 같은지, 처리 시간·peak 점유를 기록한다. 결과: results/iter_077/tests/gen_2w_F.json (존재하면 중단)."""
import glob, json, os, subprocess, sys, time

AD = 'results/iter_077/train/F_lr2e-4/epoch_16'
OUT = 'results/iter_077/tests/gen_2w_F'
REF = 'results/iter_077/gen/V8/F_lr2e-4_ep16'
RES = 'results/iter_077/tests/gen_2w_F.json'


def load(d):
    x = {}
    for f in glob.glob(d + '/gen_worker*.jsonl'):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                assert r['id'] not in x
                x[r['id']] = r
    return x


def main():
    if os.path.exists(RES):
        sys.exit('exists')
    t0 = time.time()
    ps = [subprocess.Popen([sys.executable, 'sp75_gen.py', '--variant', 'F', '--split', 'V8', '--positions', 'supervised', '--adapter', AD, '--out-dir', OUT, '--worker', str(k), '--gpu', '0'],
                           stdout=open(f'{OUT}.w{k}.log', 'w'), stderr=subprocess.STDOUT) for k in (0, 1)]
    peak = 0
    while any(p.poll() is None for p in ps):
        used = int(subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits', '-i', '0']).decode().strip())
        peak = max(peak, used)
        time.sleep(3)
    rc = [p.returncode for p in ps]
    a, b = load(OUT), load(REF)
    res = {'rc': rc, 'wall_s': time.time() - t0, 'peak_gpu0_used_mib': peak, 'n_new': len(a), 'n_ref': len(b), 'same_id_set': set(a) == set(b),
           'suffix_ids_equal_all': set(a) == set(b) and all(a[k]['suffix_ids'] == b[k]['suffix_ids'] for k in b),
           'max_abs_cand_loglik_diff': max(max(abs(x - y) for x, y in zip(a[k]['cand_loglik'], b[k]['cand_loglik'])) for k in b) if set(a) == set(b) else None,
           'workers_used': sorted({r['worker'] for r in a.values()}), 'ref_runtime_sum_s': sum(r['runtime_s'] for r in b.values()), 'new_runtime_sum_s': sum(r['runtime_s'] for r in a.values())}
    json.dump(res, open(RES, 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
