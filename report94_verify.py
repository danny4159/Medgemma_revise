"""iter_094: 별도 집계 검증. per_output의 요약 필드를 읽지 않고 judgments·reference·원시 생성 JSONL에서 분모·recall·차이를 다시 계산한다.
같은 의미 판정을 재호출하는 검증이 아니라 집계·연결·누락/중복·anchor의 독립 재계산이다."""
import hashlib,json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
R=ROOT/'results'
I90=R/'iter_090/recovery'
OUT=R/'iter_094/analysis'

def jl(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def raw_text(path):
    out={}
    for line in Path(path).read_text().splitlines():
        r=json.loads(line);k=r['id'].removesuffix('|report');assert k not in out;out[k]=r['text']
    return out

def judged(stage,cond_filter):
    """stage의 blinded/mapping/judgments에서 {조건:{image:(text,judgment)}}를 만든다."""
    b=jl(stage/'blinded.json');m=jl(stage/'private_mapping.json');byb={r['blind_id']:r for r in b['records']}
    js={}
    for p in sorted((stage/'judgments').glob('part_*.json')):
        d=jl(p);assert d['blinded_sha']==sha(stage/'blinded.json')
        for j in d['judgments']:assert j['blind_id'] not in js;js[j['blind_id']]=j
    assert set(js)==set(byb)==set(m)
    out={}
    for bid,rec in byb.items():
        cond=Path(m[bid]['stage']).name
        if cond_filter(cond):
            assert rec['image_id'] not in out.setdefault(cond,{});out[cond][rec['image_id']]=(rec['text'],js[bid],m[bid])
    return out

def strict_vec(refs,jd):
    v=[]
    for ref in refs:
        pos=[a['id'] for a in ref['atoms'] if a['polarity']=='positive' and a['certainty']=='definite']
        text,j,_=jd[ref['id']]
        s={m['ref'] for m in j['matches'] if m['status']=='strict'}
        for c in j['claims']:assert c['quote'] in text
        for m in j['matches']:assert m['quote'] in text
        v.append(len(s&set(pos))/len(pos) if pos else None)
    return v

def main():
    refs=jl(R/'iter_090/semantic/V32_reference_v3.json')['rows']
    order=[r['id'] for r in refs];assert len(order)==32==len(set(order))
    j1=judged(R/'iter_094/semantic/epoch1',lambda c:True)
    j2=judged(I90/'semantic/epoch2',lambda c:c in('R_lr0.0002_report','G_lr0.0002_report','base_report'))
    j6=judged(I90/'semantic/epoch6',lambda c:c in('R_lr0.0002_report','G_lr0.0002_report'))
    V={('R',1):strict_vec(refs,j1['R_epoch1']),('G',1):strict_vec(refs,j1['G_epoch1']),
       ('R',2):strict_vec(refs,j2['R_lr0.0002_report']),('G',2):strict_vec(refs,j2['G_lr0.0002_report']),('base',0):strict_vec(refs,j2['base_report']),
       ('R',6):strict_vec(refs,j6['R_lr0.0002_report']),('G',6):strict_vec(refs,j6['G_lr0.0002_report'])}
    # 신규 출력의 raw 텍스트·record digest 연결
    for m in 'RG':
        raw=raw_text(R/f'iter_094/gen/{m}_epoch1/worker_0.jsonl');assert set(raw)==set(order)
        for img,(text,_,mp) in j1[f'{m}_epoch1'].items():
            assert text==raw[img] and mp['id']==img+'|report'
    summ=jl(OUT/'summary.json');checks={}
    for k,v in V.items():
        el=[x for x in v if x is not None];assert len(el)==20
        name=f'{k[0]}_lr0.0002@{k[1]}' if k[0]!='base' else 'base@0'
        checks[f'recall_{name}']=abs(float(np.mean(el))-summ['conditions'][name]['strict_recall'])<1e-12
    rng=np.random.default_rng(94017)
    def diff(a,b):
        d=np.array([x-y for x,y in zip(V[a],V[b]) if x is not None]);bs=np.array([d[rng.integers(0,20,20)].mean() for _ in range(10000)])
        return dict(mean=float(d.mean()),up=int((d>0).sum()),down=int((d<0).sum()),ci95=[float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5))],
                    loo_min=min(float(np.delete(d,i).mean()) for i in range(20)))
    # 요약과 같은 호출 순서(R6-R1, R2-R1, G6-G1, G2-G1)로 난수 사용 — analyze의 criterion은 main 외 두 민감도에도 난수를 쓰므로 CI는 평균·count만 비교
    comp={}
    for name,a,b in [('R_epoch6_vs_epoch1',('R',6),('R',1)),('R_epoch2_vs_epoch1',('R',2),('R',1)),('G_epoch6_vs_epoch1',('G',6),('G',1)),('G_epoch2_vs_epoch1',('G',2),('G',1))]:
        mine=diff(a,b);saved=summ['criteria'][name]['main']
        comp[name]=dict(mine=mine,saved_mean=saved['mean'],saved_up=saved['n_up'],saved_down=saved['n_down'],saved_loo_min=saved['loo_min'],
            match=abs(mine['mean']-saved['mean'])<1e-12 and mine['up']==saved['n_up'] and mine['down']==saved['n_down'] and abs(mine['loo_min']-saved['loo_min'])<1e-12)
    checks.update({f'diff_{k}':v['match'] for k,v in comp.items()})
    n_files=0
    for m in 'RG':
        st=R/f'iter_094/gen/{m}_epoch1';c=jl(st/'completion.json');assert c['n']==32 and all(sha(f)==h for f,h in c['files'].items());n_files+=1
    checks['completion_hash_ok']=n_files==2
    checks['n_unique_requests_new']=len({(m,i) for m in ('R','G') for i in j1[f'{m}_epoch1']})==64
    assert all(v for k,v in checks.items() if k!='n_unique_requests_new') and checks['n_unique_requests_new'],checks
    p=OUT/'verify.json';assert not p.exists();p.write_text(json.dumps(dict(checks=checks,all_pass=True,independent_bootstrap_ci=comp,
        scope='집계·연결·anchor·누락/중복의 독립 재계산. 의미 판정 자체의 독립 검증이 아니다.'),indent=1))
    print(json.dumps(dict(checks=checks),indent=1))

if __name__=='__main__':
    main()
