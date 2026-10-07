"""집계 함수를 import하지 않는 별도 산술·DSL 검증. 의미 재판정의 대체재가 아니다."""
import hashlib
import json
import re
import shlex
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results/iter_088'
CONDS=['M15-R','M15-S','B0-R','B0-S','M1-R','M1-G','C-G','C-H']
PAIRS=[('B0-R','M15-R'),('M15-S','M15-R'),('B0-S','M15-S'),('C-G','M1-G'),('C-H','C-G')]


def order(img):
    return sorted(CONDS,key=lambda c:hashlib.sha256(('blind86|'+img+'|'+c).encode()).hexdigest())


def parse(text,rows,structured):
    result={}; seen=set(); img=None; c=None
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'): continue
        t=shlex.split(line)
        if re.fullmatch('P[0-9]{3}',t[0]):
            n=int(t[0][1:]); assert n not in seen; seen.add(n)
            img=rows[n]['ImageID']; continue
        if re.fullmatch('O[1-8]',t[0]):
            c=order(img)[int(t[0][1:])-1]; assert (img,c) not in result
            o=result[img,c]={'facts':{},'claims':[],'internal':[]}; continue
        if '--' in t: t=t[:t.index('--')]
        if t[0]=='f':
            f={'s':t[2], 'loc':t[3] if t[2] in ('D','P') else None,'attr':t[4] if t[2] in ('D','P') else None}
            assert t[1] not in o['facts']; o['facts'][t[1]]=f
            assert all(structured[img][c]['facts'][t[1]][k]==v for k,v in f.items())
        elif t[0]=='c':
            k=len(o['claims']); z=structured[img][c]['claims'][k]
            refs=[] if t[2]=='-' else t[2].split(',')
            assert (t[1],refs,t[3],t[4],t[5] if len(t)>5 else None)==(z['cls'],z['refs'],z['pol']+z['cert'],z['anchor'],z['at'])
            # n는 raw segment source의 고유 개수. 문자 반복 횟수와 구분한다.
            n=len({(p['seg'],p['source']) for p in z['occ']})
            assert n==z['n']
            o['claims'].append((t[1],refs,t[3],n))
        elif t[0]=='i': o['internal'].append(t[1])
    assert seen==set(range(96)) and len(result)==768
    return result


def calculate(o,fs):
    flat={}; counts={}; comp={k:0 for k in ['neg_v1','neg_new','neg_new_weakonly','pos_neg','pos_neg_other','loc','attr','neg_v1_poss','pos_neg_poss']}
    for v in ('v1','v2'):
        ids=[f for f,z in fs.items() if z[v+'_class']=='pos_def']; st=[o['facts'][f] for f in ids]; n=len(st)
        d=sum(f['s']=='D' for f in st); p=sum(f['s']=='P' for f in st)
        ds=sum(f['s']=='D' and f['loc'] in ('m','n') and f['attr'] in ('m','n') for f in st)
        counts[v]={'n':n,'D':d,'P':p,'N':sum(f['s']=='N' for f in st),'n_hedged':sum(f['s']=='n' for f in st),'D_strict':ds}
        for typ in ('loc','attr'):
            for status in ('c','o'):
                counts[v][typ+'_'+status]=sum(f['s'] in ('D','P') and f[typ]==status for f in st)
        for m,val in [('recall_def',d),('recall_strict',ds),('recall_incl_possible',d+p)]:flat[m+'_'+v]=val/n if n else None
        for typ in ('loc','attr'): flat[typ+'_c_'+v]=counts[v][typ+'_c'] if n else None
    wide=[f for f,z in fs.items() if z['v2_class'] in ('pos_def','pos_hedged','pos_temporal')]
    flat['recall_wide_D']=sum(o['facts'][f]['s']=='D' for f in wide)/len(wide) if wide else None
    cl={k:0 for k in ('S','C','U','S_d','S_p','C_d','C_p','U_d','U_p','n_total')}
    for kind,refs,pc,n in o['claims']:
        group=kind if kind in ('S','U') else 'C'; cl[group]+=n;cl[group+'_'+pc[1]]+=n; cl['n_total']+=n
        ff=[fs[f] for f in refs]
        if kind=='C.neg':
            old=any(f['v1_class']=='neg_specific' for f in ff)
            if pc[1]=='d':
                comp['neg_v1']+=n*old
                strong=any(f['v2_class']=='normal_scoped' and not f['weak'] for f in ff)
                comp['neg_new']+=n*strong
                comp['neg_new_weakonly']+=n*(not strong and not old and any(f['v2_class']=='normal_scoped' for f in ff))
            else:comp['neg_v1_poss']+=n*old
        elif kind=='C.pos':
            key=('pos_neg' if any(f['v2_class']=='pos_def' for f in ff) else 'pos_neg_other') if pc[1]=='d' else 'pos_neg_poss'
            comp[key]+=n
        if pc[1]=='d':
            comp['loc']+=n*(kind in ('C.loc','C.locattr'));comp['attr']+=n*(kind in ('C.attr','C.locattr'))
    olddef=any(f['v1_class'] in ('pos_def','neg_specific') for f in fs.values())
    ext=olddef or any(f['v2_class']=='normal_scoped' for f in fs.values())
    oldfacts=[o['facts'][k] for k,f in fs.items() if f['v1_class']=='pos_def']
    flat['contra_common']=int(bool(comp['neg_v1'] or any(f['s']=='N' or (f['s'] in ('D','P') and f['loc']=='c') for f in oldfacts))) if olddef else None
    flat['contra_v2']=int(any(comp[k] for k in ('neg_v1','neg_new','pos_neg','loc','attr'))) if ext else None
    flat['contra_v2_noweak']=int(any(comp[k] for k in ('neg_v1','pos_neg','loc','attr'))) if ext else None
    for a,b in [('contra_neg_v1','neg_v1'),('contra_neg_new','neg_new'),('contra_pos_neg','pos_neg'),('contra_loc','loc'),('contra_attr','attr')]: flat[a]=int(comp[b]>0) if ext else None
    for k in ('d','p'): flat['internal_'+k]=int(k in o['internal'])
    for k in ('S','C','U'): flat['claims_'+k]=cl[k]
    flat['claims_total']=cl['n_total']
    return flat,counts,cl,comp


def ci(d,rng):
    d=np.asarray(d,dtype=np.float64)
    a=d[rng.integers(0,len(d),size=(10000,len(d)))].mean(axis=1)
    return np.quantile(a,[.025,.975]).tolist()


def close(a,b):
    if a is None or b is None: return a is b
    return bool(np.allclose(a,b,atol=1e-12,rtol=0))


def compare(flat,report,rows,metrics,fresh=True):
    nchecks=0; rng=np.random.default_rng(84017)
    for sn in ('all','abnormal','no_abnormal'):
        ids=[r['ImageID'] for r in rows if sn=='all' or r['stratum']==sn]
        for c in CONDS:
            for m in metrics:
                vals=[flat[i,c][m] for i in ids if flat[i,c][m] is not None]
                z=report['summary'][sn]['conditions'][c][m]
                if m=='claims_total': continue # 이 필드는 summary에서 상세 dict로 바뀜
                assert z['n']==len(vals) and close(z['mean'],float(np.mean(vals)) if vals else None),(sn,c,m,z)
                nchecks+=1
        for a,b in PAIRS:
            for m in metrics:
                d=[flat[i,a][m]-flat[i,b][m] for i in ids if flat[i,a][m] is not None and flat[i,b][m] is not None]
                z=report['comparisons'][sn][a+'-'+b][m]
                if not d: assert z is None;continue
                bounds=ci(d,np.random.default_rng(84017) if fresh else rng) if len(d)>1 else None
                assert z['n']==len(d) and close(z['diff'],np.mean(d)) and close(z['ci95'],bounds),(sn,a,b,m,z,bounds)
                nchecks+=1
    return nchecks


def old_parse(text,rows,amend):
    flat={};img=None
    for l in text.splitlines():
        l=l.strip()
        if not l or l.startswith('#'):continue
        if re.fullmatch('P[0-9]{3}',l): img=rows[int(l[1:])]['ImageID']; continue
        oid,body=l.split(':',1);c=order(img)[int(oid[1:])-1]
        fpart,cpart,ipart,xpart=re.split(r'\s;\s',body)
        facts={k:(s,loc) for k,s,loc in re.findall(r'(F\d+)=([DPNU])([+~\-]?)',fpart)}
        defs=[f['fact_id'] for f in amend[img]['facts'] if f['v1_class']=='pos_def']
        wide=[f['fact_id'] for f in amend[img]['facts'] if f['v1_class'] in ('pos_def','pos_hedged','pos_temporal')]
        neg=[f for f in amend[img]['facts'] if f['v1_class']=='neg_specific']
        d=sum(facts[f][0]=='D' for f in defs);p=sum(facts[f][0]=='P' for f in defs)
        wrong=sum(facts[f]==('D','-') for f in defs);n=len(defs); nd=sum(facts[f][0]=='N' for f in defs)
        ca=len(re.findall(r'd:F\d+',cpart)); xd,xp=map(int,re.findall(r'\d+',xpart))
        flat[img,c]={'recall_def':d/n if n else None,'recall_strict':sum(facts[f][0]=='D' and facts[f][1] in ('','+') for f in defs)/n if n else None,
          'recall_incl_possible':(d+p)/n if n else None,'recall_wide_D':sum(facts[f][0]=='D' for f in wide)/len(wide) if wide else None,
          'contra_primary':int(bool(ca or nd or wrong)) if n or neg else None,'contra_a_only':int(ca>0) if neg else None,
          'internal':int(ipart.strip()[2:]),'xd':xd,'xp':xp}
    assert len(flat)==768
    return flat


def main():
    report=json.loads((OUT/'eval/report.json').read_text())
    structured=json.loads((OUT/'eval/judgments_structured.json').read_text())
    # 환자 순서는 고정된 판정 파일의 원 inputs 경로에서 얻는다.
    from report86_common import STAGES
    rows=json.loads(STAGES['E96']['inputs'].read_text())
    amend=json.loads((ROOT/'results/iter_087/reference_amend_E96.json').read_text())['patients']
    parsed=parse((OUT/'adjudication/judgments_final.txt').read_text(),rows,structured)
    flats={};cellchecks=0
    for (img,c),o in parsed.items():
        fl,counts,cl,comp=calculate(o,{f['fact_id']:f for f in amend[img]['facts']});flats[img,c]=fl
        ref=report['per_output'][img+'|'+c]
        for v in ('v1','v2'):
            for k,x in counts[v].items(): assert ref[v][k]==x,(img,c,k);cellchecks+=1
        for k,x in cl.items(): assert ref['claims'][k]==x;cellchecks+=1
        assert ref['contra_components']==comp
        for k in ('d','p'):assert ref['internal_'+k]==o['internal'].count(k)
    checks=compare(flats,report,rows,list(next(iter(flats.values()))))
    old=old_parse((ROOT/'results/iter_086/E96/judgments_E96_v2.txt').read_text(),rows,amend)
    saved=json.loads((ROOT/'results/iter_086/E96/eval_v2/report.json').read_text())
    oldchecks=compare(old,saved,rows,list(next(iter(old.values()))),fresh=False)
    original=old_parse((ROOT/'results/iter_086/E96/judgments_E96.txt').read_text(),rows,amend)
    original_saved=json.loads((ROOT/'results/iter_086/E96/eval/report.json').read_text())
    originalchecks=compare(original,original_saved,rows,list(next(iter(original.values()))),fresh=False)
    recomputed=json.loads((OUT/'eval/original_v1_recomputed.json').read_text())
    recomputedchecks=compare(old,recomputed,rows,list(next(iter(old.values()))),fresh=False)
    # precision·coverage를 별도 합산한다.
    precision_checks=0
    for sn in ('all','abnormal','no_abnormal'):
        ids=[r['ImageID'] for r in rows if sn=='all' or r['stratum']==sn]
        for c in CONDS:
            s=sum(flats[i,c]['claims_S'] for i in ids);co=sum(flats[i,c]['claims_C'] for i in ids);u=sum(flats[i,c]['claims_U'] for i in ids)
            ref=report['summary'][sn]['conditions'][c]['claims_total'];t=s+co+u
            for k,x in [('precision_lower',s/t),('precision_upper',(s+u)/t),('coverage',(s+co)/t)]:assert close(ref[k],x);precision_checks+=1
    files=[OUT/'adjudication/judgments_final.txt',OUT/'eval/report.json',OUT/'eval/judgments_structured.json',OUT/'eval/original_v1_recomputed.json',ROOT/'results/iter_086/E96/eval/report.json',ROOT/'results/iter_086/E96/eval_v2/report.json',ROOT/'results/iter_086/E96/judgments_E96.txt',ROOT/'results/iter_086/E96/judgments_E96_v2.txt',ROOT/'results/iter_087/reference_amend_E96.json',Path(__file__)]
    res={'passed':True,'parsed_outputs':len(parsed),'per_output_count_checks':cellchecks,'new_summary_ci_checks':checks,'original_summary_ci_checks':originalchecks,'iter086_corrected_v1_checks':oldchecks,'recomputed_v1_checks':recomputedchecks,'precision_checks':precision_checks,
         'recovered_error':'최초 검증은 judgments_E96_v2.txt를 eval/report.json에 대조해 실패. 원본 대 eval, 보완본 대 eval_v2로 각각 연결하여 재검증. 판정/결과 수정 없음.',
         'max_allowed_error':1e-12,'bootstrap':{'seed':84017,'n':10000,'unit':'patient paired','old_rng':'상속 순차 RNG','new_rng':'비교별 고정 RNG'},
         'scope':'집계 함수 재호출 없음. raw DSL 별도 파싱·판정 대조, 원 지표 및 수정 지표의 산술 검증. claim multiplicity는 검증된 segment provenance에서 재계산; 의미 독립 검증 아님.',
         'files':{str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (OUT/'verify').mkdir(exist_ok=True)
    with (OUT/'verify/independent.json').open('x') as f:json.dump(res,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in res.items() if k!='files'},ensure_ascii=False))


if __name__=='__main__':main()
