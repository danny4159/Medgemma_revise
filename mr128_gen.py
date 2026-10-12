"""MR-RATE 고정 영상 질문: 공식 생성, static shard/원자적 claim, 엄격 재개·봉인."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import numpy as np
from mr128_data import OUT,read,save,sha,verify_files,utc
from mr128_build import PROMPT
from mr123_run import MODEL,REV,CACHE,messages_for
from mr127_seg import gpu_info

OUT=Path(os.environ.get('MR_RATE_GENERATION_OUT',str(OUT)))

CODE=['mr128_gen.py','mr128_data.py','mr128_build.py','mr128_eval.py','mr123_run.py','mr123_data.py','mr127_seg.py']


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def prepare(role):
    gate=read(OUT/'all_anatomy_gate.json')
    if not gate['passed']:raise ValueError('all anatomy gate')
    selection=read(OUT/'evaluation_manifest.json')['records'];inputs=read(OUT/'all_inputs.json')['inputs']
    requests=[]
    for m in selection:
        if m['role']!=role:continue
        study=m['study_uid'];stage='tech' if role=='tech' else 'remaining'
        b=read(OUT/'build'/stage/(study+'.json'))
        for condition in ['U','A']:
            paths=[b['pngs'][str(k)]['path'] for k in b[condition+'_idx']]
            hashes=[b['pngs'][str(k)]['sha256'] for k in b[condition+'_idx']]
            r=dict(study_uid=study,cond=condition,paths=paths,png_sha256=hashes,
                   prompt=PROMPT,slice_idx=b[condition+'_idx'],native=inputs[study],
                   window_p1_p99=b['window_p1_p99'],model=MODEL,revision=REV)
            r['id']=digest(r);requests.append(r)
    if len(requests)!={'tech':16,'explore':80}[role]:raise ValueError('request count')
    if len({r['id'] for r in requests})!=len(requests):raise ValueError('duplicate request')
    save(OUT/(role+'_requests.json'),dict(requests=requests,all_input_sha256=sha(OUT/'all_inputs.json'),
              source_builds={str(OUT/'build'/('tech' if role=='tech' else 'remaining')/(r['study_uid']+'.json')):
                            sha(OUT/'build'/('tech' if role=='tech' else 'remaining')/(r['study_uid']+'.json')) for r in requests}))
    print('prepared',role,len(requests),flush=True)


def jsonl(path,repair=False):
    path=Path(path)
    if not path.exists():return []
    data=path.read_bytes();lines=data.splitlines(keepends=True);rows=[];valid=0
    def unique(items):
        obj={}
        for k,v in items:
            if k in obj:raise ValueError('duplicate JSON key')
            obj[k]=v
        return obj
    def constant(value):raise ValueError('nonfinite/nonstandard JSON constant: '+value)
    for i,line in enumerate(lines):
        try:
            row=json.loads(line,object_pairs_hook=unique,parse_constant=constant)
            if not isinstance(row,dict):raise ValueError('not object')
        except json.JSONDecodeError as e:
            if i!=len(lines)-1 or line.endswith(b'\n') or not repair:raise ValueError(f'corrupt JSONL at {path}:{i+1}') from e
            backup=path.with_name(path.name+'.torn.'+uuid.uuid4().hex)
            with backup.open('xb') as f:f.write(data)
            with path.open('r+b') as f:f.truncate(valid);f.flush();os.fsync(f.fileno())
            break
        rows.append(row);valid+=len(line)
        if not line.endswith(b'\n'):
            if not repair:raise ValueError('JSONL record missing newline commit marker')
            backup=path.with_name(path.name+'.newline.'+uuid.uuid4().hex)
            with backup.open('xb') as f:f.write(data)
            with path.open('ab') as f:f.write(b'\n');f.flush();os.fsync(f.fileno())
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate output IDs')
    return rows


def verify_row(row,request,config_sha):
    body={k:v for k,v in row.items() if k!='record_digest'}
    if row.get('record_digest')!=digest(body) or row.get('config_sha256')!=config_sha:raise ValueError('record digest/config')
    if row.get('request_digest')!=digest(request) or row['id']!=request['id']:raise ValueError('record request')
    if row['n_img']!=8 or row['max_new'] not in [512,1024]:raise ValueError('generation config')


def native_images(r):
    """실제 원 NIfTI 읽기·window·렌더를 매 요청에서 수행해 PNG와 pixel 대조."""
    import nibabel as nib
    from PIL import Image
    import mr123_data as D
    files=r['native']['files'];verify_files({v['path']:v['sha256'] for v in files.values()})
    verify_files(dict(zip(r['paths'],r['png_sha256'])))
    normalization=r.get('normalization','brain_percentile_1_99')
    if normalization=='volume_minmax':
        im=nib.as_closest_canonical(nib.load(files['img.nii.gz']['path']))
        a=np.asarray(im.dataobj,dtype=np.float32);b=None
        info=dict(canon_zooms=im.header.get_zooms()[:3])
    else:
        a,b,info=D.load_case(files['img.nii.gz']['path'],files['brain.nii.gz']['path'])
    lo,hi=D.normalization_window(a,b,normalization)
    if [lo,hi]!=r.get('intensity_window',r.get('window_p1_p99')):raise ValueError('native window changed')
    images=[]
    for k,p in zip(r['slice_idx'],r['paths']):
        image=D.render_slice(a,k,lo,hi,info['canon_zooms'])
        with Image.open(p) as saved:
            if not np.array_equal(np.asarray(image),np.asarray(saved.convert('RGB'))):raise ValueError('native/PNG pixel mismatch')
        images.append(image)
    return images


def make_messages(r,images):
    content=[]
    for i,image in enumerate(images):
        content.extend([dict(type='text',text=f'Image {i+1}:'),dict(type='image',image=image)])
    content.append(dict(type='text',text=r['prompt']))
    return [dict(role='user',content=content)]


def worker(directory,wid):
    import torch
    import psutil
    from transformers import AutoProcessor,AutoModelForImageTextToText
    directory=Path(directory);cfg=read(directory/'config.json');config_sha=sha(directory/'config.json')
    verify_files(cfg['code']);verify_files(cfg['evaluation_code'])
    if sha(OUT/'evaluation_lock_v2.json')!=cfg['evaluation_lock_sha256']:raise ValueError('evaluation lock changed')
    if os.environ.get('CUDA_VISIBLE_DEVICES')!=cfg['gpu_mapping'][str(wid)]:raise ValueError('worker GPU mapping')
    req_file=Path(cfg['request_file'])
    if sha(req_file)!=cfg['request_sha256']:raise ValueError('request file changed')
    requests=read(req_file)['requests'];assigned=requests[wid::cfg['workers']]
    if any(set(r)&{'label','report','role','selector_success'} for r in requests):raise ValueError('evaluation fields in request')
    output=directory/f'worker{wid}.jsonl';stop=False
    def handler(sig,frame):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,handler);signal.signal(signal.SIGINT,handler)
    with (directory/f'worker{wid}.lock').open('a') as ownership:
        fcntl.flock(ownership,fcntl.LOCK_EX|fcntl.LOCK_NB)
        existing=jsonl(output,repair=True);byid={r['id']:r for r in assigned}
        for row in existing:
            if row['id'] not in byid:raise ValueError('unassigned old output')
            verify_row(row,byid[row['id']],config_sha)
        done={row['id'] for row in existing};pending=[r for r in assigned if r['id'] not in done]
        if not pending:return 0
        torch.manual_seed(125);np.random.seed(125);torch.set_num_threads(4);self_process=psutil.Process()
        t0=time.monotonic()
        processor=AutoProcessor.from_pretrained(MODEL,revision=REV,cache_dir=CACHE,local_files_only=True)
        processor.tokenizer.padding_side='left'
        model=AutoModelForImageTextToText.from_pretrained(MODEL,revision=REV,cache_dir=CACHE,
                 local_files_only=True,torch_dtype=torch.bfloat16,device_map={'':0})
        model.eval();model_mib=torch.cuda.memory_allocated()/2**20;loaded=time.monotonic()
        attempt=uuid.uuid4().hex;events=dict(wid=wid,pid=os.getpid(),physical_gpu=os.environ['CUDA_VISIBLE_DEVICES'],
             logical_gpu=0,load_s=loaded-t0,model_mib=model_mib,started_utc=utc(),warm_start=loaded,groups=[])
        save(directory/f'{attempt}.worker{wid}.loaded.json',events)
        print('loaded',wid,'model MiB',model_mib,flush=True)
        eos=set([processor.tokenizer.eos_token_id])
        x=model.generation_config.eos_token_id;eos.update([x] if isinstance(x,int) else x or [])
        with output.open('ab') as f:
            for first in range(0,len(pending),cfg['batch']):
                if stop:break
                group=pending[first:first+cfg['batch']];claims=[]
                try:
                    claim_dir=directory/'claims';claim_dir.mkdir(exist_ok=True)
                    for r in group:
                        h=(claim_dir/(r['id']+'.lock')).open('a');fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB);claims.append(h)
                    ts=time.monotonic();images=[native_images(r) for r in group]
                    messages=[make_messages(r,im) for r,im in zip(group,images)]
                    # 공식 single 입력과 tokenize=False→processor 경로의 모든 tensor를 독립 대조한다.
                    tensor_checks=[]
                    for msg,im in zip(messages,images):
                        single=processor.apply_chat_template(msg,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt')
                        text=processor.apply_chat_template(msg,add_generation_prompt=True,tokenize=False)
                        official=processor(text=text,images=im,add_special_tokens=False,return_tensors='pt')
                        passed=set(single)==set(official) and all(torch.equal(single[k],official[k]) for k in single)
                        if not passed:raise ValueError('official processor tensor mismatch')
                        saved_input=processor.apply_chat_template(messages_for(group[len(tensor_checks)]),add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt')
                        if set(single)!=set(saved_input) or not all(torch.equal(single[k],saved_input[k]) for k in single):raise ValueError('saved PNG processor tensor mismatch')
                        tensor_checks.append(dict(all_tensor_keys=sorted(single),passed=passed,n_img=len(im)))
                    inp=processor.apply_chat_template(messages[0] if len(group)==1 else messages,
                         add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt',padding=len(group)>1)
                    ids_hash=[hashlib.sha256(inp['input_ids'][i].numpy().tobytes()).hexdigest() for i in range(len(group))]
                    inp=inp.to(model.device);inp['pixel_values']=inp['pixel_values'].to(torch.bfloat16)
                    prep_done=time.monotonic();torch.cuda.synchronize();gen_start=time.monotonic()
                    with torch.inference_mode():output_ids=model.generate(**inp,max_new_tokens=cfg['max_new'],do_sample=False)
                    torch.cuda.synchronize();gen_end=time.monotonic();plen=inp['input_ids'].shape[1]
                    rows=[]
                    for i,r in enumerate(group):
                        tokens=output_ids[i,plen:].tolist();ended=any(t in eos for t in tokens)
                        while tokens and tokens[-1]==processor.tokenizer.pad_token_id and tokens[-1] not in eos:tokens.pop()
                        text=processor.tokenizer.decode(tokens,skip_special_tokens=True)
                        row=dict(id=r['id'],study_uid=r['study_uid'],cond=r['cond'],text=text,tokens=tokens,eos=ended,
                             n_new=len(tokens),max_new=cfg['max_new'],n_img=8,batch=cfg['batch'],wid=wid,
                             config_sha256=config_sha,request_digest=digest(r),input_ids_sha256=ids_hash[i],
                             pixel_values_sha256=hashlib.sha256(inp['pixel_values'].float().cpu().numpy().tobytes()).hexdigest() if len(group)==1 else None,
                             tensor_check=tensor_checks[i],group_start=ts,gen_start=gen_start,gen_end=gen_end,
                             prep_s=prep_done-ts,gen_s=gen_end-gen_start,wall_before_save_s=time.monotonic()-ts,
                             peak_allocated_mib=torch.cuda.max_memory_allocated()/2**20,
                             peak_reserved_mib=torch.cuda.max_memory_reserved()/2**20,model_mib=model_mib,attempt=attempt)
                        row['record_digest']=digest(row);f.write((json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n').encode());rows.append(row)
                    f.flush();os.fsync(f.fileno());saved=time.monotonic()
                    io=self_process.io_counters();mem=self_process.memory_info();cpu=self_process.cpu_times()
                    events['groups'].append(dict(ids=[r['id'] for r in group],start=ts,end_after_saved=saved,
                         gen_start=gen_start,gen_end=gen_end,batch=len(group),rss_bytes=mem.rss,
                         process_cpu_user_s=cpu.user,process_cpu_system_s=cpu.system,
                         process_read_bytes=io.read_bytes,process_write_bytes=io.write_bytes,
                         system_ram_available_bytes=psutil.virtual_memory().available))
                    save(directory/f'{attempt}.group{first:03d}.worker{wid}.json',events['groups'][-1])
                    print('saved',wid,len(group),first+len(group),'/',len(pending),flush=True)
                finally:
                    for h in claims:h.close()
        events['end']=time.monotonic();events['stopped']=stop
        save(directory/f'{attempt}.worker{wid}.events.json',events)
        return 0


def verify_code(cfg,directory,allow_completed_archive=False):
    for p,h in cfg['code'].items():
        if sha(p)==h:continue
        if allow_completed_archive and (Path(directory)/'completion.json').exists() and p=='mr128_gen.py':
            proofs=read(OUT/'generation_source_registry.json')['records']
            if any(proof['sha256']==h and sha(proof['source'])==h and proof['config_sha256']==sha(Path(directory)/'config.json') for proof in proofs):continue
        raise ValueError(f'code changed: {p}')


def verify(directory,allow_completed_archive=False):
    directory=Path(directory);cfg=read(directory/'config.json');config_sha=sha(directory/'config.json')
    verify_code(cfg,directory,allow_completed_archive);verify_files(cfg['evaluation_code'])
    if sha(OUT/'evaluation_lock_v2.json')!=cfg['evaluation_lock_sha256']:raise ValueError('evaluation lock changed')
    if sha(cfg['request_file'])!=cfg['request_sha256']:raise ValueError('changed request input')
    requests=read(cfg['request_file'])['requests'];lookup={r['id']:r for r in requests};rows=[]
    if len(lookup)!=len(requests) or any(r['id']!=digest({k:v for k,v in r.items() if k!='id'}) for r in requests):raise ValueError('duplicate/invalid request ID')
    for wid in range(cfg['workers']):
        for row in jsonl(directory/f'worker{wid}.jsonl'):
            if row['id'] not in lookup:raise ValueError('extra output')
            if row['id'] not in {r['id'] for r in requests[wid::cfg['workers']]}:raise ValueError('wrong worker assignment')
            verify_row(row,lookup[row['id']],config_sha);rows.append(row)
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate output')
    for r in requests:
        verify_files(dict(zip(r['paths'],r['png_sha256'])))
        verify_files({v['path']:v['sha256'] for v in r['native']['files'].values()})
    return requests,rows


def launch(request_file,stage,batch=1,workers=2,max_new=512,pause_after=None,peak_estimate=18000):
    directory=OUT/'gen'/stage;directory.mkdir(parents=True,exist_ok=True)
    allowed=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    if len(set(allowed))!=len(allowed) or not all(g.isdigit() for g in allowed):raise ValueError('allowed GPU set')
    requests=read(request_file)['requests'];verify_files(read(OUT/'evaluation_lock_v2.json')['code'])
    if OUT==Path('results/iter_129'):
        if batch!=1:raise ValueError('iter129 batch1 contract')
        if stage.startswith('main'):
            gate=read(OUT/'technical_gate.json');verify_files(gate['evidence'])
            if not gate['passed']:raise ValueError('technical gate failed')
    initial=[g for g in gpu_info() if g['index'] in allowed];initial.sort(key=lambda g:g['free_mib'],reverse=True)
    remaining={g['index']:g['free_mib'] for g in initial};mapping={}
    for i in range(workers):
        candidates=[g for g in remaining if remaining[g]>=peak_estimate+2048]
        if not candidates:raise ValueError('worker별 예상 peak+2048MiB 합계가 허용 GPU 여유를 초과')
        g=max(candidates,key=lambda g:remaining[g]);mapping[str(i)]=g;remaining[g]-=peak_estimate+2048
    cfg=dict(request_file=str(request_file),request_sha256=sha(request_file),workers=workers,batch=batch,
         max_new=max_new,seed=125,model=MODEL,revision=REV,dtype='bfloat16',do_sample=False,peak_estimate_mib=peak_estimate,
         gpu_mapping=mapping,allowed_gpus=allowed,code={p:sha(p) for p in CODE},
         evaluation_code=read(OUT/'evaluation_lock_v2.json')['code'],evaluation_lock_sha256=sha(OUT/'evaluation_lock_v2.json'))
    with (directory/'stage.lock').open('a') as ownership:
        fcntl.flock(ownership,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (directory/'completion.json').exists():
            previous=read(directory/'config.json')
            fields=['request_sha256','workers','batch','max_new','seed','model','revision','dtype','do_sample','allowed_gpus']
            if any(previous[k]!=cfg[k] for k in fields):raise ValueError('completed run requested config differs')
            c=read(directory/'completion.json');verify_files(c['artifacts']);_,rows=verify(directory,allow_completed_archive=True)
            if len(rows)!=len(requests):raise ValueError('stale completion count')
            return 0
        if (directory/'config.json').exists():
            previous=read(directory/'config.json')
            # 재개 시 실제 장치 순서가 바뀌어도 원 mapping을 유지하며 허용 집합을 다시 검사한다.
            cfg['gpu_mapping']=previous['gpu_mapping'];mapping=cfg['gpu_mapping']
            if previous!=cfg:raise ValueError('resume config differs')
        else:save(directory/'config.json',cfg)
        tag=uuid.uuid4().hex;children=[];handles=[];stopped=False;peaks={g:0 for g in allowed};minimum={g:99999 for g in allowed}
        t0=time.monotonic()
        def stop(sig,frame):
            nonlocal stopped
            stopped=True
            for p in children:
                if p.poll() is None:p.terminate()
        handlers={s:signal.signal(s,stop) for s in [signal.SIGTERM,signal.SIGINT]}
        try:
            for wid in range(workers):
                info=next(g for g in gpu_info() if g['index']==mapping[str(wid)])
                if info['free_mib']<peak_estimate+2048:raise ValueError('예상 peak+2048MiB 여유 부족')
                env=dict(os.environ,CUDA_VISIBLE_DEVICES=mapping[str(wid)],PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',TOKENIZERS_PARALLELISM='false',
                    MR_RATE_GENERATION_OUT=str(OUT),
                    CUDA_CACHE_PATH='/home/test/.local/share/medgemma/mr_rate/'+OUT.name.replace('_','')+'/cuda_cache',
                    TORCHINDUCTOR_CACHE_DIR='/home/test/.local/share/medgemma/mr_rate/'+OUT.name.replace('_','')+'/torch_cache')
                h=(directory/f'{tag}.worker{wid}.log').open('x');handles.append(h)
                p=subprocess.Popen([sys.executable,str(Path(__file__).absolute()),'worker',str(directory),str(wid)],env=env,stdout=h,stderr=subprocess.STDOUT);children.append(p)
            save(directory/f'{tag}.launch.json',dict(config_sha256=sha(directory/'config.json'),pids=[p.pid for p in children],
                 supervisor_pid=os.getpid(),initial_gpu=initial,started_utc=utc(),pause_after=pause_after))
            print('supervisor',os.getpid(),'workers',[(p.pid,mapping[str(i)]) for i,p in enumerate(children)],flush=True)
            with (directory/f'{tag}.resources.jsonl').open('x') as resource:
                while any(p.poll() is None for p in children):
                    import psutil
                    gs=gpu_info();resource.write(json.dumps(dict(utc=utc(),gpus=gs,
                         cpu_percent=psutil.cpu_percent(),ram=psutil.virtual_memory()._asdict(),disk_io=psutil.disk_io_counters()._asdict()))+'\n');resource.flush()
                    for g in gs:
                        if g['index'] in peaks:peaks[g['index']]=max(peaks[g['index']],g['used_mib']);minimum[g['index']]=min(minimum[g['index']],g['free_mib'])
                    if any(p.poll() not in [None,0] for p in children):stop(None,None)
                    if pause_after is not None and not stopped:
                        count=len({rid for p in directory.glob('*.group*.worker*.json') for rid in read(p)['ids']})
                        if count>=pause_after and count<len(requests):stop(None,None)
                    time.sleep(1)
            rc=[p.wait() for p in children]
        except Exception as e:
            stop(None,None)
            save(directory/f'{tag}.launch_error.json',dict(error=str(e),config_sha256=sha(directory/'config.json'),
                 owned_pids=[p.pid for p in children],gpus=gpu_info(),created_utc=utc()))
            raise
        finally:
            for p in children:
                if p.poll() is None:p.terminate()
                p.wait()
            for h in handles:h.close()
            for s,h in handlers.items():signal.signal(s,h)
        requests,rows=verify(directory);ok=len(rows)==len(requests) and all(r==0 for r in rc)
        result=dict(config_sha256=sha(directory/'config.json'),wall_s=time.monotonic()-t0,child_exit_codes=rc,
              count=len(rows),expected=len(requests),stopped=stopped,complete=ok,peak_gpu_total_mib=peaks,min_gpu_free_mib=minimum)
        save(directory/f'{tag}.result.json',result)
        if ok:
            artifacts={str(p):sha(p) for p in directory.glob('*') if p.is_file() and p.name not in ['stage.lock','completion.json'] and not p.name.endswith('.lock')}
            save(directory/'completion.json',dict(count=len(rows),expected=len(requests),config_sha256=sha(directory/'config.json'),artifacts=artifacts))
        print('generation',stage,'complete',ok,'rows',len(rows),'/',len(requests),flush=True)
        return 0 if ok else (75 if stopped and all(r==0 for r in rc) else 2)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=str(OUT));sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('role',choices=['tech','explore'])
    p=sub.add_parser('worker');p.add_argument('directory');p.add_argument('wid',type=int)
    p=sub.add_parser('run');p.add_argument('--requests',default=str(OUT/'tech_requests.json'));p.add_argument('--stage',required=True)
    p.add_argument('--batch',type=int,default=1);p.add_argument('--workers',type=int,default=2);p.add_argument('--max-new',type=int,default=512);p.add_argument('--pause-after',type=int);p.add_argument('--peak-estimate',type=int,default=18000)
    a=ap.parse_args()
    OUT=Path(a.out)
    if a.action=='prepare':prepare(a.role)
    elif a.action=='worker':raise SystemExit(worker(a.directory,a.wid))
    else:raise SystemExit(launch(a.requests,a.stage,a.batch,a.workers,a.max_new,a.pause_after,a.peak_estimate))
