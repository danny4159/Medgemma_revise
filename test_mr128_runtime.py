"""실제 저장 record·실행기 보호 경로·JSONL 재개·CPU 공식 batch 입력 대조."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

from mr128_data import OUT,read,save,sha,utc
import mr128_gen as G


def main():
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    def rejects(name,fn):
        try:fn()
        except (ValueError,BlockingIOError,FileNotFoundError):check(name,True)
        else:check(name,False)
    request=read(OUT/'tech_requests.json')['requests'][0]
    _,rows=G.verify(OUT/'gen/tech_b2',allow_completed_archive=True)
    row=next(r for r in rows if r['id']==request['id'])
    cfg_sha=sha(OUT/'gen/tech_b2/config.json')
    G.verify_row(row,request,cfg_sha);check('real_record_provenance',True)
    rejects('changed_request_rejected',lambda:G.verify_row(row,dict(request,prompt=request['prompt']+' changed'),cfg_sha))
    rejects('changed_output_rejected',lambda:G.verify_row(dict(row,text='ABSENT'),request,cfg_sha))
    rejects('changed_config_rejected',lambda:G.verify_row(row,request,'0'*64))
    with tempfile.TemporaryDirectory(dir=OUT/'gen',prefix='cpu_runtime_') as t:
        root=Path(t);p=root/'torn.jsonl';valid=b'{"id":"one"}\n'
        p.write_bytes(valid+b'{"id":')
        check('torn_tail_repaired',G.jsonl(p,repair=True)==[{'id':'one'}] and p.read_bytes()==valid)
        check('torn_original_preserved',len(list(root.glob('torn.jsonl.torn.*')))==1)
        p.write_bytes(valid+b'BAD\n'+b'{"id":"two"}\n');rejects('middle_corruption_rejected',lambda:G.jsonl(p,repair=True))
        p.write_bytes(b'{"id":"one","id":"two"}\n');rejects('duplicate_keys_rejected',lambda:G.jsonl(p,repair=True))
        p.write_bytes(b'{"id":"one","score":NaN}\n');rejects('NaN_rejected',lambda:G.jsonl(p))
        p.write_bytes(valid+valid);rejects('duplicate_ID_rejected',lambda:G.jsonl(p))
        p.write_bytes(b'{"id":"one"}');rejects('missing_newline_uncommitted',lambda:G.jsonl(p))
        check('complete_unterminated_preserved',G.jsonl(p,repair=True)==[{'id':'one'}] and p.read_bytes()==valid)
        with p.open('ab') as f:f.write(b'{"id":"two"}\n')
        check('append_after_tail_resume',len(G.jsonl(p))==2)
        # 실제 launch 함수의 lock 및 완료/변조 분기. GPU 자식 생성은 반드시 차단한다.
        virtual=[dict(index=g,uuid='fixture-'+g,total_mib=200000,used_mib=0,free_mib=200000) for g in os.environ['CUDA_VISIBLE_DEVICES'].split(',')]
        with (root/'stage.lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.object(G,'gpu_info',return_value=virtual),patch.object(G.subprocess,'Popen',side_effect=AssertionError('GPU process must not start')):
                rejects('actual_launch_owner_rejected',lambda:G.launch(OUT/'tech_requests.json',root.name,batch=2))
        src=OUT/'gen/tech_b2'
        for name in ['config.json','worker0.jsonl','worker1.jsonl']:
            shutil.copyfile(src/name,root/name)
        c=read(src/'completion.json');c['artifacts']={str(root/n):sha(root/n) for n in ['config.json','worker0.jsonl','worker1.jsonl']}
        save(root/'completion.json',c)
        before={str(root/n):sha(root/n) for n in ['config.json','worker0.jsonl','worker1.jsonl','completion.json']}
        with patch.object(G,'gpu_info',return_value=virtual),patch.object(G.subprocess,'Popen',side_effect=AssertionError('completed run must not spawn')):
            check('actual_completed_launch_noop',G.launch(OUT/'tech_requests.json',root.name,batch=2)==0)
            check('completed_files_unchanged',all(sha(p)==h for p,h in before.items()))
            rejects('completed_wrong_batch_rejected',lambda:G.launch(OUT/'tech_requests.json',root.name,batch=1))
            worker=root/'worker0.jsonl';worker.write_bytes(worker.read_bytes()[:-10])
            rejects('completed_output_tamper_rejected',lambda:G.launch(OUT/'tech_requests.json',root.name,batch=2))
    # AutoProcessor의 실제 batch tensor를 single 입력의 명시적 stack/concat과 대조한다.
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import torch
    from transformers import AutoProcessor
    processor=AutoProcessor.from_pretrained(G.MODEL,revision=G.REV,cache_dir=G.CACHE,local_files_only=True)
    processor.tokenizer.padding_side='left';requests=read(OUT/'tech_requests.json')['requests']
    routing=[]
    for wid in [0,1]:
        assigned=requests[wid::2]
        for k in range(0,len(assigned),2):
            group=assigned[k:k+2];messages=[G.make_messages(r,G.native_images(r)) for r in group]
            singles=[processor.apply_chat_template(m,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt') for m in messages]
            batch=processor.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt',padding=True)
            ok=set(batch)==set(singles[0])==set(singles[1])
            details={}
            for key in batch:
                if isinstance(batch[key],torch.Tensor):
                    expected=torch.cat([s[key] for s in singles],dim=0)
                    details[key]=torch.equal(batch[key],expected)
                else:details[key]=batch[key]==singles[0][key]+singles[1][key]
            ok=ok and all(details.values());routing.append(dict(ids=[r['id'] for r in group],all_equal=ok,details=details))
    check('all16_batch_tensor_routing',len(routing)==8 and all(r['all_equal'] for r in routing))
    ok=all(c['passed'] for c in checks)
    save(OUT/'runtime_tests.json',dict(created_utc=utc(),all_pass=ok,checks=checks,batch_routing=routing,
         source_sha256=sha(__file__),generation_sha256=sha('mr128_gen.py'),GPU_model_calls=0,
         scope_ko='JSONL·변조·실제 launch 소유권/완료 분기와 CPU 공식 batch tensor 대조. GPU 부분재개는 tech_b2의 실제12→16건 기록으로 별도 확인.'))
    print('runtime checks',sum(c['passed'] for c in checks),'/',len(checks))
    return 0 if ok else 2


if __name__=='__main__':raise SystemExit(main())
