"""완료 출력과 byte 단위로 같은 가림 초안만 최종 평가에 연결한다."""
import json
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
OUT=ORIGINAL/'recovery/semantic'

def main():
    early=OUT/'epoch2_early';dest=OUT/'epoch2'
    snapshot=json.loads((early/'snapshot.json').read_text())
    final=json.loads((dest/'blinded.json').read_text());by={r['blind_id']:r for r in final['records']}
    assert snapshot['reference_sha']==final['reference_sha']
    mapping=json.loads((dest/'private_mapping.json').read_text())
    for row in snapshot['records']:
        assert row==by[row['blind_id']]
        assert snapshot['record_digests'][row['blind_id']]==mapping[row['blind_id']]['record_digest']
    files=[early/'judgments_v2/part_00.json',early/'judgments/part_01.json']
    promoted=[]
    for i,file in enumerate(files):
        value=json.loads(file.read_text());part=early/f'part_{i:02}.json'
        assert value['input_sha']==sha(part)
        expected={r['blind_id'] for r in json.loads(part.read_text())['outputs']}
        assert {j['blind_id'] for j in value['judgments']}==expected and len(value['judgments'])==len(expected)
        for j in value['judgments']:
            text=by[j['blind_id']]['text']
            for item in j['matches']+j['claims']:assert item['quote'] and item['quote'] in text
        target=dest/f'judgments/part_{i:02}.json'
        save(target,dict(blinded_sha=sha(dest/'blinded.json'),judgments=value['judgments'],
            inherited_draft=str(file),inherited_draft_sha=sha(file)))
        promoted.append(dict(source=str(file),source_sha=sha(file),target=str(target),target_sha=sha(target)))
    save(dest/'early_promotion.json',dict(passed=True,records=len(snapshot['records']),promoted=promoted,source_sha=sha(__file__)))
    print('PASS early judgments exact-output connection',len(snapshot['records']))

if __name__=='__main__':main()
