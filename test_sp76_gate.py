"""iter_076: loss gate 변조·실패·손상 파일이 실제 학습 진입점(sp75_train.py)에서 모델 적재 전에 학습을 차단하는지 검사한다 (CPU, GPU 불필요).
각 사례: run-dir에 loss_gate.json 변형을 두고 sp75_train.py를 실행 -> 비정상 종료 + 'blocks training' 메시지 + train_log/checkpoint 미생성.
결과: results/iter_076/tests/gate_tamper.json (존재하면 중단). 하나라도 차단 안 되면 비정상 종료.
"""
import json, os, subprocess, sys

import sp75_train as TR

BASE = 'results/iter_076/tests/gate_tamper'
OUT = 'results/iter_076/tests/gate_tamper.json'


def main():
    if os.path.exists(OUT) or os.path.exists(BASE):
        sys.exit('exists')
    rows = TR.load_rows('T24')
    tin = TR.inputs_digest(rows, 'F')
    code = {f: TR.file_sha(f) for f in TR.CODE}
    prov = TR.gate_provenance('F', rows, tin, code)
    good = {'status': 'PASS', 'official_loss': 6.12, 'logits_f32_ce_mean': 6.12, 'loss_sum_over_n': 6.12, 'rel_diff_official_vs_loss_sum': 0.0, 'n_valid_tokens': 2,
            'n_valid_independent': 2, 'provenance': prov}
    cases = {'fail_status': dict(good, status='FAIL'), 'nan_loss': dict(good, loss_sum_over_n=float('nan')),
             'rel_diff_2e-6': dict(good, loss_sum_over_n=6.12 * (1 + 2e-6), rel_diff_official_vs_loss_sum=2e-6),
             'token_mismatch': dict(good, n_valid_independent=3), 'other_code_hash': dict(good, provenance=dict(prov, code=dict(code, **{'sp75_vlm.py': '0' * 64}))),
             'other_inputs': dict(good, provenance=dict(prov, train_inputs_digest='0' * 64)), 'missing_provenance': {k: v for k, v in good.items() if k != 'provenance'}}
    res = {}
    for name, g in cases.items():
        d = f'{BASE}/{name}'
        os.makedirs(d)
        json.dump(g, open(f'{d}/loss_gate.json', 'w'))
        r = subprocess.run([sys.executable, 'sp75_train.py', '--run-dir', d, '--variant', 'F', '--lr', '2e-4', '--epochs', '1'], capture_output=True, text=True)
        msg = (r.stdout + r.stderr)[-300:]
        res[name] = {'rc': r.returncode, 'blocked_with_message': 'blocks training' in msg, 'no_train_log': not os.path.exists(f'{d}/train_log.jsonl'), 'no_ckpt': not os.path.exists(f'{d}/ckpt_latest.pt'), 'msg_tail': msg}
    d = f'{BASE}/corrupt_json'
    os.makedirs(d)
    open(f'{d}/loss_gate.json', 'w').write('{"status": "PASS", "official_')
    r = subprocess.run([sys.executable, 'sp75_train.py', '--run-dir', d, '--variant', 'F', '--lr', '2e-4', '--epochs', '1'], capture_output=True, text=True)
    msg = (r.stdout + r.stderr)[-300:]
    res['corrupt_json'] = {'rc': r.returncode, 'blocked_with_message': 'blocks training' in msg, 'no_train_log': not os.path.exists(f'{d}/train_log.jsonl'), 'no_ckpt': not os.path.exists(f'{d}/ckpt_latest.pt'), 'msg_tail': msg}
    res['PASS'] = all(v['rc'] != 0 and v['blocked_with_message'] and v['no_train_log'] and v['no_ckpt'] for v in res.values() if isinstance(v, dict))
    json.dump(res, open(OUT, 'w'), indent=1)
    print(json.dumps({k: (v['rc'], v['blocked_with_message']) for k, v in res.items() if isinstance(v, dict)}), res['PASS'])
    sys.exit(0 if res['PASS'] else 1)


if __name__ == '__main__':
    main()
