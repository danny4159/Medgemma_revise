"""iter_095 의미 판정용 출력 묶음: 조건명 제거(무작위화된 O-id), 접두사(Location/Description) 제거, 규칙 기반 초안.

초안은 판정 보조일 뿐이며 최종 판정은 사람이(assistant가) 원문을 읽고 수정한 judgments 파일이다. 조건명 제거는 독립 눈가림이 아니다
(영역 이름은 보이며, 판정자는 이미 E96 일부를 본 assistant다). 전문의 검토가 아니다.
"""
import json
import re
import sys

import report95_common as C
from report95_common import R95, sha_obj, save, read_jsonl_complete, REGIONS

CLAIM_KINDS = [('atelectasis', r'atelecta|collaps'), ('consolidation', r'consolidat|airspace disease|air-space'),
               ('infiltrate', r'infiltrat'), ('opacity', r'opacit|opacif|haziness|hazy|\bopaque\b|increased (pulmonary )?density|increased density'), ('pneumonia', r'pneumonia|pneumonitis')]
NEG_CUE = re.compile(r'\b(no|not|without|free of|absent|absence of|negative for|clear of|resolved)\b|\bnor\b', re.I)
HEDGE = re.compile(r'possible|possibly|may |might|suspicious|cannot be (excluded|ruled out)|concern for|likely|suggest|questionable|probable|could|equivocal', re.I)
TEMPORAL = re.compile(r'\b(new|newly|decreased|in comparison|compared|prior|again|persistent|unchanged|worsen\w*|improv\w*|interval|resolv\w*|progress\w*|stable)\b', re.I)
STRONG = re.compile(r'infiltrat|consolidat|opacit|opacif|condensat|atelecta|airspace|air-space|pneumon|haz|density|clear|edema|congest', re.I)
ZONE = [('U', r'upper|apical|apex'), ('M', r'\bmid\b|middle|perihilar|hilar'), ('L', r'lower|basal|base|bases|costophrenic|retrocardiac')]


def clean(text):
    t = text.strip()
    t = re.sub(r'^Location of the [^:]*:\s*\[[^\]]*\]\.?\s*Description:\s*', '', t)
    t = re.sub(r'^Description of the [^:]*:\s*', '', t)
    return t.strip()


def outputs_for(stage):
    """{ImageID: [{key:(cond,region), text, rec, source}]}  cond in G(C-G), L(old Locate and describe), D(new Describe)."""
    base = C.stage_base(stage)
    old = C.old_C_records(base)
    new = {}
    for s in sorted((R95 / stage_dir(stage)).glob('shard*')):
        for r in read_jsonl_complete(s / 'outputs.jsonl'):
            assert r['id'] not in new
            new[r['id']] = r
    out = {}
    for img in C.stage_patients(stage):
        lst = [{'cond': 'G', 'region': 'G', 'rec': old[(img, 'G')]}]
        for reg in REGIONS:
            lst.append({'cond': 'L', 'region': reg, 'rec': old[(img, reg)]})
            lst.append({'cond': 'D', 'region': reg, 'rec': new[f'{img}|{C.SYSTEM}|D|{reg}']})
        for x in lst:
            x['text'] = clean(x['rec']['text'])
        order = sorted(lst, key=lambda x: sha_obj(['blind95', img, x['cond'], x['region']]))
        for k, x in enumerate(order, 1):
            x['oid'] = f'O{k:02d}'
        out[img] = order
    return out


def stage_dir(stage):
    return {'E32': 'E32/main', 'E64': 'E64/main', 'D8': 'D8/w4'}[stage]


def scope_of(sentence):
    s = sentence.lower()
    if re.search(r'bibasilar|bibasal|both (lung )?bas|bilateral (lung )?bas|lung bases', s):
        return 'RL,LL'
    sides = []
    if re.search(r'bilateral|both|\blungs\b', s):
        sides = ['R', 'L']
    else:
        if re.search(r'\bright\b', s):
            sides.append('R')
        if re.search(r'\bleft\b', s):
            sides.append('L')
    zones = [z for z, pat in ZONE if re.search(pat, s)]
    if not sides and not zones:
        return 'q'
    if not sides:
        sides = ['R', 'L']
    if not zones:
        return ','.join(sides) if len(sides) == 1 else 'B'
    return ','.join(sd + z for sd in sides for z in zones)


def draft_claims(text):
    claims = []
    for sent in re.split(r'(?<=[.;])\s+', text):
        if not sent.strip():
            continue
        neg = bool(NEG_CUE.search(sent))
        kinds = [k for k, pat in CLAIM_KINDS if re.search(pat, sent, re.I)]
        if re.search(r'lungs? (is|are) clear|clear lungs?|lungs? (is|are) (grossly )?clear', sent, re.I) and not kinds:
            claims.append(('N', 'clear', scope_of(sent), '-', sent.strip()))
        if len(kinds) > 1 and 'pneumonia' in kinds:
            kinds.remove('pneumonia')  # 진단 표현은 같은 문장의 소견 종류가 있으면 별도 주장으로 세지 않는다
        if 'opacity' in kinds and re.search(r'(represent|concern\w* for|consistent with|suggest\w*|reflect\w*)[^.]*(atelecta|consolidat|infiltrat)', sent, re.I):
            kinds = [k for k in kinds if k not in ('atelectasis', 'consolidation', 'infiltrate')]  # 감별 진단 표현은 별도 주장이 아님
        for k in kinds:
            if neg:
                claims.append(('N', k, scope_of(sent), '-', sent.strip()))
            else:
                pol = 'Pu' if HEDGE.search(sent) else 'P'
                fl = ''.join(['t' if TEMPORAL.search(sent) else '', 'c' if re.search(r'infect|inflam|pneumon|metapneum|aspirat|granuloma', sent, re.I) else '',
                              'b' if re.search(r'lobe|lingula', sent, re.I) else ''])
                claims.append((pol, k, scope_of(sent), fl or '-', sent.strip()))
    seen, out = set(), []
    for c in claims:  # 같은 문장이 반복된 번호 목록은 한 번만 센다(극성·종류·범위·문장 정규화)
        key = (c[0], c[1], c[2], re.sub(r'^\d+\.\s*', '', c[4]).lower().rstrip('.'))
        key2 = (c[0], c[1], c[2])
        if key2 in seen:
            continue
        seen.add(key2)
        out.append(c)
    return out


def main():
    cmd, stage = sys.argv[1], sys.argv[2]
    outs = outputs_for(stage)
    if cmd == 'key':
        save(R95 / f'judging/blind_key_private_{stage}.json',
             {img: {x['oid']: [x['cond'], x['region'], x['rec']['id']] for x in lst} for img, lst in outs.items()})
    elif cmd == 'draft':
        lines = []
        for pi, (img, lst) in enumerate(outs.items()):
            lines.append(f'## P{pi:03d}')
            for x in sorted(lst, key=lambda x: x['oid']):
                cl = draft_claims(x['text'])
                if not cl:
                    lines.append(f"{x['oid']} | -")
                for pol, k, sc, fl, q in cl:
                    lines.append(f"{x['oid']} | {pol} | {k} | {sc} | {fl} | \"{q}\"")
        p = R95 / f'judging/draft_{stage}_v5.txt'
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('x') as f:
            f.write('\n'.join(lines) + '\n')
        print(p, len(lines))
    elif cmd == 'show':
        lo, hi = int(sys.argv[3]), int(sys.argv[4])
        keys = list(outs)
        for pi in range(lo, hi):
            img = keys[pi]
            print(f'## P{pi:03d}')
            for x in sorted(outs[img], key=lambda x: x['oid']):
                where = 'FULL' if x['region'] == 'G' else x['region']
                print(f"{x['oid']} [{where}] {x['text']}")


if __name__ == '__main__':
    main()
