"""의미 평가용 눈가림 view 생성(읽기 전용 CPU). 모델명을 숨긴 출력 ID(O1..O8)와 reference 사실 ID(F#)를 보여 준다.
python report86_view.py <stage> <start> <end>        # 환자 index 범위를 stdout으로 출력
python report86_view.py <stage> key                   # blind key(private)를 새 파일로 저장
눈가림은 불완전하다: CURE 영역 출력·MedGemma 1 문체는 형식으로 식별될 수 있다(규약에 명시).
"""
import hashlib
import json
import re
import sys

from report86_common import R86, STAGES, R85, save
import report86_facts as F

BBOX = re.compile(r"\s*\[\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*\]")
CONDS = ['M15-R', 'M15-S', 'B0-R', 'B0-S', 'M1-R', 'M1-G', 'C-G', 'C-H']


def blind_order(img):
    return sorted(CONDS, key=lambda c: hashlib.sha256(f'blind86|{img}|{c}'.encode()).hexdigest())


def load(stage):
    rows = json.loads(STAGES[stage]['inputs'].read_text())
    reads = {}
    for ln in (R86 / stage / 'readings.jsonl').read_text().splitlines():
        r = json.loads(ln)
        reads[(r['ImageID'], r['condition'])] = r
    if stage == 'D8':
        refs = {r['ImageID']: {'facts': F.facts_for(r)} for r in json.loads((R85 / 'D8/reference_private.json').read_text())}
    else:
        refs = json.loads((R86 / 'E/reference_facts_E_private.json').read_text())
    return rows, reads, refs


def collapse_repeats(t):
    """4096-token 반복 루프 같은 퇴행 출력은 중복 문장을 (xN)으로 접어 보여 준다(원문은 readings.jsonl에 그대로 있음)."""
    sents = re.split(r'(?<=[.!?])\s+', t)
    if len(t) < 1500 or len(set(sents)) > 0.5 * len(sents):
        return t
    seen, order = {}, []
    for x in sents:
        if x not in seen:
            order.append(x)
        seen[x] = seen.get(x, 0) + 1
    return ' '.join(f"{x} (x{seen[x]})" if seen[x] > 1 else x for x in order) + f"\n[view: degenerate repetition collapsed; original {len(t)} chars, {len(sents)} sentences, {len(order)} distinct]"


def clean(t):
    t = BBOX.sub('', t)
    t = re.sub(r'[ \t]+\n', '\n', t).strip()
    return collapse_repeats(t)


def render_ch(segs):
    seen, out = {}, []
    for s in segs:
        src = s['source'].split('|')[1]
        t = clean(s['text'])
        t = re.sub(r'^Location of the [^:]*:\s*\.?\s*', '', t)
        t = re.sub(r'^Description:\s*', '', t)
        t = t.replace('Description:', '').strip()
        if src == 'G':
            out.append(('GRG', t))
            continue
        seen.setdefault(t, []).append(src)
    lines = [f"[{', '.join(v)}] {k}" for k, v in seen.items()]
    return '\n'.join(lines) + '\nGRG-part: ' + [t for k, t in out][0]


def show(stage, a, b, idx=None):
    rows, reads, refs = load(stage)
    for pi, row in ([(i, rows[i]) for i in idx] if idx else enumerate(rows[a:b], a)):
        img = row['ImageID']
        print(f"==== P{pi:03d} {img[:8]} stratum={row.get('stratum', 'D8')} ====")
        for x in refs[img]['facts']:
            if x['fact_class'] in ('generic_normal', 'neg_scoped', 'excluded'):
                continue
            loc = ','.join(x['locations'])
            print(f"  {x['fact_id']} [{x['fact_class']}] {x['sentence_en']}  (labels={','.join(x['labels'])}; loc={loc})")
        gen = [x for x in refs[img]['facts'] if x['fact_class'] in ('generic_normal',)]
        if gen:
            print('  (generic normal statements present: ' + ' / '.join(x['sentence_en'] for x in gen) + ')')
        for i, c in enumerate(blind_order(img), 1):
            r = reads[(img, c)]
            body = render_ch(r['segments']) if c == 'C-H' else clean(r['text'])
            print(f"--- O{i} ---\n{body}")


def key(stage):
    rows, reads, refs = load(stage)
    k = {row['ImageID']: {f'O{i}': c for i, c in enumerate(blind_order(row['ImageID']), 1)} for row in rows}
    save(R86 / stage / 'blind_key_private.json', k)
    print('saved', len(k))


if __name__ == '__main__':
    st = sys.argv[1]
    if sys.argv[2] == 'key':
        key(st)
    elif ',' in sys.argv[2]:
        show(st, 0, 0, [int(x) for x in sys.argv[2].split(',')])
    else:
        show(st, int(sys.argv[2]), int(sys.argv[3]))
