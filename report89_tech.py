"""새 다중 턴 경로의 실제 GPU 검사. 실패를 통과로 바꾸지 않고 상세 원자료를 보존한다."""
import argparse
import copy
import json
import time
from pathlib import Path
import sys

import report89_model as M
from report86_common import save,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();out=Path(a.out).resolve();out.relative_to(M.OUT);out.mkdir(parents=True,exist_ok=False)
    mapping=M.environment(a.gpu)
    # 문턱은 결과 전에 저장한다. shape 변경의 bf16 수치 차이는 엄밀 동등성으로 보고하지 않는다.
    rules=dict(same_shape_logit_atol=0.,lambda0_loss_atol=0.,lambda0_gradient_atol=0.,
               short_full_report_nll_atol=0.002,short_full_report_logit_atol=0.125,
               short_full_gradient_relative_l2=0.02,official_loss_atol=2e-5)
    save(out/'protocol.json',dict(rules=rules,cfg=M.CFG,mapping=mapping,python=sys.executable,
         source={f:sha(f) for f in ['report89_model.py','report89_tech.py','rsna_diag/lora.py','rsna_diag/sft_data.py']},
         data_sha256=sha(M.OUT/'data/D8/manifest.json')))
    torch,proc,model=M.load();model.eval()
    rows=json.loads((M.OUT/'data/D8/manifest.json').read_text())
    checks=[];details=[]
    def check(name,ok,**kw):
        d=dict(name=name,pass_=bool(ok),**kw);checks.append(d);print(json.dumps(d),flush=True)
    def grad(b,lam):
        model.zero_grad(set_to_none=True);torch.manual_seed(17);torch.cuda.manual_seed_all(17)
        loss,vals=M.losses(model,b,lam);loss.backward()
        gs={n:p.grad.detach().cpu().clone() for n,p in M.lora.lora_params(model).items() if p.grad is not None}
        return float(loss.detach()),[v.detach().cpu().tolist() for v in vals],gs
    base_before=M.lora.base_digest(model)
    for i,row in enumerate(rows):
        ex=M.example(proc,row);small=M.example(proc,row,full=False)
        check('mask_'+str(i),int((ex['report_labels']!=-100).sum())==int((small['labels']!=-100).sum()),
              n_report=int((ex['report_labels']!=-100).sum()),n_ground=int((ex['ground_labels']!=-100).sum()),
              full_length=len(ex['input_ids']),short_length=len(small['input_ids']))
        if i not in (0,3,4):continue
        b=M.batch([ex],proc.tokenizer.pad_token_id);bs=M.batch([small],proc.tokenizer.pad_token_id)
        with torch.no_grad():
            loss,vals,logits,mask=M.losses(model,b,0.,True)
            lr=logits[mask].cpu();del logits
            s_loss,s_vals,s_logits,s_mask=M.losses(model,bs,0.,True)
            sr=s_logits[s_mask].cpu();del s_logits
        err=float((lr-sr).abs().max());nllerr=abs(float(vals[0][0])-float(s_vals[0][0]))
        check('short_full_report_'+str(i),err<=rules['short_full_report_logit_atol'] and nllerr<=rules['short_full_report_nll_atol'],max_logit_abs=err,nll_abs=nllerr)
        # 미래 user/assistant 토큰을 변경하되 길이·image·첫 turn은 보존한다.
        altered={k:v.clone() for k,v in b.items()};n=len(small['input_ids'])
        altered['input_ids'][:,n:]=proc.tokenizer('x',add_special_tokens=False)['input_ids'][0]
        with torch.no_grad():
            _,_,ll,mm=M.losses(model,altered,0.,True);diff=float((ll[mm].cpu()-lr).abs().max());del ll
        check('future_token_noninterference_'+str(i),diff==0,max_logit_abs=diff)
        del b,bs,lr,sr,altered
        torch.cuda.empty_cache()
    ex=M.example(proc,rows[0]);b=M.batch([ex],proc.tokenizer.pad_token_id)
    # 독립 공식 forward와 수동 CE의 연결: 각 loss의 다른 정규화도 별도로 계산한다.
    inp={k:v for k,v in b.items() if k not in ('labels','report_labels','ground_labels')}
    with torch.no_grad():
        oo=model(**inp,labels=b['labels'],use_cache=False)
        labs=b['labels'][:,1:];valid=labs!=-100
        logits=oo.logits[:,:-1].float()
        token_ce=torch.nn.functional.cross_entropy(logits[valid],labs[valid],reduction='none')
        manual=[]
        for name in ('report_labels','ground_labels'):
            mk=b[name][:,1:][valid]!=-100;manual.append(float(token_ce[mk].mean()))
        loss,vs=M.losses(model,b,1.)
        dd=max(abs(manual[j]-float(vs[j][0])) for j in range(2))
        check('official_ce',dd<=rules['official_loss_atol'],independent=manual,production=[float(v[0]) for v in vs],max_abs=dd,
              official_all_token_ce=float(oo.loss),independent_all_token_ce=float(token_ce.mean()))
        del oo,logits,token_ce
    model.train()
    # 동일 shape와 dropout RNG의 lambda0 동등성은 정확 일치를 요구한다.
    l1,v1,g1=grad(b,0.);l2,v2,g2=grad(b,0.)
    mx=max(float((g1[n]-g2[n]).abs().max()) for n in g1)
    check('lambda0_same_shape',l1==l2 and mx==0,loss_diff=abs(l1-l2),gradient_max_abs=mx)
    l3,v3,g3=grad(b,1.)
    aux_norm=sum(float((g3[n]-g1[n]).double().square().sum()) for n in g1)**0.5
    check('aux_gradient',aux_norm>0 and all(torch.isfinite(g).all() for g in g3.values()),delta_gradient_l2=aux_norm)
    del g2,g3
    # dropout을 제거한 일반 report-only 대조. 수치 차이를 명시적으로 판정한다.
    model.eval();_,_,gf=grad(b,0.)
    bs=M.batch([M.example(proc,rows[0],full=False)],proc.tokenizer.pad_token_id)
    _,_,gs=grad(bs,0.)
    diff=sum(float((gf[n]-gs[n]).double().square().sum()) for n in gf)**0.5
    den=sum(float(gs[n].double().square().sum()) for n in gs)**0.5
    check('short_full_gradient',diff/max(den,1e-30)<=rules['short_full_gradient_relative_l2'],relative_l2=diff/max(den,1e-30))
    check('base_frozen',M.lora.base_digest(model)==base_before,
          n_base=sum('lora_' not in n for n,_ in model.named_parameters()),
          n_trainable=sum(p.numel() for p in M.lora.lora_params(model).values()))
    result=dict(checks=checks,passed=all(c['pass_'] for c in checks),
                peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
                environment=M.generate.env_info(torch,proc,model),
                remaining_required=['optimizer update equivalence','middle/epoch resume','validation state preservation','batch throughput','generation resume'])
    save(out/'result.json',result)
    print('TECH_PARTIAL_PASS' if result['passed'] else 'TECH_FAIL',flush=True)
    sys.exit(0 if result['passed'] else 2)


if __name__=='__main__':main()
