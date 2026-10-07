"""수정 D8 전체 회귀와 실제 batch1/2 누적 gradient·처리량·메모리 비교."""
import argparse
import json
import time
import torch
from report90_numeric import OUT,environment
from report90_train import load_model,update
import report89_model as M
from report86_common import save,sha
from rsna_diag import train as T

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);a=ap.parse_args();out=OUT/'tech/regression_batch';out.mkdir(parents=True,exist_ok=False)
    mapping=environment(a.gpu);save(out/'protocol.json',dict(mapping=mapping,source={f:sha(f) for f in ['report90_moretech.py','report90_train.py','report90_stable.py','report89_model.py']}))
    _,proc,model=load_model();rows=json.loads((OUT/'data/D8/manifest.json').read_text());checks=[];model.eval()
    with torch.no_grad():
        for i,row in enumerate(rows):
            outputs=[]
            for full in (False,True):
                b=M.batch([M.example(proc,row,full=full)],proc.tokenizer.pad_token_id)
                loss,_,log,mask=M.losses(model,b,0.,True);outputs.append((float(loss),log[mask].cpu()));del b,loss,log
            ld=float((outputs[0][1]-outputs[1][1]).abs().max());nd=abs(outputs[0][0]-outputs[1][0])
            checks.append(dict(index=i,logit_max_abs=ld,nll_abs=nd,passed=ld<=.125 and nd<=.002));print(json.dumps(checks[-1]),flush=True)
    initial=M.lora.lora_state_dict(model);model.train()
    for m in model.modules():
        if isinstance(m,torch.nn.Dropout):m.p=0.
    grads=[]
    for lam in (0.,1.):
        model.zero_grad(set_to_none=True);b=M.batch([M.example(proc,rows[6])],proc.tokenizer.pad_token_id)
        loss,_=M.losses(model,b,lam);loss.backward();grads.append({k:p.grad.detach().cpu().clone() for k,p in M.lora.lora_params(model).items()});del loss,b
    aux=sum(float((grads[0][k]-grads[1][k]).double().square().sum()) for k in grads[0])**.5
    save(out/'aux_gradient.json',dict(passed=aux>0,delta_l2=aux));del grads
    # 동등성은 dropout=0에서 검사하며, seed/순서/목적함수는 양 구성 동일하다.
    records=[];states=[]
    for mb in (1,2):
        model.zero_grad(set_to_none=True);M.lora.load_lora_state(model,initial);torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
        opt=torch.optim.AdamW(list(M.lora.lora_params(model).values()),lr=1e-4,betas=(.9,.999),eps=1e-8,weight_decay=.01)
        torch.cuda.synchronize();start=time.monotonic()
        try:
            values=update(torch,model,proc,rows,list(range(8)),0,0,opt,mb,1.)
            torch.cuda.synchronize();state=M.lora.lora_state_dict(model);states.append(state)
            rec=dict(mb=mb,wall_s=time.monotonic()-start,**values,peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
                peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,oom=False)
        except torch.OutOfMemoryError as e:
            rec=dict(mb=mb,oom=True,error=str(e),wall_s=time.monotonic()-start);states.append(None)
        records.append(rec);save(out/f'batch{mb}.json',rec);print(json.dumps(rec),flush=True);del opt
        model.zero_grad(set_to_none=True);torch.cuda.empty_cache()
    relative=None
    if all(s is not None for s in states):
        delta=sum(float((states[0][k]-states[1][k]).double().square().sum()) for k in initial)**.5
        den=sum(float((states[0][k]-initial[k]).double().square().sum()) for k in initial)**.5;relative=delta/max(den,1e-30)
    chosen=1
    if relative is not None and relative<=.02 and records[1]['wall_s']<records[0]['wall_s'] and records[1]['peak_reserved_gib']+3<23.56:chosen=2
    save(out/'result.json',dict(passed=all(x['passed'] for x in checks) and aux>0 and not records[0]['oom'],checks=checks,aux_delta_l2=aux,
        batch=records,update_relative_difference=relative,chosen_mb=chosen,reason='처리량 증가·정합성·peak+worker2GiB+context1GiB 동시 충족 시에만 mb2',
        technical_optimizer_steps=sum(not r['oom'] for r in records),main_training_updates=0))
    raise SystemExit(0 if all(x['passed'] for x in checks) and aux>0 and not records[0]['oom'] else 2)

if __name__=='__main__':main()
