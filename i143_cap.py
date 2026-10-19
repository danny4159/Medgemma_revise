"""선정 전에 최장 train 입력의 생성 길이/비용을 측정한다."""
import argparse
import time
import torch
from i143_model import load,inputs,embeds,generate
from i143_data import OUT
from i141_common import read,save,sha,now


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--condition',choices=['S','A','N'],required=True); ap.add_argument('--cap',type=int,choices=[512,1024],default=512); a=ap.parse_args()
    choice=read(OUT/'tests/cache_checks_a1_cache.json'); assert choice['cache_enabled'] is False
    proc,m=load(); row=max((r for r in read(OUT/'data_manifest.json')['rows'] if r['split']=='T'),key=lambda r:r['n_slices'])
    b,ro,ii,p=inputs(proc,row); e=embeds(m,b); del b
    torch.cuda.reset_peak_memory_stats(); t=time.monotonic()
    tok,eos=generate(m,e,ro,ii,a.condition,a.cap,cache_enabled=False)
    elapsed=time.monotonic()-t
    save(OUT/'tests'/f'cap_{a.condition}_{a.cap}.json',dict(created_at=now(),patient_id=row['patient_id'],condition=a.condition,
         tokens=tok,n_tokens=len(tok),eos=eos,text=proc.decode(tok,skip_special_tokens=True),cap=a.cap,cache_enabled=False,
         seconds=elapsed,peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,source_sha256=sha(__file__)))
    print('생성 길이 검사',a.condition,len(tok),eos,elapsed,flush=True)

if __name__=='__main__': main()
