"""전체 인계 검사 및 재점검용 원문/판정 표시. 점수는 의미 판정 완료 후 계산한다."""
import contextlib
import hashlib
import io
import json
import re
import sys

import report87_eval as E
import report87_view as V
from report86_common import ROOT, sha
from report86_view import blind_order
from report88_handoff import OLD, OUT, inputs, write_new


def part_paths():
    return sorted((OLD / 'judgments_parts').glob('*.txt')) + sorted(OUT.glob('part_P*.txt'))


def load_all():
    rows, reads, amend, v1 = inputs()
    paths = part_paths()
    text = '\n'.join(p.read_text() for p in paths)
    jud = E.parse_v3(text, rows, amend, reads, v1)
    return rows, reads, amend, v1, jud


def provenance_checks(jud, reads):
    """parser 밖 필수 span·중복 연결 검사. 오류를 묵인하지 않는다."""
    errs, linked = [], {}
    for img, cs in jud.items():
        for cond, o in cs.items():
            rec = reads[img, cond]
            spans = [x['text'] for x in rec['segments']] if cond == 'C-H' else [rec['text']]
            for fid, f in o['facts'].items():
                if f['co'] and (not f['co']['span'] or not any(f['co']['span'] in t for t in spans)):
                    errs.append([img, cond, fid, 'co anchor 누락/불일치'])
            seen = set()
            ids = []
            for k, c in enumerate(o['claims']):
                key = (c['anchor'], c['at'])
                if key in seen:
                    errs.append([img, cond, k, '동일 anchor 중복 주장'])
                seen.add(key)
                ids.append({'claim_id': f'C{k+1:03}', **c})
            pairs = []
            for k, it in enumerate(o['internal']):
                parts = []
                for p in it['parts']:
                    matched = []
                    for c in ids:
                        csources = {x['source'] for x in c['occ']}
                        psources = {x['source'] for x in p['occ']}
                        if not psources.intersection(csources):
                            continue
                        # 짧은 모순 anchor와 전체 주장 anchor의 양방향 포함 대조
                        if any(a in p['anchor'] or p['anchor'] in a for a in c['anchor'].split('||')):
                            matched.append(c['claim_id'])
                    parts.append({**p, 'claim_ids': matched})
                pairs.append({**it, 'parts': parts})
            linked[img + '|' + cond] = {'claims': ids, 'internal': pairs}
    return errs, linked


def main():
    rows, reads, amend, v1, jud = load_all()
    if sys.argv[1] == 'check':
        errs, linked = provenance_checks(jud, reads)
        unlinked = [(k, n, j) for k, v in linked.items() for n, it in enumerate(v['internal']) for j, p in enumerate(it['parts']) if not p['claim_ids']]
        result = {'n_patients': len(jud), 'n_outputs': sum(map(len, jud.values())), 'errors': errs,
                  'internal_unlinked': unlinked, 'parts': {str(p.relative_to(ROOT)): sha(p) for p in part_paths()},
                  'meaning_validated': False, 'linked': linked}
        write_new(OUT / sys.argv[2], result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('parts', 'linked')}, ensure_ascii=False))
        return
    for idx in map(int, sys.argv[1].split(',')):
        V.main(idx, idx + 1)
        img = rows[idx]['ImageID']
        print('--- 현재 판정 요약 (점수 없음) ---')
        for k, c in enumerate(blind_order(img), 1):
            o = jud[img][c]
            print('O' + str(k), 'facts', {f: (x['s'], x['loc'], x['attr'], x['co']) for f,x in o['facts'].items()})
            print('  S/C', [(x['cls'], x['refs'], x['pol']+x['cert'], x['anchor'], x['at']) for x in o['claims'] if x['cls'] != 'U'])
            print('  internal', [(x['strength'], [(p['anchor'],p['at']) for p in x['parts']]) for x in o['internal']])


if __name__ == '__main__':
    main()
