"""launcher용 jobs.json 생성기. 사용: python g71_jobs.py gen OUT_JSON KEY GENROOT SPEC [SPEC...] [--per-gpu 2]
SPEC = label=adapter_dir | label=base. 각 spec은 results/iter_071/gen/<GENROOT>/<label>/에 worker 1개로 기록된다(요청 수가 작아 spec 단위 병렬)."""
import json, sys

args = sys.argv[1:]
mode = args[0]
if mode == 'gen':
    out, key, root = args[1], args[2], args[3]
    per = 2
    specs = []
    i = 4
    while i < len(args):
        if args[i] == '--per-gpu':
            per = int(args[i + 1]); i += 2
            continue
        specs.append(args[i]); i += 1
    jobs = []
    for s in specs:
        label, ad = s.split('=', 1)
        cmd = ['g71_gen.py', '--key', key, '--out-dir', f'results/iter_071/gen/{root}/{label}', '--worker', '0', '--nworkers', '1']
        if ad != 'base':
            cmd += ['--adapter', ad]
        jobs.append({'name': f'{root}_{label}', 'cmd': cmd, 'min_free_mib': 12500})
    json.dump({'gpus': [0, 1], 'per_gpu': per, 'jobs': jobs}, open(out, 'w'), indent=1)
    print(len(jobs), 'jobs ->', out)
