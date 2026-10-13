"""관측·reference·평가 규약과 실제 코드 digest를 모델 출력 전에 잠근다."""
import argparse
from pathlib import Path
import subprocess
import sys
import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw
from transformers import AutoProcessor
from i141_common import HERE, RES, read, save, sha, now
from i141_spec import BASE_CONFIG, START_TOKEN, END_TOKEN, SEMANTIC_CONTRACT

CODE = ['i141_common.py', 'i141_spec.py', 'i141_run.py', 'i141_data.py', 'i141_prepare.py', 'i141_tech.py', 'i141_eval.py']
MODEL = HERE.parent / 'hf_cache/models--google--medgemma-1.5-4b-it/snapshots' / BASE_CONFIG['revision']


def prepare():
    assert read(RES/'data_gate.json')['passed'] is True
    full = read(RES/'requests/technical.json')
    selected = []
    for pid in [x['patient_id'] for x in read(RES/'data_manifest.json')['rows'][:2]]:
        rows = [r for r in full if r['patient_id'] == pid]
        for condition in ['S','A']:
            rr = [r for r in rows if r['condition']==condition]
            for r in [rr[len(rr)//2], rr[-1]]:
                if r not in selected:
                    selected.append(r)
    save(RES/'requests/technical_pilot.json', selected)
    proc = AutoProcessor.from_pretrained(MODEL, local_files_only=True)
    ids = {'start_id':proc.tokenizer.convert_tokens_to_ids(START_TOKEN),
           'end_id':proc.tokenizer.convert_tokens_to_ids(END_TOKEN)}
    assert proc.tokenizer.convert_ids_to_tokens(ids['start_id'])==START_TOKEN
    assert proc.tokenizer.convert_ids_to_tokens(ids['end_id'])==END_TOKEN
    save(RES/'tests/boundary_check.json', {'created_at':now(),'passed':True,'ids':ids,'tokenizer_files':{
         str(p):sha(p) for p in MODEL.iterdir() if p.is_file() and ('token' in p.name or 'processor' in p.name)}})
    baseline = read(HERE.parent/'agent/runs/iter_141/code_baseline.json')
    save(RES/'derivation_manifest.json', {'created_at':now(),'source_commit':'9157bb31ca641fe720bd2d5203780df82635d53d',
         'sources':{p:sha(HERE/p) for p in ['i136_run.py','i136_common.py','i136_spec.py']},
         'reuse_manifest':read(HERE.parent/'agent/runs/iter_141/reuse_manifest.json'),
         'reused_scope':'hash/claims/lock/model loading/token boundary only; former CLI paths/presence parser unused',
         'source_baseline_path':str(HERE.parent/'agent/runs/iter_141/code_baseline.json')})
    # 대표 native mask overlay는 입력이 아닌 감사 전용 파일이다.
    sheet = Image.new('RGB',(768,512))
    draw = ImageDraw.Draw(sheet)
    for i,row in enumerate(read(RES/'data_manifest.json')['rows'][:2]):
        mask = np.asanyarray(nib.as_closest_canonical(nib.load(row['mask']['path'])).dataobj)
        z = int(np.argmax(np.sum(mask>0,axis=(0,1))))
        iminfo = next(x for x in row['images'] if x['canonical_z']==z)
        im = Image.open(iminfo['path']).convert('RGB')
        overlay = im.copy()
        plane = np.flip((mask[:,:,z]>0).T,(0,1)).astype('uint8')*255
        plane = Image.fromarray(plane).resize((256,256),Image.Resampling.NEAREST)
        red = Image.new('RGB',(256,256),(255,0,0))
        overlay = Image.composite(Image.blend(im,red,0.4),im,plane)
        sheet.paste(im,(0,i*256)); sheet.paste(overlay,(256,i*256))
        draw.text((520,i*256+20),row['patient_id']+' z'+str(z),fill='white')
    sheet.save(RES/'tests/DWI_mask_audit.png')
    print({'technical_requests':len(selected),'image_counts':[len(x['images']) for x in selected]})


def lock(stage):
    from i141_run import request_file, config_for
    config = config_for(stage)
    inputs = [RES/'data_manifest.json', RES/'reference_locked.json', RES/'data_gate.json',
              RES/'selected_download_complete.json', RES/'range_catalog.json',request_file(stage),
              RES/'tests/boundary_check.json', HERE.parent/'agent/runs/iter_141/plan.json']
    inputs.extend(RES/'official'/x for x in ['ISLES22/global_finding.json','ISLES22/modal_wise_finding.json','train_val_test_split.json'])
    for row in read(RES/'data_manifest.json')['rows']:
        inputs.append(Path(row['source_path']))
        inputs.append(Path(row['mask']['path']))
        inputs.extend(Path(x['path']) for x in row['images'])
    gates = [RES/'data_gate.json',RES/'tests/boundary_check.json']
    if stage=='main':
        gates += [RES/'tests/technical_gate.json']
        inputs += [RES/'tests/runtime_checks.json',RES/'tests/throughput_choice.json']
    models = {str(p):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in MODEL.iterdir() if p.is_file()}
    proto = {'created_at':now(),'stage':stage,'config':config,'evaluation_contract':SEMANTIC_CONTRACT,
             'inputs':{str(p):sha(p) for p in inputs},'code':{str(HERE/p):sha(HERE/p) for p in CODE},
             'gates':{str(p):sha(p) for p in gates},'model_files':models,
             'scientific_rules': 'iter_141 plan unchanged; global DWI clauses explicitly linked before generation'}
    path = RES/f'protocol_lock_{stage}.json'
    save(path,proto)
    print({'lock_created_at':proto['created_at'],'sha256':sha(path),'stage':stage})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','lock'])
    parser.add_argument('--stage',choices=['technical','technical2048','main'],default='technical')
    args=parser.parse_args()
    prepare() if args.command=='prepare' else lock(args.stage)
