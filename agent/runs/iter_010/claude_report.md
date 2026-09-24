학습과 생성이 백그라운드에서 진행 중입니다. epoch 1 결과 알림이 오면 이어서 진행합니다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
import os
os.environ["HF_HOME"]="/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache"; os.environ["HF_HUB_OFFLINE"]="1"
import transformers, numpy as np
from PIL import Image
M="google/medgemma-1.5-4b-it"; R="91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"
proc=transformers.AutoProcessor.from_pretrained(M,revision=R)
img=Image.fromarray(np.zeros((896,896,3),np.uint8))
def msgs(a=None):
    m=[{"role":"user","content":[{"type":"image","image":img},{"type":"text","text":"hello"}]}]
    if a is not None: m.append({"role":"assistant","content":[{"type":"text","text":a}]})
    return m
g=proc.apply_chat_template(msgs(),add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors="pt")
f=proc.apply_chat_template(msgs('[]'),add_generation_prompt=False,tokenize=True,return_dict=True,return_tensors="pt")
print({k:(v.shape,v.dtype) for k,v in g.items()})
print({k:(v.shape,v.dtype) for k,v in f.items()})
gi=g["input_ids"][0].tolist(); fi=f["input_ids"][0].tolist()
print(len(gi),len(fi),fi[:len(gi)]==gi, proc.tokenizer.convert_ids_to_tokens(fi[len(gi)-3:]), proc.tokenizer.padding_side)
print(proc.tokenizer.convert_ids_to_tokens(gi[:6]), proc.tokenizer.convert_ids_to_tokens(gi[-8:]))
EOF
- Bash: CUDA_VISIBLE_DEVICES=0 python -m rsna_diag.train --run-dir results/iter_010/pilot/mb1 --lr 2e-4 --seed 17 --epochs 12 --protocol results/iter_010/protocols/pilot_protocol.json --train-ids results/iter_010/manifests/pilot16_ids.json --no-val --eff-batch 4 --microbatch 1 --ckpt-every 10 > results/iter_010/pilot_mb1.log 2>&1
- Bash: CUDA_VISIBLE_DEVICES=1 python -m rsna_diag.train --run-dir results/iter_010/pilot/mb2 --lr 2e-4 --seed 17 --epochs 12 --protocol results/iter_010/protocols/pilot_protocol.json --train-ids results/iter_010/manifests/pilot16_ids.json --no-val --eff-batch 4 --microbatch 2 --ckpt-every 10 > results/iter_010/pilot_mb2.log 2>&1
- Bash: python - <<'PYEOF'
import json,glob
from rsna_diag import baselines
gt=json.load(open('results/iter_009/manifests/gt_manifest.json'))
dev=sorted(i for i in gt if gt[i]['split']=='development')
recs=baselines.load_iter9_records(set(dev))
n={i:recs[(i,'official_long')]['n_output_tokens']+recs[(i,'concise')]['n_output_tokens'] for i in dev}
o=sorted(dev,key=lambda i:n[i])
ids=o[:12]+o[-12:]
print(len(ids),[n[i] for i in ids])
json.dump(sorted(ids),open('results/iter_010/pilot/thr24_ids.json','w'))
PYEOF
- WebFetch: https://github.com/DebeshJha/Kvasir-SEG
