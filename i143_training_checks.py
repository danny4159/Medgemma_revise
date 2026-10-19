"""실제 두 환자의 loss/update·동결·중간 step 저장/재개 검사."""
import argparse
import copy
import hashlib
import time
import torch
from i143_model import load,inputs,embeds,target_loss,adapter_state,set_adapter,hidden
from i143_data import OUT
from i141_common import read,save,sha,now


def frozen_digest(m):
    h=hashlib.sha256(); n=0
    for name,p in m.named_parameters():
        if not p.requires_grad:
            h.update(name.encode()); h.update(p.detach().cpu().view(torch.uint8).numpy().tobytes()); n+=1
    return dict(sha256=h.hexdigest(),parameters=n)


def cpu_state(x):
    if isinstance(x,torch.Tensor): return x.detach().cpu().clone()
    if isinstance(x,dict): return {k:cpu_state(v) for k,v in x.items()}
    if isinstance(x,list): return [cpu_state(v) for v in x]
    return copy.deepcopy(x)


def identical(a,b):
    if isinstance(a,torch.Tensor): return a.dtype==b.dtype and a.shape==b.shape and torch.equal(a.cpu(),b.cpu())
    if isinstance(a,dict): return a.keys()==b.keys() and all(identical(a[k],b[k]) for k in a)
    if isinstance(a,list): return len(a)==len(b) and all(identical(x,y) for x,y in zip(a,b))
    return a==b


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--name',default='train_checks_a1'); a=ap.parse_args()
    torch.manual_seed(17); proc,m=load(); frozen_before=frozen_digest(m); initial=adapter_state(m)
    m.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    rows=[r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='T'][:2]
    refs={r['patient_id']:r['target'] for r in read(OUT/'reference_locked.json')['rows']}
    data=[]
    for r in rows:
        b,ro,ii,p=inputs(proc,r,refs[r['patient_id']]); e=embeds(m,b).cpu(); data.append((e,ro,ii,p,b['input_ids']))
        del b
    # 원 공식 loss와 target-only shifted CE의 같은 hidden/logits 대조.
    e,ro,ii,p,ids=data[0]; m.eval()
    with torch.no_grad():
        h=hidden(m,e.cuda(),ro,ii,'N'); logits=m.lm_head(h[:,p-1:-1]).float()
        labels=ids[:,p:].cuda(); direct=torch.nn.functional.cross_entropy(logits.flatten(0,1),labels.flatten())
        from transformers.loss.loss_utils import ForCausalLMLoss
        official=ForCausalLMLoss(logits,labels=None,vocab_size=logits.shape[-1],shift_labels=labels)
        ce_error=float((direct-official).abs()); assert ce_error<1e-6
    del e,h,logits,labels,direct,official
    results=[]
    for cond in ['S','A','N']:
        torch.cuda.empty_cache()
        set_adapter(m,initial); opt=torch.optim.AdamW([p for p in m.parameters() if p.requires_grad],lr=1e-4,weight_decay=.01)
        m.train(); torch.manual_seed(17)
        def step(datum):
            e,ro,ii,p,ids=datum; opt.zero_grad(set_to_none=True)
            loss=target_loss(m,e.cuda().requires_grad_(True),ro,ii,cond,ids,p); loss.backward()
            norm=torch.nn.utils.clip_grad_norm_([v for v in m.parameters() if v.requires_grad],1.)
            assert torch.isfinite(loss) and torch.isfinite(norm); opt.step()
            value=float(loss.detach()); del loss
            torch.cuda.empty_cache()
            return value
        t=time.monotonic(); loss1=step(data[0]); path=OUT/'tests'/f'{a.name}_{cond}_resume.pt'
        torch.save(dict(adapter=adapter_state(m),optimizer=opt.state_dict(),rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state_all()),path)
        optimizer_before=cpu_state(opt.state_dict())
        loss2=step(data[1]); expected=adapter_state(m)
        state=torch.load(path,map_location='cpu',weights_only=False); set_adapter(m,state['adapter']); opt.load_state_dict(copy.deepcopy(state['optimizer']))
        optimizer_exact=identical(optimizer_before,cpu_state(opt.state_dict()))
        assert optimizer_exact and identical(adapter_state(m),state['adapter'])
        torch.set_rng_state(state['rng']); torch.cuda.set_rng_state_all(state['cuda_rng'])
        assert identical(torch.get_rng_state(),state['rng']) and identical(torch.cuda.get_rng_state_all(),state['cuda_rng'])
        resumed_loss=step(data[1]); actual=adapter_state(m)
        difference=max(float((actual[k]-expected[k]).abs().max()) for k in actual)
        # bf16 반복 자체의 기준 대조: 동일 상태에서 같은 shape 경로를 한 번 더 실행.
        set_adapter(m,state['adapter']); opt.load_state_dict(copy.deepcopy(state['optimizer'])); torch.set_rng_state(state['rng']); torch.cuda.set_rng_state_all(state['cuda_rng'])
        repeat_loss=step(data[1]); repeat=adapter_state(m)
        resumed_floor=max(float((repeat[k]-actual[k]).abs().max()) for k in repeat)
        # 복원 경로를 통과하지 않는 독립 2-step 대조도 반복한다.
        set_adapter(m,initial); opt=torch.optim.AdamW([p for p in m.parameters() if p.requires_grad],lr=1e-4,weight_decay=.01)
        torch.manual_seed(17); uninterrupted_loss1=step(data[0]); uninterrupted_loss2=step(data[1])
        uninterrupted=adapter_state(m)
        uninterrupted_floor=max(float((uninterrupted[k]-expected[k]).abs().max()) for k in expected)
        floor=max(resumed_floor,uninterrupted_floor)
        loss_floor=max(abs(repeat_loss-resumed_loss),abs(uninterrupted_loss2-loss2))
        passed=difference<=max(1e-7,2*floor) and abs(resumed_loss-loss2)<=max(1e-6,2*loss_floor)
        torch.save(dict(expected=expected,resumed=actual,resumed_repeat=repeat,uninterrupted_repeat=uninterrupted),
                   OUT/'tests'/f'{a.name}_{cond}_adapter_comparison.pt')
        assert passed,('resume',cond,difference,floor)
        m.eval()
        with torch.no_grad():
            e,ro,ii,p,ids=data[0]; after=float(target_loss(m,e.cuda(),ro,ii,cond,ids,p))
        results.append(dict(condition=cond,first_loss=loss1,second_loss=loss2,first_patient_nll_after_two_updates=after,
                    resume_loss=resumed_loss,repeat_loss=repeat_loss,adapter_max_difference=difference,
                    resumed_repeat_difference=resumed_floor,uninterrupted_repeat_difference=uninterrupted_floor,
                    uninterrupted_repeat_loss=uninterrupted_loss2,optimizer_restore_exact=optimizer_exact,
                    repeat_max_difference=floor,passed=passed,wall_s=time.monotonic()-t))
        print(results[-1],flush=True)
    frozen_after=frozen_digest(m); assert frozen_before==frozen_after
    save(OUT/'tests'/(a.name+'.json'),dict(created_at=now(),passed=True,rows=results,ce_max_difference=ce_error,
         frozen_before=frozen_before,frozen_after=frozen_after,source_sha256=sha(__file__),
         model_source_sha256=sha(__import__('pathlib').Path(__file__).with_name('i143_model.py')),
         note='두 환자 동작 검사, 일반화/overfit 성공 주장 없음. optimizer update 경계 재개.'))

if __name__=='__main__': main()
