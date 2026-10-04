"""iter_071 독립 재계산: production parser/matching(rsna_diag.parse, det_match)을 쓰지 않고 원시 record에서 F1을 다시 계산한다.

- 응답 해석: suffix_text_raw에서 <end_of_turn>을 떼고 json.loads 전체 문자열 파싱(엄격). 실패/비 EOS/label 불일치/좌표 이상은 invalid=0.
- matching: IoU>=thr 이진 matrix의 최대 cardinality matching(Kuhn 증가경로; scipy 미설치).
- 대상: 주어진 gen 디렉터리들의 F1@0.5, F1@0.3 환자 평균을 저장 평가(report)와 비교한다.
사용: python g71_verify.py OUT.json KEY gen_dir1 [gen_dir2...]
"""
import json, sys

import numpy as np

import g71_data as D
import g71_eval as E
import g71_train as TR


def iou(a, b):
    ih = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iw = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ih * iw
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def tp_scipy(pred, gt, thr):
    """이진 IoU>=thr 이분 그래프의 최대 cardinality matching (Kuhn 증가경로). det_match의 DP와 독립 구현."""
    if not pred or not gt:
        return 0
    adj = [[pi for pi, p in enumerate(pred) if iou(p, g) >= thr] for g in gt]
    match_p = {}

    def aug(gi, seen):
        for pi in adj[gi]:
            if pi in seen:
                continue
            seen.add(pi)
            if pi not in match_p or aug(match_p[pi], seen):
                match_p[pi] = gi
                return True
        return False
    return sum(1 for gi in range(len(gt)) if aug(gi, set()))


def f1(tp, npred, ngt):
    if npred == 0 and ngt == 0:
        return 1.0
    return 0.0 if tp == 0 else 2 * tp / (npred + ngt)


def strict_boxes(rec, cat):
    if not rec['ended_eos']:
        return None
    t = rec['suffix_text_raw']
    if t.endswith('<end_of_turn>'):
        t = t[:-len('<end_of_turn>')]
    try:
        v = json.loads(t.strip())
    except Exception:
        return None
    if not isinstance(v, list):
        return None
    out = []
    for e in v:
        if not isinstance(e, dict) or e.get('label') != D.LABEL_STR[cat]:
            return None
        b = e.get('box_2d')
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b)):
            return None
        if not (0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000):
            return None
        out.append([float(x) for x in b])
    return out


def verify_dir(gdir, key):
    rows = {r['id']: r for r in TR.load_items(key)}
    recs = E.read_jsonl_dir(gdir)
    byid = {r['id']: r for r in recs}
    assert set(byid) == set(rows) and len(recs) == len(byid), 'record set mismatch'
    per = {'0.5': {}, '0.3': {}}
    n_strict_diff = 0
    for i, row in rows.items():
        b = strict_boxes(byid[i], row['category'])
        gt = [g['yxyx_norm'] for g in row['gt']]
        for thr in (0.5, 0.3):
            v = 0.0 if b is None else f1(tp_scipy(b, gt, thr), len(b), len(gt))
            per[str(thr)].setdefault(row['patient'], []).append(v)
        st, bx = E.parse_record(byid[i], row['category'])
        if (b is None) != (st not in ('valid_nonempty', 'valid_empty')):
            n_strict_diff += 1
    res = {k: {p: float(np.mean(v)) for p, v in d.items()} for k, d in per.items()}
    scored, _ = E.score_vlm(recs, rows, sorted(rows))
    prod = {thr: E.per_patient(scored, sorted(res[thr]), f'f1@{thr}') for thr in ('0.5', '0.3')}
    diff = {thr: max(abs(res[thr][p] - prod[thr][p]) for p in res[thr]) for thr in res}
    return {'dir': gdir, 'n_records': len(recs), 'indep_mean_f1@0.5': float(np.mean(list(res['0.5'].values()))), 'prod_mean_f1@0.5': float(np.mean(list(prod['0.5'].values()))),
            'indep_mean_f1@0.3': float(np.mean(list(res['0.3'].values()))), 'prod_mean_f1@0.3': float(np.mean(list(prod['0.3'].values()))),
            'max_patient_abs_diff': diff, 'n_parser_disagreements': n_strict_diff}


if __name__ == '__main__':
    out, key, dirs = sys.argv[1], sys.argv[2], sys.argv[3:]
    res = [verify_dir(d, key) for d in dirs]
    json.dump(res, open(out, 'w'), indent=1)
    for r in res:
        print(r)
