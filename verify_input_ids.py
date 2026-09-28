import glob
import json

from rsna_diag import generate as G, risk28, prompts as PR

torch, proc, model = G.load_model()
del model
torch.cuda.empty_cache()

recs = []
for f in glob.glob('results/iter_012/train/lr2e-4_s17/epoch_05/val_gen/gen_worker*.jsonl'):
    for ln in open(f):
        r = json.loads(ln)
        if r['prompt_name'] == 'concise':
            recs.append(r)
recs = sorted(recs, key=lambda r: r['id'])[:20]

n_match, n_total = 0, 0
for r in recs:
    image, aff, px = G.load_image(r['image'])
    inp = risk28.build_image_inputs(proc, image, PR.CONCISE)
    ids = inp['input_ids'][0].tolist()
    n_total += 1
    if ids == r['input_ids']:
        n_match += 1
    else:
        print('MISMATCH', r['id'], 'len stored', len(r['input_ids']), 'len rebuilt', len(ids))
    assert 'pixel_values' in inp

print(f'{n_match}/{n_total} input_ids exact match against stored records')
