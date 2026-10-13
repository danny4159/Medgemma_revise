"""GT 없는 공식 DWI SDK 실행; 관측 hook은 인자와 반환값을 변경하지 않는다."""
import argparse
import sys
import time
import traceback
from i142_common import *

def run(a):
    protocol = verify_protocol(a.protocol)
    inputs = read(RES/'inference_inputs.json')
    row = next(x for x in inputs if x['patient_id']==a.patient)
    assert a.max_length in (300,600)
    assert a.max_length==protocol.get('max_length',protocol['technical_max_length'])
    if row['role']=='main':
        choice = read(RES/'execution_choice.json')
        assert choice['technical_pass'] and a.max_length==choice['max_length']
        assert protocol['files'][str(RES/'execution_choice.json')]==sha(RES/'execution_choice.json')
    out = Path(a.out).resolve()
    assert out.is_relative_to(RES)
    with ownership(out/'owner.lock'):
        if (out/'result.json').exists():
            verify_result(out/'result.json',protocol,row)
            print('검증된 완료 출력 재사용',a.patient,flush=True)
            return
        attempt = out / ('attempt_'+str(time.time_ns()))
        attempt.mkdir(parents=True)
        masks = attempt/'masks'
        masks.mkdir()
        # worker는 GT/정답 파일을 읽지 못한다. audit hook은 fork된 전처리에도 상속됨.
        access = []
        def audit(event,args):
            if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
                path = os.fsdecode(args[0])
                if 'derivatives/' in path or path.endswith('_msk.nii.gz') or any(s in path for s in ['reference_locked','global_finding','modal_wise_finding','eval/judgments']):
                    raise PermissionError('정답 접근 금지: '+path)
                if str(OLD/'data_selected') in path:
                    access.append(path)
                    assert path==row['image'], path
        sys.addaudithook(audit)
        os.environ['AR70_GPT2']=str(MODELS/'gpt2pm')
        os.environ['AR70_MAXLEN']=str(a.max_length)
        os.environ['HF_HUB_OFFLINE']='1'
        os.environ['TRANSFORMERS_OFFLINE']='1'
        os.chdir(SDK)
        sys.path.insert(0,str(SDK))
        import numpy as np
        import torch
        import nibabel as nib
        from inference.inferenceSdk import AutoRG_Brain, setup_seed
        assert torch.cuda.is_available() and torch.cuda.device_count()==1
        started=time.perf_counter()
        cfg={'llm_folder':str(MODELS/'autorg/RG_v2'),'seg_folder':str(MODELS/'autorg'),
             'llm_chk':'AutoRG_Brain_RGv2','seg_chk':'AutoRG_Brain_SEG','output_dir':str(masks),'eval_mode':'region_segtool'}
        rec={'status':'error','patient_id':a.patient,'protocol_digest':protocol['digest'],'input':row,
             'actual_call':[{'image':row['image'],'modal':'DWI'}], 'direct_sdk':a.direct,
             'created_at':now(),'pid':os.getpid(),'cuda_visible':os.environ['CUDA_VISIBLE_DEVICES']}
        try:
            model=AutoRG_Brain([0],cfg)
            rec['cudnn_from_checkpoint']={'benchmark':torch.backends.cudnn.benchmark,'deterministic':torch.backends.cudnn.deterministic}
            # 체크포인트가 nondeterministic kernel 설정을 복원한다. 동일 seed의 수치 대조를 위해 고정한다.
            setup_seed(42)
            torch.backends.cudnn.benchmark=False
            rec['execution_seed']=42
            rec['cudnn_execution']={'benchmark':False,'deterministic':True}
            torch.cuda.synchronize()
            rec['load_s']=time.perf_counter()-started
            rec['device']=torch.cuda.get_device_name(0)
            rec['environment']={'python':sys.executable,'torch':torch.__version__}
            torch.cuda.reset_peak_memory_stats()
            logs={'segmentation_inputs':[],'report_inputs':[],'generation':[],'regions':[]}
            def array_info(x):
                if isinstance(x,torch.Tensor):
                    x=x.detach().cpu().numpy()
                x=np.ascontiguousarray(x)
                return {'shape':list(x.shape),'dtype':str(x.dtype),'sha256':hashlib.sha256(x.tobytes()).hexdigest()}
            original_generate=model.trainer.llm_model.generate
            def generate(*args,**kwargs):
                output=original_generate(*args,**kwargs)
                tokens=output.detach().cpu().tolist()
                eos=model.trainer.tokenizer.eos_token_id
                logs['generation'].append({'features':array_info(args[0]),'tokens':tokens,
                    'eos_token_id':eos,'eos':[eos in t[1:] for t in tokens],
                    'max_length':kwargs['max_length'],'decoded':model.trainer.tokenizer.batch_decode(output,skip_special_tokens=True,clean_up_tokenization_spaces=True)})
                return output
            model.trainer.llm_model.generate=generate
            seg_predict=model.segmodel.trainer.predict_preprocessed_data_return_seg_and_softmax
            def seg(*args,**kwargs):
                logs['segmentation_inputs'].append({'data':array_info(args[0]),'modal':kwargs['modal']})
                return seg_predict(*args,**kwargs)
            model.segmodel.trainer.predict_preprocessed_data_return_seg_and_softmax=seg
            predict=model.trainer.predict_preprocessed_data_return_region_report
            def region(*args,**kwargs):
                logs['report_inputs'].append({'data':array_info(args[0]),'predicted_masks':array_info(args[1]),'regions':args[2], 'modal':kwargs['modal']})
                assert args[2] is None and kwargs['modal']=='DWI'
                output=predict(*args,**kwargs)
                logs['regions'].append(output[1])
                return output
            model.trainer.predict_preprocessed_data_return_region_report=region
            seg_fn=model.segmodel.seg
            def seg_call(images,ab,ana,modals):
                assert images==[[row['image']]] and ab==[None] and ana==[None] and modals==['DWI']
                rec['seg_call']={'images':images,'ab':ab,'ana':ana,'modals':modals}
                return seg_fn(images,ab,ana,modals)
            model.segmodel.seg=seg_call
            # direct와 wrapper 차이는 입력 allowlist 검사뿐이다. 위 관측 hook은 동일.
            def wrapper(payload):
                assert len(payload)==1 and set(payload[0])=={'image','modal'}
                return model.report(payload)
            tick=time.perf_counter()
            result=model.report(rec['actual_call']) if a.direct else wrapper(rec['actual_call'])
            torch.cuda.synchronize()
            rec['inference_s']=time.perf_counter()-tick
            assert len(result)==1 and result[0]['image']==[row['image']]
            rec['report']=result[0]['pred_report']
            rec['observations']=logs
            assert logs['generation'], '공식 경로에 실제 생성 없음'
            rec['complete']=all(all(g['eos']) for g in logs['generation'])
            rec['cap_hit']=any(not e and len(t)>=a.max_length-1 for g in logs['generation'] for t,e in zip(g['tokens'],g['eos']))
            rec['peak_reserved_MiB']=torch.cuda.max_memory_reserved()/2**20
            rec['peak_allocated_MiB']=torch.cuda.max_memory_allocated()/2**20
            rec['masks']={}
            image=nib.load(row['image'])
            for key in ['ab_mask','ana_mask']:
                p=Path(result[0][key])
                m=nib.load(p)
                assert m.shape==image.shape and np.allclose(m.affine,image.affine,atol=1e-4)
                rec['masks'][key]={'path':str(p),'sha256':sha(p),'shape':list(m.shape),'affine':m.affine.tolist(),
                                  'foreground_voxels':int(np.count_nonzero(np.asarray(m.dataobj)))}
            rec['outputs']={v['path']:v['sha256'] for v in rec['masks'].values()}
            if a.equivalence:
                first_logs=logs
                logs={'segmentation_inputs':[],'report_inputs':[],'generation':[],'regions':[]}
                repeat_masks=attempt/'equivalence_masks'
                repeat_masks.mkdir()
                model.segmodel.output_mask_dir=str(repeat_masks)
                setup_seed(42)
                torch.backends.cudnn.benchmark=False
                repeated=wrapper(rec['actual_call'])
                checks={'segmentation_tensors':first_logs['segmentation_inputs']==logs['segmentation_inputs'],
                        'report_tensors':first_logs['report_inputs']==logs['report_inputs'],
                        'features_and_tokens':first_logs['generation']==logs['generation'],
                        'region_names':first_logs['regions']==logs['regions'],
                        'report':result[0]['pred_report']==repeated[0]['pred_report']}
                eq={'checks':checks,'all_pass':all(checks.values()),'direct':first_logs,'wrapper':logs,
                    'report':repeated[0]['pred_report'],'scope':'同一 seed·결정적 kernel의 공식 SDK 직접 호출 대 allowlist wrapper'}
                save(attempt/'equivalence.json',eq)
                rec['equivalence_path']=str(attempt/'equivalence.json')
                rec['outputs'][rec['equivalence_path']]=sha(attempt/'equivalence.json')
                assert eq['all_pass'], '공식 SDK 대조 실패'
            rec['status']='ok'
        except Exception:
            rec['error']=traceback.format_exc()
            rec['outputs']={}
        rec['image_access']=sorted(set(access))
        rec['wall_including_load_before_result_save_s']=time.perf_counter()-started
        rec['record_digest']=digest(rec)
        save(attempt/'record.json',rec)
        if rec['status']=='ok':
            save(out/'result.json',rec)
        finished=time.perf_counter()
        save(attempt/'timing.json',{'end_to_end_s':finished-started,'result_saved':rec['status']=='ok',
                                   'record_sha256':sha(attempt/'record.json')})
        print(a.patient,rec['status'],round(finished-started,2),flush=True)
        if rec['status']!='ok':
            print(rec['error'],flush=True)
            raise RuntimeError('SDK 실행 실패')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--patient',required=True)
    p.add_argument('--protocol',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--max-length',type=int,default=300)
    p.add_argument('--direct',action='store_true')
    p.add_argument('--equivalence',action='store_true')
    run(p.parse_args())
