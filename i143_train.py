"""동일 전체 sequence target의 세 조건 학습. 기술 gate 이후에만 진입한다."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import random
import time
import torch
from i143_data import OUT
from i143_model import load,inputs,embeds,target_loss,generate,adapter_state,set_adapter
from i141_common import read,sha,now,digest
from i143_runtime import save,validate_record
from i143_nocache import generate as nocache_generate
from i141_spec import split_final,START_TOKEN,END_TOKEN

CONFIG=dict(seed=17,rank=16,alpha=32,dropout=0,lr=1e-4,weight_decay=.01,gradient_clip=1.,effective_batch=4,
            initial_updates=48,warmup_updates=5,loss='patient_mean_target_CE',precision='bf16',microbatch=1)


def bound(gate):
    assert gate['passed'] is True
    for p,h in gate['files'].items(): assert sha(p)==h,'기술 잠금 변경: '+p


def predict(proc,model,rows,refs,condition,epoch,dest,cap,cache_enabled):
    model.eval(); records=[]
    import hashlib
    state=adapter_state(model)
    adapter_digest=digest({k:hashlib.sha256(v.numpy().tobytes()).hexdigest() for k,v in state.items()})
    del state
    provenance=dict(adapter_digest=adapter_digest,gate_sha256=sha(OUT/'training_gate.json'),cap=cap,
                    cache_enabled=cache_enabled,manifest_sha256=sha(OUT/'data_manifest.json'))
    for row in rows:
        path=dest/(row['patient_id']+'.json')
        if path.exists():
            record=read(path); validate_record(record,row,condition,epoch,provenance)
            records.append(record); continue
        for im in row['images']: assert sha(im['path'])==im['sha256']
        start=time.monotonic(); batch,roles,images,prefix=inputs(proc,row); e=embeds(model,batch)
        torch.cuda.reset_peak_memory_stats()
        saved_seconds=0.
        if cache_enabled:
            tokens,eos=generate(model,e,roles,images,condition,cap,cache_enabled=True)
        else:
            progress_dir=dest/('progress_'+row['patient_id']); progress_dir.mkdir(parents=True,exist_ok=True)
            context=dict(provenance=provenance,patient_id=row['patient_id'],condition=condition,epoch=epoch,
                         input_hashes=[im['sha256'] for im in row['images']])
            if (progress_dir/'config.json').exists(): assert read(progress_dir/'config.json')==context
            else: save(progress_dir/'config.json',context)
            initial=[]
            for checkpoint in sorted(progress_dir.glob('tokens_*.json')):
                item=read(checkpoint)
                assert item['digest']==digest({k:v for k,v in item.items() if k!='digest'})
                assert item['context_digest']==digest(context) and item['tokens'][:len(initial)]==initial
                initial=item['tokens']; saved_seconds=item['retained_seconds']
            def progress(tokens):
                checkpoint=progress_dir/f'tokens_{len(tokens):04d}.json'
                item=dict(tokens=list(tokens),context_digest=digest(context),retained_seconds=saved_seconds+time.monotonic()-start)
                item['digest']=digest(item); save(checkpoint,item)
                print(json.dumps(dict(patient_id=row['patient_id'],condition=condition,epoch=epoch,tokens=len(tokens))),flush=True)
            tokens,eos=nocache_generate(model,e,roles,images,condition,cap,initial_tokens=initial,progress=progress)
        bid=[proc.tokenizer.convert_tokens_to_ids(t) for t in (START_TOKEN,END_TOKEN)]
        status,final=split_final(tokens,*bid)
        record=dict(patient_id=row['patient_id'],condition=condition,epoch=epoch,tokens=tokens,provenance=provenance,
                    image_source_patient=row.get('image_source_patient',row['patient_id']),
                    text=proc.decode(tokens,skip_special_tokens=True),final_text=proc.decode(final,skip_special_tokens=True),
                    boundary=status,eos=eos,n_tokens=len(tokens),input_tokens=prefix,
                    input_hashes=[im['sha256'] for im in row['images']],seconds=time.monotonic()-start,
                    saved_prefix_seconds=saved_seconds,
                    peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2)
        del e,batch
        tb,tr,ti,tp=inputs(proc,row,refs[row['patient_id']]['target'])
        te=embeds(model,tb)
        with torch.no_grad(): record['target_nll']=float(target_loss(model,te,tr,ti,condition,tb['input_ids'],tp))
        del te,tb
        record['digest']=digest(record); validate_record(record,row,condition,epoch,provenance)
        save(path,record); records.append(record)
        torch.cuda.empty_cache()
    assert len({r['patient_id'] for r in records})==len(rows)
    return records


def main():
    p=argparse.ArgumentParser(); p.add_argument('--condition',choices=['S','A','N'],required=True)
    p.add_argument('--end-epoch',type=int,choices=[8,16],default=8); a=p.parse_args()
    gate=read(OUT/'training_gate.json'); bound(gate)
    if a.end_epoch==16: assert read(OUT/'extension_decision.json')['extend'] is True
    d=OUT/'train'/a.condition; d.mkdir(parents=True,exist_ok=True)
    fd=os.open(d/'owner.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cfg=dict(CONFIG,condition=a.condition,gate_sha256=sha(OUT/'training_gate.json'))
    if (d/'config.json').exists(): assert read(d/'config.json')==cfg
    else: save(d/'config.json',cfg)
    rows=read(OUT/'data_manifest.json')['rows']; train=[r for r in rows if r['split']=='T']; val=[r for r in rows if r['split']=='V']
    refs={r['patient_id']:r for r in read(OUT/'reference_locked.json')['rows']}
    proc,m=load(); params=[v for v in m.parameters() if v.requires_grad]
    opt=torch.optim.AdamW(params,lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay'])
    m.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    last=0; updates=0
    for epoch in range(1,a.end_epoch+1):
        seal=d/f'epoch{epoch:02d}.json'
        cp=d/f'epoch{epoch:02d}.pt'
        if cp.exists() and not seal.exists():
            orphan=torch.load(cp,weights_only=False,map_location='cpu')
            assert orphan['config']==cfg and orphan['epoch']==epoch and orphan['updates']==epoch*6
            expected=list(range(len(train))); random.Random(17+epoch).shuffle(expected)
            assert orphan['patient_order']==[train[i]['patient_id'] for i in expected]
            assert len(orphan['losses'])==len(train)
            save(seal,dict(created_at=now(),sha256=sha(cp),config_digest=digest(cfg),updates=orphan['updates'],
                 losses=orphan['losses'],seconds=orphan['seconds'],patient_order=orphan['patient_order'],
                 recovered_after_checkpoint_write=True))
            del orphan
        if not seal.exists(): break
        s=read(seal); assert sha(cp)==s['sha256'] and s['config_digest']==digest(cfg)
        last=epoch
    if last:
        state=torch.load(d/f'epoch{last:02d}.pt',weights_only=False,map_location='cpu')
        set_adapter(m,state['adapter']); opt.load_state_dict(state['optimizer']); torch.set_rng_state(state['rng'])
        torch.cuda.set_rng_state_all(state['cuda_rng']); updates=state['updates']
    else:
        init={k:__import__('hashlib').sha256(v.numpy().tobytes()).hexdigest() for k,v in adapter_state(m).items()}
        if (d/'initial_adapter_hashes.json').exists(): assert read(d/'initial_adapter_hashes.json')==init
        else: save(d/'initial_adapter_hashes.json',init)
        for prior in (OUT/'train').glob('*/initial_adapter_hashes.json'):
            assert read(prior)==init,'조건 간 초기 adapter 불일치: '+str(prior)
        predict(proc,m,val,refs,a.condition,0,OUT/'generation'/a.condition/'epoch00',gate['cap'],gate['cache_enabled'])
    # epoch 저장 후 validation 전 중단된 경계도 먼저 복구한다.
    if last in (2,4,8,16):
        predict(proc,m,val,refs,a.condition,last,OUT/'generation'/a.condition/f'epoch{last:02d}',gate['cap'],gate['cache_enabled'])
    for epoch in range(last+1,a.end_epoch+1):
        order=list(range(len(train))); random.Random(17+epoch).shuffle(order)
        losses=[]; t=time.monotonic(); m.train(); opt.zero_grad(set_to_none=True)
        for j,index in enumerate(order):
            r=train[index]; batch,ro,ii,prefix=inputs(proc,r,refs[r['patient_id']]['target']); e=embeds(m,batch).requires_grad_(True)
            loss=target_loss(m,e,ro,ii,a.condition,batch['input_ids'],prefix)
            assert torch.isfinite(loss); (loss/4).backward(); losses.append(float(loss.detach()))
            if (j+1)%4==0:
                lr=CONFIG['lr']*min(1.,(updates+1)/5)
                for g in opt.param_groups:g['lr']=lr
                norm=torch.nn.utils.clip_grad_norm_(params,1.); assert torch.isfinite(norm)
                opt.step(); opt.zero_grad(set_to_none=True); updates+=1
                print(json.dumps(dict(epoch=epoch,update=updates,mean_loss=sum(losses[-4:])/4,lr=lr,grad_norm=float(norm))),flush=True)
            del e,batch,loss
            torch.cuda.empty_cache()
        cp=d/f'epoch{epoch:02d}.pt'; temp=d/f'epoch{epoch:02d}.{time.time_ns()}.partial'
        state=dict(adapter=adapter_state(m),optimizer=opt.state_dict(),rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state_all(),
                   epoch=epoch,updates=updates,patient_order=[train[i]['patient_id'] for i in order],config=cfg,
                   losses=losses,seconds=time.monotonic()-t)
        assert not cp.exists(); torch.save(state,temp); os.rename(temp,cp)
        save(d/f'epoch{epoch:02d}.json',dict(created_at=now(),sha256=sha(cp),config_digest=digest(cfg),updates=updates,
             losses=losses,seconds=time.monotonic()-t,patient_order=state['patient_order']))
        if epoch in (2,4,8,16):
            predict(proc,m,val,refs,a.condition,epoch,OUT/'generation'/a.condition/f'epoch{epoch:02d}',gate['cap'],gate['cache_enabled'])
    complete=d/f'complete{a.end_epoch:02d}.json'
    if complete.exists():
        old=read(complete); assert old['updates']==updates and old['config_digest']==digest(cfg)
    else: save(complete,dict(created_at=now(),updates=updates,epoch=a.end_epoch,config_digest=digest(cfg)))
    os.close(fd)

if __name__=='__main__': main()
