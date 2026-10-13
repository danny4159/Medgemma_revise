"""함수 변경 없는 SDK 실행과 관측용 generate hook의 실제 token·보고서를 대조한다."""
import argparse
import sys
from i142_common import *

def main(a):
    protocol=verify_protocol(RES/'protocol_main.json')
    row=next(r for r in read(RES/'inference_inputs.json') if r['patient_id']==a.patient)
    assert row['role']=='technical'
    out=RES/'tests/hook_control'/a.patient
    out.mkdir(parents=True)
    os.environ.update(AR70_GPT2=str(MODELS/'gpt2pm'),AR70_MAXLEN='300',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    os.chdir(SDK)
    sys.path.insert(0,str(SDK))
    import numpy as np
    import torch
    from inference.inferenceSdk import AutoRG_Brain,setup_seed
    masks=out/'direct_masks'
    masks.mkdir()
    cfg={'llm_folder':str(MODELS/'autorg/RG_v2'),'seg_folder':str(MODELS/'autorg'),
         'llm_chk':'AutoRG_Brain_RGv2','seg_chk':'AutoRG_Brain_SEG','output_dir':str(masks),'eval_mode':'region_segtool'}
    model=AutoRG_Brain([0],cfg)
    setup_seed(42)
    torch.backends.cudnn.benchmark=False
    direct=[]
    sdk_path=str(SDK/'inference/inferenceSdk.py')
    def info(x):
        if isinstance(x,torch.Tensor):
            x=x.detach().cpu().numpy()
        x=np.ascontiguousarray(x)
        return {'shape':list(x.shape),'dtype':str(x.dtype),'sha256':hashlib.sha256(x.tobytes()).hexdigest()}
    def trace(frame,event,arg):
        if frame.f_code.co_filename!=sdk_path or frame.f_code.co_name!='report':
            return None
        local=frame.f_locals
        if event=='line' and 'output' in local and 'region_features' in local and not direct:
            direct.append({'features':info(local['region_features']),'data':info(local['d']),
                           'predicted_masks':info(local['s']),'tokens':local['output'].detach().cpu().tolist()})
        return trace
    payload=[{'image':row['image'],'modal':'DWI'}]
    # SDK/model 함수를 교체하지 않고 report의 지역 변수만 읽는다.
    sys.settrace(trace)
    try:
        first=model.report(payload)
    finally:
        sys.settrace(None)
    assert direct
    second_masks=out/'hook_masks'
    second_masks.mkdir()
    model.segmodel.output_mask_dir=str(second_masks)
    original=model.trainer.llm_model.generate
    hooked=[]
    def observe(*args,**kwargs):
        value=original(*args,**kwargs)
        hooked.append({'features':info(args[0]),'tokens':value.detach().cpu().tolist()})
        return value
    model.trainer.llm_model.generate=observe
    setup_seed(42)
    torch.backends.cudnn.benchmark=False
    second=model.report(payload)
    checks={'token_equal':direct[0]['tokens']==hooked[0]['tokens'],
            'feature_equal':direct[0]['features']==hooked[0]['features'],
            'report_equal':first[0]['pred_report']==second[0]['pred_report'],
            'ab_mask_equal':sha(first[0]['ab_mask'])==sha(second[0]['ab_mask']),
            'ana_mask_equal':sha(first[0]['ana_mask'])==sha(second[0]['ana_mask'])}
    save(out/'check.json',{'patient_id':a.patient,'checks':checks,'all_pass':all(checks.values()),
       'direct_no_function_patch':True,'trace_scope':'SDK report 지역 변수만 읽음. 모델/전처리/generate 함수 교체 없음.',
       'direct':direct,'hook':hooked,'direct_report':first[0]['pred_report'],'hook_report':second[0]['pred_report'],
       'actual_call':payload,'protocol_digest':protocol['digest'],'source_sha256':sha(__file__)})
    assert all(checks.values())
    print(checks)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--patient',required=True)
    main(p.parse_args())
