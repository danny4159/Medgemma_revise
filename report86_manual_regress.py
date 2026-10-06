"""수동 RSNA 판독 관찰(base.jsonl/sft.jsonl)의 원 token 회귀: 원 코드 경로(G.run_request)·원 protocol(caps 512/1024, seed 42)로
현재 환경에서 일부 행을 재생성해 suffix token과 input_ids를 원본과 비교한다. 수동 원본 파일은 읽기만 한다.
python report86_manual_regress.py all <n_per_model>     # base는 GPU 0, sft는 GPU 1에서 동시에 실행
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from report86_common import ROOT, UP, R86, isolated_env, save, sha, sha_obj

MAN = ROOT / 'results/manual_rsna_report_transfer_20261006'
OUT = R86 / 'manual_regress'


def worker(model_name, gpu, n, ids_override=None, tag=''):
    os.environ['CUDA_VISIBLE_DEVICES'] = gpu
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    from rsna_diag import generate as G
    torch.set_num_threads(4)
    torch.manual_seed(42)
    protocol = json.loads((MAN / 'protocol.json').read_text())
    orig = {r['id']: r for r in map(json.loads, (MAN / f'{model_name}.jsonl').read_text().splitlines())}
    ids = ids_override or sorted(orig, key=lambda i: sha_obj(['manual-regress86', i]))[:n]
    wanted = {r['id']: r for r in protocol['rows']}
    snap = UP / 'hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots' / G.MODEL_REVISION
    proc = AutoProcessor.from_pretrained(str(snap), local_files_only=True)
    proc.image_processor.do_pan_and_scan = False
    model = AutoModelForImageTextToText.from_pretrained(str(snap), local_files_only=True, dtype=torch.bfloat16, device_map='cuda', attn_implementation='sdpa')
    adapter = G.load_adapter(torch, model, protocol['adapter']) if model_name == 'sft' else None
    if model_name == 'sft':
        assert adapter == protocol['adapter_expected_digest']
    model.eval()
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    items = []
    for i in ids:
        row = wanted[i]
        assert sha(row['image']) == row['file_sha256']
        rec = G.run_request(torch, proc, model, eos, row, 'free_report', protocol['prompt'], caps=protocol['caps'])
        o = orig[i]
        items.append({'id': i, 'tokens_equal': rec['suffix_ids'] == o['suffix_ids'], 'input_ids_equal': rec['input_ids'] == o['input_ids'],
                      'n_new_old': len(o['suffix_ids']), 'n_new_new': len(rec['suffix_ids']), 'ended_eos_old': o['ended_eos'], 'ended_eos_new': rec['ended_eos']})
        print(json.dumps(items[-1]), flush=True)
    save(OUT / f'{model_name}{tag}_result.json', {'model': model_name, 'gpu': gpu, 'n': len(items), 'n_tokens_equal': sum(x['tokens_equal'] for x in items),
                                             'n_input_ids_equal': sum(x['input_ids_equal'] for x in items), 'items': items, 'torch': torch.__version__,
                                             'adapter_digest': adapter, 'orig_file_sha256': sha(MAN / f'{model_name}.jsonl'),
                                             'protocol_sha256': sha(MAN / 'protocol.json'), 'code_sha256': {f: sha(ROOT / f) for f in ['rsna_diag/generate.py', 'rsna_diag/lora.py']}})


def main():
    if sys.argv[1] == 'all':
        n = sys.argv[2]
        OUT.mkdir(parents=True, exist_ok=False)
        procs = []
        for model_name, gpu in (('base', '0'), ('sft', '1')):
            lg = (OUT / f'{model_name}.log').open('x')
            procs.append(subprocess.Popen([sys.executable, __file__, 'worker', model_name, gpu, n], cwd=ROOT, env=isolated_env(), stdout=lg, stderr=subprocess.STDOUT))
        rcs = [p.wait() for p in procs]
        print(json.dumps({'returncodes': rcs}))
    else:
        worker(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5].split(',') if len(sys.argv) > 5 else None, sys.argv[6] if len(sys.argv) > 6 else '')


if __name__ == '__main__':
    main()
