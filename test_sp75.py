"""iter_075/076 CPU fixture: 입력 연결·allowlist·ROI/표시·parser·metric·교환·prior + (iter_076) 선택·연장·loss gate·평가 입력·tail 복구.
결과: results/iter_076/tests/fixtures_cpu.json (존재하면 중단). 실패 시 비정상 종료."""
import json, os, sys
import numpy as np
from PIL import Image

import sp75_data as D
import sp75_metrics as M
import sp75_vlm as V

res = {}


def chk(name, cond, info=None):
    res[name] = {'pass': bool(cond), 'info': info}


sp, split_of = D.load_split()
man = D.load_manifest()
rows = man['rows']
F139 = set(json.load(open('results/iter_021/data/split.json'))['F'])
chk('allowlist_56_no_F139', len(split_of) == 56 and not set(split_of) & F139)
chk('manifest_patients_only_allowlist', set(man['patients']) == set(split_of))
chk('splits_disjoint', len(set(sp['T24']) | set(sp['V8']) | set(sp['E24'])) == 56)
try:
    D.G71.guard(sorted(F139)[0]); chk('F139_guard_blocks', False)
except PermissionError:
    chk('F139_guard_blocks', True)
chk('no_T24_V8_held_rows', not [r for r in rows if r['split'] in ('T24', 'V8') and r['position_set'] == 'held'])
chk('T24_V8_ordinals_135_only', all(r['ordinal'] in (1, 3, 5) for r in rows if r['split'] in ('T24', 'V8')))
chk('E24_ordinals_12345', {r['ordinal'] for r in rows if r['split'] == 'E24'} == {1, 2, 3, 4, 5})
inc = [r for r in rows if not r['excluded']]
chk('exclusions_are_mask_related_only', all(('mask' in r['excluded']) for r in rows if r['excluded']), [(r['id'], r['excluded']) for r in rows if r['excluded']])
chk('grades_1to5_no_imputation', all(r['grade'] in (1, 2, 3, 4, 5) for r in inc))
chk('each_set_has_all_5_grades', all({r['grade'] for r in inc if r['split'] == s and r['position_set'] == p} == {1, 2, 3, 4, 5} for s, p in (('T24', 'supervised'), ('V8', 'supervised'), ('E24', 'supervised'), ('E24', 'held'))))
# 입력 연결: 파일 hash, 3장, ROI 안쪽 불변, 바깥선만 표시
ok_hash, ok_outline, ok_roi, ok_three = True, True, True, True
for r in inc:
    if len(r['inputs']['F']) != 3 or len(r['inputs']['R']) != 3:
        ok_three = False
    for v in ('F', 'R'):
        for e in r['inputs'][v]:
            if D.sha_bytes(open(e['path'], 'rb').read()) != e['file_sha256']:
                ok_hash = False
    base = {e['off']: np.asarray(Image.open(f"{D.DATA}/images/{r['patient']}_{e['off']}.png")) for e in r['inputs']['F']}
    x0, y0, x1, y1 = r['roi']['roi_int_xyxy']
    for e, er in zip(r['inputs']['F'], r['inputs']['R']):
        f = np.asarray(Image.open(e['path']))
        b = base[e['off']]
        inner_same = np.array_equal(f[y0:y1, x0:x1, 0], b[y0:y1, x0:x1])
        diff = (f != np.repeat(b[:, :, None], 3, axis=2)).any(axis=2)
        diff_in_roi = diff[y0:y1, x0:x1].any()
        if not inner_same or diff_in_roi:
            ok_outline = False
        crop = np.asarray(Image.open(er['path']))
        if not np.array_equal(crop, b[y0:y1, x0:x1]):
            ok_roi = False
chk('F_R_three_images_each', ok_three)
chk('F_R_file_hash_match', ok_hash)
chk('F_outline_only_outside_roi_interior_unchanged', ok_outline)
chk('R_crop_equals_roi_of_base', ok_roi)
chk('roi_contains_all_mask_bboxes', all(r['roi']['roi_xyxy_px'][0] <= r['roi']['union_xyxy_px'][0] + 1e-9 and r['roi']['roi_xyxy_px'][2] >= r['roi']['union_xyxy_px'][2] - 1e-9 for r in inc))
old = json.load(open('results/iter_071/data/manifest.json'))
same = all(old['patients'][p]['images'][k]['file_sha256'] == v['file_sha256'] for p, i in man['patients'].items() for k, v in i['images'].items())
chk('base_slices_identical_to_iter071_hashes', same)
chk('manifest_no_model_output_or_clinical_text_in_inputs', all('grade' not in json.dumps(r['inputs']).lower() for r in inc))
chk('prompts_contain_no_patient_grade', all(c not in V.PROMPTS['F'].replace('Pfirrmann grade (1 = bright', '').replace('5 = dark', '') for c in ['grade 3', 'grade 4']))
# parser
pt = {'3': 3, ' 3 ': 3, '3.': 3, '3..': None, '33': None, 'Grade 3': None, '3 4': None, '': None, '6': None, '0': None, '3\n': 3, '3. ': 3, '.': None}
chk('parser_whole_string', all(V.parse(k) == v for k, v in pt.items()), pt)
# metric hand-calc
t = [1, 1, 2, 5]
p = [1, 3, None, 4]
cs, n = M.class_std_mae(t, p)
chk('class_std_mae_hand', abs(cs - np.mean([(0 + 2) / 2, 4.0, 1.0])) < 1e-12 and n == 3, cs)
sw = M.swap_predictions([{'patient': str(i), 'ordinal': 1} for i in range(5)], [1, 2, 3, 4, 5])
chk('swap_is_derangement_permutation', sorted(sw) == [1, 2, 3, 4, 5] and all(sw[i] != i + 1 for i in range(5)), sw)
tr = [r for r in inc if r['split'] == 'T24']
gp, op, pri = M.prior_predictions(tr, [r for r in inc if r['split'] == 'E24'])
chk('prior_train_only_dist_sums_to_1', all(abs(sum(v) - 1) < 1e-9 for v in pri['ordinal'].values()) and abs(sum(pri['global']) - 1) < 1e-9, pri)
chk('prior_uses_T24_only', pri['global'] == [sum(1 for r in tr if r['grade'] == g) / len(tr) for g in range(1, 6)])
b1 = M.boot_diff([r for r in inc if r['split'] == 'E24' and r['position_set'] == 'held'], [1] * 47, [3] * 47, n=200)
b2 = M.boot_diff([r for r in inc if r['split'] == 'E24' and r['position_set'] == 'held'], [1] * 47, [3] * 47, n=200)
chk('bootstrap_deterministic_seed7501', b1 == b2, b1)
# ---- iter_076 추가 검사 ----
import tempfile
import sp76_select as SEL
import sp75_train as TR
import sp75_eval as EV
import sp75_gen as GN
chk('pick_lr_lowest_primary', SEL.pick_lr([{'lr': '2e-5', 'primary': 0.9, 'ce': 1.0}, {'lr': '2e-4', 'primary': 0.8, 'ce': 5.0}]) == '2e-4')
chk('pick_lr_tie_primary_then_ce', SEL.pick_lr([{'lr': '2e-5', 'primary': 0.8, 'ce': 2.0}, {'lr': '2e-4', 'primary': 0.8, 'ce': 1.0}]) == '2e-4')
chk('pick_lr_full_tie_smaller_lr', SEL.pick_lr([{'lr': '2e-4', 'primary': 0.8, 'ce': 1.0}, {'lr': '2e-5', 'primary': 0.8, 'ce': 1.0}]) == '2e-5')
chk('ext_ce_exactly_5pct_extends', SEL.needs_extension({'primary': 0.8, 'ce': 2.0}, {'primary': 0.8, 'ce': 1.9})[0])
chk('ext_ce_4pct_no', not SEL.needs_extension({'primary': 0.8, 'ce': 2.0}, {'primary': 0.8, 'ce': 1.92})[0])
chk('ext_primary_gain_0.10_extends', SEL.needs_extension({'primary': 0.9, 'ce': 2.0}, {'primary': 0.8, 'ce': 2.5})[0])
chk('ext_primary_gain_0.09_no', not SEL.needs_extension({'primary': 0.89, 'ce': 2.0}, {'primary': 0.8, 'ce': 2.5})[0])
chk('final_epoch_prefers_better_primary', SEL.final_epoch({16: {'primary': 0.9, 'ce': 1.0}, 32: {'primary': 0.8, 'ce': 3.0}}) == 32)
chk('final_epoch_tie_ce_then_earlier', SEL.final_epoch({16: {'primary': 0.8, 'ce': 1.0}, 32: {'primary': 0.8, 'ce': 1.0}}) == 16 and
    SEL.final_epoch({16: {'primary': 0.8, 'ce': 2.0}, 32: {'primary': 0.8, 'ce': 1.0}}) == 32)
chk('final_epoch_excludes_epoch8', SEL.final_epoch({8: {'primary': 0.1, 'ce': 0.1}, 16: {'primary': 0.9, 'ce': 1.0}}) == 16)
g = {'status': 'PASS', 'official_loss': 6.12, 'logits_f32_ce_mean': 6.12, 'loss_sum_over_n': 6.12, 'rel_diff_official_vs_loss_sum': 0.0, 'n_valid_tokens': 2, 'n_valid_independent': 2, 'provenance': {'a': 1}}
chk('gate_pass_valid', TR.validate_gate(g, {'a': 1}) == [])
chk('gate_rejects_fail_status', bool(TR.validate_gate(dict(g, status='FAIL'), {'a': 1})))
chk('gate_rejects_nan', bool(TR.validate_gate(dict(g, loss_sum_over_n=float('nan')), {'a': 1})))
chk('gate_rejects_rel_gt_1e-6', bool(TR.validate_gate(dict(g, loss_sum_over_n=6.12 * (1 + 2e-6), rel_diff_official_vs_loss_sum=2e-6), {'a': 1})))
chk('gate_rejects_token_mismatch', bool(TR.validate_gate(dict(g, n_valid_independent=3), {'a': 1})))
chk('gate_rejects_provenance_change', bool(TR.validate_gate(g, {'a': 2})))
chk('gate_rejects_inconsistent_stored_rel', bool(TR.validate_gate(dict(g, rel_diff_official_vs_loss_sum=0.5), {'a': 1})))
chk('eval_constants', (EV.MARGIN, EV.PASS_ABS, EV.H_TOL, EV.C_NOT_WORSE) == (0.20, 1.0, 0.10, 0.10))
with tempfile.TemporaryDirectory() as td:
    pj = os.path.join(td, 'p.json')
    erows = [{'id': 'a', 'patient': '1', 'ordinal': 1, 'position_set': 'supervised'}, {'id': 'b', 'patient': '2', 'ordinal': 3, 'position_set': 'held'}]
    good = [{'id': 'a', 'patient': '1', 'ordinal': 1, 'position_set': 'supervised', 'pred': 2}, {'id': 'b', 'patient': '2', 'ordinal': 3, 'position_set': 'held', 'pred': 3}]

    def tryload(preds):
        json.dump({'preds': preds}, open(pj, 'w'))
        try:
            EV.load_json_pred(pj, erows)
            return True
        except RuntimeError:
            return False
    chk('json_pred_ok', tryload(good))
    chk('json_pred_rejects_duplicate', not tryload(good + [good[0]]))
    chk('json_pred_rejects_missing', not tryload(good[:1]))
    chk('json_pred_rejects_extra', not tryload(good + [dict(good[0], id='z')]))
    chk('json_pred_rejects_bad_grade', not tryload([dict(good[0], pred=7), good[1]]))
    gp = os.path.join(td, 'w.jsonl')
    open(gp, 'wb').write(b'{"id": "a"}\n{"id": "b", "te')
    r1 = GN.repair_tail(gp)
    chk('gen_repair_torn_tail', r1 is not None and open(gp, 'rb').read() == b'{"id": "a"}\n')
    open(gp, 'wb').write(b'{"id": "a"}\n{"id": "b"}')
    chk('gen_complete_last_line_without_newline_kept', GN.repair_tail(gp) is None and open(gp, 'rb').read().endswith(b'}'))
    open(gp, 'wb').write(b'{"id": "a"}\n')
    chk('gen_repair_noop_on_clean', GN.repair_tail(gp) is None)
fails = [k for k, v in res.items() if not v['pass']]
out = 'results/iter_076/tests/fixtures_cpu.json'
if os.path.exists(out):
    sys.exit('exists')
json.dump({'n': len(res), 'n_pass': len(res) - len(fails), 'fails': fails, 'checks': res}, open(out, 'w'), indent=1, default=str)
print(len(res), 'checks', len(fails), 'fails', fails)
sys.exit(1 if fails else 0)
