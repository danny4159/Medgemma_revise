"""고정 R/G CE trainer. 원자적 checkpoint·pending validation·실제 설정 검증."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import time
import numpy as np
import report89_model as M
from report90_numeric import OUT,environment
from report90_stable import apply
from report86_common import sha,sha_obj,save
from rsna_diag import train as T

SOURCES=['report90_train.py','report90_numeric.py','report90_stable.py','report89_model.py','rsna_diag/lora.py','rsna_diag/sft_data.py','rsna_diag/train.py']

def load_model():
    torch,proc,model=M.load();apply(model);T.set_deterministic(torch)
    return torch,proc,model

def order(seed,epoch,n):return np.random.default_rng(seed*1000+epoch).permutation(n).tolist()

def update(torch,model,proc,rows,ids,epoch,step,opt,mb,lam):
    model.train();opt.zero_grad(set_to_none=True);values=[]
    for offset in range(0,len(ids),mb):
        part=ids[offset:offset+mb]
        seed=int(hashlib.sha256(f'17|{step}|{offset}'.encode()).hexdigest()[:8],16);T.seed_all(torch,seed)
        batch=M.batch([M.example(proc,rows[i],epoch) for i in part],proc.tokenizer.pad_token_id)
        loss,vals=M.losses(model,batch,lam)
        (loss*len(part)/len(ids)).backward()
        values.append([float(loss.detach())*len(part)/len(ids),*[float(v.detach().mean())*len(part)/len(ids) for v in vals]])
        del batch,loss,vals
    norm=float(torch.nn.utils.clip_grad_norm_(list(M.lora.lora_params(model).values()),1.))
    assert math.isfinite(norm) and all(math.isfinite(x) for row in values for x in row)
    opt.step();opt.zero_grad(set_to_none=True)
    return dict(loss=sum(v[0] for v in values),report_nll=sum(v[1] for v in values),ground_nll=sum(v[2] for v in values),grad_norm=norm)

def validate(torch,model,proc,rows,opt):
    rng=T.rng_state(torch);before=T.live_digests(torch,model,opt);mode=model.training
    grads={n:None if p.grad is None else p.grad.detach().clone() for n,p in M.lora.lora_params(model).items()}
    vals=[];model.eval()
    try:
        with torch.no_grad():
            for row in rows:
                b=M.batch([M.example(proc,row,full=False)],proc.tokenizer.pad_token_id)
                loss,_=M.losses(model,b,0.);vals.append(float(loss));del b,loss
    finally:
        model.train(mode);T.set_rng_state(torch,rng)
    after=T.live_digests(torch,model,opt)
    grad_equal=all((p.grad is None if grads[n] is None else p.grad is not None and torch.equal(p.grad,grads[n])) for n,p in M.lora.lora_params(model).items())
    assert before==after and model.training==mode and grad_equal
    return dict(n=len(vals),report_nll=float(np.mean(vals)),per_patient=vals,state_preserved=True,digests=after)

def run(a):
    run=Path(a.run_dir).resolve();run.relative_to(OUT);run.mkdir(parents=True,exist_ok=True)
    with (run/'owner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        mapping=environment(a.gpu)
        train_path=Path(a.train);val_path=Path(a.validation)
        rows=json.loads(train_path.read_text());vrows=json.loads(val_path.read_text())
        rows=sorted(rows,key=lambda r:r['PatientID'])
        if a.test_patients:rows=rows[:a.test_patients];vrows=vrows[:2]
        if not a.test_patients:
            gate=json.loads((OUT/'training_gate.json').read_text());assert gate['passed']
            for p,h in gate['evidence'].items():assert sha(p)==h
        cfg=dict(model=M.CFG,mode=a.mode,lr=a.lr,mb=a.mb,train_sha=sha(train_path),val_sha=sha(val_path),
            patient_ids=[r['PatientID'] for r in rows],seed=17,chunk=64,deterministic=True,
            code={p:sha(p) for p in SOURCES},test_patients=a.test_patients)
        digest=sha_obj(cfg);cp=run/'config.json'
        if cp.exists():assert json.loads(cp.read_text())==cfg,'config changed'
        else:save(cp,cfg)
        torch,proc,model=load_model();model.train()
        opt=torch.optim.AdamW(list(M.lora.lora_params(model).values()),lr=a.lr,betas=(.9,.999),eps=1e-8,weight_decay=.01)
        checkpoints=sorted(run.glob('checkpoint_*.pt'))
        step=0;epoch=0;pos=0;pending=None;prior_s=0.
        if checkpoints:
            marker=json.loads(checkpoints[-1].with_suffix('.json').read_text())
            assert marker['sha256']==sha(checkpoints[-1]) and marker['config_digest']==digest
            ck=torch.load(checkpoints[-1],map_location='cpu',weights_only=False);assert ck['config_digest']==digest
            M.lora.load_lora_state(model,ck['adapter']);opt.load_state_dict(ck['optimizer']);T.set_rng_state(torch,ck['rng'])
            assert T.live_digests(torch,model,opt)==ck['digests']
            step,epoch,pos,pending,prior_s=[ck[k] for k in ('step','epoch','pos','pending','elapsed_s')]
        attempt=len(list(run.glob('attempt_*.json')));start=time.monotonic()
        save(run/f'attempt_{attempt:03}.json',dict(mapping=mapping,start_step=step,pending=pending,config_digest=digest))
        stop=[False]
        signal.signal(signal.SIGTERM,lambda *args:stop.__setitem__(0,True))
        def checkpoint(pend=None):
            target=run/f'checkpoint_{step:06}.pt'
            state=dict(adapter=M.lora.lora_state_dict(model),optimizer=opt.state_dict(),rng=T.rng_state(torch),
                digests=T.live_digests(torch,model,opt),step=step,epoch=epoch,pos=pos,pending=pend,
                elapsed_s=prior_s+time.monotonic()-start,config_digest=digest)
            assert not target.exists()
            T.atomic_save(torch,state,str(target))
            save(run/f'checkpoint_{step:06}.json',dict(sha256=sha(target),config_digest=digest,step=step,epoch=epoch,pending=pend))
        def val(e):
            target=run/f'validation_{e:02}.json'
            if target.exists():
                saved=json.loads(target.read_text());assert saved['checkpoint_sha']==sha(run/f'checkpoint_{step:06}.pt') and saved['config_digest']==digest
            else:save(target,dict(validate(torch,model,proc,vrows,opt),epoch=e,checkpoint_sha=sha(run/f'checkpoint_{step:06}.pt'),config_digest=digest))
        if pending is not None:val(pending)
        spe=math.ceil(len(rows)/8);target_steps=a.epochs*spe
        with (run/f'events_{attempt:03}.jsonl').open('x') as log:
            while step<target_steps:
                ids=order(17,epoch,len(rows))[pos:pos+8]
                torch.cuda.synchronize();t=time.monotonic();torch.cuda.reset_peak_memory_stats()
                values=update(torch,model,proc,rows,ids,epoch,step,opt,a.mb,1. if a.mode=='G' else 0.)
                torch.cuda.synchronize();step+=1;pos+=len(ids);ended=pos==len(rows)
                if ended:epoch+=1;pos=0
                event=dict(values,step=step,epoch=epoch,pos=pos,ids=[rows[i]['PatientID'] for i in ids],wall_s=time.monotonic()-t,
                    peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
                    digests=T.live_digests(torch,model,opt))
                log.write(json.dumps(event)+'\n');log.flush()
                print(json.dumps({k:event[k] for k in ('step','epoch','loss','wall_s','peak_reserved_gib')}),flush=True)
                need_val=ended and epoch in (1,2,4,6,8,12)
                if ended or step%32==0 or step==a.stop_step or stop[0]:checkpoint(epoch if need_val else None)
                if step==a.stop_step or stop[0]:return 75
                if need_val:val(epoch)
        complete=run/f'complete_{a.epochs:02}.json'
        if complete.exists():
            previous=json.loads(complete.read_text())
            assert previous['step']==step and previous['config_digest']==digest and previous['checkpoint_sha']==sha(run/f'checkpoint_{step:06}.pt')
        else:save(complete,dict(step=step,epoch=epoch,config_digest=digest,
            checkpoint_sha=sha(run/f'checkpoint_{step:06}.pt'),elapsed_s=prior_s+time.monotonic()-start))
        return 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--gpu',required=True);p.add_argument('--run-dir',required=True)
    p.add_argument('--train',default=str(OUT/'data/T512/manifest.json'));p.add_argument('--validation',default=str(OUT/'data/V64/manifest.json'))
    p.add_argument('--mode',choices=['R','G'],required=True);p.add_argument('--lr',type=float,choices=[1e-4,2e-4],required=True)
    p.add_argument('--mb',type=int,choices=[1,2],default=1);p.add_argument('--epochs',type=int,required=True)
    p.add_argument('--test-patients',type=int,default=0);p.add_argument('--stop-step',type=int,default=-1)
    raise SystemExit(run(p.parse_args()))
