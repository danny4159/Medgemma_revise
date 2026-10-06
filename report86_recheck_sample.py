"""사후 점검 24명(층별 sha256('recheck86|ImageID') 최소 12명) 고정 목록. 규약에 사전 기재된 규칙이다. python report86_recheck_sample.py <stage>"""
import hashlib
import json
import sys

from report86_common import R86, STAGES, save

stage = sys.argv[1]
rows = json.loads(STAGES[stage]['inputs'].read_text())
sel = []
for stratum in ('abnormal', 'no_abnormal'):
    sub = [(i, r) for i, r in enumerate(rows) if r['stratum'] == stratum]
    sub.sort(key=lambda t: hashlib.sha256(f"recheck86|{t[1]['ImageID']}".encode()).hexdigest())
    sel += [{'index': i, 'ImageID': r['ImageID'], 'stratum': stratum} for i, r in sub[:12]]
sel.sort(key=lambda x: x['index'])
save(R86 / stage / 'recheck_sample.json', {'rule': "per stratum, first 12 by sha256('recheck86|ImageID')", 'patients': sel})
print([x['index'] for x in sel])
