"""iter_077 메모리·재현성 probe (학습 의미 변경 없음; 진단 전용, 학습 없음).

iter_076 결정적 실행(set_deterministic: math SDPA만)은 allocated 21.5GiB·43초/step이었다. 어떤 SDPA backend 구성에서
(a) peak allocated/reserved (b) 같은 입력·초기 상태 두 번의 forward/backward gradient가 bit 단위로 같은지를 측정한다.
구성: nondet_default(기본), det_math(현 --deterministic), det_flag_only(use_deterministic_algorithms만, SDPA backend 기본), det_efficient(math 끄고 efficient/flash 허용)
사용: python sp77_sdpa_probe.py --out results/iter_077/tests/sdpa_probe.json --gpu 0
"""
import argparse, hashlib, json, os, sys, time

import sp75_data as D
import sp75_vlm as V
from rsna_diag import generate, lora
from rsna_diag import train as T


def grad_digest(torch, params):
    h = hashlib.sha256()
    for p in params:
        h.update(p.grad.detach().float().cpu().numpy().tobytes())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--gpu', required=True)
    a = ap.parse_args()
    inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    if a.gpu not in inh:
        sys.exit(f'gpu {a.gpu} not in inherited {inh}')
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    if os.path.exists(a.out):
        sys.exit('exists')
    import torch
    T.seed_all(torch, 17)
    man = D.load_manifest()
    rows = sorted([r for r in man['rows'] if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))[:2]
    _, proc, model = generate.load_model()
    lora.apply_lora(model, 16, 32, 0.0, seed=17)   # dropout 0: 이 probe는 backend 간 수치 재현만 본다
    params = list(lora.lora_params(model).values())
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    model.train()
    batches = [V.to_cuda(V.collate([V.build_example(proc, V.load_images(r['inputs']['F']), V.PROMPTS['F'], str(r['grade']))], proc.tokenizer.pad_token_id)) for r in rows]
    res = {'attn_implementation': getattr(model.config, '_attn_implementation', None), 'gpu_logical': a.gpu, 'configs': {}}

    def setcfg(name):
        be = torch.backends.cuda
        torch.use_deterministic_algorithms(name.startswith('det'))
        be.enable_flash_sdp(True); be.enable_mem_efficient_sdp(True); be.enable_math_sdp(True)
        if name == 'det_math':
            be.enable_flash_sdp(False); be.enable_mem_efficient_sdp(False)
        if name == 'det_efficient':
            be.enable_math_sdp(False)

    for name in ('nondet_default', 'det_flag_only', 'det_efficient', 'det_math'):
        entry = {}
        try:
            setcfg(name)
            digs, losses, ts = [], [], []
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            for rep in range(2):
                for p in params:
                    p.grad = None
                t0 = time.time()
                tot = 0.0
                for b in batches:
                    ls, n = V.loss_sum(torch, model, b)
                    (ls / (2 * len(batches))).backward()
                    tot += float(ls) / n
                torch.cuda.synchronize()
                ts.append(time.time() - t0)
                losses.append(tot)
                digs.append(grad_digest(torch, params))
            entry = {'grad_digest_rep': digs, 'repeat_bitwise_equal': digs[0] == digs[1], 'losses': losses, 'sec_per_2ex_fwd_bwd': ts,
                     'peak_allocated_gib': torch.cuda.max_memory_allocated() / 2 ** 30, 'peak_reserved_gib': torch.cuda.max_memory_reserved() / 2 ** 30}
        except Exception as ex:
            entry = {'error': repr(ex)[:400]}
        res['configs'][name] = entry
        print(name, json.dumps(entry), flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + '.tmp'
    json.dump(res, open(tmp, 'w'), indent=1)
    os.replace(tmp, a.out)


if __name__ == '__main__':
    main()
