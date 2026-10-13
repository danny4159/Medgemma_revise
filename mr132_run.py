"""잠긴 입력의 GPU 추론: 배타 소유권·원자 claim·개별 결과·안전 재개."""
import argparse,os,sys,time,json,fcntl,subprocess,hashlib,signal
from pathlib import Path
from mr132_common import RES,read,save,sha,digest,now
from mr132_spec import CONFIG

MODEL=Path(__file__).resolve().parent.parent/'hf_cache/models--google--medgemma-1.5-4b-it/snapshots'/CONFIG['revision']
PROTOCOL=RES/'protocol_lock_v2.json'
def smi():
    s=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    return [dict(zip(['index','uuid','total','used','free','utilization'],[x.strip() for x in line.split(',')])) for line in s.strip().splitlines()]

def allowed():
    raw=os.environ.get('CUDA_VISIBLE_DEVICES')
    if raw is None: raise RuntimeError('CUDA_VISIBLE_DEVICES must be explicit')
    ids=raw.split(','); assert ids and all(i.strip().isdigit() for i in ids)
    actual={r['index'] for r in smi()}; assert set(ids)<=actual
    return ids

def verify_protocol(models=False,worker_only=False):
    lock=read(PROTOCOL); assert lock['config']==CONFIG
    for p,h in {**lock['code'],**({} if worker_only else lock['inputs'])}.items():
        if sha(p)!=h: raise ValueError('protocol mismatch: '+p)
    for p,r in lock['model_files'].items():
        assert Path(p).stat().st_size==r['bytes']
        if models and sha(p)!=r['sha256']: raise ValueError('model mismatch')
    return sha(PROTOCOL)

def requests(path):
    rr=read(path); ids=[r['id'] for r in rr]; assert len(set(ids))==len(ids)
    known={}
    for stage in ['technical','development','holdout']:
        p=RES/'requests'/f'{stage}.json'
        if p.exists(): known.update({r['id']:r for r in read(p)})
    for r in rr:
        assert r==known[r['id']]
        assert digest({k:v for k,v in r.items() if k!='request_digest'})==r['request_digest']
        assert r['kind'] in ['single','pair'] and len(r['groups'])==(1 if r['kind']=='single' else 2)
        for g in r['groups']:
            assert len(g)==8
            for im in g:
                assert sha(im['path'])==im['sha256']
        assert not any(s in r['prompt'] for s in ['headmotion','acq-standard','sub-','MRIQC','expert score'])
    return rr

def load_records(job,repair=False):
    fd=os.open(Path(job)/'records.lock',os.O_CREAT|os.O_RDWR,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX if repair else fcntl.LOCK_SH)
    try: return _load_records(job,repair)
    finally: os.close(fd)

def _load_records(job,repair=False):
    records=[]
    for p in sorted(Path(job).glob('worker*.jsonl')):
        raw=p.read_bytes(); lines=raw.splitlines(keepends=True); good=0
        for i,line in enumerate(lines):
            try:
                if not line.endswith(b'\n'): raise ValueError('uncommitted tail')
                r=json.loads(line)
            except Exception:
                if i!=len(lines)-1 or not repair: raise ValueError('corrupt JSONL: '+str(p))
                save(p.with_name(p.name+'.tail_'+str(time.time_ns())+'.json'),dict(bytes_hex=raw[good:].hex(),source_sha256=sha(p),reason='last uncommitted row'))
                with open(p,'r+b') as f: f.truncate(good); f.flush(); os.fsync(f.fileno())
                break
            assert r['record_digest']==digest({k:v for k,v in r.items() if k!='record_digest'})
            records.append(r); good+=len(line)
    assert len({r['id'] for r in records})==len(records),'duplicate result'
    return records

def check_records(records,rr,proto):
    expected={r['id']:r for r in rr}
    for r in records:
        req=expected[r['id']]
        assert r['request_digest']==req['request_digest'] and r['protocol_sha256']==proto and r['config_digest']==digest(CONFIG)
        assert r['kind']==req['kind']
        assert r['image_hashes']==[im['sha256'] for g in req['groups'] for im in g]

def verify_job(job,reqpath,complete=True):
    proto=verify_protocol(); rr=requests(reqpath); rec=load_records(job); check_records(rec,rr,proto)
    if complete:
        c=read(Path(job)/'completion.json'); assert c['n_records']==len(rr)==len(rec) and c['protocol_sha256']==proto and c['requests_sha256']==sha(reqpath)
        assert c['config']==CONFIG and all(x==0 for x in c['returncodes'])
        assert {r['id'] for r in rec}=={r['id'] for r in rr}
        assert all(sha(p)==h for p,h in c['files'].items())
    return rec

def messages(req):
    from PIL import Image
    content=[dict(type='text',text=req['prompt'])]
    for i,group in enumerate(req['groups']):
        content.append(dict(type='text',text='\nAcquisition '+('A' if i==0 else 'B')+':\n'))
        for n,im in enumerate(group):
            content.append(dict(type='text',text=f'\nAxial slice {n+1}/8, inferior to superior:\n'))
            content.append(dict(type='image',image=Image.open(im['path']).convert('RGB')))
    return [dict(role='user',content=content)]

def input_tensor(proc,rr):
    return proc.apply_chat_template(messages(rr[0]) if len(rr)==1 else [messages(r) for r in rr],add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt',padding=True)

def worker(args):
    assert args.lock_fd is not None; os.fstat(args.lock_fd)
    proto=verify_protocol(worker_only=True); rr=requests(args.requests); job=Path(args.job); claims=job/'claims'
    # 감독기의 flock fd를 상속하여 부모가 죽어도 자식이 살아 있는 동안 새 감독기를 거부한다.
    import torch,numpy as np
    from transformers import AutoProcessor,AutoModelForImageTextToText
    torch.manual_seed(132); np.random.seed(132); torch.set_num_threads(4)
    proc=AutoProcessor.from_pretrained(MODEL,local_files_only=True); proc.tokenizer.padding_side='left'
    model=AutoModelForImageTextToText.from_pretrained(MODEL,local_files_only=True,dtype=torch.bfloat16,device_map={'':'cuda:0'},attn_implementation='sdpa').eval()
    done={r['id'] for r in load_records(job)}; start=time.monotonic(); count=0
    out=job/f'worker{args.worker}_{args.attempt}.jsonl'
    with open(out,'xb') as f:
        while True:
            batch=[]; owned=[]
            for req in rr:
                if req['id'] in done: continue
                if batch and req['kind']!=batch[0]['kind']: continue
                p=claims/(req['id']+'.json')
                try:
                    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                except FileExistsError: continue
                with os.fdopen(fd,'w') as c: json.dump(dict(pid=os.getpid(),worker=args.worker,request_digest=req['request_digest']),c)
                # 완료 row는 claim 파일을 지운 후 다시 claim될 수 있어 현재 sibling row를 다시 확인한다.
                current={r['id'] for r in load_records(job)}
                if req['id'] in current: p.unlink(); done.update(current); continue
                batch.append(req); owned.append(p)
                if len(batch)==args.batch: break
            if not batch: break
            torch.cuda.reset_peak_memory_stats(); t=time.monotonic()
            inputs=input_tensor(proc,batch).to(model.device,dtype=torch.bfloat16)
            input_len=inputs['input_ids'].shape[-1]
            with torch.inference_mode(): generated=model.generate(**inputs,max_new_tokens=512,do_sample=False)
            torch.cuda.synchronize(); elapsed=time.monotonic()-t
            for i,req in enumerate(batch):
                tokens=generated[i,input_len:].tolist(); eosids=model.generation_config.eos_token_id; eosids=[eosids] if isinstance(eosids,int) else eosids
                stop=next((n+1 for n,v in enumerate(tokens) if v in eosids),len(tokens)); tokens=tokens[:stop]
                rec=dict(id=req['id'],kind=req['kind'],request_digest=req['request_digest'],protocol_sha256=proto,config_digest=digest(CONFIG),image_hashes=[im['sha256'] for g in req['groups'] for im in g],text=proc.decode(tokens,skip_special_tokens=True),tokens=tokens,n_tokens=len(tokens),eos=bool(tokens and tokens[-1] in eosids),wall_s=elapsed/len(batch),batch_wall_s=elapsed,batch_size=len(batch),input_len=input_len,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,worker=args.worker,gpu=os.environ['CUDA_VISIBLE_DEVICES'],completed_at=now())
                rec['record_digest']=digest(rec)
                recordfd=os.open(job/'records.lock',os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(recordfd,fcntl.LOCK_EX)
                try: f.write((json.dumps(rec,sort_keys=True)+'\n').encode()); f.flush(); os.fsync(f.fileno())
                finally: os.close(recordfd)
                done.add(req['id']); count+=1
            for p in owned: p.unlink()
            del inputs,generated
            if args.limit and count>=args.limit: break
    save(job/f'worker{args.worker}_{args.attempt}_exit.json',dict(completed=count,wall_s=time.monotonic()-start,returncode=0))

def launch(args):
    proto=verify_protocol(models=True); rr=requests(args.requests); job=Path(args.job); job.mkdir(parents=True,exist_ok=True)
    fd=os.open(job/'supervisor.lock',os.O_CREAT|os.O_RDWR,0o600)
    try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: os.close(fd); raise RuntimeError('active supervisor/children; refuse launch')
    children=[]; logs=[]; started=time.monotonic()
    try:
        if (job/'completion.json').exists(): verify_job(job,args.requests); print('검증된 완료 재사용'); return
        existing=load_records(job,repair=True); check_records(existing,rr,proto)
        (job/'claims').mkdir(exist_ok=True)
        # flock을 얻었으므로 이전 자식이 없다. stale claim만 별도 보존 후 회수한다.
        stale=list((job/'claims').glob('*.json'))
        if stale:
            save(job/f'stale_claims_{time.time_ns()}.json',{str(p):read(p) for p in stale})
            for p in stale:p.unlink()
        attempt=str(time.time_ns()); ids=allowed(); free={r['index']:int(r['free']) for r in smi()}; ids.sort(key=lambda g:-free[g])
        nworkers=args.workers; mapping=[ids[i%len(ids)] for i in range(nworkers)]
        for g in ids:
            required=mapping.count(g)*(args.peak+2048)
            if free[g]<required: raise RuntimeError(f'memory admission {g}: free {free[g]} < {required}')
        save(job/f'launch_{attempt}.json',dict(created_at=now(),requests_sha256=sha(args.requests),protocol_sha256=proto,config=CONFIG,batch=args.batch,mapping=mapping,physical_logical_mapping={g:0 for g in ids},memory_before=smi(),estimated_peak_mib=args.peak,worker_margin_mib=2048,existing=len(existing)))
        for i,gpu in enumerate(mapping):
            # 시작 직전에 다시 조회하고 이미 예약된 worker의 전체 peak+여유를 고려한다.
            current={r['index']:int(r['free']) for r in smi()}
            if current[gpu]<(args.peak+2048): raise RuntimeError('memory changed before child start')
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=gpu,TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4',HF_HUB_OFFLINE='1')
            log=open(job/f'worker{i}_{attempt}.log','xb'); logs.append(log)
            cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--job',str(job),'--requests',str(args.requests),'--worker',str(i),'--attempt',attempt,'--batch',str(args.batch),'--lock-fd',str(fd),'--limit',str(args.limit)]
            children.append(subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,pass_fds=(fd,)))
        with open(job/f'resources_{attempt}.jsonl','x') as resources:
            while any(c.poll() is None for c in children):
                resources.write(json.dumps(dict(time=now(),gpu=smi(),cpu_load=os.getloadavg(),memory=Path('/proc/meminfo').read_text().splitlines()[:3]))+'\n'); resources.flush()
                if any(c.poll() not in [None,0] for c in children):
                    for c in children:
                        if c.poll() is None:c.terminate()
                    break
                time.sleep(5)
        rc=[c.wait() for c in children]; rec=load_records(job); check_records(rec,rr,proto)
        save(job/f'result_{attempt}.json',dict(returncodes=rc,n_records=len(rec),n_expected=len(rr),wall_s=time.monotonic()-started,resources=str(job/f'resources_{attempt}.jsonl')))
        if any(rc): raise RuntimeError('child failed: '+str(rc))
        if len(rec)==len(rr):
            assert {r['id'] for r in rec}=={r['id'] for r in rr}
            save(job/'completion.json',dict(created_at=now(),config=CONFIG,protocol_sha256=proto,requests_sha256=sha(args.requests),n_records=len(rec),returncodes=rc,files={str(p):sha(p) for p in job.glob('worker*.jsonl')},attempt=attempt))
        elif not args.limit: raise RuntimeError('incomplete generation')
        print('생성',len(rec),'/',len(rr),'rc',rc,'wall',time.monotonic()-started)
    finally:
        for c in children:
            if c.poll() is None:c.terminate()
        for c in children:
            try:c.wait(timeout=30)
            except subprocess.TimeoutExpired:c.kill(); c.wait()
        for f in logs:f.close()
        os.close(fd)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('command',choices=['launch','worker','verify']); ap.add_argument('--job',required=True); ap.add_argument('--requests',required=True); ap.add_argument('--workers',type=int,default=2); ap.add_argument('--batch',type=int,default=1); ap.add_argument('--peak',type=int,default=18000); ap.add_argument('--limit',type=int,default=0); ap.add_argument('--worker',type=int,default=0); ap.add_argument('--attempt'); ap.add_argument('--lock-fd',type=int); args=ap.parse_args()
    if args.command=='worker': worker(args)
    elif args.command=='launch': launch(args)
    else: print('검증',len(verify_job(args.job,args.requests)))
if __name__=='__main__': main()
