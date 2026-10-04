"""iter_067 CPU 검사: canonical 기하(축 permutation·flip), crop 경계, protocol 변조 거부, 지표 함수. 결과: results/iter_067/tests/cpu_tests.json
사용: python sp67_test.py"""
import json, os, shutil, sys
import numpy as np
import sp67_data as S
import sp67_eval as E
import sp67_run as R

res = []


def check(name, cond, detail=None):
    res.append({'name': name, 'pass': bool(cond), 'detail': detail})
    print('PASS' if cond else 'FAIL', name, detail if not cond else '')


def synth_geometry():
    # RAI 예: identity. ASL 예: 실제 header의 direction.
    for tag, D in (('RAI', [1, 0, 0, 0, 1, 0, 0, 0, 1]),
                   ('ASL', [0, 1, 0, 0, 0, -1, -1, 0, 0])):
        img = S.sitk.Image([5, 7, 9], S.sitk.sitkInt16)
        img.SetDirection(D); img.SetSpacing([3.0, 0.5, 0.7]); img.SetOrigin([1.0, 2.0, 3.0])
        arr = np.arange(5 * 7 * 9).reshape(9, 7, 5).astype(np.int16)
        arr_img = S.sitk.GetImageFromArray(arr); arr_img.CopyInformation(img)
        ca = S.canon_axes(arr_img.GetDirection())
        V, sp = S.to_canonical(arr, arr_img.GetSpacing(), ca)
        ok = True
        rng = np.random.RandomState(1)
        for _ in range(50):
            c = tuple(int(rng.randint(0, n)) for n in V.shape)
            oi = S.canon_to_orig_index(ca, V.shape, c)
            ok &= bool(arr[oi[2], oi[1], oi[0]] == V[c])
            ph = np.array(arr_img.TransformIndexToPhysicalPoint(oi))
            # canonical 축 (x,z,y)는 물리 x,z,y 증가 방향
            for ax in range(3):
                d = list(c); d[ax] += 1
                if d[ax] >= V.shape[ax]:
                    continue
                ph2 = np.array(arr_img.TransformIndexToPhysicalPoint(S.canon_to_orig_index(ca, V.shape, tuple(d))))
                pa = [0, 2, 1][ax]
                ok &= bool(ph2[pa] - ph[pa] > 0 and abs((ph2 - ph)[pa]) - sp[ax] < 1e-9)
        check(f'canonical_physical_{tag}', ok)
        check(f'canonical_shape_{tag}', sorted(V.shape) == [5, 7, 9] and sp == [arr_img.GetSpacing()[i] for i in ca['idx_axis']])
    try:
        S.canon_axes([0.7, 0.7, 0, 0, 0, 1, 1, 0, 0]); check('oblique_axis_rejected', False)
    except S.GeomError:
        check('oblique_axis_rejected', True)


def crop_tests():
    info = {'lo': [0, 100, 50], 'hi': [3, 119, 89]}   # si extent 20 vox, AP 40 vox
    cb = S.crop_box(info, (10, 300, 200), (4.0, 0.5, 0.5))
    W = 40 * 0.5
    check('crop_margin_si', abs(cb['margin_mm']['sup'] - W) <= 0.5 and abs(cb['margin_mm']['inf'] - W) <= 0.5, cb['margin_mm'])
    check('crop_margin_ap', abs(cb['margin_mm']['ant'] - 0.25 * W) <= 0.5 and abs(cb['margin_mm']['post'] - 0.25 * W) <= 0.5, cb['margin_mm'])
    cb2 = S.crop_box({'lo': [0, 5, 2], 'hi': [3, 20, 40]}, (10, 300, 200), (4.0, 0.5, 0.5))
    check('crop_clip_flagged', cb2['clip']['si_clipped_lo'] and cb2['clip']['pa_clipped_lo'] and cb2['si'][0] == 0 and cb2['pa'][0] == 0, cb2['clip'])


def metric_tests():
    y = np.array([0, 0, 2, 2, 1, 3]); p = np.array([0, 2, 2, 1, 1, 0])
    n0, c0, n2, c2 = E.ba02_counts(y, p)
    check('ba02_counts', (n0, c0, n2, c2) == (2, 1, 2, 1))   # 예측 I는 II 행의 오답
    cnt = np.array([[2, 1, 2, 1.0]])
    check('ba02_value', abs(E.ba_from_counts(cnt)[0] - 0.5) < 1e-12)
    check('ba02_nan_when_class_absent', np.isnan(E.ba_from_counts(np.array([[2, 1, 0, 0.0]]))[0]))
    P = np.array([[0.25, 0.25, 0.25, 0.25]])
    check('tie_argmax_smaller_grade', int((0.5 * (P + P)).argmax(1)[0]) == 0)


def protocol_tests():
    base = 'results/iter_067/data'
    req, lab, prot = f'{base}/requests_D.jsonl', f'{base}/pairs_D.json', f'{base}/protocol_D_v2.json'
    R.check_protocol(prot, req, lab)
    os.makedirs('results/iter_067/tests/tamper', exist_ok=True)
    t_req = 'results/iter_067/tests/tamper/requests_D_tampered.jsonl'
    rows = open(req).read().split('\n')
    rows[0] = rows[0].replace('Modic', 'Modik', 1) if 'Modic' in rows[0] else rows[0] + ' '
    open(t_req, 'w').write('\n'.join(rows))
    try:
        R.check_protocol(prot, t_req, lab); check('tamper_requests_rejected', False)
    except SystemExit:
        check('tamper_requests_rejected', True)
    t_lab = 'results/iter_067/tests/tamper/pairs_D_tampered.json'
    d = json.load(open(lab)); d[0]['ivd'][0]['modic'] = (d[0]['ivd'][0]['modic'] + 1) % 4
    json.dump(d, open(t_lab, 'w'))
    try:
        R.check_protocol(prot, req, t_lab); check('tamper_labels_rejected', False)
    except SystemExit:
        check('tamper_labels_rejected', True)


def request_tests():
    rows = [json.loads(l) for l in open('results/iter_067/data/requests_D.jsonl')]
    check('rid_unique', len({r['rid'] for r in rows}) == len(rows))
    # 모델 입력 prompt에 정답/등급이 들어가지 않는지: prompt는 환자·IVD와 무관한 템플릿 + 영상 수만 포함
    import re
    stripped = {(r['cond'], re.sub(r'\d+', '#', r['prompt'])) for r in rows}
    check('prompt_template_only_counts_vary', len(stripped) == len({r['cond'] for r in rows}), len(stripped))
    check('T_has_no_images', all(r['images'] == [] for r in rows if r['cond'] == 'T'))
    j = [r for r in rows if r['cond'] == 'J']
    s1 = {(r['patient'], r['ivd']): r for r in rows if r['cond'] == 'S1'}
    s2 = {(r['patient'], r['ivd']): r for r in rows if r['cond'] == 'S2'}
    check('J_is_S1_then_S2', all(r['images'] == s1[(r['patient'], r['ivd'])]['images'] + s2[(r['patient'], r['ivd'])]['images'] for r in j))


if __name__ == '__main__':
    synth_geometry(); crop_tests(); metric_tests(); protocol_tests(); request_tests()
    os.makedirs('results/iter_067/tests', exist_ok=True)
    json.dump({'n': len(res), 'n_pass': sum(r['pass'] for r in res), 'tests': res}, open('results/iter_067/tests/cpu_tests.json', 'w'), indent=1)
    print(sum(r['pass'] for r in res), '/', len(res))
    sys.exit(0 if all(r['pass'] for r in res) else 1)
