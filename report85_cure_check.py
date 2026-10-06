"""CURE PEFT 저장 모듈과 공식 notebook 직접 생성 대조. 별도 단회 검사."""
import json
import os
from pathlib import Path
import sys
from report84_preflight import ROOT, BASE_REV, ADAPTER_REV, sha, save


def main():
    gpu=sys.argv[1]
    assert gpu in os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    os.environ['CUDA_VISIBLE_DEVICES']=gpu
    os.environ['HF_HUB_OFFLINE']='1'
    out=ROOT/'results/iter_085/cure_check'
    out.mkdir(exist_ok=False)
    import torch
    from transformers import AutoModelForImageTextToText,AutoProcessor,BitsAndBytesConfig
    from peft import PeftModel,get_peft_model_state_dict
    from safetensors.torch import load_file
    torch.set_num_threads(4); torch.manual_seed(17)
    base=ROOT/'results/iter_085/models/models--google--medgemma-4b-it/snapshots'/BASE_REV
    adapter=ROOT/'results/iter_085/models/models--pamessina--medgemma-4b-it-cure/snapshots'/ADAPTER_REV
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_use_double_quant=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_quant_storage=torch.bfloat16)
    model=AutoModelForImageTextToText.from_pretrained(str(base),local_files_only=True,quantization_config=quant,torch_dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa')
    model=PeftModel.from_pretrained(model,str(adapter),local_files_only=True)
    model.eval()
    expected=load_file(str(adapter/'adapter_model.safetensors'))
    actual=get_peft_model_state_dict(model)
    assert set(expected)==set(actual), 'PEFT key mismatch'
    bad=[k for k in expected if expected[k].shape!=actual[k].shape or not torch.equal(expected[k].float(),actual[k].detach().cpu().float())]
    assert not bad, bad[:5]
    saved=[k for k in expected if 'embed_tokens' in k or 'lm_head' in k]
    assert len(saved)>=2
    del expected,actual
    proc=AutoProcessor.from_pretrained(str(base),local_files_only=True)
    proc.tokenizer.padding_side='left'
    sys.path.insert(0,str(ROOT/'results/iter_085/official/minimal'))
    from vlm_research_kit.data.transforms_factory import create_image_transforms
    trans=create_image_transforms(use_model_specific_transforms=True,model_name='pil_with_augmentations',bbox_format='cxcywh',image_size=[448,448],is_train=False,augmenter_override_params={'apply_clahe':True,'clahe_clip_limit':[3.,3.]})
    raw=json.loads((ROOT/'results/iter_085/D8/raw_manifest.json').read_text())[0]
    assert sha(raw['raw_path'])==raw['sha256']
    im=trans(raw['raw_path'])['pixel_values']
    messages=[{'role':'user','content':[{'type':'image','image':im},{'type':'text','text':'Generate a grounded report.'}]}]
    inp=proc.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt',padding=True).to(model.device)
    with torch.inference_mode():
        ids=model.generate(**inp,max_new_tokens=1024,do_sample=False)[0,inp['input_ids'].shape[1]:].tolist()
    ref=json.loads((ROOT/'results/iter_085/D8/C/outputs.jsonl').read_text().splitlines()[0])
    result={'strict_keys_shapes_values':True,'saved_modules':saved,'source_sha256':sha(__file__),'adapter_sha256':sha(adapter/'adapter_model.safetensors'),'official_suffix_ids':ids,'wrapper_suffix_ids':ref['attempts'][0]['suffix_ids'],'token_equal':ids==ref['attempts'][0]['suffix_ids'],'official_input_ids_equal':inp['input_ids'][0].tolist()==ref['input_ids'],'pass':ids==ref['attempts'][0]['suffix_ids'] and inp['input_ids'][0].tolist()==ref['input_ids']}
    save(out/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('ids')},ensure_ascii=False))
    return 0 if result['pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
