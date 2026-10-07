"""독립 검증기의 실제 진입점·점수 변조 거부 대조."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import report90_semantic_eval as E
import report90_semantic_verify as V
from report90_numeric import OUT
from report86_common import save,sha

def main():
    source=OUT/'tests/semantic_strata';root=OUT/'tests/semantic_independent';good=root/'good';good.mkdir(parents=True,exist_ok=False)
    refs=json.loads((source/'reference.json').read_text())
    for r in refs['rows']:
        r['report']='Finding present.'
        for a in r['atoms']:a.update(source=r['report'],start=0,end=len(r['report']))
    save(good/'reference.json',refs)
    blind=json.loads((source/'blinded.json').read_text());blind['reference_sha']=sha(good/'reference.json');save(good/'blinded.json',blind)
    save(good/'private_mapping.json',json.loads((source/'private_mapping.json').read_text()))
    judges=json.loads((source/'judgments/part_00.json').read_text());judges['blinded_sha']=sha(good/'blinded.json');save(good/'judgments/part_00.json',judges)
    E.main(SimpleNamespace(stage=str(good),reference=str(good/'reference.json')))
    V.verify(good,good/'reference.json',good/'verify.json')
    bad=root/'wrong_score';shutil.copytree(good,bad)
    rows=json.loads((bad/'eval/per_output.json').read_text());rows[0]['strict_recall']=0
    # 새 fixture 사본의 잘못된 값만 변경한다. 실제 산출물은 보존한다.
    (bad/'eval/per_output.json').write_text(json.dumps(rows))
    rejected=False
    try:V.verify(bad,bad/'reference.json',bad/'rejection.json')
    except AssertionError:rejected=True
    detail=json.loads((bad/'rejection.json').read_text());assert rejected and not detail['passed']
    assert any(x['field']=='b0/strict_recall' for x in detail['differences'])
    save(root/'result.json',dict(passed=True,valid_path=True,tampered_patient_score_rejected=True,source_sha={p:sha(p) for p in [__file__,'report90_semantic_verify.py','report90_semantic_eval.py']}))
    print('PASS independent verification and actual patient-score tamper rejection')
if __name__=='__main__':main()
