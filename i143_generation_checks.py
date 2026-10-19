"""전체 길이의 cache/no-cache logits, 실제 cap과 GPU 메모리 검사."""
import argparse
import time
import torch
from i143_model import load,inputs,embeds,hidden,generate
from i143_data import OUT
from i141_common import read,save,sha,now


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--name',default='generation_checks_a1'); ap.add_argument('--cache-only',action='store_true'); a=ap.parse_args()
    proc,m=load(); row=max((r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='T'),key=lambda x:x['n_slices'])
    b,ro,ii,p=inputs(proc,row); e=embeds(m,b); del b
    from transformers.cache_utils import DynamicCache
    comparisons=[]
    with torch.no_grad():
        for cond in ['S','A','N']:
            cache=DynamicCache(); seq=e; full=e; r=ro; im=ii; diffs=[]; tokens=[]
            for step in range(3):
                hc=hidden(m,seq,r,im,cond,cache=cache,offset=0 if step==0 else len(r)-1)
                hn=hidden(m,full,r,im,cond)
                lc=m.lm_head(hc[:,-1]).float(); ln=m.lm_head(hn[:,-1]).float()
                diffs.append(float((lc-ln).abs().max())); tokens.append([int(lc.argmax(-1)),int(ln.argmax(-1))])
                t=m.model.get_input_embeddings()(ln.argmax(-1).reshape(1,1)); seq=t; full=torch.cat([full,t],1)
                r=torch.cat([r,r.new_tensor([-2])]); im=torch.cat([im,im.new_tensor([-1])])
                assert all(cache.layers[j].get_seq_length()==len(r)-1 for j in range(34))
            comparisons.append(dict(condition=cond,max_logit_diff=max(diffs),step_diffs=diffs,tokens=tokens,
                                    token_equal=all(x==y for x,y in tokens),within_tolerance=max(diffs)<=.125))
            del cache,hc,hn,lc,ln,seq,full
    cache_ok=all(x['token_equal'] and x['within_tolerance'] for x in comparisons)
    save(OUT/'tests'/(a.name+'_cache.json'),dict(created_at=now(),comparisons=comparisons,cache_enabled=cache_ok,
         tolerance=.125,fallback='no-cache 전체 prefix 재계산' if not cache_ok else None))
    if a.cache_only: return
    outputs=[]; cap=512
    for cond in ['S','A','N']:
        t=time.monotonic(); torch.cuda.reset_peak_memory_stats()
        tok,eos=generate(m,e,ro,ii,cond,cap,cache_enabled=cache_ok)
        outputs.append(dict(condition=cond,tokens=tok,text=proc.decode(tok,skip_special_tokens=True),eos=eos,
                     cap=cap,seconds=time.monotonic()-t,peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2))
        save(OUT/'tests'/f'{a.name}_{cond}_cap512.json',outputs[-1])
    if not all(x['eos'] for x in outputs):
        cap=1024
        for cond in ['S','A','N']:
            t=time.monotonic(); tok,eos=generate(m,e,ro,ii,cond,cap,cache_enabled=cache_ok)
            save(OUT/'tests'/f'{a.name}_{cond}_cap1024.json',dict(condition=cond,tokens=tok,text=proc.decode(tok,skip_special_tokens=True),eos=eos,seconds=time.monotonic()-t))
    save(OUT/'tests'/(a.name+'.json'),dict(created_at=now(),cap=cap,cache_enabled=cache_ok,passed=True,
         source_sha256=sha(__file__),note='EOS는 내용 정확도 gate가 아님. cap 증가는 계획상 1회만.'))

if __name__=='__main__': main()
