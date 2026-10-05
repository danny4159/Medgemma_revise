"""iter_076 복구 manifest: 기준 계획 hash, 코드 HEAD, 호스트 프로세스·GPU 상태, iter_075 보존 산출물의 sha256과 lock 소유권을 기록한다.
원본(iter_075)은 읽기만 한다. 결과: results/iter_076/recovery_manifest.json (존재하면 중단).
"""
import hashlib, json, os, subprocess, sys, time

OUT = 'results/iter_076/recovery_manifest.json'
BASE_PLAN = '../agent/runs/iter_075/plan.md'
BASE_PLAN_SHA = 'ea40768f17ae65b10f0027ca9ca9423205bb106198ebf891af7ec0bf17a73b8b'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def procs():
    out = []
    for p in os.listdir('/proc'):
        if p.isdigit():
            try:
                cmd = open(f'/proc/{p}/cmdline', 'rb').read().replace(b'\0', b' ').decode()[:200]
                st = open(f'/proc/{p}/stat').read().split()
            except Exception:
                continue
            if any(k in cmd for k in ('sp75_', 'sp76_', 'rsna_diag')):
                out.append({'pid': int(p), 'cmd': cmd, 'start_ticks': st[21]})
    return out


def main():
    if os.path.exists(OUT):
        sys.exit('exists')
    res = {'ts': time.time(), 'base_plan': BASE_PLAN, 'base_plan_sha256_expected': BASE_PLAN_SHA, 'base_plan_sha256_actual': sha(BASE_PLAN)}
    res['base_plan_matches'] = res['base_plan_sha256_actual'] == BASE_PLAN_SHA
    res['git_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    res['git_status_short'] = subprocess.check_output(['git', 'status', '--short']).decode().splitlines()
    res['host_related_processes'] = procs()
    res['nvidia_compute_apps'] = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_memory,gpu_uuid', '--format=csv,noheader'], capture_output=True, text=True).stdout.strip().splitlines()
    res['nvidia_gpus'] = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.total', '--format=csv,noheader'], capture_output=True, text=True).stdout.strip().splitlines()
    res['cuda_visible_devices'] = os.environ.get('CUDA_VISIBLE_DEVICES')
    keep = {}
    base = 'results/iter_075'
    for root, _, files in os.walk(base):
        for f in files:
            p = os.path.join(root, f)
            if f.endswith('.lock'):
                keep[p] = {'lock_file_present': True, 'content': open(p).read()[:300]}
            elif any(x in p for x in ('/tests/resume/', '/tests/tech_', '/C/selection', '/H/selection', '/data/manifest', 'env_record', 'fixtures_cpu')) and os.path.getsize(p) < (2 << 30):
                keep[p] = {'sha256': sha(p), 'bytes': os.path.getsize(p)}
    res['iter_075_preserved_files'] = keep
    res['iter_075_missing_expected'] = [p for p in ('results/iter_075/tests/resume/ref/epoch_02/val_ce.json', 'results/iter_075/tests/resume/A/epoch_02/val_ce.json',
                                                    'results/iter_075/tests/resume/B') if not os.path.exists(p)]
    res['decision'] = ('iter_075 ref/A 2-epoch 검사 trajectory는 코드 변경(train_digest에 code hash 포함)과 step2부터의 수치 차이 때문에 재개 대상으로 사용하지 않고 원본 그대로 보존한다. '
                       '재개 검사는 새 코드·결정적 설정으로 results/iter_076/tests/resume에서 처음부터 수행한다.')
    json.dump(res, open(OUT, 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('base_plan_matches', 'git_head', 'host_related_processes', 'nvidia_compute_apps', 'iter_075_missing_expected')}, indent=1))


if __name__ == '__main__':
    main()
