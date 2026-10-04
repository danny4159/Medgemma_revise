"""iter_070 launcher: seal inputs, shard eligible cases over workers (2 per GPU on GPUs 0,1), wait, record exit codes.

Usage: python ar70_launch.py <out_dir> [workers_per_gpu]
Cases are statically sharded (round-robin by sorted ID) so each case has exactly one owner; resume is by skipping
existing per-(case,cond) results inside ar70_run.py.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

PY = 'results/environments/autorg70/bin/python'
LABELS = 'results/iter_070/data/label_table.json'


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def main():
    out = sys.argv[1]
    wpg = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    os.makedirs(out, exist_ok=True)
    L = json.load(open(LABELS))
    cases = sorted(c for c, v in L['val'].items() if v['label'] != 'EXCLUDED')
    seal = {'labels': sha(LABELS), 'brats_manifest': sha('results/iter_070/data/brats_manifest.json'),
            'weights': sha('results/iter_070/models/weights_manifest.json'),
            'patch': sha('results/iter_070/external/patched/ar70_patch.diff'), 'run': sha('ar70_run.py'),
            'cases': cases, 'workers_per_gpu': wpg}
    sp = os.path.join(out, 'seal.json')
    if os.path.exists(sp):
        old = json.load(open(sp))
        assert {k: v for k, v in old.items() if k != 'workers_per_gpu'} == {k: v for k, v in seal.items() if k != 'workers_per_gpu'}, 'seal mismatch (resume with changed inputs)'
    else:
        json.dump(seal, open(sp, 'w'), indent=1)
    allowed = [x for x in os.environ.get('CUDA_VISIBLE_DEVICES', '0,1').split(',') if x != '']
    nw = wpg * len(allowed)
    shards = [cases[i::nw] for i in range(nw)]
    t0 = time.time()
    procs = []
    for i, sh in enumerate(shards):
        if not sh:
            continue
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=allowed[i % len(allowed)], PYTHONUNBUFFERED='1')
        os.makedirs(os.path.join(out, 'log'), exist_ok=True)
        f = open(os.path.join(out, 'log', f'worker{i}.log'), 'a')
        p = subprocess.Popen([PY, 'ar70_run.py', '--cases', ','.join(sh), '--out', out], stdout=f, stderr=subprocess.STDOUT, env=env)
        procs.append((i, allowed[i % len(allowed)], sh, p))
    rcs = {}
    peak = {}
    while any(p.poll() is None for _, _, _, p in procs):
        q = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
        for ln in q.strip().splitlines():
            gi, mu = [x.strip() for x in ln.split(',')]
            peak[gi] = max(peak.get(gi, 0), int(mu))
        time.sleep(3)
    for i, g, sh, p in procs:
        rcs[i] = {'physical_gpu': g, 'cases': sh, 'rc': p.wait()}
    json.dump({'wall_s': time.time() - t0, 'peak_gpu_used_MiB': peak, 'workers': rcs}, open(os.path.join(out, 'launch_result.json'), 'w'), indent=1)
    print(json.dumps({'wall_s': time.time() - t0, 'rcs': {i: v['rc'] for i, v in rcs.items()}}))


if __name__ == '__main__':
    main()
