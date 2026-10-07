"""새 판독/grounding 요청의 고정 shard 생성. 완료 전 전체 provenance 재검증."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import hashlib
from report86_common import sha,sha_obj,save,record_digest,read_jsonl_complete
from report90_numeric import OUT
import report89_model as M
from report90_train import load_model
from rsna_diag import generate as G

SOURCES=['report90_gen.py','report90_train.py','report90_stable.py','report90_numeric.py','report89_model.py','rsna_diag/generate.py','rsna_diag/lora.py']

def protocol(requests,checkpoint):
    return dict(requests_sha=sha(requests),checkpoint=None if checkpoint is None else str(Path(checkpoint).resolve()),
        checkpoint_sha=None if checkpoint is None else sha(checkpoint),model_revision=G.MODEL_REVISION,
        seed=17,caps=[1024,2048,4096],chunk=64,deterministic=True,code={f:sha(f) for f in SOURCES})

def verify(out,requests,proto,workers):
    out=Path(out);rows=json.loads(Path(requests).read_text());expected={r['id']:r for r in rows};assert len(expected)==len(rows)
    assert protocol(requests,proto['checkpoint'])==proto
    got=[]
    for s in range(workers):
        file=out/f'worker_{s}.jsonl'
        if file.exists() and file.read_bytes() and not file.read_bytes().endswith(b'\n'):raise ValueError('torn tail requires owned repair')
        for rec in read_jsonl_complete(file):
            assert rec['id'] in expected;req=expected[rec['id']]
            assert rec['protocol_digest']==sha_obj(proto) and rec['request_digest']==sha_obj(req)
            assert rec['record_digest']==record_digest(rec) and rec['image_sha256']==sha(req['image'])==req['file_sha256']
            assert rows.index(req)%workers==s;got.append(rec)
    assert len(got)==len({r['id'] for r in got})
    return got,expected

def worker(a):
    out=Path(a.out).resolve();out.relative_to(OUT);out.mkdir(parents=True,exist_ok=True)
    proto=protocol(a.requests,a.checkpoint);cfg=out/'protocol.json';assert json.loads(cfg.read_text())==proto
    assert json.loads((out/'mapping.json').read_text())['workers']==a.workers
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert a.gpu in allowed
    os.environ['CUDA_VISIBLE_DEVICES']=a.gpu;M.OUT=OUT
    # cache 격리, 생성 메모리 admission은 parent가 실제 점유와 예약량을 합산한다.
    for var,name in dict(HF_HOME='hf',HF_HUB_CACHE='hf/hub',HF_XET_CACHE='hf/xet',XDG_CACHE_HOME='xdg',TORCH_HOME='torch',TMPDIR='tmp',CUDA_CACHE_PATH='cuda').items():
        p=OUT/'runtime_cache'/name;p.mkdir(parents=True,exist_ok=True);os.environ[var]=str(p)
    os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8';os.environ['HF_HUB_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
    with (out/f'worker_{a.shard}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from pg43_run import repair_tail
        repair_tail(str(out/f'worker_{a.shard}.jsonl'))
        allrows=json.loads(Path(a.requests).read_text());rows=allrows[a.shard::a.workers]
        expected={r['id']:r for r in rows};old=read_jsonl_complete(out/f'worker_{a.shard}.jsonl')
        assert len(old)==len({r['id'] for r in old})
        for rec in old:
            assert rec['id'] in expected;req=expected[rec['id']]
            assert rec['protocol_digest']==sha_obj(proto) and rec['request_digest']==sha_obj(req) and rec['record_digest']==record_digest(rec)
            assert sha(req['image'])==req['file_sha256']==rec['image_sha256']
        for req in rows:assert sha(req['image'])==req['file_sha256']
        done={r['id'] for r in old};todo=[r for r in rows if r['id'] not in done]
        if not todo:return
        torch,proc,model=load_model()
        if a.checkpoint:
            ck=torch.load(a.checkpoint,map_location='cpu',weights_only=False);M.lora.load_lora_state(model,ck['adapter'])
            assert M.lora.state_digest(M.lora.lora_state_dict(model))==ck['digests']['adapter']
            del ck
        model.eval();eos=model.generation_config.eos_token_id;eos=[eos] if isinstance(eos,int) else eos
        saved=0
        with (out/f'worker_{a.shard}.jsonl').open('a') as f:
            for req in todo:
                image,_,_=G.load_image(req['image']);inp=G.build_inputs(proc,image,req['prompt'])
                official=proc.apply_chat_template([dict(role='user',content=[dict(type='image',image=image),dict(type='text',text=req['prompt'])])],add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt',padding=True)
                assert set(inp)==set(official) and all(torch.equal(inp[k],official[k]) for k in inp)
                attempts=[]
                for cap in proto['caps']:
                    result=G.generate(torch,proc,model,inp,cap,eos);attempts.append(result)
                    if result['ended_eos']:break
                rec=dict(id=req['id'],request_digest=sha_obj(req),protocol_digest=sha_obj(proto),image_sha256=req['file_sha256'],
                    input_ids=inp['input_ids'][0].tolist(),text=proc.decode(result['suffix_ids'],skip_special_tokens=True),attempts=attempts,
                    gpu=a.gpu,shard=a.shard)
                rec['record_digest']=record_digest(rec);f.write(json.dumps(rec,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
                saved+=1;print(json.dumps(dict(shard=a.shard,saved=saved,of=len(todo),tokens=result['n_new'])),flush=True)
                if a.limit and saved>=a.limit:return

def launch(a):
    out=Path(a.out).resolve();out.relative_to(OUT);out.mkdir(parents=True,exist_ok=True)
    with (out/'launcher.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        proto=protocol(a.requests,a.checkpoint)
        for path,value in [(out/'protocol.json',proto),(out/'mapping.json',dict(workers=a.workers))]:
            if path.exists():assert json.loads(path.read_text())==value
            else:save(path,value)
        existing,expected=verify(out,a.requests,proto,a.workers)
        if len(existing)==len(expected):
            cp=out/'completion.json'
            completion=dict(n=len(existing),protocol_digest=sha_obj(proto),files={str(out/f'worker_{s}.jsonl'):sha(out/f'worker_{s}.jsonl') for s in range(a.workers)})
            if cp.exists():assert json.loads(cp.read_text())==completion
            else:save(cp,completion)
            return 0
        allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');procs=[];logs=[];attempt=len(list(out.glob('launch_*.json')))
        start=time.monotonic()
        try:
            for s in range(a.workers):
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free','--format=csv,noheader,nounits'],text=True)
                free={x.split(',')[0].strip():int(x.split(',')[1]) for x in raw.splitlines()}
                usage=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],text=True)
                actual={int(x.split(',')[0]):int(x.split(',')[1]) for x in usage.splitlines() if x.strip()}
                # 실제 점유는 free에 이미 반영됨. 아직 적재되지 않은 예약분과 worker별 여유만 추가 차감한다.
                choices={g:free[g]-sum(max(0,a.peak_mib-actual.get(p.pid,0))+2048 for _,p,gg in procs if gg==g and p.poll() is None) for g in allowed}
                gpu=max(choices,key=choices.get);assert choices[gpu]>=a.peak_mib+2048,('memory admission',choices)
                cmd=[sys.executable,__file__,'worker','--requests',a.requests,'--out',str(out),'--gpu',gpu,'--shard',str(s),'--workers',str(a.workers)]
                if a.checkpoint:cmd+=['--checkpoint',a.checkpoint]
                if a.limit:cmd+=['--limit',str(a.limit)]
                so=(out/f'launch{attempt}_worker{s}.stdout.log').open('x');se=(out/f'launch{attempt}_worker{s}.stderr.log').open('x');logs.extend([so,se])
                procs.append((s,subprocess.Popen(cmd,stdout=so,stderr=se),gpu))
            codes={s:p.wait() for s,p,_ in procs}
        finally:
            for _,p,_ in procs:
                if p.poll() is None:p.terminate()
            for _,p,_ in procs:p.wait()
            for f in logs:f.close()
        save(out/f'launch_{attempt:03}.json',dict(codes=codes,wall_s=time.monotonic()-start,mapping={s:g for s,_,g in procs},protocol_digest=sha_obj(proto)))
        assert all(c==0 for c in codes.values())
        recs,expected=verify(out,a.requests,proto,a.workers)
        if len(recs)==len(expected):save(out/'completion.json',dict(n=len(recs),protocol_digest=sha_obj(proto),files={str(out/f'worker_{s}.jsonl'):sha(out/f'worker_{s}.jsonl') for s in range(a.workers)}))
        return 0 if len(recs)==len(expected) or a.limit else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','launch']);p.add_argument('--requests',required=True);p.add_argument('--out',required=True)
    p.add_argument('--checkpoint');p.add_argument('--workers',type=int,default=2);p.add_argument('--shard',type=int,default=0);p.add_argument('--gpu');p.add_argument('--limit',type=int,default=0);p.add_argument('--peak-mib',type=int,default=10000)
    a=p.parse_args();raise SystemExit(worker(a) if a.command=='worker' else launch(a))
