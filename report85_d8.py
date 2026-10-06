"""iter_085 D8 실제 입력 검사·생성. 본평가 진입 허가는 별도다."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from report84_preflight import ROOT, UP, sha, save, BASE_REV, ADAPTER_REV


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--system', choices=['M15', 'B0', 'M1', 'M1G', 'C'], required=True)
    p.add_argument('--gpu', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert a.gpu in allowed
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['HF_HUB_OFFLINE'] = '1'
    out = Path(a.out).resolve()
    out.relative_to(ROOT/'results/iter_085')
    out.mkdir(parents=True, exist_ok=a.resume)
    lock = (out/'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail, read_records
    # 종료된 자기 shard만 복구한다. 다른 worker의 claim이나 출력은 변경하지 않는다.
    repair_tail(str(out/'outputs.jsonl'))
    import numpy as np
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
    from rsna_diag import generate as G, lora
    torch.set_num_threads(4)
    torch.manual_seed(17)
    dpath = ROOT/'results/iter_085/D8/inputs.json'
    rows = json.loads(dpath.read_text())
    for row in rows:
        assert sha(row['image']) == row['file_sha256']
    rawpath = ROOT/'results/iter_085/D8/raw_manifest.json'
    raw = {r['ImageID']: r for r in json.loads(rawpath.read_text())}
    is15 = a.system in ['M15', 'B0']
    base = (UP/'hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots'/G.MODEL_REVISION if is15
            else ROOT/'results/iter_085/models/models--google--medgemma-4b-it/snapshots'/BASE_REV)
    processor = AutoProcessor.from_pretrained(str(base), local_files_only=True)
    processor.tokenizer.padding_side = 'left'
    if is15:
        processor.image_processor.do_pan_and_scan = False
    kw = dict(torch_dtype=torch.bfloat16, device_map={'': 0}, local_files_only=True, attn_implementation='sdpa')
    if a.system in ['M1G', 'C']:
        kw['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_storage=torch.bfloat16)
    start = time.monotonic()
    model = AutoModelForImageTextToText.from_pretrained(str(base), **kw)
    adapter_digest = None
    if a.system == 'B0':
        ap = ROOT/'results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt'
        blob = torch.load(ap, map_location='cpu', weights_only=True)
        cfg = blob['config']
        lora.apply_lora(model, cfg['r'], cfg['alpha'], 0.)
        own = {n: v for n, v in model.named_parameters() if 'lora_' in n}
        assert set(own) == set(blob['state'])
        assert all(own[n].shape == v.shape for n,v in blob['state'].items())
        lora.load_lora_state(model, blob['state'])
        adapter_digest = lora.state_digest(lora.lora_state_dict(model))
        assert adapter_digest == 'e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11'
    elif a.system == 'C':
        from peft import PeftModel
        ap = ROOT/'results/iter_085/models/models--pamessina--medgemma-4b-it-cure/snapshots'/ADAPTER_REV
        model = PeftModel.from_pretrained(model, str(ap), local_files_only=True)
        assert set(model.peft_config['default'].modules_to_save) == {'lm_head','embed_tokens'}
        adapter_digest = sha(ap/'adapter_model.safetensors')
    model.eval()
    assert not any(m.training for m in model.modules())
    transform = None
    if a.system in ['M1G', 'C']:
        sys.path.insert(0,str(ROOT/'results/iter_085/official/minimal'))
        from vlm_research_kit.data.transforms_factory import create_image_transforms
        transform = create_image_transforms(use_model_specific_transforms=True, model_name='pil_with_augmentations',
            bbox_format='cxcywh', image_size=[448,448], is_train=False,
            augmenter_override_params={'apply_clahe':True,'clahe_clip_limit':[3.,3.]})
    manual = json.loads((ROOT/'results/manual_rsna_report_transfer_20261006/protocol.json').read_text())
    prompts = [('R', manual['prompt']), ('S',manual['prompt']+' Systematically review the lungs, pleura, cardiomediastinal silhouette, bones, and visible devices. Mention an abnormality only when supported by this image, and distinguish definite from uncertain findings.')] if is15 else [('R','Describe this X-ray')] if a.system=='M1' else [('G','Generate a grounded report.')]
    if a.system=='C':
        import ast
        src = ROOT/'results/iter_084/preflight_01/official/vlm_research_kit/data/datasets/chest_imagenome_dataset.py'
        locations = next(ast.literal_eval(n.value) for n in ast.parse(src.read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SUPPORTED_LOCATE_AND_DESCRIBE_LOCATIONS' for t in n.targets))
        assert len(locations)==29
        prompts += [(loc, f'Locate and describe the {loc}.') for loc in sorted(locations)]
    protocol = {'system':a.system,'base':str(base),'adapter_digest':adapter_digest,'seed':17,'caps':[1024,2048,4096],
        'prompts':prompts,'input_sha256':sha(dpath),'raw_sha256':sha(rawpath),'gpu':a.gpu,'logical_gpu':0,
        'python':sys.executable,'source_sha256':{str(ROOT/f):sha(ROOT/f) for f in ['report85_d8.py','rsna_diag/generate.py','rsna_diag/lora.py','rsna_diag/geometry.py']},
        'torch':torch.__version__,'scope':'D8 기술·규약 개발; 본평가 gate 아님'}
    if (out/'protocol.json').exists():
        assert a.resume and json.loads((out/'protocol.json').read_text()) == json.loads(json.dumps(protocol)), 'resume protocol mismatch'
    else:
        save(out/'protocol.json',protocol)
    pdig=sha(out/'protocol.json')
    existing=read_records(str(out/'outputs.jsonl'))
    expected={r['ImageID']+'|'+a.system+'|'+n for r in rows for n,_ in prompts}
    assert len(existing)==len({r['id'] for r in existing}), 'duplicate output'
    for rec in existing:
        assert rec['id'] in expected and rec['protocol_digest']==pdig
        assert rec['record_digest']==hashlib.sha256(json.dumps({k:v for k,v in rec.items() if k!='record_digest'},sort_keys=True).encode()).hexdigest(), 'record changed'
    done={r['id'] for r in existing}
    checks=[{'id':r['id'],'official_tensor_equal':True,'eos':r['attempts'][-1]['ended_eos']} for r in existing]
    eos=model.generation_config.eos_token_id
    eos=[eos] if isinstance(eos,int) else eos
    events=(out/'attempts.jsonl').open('a',buffering=1)
    events.write(json.dumps({'event':'start','pid':os.getpid(),'time':time.time(),'loading_s':time.monotonic()-start,'existing_n':len(existing)})+'\n')
    with (out/'outputs.jsonl').open('a',buffering=1) as f:
        for row in rows:
            assert sha(row['image'])==row['file_sha256']
            if transform:
                rr=raw[row['ImageID']]; assert sha(rr['raw_path'])==rr['sha256']
                im=transform(rr['raw_path'])['pixel_values']
                assert np.array_equal(np.asarray(im),np.asarray(transform(rr['raw_path'])['pixel_values']))
            else:
                im,_,_=G.load_image(row['image'])
            for name,prompt in prompts:
                rid=row['ImageID']+'|'+a.system+'|'+name
                if rid in done:
                    continue
                events.write(json.dumps({'event':'request_start','id':rid,'time':time.time()})+'\n')
                inp=G.build_inputs(processor,im,prompt)
                official=processor.apply_chat_template([{'role':'user','content':[{'type':'image','image':im},{'type':'text','text':prompt}]}],add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt',padding=True)
                assert set(inp)==set(official)
                assert all(torch.equal(inp[k],official[k]) for k in inp)
                attempts=[]
                for cap in [1024,2048,4096]:
                    result=G.generate(torch,processor,model,inp,cap,eos); attempts.append(result)
                    if result['ended_eos']: break
                rec={'id':row['ImageID']+'|'+a.system+'|'+name,'ImageID':row['ImageID'],'condition':name,
                    'protocol_digest':sha(out/'protocol.json'),'image_sha256':row['file_sha256'],
                    'text':processor.decode(result['suffix_ids'],skip_special_tokens=True),'attempts':attempts,
                    'input_ids':inp['input_ids'][0].tolist(),'pixel_sha256':hashlib.sha256(np.asarray(im).tobytes()).hexdigest()}
                rec['record_digest']=hashlib.sha256(json.dumps(rec,sort_keys=True).encode()).hexdigest()
                f.write(json.dumps(rec,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
                events.write(json.dumps({'event':'request_saved','id':rid,'time':time.time()})+'\n')
                checks.append({'id':rec['id'],'official_tensor_equal':True,'eos':result['ended_eos']})
                print(json.dumps({'done':len(checks),'total':len(rows)*len(prompts),'system':a.system,'tokens':result['n_new'],'seconds':result['runtime_s']}),flush=True)
    assert len(checks)==len({c['id'] for c in checks})==len(rows)*len(prompts)
    events.write(json.dumps({'event':'end','pid':os.getpid(),'time':time.time()})+'\n'); events.close()
    if (out/'completion.json').exists():
        old=json.loads((out/'completion.json').read_text())
        assert all(sha(out/n)==h for n,h in old['files'].items())
    else:
        save(out/'checks.json',checks)
        save(out/'completion.json',{'n':len(checks),'wall_s_current_attempt':time.monotonic()-start,'files':{n:sha(out/n) for n in ['protocol.json','outputs.jsonl','checks.json']},'experiment_complete':False,'cost_scope':'current attempt only; all start/save/end events in attempts.jsonl; interrupted in-flight cost not used for system comparison'})


if __name__=='__main__':
    main()
