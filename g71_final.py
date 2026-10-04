"""iter_071 E24 최종 비교 (T24 미진입 분기): D8/R8 VLM, detector M8, train-only template P, 환자 교환 swap. 잠금(e24_lock.json) 검증 후 한 번 평가한다.
결과: results/iter_071/eval/E24_report.json, E24_per_patient.json. 사용: python g71_final.py
"""
import hashlib, json, os, sys

import numpy as np

import g71_analyze as A
import g71_baseline as B
import g71_data as D
import g71_det_stage as DS
import g71_eval as E
import g71_train as TR

OUT = 'results/iter_071/eval'
KEY = 'E24'


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def verify_lock():
    lock = json.load(open('results/iter_071/decide/e24_lock.json'))
    for f, h in lock['code'].items():
        if sha(f) != h:
            sys.exit(f'locked code changed: {f}')
    if sha('results/iter_071/data/manifest.json') != lock['manifest_sha256']:
        sys.exit('manifest changed')
    for v in lock['vlm'].values():
        if sha(v['adapter']) != v['adapter_file_sha256']:
            sys.exit('adapter changed')
    if sha(lock['detector']['ckpt']) != lock['detector']['ckpt_sha256']:
        sys.exit('detector checkpoint changed')
    return lock


def vec(scored, pats, key='f1@0.5'):
    return [E.per_patient(scored, pats, key)[p] for p in pats]


def summ_extra(scored, raw, rows):
    st = [v['status'] for v in scored.values()]
    gt_ne = [i for i in scored if scored[i]['n_gt'] > 0]
    return {'valid_rate': sum(s in ('valid_empty', 'valid_nonempty') for s in st) / len(st), 'status_counts': {k: st.count(k) for k in sorted(set(st))},
            'mean_recall@0.5(nonempty GT)': float(np.nanmean([scored[i]['recall@0.5'] for i in gt_ne])), 'fp_per_image_query@0.5': float(np.mean([scored[i]['fp@0.5'] for i in scored])),
            'mean_pred': float(np.mean([scored[i]['n_pred'] for i in scored])), 'mean_gt': float(np.mean([scored[i]['n_gt'] for i in scored]))}


def main():
    lock = verify_lock()
    os.makedirs(OUT, exist_ok=True)
    rows = {r['id']: r for r in TR.load_items(KEY)}
    ids = sorted(rows)
    pats = sorted({r['patient'] for r in rows.values()}, key=int)
    systems, raws = {}, {}
    for init in ('D', 'R'):
        s = A.score_dir(f'results/iter_071/gen/E24/{init}8', KEY)
        systems[f'{init}8'], raws[f'{init}8'] = s['scored'], s['raw']
        # label을 무시한 보조 점수(형식 오류와 위치 오류 분리): label_mismatch를 label 무시 parse로 재계산하지 않고 상태 계수만 보고
    scored_m, raw_m, _, capped = DS.score_det(json.load(open(f"{lock['detector']['run']}/infer_E24_e{lock['detector']['epoch']}.json")), KEY, lock['detector']['threshold'])
    systems['M8'], raws['M8'] = scored_m, raw_m
    tm = lock['template']
    systems['P'] = B.score_template(tm, rows, ids)
    for k in ('D8', 'R8'):
        sw, donor = B.swap_score(raws[k], rows, pats)
        systems[f'{k}_swap'] = sw
    systems['M8_swap'] = B.swap_score(raws['M8'], rows, pats)[0]
    idx = E.boot_indices(len(pats))
    V = {k: {t: vec(s, pats, t) for t in ('f1@0.5', 'f1@0.3')} for k, s in systems.items()}
    rep = {'n_patients': len(pats), 'n_requests': len(ids), 'bootstrap': 'patient-level, 10000, seed 7101, percentile 95%', 'lock_enter_T24': lock['enter_T24'], 'detector_cap_images': capped,
           'systems': {}, 'paired': {}}
    for k, s in systems.items():
        rep['systems'][k] = {'f1@0.5': E.mean_ci(V[k]['f1@0.5'], idx), 'f1@0.3': E.mean_ci(V[k]['f1@0.3'], idx)}
        if k in raws:
            rep['systems'][k].update(summ_extra(s, raws[k], rows))
        for cat in D.CATS:
            rep['systems'][k][f'f1@0.5_{cat}'] = float(np.mean(list(E.per_patient_cat(s, pats, cat).values())))
    pairs = [('R8', 'D8'), ('R8', 'P'), ('D8', 'P'), ('R8', 'R8_swap'), ('D8', 'D8_swap'), ('M8', 'R8'), ('M8', 'D8'), ('M8', 'P'), ('M8', 'M8_swap')]
    for a, b in pairs:
        rep['paired'][f'{a}-{b}'] = {t: E.paired_ci(V[a][t], V[b][t], idx) for t in ('f1@0.5', 'f1@0.3')}
    # R vs D 형식/위치 분해: 양쪽 모두 valid인 항목만의 평균 위치 점수
    both = [i for i in ids if raws['D8'][i]['status'] in ('valid_empty', 'valid_nonempty') and raws['R8'][i]['status'] in ('valid_empty', 'valid_nonempty')]
    rep['R_vs_D_both_valid'] = {'n_items': len(both), 'D8_f1@0.5': float(np.mean([systems['D8'][i]['f1@0.5'] for i in both])) if both else None,
                                'R8_f1@0.5': float(np.mean([systems['R8'][i]['f1@0.5'] for i in both])) if both else None}
    json.dump(rep, open(f'{OUT}/E24_report.json', 'w'), indent=1)
    json.dump({k: {'patients': pats, **{t: v[t] for t in v}} for k, v in V.items()}, open(f'{OUT}/E24_per_patient.json', 'w'))
    print(json.dumps({k: {t: round(v[t]['mean'], 4) for t in ('f1@0.5', 'f1@0.3')} for k, v in rep['systems'].items()}, indent=1))
    for k, v in rep['paired'].items():
        print(k, {t: {a: round(b, 4) for a, b in x.items()} for t, x in v.items()})


if __name__ == '__main__':
    main()
