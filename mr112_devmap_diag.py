"""iter_112: 8-bit 적재 device_map 진단 (meta device, GPU/가중치 미사용). 모듈별 int8/bf16 크기와 auto device_map 결과를 기록."""
import json
import sys

import torch
from accelerate import infer_auto_device_map, init_empty_weights
from accelerate.utils import get_balanced_memory

import mr112_model as MM

MM.ensure_weight_dir()
from internvl.model.internvl_chat import InternVLChatConfig, InternVLChatModel

cfg = InternVLChatConfig.from_pretrained(MM.WDIR)
cfg.llm_config._attn_implementation_internal = "sdpa"
with init_empty_weights():
    m = InternVLChatModel(cfg)
tot = sum(p.numel() for p in m.parameters())
print("params B", tot / 1e9)
sizes = {}
for n, c in m.named_children():
    sizes[n] = sum(p.numel() for p in c.parameters())
print({k: round(v / 1e9, 3) for k, v in sizes.items()})
lm = m.language_model.base_model.model
print("embed+lm_head B", (lm.model.embed_tokens.weight.numel() + lm.lm_head.weight.numel()) / 1e9)
for mem in (22, 23):
    mm = {0: f"{mem}GiB", 1: f"{mem}GiB"}
    dm = infer_auto_device_map(m, max_memory=mm, no_split_module_classes=m._no_split_modules, dtype=torch.int8)
    cpu = [k for k, v in dm.items() if v in ("cpu", "disk")]
    print(mem, "GiB: n_cpu_disk", len(cpu), cpu[:6])
    mb = get_balanced_memory(m, max_memory=mm, no_split_module_classes=m._no_split_modules, dtype=torch.int8, low_zero=False)
    print("  balanced", mb)
