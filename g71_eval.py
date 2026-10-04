"""iter_071 평가 라이브러리: 엄격 parser(rsna_diag.parse) + category/label 검사 + 최대 cardinality matching F1 + 환자 bootstrap.

- invalid(형식 실패·잘못된 label)는 점수 0, 누락 record는 예외(모델 오답으로 바꾸지 않음).
- GT와 예측이 모두 빈 slice-category는 1. GT가 비었는데 예측이 있거나 반대면 0 (F1 정의).
- matching: IoU>=thr 쌍의 최대 cardinality one-to-one (rsna_diag.det_match.bounded_match, GT<=16). F1은 TP 수만으로 정해지므로 동률 규약은 점수에 영향이 없다.
  독립 검증은 scipy linear_sum_assignment로 TP를 재계산한다(g71_verify.py).
- 주지표: (slice,category) 6개 동일 가중 평균 -> 환자 평균. bootstrap은 환자 단위 10,000회 seed 7101.
"""
import json
import math

import numpy as np

import g71_data as D
from rsna_diag import det_match, metrics as M, parse as PA

MAX_GT = 16


def f1_from(tp, npred, ngt):
    if npred == 0 and ngt == 0:
        return 1.0
    p = tp / npred if npred else 0.0
    r = tp / ngt if ngt else 0.0
    return 2 * p * r / (p + r) if p + r > 0 else 0.0


def score_boxes(pred, gt, thr):
    """pred/gt: [[y0,x0,y1,x1],...] -> dict(tp, n_pred, n_gt, f1, recall, fp)."""
    pairs = det_match.bounded_match(pred, gt, thr, max_gt=MAX_GT)
    tp = len(pairs)
    return {'tp': tp, 'n_pred': len(pred), 'n_gt': len(gt), 'f1': f1_from(tp, len(pred), len(gt)),
            'recall': (tp / len(gt)) if gt else float('nan'), 'fp': len(pred) - tp}


def parse_record(rec, cat):
    """VLM record -> (status, boxes). label이 요청 category와 다르면 'label_mismatch'."""
    p = PA.parse_response(rec['suffix_text_raw'], rec['ended_eos'])
    st = p['status']
    if st in PA.VALID and p['boxes']:
        if any(l != D.LABEL_STR[cat] for l in p['labels']):
            return 'label_mismatch', []
    return st, [[float(v) for v in b] for b in p['boxes']] if st in PA.VALID else []


def score_item(status, boxes, gt_boxes):
    valid = status in PA.VALID
    out = {'status': status, 'n_gt': len(gt_boxes)}
    for thr in (0.5, 0.3):
        if valid:
            s = score_boxes(boxes, gt_boxes, thr)
        else:
            s = {'tp': 0, 'n_pred': 0, 'n_gt': len(gt_boxes), 'f1': 0.0, 'recall': 0.0 if gt_boxes else float('nan'), 'fp': 0}
        out[f'f1@{thr}'] = s['f1']
        out[f'recall@{thr}'] = s['recall']
        out[f'tp@{thr}'] = s['tp']
        out[f'fp@{thr}'] = s['fp']
    out['n_pred'] = len(boxes) if valid else 0
    return out


def gt_index(manifest_rows):
    return {r['id']: r for r in manifest_rows}


def per_patient(scored, patients, key='f1@0.5'):
    """scored: {item_id: score dict}. 환자별 6개 동일 가중 평균."""
    out = {}
    for p in patients:
        vals = [scored[D.item_id(p, o, c)][key] for o in D.OFFSETS for c in D.CATS]
        out[p] = float(np.mean(vals))
    return out


def per_patient_cat(scored, patients, cat, key='f1@0.5'):
    return {p: float(np.mean([scored[D.item_id(p, o, cat)][key] for o in D.OFFSETS])) for p in patients}


def boot_indices(n, B=10000, seed=7101):
    return np.random.default_rng(seed).integers(0, n, size=(B, n), dtype=np.int32)


def paired_ci(a, b, idx):
    d = np.asarray(a, float) - np.asarray(b, float)
    m = d[idx].mean(axis=1)
    return {'mean': float(d.mean()), 'lo': float(np.percentile(m, 2.5)), 'hi': float(np.percentile(m, 97.5)), 'n': int(len(d))}


def mean_ci(a, idx):
    a = np.asarray(a, float)
    m = a[idx].mean(axis=1)
    return {'mean': float(a.mean()), 'lo': float(np.percentile(m, 2.5)), 'hi': float(np.percentile(m, 97.5)), 'n': int(len(a))}


def read_jsonl_dir(d):
    import glob
    recs = []
    for f in sorted(glob.glob(f'{d}/gen_worker*.jsonl')):
        for ln in open(f):
            if ln.strip():
                recs.append(json.loads(ln))
    return recs


def score_vlm(recs, rows_by_id, expected_ids):
    """record 목록 -> {id: score}. 누락·중복·잉여는 예외."""
    by = {}
    for r in recs:
        if r['id'] in by:
            raise RuntimeError(f"duplicate record {r['id']}")
        by[r['id']] = r
    miss, extra = set(expected_ids) - set(by), set(by) - set(expected_ids)
    if miss or extra:
        raise RuntimeError(f'incomplete request set: missing {len(miss)} extra {len(extra)}')
    out, raw = {}, {}
    for i in expected_ids:
        row = rows_by_id[i]
        st, boxes = parse_record(by[i], row['category'])
        out[i] = score_item(st, boxes, [g['yxyx_norm'] for g in row['gt']])
        raw[i] = {'status': st, 'boxes': boxes}
    return out, raw
