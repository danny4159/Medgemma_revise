"""a1 실패의 수치 원인 분리. 자료 gate를 우회하거나 본학습을 허가하지 않는다."""
import argparse
import json
from pathlib import Path
import sys
import time

import report89_model as M
from report86_common import save,sha
from rsna_diag import train as T


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args();out=Path(a.out).resolve();out.relative_to(M.OUT);out.mkdir(parents=True,exist_ok=False)
    mapping=M.environment(a.gpu)
    save(out/'protocol.json',dict(source={f:sha(f) for f in ['report89_model.py','report89_numeric.py','rsna_diag/train.py']},
         mapping=mapping,reason='동일 경로 반복 차이와 seq shape 효과를 분리',
         criteria='동일 shape/결정적 backend/동일 RNG의 loss, gradient, update 정확 일치',
         inherited_failure_sha256=sha(M.OUT/'tech/a1/result.json'),training_authorized=False))
    torch,proc,model=M.load();T.set_deterministic(torch)
    row=json.loads((M.OUT/'data/D8/manifest.json').read_text())[0]
    full=M.example(proc,row);short=M.example(proc,row,full=False)
    b=M.batch([full],proc.tokenizer.pad_token_id);bs=M.batch([short],proc.tokenizer.pad_token_id)
    n=len(short['input_ids'])
    # 같은 sequence 길이와 head shape를 유지하면서 미래 token 전체를 attention에서 제외한다.
    bp={k:v.clone() for k,v in b.items()};bp['attention_mask'][:,n:]=0;bp['input_ids'][:,n:]=proc.tokenizer.pad_token_id
    model.eval()
    details={}
    def forward(bb):
        with torch.no_grad():
            inp={k:v for k,v in bb.items() if k not in ('labels','report_labels','ground_labels')}
            hh=model.model(**inp,use_cache=False).last_hidden_state[:,:-1]
            rh=hh[bb['report_labels'][:,1:]!=-100].cpu()
            ll,v,log,mask=M.losses(model,bb,0.,True)
            return rh,log[mask].cpu(),float(ll)
    hf,lf,nf=forward(b);hs,ls,ns=forward(bs);hp,lp,np_=forward(bp)
    details['short_full']=dict(hidden_max_abs=float((hf-hs).abs().max()),logit_max_abs=float((lf-ls).abs().max()),nll_abs=abs(nf-ns))
    details['same_shape_future_masked']=dict(hidden_max_abs=float((hf-hp).abs().max()),logit_max_abs=float((lf-lp).abs().max()),nll_abs=abs(nf-np_))
    print(json.dumps(details),flush=True)
    initial=M.lora.lora_state_dict(model)
    params=list(M.lora.lora_params(model).values())
    model.train()
    def update(bb,independent=False):
        M.lora.load_lora_state(model,initial);model.zero_grad(set_to_none=True)
        T.seed_all(torch,17)
        opt=torch.optim.AdamW(params,lr=1e-4,betas=(0.9,0.999),eps=1e-8,weight_decay=0.01)
        loss,vals=M.losses(model,bb,0.)
        if independent:loss=vals[0].mean()
        loss.backward()
        grads={k:p.grad.detach().cpu().clone() for k,p in M.lora.lora_params(model).items()}
        torch.nn.utils.clip_grad_norm_(params,1.);opt.step()
        return dict(loss=float(loss.detach()),grads=grads,state=M.lora.lora_state_dict(model),optimizer=T.opt_digest(torch,opt),rng=T.rng_digest(torch))
    r=update(b,True);g0=update(b,False)
    details['R_vs_G_lambda0']=dict(loss_abs=abs(r['loss']-g0['loss']),
         gradient_max_abs=max(float((r['grads'][k]-g0['grads'][k]).abs().max()) for k in r['grads']),
         adapter_equal=M.lora.state_digest(r['state'])==M.lora.state_digest(g0['state']),
         optimizer_equal=r['optimizer']==g0['optimizer'],rng_equal=r['rng']==g0['rng'])
    d=details['R_vs_G_lambda0'];details['same_shape_pass']=d['loss_abs']==0 and d['gradient_max_abs']==0 and d['adapter_equal'] and d['optimizer_equal'] and d['rng_equal']
    save(out/'result.json',dict(details=details,passed=details['same_shape_pass'],
         original_gate_status='a1 FAIL 유지; shape 대조 및 전체 required_checks 미해결',
         peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
         main_training_updates=0,technical_optimizer_steps=2,environment=M.generate.env_info(torch,proc,model)))
    print(json.dumps(details),flush=True)
    sys.exit(0 if details['same_shape_pass'] else 2)


if __name__=='__main__':main()
