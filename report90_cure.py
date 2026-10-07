"""공식 MedGemma1+CURE GRG 경로를 새 provenance/재개 실행기에 연결한다."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import report90_gen_safe as S
from report86_common import ROOT,R85,BASE_REV,ADAPTER_REV,base_path,adapter_path_C,sha

C=S.C
old_protocol=C.protocol

def protocol(requests,checkpoint):
    assert checkpoint is None
    p=old_protocol(requests,checkpoint)
    p.update(model_revision=BASE_REV,adapter_revision=ADAPTER_REV,adapter_sha=sha(adapter_path_C()/'adapter_model.safetensors'),
        quantization='NF4 double quant bf16 compute/storage',input_transform='official CLAHE3 resize448',
        deterministic=False,chunk=None,prompt='Generate a grounded report.')
    p['code']['report90_cure.py']=sha(__file__)
    for f in sorted((R85/'official/minimal').rglob('*.py')):p['code'][str(f)]=sha(f)
    for r in json.loads(Path(requests).read_text()):assert r['prompt']==p['prompt']
    return p

def load():
    import torch
    import numpy as np
    from transformers import AutoProcessor,AutoModelForImageTextToText,BitsAndBytesConfig
    from peft import PeftModel
    torch.set_num_threads(4);torch.manual_seed(17)
    processor=AutoProcessor.from_pretrained(base_path('C'),local_files_only=True);processor.tokenizer.padding_side='left'
    model=AutoModelForImageTextToText.from_pretrained(base_path('C'),torch_dtype=torch.bfloat16,device_map={'':0},local_files_only=True,
        attn_implementation='sdpa',quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_quant_storage=torch.bfloat16))
    model=PeftModel.from_pretrained(model,str(adapter_path_C()),local_files_only=True)
    assert set(model.peft_config['default'].modules_to_save)=={'lm_head','embed_tokens'}
    sys.path.insert(0,str(R85/'official/minimal'))
    from vlm_research_kit.data.transforms_factory import create_image_transforms
    transform=create_image_transforms(use_model_specific_transforms=True,model_name='pil_with_augmentations',bbox_format='cxcywh',
        image_size=[448,448],is_train=False,augmenter_override_params={'apply_clahe':True,'clahe_clip_limit':[3.,3.]})
    def image(path):
        im=transform(path)['pixel_values'];assert np.array_equal(np.asarray(im),np.asarray(transform(path)['pixel_values']))
        return im,None,None
    C.G.load_image=image
    return torch,processor,model

S.protocol=protocol;C.protocol=protocol;C.load_model=load;C.__file__=__file__

if __name__=='__main__':
    os.environ['NO_ALBUMENTATIONS_UPDATE']='1'
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','launch']);p.add_argument('--requests',required=True);p.add_argument('--out',required=True)
    p.add_argument('--checkpoint');p.add_argument('--workers',type=int,default=2);p.add_argument('--shard',type=int,default=0);p.add_argument('--gpu');p.add_argument('--limit',type=int,default=0);p.add_argument('--peak-mib',type=int,default=12000)
    a=p.parse_args();raise SystemExit(C.worker(a) if a.command=='worker' else S.launch(a))
