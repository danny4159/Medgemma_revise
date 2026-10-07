"""실제 집계 진입점의 층별 분모 회귀와 기존 의미 fixture 재실행."""
import json
from types import SimpleNamespace
from pathlib import Path
import test_report90_semantic as old
import report90_semantic_eval as E
from report90_numeric import OUT
from report86_common import save,sha

def main():
    original=old.save
    old.save=lambda p,d:original(OUT/'tests/semantic_fixtures_v3.json',d)
    old.main()
    root=OUT/'tests/semantic_strata';root.mkdir(parents=True,exist_ok=False)
    refs=[];outputs=[];judgments=[];mapping={}
    for i,abnormal in enumerate([True,False]):
        atom=dict(id=f'a{i}',polarity='positive',certainty='definite',ambiguous=False)
        refs.append(dict(id=f'i{i}',patient=f'p{i}',abnormal=abnormal,atoms=[atom]))
        outputs.append(dict(blind_id=f'b{i}',image_id=f'i{i}',text='Finding present.',non_eos=False))
        mapping[f'b{i}']=dict(stage='condition')
        match=[dict(ref=f'a{i}',status='strict',quote='Finding present.',location='na',attributes='na',ambiguous=False)] if abnormal else []
        judgments.append(dict(blind_id=f'b{i}',matches=match,claims=[dict(finding='finding',polarity='positive',certainty='definite',
            status='supported' if abnormal else 'unknown',quote='Finding present.',refs=[f'a{i}'] if abnormal else [])],internal_conflicts=[]))
    save(root/'reference.json',dict(rows=refs));save(root/'blinded.json',dict(reference_sha=sha(root/'reference.json'),provenance={},records=outputs))
    save(root/'private_mapping.json',mapping);save(root/'judgments/part_00.json',dict(blinded_sha=sha(root/'blinded.json'),judgments=judgments))
    E.main(SimpleNamespace(stage=str(root),reference=str(root/'reference.json')))
    result=json.loads((root/'eval/report.json').read_text())['conditions']['condition']
    assert result['strict_recall']==1 and result['recall_n']==1 and result['n']==2 and result['abnormal_n']==1
    save(root/'test_result.json',dict(passed=True,checks=['actual_entrypoint_abnormal_recall_denominator','unknown_not_contradiction'],result=result,
        sources={p:sha(p) for p in [__file__,'report90_semantic_eval.py','test_report90_semantic.py']}))
    print('PASS: inherited 9 fixtures and actual-entrypoint stratum denominator')
if __name__=='__main__':main()
