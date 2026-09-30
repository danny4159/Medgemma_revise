"""표준 LoRA (peft 미설치·설치 금지). y = W x + (alpha/r) B A x. 언어모델 attention/MLP 선형층만 (iter_010).

- A: kaiming_uniform(a=sqrt(5)) (loralib 표준), B: 0 -> 초기 항등. base weight는 동결·불변.
- LoRA 파라미터는 fp32 master, 연산은 fp32 후 base 출력 dtype으로 cast해 더한다.
"""
import hashlib
import math

import torch
import torch.nn as nn

TARGET_SUFFIXES = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")
LM_LAYER_PREFIX = "model.language_model.layers."


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Linear, r=16, alpha=32, dropout=0.05):
        super().__init__()
        self.base, self.r, self.alpha, self.scaling = base, r, alpha, alpha / r
        dev = base.weight.device
        self.lora_A = nn.Parameter(torch.empty(r, base.in_features, dtype=torch.float32, device=dev))
        self.lora_B = nn.Parameter(torch.zeros(base.out_features, r, dtype=torch.float32, device=dev))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        y = self.base(x)
        z = (self.drop(x).to(torch.float32) @ self.lora_A.t()) @ self.lora_B.t() * self.scaling
        return y + z.to(y.dtype)


def apply_lora(model, r=16, alpha=32, dropout=0.05, seed=None):
    """LM layer의 대상 선형층을 LoRALinear로 교체하고 다른 모든 파라미터를 동결한다. returns 교체한 모듈 이름 목록."""
    if seed is not None:
        torch.manual_seed(seed)
    for p in model.parameters():
        p.requires_grad_(False)
    names = []
    for name, mod in list(model.named_modules()):
        if name.startswith(LM_LAYER_PREFIX) and name.rsplit(".", 1)[-1] in TARGET_SUFFIXES and isinstance(mod, nn.Linear):
            parent = model.get_submodule(name.rsplit(".", 1)[0])
            setattr(parent, name.rsplit(".", 1)[1], LoRALinear(mod, r, alpha, dropout))
            names.append(name)
    if not names:
        raise RuntimeError("no LoRA target modules found")
    return names


def lora_params(model):
    return {n: p for n, p in model.named_parameters() if p.requires_grad}


def lora_state_dict(model):
    return {n: p.detach().to("cpu", torch.float32).clone() for n, p in model.named_parameters() if "lora_" in n}


def load_lora_state(model, state, strict=True):
    own = {n: p for n, p in model.named_parameters() if "lora_" in n}
    if strict and set(own) != set(state):
        raise ValueError(f"lora keys mismatch: missing {sorted(set(own) - set(state))[:3]} extra {sorted(set(state) - set(own))[:3]}")
    with torch.no_grad():
        for n, p in own.items():
            p.copy_(state[n].to(p.device, p.dtype))


def state_digest(state):
    h = hashlib.sha256()
    for n in sorted(state):
        t = state[n].detach().to("cpu", torch.float32).contiguous()
        h.update(n.encode())
        h.update(str(tuple(t.shape)).encode())
        h.update(t.numpy().tobytes())
    return h.hexdigest()


def base_digest(model):
    """LoRA를 제외한 모든 파라미터의 (이름, shape, 첫/마지막 1M 원소 합 등이 아닌) 전체 hash. 동결 검증용 (느리지만 정확)."""
    h = hashlib.sha256()
    for n, p in model.named_parameters():
        if "lora_" in n:
            continue
        h.update(n.replace(".base.", ".").encode())  # LoRA 적용 전후 이름을 같게 정규화
        h.update(p.detach().to("cpu").contiguous().view(torch.uint8).numpy().tobytes() if p.dtype != torch.bfloat16
                 else p.detach().to("cpu").contiguous().view(torch.int16).numpy().tobytes())
    return h.hexdigest()
