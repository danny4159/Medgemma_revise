"""길이별 오차의 최초 발생층과 head shape 영향을 실제 GPU에서 분리한다."""
import argparse
import os
import sys
import time
import subprocess
import json
from pathlib import Path
import report89_model as M
from report86_common import save,sha
from rsna_diag import train as T

OUT=M.ROOT/'results/iter_090'

def environment(gpu):
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert gpu in allowed
    smi=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,memory.free','--format=csv,noheader,nounits'],text=True)
    row=next(x.split(', ') for x in smi.splitlines() if x.split(', ')[0]==gpu)
    assert float(row[-1])>=14.19*1024+2048+1024
    M.OUT=OUT
    # 기존 cache 격리만 재사용하며 admission은 실제 peak+context+worker 여유로 선행한다.
    mapping=M.environment(gpu);mapping.update(peak_basis_gib=14.19,worker_margin_mib=2048,context_margin_mib=1024)
    return mapping

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--name',required=True)
    ap.add_argument('--fp32-linear',action='store_true');ap.add_argument('--fp64-linear',action='store_true');a=ap.parse_args()
    assert not (a.fp32_linear and a.fp64_linear)
    out=OUT/'tech'/a.name;out.mkdir(parents=True,exist_ok=False)
    mapping=environment(a.gpu)
    save(out/'protocol.json',dict(mapping=mapping,python=sys.executable,source={f:sha(f) for f in ['report90_numeric.py','report89_model.py','rsna_diag/train.py']},
        manifest_sha256=sha(OUT/'data/D8/manifest.json'),fp32_linear=a.fp32_linear,fp64_linear=a.fp64_linear,
        gates=dict(logits=0.125,nll=0.002,gradient_relative_l2=0.02,official_ce=2e-5),training_authorized=False))
    start=time.monotonic();torch,proc,model=M.load();T.set_deterministic(torch);model.eval()
    # 연산 shape에 따른 bf16 GEMM 반올림을 해당 선형층에서만 제거하는 대조.
    if a.fp32_linear or a.fp64_linear:
        import types
        dtype=torch.float64 if a.fp64_linear else torch.float32
        def linear(self,x):return torch.nn.functional.linear(x.to(dtype),self.weight.to(dtype),None if self.bias is None else self.bias.to(dtype)).to(x.dtype)
        for module in model.modules():
            if isinstance(module,torch.nn.Linear):module.forward=types.MethodType(linear,module)
    rows=json.loads((OUT/'data/D8/manifest.json').read_text());details=[]
    for idx in (0,3,4):
        row=rows[idx];ex=M.example(proc,row);small=M.example(proc,row,full=False)
        b=M.batch([ex],proc.tokenizer.pad_token_id);bs=M.batch([small],proc.tokenizer.pad_token_id);n=len(small['input_ids'])
        masks=['attention_mask','token_type_ids']
        inputs={k:bool(torch.equal(b[k][:,:n],bs[k])) for k in masks if k in b}
        inputs.update(ids=bool(torch.equal(b['input_ids'][:,:n],bs['input_ids'])),pixel=bool(torch.equal(b['pixel_values'],bs['pixel_values'])),report_labels=bool(torch.equal(b['report_labels'][:,:n],bs['report_labels'])))
        assert all(inputs.values())
        def forward(bb):
            inp={k:v for k,v in bb.items() if k not in ('labels','report_labels','ground_labels')}
            with torch.no_grad():
                oo=model.model(**inp,use_cache=False,output_hidden_states=True)
                hs=[h[:,:n-1].cpu() for h in oo.hidden_states]
                hidden=oo.last_hidden_state[:,:-1];sel=bb['labels'][:,1:]!=-100;rm=bb['report_labels'][:,1:][sel]!=-100
                allhead=model.lm_head(hidden[sel]).float()[rm]
                rh=hidden[bb['report_labels'][:,1:]!=-100]
                samehead=model.lm_head(rh).float()
                fphead=torch.nn.functional.linear(rh.float(),model.lm_head.weight.float()).float()
                loss,_,ll,mask=M.losses(model,bb,0.,True)
                return hs,rh.cpu(),allhead.cpu(),samehead.cpu(),fphead.cpu(),float(loss),ll[mask].cpu()
        f=forward(b);s=forward(bs)
        delta=lambda x,y:float((x-y).abs().max())
        layer=[delta(x,y) for x,y in zip(f[0],s[0])]
        altered={k:v.clone() for k,v in b.items()};altered['input_ids'][:,n:]=proc.tokenizer('x',add_special_tokens=False)['input_ids'][0]
        af=forward(altered)
        masked={k:v.clone() for k,v in b.items()};masked['attention_mask'][:,n:]=0;masked['input_ids'][:,n:]=proc.tokenizer.pad_token_id
        mf=forward(masked)
        d=dict(index=idx,inputs=inputs,lengths=[n,len(ex['input_ids'])],hidden_layers_max_abs=layer,
            report_hidden_max_abs=delta(f[1],s[1]),head_all_rows_max_abs=delta(f[2],s[2]),head_report_only_max_abs=delta(f[3],s[3]),
            head_fp32_max_abs=delta(f[4],s[4]),same_hidden_head_row_effect=delta(f[2],f[3]),
            logit_max_abs=delta(f[6],s[6]),nll_abs=abs(f[5]-s[5]),future_content_max_abs=delta(f[6],af[6]),future_mask_max_abs=delta(f[6],mf[6]))
        d['passed']=d['logit_max_abs']<=0.125 and d['nll_abs']<=0.002 and d['future_content_max_abs']==0 and d['future_mask_max_abs']==0
        details.append(d);save(out/f'case_{idx}.json',d);print(json.dumps(d),flush=True)
        del b,bs,f,s,af,mf,altered,masked;torch.cuda.empty_cache()
    result=dict(passed=all(d['passed'] for d in details),details=details,wall_s=time.monotonic()-start,
        peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
        main_training_updates=0,generated_reports=0,environment=M.generate.env_info(torch,proc,model))
    save(out/'result.json',result)
    sys.exit(0 if result['passed'] else 2)

if __name__=='__main__':main()
