"""사후(post hoc) 기술 집계: 원 판정과 별개. 첫 줄은 EOS 무관 집계, 설명문의 low/mixed 언급은 단순 키워드(임상 판정 아님)."""
import re, glob, json
from collections import Counter
from i133_common import RES, read, save, now, sha

man = read(RES / 'data_manifest.json'); lab = {a['pid']: a['report_label'] for a in man['audit']}
rows = []
for f in sorted(glob.glob(str(RES / 'jobs/main/worker*.jsonl'))):
    for l in open(f): rows.append(json.loads(l))
assert len(rows) == 45
pat = re.compile(r'hypointens|low[- ]signal|low signal|mixed|heterogene|dark|necro', re.I)
first = Counter(); kw = {}; nopix = {}
for r in rows:
    pid, c = r['id'].split('__'); fl = r['text'].strip().splitlines()[0].strip()
    first[(c, fl)] += 1
    body = '\n'.join(r['text'].strip().splitlines()[1:])
    k = (c, lab[pid]); d = kw.setdefault(f'{c}|{lab[pid]}', dict(n=0, with_keyword=0, non_eos=0)); d['n'] += 1; d['with_keyword'] += bool(pat.search(body)); d['non_eos'] += (not r['eos'])
    if c == 'M': nopix[pid] = body[:200]
save(RES / 'eval/post_hoc.json', dict(created_at=now(), note='사후 기술 집계. 주판정·parser는 변경하지 않음. 키워드 언급은 임상 판독이 아님.',
     first_line_regardless_of_eos={f'{c}|{fl}': n for (c, fl), n in sorted(first.items())}, keyword_mentions_in_explanation=kw, M_explanation_heads=nopix, source=str(RES / 'jobs/main'), code_sha256=sha(__file__)))
print(dict(first)); print(kw)
for p, t in list(nopix.items())[:3]: print(p, repr(t))
