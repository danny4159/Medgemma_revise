"""E128 가림 판독 512건의 judgments 작성. 수동 spec(report92_spec_e)이 있으면 우선하고, 없으면 규칙표(report92_autojudge)를 쓴다.
규칙표로 처리되지 않은 출력은 --list로 확인해 사람이 읽고 수동 spec에 추가한다."""
import argparse
import importlib
import json
from pathlib import Path
from report86_common import save,sha
import report92_autojudge as A

ROOT=Path('results/iter_090/recovery/semantic/E')

def collect(spec):
    refs={r['id']:r for r in json.loads(Path('results/iter_090/recovery/semantic/E_reference.json').read_text())['rows']}
    order=list(refs);out={};todo=[];used=set()
    for k in range(32):
        part=json.loads((ROOT/f'part_{k:02}.json').read_text())
        for o in part['outputs']:
            hits=[p for p in spec if o['blind_id'].startswith(p)];assert len(hits)<=1,(o['blind_id'],hits)
            ref=refs[o['image_id']]
            if hits:
                s=spec[hits[0]];used.add(hits[0]);m,c,ic=s.get('m',[]),s.get('c',[]),s.get('ic',[])
                if s.get('add'):
                    # 규칙표가 처리한 문장에 수동 판정(미처리 문장)을 더한다. 미처리 문장은 수동 claim 인용이 덮어야 한다.
                    am,ac,bad=A.judge(o['text'],ref['atoms'],ref['abnormal'],partial=True)
                    skip=s.get('skip',[])
                    for b in bad:
                        assert any(b.startswith(p) for p in skip) or any(b[:25] in x['quote'] or x['quote'][:25] in b for x in c),(o['blind_id'],b)
                    m,c=am+m,ac+c
                    # 같은 ref의 중복 match는 strict 우선으로 하나만 둔다
                    best={}
                    for x in m:
                        if x['ref'] not in best or (x['status']=='strict' and best[x['ref']]['status']!='strict'):best[x['ref']]=x
                    m=list(best.values())
            else:
                try:m,c=A.judge(o['text'],ref['atoms'],ref['abnormal']);ic=[]
                except A.Unhandled as e:todo.append((order.index(o['image_id']),o,e.args[0]));continue
            best={}
            for x in m:
                if x['ref'] not in best or (x['status']=='strict' and best[x['ref']]['status']!='strict'):best[x['ref']]=x
            m=list(best.values())
            out[o['blind_id']]=dict(blind_id=o['blind_id'],matches=m,claims=c,internal_conflicts=ic,format_failure=bool(hits and spec[hits[0]].get('ff')))
    assert used==set(spec),set(spec)-used
    return refs,order,out,todo

def main(a):
    spec={}
    for name in ('report92_spec_e','report92_spec_e2'):
        if Path(name+'.py').exists():
            part=importlib.import_module(name).SPEC;assert not set(spec)&set(part);spec.update(part)
    refs,order,out,todo=collect(spec)
    if a.list or todo:
        last=-1
        for idx,o,bad in sorted(todo,key=lambda x:x[0]):
            r=refs[o['image_id']]
            if idx!=last:
                print('##',idx,'ABN' if r['abnormal'] else 'nor','|',r['report'])
                for at in r['atoms']:print('   ',at['id'][-3:],at['polarity'][0],at['certainty'][0],at['finding'],'|',at['location'],'|',at['attributes'],'|amb' if at['ambiguous'] else '')
                last=idx
            print('  >',o['blind_id'][:8],'NONEOS' if o['non_eos'] else '',repr(o['text'][:600]),'|| UNHANDLED:',[b[:60] for b in bad])
        print('unhandled outputs',len(todo),'handled',len(out));return
    blinded=ROOT/'blinded.json';(ROOT/'judgments').mkdir(exist_ok=True)
    for k in range(32):
        part=json.loads((ROOT/f'part_{k:02}.json').read_text())
        content=dict(blinded_sha=sha(blinded),judgments=[out[o['blind_id']] for o in part['outputs']])
        target=ROOT/'judgments'/f'part_{k:02}.json'
        if target.exists():assert json.loads(target.read_text())==json.loads(json.dumps(content));continue
        save(target,content)
    print('wrote',len(out),'judgments')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--list',action='store_true');main(p.parse_args())
