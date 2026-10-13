"""사후(post-hoc) 기술 집계 — 주판정과 별개. 첫 줄 상태와 무관하게 설명문 키워드(i134_spec.NEG/POS)로 '병변 없음 취지'/'병변 있음 취지'를 센다.
의미 평가기가 아니며 원 답·주판정을 바꾸지 않는다. 결과: results/iter_134/eval_posthoc_content.json"""
import json
from collections import Counter
import i134_run as R
from i134_common import RES, save, now
from i134_spec import NEG, POS, parse, CONDS

rec = R.verify_job(RES / 'jobs/main', 'main'); out = {}
for c in CONDS:
    rows = [r for r in rec if r['id'].endswith('__' + c)]; cnt = Counter()
    for r in rows:
        body = ' '.join(r['text'].strip().splitlines()[1:]) if parse(r['text'], r['eos']) else r['text']
        neg = bool(NEG.search(body)); pos = bool(POS.search(NEG.sub(' ', body)))
        cnt['says_no_lesion' if neg and not pos else 'says_lesion' if pos and not neg else 'mixed' if neg and pos else 'neither'] += 1
        cnt['first_line_PRESENT'] += parse(r['text'], r['eos']) == 'PRESENT'
    out[c] = dict(n=len(rows), **cnt)
save(RES / 'eval_posthoc_content.json', dict(created_at=now(), note='post-hoc keyword tally, not a validated semantic evaluator; main decision unchanged', per_condition=out))
print(json.dumps(out))
