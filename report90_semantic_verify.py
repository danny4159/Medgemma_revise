"""생성문·판정 원문에서 환자 벡터를 별도로 재계산한다. 임상 판정 검증은 아니다."""
import argparse
from collections import Counter
import json
from pathlib import Path
import math
from report86_common import save,sha

METRICS=['strict_recall','type_recall','possible_only','no_ambiguous_reference','no_ambiguous_match',
         'contradiction','internal_contradiction','non_eos','format_failure']
RECALL=set(METRICS[:5])

def verify(stage,reference,output):
    stage=Path(stage);reference=Path(reference)
    refs=json.loads(reference.read_text())['rows'];refmap={r['id']:r for r in refs};assert len(refmap)==len(refs)
    blinded=json.loads((stage/'blinded.json').read_text());assert blinded['reference_sha']==sha(reference)
    for p,h in blinded['provenance'].items():assert sha(p)==h
    mapping=json.loads((stage/'private_mapping.json').read_text())
    generated={r['blind_id']:r for r in blinded['records']};assert len(generated)==len(blinded['records'])
    judgments=[]
    for p in sorted((stage/'judgments').glob('part_*.json')):
        d=json.loads(p.read_text());assert d['blinded_sha']==sha(stage/'blinded.json');judgments+=d['judgments']
    rated={j['blind_id']:j for j in judgments};assert len(rated)==len(judgments) and set(rated)==set(generated)==set(mapping)
    report=json.loads((stage/'eval/report.json').read_text())
    for p,h in report['provenance'].items():assert sha(p)==h
    scored=json.loads((stage/'eval/per_output.json').read_text());scores={r['blind_id']:r for r in scored}
    assert len(scores)==len(scored) and set(scores)==set(generated)
    differences=[];computed=[];anchors=0
    def same(label,x,y):
        ok=(x is None and y is None) or (x is not None and y is not None and math.isfinite(float(x)) and abs(float(x)-float(y))<=1e-12)
        if not ok:differences.append(dict(field=label,computed=x,stored=y))
    for bid,raw in generated.items():
        ref=refmap[raw['image_id']];j=rated[bid];stored=scores[bid];atoms={a['id']:a for a in ref['atoms']};assert len(atoms)==len(ref['atoms'])
        assert stored['image_id']==ref['id'] and stored['patient']==ref['patient'] and stored['abnormal']==ref['abnormal']
        assert stored['condition']==Path(mapping[bid]['stage']).name
        for atom in atoms.values():
            assert ref['report'][atom['start']:atom['end']]==atom['source'];anchors+=1
        seen=set()
        for m in j['matches']:
            assert m['ref'] in atoms and m['ref'] not in seen;seen.add(m['ref']);assert m['quote'] and m['quote'] in raw['text']
            assert m['status'] in ['strict','type_only','possible_only'] and atoms[m['ref']]['polarity']=='positive'
            if m['status']=='strict':
                for field in ['location','attributes']:
                    assert m[field] in ['match','na'] and (not atoms[m['ref']].get(field) or m[field]=='match')
        for kind in ['matches','claims']:
            assert len(stored[kind])==len(j[kind])
            for source,linked in zip(j[kind],stored[kind]):
                assert all(linked[k]==v for k,v in source.items());a=linked['anchor']
                assert raw['text'][a['start']:a['end']]==a['quote']==source['quote'];anchors+=1
        assert len(stored['internal_conflicts'])==len(j['internal_conflicts'])
        for pair,linked_pair in zip(j['internal_conflicts'],stored['internal_conflicts']):
            assert len(pair)==2 and pair[0]!=pair[1] and all(q and q in raw['text'] for q in pair);anchors+=2
            assert len(linked_pair)==2
            for q,a in zip(pair,linked_pair):assert raw['text'][a['start']:a['end']]==a['quote']==q
        positive=[a for a in atoms.values() if a['polarity']=='positive' and a['certainty']=='definite']
        selected={m['ref']:m for m in j['matches']}
        def recall(den,accepted,unambiguous=False):
            if not den:return None
            total=0
            for a in den:
                m=selected.get(a['id'])
                total+=int(m is not None and m['status'] in accepted and (not unambiguous or not m['ambiguous']))
            return total/len(den)
        row=dict(condition=stored['condition'],patient=ref['patient'],abnormal=ref['abnormal'],positive_n=len(positive),
            strict_recall=recall(positive,{'strict'}),type_recall=recall(positive,{'strict','type_only'}),
            possible_only=recall(positive,{'possible_only'}),no_ambiguous_reference=recall([a for a in positive if not a['ambiguous']],{'strict'}),
            no_ambiguous_match=recall(positive,{'strict'},True),contradiction=sum(c['status']=='contradicted' for c in j['claims'])>0,
            internal_contradiction=len(j['internal_conflicts'])>0,non_eos=raw['non_eos'],format_failure=bool(j.get('format_failure')))
        for key in METRICS+['positive_n']:same(bid+'/'+key,row[key],stored[key])
        assert dict(Counter(c['status'] for c in j['claims']))=={k:v for k,v in stored['claim_counts'].items() if v}
        computed.append(row)
    for condition,aggregate in report['conditions'].items():
        rows=[r for r in computed if r['condition']==condition]
        assert len(rows)==len(refs) and len({r['patient'] for r in rows})==len(rows)
        same(condition+'/n',len(rows),aggregate['n']);same(condition+'/abnormal_n',sum(r['abnormal'] for r in rows),aggregate['abnormal_n'])
        same(condition+'/recall_n',sum(r['abnormal'] and r['positive_n']>0 for r in rows),aggregate['recall_n'])
        for key in METRICS:
            vals=[r[key] for r in rows if r[key] is not None and (key not in RECALL or r['abnormal'])]
            same(condition+'/'+key,sum(vals)/len(vals) if vals else None,aggregate[key])
        for key in ['contradiction','internal_contradiction']:
            vals=[r[key] for r in rows if r['abnormal']];same(condition+'/'+key+'_abnormal',sum(vals)/len(vals),aggregate[key+'_abnormal'])
    result=dict(passed=not differences,outputs=len(computed),anchor_checks=anchors,differences=differences,
        sources={str(p):sha(p) for p in [reference,stage/'blinded.json',stage/'private_mapping.json',stage/'eval/report.json',stage/'eval/per_output.json',Path(__file__)]},
        scope='별도 원문/판정 계산의 정합성. assistant 의미 판정의 임상적 타당성이나 독립 평가자 합의가 아님.')
    save(output,result);assert result['passed'],differences[:5]
    print('PASS',len(computed),'outputs;',anchors,'anchors')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--reference',required=True);p.add_argument('--output',required=True);a=p.parse_args();verify(a.stage,a.reference,a.output)
