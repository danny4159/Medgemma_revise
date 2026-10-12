"""iter_123: 본 생성 전 평가·요청 코드/입력 잠금. usage: python mr123_lock.py <stage> <build_json>"""
import hashlib, json, os, sys, time
import mr123_run as R

CODE = ['mr123_labels.py', 'mr123_select.py', 'mr123_data.py', 'mr123_run.py', 'mr123_eval.py', 'mr123_launch.py', 'mr123_fetch.py', 'mr123_tech_build.py']


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


stage, build = sys.argv[1], sys.argv[2]
p = R.GEN + stage + '/protocol.json'
assert not os.path.exists(p)
d = dict(stage=stage, locked_at_unix=time.time(), locked_at=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
         note='이 잠금은 explore 생성 출력이 존재하기 전에 작성됨. 평가 코드·parser·결정 기준 포함.',
         code_sha256={c: sha(c) for c in CODE},
         inputs=dict(requests=sha(R.GEN + stage + '/requests.jsonl'), selection_lock=sha(R.D.RES + 'data/selection_lock.json'),
                     build=sha(build), fetch_ledger=sha(R.D.RES + 'data/fetch_ledger.json')),
         model=dict(name=R.MODEL, revision=R.REV, dtype='bfloat16', greedy=True, max_new_tokens=512),
         existing_outputs=[f for f in os.listdir(R.GEN + stage) if f.startswith('worker_')])
json.dump(d, open(p, 'w'), indent=1)
print(d['locked_at'], d['existing_outputs'])
