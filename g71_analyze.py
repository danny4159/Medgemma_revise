"""iter_071 단계별 분석: V4 학습 추세 -> 연장 판정 -> V8 checkpoint 선택 -> T24 진입 판정 -> E24 최종 비교.
사전 규칙은 plan.md(iter_071)를 그대로 구현한다. 사후 규칙 변경 없음. 결과는 results/iter_071/decide/*.json.
사용: python g71_analyze.py v4 [epoch 목록]   |   v8 ...   |   (이후 단계는 이 파일에 추가)
"""
import glob, json, os, sys

import numpy as np

import g71_data as D
import g71_eval as E
import g71_train as TR

OUT = 'results/iter_071/decide'
V4_EPOCHS = (4, 8, 16)


def score_dir(gdir, key):
    rows = {r['id']: r for r in TR.load_items(key)}
    recs = E.read_jsonl_dir(gdir)
    scored, raw = E.score_vlm(recs, rows, sorted(rows))
    pats = sorted({r['patient'] for r in rows.values()}, key=int)
    return {'scored': scored, 'raw': raw, 'patients': pats, 'rows': rows, 'recs': recs}


def summarize(s):
    st = [v['status'] for v in s['scored'].values()]
    valid = sum(x in ('valid_empty', 'valid_nonempty') for x in st)
    f5 = E.per_patient(s['scored'], s['patients'], 'f1@0.5')
    f3 = E.per_patient(s['scored'], s['patients'], 'f1@0.3')
    return {'f1@0.5': float(np.mean(list(f5.values()))), 'f1@0.3': float(np.mean(list(f3.values()))), 'valid_rate': valid / len(st), 'n': len(st),
            'status_counts': {k: st.count(k) for k in sorted(set(st))}, 'n_truncated': sum(1 for r in s['recs'] if not r['ended_eos']),
            'mean_pred_boxes': float(np.mean([v['n_pred'] for v in s['scored'].values()])), 'mean_gt_boxes': float(np.mean([v['n_gt'] for v in s['scored'].values()]))}


def val_ce(traj, e):
    p = f'results/iter_071/train/{traj}/epoch_{e:02d}/val_ce.json'
    return json.load(open(p))['val_ce']


def v4_stage(trajs, epochs=V4_EPOCHS):
    res = {}
    for t in trajs:
        res[t] = {}
        for e in epochs:
            d = f'results/iter_071/gen/V4/{t}_e{e}'
            if not os.path.exists(d) or len(E.read_jsonl_dir(d)) < 24:
                res[t][e] = {'incomplete': True, 'n_records': len(E.read_jsonl_dir(d)) if os.path.exists(d) else 0}
                continue
            s = summarize(score_dir(d, 'V4'))
            s['val_ce'] = val_ce(t, e)
            res[t][e] = s
    return res


def extension_rule(res, epochs=(8, 16)):
    """같은 LR의 D/R 중 하나라도 e8->e16 V4 F1@0.5가 +0.02 이상, 또는 val CE가 5% 이상 줄면서 F1 하락이 0.03 이내이면 해당 LR 두 trajectory를 연장."""
    out = {}
    for lr in ('2e-4', '2e-5'):
        why = {}
        for init in ('D', 'R'):
            t = f'T8_{init}_lr{lr}'
            a, b = res[t][epochs[0]], res[t][epochs[1]]
            dF = b['f1@0.5'] - a['f1@0.5']
            ce_drop = (a['val_ce'] - b['val_ce']) / a['val_ce']
            why[init] = {'dF1@0.5_e8_to_e16': dF, 'val_ce_rel_drop': ce_drop, 'cond_f1_up': dF >= 0.02, 'cond_ce': bool(ce_drop >= 0.05 and dF >= -0.03)}
        out[lr] = {'detail': why, 'extend': any(v['cond_f1_up'] or v['cond_ce'] for v in why.values())}
    return out



def best_v4(res, traj):
    """trajectory의 V4 최고 F1@0.5 epoch(동률은 이른 epoch)과 마지막 epoch."""
    ok = {e: v for e, v in res[traj].items() if not v.get('incomplete')}
    best = max(sorted(ok), key=lambda e: (round(ok[e]['f1@0.5'], 12), -e))
    return best, max(ok)


def v8_scores(root='results/iter_071/gen/V8'):
    out = {}
    for d in sorted(glob.glob(f'{root}/*')):
        if len(E.read_jsonl_dir(d)) < 48:
            continue
        s = score_dir(d, 'V8')
        out[os.path.basename(d)] = summarize(s)
    return out


def swap_and_template(gdir, key, train_key):
    import g71_baseline as B
    s = score_dir(gdir, key)
    sw, donor = B.swap_score(s['raw'], s['rows'], s['patients'])
    tm = B.train_template(train_key)
    ts = B.score_template(tm, s['rows'], sorted(s['rows']))
    f = lambda sc, k='f1@0.5': float(np.mean(list(E.per_patient(sc, s['patients'], k).values())))
    return {'actual': f(s['scored']), 'swap': f(sw), 'template': f(ts), 'actual@0.3': f(s['scored'], 'f1@0.3'), 'swap@0.3': f(sw, 'f1@0.3'), 'template@0.3': f(ts, 'f1@0.3'),
            'template_sources': {c: v['source_id'] for c, v in tm.items()}}


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[1] == 'v4':
        trajs = [f'T8_{i}_lr{l}' for l in ('2e-4', '2e-5') for i in ('D', 'R')]
        res = v4_stage(trajs)
        json.dump(res, open(f'{OUT}/v4_stage.json', 'w'), indent=1)
        for t, d in res.items():
            for e, s in d.items():
                if s.get('incomplete'):
                    print(t, e, s)
                    continue
                print(t, e, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items() if k != 'status_counts'}, s['status_counts'])
        ext = extension_rule(res)
        json.dump(ext, open(f'{OUT}/extension_decision.json', 'w'), indent=1)
        print(json.dumps(ext, indent=1))
    if sys.argv[1] == 'v8':
        r = v8_scores()
        json.dump(r, open(f'{OUT}/v8_scores.json', 'w'), indent=1)
        for k, v in r.items():
            print(k, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items()})
    if sys.argv[1] == 'v8x':  # v8x GEN_DIR TRAIN_KEY: swap/template 비교
        print(json.dumps(swap_and_template(sys.argv[2], 'V8', sys.argv[3]), indent=1))
    if sys.argv[1] == 'gate':
        r = v8_scores()
        sel = {}
        for init in ('D', 'R'):
            cands = []
            for name, v in r.items():
                parts = name.split('_')  # T8 D lr2e-4 e4
                if parts[1] != init:
                    continue
                lr, ep = float(parts[2][2:]), int(parts[3][1:])
                cands.append((-round(v['f1@0.5'], 12), -round(v['f1@0.3'], 12), ep, lr, name))
            cands.sort()
            sel[init] = cands[0][4]
        out = {'selected': sel, 'candidates': {k: {'f1@0.5': v['f1@0.5'], 'f1@0.3': v['f1@0.3']} for k, v in r.items()}}
        gate = {}
        for init, name in sel.items():
            x = swap_and_template(f'results/iter_071/gen/V8/{name}', 'V8', 'T8')
            gate[init] = dict(x, name=name, cond_template=(x['actual'] - x['template'] >= 0.05), cond_swap=(x['actual'] - x['swap'] >= 0.05))
            gate[init]['pass'] = bool(gate[init]['cond_template'] and gate[init]['cond_swap'])
        out['gate'] = gate
        out['enter_T24'] = any(g['pass'] for g in gate.values())
        json.dump(out, open(f'{OUT}/t24_gate.json', 'w'), indent=1)
        print(json.dumps(out, indent=1))
