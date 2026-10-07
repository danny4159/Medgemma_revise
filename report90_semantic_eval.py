"""원문 연결된 assistant 판정의 집계. 의미 판정 자체를 자동 추정하지 않는다."""
import argparse
import json
from pathlib import Path
import numpy as np
from report86_common import sha,save

def anchor(text,quote):
    assert quote and quote in text,('unlinked quote',quote)
    start=text.index(quote);return dict(quote=quote,start=start,end=start+len(quote))

def score(ref,output,j):
    text=output['text'];atoms={a['id']:a for a in ref['atoms']};seen=set();matches=[]
    for m in j['matches']:
        assert m['ref'] in atoms and m['ref'] not in seen;seen.add(m['ref'])
        assert m['status'] in ['strict','type_only','possible_only']
        a=atoms[m['ref']];assert a['polarity']=='positive'
        if m['status']=='strict':
            assert m['location'] in ['match','na'] and m['attributes'] in ['match','na']
            if a.get('location'):assert m['location']=='match'
            if a.get('attributes'):assert m['attributes']=='match'
        else:
            assert m['location'] in ['match','missing','conflict','ambiguous','na']
            assert m['attributes'] in ['match','missing','conflict','ambiguous','na']
        matches.append(dict(m,anchor=anchor(text,m['quote'])))
    claims=[]
    for c in j['claims']:
        assert c['status'] in ['supported','contradicted','unknown']
        assert c['certainty'] in ['definite','possible'] and c['polarity'] in ['positive','negative']
        assert all(x in atoms for x in c['refs'])
        assert c['finding']
        if c['status']!='unknown':assert c['refs']
        claims.append(dict(c,anchor=anchor(text,c['quote'])))
    assert claims or not text.strip() or j.get('format_failure'), 'nonempty output needs semantic review'
    conflicts=[]
    for pair in j['internal_conflicts']:
        assert len(pair)==2 and pair[0]!=pair[1]
        conflicts.append([anchor(text,q) for q in pair])
    positive=[a for a in atoms.values() if a['polarity']=='positive' and a['certainty']=='definite']
    strict={m['ref'] for m in matches if m['status']=='strict'};kinds={m['ref'] for m in matches if m['status'] in ['strict','type_only']}
    possible={m['ref'] for m in matches if m['status']=='possible_only'}
    unamb=[a for a in positive if not a['ambiguous']];sure={m['ref'] for m in matches if m['status']=='strict' and not m['ambiguous']}
    ratio=lambda ids,den:sum(a['id'] in ids for a in den)/len(den) if den else None
    return dict(blind_id=output['blind_id'],image_id=ref['id'],patient=ref['patient'],abnormal=ref['abnormal'],
        positive_n=len(positive),strict_recall=ratio(strict,positive),type_recall=ratio(kinds,positive),possible_only=ratio(possible,positive),
        no_ambiguous_reference=ratio(strict,unamb),no_ambiguous_match=ratio(sure,positive),
        contradiction=any(c['status']=='contradicted' for c in claims),internal_contradiction=bool(conflicts),
        non_eos=output['non_eos'],format_failure=bool(j.get('format_failure')),matches=matches,claims=claims,internal_conflicts=conflicts,
        claim_counts={s:sum(c['status']==s for c in claims) for s in ['supported','contradicted','unknown']})

def main(a):
    root=Path(a.stage);reference=Path(a.reference);refs=json.loads(reference.read_text())['rows'];byref={r['id']:r for r in refs}
    blinded=json.loads((root/'blinded.json').read_text());assert blinded['reference_sha']==sha(reference)
    for p,h in blinded['provenance'].items():assert sha(p)==h
    outputs=blinded['records'];byout={r['blind_id']:r for r in outputs};assert len(byout)==len(outputs)
    mapping=json.loads((root/'private_mapping.json').read_text());assert set(mapping)==set(byout)
    judgments=[];files=sorted((root/'judgments').glob('part_*.json'));assert files
    for file in files:
        d=json.loads(file.read_text());assert d['blinded_sha']==sha(root/'blinded.json');judgments.extend(d['judgments'])
    byj={r['blind_id']:r for r in judgments};assert len(byj)==len(judgments) and set(byj)==set(byout)
    per=[]
    for bid,out in byout.items():
        s=score(byref[out['image_id']],out,byj[bid]);s['condition']=Path(mapping[bid]['stage']).name;per.append(s)
    report={}
    for condition in sorted({x['condition'] for x in per}):
        rows=[x for x in per if x['condition']==condition];assert len(rows)==len(refs)
        report[condition]=dict(n=len(rows),abnormal_n=sum(x['abnormal'] for x in rows),recall_n=sum(x['abnormal'] and x['strict_recall'] is not None for x in rows))
        for k in ['strict_recall','type_recall','possible_only','no_ambiguous_reference','no_ambiguous_match','contradiction','internal_contradiction','non_eos','format_failure']:
            recall_metric=k in ['strict_recall','type_recall','possible_only','no_ambiguous_reference','no_ambiguous_match']
            vals=[x[k] for x in rows if x[k] is not None and (x['abnormal'] or not recall_metric)];report[condition][k]=float(np.mean(vals)) if vals else None
        for k in ['contradiction','internal_contradiction']:
            report[condition][k+'_abnormal']=float(np.mean([x[k] for x in rows if x['abnormal']]))
    dest=root/'eval';save(dest/'per_output.json',per)
    save(dest/'report.json',dict(conditions=report,provenance={str(p):sha(p) for p in [reference,root/'blinded.json',root/'private_mapping.json',*files,Path(__file__)]},
        scope='assistant reference/anchor judgments; not clinician assessment or clinical precision'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--reference',required=True);main(p.parse_args())
