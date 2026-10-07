"""고정 행 선형 경로의 공식 CE·실제 gradient/update gate. 실패하면 학습 금지."""
import argparse
import json
import time
import torch
from report90_numeric import OUT,environment
from report90_stable import apply
import report89_model as M
from rsna_diag import train as T
from report86_common import save,sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gpu',required=True);ap.add_argument('--name',default='stable_training_v2');a=ap.parse_args()
    out=OUT/'tech'/a.name;out.mkdir(parents=True,exist_ok=False)
    mapping=environment(a.gpu)
    save(out/'protocol.json',dict(mapping=mapping,source={f:sha(f) for f in ['report90_tech.py','report90_stable.py','report89_model.py','rsna_diag/train.py','rsna_diag/lora.py']},
        manifest_sha256=sha(OUT/'data/D8/manifest.json'),criteria=dict(official_ce=2e-5,gradient_relative_l2=0.02,lambda0_exact=True),training_authorized=False))
    start=time.monotonic();_,proc,model=M.load();apply(model);T.set_deterministic(torch)
    rows=json.loads((OUT/'data/D8/manifest.json').read_text());checks=[]
    def check(name,passed,**kw):
        d=dict(name=name,passed=bool(passed),**kw);checks.append(d);save(out/(name+'.json'),d);print(json.dumps(d),flush=True)
    base_before=M.lora.base_digest(model)
    for i,row in enumerate(rows):
        full=M.example(proc,row);short=M.example(proc,row,full=False);n=len(short['input_ids'])
        check(f'input_{i}',torch.equal(full['input_ids'][:n],short['input_ids']) and torch.equal(full['pixel_values'],short['pixel_values']) and
            torch.equal(full['report_labels'][:n],short['report_labels']) and not ((full['report_labels']!=-100)&(full['ground_labels']!=-100)).any(),
            report_tokens=int((full['report_labels']!=-100).sum()),ground_tokens=int((full['ground_labels']!=-100).sum()))
    b=M.batch([M.example(proc,rows[0])],proc.tokenizer.pad_token_id)
    bs=M.batch([M.example(proc,rows[0],full=False)],proc.tokenizer.pad_token_id)
    model.eval()
    inp={k:v for k,v in b.items() if k not in ('labels','report_labels','ground_labels')}
    with torch.no_grad():
        oo=model(**inp,labels=b['labels'],use_cache=False);labs=b['labels'][:,1:];valid=labs!=-100
        token=torch.nn.functional.cross_entropy(oo.logits[:,:-1].float()[valid],labs[valid],reduction='none')
        independent=[float(token[b[name][:,1:][valid]!=-100].mean()) for name in ('report_labels','ground_labels')]
        _,vals=M.losses(model,b,1.);production=[float(v[0]) for v in vals]
        delta=max(abs(x-y) for x,y in zip(independent,production))
        check('official_ce',delta<=2e-5,max_abs=delta,independent=independent,production=production)
        del oo,token,vals
    initial=M.lora.lora_state_dict(model);params=list(M.lora.lora_params(model).values())
    drops=[(m,m.p) for m in model.modules() if isinstance(m,torch.nn.Dropout)]
    def step(bb,independent=False,lam=0.,training=False):
        M.lora.load_lora_state(model,initial);model.zero_grad(set_to_none=True);model.train();T.seed_all(torch,17)
        for m,p in drops:m.p=p if training else 0.
        opt=torch.optim.AdamW(params,lr=1e-4,betas=(0.9,0.999),eps=1e-8,weight_decay=0.01)
        loss,vals=M.losses(model,bb,lam)
        if independent:loss=vals[0].mean()
        loss.backward();grad={k:p.grad.detach().cpu().clone() for k,p in M.lora.lora_params(model).items()}
        torch.nn.utils.clip_grad_norm_(params,1.);opt.step()
        return dict(loss=float(loss.detach()),grad=grad,adapter=M.lora.lora_state_dict(model),optimizer=T.opt_digest(torch,opt),rng=T.rng_digest(torch))
    r=step(b,True,training=True);g=step(b,False,training=True)
    exact=r['loss']==g['loss'] and all(torch.equal(r['grad'][k],g['grad'][k]) for k in r['grad'])
    check('lambda0',exact and M.lora.state_digest(r['adapter'])==M.lora.state_digest(g['adapter']) and r['optimizer']==g['optimizer'] and r['rng']==g['rng'],
        loss_abs=abs(r['loss']-g['loss']),gradient_exact=exact,adapter_equal=M.lora.state_digest(r['adapter'])==M.lora.state_digest(g['adapter']),optimizer_equal=r['optimizer']==g['optimizer'],rng_equal=r['rng']==g['rng'])
    del r,g;torch.cuda.empty_cache()
    f=step(b);s=step(bs)
    diff=sum(float((f['grad'][k]-s['grad'][k]).double().square().sum()) for k in f['grad'])**0.5
    den=sum(float(s['grad'][k].double().square().sum()) for k in s['grad'])**0.5
    adiff=sum(float((f['adapter'][k]-s['adapter'][k]).double().square().sum()) for k in f['adapter'])**0.5
    update_norm=sum(float((s['adapter'][k]-initial[k]).double().square().sum()) for k in s['adapter'])**0.5
    check('short_full_gradient',diff/max(den,1e-30)<=0.02,relative_l2=diff/max(den,1e-30),loss_abs=abs(f['loss']-s['loss']),
        adapter_update_difference_l2=adiff,short_update_l2=update_norm,adapter_update_relative_difference=adiff/max(update_norm,1e-30),
        adapter_max_abs=max(float((f['adapter'][k]-s['adapter'][k]).abs().max()) for k in f['adapter']))
    del f,s;torch.cuda.empty_cache()
    check('base_frozen',M.lora.base_digest(model)==base_before)
    save(out/'result.json',dict(passed=all(c['passed'] for c in checks),checks=checks,technical_optimizer_steps=4,main_training_updates=0,
        wall_s=time.monotonic()-start,peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
        remaining=['aux gradient','D8 all shape regression','middle/epoch resume','validation state','throughput','full pixel checks','generation checks']))
    raise SystemExit(0 if all(c['passed'] for c in checks) else 2)

if __name__=='__main__':main()
