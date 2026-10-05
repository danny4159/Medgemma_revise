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


def _tensor_bytes(t):
    t = t.detach().to("cpu").contiguous()
    if t.dtype == torch.bfloat16:
        return t.view(torch.int16).numpy().tobytes()
    return t.view(torch.uint8).numpy().tobytes()


def split_report(model, optimizer_params=None):
    """LoRA / 비LoRA parameter를 객체 단위로 분리해 개수·numel·byte를 센다 (iter_076 동결 검사).

    분리 기준은 'lora_' 이름의 parameter 객체와 나머지이다. 정규화 이름 충돌, 빈 집합(수·numel·byte 0)은 예외.
    optimizer_params: optimizer에 들어간 parameter 목록(있으면 비LoRA 포함 여부 검사).
    """
    lo, non = {}, {}
    for n, p in model.named_parameters():
        (lo if "lora_" in n else non)[n] = p
    norm = [n.replace(".base.", ".") for n in non]
    if len(set(norm)) != len(norm):
        raise RuntimeError("normalized non-LoRA parameter names collide")
    rep = {"n_lora": len(lo), "n_non_lora": len(non), "numel_lora": sum(p.numel() for p in lo.values()), "numel_non_lora": sum(p.numel() for p in non.values()),
           "bytes_lora": sum(p.numel() * p.element_size() for p in lo.values()), "bytes_non_lora": sum(p.numel() * p.element_size() for p in non.values()),
           "non_lora_requires_grad": sum(1 for p in non.values() if p.requires_grad), "lora_requires_grad_false": sum(1 for p in lo.values() if not p.requires_grad),
           "non_lora_dtypes": sorted({str(p.dtype) for p in non.values()}), "lora_dtypes": sorted({str(p.dtype) for p in lo.values()})}
    for k in ("n_lora", "n_non_lora", "numel_lora", "numel_non_lora", "bytes_lora", "bytes_non_lora"):
        if rep[k] <= 0:
            raise RuntimeError(f"empty parameter set: {k}=0")
    if optimizer_params is not None:
        ids = {id(p) for p in optimizer_params}
        rep["optimizer_contains_non_lora"] = sum(1 for p in non.values() if id(p) in ids)
        rep["optimizer_lora_covered"] = all(id(p) in ids for p in lo.values())
        rep["optimizer_n_params"] = len(ids)
    return rep


def exact_digest(model, lora=False):
    """정확한 parameter 이름·dtype·shape·byte 전체의 sha256 (정규화 없음). lora=False면 비LoRA만. 빈 집합이면 예외. returns (hexdigest, n_params, n_bytes)."""
    h = hashlib.sha256()
    n_par = n_bytes = 0
    for n, p in sorted(model.named_parameters(), key=lambda x: x[0]):
        if ("lora_" in n) != lora:
            continue
        b = _tensor_bytes(p)
        h.update(f"{n}|{p.dtype}|{tuple(p.shape)}|{len(b)}".encode())
        h.update(b)
        n_par += 1
        n_bytes += len(b)
    if n_par == 0 or n_bytes == 0:
        raise RuntimeError("exact_digest over an empty parameter set")
    return h.hexdigest(), n_par, n_bytes
