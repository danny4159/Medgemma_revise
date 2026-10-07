"""E 출력 전에 직접 검토한 원자 정의를 원문 offset과 연결한다."""
import json
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
OUT=ORIGINAL/'recovery'

def main():
    data=OUT/'data/E128';manifest=data/'manifest.json';rows=json.loads(manifest.read_text())
    completed=json.loads((data/'completion.json').read_text());assert completed['passed']
    for p,h in completed['files'].items():assert sha(p)==h
    definitions=OUT/'semantic/E_definitions.json';manual=json.loads(definitions.read_text())
    assert manual['manifest_sha']==sha(manifest) and len(manual['rows'])==len(rows)==128
    assert not (OUT/'final_generation').exists(), 'reference는 E 생성 전에 작성'
    refs=[]
    for i,(row,definition) in enumerate(zip(rows,manual['rows'])):
        assert definition['id']==row['ImageID'] and definition['reviewed'] is True
        sentences=[f['sentence_en'].strip() for f in row['findings']]
        assert row['report']==' '.join(sentences)
        offsets=[];cursor=0
        for s in sentences:offsets.append(cursor);cursor+=len(s)+1
        atoms=[]
        for k,item in enumerate(definition['atoms']):
            indices,finding,polarity,certainty,location,attributes,ambiguous=item
            indices=[indices] if isinstance(indices,int) else indices
            assert indices and indices==sorted(set(indices)) and all(0<=j<len(sentences) for j in indices)
            assert polarity in ['positive','negative'] and certainty in ['definite','possible'] and isinstance(ambiguous,bool)
            start=offsets[indices[0]];end=offsets[indices[-1]]+len(sentences[indices[-1]])
            atoms.append(dict(id=f'E{i:03}A{k:02}',finding=finding,polarity=polarity,certainty=certainty,
                location=location,attributes=attributes,ambiguous=ambiguous,source=row['report'][start:end],start=start,end=end,
                source_index=indices,abnormal=any(row['findings'][j]['abnormal'] for j in indices)))
        assert atoms
        refs.append(dict(id=row['ImageID'],patient=row['PatientID'],report=row['report'],abnormal=row['retained_abnormal'],atoms=atoms))
    save(OUT/'semantic/E_reference.json',dict(rows=refs,manifest_sha=sha(manifest),definition_sha=sha(definitions),source_sha=sha(__file__),
        scope='생성 전 assistant 원문 의미 해석. 임상 gold 또는 전문의 판독 검증이 아님.'))
    print('E reference',len(refs),'patients',sum(len(r['atoms']) for r in refs),'atoms; generated outputs unopened')

if __name__=='__main__':main()
