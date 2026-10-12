"""iter129의 고정 입력 개입·출처·기술 분기·평가 감독. 추가 선정/segmentation 없음."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import nibabel as nib
import numpy as np
from PIL import Image, ImageDraw
import mr123_data as D
from mr128_data import read,save,sha,verify_files,utc
import mr128_gen as G
from mr129_eval import analyze,independent

OUT=Path('results/iter_129'); OLD=Path('results/iter_128')
ROOT=Path('/home/test/.local/share/medgemma/mr_rate/iter129')
CODE=['mr129_control.py','mr129_eval.py','mr129_tests.py']+G.CODE+['mr127_select.py','mr127_assets.py','mr125_select.py']
G.OUT=OUT


def original(stage):
    directory=OLD/'gen'/stage;cfg=read(directory/'config.json');c=read(directory/'completion.json')
    verify_files(c['artifacts'])
    if sha(cfg['request_file'])!=cfg['request_sha256']:raise ValueError('old request changed')
    req=read(cfg['request_file'])['requests'];lookup={r['id']:r for r in req};rows=[]
    if len(lookup)!=len(req):raise ValueError('old duplicate request')
    for wid in range(cfg['workers']):
        for r in G.jsonl(directory/f'worker{wid}.jsonl'):
            G.verify_row(r,lookup[r['id']],sha(directory/'config.json'));rows.append(r)
    if len(rows)!=len(req) or len({r['id'] for r in rows})!=len(req):raise ValueError('old incomplete/duplicate')
    for r in req:
        verify_files(dict(zip(r['paths'],r['png_sha256'])))
        verify_files({v['path']:v['sha256'] for v in r['native']['files'].values()})
    return {r['study_uid']:r for r in req if r['cond']=='U'}, {r['study_uid']:r for r in rows if r['cond']=='U'}


def independent_render(a,k,lo,hi,zooms):
    # 독립 구현에서 volume 정규화와 방향·spacing·padding을 직접 계산한다.
    # 기존 render의 half-up과 짝수 반올림 경계 차이를 피한다.
    values=np.floor(255*np.clip((a[:,:,k]-lo)/(hi-lo),0,1)+.5).astype('uint8')
    pixels=np.flip(np.transpose(values),(0,1));h,w=pixels.shape
    ratio=896/max(h*zooms[1],w*zooms[0]);hh=round(h*zooms[1]*ratio);ww=round(w*zooms[0]*ratio)
    im=Image.fromarray(pixels).resize((max(1,ww),max(1,hh)),Image.Resampling.BICUBIC)
    canvas=Image.new('L',(896,896));canvas.paste(im,((896-im.width)//2,(896-im.height)//2))
    return canvas.convert('RGB')


def prepare():
    if (OUT/'evaluation_lock_v2.json').exists():
        verify_lock();print('existing locked preparation verified',flush=True);return
    OUT.mkdir(parents=True,exist_ok=True)
    reuse=read('../agent/runs/iter_129/reuse_manifest.json');provenance={}
    for p,r in reuse['files'].items():
        blob=subprocess.check_output(['git','show',r['source_commit']+':'+p])
        h=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
        if h!=r['blob']:raise ValueError('reuse blob')
        if p not in ['mr123_data.py','mr128_gen.py'] and Path(p).read_bytes()!=blob:raise ValueError('unintended reuse edit')
        provenance[p]=dict(source_commit=r['source_commit'],original_blob=h,current_sha256=sha(p),modified=Path(p).read_bytes()!=blob)
        target=OUT/'source_before'/p
        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
    preserved={str(p):sha(p) for p in OLD.rglob('*') if p.is_file()}
    save(OUT/'preservation_before.json',preserved)
    manifest=read(OLD/'evaluation_manifest.json')['records']
    subset=[r for r in manifest if r['role'] in ['tech','explore']]
    if Counter(r['role'] for r in subset)!=dict(tech=8,explore=40):raise ValueError('roles')
    if len({r['patient_uid'] for r in subset})!=48:raise ValueError('patient separation')
    save(OUT/'evaluation_manifest.json',dict(records=subset,original_sha256=sha(OLD/'evaluation_manifest.json')))
    previous={role:original(stage) for role,stage in [('tech','tech_b1'),('explore','main')]}
    inputs={};audit=[];requests={'tech':[],'explore':[]}
    for m in subset:
        s=m['study_uid'];oldreq=previous[m['role']][0][s];t0=time.monotonic()
        # Native volume만 min/max에 사용한다. 기존 mask는 P 연결 검증에만 사용한다.
        source=oldreq['native'];verify_files({v['path']:v['sha256'] for v in source['files'].values()})
        a,b,info=D.load_case(source['files']['img.nii.gz']['path'],source['files']['brain.nii.gz']['path'])
        if info['canon_axcodes']!='RAS' or not info['affine_match'] or not np.isfinite(a).all():raise ValueError('input geometry')
        windows={'P':D.normalization_window(a,b),'M':D.normalization_window(a,normalization='volume_minmax')}
        raw=nib.load(source['files']['img.nii.gz']['path']).get_fdata(dtype=np.float32)
        ref=(float(raw.reshape(-1).min()),float(raw.reshape(-1).max()))
        if windows['M']!=ref:raise ValueError('independent native min/max')
        if list(windows['P'])!=oldreq['window_p1_p99']:raise ValueError('old P window changed')
        if oldreq['slice_idx']!=source['U_idx'] or len(set(source['U_idx']))!=8:raise ValueError('fixed U indices')
        for c in ['P','M']:
            paths=[];hs=[];stats=[];montage=Image.new('RGB',(896,448));draw=ImageDraw.Draw(montage)
            for i,k in enumerate(source['U_idx']):
                lo,hi=windows[c];image=D.render_slice(a,k,lo,hi,info['canon_zooms'])
                if c=='P':
                    with Image.open(oldreq['paths'][i]) as old:
                        if not np.array_equal(np.asarray(image),np.asarray(old.convert('RGB'))):raise ValueError('P old pixels')
                else:
                    refim=independent_render(a,k,*ref,info['canon_zooms'])
                    if not np.array_equal(np.asarray(refim),np.asarray(image)):raise ValueError('M independent rendering')
                p=ROOT/'png'/s/c/f's{k:03d}.png';p.parent.mkdir(parents=True,exist_ok=True)
                buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
                if p.exists() and p.read_bytes()!=data:raise ValueError('existing PNG conflict')
                if not p.exists():p.write_bytes(data)
                if c=='P' and sha(p)!=oldreq['png_sha256'][i]:raise ValueError('P PNG hash changed')
                paths.append(str(p));hs.append(sha(p));pixels=np.asarray(image)
                stats.append(dict(min=int(pixels.min()),max=int(pixels.max()),mean=float(pixels.mean())))
                montage.paste(image.resize((224,224)),(i%4*224,i//4*224))
                draw.text((i%4*224+3,i//4*224+3),str(k),fill='red')
            if m['role']=='tech':
                mp=OUT/'montages'/f'{s}_{c}.png';mp.parent.mkdir(parents=True,exist_ok=True)
                if not mp.exists():montage.save(mp)
            r=dict(study_uid=s,cond=c,paths=paths,png_sha256=hs,prompt=oldreq['prompt'],
                   slice_idx=source['U_idx'],native=source,intensity_window=list(windows[c]),
                   normalization='volume_minmax' if c=='M' else 'brain_percentile_1_99',model=G.MODEL,revision=G.REV)
            r['id']=G.digest(r);requests[m['role']].append(r)
            audit.append(dict(study_uid=s,condition=c,window=list(windows[c]),native_minmax=list(ref),
                independent_pixels=True,pixel_stats=stats,original_request_id=oldreq['id'],
                no_report_or_label_in_request=True,normalization_uses_mask=c=='P',geometry=info))
        inputs[s]=dict(source=source,original_request=oldreq,build_read_render_save_s=time.monotonic()-t0)
    save(OUT/'input_audit.json',dict(records=audit,patients=48,PNG_count=768,inputs=inputs))
    for role,rr in requests.items():
        save(OUT/(role+'_requests.json'),dict(requests=rr))
    env=dict(python=sys.executable,CUDA_VISIBLE_DEVICES=os.environ.get('CUDA_VISIBLE_DEVICES'),
        packages={p:importlib.metadata.version(p) for p in ['torch','transformers','numpy','nibabel','pillow','psutil']},
        model=G.MODEL,revision=G.REV,no_new_download=True,no_training=True,no_segmentation=True)
    save(OUT/'environment.json',env);save(OUT/'reuse_checks.json',dict(files=provenance,passed=True))
    from mr129_tests import cpu
    cpu()
    locked={str(p):sha(p) for p in [OUT/'evaluation_manifest.json',OUT/'input_audit.json',OUT/'tech_requests.json',OUT/'explore_requests.json',
                OLD/'evaluation_manifest.json',OLD/'all_inputs.json',OLD/'tech_requests.json',OLD/'explore_requests.json',
                Path('../agent/runs/iter_129/plan.json'),Path('../agent/runs/iter_129/plan.md')]}
    for r in requests['tech']+requests['explore']:
        locked.update(dict(zip(r['paths'],r['png_sha256'])))
        locked.update({v['path']:v['sha256'] for v in r['native']['files'].values()})
    save(OUT/'evaluation_lock_v2.json',dict(created_utc=utc(),code={p:sha(p) for p in sorted(set(CODE))},inputs=locked,
        preserved_results_sha256=sha(OUT/'preservation_before.json'),contract=read('../agent/runs/iter_129/plan.json')['decision_contract']))
    print('locked before generation',sha(OUT/'evaluation_lock_v2.json'),'48 patients / 768 PNGs',flush=True)


def verify_lock():
    lock=read(OUT/'evaluation_lock_v2.json');verify_files(lock['code']);verify_files(lock['inputs'])
    if sha(OUT/'preservation_before.json')!=lock['preserved_results_sha256']:raise ValueError('preservation manifest changed')


def run(stage,req,pause=None,workers=2,peak=10000,max_new=512):
    verify_lock()
    return G.launch(str(req),stage,batch=1,workers=workers,max_new=max_new,pause_after=pause,peak_estimate=peak)


def verified(stage):
    d=OUT/'gen'/stage;req,rows=G.verify(d);c=read(d/'completion.json');verify_files(c['artifacts'])
    if len(rows)!=len(req) or c['count']!=len(req):raise ValueError('incomplete generation')
    return req,rows


def tech(max_new=512,stage='tech'):
    if run(stage,OUT/'tech_requests.json',max_new=max_new)!=0:raise ValueError('technical run failed')
    req,rows=verified(stage);oldreq,old=original('tech_b1')
    capped=[r['id'] for r in rows if not r['eos'] and r['n_new']>=r['max_new']]
    if capped:
        if max_new==512:return tech(1024,'tech_1024')
        raise ValueError('technical truncation persists')
    if not all(r['eos'] for r in rows):raise ValueError('non-EOS technical response')
    matches=[]
    for r in rows:
        if r['cond']!='P':continue
        matches.append(dict(study_uid=r['study_uid'],tokens_same=r['tokens']==old[r['study_uid']]['tokens'],
           input_ids_same=r['input_ids_sha256']==old[r['study_uid']]['input_ids_sha256'],tensor_check=r['tensor_check']))
    if not all(r['input_ids_same'] for r in matches):raise ValueError('P input regression')
    # P pixel/hash와 native→PNG tensor 일치는 사전 audit와 worker에서 전부 강제한다.
    reuse=all(r['tokens_same'] for r in matches)
    save(OUT/'technical_regression.json',dict(stage=stage,max_new=max_new,P_matches=matches,
        reuse_P40=reuse,all_eos=True,official_tensor_checks=len(rows),all_tensor_checks_passed=all(r['tensor_check']['passed'] for r in rows)))
    results=[read(p) for p in (OUT/'gen'/stage).glob('*.result.json')]
    events=[read(p) for p in (OUT/'gen'/stage).glob('*.events.json')]
    wall=sum(r['wall_s'] for r in results);loading=sum(e['load_s'] for e in events)
    gen_span=max(r['gen_end'] for r in rows)-min(r['gen_start'] for r in rows)
    # 잔여 생성의 이상적 절약보다 추가 두 worker 적재 추정이 크면 비교를 생략한다.
    remaining=40 if reuse else 80;best_possible_saving=gen_span/16*remaining/2
    additional_load_estimate=loading
    policy=dict(workers=2,batch=1,technical_wall_s=wall,technical_requests_per_minute=960/wall,
       generation_span_s=gen_span,load_s_sum=loading,remaining_requests=remaining,
       ideal_four_worker_saving_s=best_possible_saving,additional_two_worker_load_estimate_s=additional_load_estimate,
       predicted_main_wall_s=max(e['load_s'] for e in events)+gen_span/16*remaining,
       GPU_peak=[r['peak_gpu_total_mib'] for r in results],
       reason_ko='추가 두 모델 적재 비용 추정이 이상적인 잔여 생성 절약보다 크므로 기존 실측을 재사용한다.' if additional_load_estimate>=best_possible_saving else '처리량 비교 후보',
       compare_four_workers=additional_load_estimate<best_possible_saving)
    save(OUT/'throughput_selection.json',policy)
    print('technical regression',sum(r['tokens_same'] for r in matches),'/8; reuse P40',reuse,'throughput choice',policy,flush=True)


def gate():
    verify_lock();reg=read(OUT/'technical_regression.json');rt=read(OUT/'runtime_checks.json')
    if not rt['passed'] or not reg['all_eos'] or not reg['all_tensor_checks_passed']:raise ValueError('technical integrity failure')
    evidence={str(p):sha(p) for p in [OUT/'technical_regression.json',OUT/'runtime_checks.json',OUT/'cpu_tests.json',OUT/'throughput_selection.json',OUT/'throughput_selection_final.json',OUT/'evaluation_lock_v2.json']}
    for stage in [reg['stage'],'runtime']:
        verified(stage);evidence[str(OUT/'gen'/stage/'completion.json')]=sha(OUT/'gen'/stage/'completion.json')
    save(OUT/'technical_gate.json',dict(passed=True,created_utc=utc(),evidence=evidence,reuse_P40=reg['reuse_P40']))


def main_generation():
    reg=read(OUT/'technical_regression.json');gate()
    rr=read(OUT/'explore_requests.json')['requests']
    use=[r for r in rr if r['cond']=='M' or not reg['reuse_P40']]
    request_file=OUT/'main_requests.json';save(request_file,dict(requests=use))
    choice=read(OUT/'throughput_selection_final.json')
    if run('main',request_file,workers=choice['workers'],max_new=reg['max_new'])!=0:raise ValueError('main generation failed')


def cost(directory,condition):
    groups=[];loads=[]
    _,rows=(original(directory.name) if directory.parent==OLD/'gen' else (None,verified(directory.name)[1]))
    # 기존 original()은 U만 반환한다. event ID를 연결해 저장 완료까지 측정한다.
    if isinstance(rows,dict):rows=list(rows.values())
    wanted={r['id'] for r in rows if r['cond']==condition}
    for p in directory.glob('*.events.json'):
        e=read(p);loads.append(e['load_s'])
        for g in e['groups']:
            if set(g['ids'])&wanted:
                if len(g['ids'])!=1:raise ValueError('cost batch1 required')
                groups.append(g)
    if len(groups)!=len(wanted):raise ValueError('missing/duplicate timing events')
    values=[g['end_after_saved']-g['start'] for g in groups]
    return dict(request_n=len(values),native_read_to_saved_sum_s=sum(values),mean_s=float(np.mean(values)),
                p50_s=float(np.median(values)),p95_s=float(np.quantile(values,.95)),model_load_s=loads,
                scope_ko='검증·원 NIfTI 읽기·렌더·processor·생성·JSONL fsync까지; 모델 적재 별도',
                paired_timing=False)


def evaluate():
    verify_lock();verified('main');reg=read(OUT/'technical_regression.json')
    req,gen=verified('main');M={r['study_uid']:r for r in gen if r['cond']=='M'}
    oldreq,old=original('main')
    P=old if reg['reuse_P40'] else {r['study_uid']:r for r in gen if r['cond']=='P'}
    expected=read(OUT/'explore_requests.json')['requests']
    if reg['reuse_P40']:
        for r in expected:
            if r['cond']=='P':
                oldr=oldreq[r['study_uid']]
                for k in ['prompt','slice_idx','png_sha256','native','model','revision']:
                    if r[k]!=oldr[k]:raise ValueError('stored P pairing mismatch '+k)
    manifest=[r for r in read(OUT/'evaluation_manifest.json')['records'] if r['role']=='explore']
    report,rows=analyze(manifest,P,M);report['reused_P40']=reg['reuse_P40']
    report['cost']={'P':cost(OLD/'gen'/'main','U') if reg['reuse_P40'] else cost(OUT/'gen'/'main','P'),
                    'M':cost(OUT/'gen'/'main','M')}
    report['specialist_reference_only']={k:read(OLD/'eval/report.json')[k] for k in ['S_available_n','S_available_metrics','S_AUROC_available']}
    report['provenance']=dict(evaluation_lock_sha256=sha(OUT/'evaluation_lock_v2.json'),
       technical_gate_sha256=sha(OUT/'technical_gate.json'),main_completion_sha256=sha(OUT/'gen/main/completion.json'),
       old_completion_sha256=sha(OLD/'gen/main/completion.json'))
    verification=independent(rows,report)
    verify_files(read(OUT/'preservation_before.json'))
    for p,h in read(OLD/'medgemma_assets_readonly.json')['files'].items():
        if sha(p)!=h['sha256']:raise ValueError('model assets changed')
    save(OUT/'eval/report.json',report);save(OUT/'eval/per_patient.json',dict(rows=rows))
    save(OUT/'eval/independent_verify.json',verification)
    outputs={str(p):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in ['completion.json','stage.lock'] and not p.name.endswith('.lock')}
    save(OUT/'completion.json',dict(passed=True,created_utc=utc(),artifacts=outputs,decision=report['decision'],
        preservation_verified=len(read(OUT/'preservation_before.json')),model_assets_verified=True))
    print('REPORT',report,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','tech','gate','main','eval']);a=ap.parse_args()
    {'prepare':prepare,'tech':tech,'gate':gate,'main':main_generation,'eval':evaluate}[a.action]()
