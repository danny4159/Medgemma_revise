"""detector 추론(V8/E24)·threshold 선택·extension 판정·점수화. 사용:
  python g71_det_stage.py infer RUN_DIR KEY EPOCHS      (예: infer results/iter_071/det/T8_lr0.005 V8 8,16,24,32)
  python g71_det_stage.py select TRAIN_KEY RUN_DIR[,RUN_DIR2] EPOCHS    (V8 macro F1@0.5 최대 threshold/checkpoint 선택)
"""
import json, os, sys

import numpy as np

import g71_data as D
import g71_eval as E
import g71_train as TR
from rsna_diag import geometry as G

THRS = [0.01, 0.05] + [round(0.10 + 0.05 * i, 2) for i in range(19)] + [0.99]  # 0.01, 0.05, 0.10..1.00 grid (1.00 제외 아래서 처리)
THRS = [t for t in THRS if t < 1.0] + [0.99]  # plan grid {0.01,0.05,0.10,...,0.95,0.99}


def preds_to_items(pred_json, key, thr, cap=100):
    """원시 detector 후보 -> {item_id: (status, norm boxes)}. category label 1=vertebra 2=disc, score>=thr."""
    P = pred_json['preds']
    out, capped = {}, 0
    for r in TR.load_items(key):
        pr = P[f"{r['patient']}_{D.OFF_NAME[r['offset']]}"]
        h, w = pr['img_hw']
        top, left, side = G.pad_offsets(h, w)
        lab = 1 if r['category'] == 'vertebra' else 2
        boxes = [G.canvas_to_norm(b, top, left, side) for b, s, l in zip(pr['boxes_xyxy_px'], pr['scores'], pr['labels']) if l == lab and s >= thr]
        if len(pr['scores']) >= cap:
            capped += 1
        out[r['id']] = ('valid_nonempty' if boxes else 'valid_empty', boxes)
    return out, capped


def score_det(pred_json, key, thr):
    rows = {r['id']: r for r in TR.load_items(key)}
    items, capped = preds_to_items(pred_json, key, thr)
    scored = {i: E.score_item(st, bx, [g['yxyx_norm'] for g in rows[i]['gt']]) for i, (st, bx) in items.items()}
    raw = {i: {'status': st, 'boxes': bx} for i, (st, bx) in items.items()}
    pats = sorted({r['patient'] for r in rows.values()}, key=int)
    return scored, raw, pats, capped


def select(train_key, runs, epochs):
    res = {}
    for run in runs:
        for e in epochs:
            p = f'{run}/infer_V8_e{e}.json'
            if not os.path.exists(p):
                continue
            pj = json.load(open(p))
            for thr in THRS:
                scored, _, pats, capped = score_det(pj, 'V8', thr)
                f5 = float(np.mean(list(E.per_patient(scored, pats, 'f1@0.5').values())))
                f3 = float(np.mean(list(E.per_patient(scored, pats, 'f1@0.3').values())))
                res[f'{run}|{e}|{thr}'] = {'run': run, 'epoch': e, 'thr': thr, 'f1@0.5': f5, 'f1@0.3': f3, 'n_capped_images': capped}
    return res


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'infer':
        import g71_det as X
        run, key, eps = sys.argv[2], sys.argv[3], [int(x) for x in sys.argv[4].split(',')]
        for e in eps:
            out = f'{run}/infer_{key}_e{e}.json'
            if os.path.exists(out):
                continue
            X.infer(f'{run}/epoch_{e:02d}/model.pt', key, out)
            print('wrote', out, flush=True)
    elif cmd == 'select':
        tk, runs, eps = sys.argv[2], sys.argv[3].split(','), [int(x) for x in sys.argv[4].split(',')]
        r = select(tk, runs, eps)
        os.makedirs('results/iter_071/decide', exist_ok=True)
        json.dump(r, open(f'results/iter_071/decide/det_select_{tk}.json', 'w'), indent=1)
        best_by_run_epoch = {}
        for k, v in r.items():
            kk = (v['run'], v['epoch'])
            if kk not in best_by_run_epoch or v['f1@0.5'] > best_by_run_epoch[kk]['f1@0.5'] + 1e-12 or (abs(v['f1@0.5'] - best_by_run_epoch[kk]['f1@0.5']) <= 1e-12 and v['thr'] > best_by_run_epoch[kk]['thr']):
                best_by_run_epoch[kk] = v
        for kk, v in sorted(best_by_run_epoch.items()):
            print(kk, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items() if a not in ('run', 'epoch')})
