"""고정 case 그래프 실행. case flock·원자적 request JSON·attempt별 비용 보존."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from mt52_prepare import ROOT,OUT,safe,save,sha256_file
from mt52_spec import prompt,digest,MODEL_REVISION,check_case
from mt52_sanity import images,build
from rsna_diag.queue_lock import try_lock,my_info

CODE=['mt52_run.py','mt52_sanity.py','mt52_spec.py','mt52_prepare.py','rsna_diag/generate.py','rsna_diag/queue_lock.py']

def atomic(path,value):
    path=safe(path,True);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.partial.'+uuid.uuid4().hex)
    with temp.open('x') as f:
        json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    os.link(temp,path) # 기존 정식 결과를 덮어쓰지 않는다.

def verify_protocol(path):
    p=json.loads(safe(path).read_text())
    for f,h in p['files'].items():
        if sha256_file(safe(ROOT/f))!=h:raise ValueError('protocol file changed: '+f)
    assert p['revision']==MODEL_REVISION
    return p,sha256_file(path)

def stages(c,only):
    if only:return [(s,None) for s in only]
    return [('T',None),('D',None)]+[('F',i) for i in range(len(c['images']))]+[(s,None) for s in ['U','C','R','H','X']]

def worker(a):
    job=safe(ROOT/a.job);p,pdig=verify_protocol(job/'protocol.json')
    cs=json.loads((ROOT/p['inference']).read_text());assert len({c['case_key'] for c in cs})==len(cs)
    manifest={r['case_key']:r for r in json.loads((ROOT/p['images']).read_text())}
    for c in cs:check_case(c)
    allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert a.gpu in allowed
    os.environ['CUDA_VISIBLE_DEVICES']=a.gpu
    from rsna_diag.generate import load_model,env_info
    start=time.time();torch,proc,model=load_model();torch.manual_seed(5201)
    env=env_info(torch,proc,model);eos=env['eos_token_id'];eos=eos if isinstance(eos,list) else [eos]
    atomic(job/'attempts'/a.attempt/f'worker{a.worker}_env.json',{'env':env,'load_seconds':time.time()-start,'gpu':a.gpu})
    for c in cs:
        cid=c['case_key'].replace('Case number ','c');(job/'claims').mkdir(exist_ok=True)
        lk,_,_=try_lock(job/'claims'/cid,my_info(worker=a.worker))
        if lk is None:continue
        try:
            ims=images(c,manifest);parents={}
            for stage,index in stages(c,p['only']):
                name=stage if index is None else f'F{index:02d}'
                needed=[parents[f'F{i:02d}'] for i in range(len(ims))] if stage=='U' else [parents['U']] if stage in ('C','R') else [parents['H']] if stage=='X' else []
                text=prompt(c,stage,[r['text'] for r in needed],index)
                idx=[index] if stage=='F' else list(range(len(ims))) if stage in ('D','R','H','X') else []
                cap=p['caps'].get(stage,1024)
                if stage=='H':cap=len(ims)*p['caps']['F']+p['caps']['U']
                spec={'case':c['case_key'],'stage':name,'prompt':text,'images':[manifest[c['case_key']]['images'][i] for i in idx],
                    'parents':[r['record_digest'] for r in needed],'cap':cap,'protocol':pdig}
                rid=digest(spec);path=job/'records'/cid/f'{name}.json'
                if path.exists():
                    rec=json.loads(safe(path).read_text());rd=rec.pop('record_digest')
                    assert rd==digest(rec) and rec['request_id']==rid and rec['spec']==spec,'stale or damaged result'
                    rec['record_digest']=rd;parents[name]=rec;continue
                inp=build(proc,[ims[i] for i in idx],text,idx)
                x={k:v.to('cuda',dtype=torch.bfloat16) if v.is_floating_point() else v.to('cuda') for k,v in inp.items()}
                torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats();t=time.time()
                atomic(job/'attempts'/a.attempt/f'{cid}_{name}_start.json',{'time':t,'request_id':rid,'worker':a.worker,'gpu':a.gpu})
                with torch.inference_mode():y=model.generate(**x,max_new_tokens=cap,do_sample=False)
                torch.cuda.synchronize();end=time.time();ids=y[0,inp['input_ids'].shape[1]:].tolist()
                rec={'spec':spec,'request_id':rid,'text':proc.decode(ids,skip_special_tokens=True),'tokens':ids,
                    'input_tokens':inp['input_ids'][0].tolist(),'eos':bool(ids and ids[-1] in eos),
                    't_start':t,'t_end':end,'runtime':end-t,'worker':a.worker,'gpu':a.gpu,'attempt':a.attempt,
                    'peak_alloc_GiB':torch.cuda.max_memory_allocated()/2**30,'peak_reserved_GiB':torch.cuda.max_memory_reserved()/2**30}
                rec['record_digest']=digest(rec);atomic(path,rec);parents[name]=rec
                print(cid,name,len(ids),rec['eos'],round(end-t,2),flush=True);del x,y,inp
        finally:lk.release()

def launch(a):
    job=safe(ROOT/a.job,True);job.mkdir(parents=True,exist_ok=True)
    lk,_,_=try_lock(job/'launch.lock',my_info())
    if lk is None:raise RuntimeError('launcher already running')
    children=[];logs=[]
    try:
        files=CODE+[a.inference,a.images,'results/iter_052/data/D_selection.json','results/iter_052/provenance/D_image_returns_v2.json']
        protocol={'files':{f:sha256_file(safe(ROOT/f)) for f in files},'inference':a.inference,'images':a.images,
                  'revision':MODEL_REVISION,'only':a.only.split(',') if a.only else [],'caps':{'F':512,'U':1024,'T':1024,'D':1024,'C':1024,'R':1024,'X':1024}}
        if a.double_caps:
            for s in a.double_caps.split(','):
                assert s in protocol['caps']
                protocol['caps'][s]*=2
        if (job/'protocol.json').exists():
            old,_=verify_protocol(job/'protocol.json');assert old==protocol,'requested configuration mismatch'
        else:save(job/'protocol.json',protocol)
        allowed=os.environ['CUDA_VISIBLE_DEVICES'].split(',');assert all(x.isdigit() for x in allowed)
        out=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.free,memory.total','--format=csv,noheader,nounits'],text=True)
        gpu={x.split(',')[0].strip():[int(v.strip()) for v in x.split(',')[1:]] for x in out.strip().splitlines()}
        order=sorted(allowed,key=lambda g:-gpu[g][0]);mapping=[order[i%len(order)] for i in range(a.workers)]
        for g in order:
            if mapping.count(g)*(a.peak_gib+2)*1024>gpu[g][0]:raise RuntimeError('insufficient memory margin '+g)
        attempt=time.strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8];ad=job/'attempts'/attempt;ad.mkdir(parents=True)
        save(ad/'launch.json',{'allowed':allowed,'mapping':mapping,'free_MiB':gpu,'peak_estimate_GiB':a.peak_gib,'per_worker_margin_GiB':2})
        def stop(sig,frame):
            for c in children:
                if c.poll() is None:c.terminate()
            raise KeyboardInterrupt('signal '+str(sig))
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        start=time.time()
        for i,g in enumerate(mapping):
            f=(ad/f'worker{i}.log').open('x');logs.append(f)
            cmd=[sys.executable,str(ROOT/'mt52_run.py'),'--job',a.job,'--worker',str(i),'--gpu',g,'--attempt',attempt]
            children.append(subprocess.Popen(cmd,stdout=f,stderr=f))
        with (ad/'resources.jsonl').open('x') as f:
            while any(c.poll() is None for c in children):
                if any(c.poll() not in (None,0) for c in children):raise RuntimeError('worker failure')
                stat=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
                f.write(json.dumps({'time':time.time(),'gpu':stat})+'\n');f.flush();time.sleep(5)
        if any(c.returncode!=0 for c in children):raise RuntimeError('worker failure')
        _,pdig=verify_protocol(job/'protocol.json');cs=json.loads((ROOT/a.inference).read_text())
        expected={(c['case_key'].replace('Case number ','c'),s if i is None else f'F{i:02d}') for c in cs for s,i in stages(c,protocol['only'])}
        paths=list((job/'records').glob('*/*.json'));actual={(p.parent.name,p.stem) for p in paths}
        assert actual==expected
        save(ad/'completion.json',{'status':'PASS','exit_codes':[c.returncode for c in children],'wall':time.time()-start,
            'protocol':pdig,'n':len(paths),'records':{str(p.relative_to(ROOT)):sha256_file(p) for p in paths}})
        print('complete',len(paths),time.time()-start)
    finally:
        for c in children:
            if c.poll() is None:c.terminate()
        for c in children:
            try:c.wait(timeout=30)
            except subprocess.TimeoutExpired:c.kill();c.wait()
        for f in logs:f.close()
        lk.release()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',required=True);p.add_argument('--worker',type=int)
    p.add_argument('--gpu');p.add_argument('--attempt');p.add_argument('--workers',type=int,default=2)
    p.add_argument('--peak-gib',type=float,default=12.0);p.add_argument('--only',default='')
    p.add_argument('--double-caps',default='')
    p.add_argument('--inference',default='results/iter_052/data/D_inference.json');p.add_argument('--images',default='results/iter_052/data/D_images.json')
    a=p.parse_args();worker(a) if a.worker is not None else launch(a)
