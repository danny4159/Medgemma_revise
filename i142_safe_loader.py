"""실제 재사용용 로더: 가중치 경로와 SDK가 쓰는 trainer 로그 경로를 분리한다."""
from i142_common import *

def config(output_dir):
    view=RES/'model_view'
    assert view.is_dir()
    for name in ('AutoRG_Brain_SEG.model','AutoRG_Brain_SEG.model.pkl','RG_v2/AutoRG_Brain_RGv2.model','RG_v2/AutoRG_Brain_RGv2.model.pkl'):
        link=view/'autorg'/name
        source=MODELS/'autorg'/name
        assert link.is_symlink() and link.resolve()==source.resolve()
    return {'llm_folder':str(view/'autorg/RG_v2'),'seg_folder':str(view/'autorg'),
        'llm_chk':'AutoRG_Brain_RGv2','seg_chk':'AutoRG_Brain_SEG','output_dir':str(output_dir),'eval_mode':'region_segtool'}

def check(out,patient=None):
    import sys
    out=Path(out).resolve()
    assert out.is_relative_to(RES)
    out.mkdir()
    old_logs={str(p):sha(p) for p in (MODELS/'autorg').rglob('*.txt')}
    os.environ.update(AR70_GPT2=str(MODELS/'gpt2pm'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    os.chdir(SDK)
    sys.path.insert(0,str(SDK))
    from inference.inferenceSdk import AutoRG_Brain
    model=AutoRG_Brain([0],config(out))
    checks={'old_logs_unchanged':old_logs=={str(p):sha(p) for p in (MODELS/'autorg').rglob('*.txt')},
         'seg_log_under_iter142':Path(model.segmodel.trainer.log_file).resolve().is_relative_to(RES),
         'new_seg_log_exists':Path(model.segmodel.trainer.log_file).is_file(),
         'seg_folder_under_iter142':Path(model.segmodel.trainer.output_folder).resolve().is_relative_to(RES)}
    generated=None
    if patient:
        from inference.inferenceSdk import setup_seed
        import torch
        row=next(r for r in read(RES/'inference_inputs.json') if r['patient_id']==patient)
        assert row['role']=='technical'
        setup_seed(42)
        torch.backends.cudnn.benchmark=False
        os.environ['AR70_MAXLEN']='300'
        generated_tokens=[]
        original=model.trainer.llm_model.generate
        def observe(*args,**kwargs):
            value=original(*args,**kwargs)
            generated_tokens.append(value.detach().cpu().tolist())
            return value
        model.trainer.llm_model.generate=observe
        payload=[{'image':row['image'],'modal':'DWI'}]
        result=model.report(payload)
        previous=read(RES/'jobs/tech_equivalence_v2'/patient/'result.json')
        checks['safe_report_matches_prior']=result[0]['pred_report']==previous['report']
        checks['safe_tokens_match_prior']=generated_tokens==[g['tokens'] for g in previous['observations']['generation']]
        checks['safe_masks_match_prior']=all(sha(result[0][key])==previous['masks'][key]['sha256'] for key in ['ab_mask','ana_mask'])
        checks['old_logs_unchanged_after_generation']=old_logs=={str(p):sha(p) for p in (MODELS/'autorg').rglob('*.txt')}
        generated={'patient_id':patient,'actual_call':payload,'report':result[0]['pred_report'],'tokens':generated_tokens,
                   'mask_hashes':{key:sha(result[0][key]) for key in ['ab_mask','ana_mask']}}
    save(out/'check.json',{'created_at':now(),'checks':checks,'all_pass':all(checks.values()),
        'old_logs':old_logs,'config':config(out),'source_sha256':sha(__file__),'generated':generated,
        'scope':'실제 GPU 로딩·로그 분리와 선택한 기술 사례의 전체 예측/판독 경로 검사. 개발 6명 본출력은 재생성하지 않음.'})
    assert all(checks.values())
    print(checks)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--patient')
    a=p.parse_args()
    check(a.out,a.patient)
