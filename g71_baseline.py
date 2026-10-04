"""iter_071 단순 대조: train-only category별 bbox template(P)와 환자 교환(swap) 재채점.

P: train 영상(환자·slice) 각각의 정규화 bbox set을 후보로 두고, 후보 i의 선택 점수 = 다른 train 환자의 같은 category 영상 전체에 대한 평균 F1@0.5(자기 환자 제외).
   최대 점수 후보를 선택하고 동률은 (환자 int id, slice offset) 순. 선택된 한 개 set을 모든 평가 slice에 그대로 출력한다.
swap: 평가 환자를 int id 순으로 정렬한 고정 순환 permutation(i -> i+1 mod n)의 donor 출력(같은 category·slice offset)을 해당 환자 GT로 재채점한다. 영상 의존성 진단용.
"""
import numpy as np

import g71_data as D
import g71_eval as E
import g71_train as TR


def train_template(key):
    rows = TR.load_items(key)
    out = {}
    for cat in D.CATS:
        cand = sorted([r for r in rows if r['category'] == cat], key=lambda r: (int(r['patient']), r['offset']))
        best, best_s, scores = None, -1.0, []
        for c in cand:
            cb = [g['yxyx_norm'] for g in c['gt']]
            vals = [E.score_boxes(cb, [g['yxyx_norm'] for g in o['gt']], 0.5)['f1'] for o in cand if o['patient'] != c['patient']]
            s = float(np.mean(vals))
            scores.append(s)
            if s > best_s + 1e-12:
                best, best_s = c, s
        out[cat] = {'source_id': best['id'], 'boxes': [g['yxyx_norm'] for g in best['gt']], 'train_selection_f1@0.5': best_s}
    return out


def score_template(tmpl, rows_by_id, ids):
    return {i: E.score_item('valid_nonempty' if tmpl[rows_by_id[i]['category']]['boxes'] else 'valid_empty', tmpl[rows_by_id[i]['category']]['boxes'],
                            [g['yxyx_norm'] for g in rows_by_id[i]['gt']]) for i in ids}


def swap_score(raw, rows_by_id, patients):
    """raw: {id: {'status','boxes'}} (VLM 또는 detector 출력 후처리). donor 출력을 환자 GT로 재채점."""
    pts = sorted(patients, key=int)
    donor = {p: pts[(k + 1) % len(pts)] for k, p in enumerate(pts)}
    assert all(donor[p] != p for p in pts)
    out = {}
    for p in pts:
        for o in D.OFFSETS:
            for c in D.CATS:
                i, j = D.item_id(p, o, c), D.item_id(donor[p], o, c)
                out[i] = E.score_item(raw[j]['status'], raw[j]['boxes'], [g['yxyx_norm'] for g in rows_by_id[i]['gt']])
    return out, donor
