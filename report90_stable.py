"""길이와 무관한 고정 행 수 GEMM 대조. 가중치·loss·attention 의미는 유지한다."""
import types
import torch
import report90_numeric as N
from report86_common import save,sha

def apply(model,chunk=64):
    def forward(self,x):
        shape=x.shape;flat=x.reshape(-1,shape[-1]);parts=[]
        for start in range(0,len(flat),chunk):
            v=flat[start:start+chunk];n=len(v)
            if n<chunk:v=torch.nn.functional.pad(v,(0,0,0,chunk-n))
            parts.append(torch.nn.functional.linear(v,self.weight,self.bias)[:n])
        return torch.cat(parts,0).reshape(*shape[:-1],self.out_features)
    names=[]
    for name,module in model.named_modules():
        if isinstance(module,torch.nn.Linear) and ('language_model' in name or name=='lm_head'):
            module.forward=types.MethodType(forward,module);names.append(name)
    return names

if __name__=='__main__':
    original=N.M.load
    def load():
        torch,proc,model=original();names=apply(model)
        save(N.OUT/'tech/stable_linear/patch_protocol.json',dict(source_sha256=sha(__file__),chunk=64,patched=names,
            reason='첫 query projection의 행 수 의존 반올림을 고정 GEMM shape로 통제; FP64보다 저비용 후보',training_authorized=False))
        return torch,proc,model
    N.M.load=load;N.main()
