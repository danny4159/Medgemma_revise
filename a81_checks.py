"""기술 실행의 실제 출력·봉인·재개·처리량 근거를 연결한다."""
import argparse
from pathlib import Path
import numpy as np
import a81_common as C
import a81_run as R


def old_sources():
    files = {}
    vp='results/iter_078/eval/report_V8.json'; v=C.read(vp)
    q='results/iter_077/gen/V8/R_lr2e-4_ep16/gen_worker0.jsonl'
    assert C.sha(q)==v['sources']['Q_src_sha256']['gen_worker0.jsonl']
    ep='results/iter_077/eval/eval_seal.json'; e=C.read(ep)
    for p,h in e['outputs'].items():
        if '/R_adapted/' in p:
            assert C.sha(p)==h; files[p]=h
    for p in (vp,ep,q): files[p]=C.sha(p)
    assert C.sha('results/iter_078/features.json')==v['sources']['features']
    C.save(C.ROOT/'tests/old_source_seals.json', {'passed':True,'files':files})


def compare(name, left, right):
    proto=C.ROOT/'protocol_tech.json'
    a=R.verify(proto,left); b=R.verify(proto,right)
    assert set(a)==set(b)
    mismatch=[k for k in a if a[k]['suffix_ids']!=b[k]['suffix_ids']]
    result={'passed':not mismatch,'n':len(a),'mismatch':mismatch,
            'files':{str(p):C.sha(p) for d in (left,right) for p in Path(d).glob('worker*/records/*.json')}}
    C.save(C.ROOT/f'tests/{name}.json', result)
    assert result['passed'],result
    print(name,len(a),'PASS')


def finalize(use4=False):
    root=C.ROOT/'tests'
    files={}
    for name in ('cpu','proc','old_source_seals','resume_compare','worker_lock','launcher_lock','selection_verify'):
        p=root/f'{name}.json'; d=C.read(p); assert d['passed']; files[str(p)]=C.sha(p)
        if 'files' in d: C.check_hashes(d['files']); files.update(d['files'])
    tech=list((root/'tech_w2').glob('worker*/tech_*.json'))
    assert len(tech)==2 and all(C.read(p)['passed'] and len(C.read(p)['checks'])==16 for p in tech)
    for p in tech: files[str(p)]=C.sha(p)
    pending=C.read(root/'pending_preserved_before.json')
    assert C.sha(pending['path'])==pending['sha256']
    files[str(root/'pending_preserved_before.json')]=C.sha(root/'pending_preserved_before.json')
    if use4:
        p=root/'concurrency_compare.json'; assert C.read(p)['passed']; files[str(p)]=C.sha(p)
    runs={}
    for name in ['tech_w2']+(['tech_w4'] if use4 else []):
        d=root/name; launches=list(d.glob('launch_*.json')); assert len(launches)==1
        l=C.read(launches[0]); assert not any(l['exit_codes'])
        rec=R.verify(C.ROOT/'protocol_tech.json',d)
        times=[r['runtime_s'] for r in rec.values()]
        runs[name]={'n':len(rec),'wall_s':l['wall_s'],'req_per_min_including_load':len(rec)/l['wall_s']*60,
                    'peak_used_mib':l['peak_used_mib'],'max_reserved_gib':max(r['peak_mem_reserved_gb'] for r in rec.values()),
                    'p95_generation_s':float(np.percentile(times,95)), 'longest_output_tokens':max(r['n_new'] for r in rec.values()),
                    'oom':False, 'exit_codes':l['exit_codes']}
        files[str(launches[0])]=C.sha(launches[0])
    chosen=4 if use4 and runs['tech_w4']['wall_s']<runs['tech_w2']['wall_s'] else 2
    C.save(C.ROOT/'resource_decision.json',{'runs':runs,'workers':chosen,'batch':1,
           'note':'정답 점수는 구성 선택에 미사용. 동일 16 요청·tensor 기술 검사 포함 wall. 작은 pilot의 적재/CPU 경합 포함; 비용 우위 일반화 금지.',
           'estimated_E24_wall_s':runs[f'tech_w{chosen}']['wall_s']*141/16})
    files[str(C.ROOT/'resource_decision.json')]=C.sha(C.ROOT/'resource_decision.json')
    C.save(root/'technical_gate.json',{'passed':True,'files':files,'selected_workers':chosen})
    print('technical gate PASS; workers',chosen)


def selection_verify():
    rows=C.read(C.ROOT/'data/baseline_V8.json'); saved=C.read(C.ROOT/'selection.json')
    candidates={}
    for name in ['Q','C_argmax','C_median']+[f'gate_{t}' for t in [.2,.4,.6,.8,1.01]]:
        preds=[]; calls=0; tau=float(name[5:]) if name.startswith('gate_') else -1
        for r in rows:
            if name=='Q': val=r['Q']; calls+=1
            elif name=='C_argmax': val=r['C']
            elif name=='C_median': val=next(i+1 for i in range(5) if sum(r['probs'][:i+1]) >= .5)
            else:
                use=max(r['probs'])<tau; calls+=use
                val=r['Q'] if use and r['Q'] is not None else r['C']
            preds.append(val)
        errors=[4 if p is None else abs(p-r['grade']) for r,p in zip(rows,preds)]
        class_mean=np.mean([np.mean([e for r,e in zip(rows,errors) if r['grade']==g]) for g in range(1,6) if any(r['grade']==g for r in rows)])
        candidates[name]=(float(class_mean),float(np.mean(errors)),int(calls),tau)
        assert preds==saved['candidates'][name]['pred']
    chosen=min(candidates,key=candidates.get)
    assert chosen==saved['name']
    C.save(C.ROOT/'tests/selection_verify.json',{'passed':True,'chosen':chosen,'scores':candidates,'selection_sha256':C.sha(C.ROOT/'selection.json')})


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['sources','compare','finalize','selection']); p.add_argument('--name'); p.add_argument('--left'); p.add_argument('--right'); p.add_argument('--use4',action='store_true'); a=p.parse_args()
    if a.mode=='sources': old_sources()
    elif a.mode=='compare': compare(a.name,a.left,a.right)
    elif a.mode=='selection': selection_verify()
    else: finalize(a.use4)
