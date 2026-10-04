"""paired 비용 block 실행기. 사용: python g71_costrun.py OUT_ROOT BLOCK_IDS(예: 1,3) ORDER_PARITY
각 block은 같은 GPU(현재 프로세스의 CUDA_VISIBLE_DEVICES)에서 vlm과 det를 순서를 번갈아(홀수 block: vlm->det, 짝수 block: det->vlm) 한 프로세스씩 실행한다."""
import json, os, subprocess, sys

root, blocks = sys.argv[1], [int(x) for x in sys.argv[2].split(',')]
lock = json.load(open('results/iter_071/decide/e24_lock.json'))
adapter = lock['vlm']['D']['adapter_dir']  # 최종 VLM: V8에서 선택된 D8 (사전 선택, E24 결과와 무관)
for b in blocks:
    order = ['vlm', 'det'] if b % 2 == 1 else ['det', 'vlm']
    for s in order:
        out = f'{root}/block{b}_{s}'
        if os.path.exists(f'{out}/timing.json'):
            continue
        cmd = [sys.executable, 'g71_cost.py', s, out] + (['--adapter', adapter] if s == 'vlm' else ['--ckpt', lock['detector']['ckpt'], '--thr', str(lock['detector']['threshold'])])
        r = subprocess.run(cmd, capture_output=True, text=True)
        open(f'{out}.log', 'w').write(r.stdout[-3000:] + r.stderr[-3000:])
        if r.returncode != 0:
            sys.exit(f'block {b} {s} failed rc={r.returncode}')
        print('done', b, s, flush=True)
