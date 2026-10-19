"""no-cache 결과를 덮어쓰지 않고 고정 1024 cap까지 재개한다."""
import argparse
import copy
import time
import torch
from i143_model import load,inputs,embeds,generate as original_generate
from i143_nocache import generate
from i143_data import OUT
from i143_runtime import save
from i141_common import read,sha,now


def main():
    p=argparse.ArgumentParser(); p.add_argument('--condition',choices=['S','A','N'],required=True); a=p.parse_args()
    proc,m=load(); rows=[r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='T']
    test=copy.deepcopy(rows[0]); test['images']=test['images'][:2]
    b,ro,ii,prefix=inputs(proc,test); e=embeds(m,b); checks=[]
    for condition in ['S','A','N']:
        full,feos=original_generate(m,e,ro,ii,condition,6,cache_enabled=False)
        resumed,reos=generate(m,e,ro,ii,condition,6,initial_tokens=full[:3])
        assert full==resumed and feos==reos
        checks.append(dict(condition=condition,full=full,resumed=resumed,equal=True))
    save(OUT/'tests'/f'cap_{a.condition}_resume_checks.json',dict(created_at=now(),passed=True,checks=checks,
         source_sha256=sha('i143_nocache.py'),model_source_sha256=sha('i143_model.py')))
    del b,e; torch.cuda.empty_cache()
    row=max(rows,key=lambda r:r['n_slices']); b,ro,ii,prefix=inputs(proc,row); e=embeds(m,b); del b
    config=dict(patient_id=row['patient_id'],condition=a.condition,cap=1024,cache_enabled=False,
         image_hashes=[im['sha256'] for im in row['images']],model_source_sha256=sha('i143_model.py'),source_sha256=sha('i143_nocache.py'))
    d=OUT/'tests'/f'cap_{a.condition}_1024_progress'; d.mkdir(exist_ok=True)
    if (d/'config.json').exists(): assert read(d/'config.json')==config
    else: save(d/'config.json',config)
    initial=[]; parent=None; prior=OUT/'tests'/f'cap_{a.condition}_512.json'
    if prior.exists():
        old=read(prior); assert old['condition']==a.condition and old['patient_id']==row['patient_id'] and old['cache_enabled'] is False
        initial=old['tokens']; parent=dict(path=str(prior),sha256=sha(prior),seconds=old['seconds'])
    for path in sorted(d.glob('tokens_*.json')):
        item=read(path); assert item['tokens'][:len(initial)]==initial
        initial=item['tokens']
    t=time.monotonic(); torch.cuda.reset_peak_memory_stats()
    def checkpoint(tokens):
        path=d/f'tokens_{len(tokens):04d}.json'
        if path.exists(): assert read(path)['tokens']==tokens
        else: save(path,dict(created_at=now(),tokens=list(tokens),seconds=time.monotonic()-t))
        print('token checkpoint',a.condition,len(tokens),flush=True)
    tok,eos=generate(m,e,ro,ii,a.condition,1024,initial_tokens=initial,progress=checkpoint)
    save(OUT/'tests'/f'cap_{a.condition}_1024.json',dict(created_at=now(),**{k:v for k,v in config.items() if k not in ['source_sha256']},
         tokens=tok,n_tokens=len(tok),eos=eos,text=proc.decode(tok,skip_special_tokens=True),seconds=time.monotonic()-t,
         peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,source_sha256=sha(__file__),parent=parent,resumed_tokens=len(initial)))


if __name__=='__main__':main()
