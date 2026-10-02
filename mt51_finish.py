"""iter_051 감사 출처 연결, 중복 후보, 자료 gate. 과거 경로에 쓰지 않는다."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from statistics import NormalDist
import numpy as np
from PIL import Image
import mt51_audit as A

ROOT, OUT = A.ROOT, A.OUT

def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def load(p):
    return json.loads(A.safe(p).read_text())

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def validate_input(row):
    require(set(row)=={'id','history','options','images'}, 'input top-level allowlist')
    require(isinstance(row['history'],str) and isinstance(row['id'],str), 'input types')
    require(set(row['options'])==set('ABCDE') and all(isinstance(s,str) for s in row['options'].values()),'option keys')
    require(len(set(' '.join(s.lower().split()) for s in row['options'].values()))==5,'duplicate options')
    require(len(row['images'])>=2, 'image count')
    for i,im in enumerate(row['images']):
        require(set(im)=={'index','path','file_sha256','rgb_pixel_sha256'}, 'image allowlist')
        require(im['index']==i, 'image order')
        path=A.safe(ROOT/im['path'])
        require(path.is_relative_to(Path(A.C.R49)/'images'),'image path scope')
        require(A.sha(path)==im['file_sha256'],'input file digest')

def validate_eval(row, inp):
    require(set(row)=={'id','correct_answer','correct_answer_text'}, 'evaluation keys')
    require(row['id']==inp['id'] and row['correct_answer'] in 'ABCDE' and len(row['correct_answer'])==1, 'answer letter')
    require(inp['options'][row['correct_answer']]==row['correct_answer_text'],'answer text')

def capacity(n, development=24, minimum=156):
    require(n>=0 and development==24 and minimum==156, 'fixed gate settings')
    upper=max(0,n-development)
    return {'eligible_cases':n,'development_min_cases':development,'evaluation_cluster_upper_bound':upper,'minimum_evaluation_clusters':minimum,'run':upper>=minimum}

def visual():
    src = load(OUT/'audit/source_check.json')
    expected = {r['case_id']: r for r in src['cases']}
    records = {}
    for n in range(1,40):
        p = OUT/'audit/visual'/f'b{n:02}.json'
        for r in load(p):
            cid = r['case_id']
            if cid in records or cid not in expected:
                raise ValueError('duplicate/unknown visual case')
            for k in ('case_key','sheet','sheet_sha256','ordered_images'):
                if r[k] != expected[cid][k]:
                    raise ValueError('visual source/order mismatch')
            if A.sha(A.safe(ROOT/r['sheet'])) != r['sheet_sha256']:
                raise ValueError('sheet digest mismatch')
            if not r['evidence'].startswith('iter_051 Codex view_image batch b'):
                raise ValueError('unverified inherited visual evidence')
            records[cid] = dict(r, decision_file=str(p.relative_to(ROOT)))
    if set(records) != set(expected):
        raise ValueError('missing visual case; no default keep')
    pending = {k for k,v in records.items() if v['visual_status']=='pending'}
    resolutions = load(OUT/'audit/visual_resolutions.json')
    if len(resolutions) != len(pending) or {r['case_id'] for r in resolutions} != pending:
        raise ValueError('unresolved visual cases')
    for r in resolutions:
        orig = records[r['case_id']]
        if r['source_check_sha256'] != A.sha(OUT/'audit/source_check.json'):
            raise ValueError('resolution source mismatch')
        for im in r['viewed_originals']:
            if im != orig['ordered_images'][im['index']]:
                raise ValueError('resolution image mismatch')
        orig['visual_status'] = r['visual_status']
        orig['resolution'] = r
    if any(r['visual_status'] not in ('keep','exclude') for r in records.values()):
        raise ValueError('pending case')
    return records

# 원문 재검토: 현재 확정 진단 공개와 검사/과거력/의심/미제공 subtype 구분.
CORRECTIONS = {
 'c12509':'검사 결과가 pseudohypoparathyroidism 양상이라는 정보. 정답의 type E brachydactyly를 확정하지 않음.',
 'c1261':'Klein line 및 성장판 소견은 검사 결과. 정답 진단명 직접 공개로 분류하지 않음.',
 'c13075':'증상 및 cavernous blood gas 검사 결과이며 진단 직접 공개 아님.',
 'c2147':'cystic fibrosis는 과거력. 현재 small bowel disease 자체는 명시하지 않음.',
 'c3995':'diagnosis was proposed라는 의심 진단. 확정 사실 직접 공개와 구분.',
 'c5258':'tuberous sclerosis는 기존 병력. 현재 tibia/fibula 침범을 확정하지 않음.',
 'c6456':'질병 계열은 공개하나 정답 type 3 subtype은 공개하지 않음. 선택지 제거 자체는 제외 기준 아님.',
 'c791':'past history of filarial infection이며 현재 유방 석회화 진단 공개 아님.',
 'c865':'피부 biopsy의 urticaria pigmentosa 및 검사 결과. systemic mastocytosis 확정 진단 아님.',
 'c8818':'endemic area 노출 정보이며 현재 skeletal fluorosis 진단 공개 아님.',
 'c9353':'ossified stylohyoid ligament는 영상 소견. 임상 증후군 정답 직접 공개와 구분.',
}

def history():
    cs = A.cases()
    text = ''
    for c in cs:
        text += f"## {c['case_key']} | n_img={len(c['images'])} | {','.join(c['_audit']['sub_modalities'])}\n"
        text += 'HISTORY: '+c['CLINICAL_HISTORY']+'\n'
        for k in 'ABCDE':
            text += '  '+('*' if k==c['_eval']['correct_answer'] else ' ')+k+' '+c['options'][k]+'\n'
        text += '\n'
    tp = A.OLD/'case_text_for_audit.md'
    if text != tp.read_text():
        raise ValueError('history source text mismatch')
    lines=text.splitlines()
    calls, evidence = {}, {}
    stream=ROOT.parent/'agent/runs/iter_050/claude_stream.jsonl'
    for no,line in enumerate(stream.open(),1):
        try: r=json.loads(line)
        except json.JSONDecodeError: continue
        message=r.get('message',{})
        if not isinstance(message,dict): continue
        content=message.get('content',[])
        if not isinstance(content,list): continue
        for x in content:
            if not isinstance(x,dict): continue
            if x.get('type')=='tool_use' and x.get('name')=='Read' and str(x.get('input',{}).get('file_path','')).endswith('case_text_for_audit.md'):
                calls[x['id']]=x['input']
            if x.get('type')=='tool_result' and x.get('tool_use_id') in calls:
                f=r.get('tool_use_result',{}).get('file',{})
                start=f.get('startLine'); num=f.get('numLines')
                if start not in (1,481,1001,1521): continue
                if x.get('is_error') or not isinstance(f.get('content'),str): raise ValueError('history render failure')
                if f['content'].rstrip('\n') != '\n'.join(lines[start-1:start-1+num]).rstrip('\n'):
                    raise ValueError('history returned text differs')
                # 실제 모델에 반환된 tool_result에도 전체 행이 있었는지 확인한다.
                returned=x.get('content','')
                if not isinstance(returned,str): raise ValueError('unexpected result')
                for i,t in enumerate(lines[start-1:start-1+num],start):
                    if t and f'{i}\t{t}' not in returned: raise ValueError('history response truncated')
                evidence[start]={'stream_line':no,'tool_use_id':x['tool_use_id'],'start':start,'num_lines':num,'returned_text_sha256':digest(returned),'file_content_sha256':digest(f['content'])}
    if set(evidence)!={1,481,1001,1521}: raise ValueError('missing history read evidence')
    records=[]
    for i,c in enumerate(cs):
        line=8*i+1
        part=1 if line<481 else 2 if line<1001 else 3 if line<1521 else 4
        start=(1,481,1001,1521)[part-1]
        oldp=A.OLD/'decisions'/f'history_part{part}.json'; old=load(oldp)
        cid=c['case_key'].replace('Case number ','c')
        prior=old['exclude'].get(c['case_key'])
        corrected=cid in CORRECTIONS
        decision='keep' if corrected or prior is None else 'exclude'
        reason=CORRECTIONS.get(cid) or (prior[1] if prior else old.get('keep_flags',{}).get(c['case_key'],'원문 반환과 전체 범위 검토 기록 연결. 확정 정답 공개로 분류되지 않은 항목을 승계.'))
        records.append({'case_id':cid,'case_key':c['case_key'],'history_status':decision,'reason':reason,'corrected':corrected,'previous_decision':prior,'history':c['CLINICAL_HISTORY'],'options':c['options'],'answer':c['_eval'],'source_case_digest':digest(c),'old_audit':str(oldp.relative_to(ROOT)),'old_audit_sha256':A.sha(oldp),'text_lines':[line,line+7],'read_evidence':evidence[start]})
    A.write(OUT/'audit/history_linked.json',{'records':records,'coverage':len(records),'stream':str(stream),'stream_sha256':A.sha(stream),'text_sha256':A.sha(tp),'corrections':CORRECTIONS})
    print('history',Counter(r['history_status'] for r in records),'corrections',len(CORRECTIONS))

def duplicates():
    src=load(OUT/'audit/source_check.json')
    transform=np.cos(np.pi*np.arange(8)[:,None]*(2*np.arange(32)[None,:]+1)/64)*np.sqrt(2/32)
    transform[0]/=np.sqrt(2)
    rows=[]
    for c in src['cases']:
        for im in c['ordered_images']:
            p=A.safe(Path(A.C.R49)/im['path'])
            if A.sha(p)!=im['file_sha256']: raise ValueError('image digest')
            with Image.open(p) as img:
                g=img.convert('L').resize((32,32),Image.Resampling.LANCZOS)
                ar=np.asarray(g,dtype=np.float64)
                d=(transform@ar@transform.T).flatten()
                bits=d>np.median(d[1:]); bits[0]=False
                ph=sum(int(v)<<i for i,v in enumerate(bits))
                small=np.asarray(img.convert('L').resize((8,8),Image.Resampling.LANCZOS),dtype=float)
                ah=sum(int(v)<<i for i,v in enumerate((small>small.mean()).flatten()))
            rows.append({'case_id':c['case_id'],**im,'phash':f'{ph:016x}','ahash':f'{ah:016x}'})
    pairs=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            hd=(int(a['phash'],16)^int(b['phash'],16)).bit_count()
            ad=(int(a['ahash'],16)^int(b['ahash'],16)).bit_count()
            exact=a['native_pixel_sha256']==b['native_pixel_sha256']
            if exact or hd<=6 or ad<=3:
                pairs.append({'a':[a['case_id'],a['index']],'b':[b['case_id'],b['index']],'phash_hamming':hd,'ahash_hamming':ad,'exact':exact,'cross_case':a['case_id']!=b['case_id']})
    A.write(OUT/'audit/duplicate_candidates.json',{'rule':'pHash DCT32/low8 median excluding DC hamming<=6 OR aHash8 hamming<=3 OR exact native pixel; candidates require visual review','images':rows,'pairs':pairs})
    print('duplicates',len(pairs),'cross',sum(p['cross_case'] for p in pairs))

def gate():
    src=load(OUT/'audit/source_check.json')
    require(A.sha(Path(A.C.R49)/'raw/train.jsonl')==A.C.TRAIN_SHA,'raw digest')
    require(A.sha(Path(A.C.R49)/'image_manifest.json')==src['source_manifest_sha256'],'image manifest digest')
    require(A.sha(Path(A.C.R49)/'audit_v2/eligible_cases.jsonl')==src['eligible_sha256'],'case manifest digest')
    require(A.C.PIL.__version__=='12.3.0' if hasattr(A.C,'PIL') else A.PIL.__version__=='12.3.0','decoder')
    for name,sha in src['code_sha256'].items():
        if name!='mt51_audit.py': require(A.sha(ROOT/name)==sha,'inherited code digest')
    for name,sha in src['base_plans'].items():
        require(A.sha(ROOT.parent/'agent/runs/iter_050'/name)==sha,'base plan digest')
    for record in src['previous_audits']:
        require(A.sha(ROOT/record['path'])==record['sha256'],'prior audit changed')
    vis=visual(); hist=load(OUT/'audit/history_linked.json')
    require(A.sha(Path(hist['stream']))==hist['stream_sha256'],'history stream digest')
    require(A.sha(A.OLD/'case_text_for_audit.md')==hist['text_sha256'],'history text digest')
    hs={r['case_id']:r for r in hist['records']}
    require(len(hs)==len(hist['records'])==254,'history coverage')
    cs=A.cases(); raw={}
    keys={c['case_key'] for c in cs}
    for r in A.C.read_jsonl(Path(A.C.R49)/'raw/train.jsonl'):
        if r['title'] in keys:
            require(r['title'] not in raw,'raw duplicate title'); raw[r['title']]=r
    require(set(raw)==keys,'raw case coverage')
    allrows=[]; inputs=[]; labels=[]
    for c in cs:
        cid=c['case_key'].replace('Case number ','c'); h=hs[cid]; v=vis[cid]; r=raw[c['case_key']]
        require(digest(c)==h['source_case_digest'],'history case digest')
        require(A.sha(ROOT/h['old_audit'])==h['old_audit_sha256'],'old history digest')
        require(c['CLINICAL_HISTORY']==r['CLINICAL_HISTORY'] and c['options']==r['options'],'raw text/options')
        require(c['_eval']=={k:r[k] for k in ('correct_answer','correct_answer_text')},'raw answer')
        require(r['is_longitudinal'] is False and r['image_count']==len(c['images']),'raw eligibility')
        ims=[]
        for i,(im,iv) in enumerate(zip(c['images'],v['ordered_images'])):
            require(im['path']==r[f'image_{i+1:02}_path']==iv['path'] and im['id']==r[f'image_{i+1:02}_id'],'raw image order')
            require(r[f'image_{i+1:02}_modality']=='X-ray','raw modality')
            p=A.safe(Path(A.C.R49)/im['path'])
            require(A.sha(p)==iv['file_sha256'],'current image hash')
            rgb,info=A.C.load_rgb(im['path'])
            require(info['native_pixel_sha256']==iv['native_pixel_sha256'] and info['pixel_sha256']==iv['pixel_sha256'],'current pixel digest')
            ims.append({'index':i,'path':str(p.relative_to(ROOT)),'file_sha256':iv['file_sha256'],'rgb_pixel_sha256':iv['pixel_sha256']})
        require(len(ims)==len(c['images'])==len(v['ordered_images']),'image coverage')
        keep=h['history_status']=='keep' and v['visual_status']=='keep'
        inp={'id':cid,'history':c['CLINICAL_HISTORY'],'options':c['options'],'images':ims}
        lab={'id':cid,**c['_eval']}
        validate_input(inp); validate_eval(lab,inp)
        allrows.append({'id':cid,'eligible':keep,'image_count':len(ims),'subtypes':c['_audit']['sub_modalities'],'anatomy':v['anatomy'],'visual':v,'history':h})
        if keep: inputs.append(inp); labels.append(lab)
    cap=capacity(len(inputs))
    # 충분한 case도 cluster 중복으로 실패할 수 있다. 이 경로는 명백한 상한 실패만 봉인한다.
    require(not cap['run'],'upper bound passes; full clustering/split/precision required')
    dup=load(OUT/'audit/duplicate_candidates.json')
    histgroups=defaultdict(list); optgroups=defaultdict(list)
    for inp in inputs:
        histgroups[' '.join(inp['history'].lower().split())].append(inp['id'])
        optgroups[digest(inp['options'])].append(inp['id'])
    precision=[];z=NormalDist().inv_cdf(1-.0125/2)
    for q in (.10,.25,.40):
        precision.append({'assumed_discordance':q,'optimistic_n_clusters':cap['evaluation_cluster_upper_bound'],'normal_half_width':z*(q/cap['evaluation_cluster_upper_bound'])**.5,'equal_cluster_assumption':True})
    report={'status':'DATA_GATE_FAIL','run_gpu':False,**cap,'n_source_cases':254,'n_source_images':896,
      'visual_counts':dict(Counter(r['visual_status'] for r in vis.values())),
      'history_counts':dict(Counter(r['history_status'] for r in hs.values())),
      'history_corrections':len(CORRECTIONS),'eligible_images':sum(len(r['images']) for r in inputs),
      'excluded_cases':254-len(inputs),'visual_and_history_excluded':sum(r['visual']['visual_status']=='exclude' and r['history']['history_status']=='exclude' for r in allrows),
      'duplicate_screen':{'candidate_pairs':len(dup['pairs']),'cross_case_candidates':sum(r['cross_case'] for r in dup['pairs']),'exact_cross_case_pairs':sum(r['cross_case'] and r['exact'] for r in dup['pairs']),'phash_le6_cross_case_pairs':sum(r['cross_case'] and r['phash_hamming']<=6 for r in dup['pairs']),'history_groups':[v for k,v in histgroups.items() if k and len(v)>1],'options_groups':[v for v in optgroups.values() if len(v)>1],'candidate_review_complete':False},
      'precision_scenarios':precision,'unequal_cluster_note':'실제 cluster 미확정. case 수만으로 E cluster 최대145가 증명되므로 unequal size는 이 상한을 개선할 수 없음. 정밀도 표는 낙관적 동일 크기 가정이며 비용/정밀도 실측 아님.',
      'split_created':False,'why_no_split':'169개 전부 독립이라고 해도 D24 뒤 E 최대145<156. 후보 중복의 판정/층화 split은 GPU 진입 결정을 바꿀 수 없어 실행하지 않음. 실제 E cluster 수로 보고하지 않는다.',
      'new_model_requests':0,'gpu_seconds':0,'hypothesis_tested':False,
      'next':'현재 자료 범위 진단 보류. 모델 가설 기각이나 의료 VLM 전체 투자 중단을 뜻하지 않음.',
      'code_amendment':{'mt51_audit.py_previous_sha256':src['code_sha256']['mt51_audit.py'],'current_sha256':A.sha(ROOT/'mt51_audit.py'),'change':'safe에서 .. 경로를 명시적으로 거부하는 2행 추가; 원본 render 검사/기존 결과 불변'},
      'limitations':['에이전트 주석 감사는 임상 gold 검증 아님','실제 near-duplicate cluster 확정 및 D/E 생성은 미실행','모델 정상 사용·생성·재개·성능 비교는 자료 gate 미통과로 미실행']}
    A.write(OUT/'data/inference_candidates.json',inputs)
    A.write(OUT/'data/evaluation_private.json',labels)
    A.write(OUT/'audit/case_decisions.json',allrows)
    A.write(OUT/'audit/gate.json',report)
    print(json.dumps({k:report[k] for k in ('status','eligible_cases','eligible_images','evaluation_cluster_upper_bound','minimum_evaluation_clusters','run_gpu')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['history','duplicates','gate']);a=p.parse_args()
    globals()[a.action]()
