"""공식 processor 경로·이미지 순서와 실제 생성 회귀 검사."""
import argparse,hashlib,json,numpy as np
from mr132_common import RES,read,save,sha,now
from mr132_run import MODEL,messages,input_tensor,verify_job

def tensor_checks():
    import torch
    torch.set_num_threads(4)
    from transformers import AutoProcessor
    proc=AutoProcessor.from_pretrained(MODEL,local_files_only=True);proc.tokenizer.padding_side='left'
    rr=read(RES/'requests/technical.json'); checks=[]
    subset=[r for r in rr if r['id'].endswith('single_0') or r['id'].endswith('pair_01')]
    for r in subset:
        wrapped=input_tensor(proc,[r])
        msg=messages(r); text=proc.apply_chat_template(msg,add_generation_prompt=True,tokenize=False)
        imgs=[c['image'] for c in msg[0]['content'] if c['type']=='image']
        official=proc(text=[text],images=imgs,return_tensors='pt',padding=True,add_special_tokens=False)
        eq=sorted(wrapped)==sorted(official) and all(torch.equal(wrapped[k],official[k]) for k in wrapped)
        assert eq and wrapped['pixel_values'].shape[0]==len(imgs)
        solo=torch.cat([proc.image_processor(images=[im],return_tensors='pt')['pixel_values'] for im in imgs])
        order=torch.equal(solo,wrapped['pixel_values']);assert order
        checks.append(dict(id=r['id'],official_keys={k:list(v.shape) for k,v in official.items()},tensors_equal=eq,image_order_equal=order,input_sha256=hashlib.sha256(wrapped['input_ids'].numpy().tobytes()).hexdigest(),pixel_sha256=hashlib.sha256(wrapped['pixel_values'].numpy().tobytes()).hexdigest()))
    save(RES/'tests/tensors.json',dict(created_at=now(),all_pass=True,checks=checks,source_sha256=sha(__file__)))
    print('공식 tensor·영상 순서',len(checks),'PASS')

def compare():
    a=verify_job(RES/'gen/pilot_b1',RES/'requests/pilot.json');b=verify_job(RES/'gen/pilot_b2',RES/'requests/pilot.json')
    tokens={r['id']:r['tokens'] for r in a};mismatch=[r['id'] for r in b if tokens[r['id']]!=r['tokens']]
    reports={}
    for name,records in [('batch1',a),('batch2',b)]:
        job=RES/'gen'/('pilot_b1' if name=='batch1' else 'pilot_b2');wall=sum(r['wall_s'] for r in records)
        result=sorted(job.glob('result_*.json'))[-1];allwall=read(result)['wall_s']
        resource=[]
        for p in job.glob('resources*.jsonl'):resource.extend(json.loads(l) for l in p.read_text().splitlines())
        reports[name]=dict(n_requests=len(records),loading_included_wall_s=allwall,loading_included_req_min=len(records)/allwall*60,generation_request_s=wall,generation_effective_req_min=len(records)/wall*120,peak_reserved_mib=max(r['peak_reserved_mib'] for r in records),peak_allocated_mib=max(r['peak_allocated_mib'] for r in records),observed_gpu_used_mib={g:max(int(x['used']) for r in resource for x in r['gpu'] if x['index']==g) for g in ['0','1']},by_kind={k:dict(n=sum(r['kind']==k for r in records),p95_s=float(np.quantile([r['wall_s'] for r in records if r['kind']==k],.95)),total_s=sum(r['wall_s'] for r in records if r['kind']==k),max_tokens=max(r['n_tokens'] for r in records if r['kind']==k)) for k in ['single','pair']},all_eos=all(r['eos'] for r in records))
    chosen=2 if not mismatch and reports['batch2']['loading_included_req_min']>reports['batch1']['loading_included_req_min'] and reports['batch2']['all_eos'] else 1
    peak=reports['batch'+str(chosen)]['peak_reserved_mib']
    save(RES/'tests/throughput.json',dict(created_at=now(),configs=reports,token_mismatches=mismatch,chosen_batch=chosen,chosen_workers=2,worker2_per_gpu_feasible=2*(peak+2048)<=24576-100,worker2_per_gpu_reason='실측 peak 합과 worker당2GiB 여유의 admission을 적용; batch2 출력/처리량 우선 비교',estimated_development_wall_s=(40*3*reports['batch'+str(chosen)]['by_kind']['single']['total_s']/6+40*6*reports['batch'+str(chosen)]['by_kind']['pair']['total_s']/6)/2,estimate_note='기술6 single+6 pair 평균 요청시간과 두 GPU 병렬 가정; 실제 큐 tail·loading 추가'))
    print('처리량',reports,'token mismatch',mismatch,'selected',chosen)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['tensors','compare']);a=ap.parse_args()
    tensor_checks() if a.mode=='tensors' else compare()
