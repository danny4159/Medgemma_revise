"""iter_071 실행 경로 검사(GPU): (1) 생성 worker 부분 완료 후 재개, (2) 손상된 마지막 줄(torn tail) 복구, (3) adapter/학습 설정 변조 거부, (4) 2 worker 분할 일치.
기준: results/iter_071/gen/V4/T8_D_lr2e-4_e4의 같은 id 4건(같은 adapter). 결과: results/iter_071/tests/runtests.json
"""
import json, os, subprocess, sys, shutil

OUT = 'results/iter_071/tests'
ids = f'{OUT}/gen_resume_ids.json'
ad = 'results/iter_071/train/T8_D_lr2e-4/epoch_04'
d = f'{OUT}/gen_resume'
res = {}


def run(args, expect_ok=True):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, env=dict(os.environ, CUDA_VISIBLE_DEVICES=os.environ.get('G71_GPU', '0')))
    return r.returncode, (r.stdout + r.stderr)[-600:]


def toks(dirp):
    out = {}
    for f in sorted(os.listdir(dirp)):
        if f.startswith('gen_worker') and f.endswith('.jsonl'):
            for ln in open(f'{dirp}/{f}'):
                if ln.strip():
                    r = json.loads(ln)
                    out[r['id']] = r['suffix_ids']
    return out


ref = toks('results/iter_071/gen/V4/T8_D_lr2e-4_e4')
if os.path.exists(d):
    shutil.rmtree(d)
base = ['g71_gen.py', '--key', 'V4', '--adapter', ad, '--out-dir', d, '--ids-file', ids]
# (1) 2건만 처리 후 정상 종료 -> 재개
rc, o = run(base + ['--worker', '0', '--nworkers', '1', '--max-requests', '2'])
n1 = len(toks(d))
# (2) 마지막 줄을 중간에서 자른 torn tail을 만든다 (두 번째 record 일부만 남김)
f = f'{d}/gen_worker0.jsonl'
data = open(f, 'rb').read()
lines = data.split(b'\n')
open(f, 'wb').write(lines[0] + b'\n' + lines[1][:200])
rc2, o2 = run(base + ['--worker', '0', '--nworkers', '1'])
t = toks(d)
res['resume_after_partial_and_torn_tail'] = {'rc_first': rc, 'n_after_first': n1, 'rc_resume': rc2, 'n_final': len(t), 'torn_files': [x for x in os.listdir(d) if '.torn.' in x],
                                            'identical_tokens_vs_reference_run': all(t[i] == ref[i] for i in t), 'pass': rc == 0 and rc2 == 0 and len(t) == 4 and all(t[i] == ref[i] for i in t)}
# (3) 변조 거부: 다른 adapter로 같은 out-dir 재개
rc3, o3 = run(['g71_gen.py', '--key', 'V4', '--adapter', 'results/iter_071/train/T8_D_lr2e-4/epoch_08', '--out-dir', d, '--ids-file', ids, '--worker', '0', '--nworkers', '1'])
res['tamper_adapter_rejected'] = {'rc': rc3, 'msg': o3[-250:], 'pass': rc3 != 0 and 'mismatch' in o3.lower()}
# (3b) 학습 설정 변조: 다른 LR로 기존 run-dir 재개 거부 (모델 적재 후 config digest 검사)
rc4, o4 = run(['g71_train.py', '--run-dir', 'results/iter_071/tests/resume_ref', '--init', 'base', '--lr', '1e-4', '--train-key', 'T8', '--epochs', '2', '--save-epochs', '2', '--ckpt-every', '3'])
res['tamper_train_lr_rejected'] = {'rc': rc4, 'msg': o4[-250:], 'pass': rc4 != 0 and 'differs' in o4}
json.dump(res, open(f'{OUT}/runtests.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
