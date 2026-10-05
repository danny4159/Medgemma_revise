"""고정 조건·metric·gate 및 실제 실행 경로의 변조 거부 fixture."""
import argparse
import copy
from pathlib import Path
import numpy as np
import a81_common as C
import a81_eval as E
import a81_run as R
import rf78_vlm as V
import sp75_vlm as S
import sp75_metrics as M


def cpu(dest):
    checks = {}
    for split in ('V8','E24'):
        req = C.read(C.ROOT / f'data/requests_{split}.json')
        for r in req: C.check_request(r)
        by = {(r['id'],r['cond']): r for r in req}
        base = C.read(C.ROOT / f'data/baseline_{split}.json')
        for b in base:
            a,t,x,q = [by[b['id'], c] for c in ('A','T','X','Q')]
            assert a['prompt'] == x['prompt']
            assert a['automated_grade'] == t['automated_grade'] == x['automated_grade'] == b['C']
            assert t['images'] == [] and 'These are three' not in t['prompt']
            assert a['images'] == q['images']
            donors = sorted([r for r in base if r['ordinal'] == b['ordinal']], key=lambda r:int(r['patient']))
            j = next(i for i,r in enumerate(donors) if r['id'] == b['id'])
            donor = donors[(j+1)%len(donors)]
            assert x['donor'] == donor['id'] and donor['patient'] != b['patient']
            assert x['images'] == by[donor['id'],'A']['images']
        checks[f'{split}_all_requests_donor_gt_separation'] = True
    checks['parser'] = all(S.parse(s) == y for s,y in [('1',1),(' 5. ',5),('1 or 2',None),('0',None),('55',None)])
    checks['invalid_error4'] = M.abs_err([1,5],[None,3]).tolist() == [4,2]
    rows = [{'Q':None,'C':2,'probs':[.1,.4,.3,.1,.1]}, {'Q':4,'C':2,'probs':[.1,.4,.3,.1,.1]}]
    cs=E.candidates(rows)
    checks['strict_threshold_equal'] = cs['gate_0.4']['pred'] == [2,2]
    checks['fallback_argmax'] = cs['gate_0.6']['pred'] == [2,4]
    checks['median'] = cs['C_median']['pred'] == [2,2]
    checks['gate_calls_include_invalid'] = cs['gate_0.6']['calls'] == 2
    r=C.read(C.ROOT / 'data/requests_V8.json')[0]
    for field,value in [('automated_grade', 1 if r['automated_grade'] != 1 else 2), ('donor','different'), ('prompt','different')]:
        changed=copy.deepcopy(r); changed[field]=value
        checks[f'digest_{field}'] = C.request_key(changed) != C.request_key(r)
    bad=copy.deepcopy(r); bad['grade']=3
    try: C.check_request(bad)
    except ValueError as e: checks['GT_rejected'] = 'allowlist' in str(e)
    else: checks['GT_rejected'] = False
    C.save(dest, {'passed':all(checks.values()), 'checks':checks})
    assert all(checks.values()), checks
    print('CPU',len(checks),'PASS')


def proc(protocol, source, dest):
    p,reqs=R.load_protocol(protocol); done=R.verify(protocol, source)
    root=Path(dest).parent/'tamper_cases'; checks={}
    first=next(iter(done.values()))
    variants={'config': lambda x:x['config'].update(max_new_tokens=99),
              'adapter':lambda x:x.update(adapter_digest='wrong'),
              'request':lambda x:x['request'].update(automated_grade=0),
              'protocol':lambda x:x.update(protocol_digest='wrong')}
    for name, mutate in variants.items():
        d=root/name; x=copy.deepcopy(first); mutate(x)
        C.save(d/'worker0/records/one.json',x)
        try: R.records(d,p,reqs)
        except ValueError: checks[name]=True
        else: checks[name]=False
    d=root/'duplicate'
    for k in ('one','two'): C.save(d/f'worker0/records/{k}.json',first)
    try: R.records(d,p,reqs)
    except ValueError as e: checks['duplicate']='duplicate' in str(e)
    else: checks['duplicate']=False
    d=root/'missing'; C.save(d/'worker0/records/one.json',first)
    try: R.verify(protocol,d)
    except ValueError as e: checks['missing']='missing outputs' in str(e)
    else: checks['missing']=False
    bad=copy.deepcopy(p); bad['config']['batch']=2; bp=root/'wrong_protocol.json'; C.save(bp,bad)
    try: R.load_protocol(bp)
    except ValueError as e: checks['protocol_config']='config mismatch' in str(e)
    else: checks['protocol_config']=False
    bad=copy.deepcopy(p); bad['request_keys'][0]='wrong'; bp=root/'wrong_requests.json'; C.save(bp,bad)
    try: R.load_protocol(bp)
    except ValueError as e: checks['protocol_requests']='request digest' in str(e)
    else: checks['protocol_requests']=False
    checks['Q_suffix'] = all(x['suffix_ids'] == next(b['Q_suffix_ids'] for b in C.read(C.ROOT/'data/baseline_V8.json') if b['id']==x['request']['id'])
                             for x in done.values() if x['request']['cond']=='Q')
    C.save(dest, {'passed':all(checks.values()), 'checks':checks})
    assert all(checks.values()), checks
    print('PROC',len(checks),'PASS')


if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('mode',choices=['cpu','proc']); ap.add_argument('--dest',required=True)
    ap.add_argument('--protocol'); ap.add_argument('--source'); a=ap.parse_args()
    if a.mode=='cpu': cpu(a.dest)
    else: proc(a.protocol,a.source,a.dest)
