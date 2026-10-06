"""판정 규칙 일관성 스캔(CPU, 읽기 전용): reference에 장치성 소견이 있는 환자에서 출력이 '장치/이물 없음'을 서술한 경우의 판정을 열거한다.
규약: 장치 부재 서술('No visible devices', 'No radiopaque foreign bodies')은 장치성 사실에 대해 N. 일관되지 않은 판정은 별도 수정본에서 같은 규칙으로 전 환자에 적용한다.
python report86_consistency_scan.py <stage> <judgments.txt>
"""
import json
import re
import sys

from report86_common import R86, STAGES
from report86_eval import parse_judgments
from report86_view import load

DEVICE_LABELS = {'mammary prosthesis', 'metal', 'osteosynthesis material', 'sternotomy', 'suture material', 'pacemaker', 'single chamber device',
                 'ventriculoperitoneal drain tube', 'prosthesis', 'catheter', 'electrode', 'central venous catheter', 'endotracheal tube'}
NEG_DEVICE = re.compile(r"\b(no|not)\b[^.]{0,40}\b(devices?|foreign bod\w*|radiopaque (objects?|markers?|devices?))\b", re.I)

stage, jpath = sys.argv[1], sys.argv[2]
rows, reads, refs = load(stage)
jud = parse_judgments(open(jpath).read(), rows, refs)
out = []
for r in rows:
    img = r['ImageID']
    dev = [x for x in refs[img]['facts'] if x['fact_class'] in ('pos_def', 'pos_hedged', 'pos_temporal', 'pos_ambiguous') and set(x['labels']) & DEVICE_LABELS]
    if not dev:
        continue
    for c in ['M15-R', 'M15-S', 'B0-R', 'B0-S', 'M1-R', 'M1-G', 'C-G', 'C-H']:
        txt = reads[(img, c)]['text']
        has_neg = bool(NEG_DEVICE.search(txt))
        for x in dev:
            st = jud[img][c]['facts'][x['fact_id']]['s']
            if has_neg and st != 'N':
                out.append({'ImageID': img[:8], 'cond': c, 'fact': x['fact_id'], 'sentence': x['sentence_en'], 'status': st, 'neg_device_phrase': NEG_DEVICE.search(txt).group(0)[:80]})
            if (not has_neg) and st == 'N':
                out.append({'ImageID': img[:8], 'cond': c, 'fact': x['fact_id'], 'sentence': x['sentence_en'], 'status': st, 'neg_device_phrase': None, 'note': 'N without neg-device phrase'})
print(json.dumps(out, indent=1, ensure_ascii=False))
print(len(out), 'candidates')
