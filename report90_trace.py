"""첫 decoder block의 길이별 수치 차이를 모듈·attention 입력별로 추적한다."""
import argparse
import json
import torch
from report90_numeric import OUT,environment
import report89_model as M
from rsna_diag import train as T
from report86_common import save,sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--fp32-linear',action='store_true');a=ap.parse_args()
    out=OUT/('tech/first_layer_trace_fp32' if a.fp32_linear else 'tech/first_layer_trace');out.mkdir(parents=True,exist_ok=False)
    mapping=environment(a.gpu)
    save(out/'protocol.json',dict(mapping=mapping,source={f:sha(f) for f in ['report90_trace.py','report90_numeric.py','report89_model.py']}))
    _,proc,model=M.load();T.set_deterministic(torch);model.eval()
    if a.fp32_linear:
        import types
        def linear(self,x):return torch.nn.functional.linear(x.float(),self.weight.float(),None if self.bias is None else self.bias.float()).to(x.dtype)
        for module in model.modules():
            if isinstance(module,torch.nn.Linear):module.forward=types.MethodType(linear,module)
    row=json.loads((OUT/'data/D8/manifest.json').read_text())[0]
    small=M.example(proc,row,full=False);n=len(small['input_ids']);stores={};handles=[]
    def hook(name):
        def fn(module,inp,out):
            v=out[0] if isinstance(out,tuple) else out
            if torch.is_tensor(v):
                if v.ndim==3:v=v[:,:n]
                elif v.ndim==4:v=v[:,:,:n]
                stores[name]=v.detach().cpu()
        return fn
    for name,module in model.named_modules():
        if '.language_model.layers.0.' in name:handles.append(module.register_forward_hook(hook(name)))
    assert handles
    qinputs=[]
    q=model.model.language_model.layers[0].self_attn.q_proj.base
    q.register_forward_pre_hook(lambda module,inp:qinputs.append(inp[0].detach().clone()))
    results=[]
    for full in (False,True):
        b=M.batch([M.example(proc,row,full=full)],proc.tokenizer.pad_token_id)
        with torch.no_grad():M.losses(model,b,0.)
        results.append(dict(stores));stores.clear()
    comparisons={k:float((results[0][k]-results[1][k]).abs().max()) for k in results[0]}
    isolated={}
    for dtype in (torch.bfloat16,torch.float32,torch.float64):
        t0=__import__('time').monotonic()
        with torch.no_grad():
            ys=[torch.nn.functional.linear(x.to(dtype),q.weight.to(dtype)).to(torch.bfloat16)[:,:n] for x in qinputs]
        isolated[str(dtype)]=dict(max_abs=float((ys[0]-ys[1]).abs().max()),wall_s=__import__('time').monotonic()-t0)
    save(out/'result.json',dict(module_max_abs=comparisons,isolated_q_projection=isolated,fp32_linear=a.fp32_linear,scope='첫 D8 첫 decoder block; dropout off; deterministic math SDPA'))
    print(json.dumps(comparisons),flush=True)

if __name__=='__main__':main()
