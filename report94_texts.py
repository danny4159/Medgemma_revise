"""iter_094: epoch1 R/G 출력 문장 분포 확인(읽기 전용 출력)."""
import json
from collections import Counter
from pathlib import Path

R=Path(__file__).resolve().parent/'results'
for m in 'RG':
    rows=[json.loads(l) for l in (R/f'iter_094/gen/{m}_epoch1/worker_0.jsonl').read_text().splitlines()]
    print(m)
    for t,n in Counter(r['text'] for r in rows).most_common():
        print(n,repr(t))
