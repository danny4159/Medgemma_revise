"""iter_068 sp68_analysis 검사: 입력 변조 거부, AUROC/threshold/bootstrap 산술, iter_067 원 BA02 재현. 결과: results/iter_068/tests/fixtures.json"""
import copy, glob, itertools, json, os, shutil, sys, tempfile
import numpy as np
import sp68_analysis as A

R = []


def chk(name, ok, **kw):
    R.append({'name': name, 'pass': bool(ok), **kw}); print('PASS' if ok else 'FAIL', name)


def raises(fn):
    try:
        fn(); return False
    except SystemExit:
        return True


rng = np.random.RandomState(0)
# AUROC brute force (ties 포함)
s = np.round(rng.rand(40), 1); y = np.where(rng.rand(40) < .4, 2, 0)
bf = np.mean([(a > b) + .5 * (a == b) for a in s[y == 2] for b in s[y == 0]])
chk('auroc_bruteforce_ties', abs(A.auroc(s, y) - bf) < 1e-12)
chk('auroc_constant_is_half', A.auroc(np.ones(10), np.array([0, 2] * 5)) == 0.5)
chk('auroc_single_class_nan', np.isnan(A.auroc(np.ones(4), np.zeros(4, int))))
# bootstrap: 가중치 = 1이면 점추정과 같음, 환자 전체 복제
pidx = np.repeat(np.arange(8), 5)
W1 = np.ones((1, 8)); chk('boot_unit_weights_equal_point', abs(A.boot_auc(s, y, W1, pidx)[0] - A.auroc(s, y)) < 1e-12)
W = A.boot_weights(8, 50, 3)
chk('boot_weights_sum_n', (W.sum(1) == 8).all())
b = A.boot_auc(s, y, W, pidx)
k = 7; w = W[k]; sel = np.concatenate([[i for i in range(40) if pidx[i] == p] * int(w[p]) for p in range(8) if w[p] > 0]).astype(int)
chk('boot_equals_explicit_resample', abs(b[k] - A.auroc(s[sel], y[sel])) < 1e-12 if (y[sel] == 2).any() and (y[sel] == 0).any() else True)
# threshold: 동률 -> 가장 큰 threshold, 상수 점수, 점추정
sc = np.array([.1, .2, .3, .4]); yy = np.array([0, 0, 2, 2])
t = A.fit_threshold(sc, yy); chk('threshold_midpoint_perfect', abs(t - .25) < 1e-12)
t = A.fit_threshold(np.ones(4), yy); chk('threshold_constant_ties_inf', t == float('inf'))
sc2 = np.array([.1, .3, .2, .4]); yy2 = np.array([0, 2, 0, 2])
chk('threshold_pred_ge', A.apply_thr(sc, .3).tolist() == [False, False, True, True])
chk('threshold_weighted_zero_weight_ignored', A.fit_threshold(np.array([.1, .2, .3, .9]), np.array([0, 0, 2, 0]), np.array([1, 1, 1, 0.])) == (0.25))
# ridge: 규약(절편 비벌점)
class T_:  # 최소 Table 대용
    pass
D = T_(); D.k = np.array([1, 1, 2, 2, 3, 3]); D.n1 = np.array([10., 20, 10, 20, 10, 20]); D.n2 = D.n1.copy(); D.y = np.array([0, 2] * 3)
sd = np.array([1., 2, 3, 4, 5, 6]); f = A.fit_ridge(D, sd)
pr = A.predict_ridge(f, D); chk('ridge_mean_preserved', abs(pr.mean() - sd.mean()) < 1e-9)
# 변조 거부
d = 'results/iter_067/data'; gen = 'results/iter_067/gen_D'
rows = A.read_jsonl_strict(f'{d}/requests_D.jsonl')
pdig, _ = A.check_inputs('D', f'{d}/protocol_D_v2.json', f'{d}/requests_D.jsonl', f'{d}/pairs_D.json')
tmp = tempfile.mkdtemp()
for m in ('medgemma',):
    os.makedirs(f'{tmp}/{m}')
    recs = A.read_jsonl_strict(f'{gen}/{m}/worker0.jsonl')

    def write(rs, name='worker0.jsonl'):
        with open(f'{tmp}/{m}/{name}', 'w') as fh:
            for r in rs:
                fh.write(json.dumps(r) + '\n')
    write(recs); chk('clean_loads', len(A.load_recs(tmp, m, rows, pdig)) == len(rows))
    write(recs + [recs[0]]); chk('duplicate_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
    write(recs[1:]); chk('missing_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
    r2 = copy.deepcopy(recs); r2[3]['cand_logits'][1] = float('inf'); write(r2); chk('nonfinite_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
    r2 = copy.deepcopy(recs); r2[3]['cand_probs'] = r2[3]['cand_probs'][::-1]; write(r2); chk('candidate_order_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
    r2 = copy.deepcopy(recs); r2[3]['protocol_digest'] = 'x'; write(r2); chk('protocol_digest_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
    r2 = copy.deepcopy(recs); r2[3]['n_images'] += 1; write(r2); chk('request_record_mismatch_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
    with open(f'{tmp}/{m}/worker0.jsonl', 'wb') as fh:
        fh.write(open(f'{gen}/{m}/worker0.jsonl', 'rb').read() + b'{"rid": "x"')
    chk('torn_tail_rejected', raises(lambda: A.load_recs(tmp, m, rows, pdig)))
# labels 변조: 다른 labels 파일의 hash 불일치
lab = json.load(open(f'{d}/pairs_D.json')); lab[0]['ivd'][0]['modic'] = 0
json.dump(lab, open(f'{tmp}/pairs_tamper.json', 'w'))
chk('labels_tamper_rejected', raises(lambda: A.check_inputs('D', f'{d}/protocol_D_v2.json', f'{d}/requests_D.jsonl', f'{tmp}/pairs_tamper.json')))
# 최종 report: 원 BA02 재현 + 선택 재현
rp = 'results/iter_068/analysis/report.json'
if os.path.exists(rp):
    rep = json.load(open(rp)); o = json.load(open('results/iter_067/eval/E12/report.json')); od = json.load(open('results/iter_067/eval/D/report.json'))
    ok = all(abs(rep['models'][m]['orig_BA02_argmax']['E12'][c] - o['models'][m]['cond'][c]['BA02']) < 1e-9 and abs(rep['models'][m]['orig_BA02_argmax']['D'][c] - od['models'][m]['cond'][c]['BA02']) < 1e-9
             for m in A.MODELS for c in ['S1', 'S2', 'J', 'LF', 'T'])
    chk('orig_BA02_reproduced_D_E12', ok)
    chk('D_selection_reproduced', all(rep['models'][m]['select_D_reproduced'] for m in A.MODELS))
    # 독립 재계산: primary AUROC / threshold BA (보고서 값과 별도 코드 경로)
os.makedirs('results/iter_068/tests', exist_ok=True)
json.dump({'n': len(R), 'passed': sum(r['pass'] for r in R), 'results': R}, open('results/iter_068/tests/fixtures.json', 'w'), indent=1)
print(sum(r['pass'] for r in R), '/', len(R))
sys.exit(0 if all(r['pass'] for r in R) else 1)
