"""기존 RSNA bbox SFT의 자유 판독문 전이: 고정 60명 paired pilot, 추가 학습 없음."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
RESEARCH=ROOT/'research'
OUT=RESEARCH/'results/manual_rsna_report_transfer_20261006'
PROMPT=('Describe the radiographic findings in this chest X-ray and provide a concise impression. '
        'Write a short radiology report with Findings and Impression sections in English. '
        'Base the report only on the image provided; do not assume clinical history or prior examinations.')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.replace(path)


def prepare():
    m=RESEARCH/'results/iter_016/manifests'
    sets=json.loads((m/'sets.json').read_text())
    labels=json.loads((m/'labels.json').read_text())
    images={r['id']:r for r in map(json.loads,(m/'infer_manifest.jsonl').read_text().splitlines())}
    train=json.loads((RESEARCH/'results/iter_010/manifests/train_ids.json').read_text())
    train_patients={x.split('_',1)[1] for x in train}
    full_images={r['id']:r for r in map(json.loads,(RESEARCH/'results/iter_010/manifests/infer_manifest.jsonl').read_text().splitlines())}
    train_hashes={full_images[x]['pixel_sha256'] for x in train if x in full_images}
    rows=[]
    for category in ('opacity','normal','not_normal_no_opacity'):
        ids=sorted(sets['E600'][category],key=lambda s:hashlib.sha256(('report-transfer-20261006|'+s).encode()).hexdigest())[:20]
        for id_ in ids:
            item=images[id_];lab=labels[id_]
            if lab['category']!=category or lab['patient'] in train_patients or item['pixel_sha256'] in train_hashes:
                raise ValueError('category or training leakage')
            path=RESEARCH/item['image']
            if sha(path)!=item['file_sha256']:
                raise ValueError('image hash mismatch')
            rows.append({**item,'image':str(path),'patient':lab['patient']})
    protocol={'version':1,'prompt':PROMPT,'caps':[512,1024],'n':len(rows),
              'selection':'20 per category from previously used E600; independent of report outputs; not fresh test',
              'adapter':str(RESEARCH/'results/iter_012/train/lr2e-4_s17/epoch_05'),
              'adapter_expected_digest':json.loads((m/'checkpoints.json').read_text())['B0']['digest'],
              'rows':rows,'source_sha256':{str(m/f):sha(m/f) for f in ('sets.json','labels.json','infer_manifest.jsonl','checkpoints.json')},
              'code_sha256':{str(f):sha(f) for f in (Path(__file__),RESEARCH/'rsna_diag/generate.py',RESEARCH/'rsna_diag/lora.py')}}
    if (OUT/'protocol.json').exists() and json.loads((OUT/'protocol.json').read_text())!=protocol:
        raise ValueError('existing protocol differs')
    save(OUT/'protocol.json',protocol)
    save(OUT/'labels.json',{r['id']:labels[r['id']] for r in rows})
    print('고정 완료:',len(rows),'명. 학습 환자 및 pixel hash 중복 없음.')


def worker(model_name,gpu):
    os.environ['CUDA_VISIBLE_DEVICES']=str(gpu)
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TOKENIZERS_PARALLELISM']='false'
    os.environ['OMP_NUM_THREADS']='4'
    import torch
    from transformers import AutoProcessor,AutoModelForImageTextToText
    sys.path.insert(0,str(RESEARCH))
    from rsna_diag import generate as G
    torch.set_num_threads(4);torch.manual_seed(42)
    torch.cuda.set_per_process_memory_fraction(.85)
    lock=open(OUT/f'{model_name}.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    protocol=json.loads((OUT/'protocol.json').read_text())
    for f,h in protocol['code_sha256'].items():
        if sha(f)!=h:raise ValueError('code changed')
    pdig=sha(OUT/'protocol.json')
    snap=ROOT/'hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots'/G.MODEL_REVISION
    proc=AutoProcessor.from_pretrained(str(snap),local_files_only=True)
    proc.image_processor.do_pan_and_scan=False
    model=AutoModelForImageTextToText.from_pretrained(str(snap),local_files_only=True,dtype=torch.bfloat16,
                                                   device_map='cuda',attn_implementation='sdpa')
    adapter=G.load_adapter(torch,model,protocol['adapter']) if model_name=='sft' else None
    if model_name=='sft' and adapter!=protocol['adapter_expected_digest']:
        raise ValueError('adapter differs from iter_016 audited checkpoint')
    model.eval()
    env=G.env_info(torch,proc,model)
    save(OUT/f'{model_name}_config.json',{'protocol_digest':pdig,'adapter_digest':adapter,'env':env})
    eos=model.generation_config.eos_token_id
    eos=[eos] if isinstance(eos,int) else eos
    dest=OUT/f'{model_name}.jsonl'
    existing=[json.loads(s) for s in dest.read_text().splitlines() if s] if dest.exists() else []
    wanted={r['id']:r for r in protocol['rows']}
    if len(existing)!=len({r['id'] for r in existing}):raise ValueError('duplicate outputs')
    for row in existing:
        if row['id'] not in wanted or row['protocol_digest']!=pdig or row['adapter_digest']!=adapter:
            raise ValueError('resume mismatch')
    done={r['id'] for r in existing}
    with open(dest,'a',buffering=1) as f:
        for i,row in enumerate(protocol['rows']):
            if row['id'] in done:continue
            if sha(row['image'])!=row['file_sha256']:raise ValueError('image changed')
            record=G.run_request(torch,proc,model,eos,row,'free_report',protocol['prompt'],caps=protocol['caps'])
            record.update(model=model_name,adapter_digest=adapter,protocol_digest=pdig,
                          text=proc.tokenizer.decode(record['suffix_ids'],skip_special_tokens=True),
                          patient=row['patient'])
            f.write(json.dumps(record)+'\n')
            print(json.dumps({'model':model_name,'done':i+1,'total':len(protocol['rows']),
                              'seconds':record['runtime_s_total'],'tokens':record['n_output_tokens'],
                              'eos':record['ended_eos']}),flush=True)
    records=[json.loads(s) for s in dest.read_text().splitlines() if s]
    if len(records)!=len(wanted) or {r['id'] for r in records}!=set(wanted):raise ValueError('incomplete')
    save(OUT/f'{model_name}_completed.json',{'time':time.time(),'n':len(records),'output_sha256':sha(dest),
                                          'protocol_digest':pdig,'adapter_digest':adapter,
                                          'n_truncated':sum(not r['ended_eos'] for r in records)})


def blind():
    records=[];key={}
    for name in ('base','sft'):
        for r in map(json.loads,(OUT/f'{name}.jsonl').read_text().splitlines()):
            anon=hashlib.sha256(('blind-report|'+r['id']+'|'+name).encode()).hexdigest()[:10]
            records.append({'id':anon,'text':r['text'],'truncated':not r['ended_eos']})
            key[anon]={'model':name,'patient_id':r['id']}
    records.sort(key=lambda r:r['id'])
    save(OUT/'blinded_reports.json',records)
    save(OUT/'blind_key.json',key)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','worker','blind'])
    p.add_argument('--model',choices=['base','sft']);p.add_argument('--gpu',type=int)
    a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='blind':blind()
    else:
        if a.model is None or a.gpu is None:p.error('worker requires model and gpu')
        worker(a.model,a.gpu)
