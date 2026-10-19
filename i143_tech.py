"""사전 고정 기술 검사. 실패는 본학습 진입을 막는다."""
import argparse
import copy
import json
import os
import time
from pathlib import Path
import torch
import torch.nn.functional as F
from i143_data import OUT
from i141_common import read,save,sha,now
from i143_model import Mask,chunk_attention,load,inputs,embeds,hidden,target_loss,generate,adapter_state,set_adapter


def run(args):
    checks=[]; started=time.monotonic()
    def check(name,passed,**detail):
        checks.append(dict(name=name,passed=bool(passed),**detail))
        print(json.dumps(checks[-1]),flush=True)
        assert passed,name
    # float64 dense reference: backend forward 및 q/k/v gradient를 별도 softmax 식과 대조.
    torch.manual_seed(17)
    r=torch.tensor([-1,-1,0,0,1,1,2,2,-2,-2],device='cuda')
    im=torch.tensor([-1,-1,0,0,1,1,2,2,-1,-1],device='cuda')
    for cond in ('S','A','N'):
        spec=Mask(r,im,cond,window=4,chunk=3)
        q=torch.randn(1,2,10,8,device='cuda',dtype=torch.float64,requires_grad=True)
        k=torch.randn(1,1,10,8,device='cuda',dtype=torch.float64,requires_grad=True)
        v=torch.randn_like(k,requires_grad=True)
        out,_=chunk_attention(None,q,k,v,spec,scaling=8**-.5)
        mask=spec.materialize(0,10,0,10)
        score=(q@k.repeat_interleave(2,1).transpose(-1,-2))*8**-.5
        ref=(score.masked_fill(~mask,-torch.inf).softmax(-1)@v.repeat_interleave(2,1)).transpose(1,2)
        g=torch.autograd.grad(out.square().sum(),(q,k,v),retain_graph=True)
        gr=torch.autograd.grad(ref.square().sum(),(q,k,v))
        err=float((out-ref).abs().max()); ge=max(float((a-b).abs().max()) for a,b in zip(g,gr))
        check('dense_'+cond,err<1e-10 and ge<1e-9,forward_max=err,gradient_max=ge)
    proc,model=load(); check('adapter_parameter_count',sum(p.numel() for p in model.parameters() if p.requires_grad)==8912896)
    manifest=read(OUT/'data_manifest.json')['rows']; refs={r['patient_id']:r for r in read(OUT/'reference_locked.json')['rows']}
    train=[r for r in manifest if r['split']=='T']
    row=copy.deepcopy(train[0]); row['images']=row['images'][:2]
    # 기술 부분 입력은 tensor/mask 동작 검사 전용이며 전체 report 학습으로 쓰지 않는다.
    b,roles,images,prefix=inputs(proc,row)
    eb=embeds(model,b)
    from transformers.models.gemma3.modeling_gemma3 import get_block_sequence_ids_for_mask,create_masks_for_vision_model
    block=get_block_sequence_ids_for_mask(b['token_type_ids'].to('cuda'),device='cuda')
    official=create_masks_for_vision_model(model.config.text_config,eb,b['attention_mask'].to('cuda'),None,
                 torch.arange(eb.shape[1],device='cuda')[None],block)
    for kind,mask in official.items():
        spec=Mask(roles.to('cuda'),images.to('cuda'),'N',window=1024 if kind=='sliding_attention' else None)
        expected=spec.materialize(0,len(roles),0,len(roles))
        native=mask if mask.dtype==torch.bool else mask==0
        check('native_mask_'+kind,torch.equal(native,expected),n_tokens=len(roles))
    with torch.no_grad():
        model.model.language_model.config._attn_implementation='sdpa'
        ob=model.model(**{k:v.to('cuda',dtype=torch.bfloat16) if v.is_floating_point() else v.to('cuda') for k,v in b.items()},use_cache=False,return_dict=True)
        oh=ob.last_hidden_state; mh=hidden(model,eb,roles,images,'N')
        logits1=model.lm_head(oh[:,-8:]).float(); logits2=model.lm_head(mh[:,-8:]).float()
        diff=float((logits1-logits2).abs().max())
        check('native_forward',diff<=0.125,max_logit_difference=diff,tolerance=0.125)
        del ob,oh,mh,logits1,logits2
        altered=eb.clone(); altered[:,images==0]+=torch.randn_like(altered[:,images==0])*.5
        for cond in ('S','A'):
            h1=hidden(model,eb,roles,images,cond); h2=hidden(model,altered,roles,images,cond)
            change=float((h1[:,roles==1]-h2[:,roles==1]).abs().max())
            check('group_intervention_'+cond,change==0 if cond=='S' else change>0,local_change=change)
        # 5 decode steps, cached vs whole-prefix recompute. Greedy arrays must agree.
        for cond in ('S','A','N'):
            a,_=generate(model,eb,roles,images,cond,5,True)
            c,_=generate(model,eb,roles,images,cond,5,False)
            check('cache_tokens_'+cond,a==c,cached=a,no_cache=c)
    # 전체 sequence actual report target, report-only loss and two train patients.
    del b,eb
    for layer in model.model.language_model.layers:
        layer.gradient_checkpointing=True
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.train()
    longest=max(train,key=lambda x:x['n_slices'])
    save(OUT/'tests'/(args.name+'_pre_memory.json'),dict(created_at=now(),patient_id=longest['patient_id'],slices=longest['n_slices']))
    batch,ro,ii,p=inputs(proc,longest,refs[longest['patient_id']]['target']); e=embeds(model,batch).requires_grad_(True)
    torch.cuda.reset_peak_memory_stats()
    before=adapter_state(model)
    opt=torch.optim.AdamW([x for x in model.parameters() if x.requires_grad],lr=1e-4,weight_decay=.01)
    t=time.monotonic(); loss=target_loss(model,e,ro,ii,'N',batch['input_ids'],p); loss.backward()
    norms=[float(e.grad[:,ro==i].norm()) for i in range(longest['n_slices'])]
    check('all_slices_gradient',all(x>0 and x<float('inf') for x in norms),norms=norms)
    torch.nn.utils.clip_grad_norm_([x for x in model.parameters() if x.requires_grad],1.); opt.step(); opt.zero_grad(set_to_none=True)
    peak=torch.cuda.max_memory_reserved()/1024**2
    check('longest_training_memory',peak+2048<torch.cuda.get_device_properties(0).total_memory/1024**2,
          reserved_mib=peak,allocated_mib=torch.cuda.max_memory_allocated()/1024**2,step_seconds=time.monotonic()-t,loss=float(loss),tokens=int(e.shape[1]))
    after=adapter_state(model)
    check('actual_weight_update',any(not torch.equal(before[k],after[k]) for k in after))
    path=OUT/'tests'/(args.name+'_adapter.pt'); torch.save(after,path)
    set_adapter(model,before); set_adapter(model,torch.load(path,weights_only=True))
    check('adapter_reload',all(torch.equal(v.cpu(),after[k]) for k,v in model.named_parameters() if v.requires_grad))
    save(OUT/'tests'/(args.name+'_checks.json'),dict(created_at=now(),checks=checks,passed=all(x['passed'] for x in checks),
         source_sha256=sha(__file__),model_source_sha256=sha(Path(__file__).with_name('i143_model.py')),wall_s=time.monotonic()-started,
         remaining=['two-patient sanity','restart equivalence','microbatch comparison','generation cap','evaluation lock']))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--name',default='tech_a1'); a=p.parse_args()
    try: run(a)
    except Exception as e:
        import traceback
        save(OUT/'tests'/(a.name+'_failure.json'),dict(created_at=now(),error=repr(e),traceback=traceback.format_exc(),
             peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2 if torch.cuda.is_initialized() else None))
        raise
