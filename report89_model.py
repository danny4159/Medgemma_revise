"""iter_089 판독/후속 위치 CE. 기존 LoRA와 processor 함수를 제한 재사용한다."""
import os
from pathlib import Path
import json
import hashlib
import subprocess

from report86_common import base_path, manual_prompt, sha, save
from rsna_diag import generate, lora, sft_data

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/iter_089'
CFG=dict(r=16,alpha=32,dropout=0.05,weight_decay=0.01,betas=[0.9,0.999],eps=1e-8,
         grad_clip=1.,effective_batch=8,seed=17,precision='bf16 base; fp32 LoRA and CE',
         normalization='patient report token mean + lambda * patient grounding token mean; batch patient mean',
         attention='sdpa', report_prompt=manual_prompt())


def environment(gpu):
    allowed=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    assert gpu in allowed, (gpu,allowed)
    smi=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,pci.bus_id,memory.total,memory.used,memory.free','--format=csv,noheader,nounits'],text=True)
    row=next(s.split(', ') for s in smi.strip().splitlines() if s.split(', ')[0]==gpu)
    assert int(row[-1]) >= 16000, ('insufficient memory',row)
    os.environ['CUDA_VISIBLE_DEVICES']=gpu
    for var,name in dict(HF_HOME='hf',HF_HUB_CACHE='hf/hub',HF_XET_CACHE='hf/xet',XDG_CACHE_HOME='xdg',
                         TORCH_HOME='torch',TORCHINDUCTOR_CACHE_DIR='inductor',TRITON_CACHE_DIR='triton',
                         CUDA_CACHE_PATH='cuda',TMPDIR='tmp').items():
        p=OUT/'runtime_cache'/name;p.mkdir(parents=True,exist_ok=True);os.environ[var]=str(p)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
    os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
    return dict(allowed=allowed,physical_gpu=gpu,logical_gpu=0,nvidia_smi=smi)


def load():
    import torch
    from transformers import AutoProcessor,AutoModelForImageTextToText
    torch.set_num_threads(4)
    torch.manual_seed(17)
    proc=AutoProcessor.from_pretrained(base_path('M15'),local_files_only=True)
    proc.image_processor.do_pan_and_scan=False
    model=AutoModelForImageTextToText.from_pretrained(base_path('M15'),local_files_only=True,
              dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa')
    names=lora.apply_lora(model,16,32,0.05,seed=17)
    assert len(names)==238
    assert all(('lora_' in n)==p.requires_grad for n,p in model.named_parameters())
    model.config.use_cache=False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    return torch,proc,model


def ground_target(row,epoch):
    fs=[f for f in row['findings'] if f.get('abnormal') is True and f.get('boxes')]
    if not fs:return None
    # 고정 환자 hash 시작점에서 epoch별 순환; 같은 epoch의 R/G는 동일하다.
    start=int(hashlib.sha256(row['PatientID'].encode()).hexdigest(),16)%len(fs)
    f=fs[(start+epoch)%len(fs)]
    prompt='Locate the finding described by this sentence: '+f['sentence_en']+' Return JSON boxes with box_2d in [ymin, xmin, ymax, xmax] coordinates from 0 to 1000 and label "finding".'
    target=json.dumps([dict(box_2d=b,label='finding') for b in sft_data.target_boxes(f['canvas_boxes'])])
    return prompt,target,f['source_index']


def example(proc,row,epoch=0,full=True):
    import torch
    assert sha(row['image'])==row['file_sha256']
    image,_,_=generate.load_image(row['image'])
    one=sft_data.build_example(proc,image,CFG['report_prompt'],row['report'])
    gr=ground_target(row,epoch) if full else None
    if gr:
        msgs=[dict(role='user',content=[dict(type='image',image=image),dict(type='text',text=CFG['report_prompt'])]),
              dict(role='assistant',content=[dict(type='text',text=row['report'])]),
              dict(role='user',content=[dict(type='text',text=gr[0])])]
        prefix=proc.apply_chat_template(msgs,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt')
        msgs.append(dict(role='assistant',content=[dict(type='text',text=gr[1])]))
        batch=proc.apply_chat_template(msgs,add_generation_prompt=False,tokenize=True,return_dict=True,return_tensors='pt')
        ids=batch['input_ids'][0];n=len(one['input_ids']);ng=prefix['input_ids'].shape[1]
        assert torch.equal(ids[:n],one['input_ids']) and torch.equal(ids[:ng],prefix['input_ids'][0])
        assert torch.equal(batch['pixel_values'],one['pixel_values'])
        assert proc.tokenizer.decode(ids[ng:].tolist(),skip_special_tokens=False)==gr[1]+'<end_of_turn>\n'
        ex={k:(v if k=='pixel_values' else v[0]) for k,v in batch.items()}
        report=torch.full_like(ids,-100);report[:n]=one['labels']
        ground=torch.full_like(ids,-100);ground[ng:-1]=ids[ng:-1]
    else:
        ex={k:v for k,v in one.items() if k not in ('labels','n_prefix')}
        report=one['labels'];ground=torch.full_like(report,-100)
    assert not ((report!=-100)&(ground!=-100)).any()
    ex.update(labels=torch.where(report!=-100,report,ground),report_labels=report,ground_labels=ground)
    return ex


def batch(exs,pad_id):
    import torch
    b=sft_data.collate(exs,pad_id)
    for name in ('report_labels','ground_labels'):
        b[name]=torch.full_like(b['labels'],-100)
        for i,e in enumerate(exs):b[name][i,:len(e[name])]=e[name]
    return {k:(v.cuda().to(torch.bfloat16) if k=='pixel_values' else v.cuda()) for k,v in b.items()}


def losses(model,b,lam,return_logits=False):
    import torch
    inp={k:v for k,v in b.items() if k not in ('labels','report_labels','ground_labels')}
    hidden=model.model(**inp,use_cache=False).last_hidden_state[:,:-1]
    labels=b['labels'][:,1:];sel=labels!=-100
    logits=model.lm_head(hidden[sel]).float()
    cap=getattr(model.config.get_text_config(),'final_logit_softcapping',None)
    if cap:logits=cap*torch.tanh(logits/cap)
    ce=torch.nn.functional.cross_entropy(logits,labels[sel],reduction='none')
    indices=sel.nonzero()[:,0]
    vals=[]
    for name in ('report_labels','ground_labels'):
        mask=b[name][:,1:][sel]!=-100
        sums=torch.zeros(labels.shape[0],device=ce.device).index_add(0,indices,ce*mask)
        counts=(b[name][:,1:]!=-100).sum(1)
        vals.append(sums/counts.clamp_min(1))
    loss=(vals[0]+lam*vals[1]).mean()
    if return_logits:return loss,vals,logits,b['report_labels'][:,1:][sel]!=-100
    return loss,vals
