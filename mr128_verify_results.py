"""production metric/parser를 import하지 않는 원 출력·부피 기반 독립 재계산."""
from fractions import Fraction
import csv
import json
from pathlib import Path
import re
import numpy as np
import nibabel as nib
from nibabel.processing import resample_from_to
from mr128_data import OUT,read,save,sha,utc,verify_files


def answer(row):
    if not row['eos']:return 'INVALID'
    lines=[l for l in row['text'].strip().splitlines() if l.strip()]
    if not lines:return 'INVALID'
    first=re.sub(r'[*_`#>\-:.\[\]()"]',' ',lines[0]).strip()
    found=[s for s in ['PRESENT','ABSENT','UNCERTAIN'] if re.search(r'\b'+s+r'\b',first,re.I)]
    return found[0] if len(found)==1 else 'INVALID'


def ba(y,p):
    positives=[i for i,v in enumerate(y) if v];negatives=[i for i,v in enumerate(y) if not v]
    return (Fraction(sum(p[i]=='PRESENT' for i in positives),len(positives))+
            Fraction(sum(p[i]=='ABSENT' for i in negatives),len(negatives)))/2


def volume_score(study):
    c=read(OUT/'seg/remaining'/(study+'.complete.json'))
    p=Path(c['directory'])/'vol.csv'
    with p.open(newline='') as f:table=list(csv.reader(f))
    v={k:float(n) for k,n in zip(table[0][1:],table[1][1:])}
    return (v['left lateral ventricle']+v['right lateral ventricle'])/v['total intracranial']


def main():
    report=read(OUT/'eval/report.json');saved=read(OUT/'eval/per_patient.json');cal=read(OUT/'calibration_lock.json')
    verify_files(report['provenance']['builds']);c=read(OUT/'gen/main/completion.json');verify_files(c['artifacts'])
    records=[]
    for p in sorted((OUT/'gen/main').glob('worker*.jsonl')):
        for line in p.read_text().splitlines():records.append(json.loads(line))
    if len(records)!=80 or len({r['id'] for r in records})!=80:raise ValueError('main raw complete80')
    lookup={(r['study_uid'],r['cond']):r for r in records};manifest=read(OUT/'evaluation_manifest.json')['records']
    rows=[];checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    for m in manifest:
        if m['role']!='explore':continue
        study=m['study_uid'];U=answer(lookup[(study,'U')]);A=answer(lookup[(study,'A')]);old=next(r for r in saved if r['study_uid']==study)
        check(study+':raw_states',U==old['U'] and A==old['A'])
        score=volume_score(study) if (OUT/'seg/remaining'/(study+'.complete.json')).exists() else None
        check(study+':official_S',score==old['S'])
        sp='PRESENT' if score is not None and cal['complete'] and score>=cal['result']['chosen']['threshold'] else 'ABSENT' if score is not None and cal['complete'] else None
        rows.append(dict(**m,U=U,A=A,S_state=sp,S=score))
    y=[int(r['label']=='positive') for r in rows];U=[r['U'] for r in rows];A=[r['A'] for r in rows]
    check('U_BA',float(ba(y,U))==report['U']['BA']);check('A_BA',float(ba(y,A))==report['A']['BA'])
    cells={}
    for i,r in enumerate(rows):cells.setdefault((r['batch_id'],r['label']),[]).append(i)
    comparisons=[('A','U',report['A_minus_U'])]
    if report['S_complete']:
        S=[r['S_state'] for r in rows];check('S_BA',float(ba(y,S))==report['S']['BA'])
        comparisons.extend([('S_state',k,report['S_minus'][k]) for k in ['U','A']])
        scores=[r['S'] for r in rows];pos=[s for s,v in zip(scores,y) if v];neg=[s for s,v in zip(scores,y) if not v]
        roc=sum((1 if a>b else .5 if a==b else 0) for a in pos for b in neg)/(len(pos)*len(neg))
        check('S_AUROC',roc==report['S_AUROC_available'])
    available=[r for r in rows if r['S'] is not None]
    if available:
        pos=[r['S'] for r in available if r['label']=='positive'];neg=[r['S'] for r in available if r['label']=='negative']
        roc=sum((1 if a>b else .5 if a==b else 0) for a in pos for b in neg)/(len(pos)*len(neg)) if pos and neg else None
        check('available_S_AUROC',roc==report['S_AUROC_available'])
        if cal['complete']:
            check('available_S_BA',float(ba([int(r['label']=='positive') for r in available],[r['S_state'] for r in available]))==report['S_available_metrics']['BA'])
    for first,second,old in comparisons:
        rng=np.random.default_rng(125);values=[]
        a=[r[first] for r in rows];b=[r[second] for r in rows]
        for _ in range(10000):
            ix=[]
            for cell in sorted(cells):ix.extend(rng.choice(cells[cell],len(cells[cell]),replace=True).tolist())
            yy=[y[i] for i in ix];aa=[a[i] for i in ix];bb=[b[i] for i in ix]
            values.append(float(ba(yy,aa)-ba(yy,bb)))
        check(first+'-'+second+':mean',float(ba(y,a)-ba(y,b))==old['mean'])
        check(first+'-'+second+':CI95',np.allclose(np.quantile(values,[.025,.975]),old['CI95'],atol=1e-12))
    if report['S_available_minus']:
        cells_available={}
        for i,r in enumerate(available):cells_available.setdefault((r['batch_id'],r['label']),[]).append(i)
        for second,old in report['S_available_minus'].items():
            rng=np.random.default_rng(125);values=[]
            yy=[int(r['label']=='positive') for r in available];ss=[r['S_state'] for r in available];other=[r[second] for r in available]
            for _ in range(10000):
                ix=[i for cell in sorted(cells_available) for i in rng.choice(cells_available[cell],len(cells_available[cell]),replace=True).tolist()]
                values.append(float(ba([yy[i] for i in ix],[ss[i] for i in ix])-ba([yy[i] for i in ix],[other[i] for i in ix])))
            check('available_S-'+second,float(ba(yy,ss)-ba(yy,other))==old['mean'] and np.allclose(np.quantile(values,[.025,.975]),old['CI95'],atol=1e-12))
    if cal['complete']:
        calibration=[dict(m,S=volume_score(m['study_uid'])) for m in manifest if m['role']=='calib']
        ys=[int(r['label']=='positive') for r in calibration];scores=[r['S'] for r in calibration];v=sorted(set(scores))
        candidates=[0.0]+[(a+b)/2 for a,b in zip(v,v[1:])]+[float(np.nextafter(v[-1],np.inf))]
        def rank(t):
            p=['PRESENT' if s>=t else 'ABSENT' for s in scores]
            spec=sum(not y and z=='ABSENT' for y,z in zip(ys,p))/sum(not y for y in ys)
            return ba(ys,p),spec,t
        chosen=max(candidates,key=rank)
        check('calibration_only_threshold',chosen==cal['result']['chosen']['threshold'])
    # production 비용/분기 함수를 사용하지 않고 실제 stage sidecar를 다시 연결한다.
    costs=read(OUT/'eval/per_patient_costs.json')
    check('cost_patient_set',len(costs)==40 and {r['study_uid'] for r in costs}=={r['study_uid'] for r in rows})
    groups=[g for p in sorted((OUT/'gen/main').glob('*.worker*.events.json')) for g in read(p)['groups']]
    group_pairs=[(i,g) for g in groups for i in g['ids']]
    check('cost_request_set',len(group_pairs)==80 and {i for i,g in group_pairs}=={r['id'] for r in records})
    group_lookup=dict(group_pairs);cost_lookup={r['study_uid']:r for r in costs}
    for row in saved:
        study=row['study_uid'];build=read(OUT/'build/remaining'/(study+'.json'));cost=cost_lookup[study]
        cpath=OUT/'seg/remaining'/(study+'.complete.json')
        if cpath.exists():
            seg=read(cpath);verify_files(seg['result']['artifacts'])
            native=nib.load(build['source_input']['files']['img.nii.gz']['path'])
            mask=nib.load(Path(seg['directory'])/'seg.nii.gz')
            restored=nib.as_closest_canonical(resample_from_to(mask,(native.shape,native.affine),order=0,mode='constant',cval=0))
            areas=np.sum(np.isin(np.asarray(restored.dataobj),[4,43]),axis=(0,1))
            keep=np.flatnonzero(areas>=.05*areas.max()) if areas.max()>0 else []
            selected=np.rint(np.linspace(int(keep[0]),int(keep[-1]),8)).astype(int).tolist() if len(keep) else []
            fallback=None if len(set(selected))==8 else 'lt8_unique' if len(keep) else 'no_ventricle_voxels'
            expected=selected if fallback is None else build['U_idx']
            check(study+':native_A_fallback',row['A_fallback']==fallback and row['A_idx']==expected)
        else:
            check(study+':seg_failure_fallback',row['A_fallback'] is not None and row['A_idx']==row['U_idx'] and row['S'] is None)
        ug=group_lookup[row['U_request']];ag=group_lookup[row['A_request']]
        u=ug['end_after_saved']-ug['start'];a=ag['end_after_saved']-ag['start'];render=build['warm_read_to_saved_s']
        check(study+':VLM_cost',cost['U_warm_raw_to_answer_s']==u and cost['A_VLM_warm_raw_to_answer_s']==a and u>0 and a>0)
        check(study+':shared_extra_cost',cost['A_extra_after_shared_S_s']==render+a and cost['A_mask_restore_render_s']==render)
        tp=OUT/'seg/remaining'/(study+'.timing.json')
        if tp.exists():
            t=read(tp);s=t['answer_saved_monotonic']-t['official']['warm_start_monotonic']
            check(study+':S_cost',s==t['warm_raw_read_to_S_answer_saved_s']==cost['S_warm_raw_to_score_answer_s'] and t['answer_sha256']==sha(cpath) and s>0)
            check(study+':A_component_cost',cost['A_independent_warm_component_sum_s']==s+render+a)
    check('fallback_count',sum(r['A_fallback'] is not None for r in saved)==report['fallback_n'])
    check('U_cost_mean',float(np.mean([r['U_warm_raw_to_answer_s'] for r in costs]))==report['costs']['U_warm_mean_s'])
    if report['costs']['complete']:
        s_cost=float(np.mean([r['S_warm_raw_to_score_answer_s'] for r in costs]));a_cost=float(np.mean([r['A_independent_warm_component_sum_s'] for r in costs]))
        check('S_A_cost_means',s_cost==report['costs']['S_warm_mean_s'] and a_cost==report['costs']['A_independent_warm_component_sum_mean_s'])
    else:s_cost=a_cost=None
    gap=ba(y,A)-ba(y,U);a_ba=ba(y,A);u_ba=ba(y,U)
    sensitivity=sum(v and z=='PRESENT' for v,z in zip(y,A))/sum(y)
    specificity=sum(not v and z=='ABSENT' for v,z in zip(y,A))/sum(not v for v in y)
    positive=gap>=Fraction('0.15') and report['A_minus_U']['CI95'][0]>0 and a_ba>=Fraction('.75') and sensitivity>=.65 and specificity>=.65
    sufficient=report['S_complete'] and ba(y,S)>=Fraction('.80') and a_ba-ba(y,S)<Fraction('.05') and a_cost is not None and s_cost is not None and a_cost>s_cost
    negative=u_ba<=Fraction('.60') and a_ba<=Fraction('.60')
    investment='단순 대안 이후 현재 이진 과제 VLM 방법 투자 보류' if sufficient else '현재 frozen 설계 종료' if negative else '제한된 sampling 관찰 보존; 독립 확인/방법 진입은 GPT의 별도 판단' if positive else '근거 부족으로 현재 설계 보류'
    check('original_decision_contract',report['decision']==dict(positive_sampling_observation=bool(positive),simple_alternative_sufficient=bool(sufficient),negative_frozen_design=bool(negative),investment=investment,no_automatic_expansion=True,clinical_accuracy_claim=False))
    check('pre_generation_source_lock',verify_files(read(OUT/'main_analysis_lock.json')['code']) is None)
    ok=all(c['passed'] for c in checks)
    save(OUT/'eval/independent_verify.json',dict(created_utc=utc(),all_pass=ok,checks=checks,
         source_sha256=sha(__file__),report_sha256=sha(OUT/'eval/report.json'),
         per_patient_sha256=sha(OUT/'eval/per_patient.json'),main_completion_sha256=sha(OUT/'gen/main/completion.json'),
         scope_ko='원시 문자열·공식 CSV로 상태/BA/AUROC/threshold/10,000회 paired CI와 native mask fallback·비용 sidecar·원 분기를 재계산. 임상 의미 정답의 독립 검증은 아니다.'))
    print('independent results',sum(c['passed'] for c in checks),'/',len(checks));return 0 if ok else 2


if __name__=='__main__':raise SystemExit(main())
