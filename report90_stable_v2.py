"""비영 LoRA A/B 경로까지 고정 행 연산을 적용한다. 가중치·loss는 그대로다."""
import types
import torch
from report90_stable import apply as base_apply
from rsna_diag.lora import LoRALinear

def apply(model,chunk=64):
    names=base_apply(model,chunk)
    def forward(self,x):
        y=self.base(x);v=self.drop(x).to(torch.float32);flat=v.reshape(-1,v.shape[-1]);parts=[]
        for start in range(0,len(flat),chunk):
            a=flat[start:start+chunk];n=len(a)
            if n<chunk:a=torch.nn.functional.pad(a,(0,0,0,chunk-n))
            parts.append(((a@self.lora_A.t())@self.lora_B.t())[:n]*self.scaling)
        z=torch.cat(parts,0).reshape(*x.shape[:-1],self.base.out_features)
        return y+z.to(y.dtype)
    for name,module in model.named_modules():
        if isinstance(module,LoRALinear):module.forward=types.MethodType(forward,module);names.append(name)
    return names
