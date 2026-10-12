"""iter_124 CPU 검사: 반입 SHA, W 요청 재현, parser, MedGemma 기존 W 상태, JSONL 손상/중복/누락/변조 거부. 결과는 새 파일에만 쓴다."""
import glob, json, os, shutil, subprocess, sys, tempfile

import mr124_run as M
import mr123_run as R

OUT = 'results/iter_124/tests/cpu_tests_v2.json'  # v1: 33/34, 실패는 검사 문구 결함(읽기 참조까지 금지)이었고 코드 문제 아님
res = []


def chk(name, ok, detail=''):
    res.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})


# 1. 반입 파일 blob/의존성
bl = {'mr123_data.py': '29a546610abbba25cf461028f34909e19e5b9db3', 'mr123_run.py': '17951678816aae93037948aa62703638f937baca'}
for f, b in bl.items():
    chk('blob ' + f, subprocess.check_output(['git', 'hash-object', '--', f], text=True).strip() == b)
chk('mr123_run imports mr123_data', R.D.__name__ == 'mr123_data')
chk('mr123_run.GEN은 iter_123 경로(본 반복은 사용하지 않음)', 'iter_123' in R.GEN and 'iter_123' not in ' '.join(M.OUTROOT for _ in [0]))

# 2. 요청 재현 (PNG 순서·sha·prompt)
src = {r['study_uid']: r for r in R.read_jsonl(M.SRC123['explore']) + R.read_jsonl(M.SRC123['tech']) if r['cond'] == 'W'}
for stage in ('explore', 'tech'):
    rows = M.read_jsonl(f'results/iter_124/gen/{stage}/requests.jsonl')
    ok = all(r['paths'] == src[r['study_uid']]['paths'] and r['png_sha256'] == src[r['study_uid']]['png_sha256'] and r['prompt'] == src[r['study_uid']]['prompt']
             and [M.sha_file(p) for p in r['paths']] == r['png_sha256'] for r in rows)
    chk(f'{stage} 요청 == iter_123 W 요청(경로·순서·PNG sha·prompt), PNG 현재 hash', ok, len(rows))
    chk(f'{stage} 요청에 label 등 정답 문자열이 prompt에 없음', all(r['label'] not in r['prompt'] and r['study_uid'] not in r['prompt'] for r in rows))
    chk(f'{stage} 요청 id 고유', len({r['id'] for r in rows}) == len(rows))
ex = M.read_jsonl('results/iter_124/gen/explore/requests.jsonl')
el = json.load(open(M.LOCK_ELIG))
chk('탐색 요청 == 적격 23명 정확히', {r['study_uid'] for r in ex} == {r['study_uid'] for r in el['rows'] if r['eligible']} and len(ex) == 23)
chk('7YYNKXI6YW 제외·대체 없음', '7YYNKXI6YW' not in {r['study_uid'] for r in ex})
tech = M.read_jsonl('results/iter_124/gen/tech/requests.jsonl')
chk('기술 4명이 탐색 24명과 겹치지 않음', not ({r['study_uid'] for r in tech} & {r['study_uid'] for r in el['rows']}) and len(tech) == 4)

# 3. parser
cases = [('PRESENT\nbecause', ('PRESENT', 'ok_strict')), ('**ABSENT**\nx', ('ABSENT', 'ok_strict')), ('UNCERTAIN', ('UNCERTAIN', 'ok_strict')),
         ('Answer: PRESENT', ('PRESENT', 'ok_loose')), ('PRESENT or ABSENT', ('INVALID', 'multi_state')), ('', ('INVALID', 'empty')),
         ('I am sorry, I cannot', ('INVALID', 'refusal')), ('The scan shows lesions', ('INVALID', 'no_state')), ('absent', ('ABSENT', 'ok_strict'))]
for t, exp in cases:
    chk('parse ' + repr(t[:25]), R.parse(t) == exp, R.parse(t))
out123 = []
for f in glob.glob('results/iter_123/gen/explore/worker_m*.jsonl'):
    out123 += R.read_jsonl(f)
chk('iter_123 192 출력 parser 재현', len(out123) == 192 and all(R.parse(o['text']) == (o['state'], o['parse_code']) for o in out123), len(out123))
byid = {o['id']: o for o in out123}
sel_ids = {r['orig_id'] for r in ex}
wst = [byid[i]['state'] for i in sel_ids]
chk('선정 23명의 MedGemma W 상태가 모두 PRESENT(기존 W 상태 유지)', len(wst) == 23 and all(s == 'PRESENT' for s in wst), wst.count('PRESENT'))

# 4. JSONL / protocol / verify 거부 검사
tmp = tempfile.mkdtemp(dir='results/iter_124/tests')
good = tmp + '/g.jsonl'
open(good, 'w').write('{"a":1}\n{"a":2}\n{"a":3')
chk('torn tail은 읽기에서 무시', M.read_jsonl(good) == [{'a': 1}, {'a': 2}])
mid = tmp + '/m.jsonl'
open(mid, 'w').write('{"a":1}\nBROKEN\n{"a":3}\n')
try:
    M.read_jsonl(mid); chk('중간 손상은 예외', False)
except Exception:
    chk('중간 손상은 예외', True)
try:
    M.repair_tail(mid); chk('중간 손상 repair 거부', False)
except Exception:
    chk('중간 손상 repair 거부', True)
n = M.repair_tail(good)
chk('repair_tail은 꼬리만 보존·제거', n > 0 and M.read_jsonl(good) == [{'a': 1}, {'a': 2}] and len(glob.glob(good + '.corrupt_*')) == 1, n)
# protocol 변조: 요청 파일 복사본 변경
prot = 'results/iter_124/gen/tech/protocol.json'
req = 'results/iter_124/gen/tech/requests.jsonl'
bad_req = tmp + '/req.jsonl'
shutil.copy(req, bad_req)
open(bad_req, 'a').write('\n')
p = subprocess.run([sys.executable, 'mr124_run.py', 'launch', '--requests', bad_req, '--protocol', prot, '--out-dir', tmp + '/o', '--gpus', '0', '--peak-gb', '1'],
                   capture_output=True, text=True)
chk('요청 변조 시 protocol 불일치로 거부', p.returncode != 0 and 'PROTOCOL MISMATCH' in (p.stdout + p.stderr), (p.stdout + p.stderr)[-150:])
badprot = tmp + '/prot.json'
pj = json.load(open(prot)); pj['digest'] = '0' * 64
json.dump(pj, open(badprot, 'w'))
p = subprocess.run([sys.executable, 'mr124_run.py', 'worker', '--requests', req, '--protocol', badprot, '--out-dir', tmp + '/o2', '--worker', '0'], capture_output=True, text=True)
chk('digest 변조 시 worker 거부', p.returncode != 0, (p.stdout + p.stderr)[-150:])
# verify: 빈 출력/누락/중복 거부
os.makedirs(tmp + '/v_empty')
p = subprocess.run([sys.executable, 'mr124_run.py', 'verify', '--requests', req, '--protocol', prot, '--out-dir', tmp + '/v_empty', '--out', tmp + '/v_empty.json'], capture_output=True, text=True)
chk('빈 출력(누락·launch 기록 없음)은 verify 실패', p.returncode != 0 and 'missing 4' in (p.stdout + p.stderr), (p.stdout + p.stderr)[-200:])
# 강제 GPU 허용 집합 밖
p = subprocess.run([sys.executable, 'mr124_run.py', 'launch', '--requests', req, '--protocol', prot, '--out-dir', tmp + '/o3', '--gpus', '5', '--peak-gb', '1'],
                   capture_output=True, text=True, env=dict(os.environ, CUDA_VISIBLE_DEVICES='0,1'))
chk('허용 GPU 집합 밖 거부', p.returncode != 0, (p.stdout + p.stderr)[-150:])

# 5. iter_123 쓰기 없음
newer = subprocess.run(['find', 'results/iter_123', '-newer', 'results/iter_124/data/candidates.json', '-type', 'f'], capture_output=True, text=True).stdout.strip()
chk('iter_123 경로에 본 반복 이후 변경된 파일 없음', newer == '', newer[:100])
chk('mr124 코드의 iter_123 참조는 읽기 전용(해당 줄에 쓰기 모드 open 없음)',
    not [l for l in open('mr124_run.py') if 'iter_123' in l and ("'w'" in l or "'a'" in l or 'append_row' in l)])

json.dump({'n': len(res), 'n_pass': sum(r['ok'] for r in res), 'results': res}, open(OUT, 'w'), indent=1) if not os.path.exists(OUT) else None
print(sum(r['ok'] for r in res), '/', len(res))
for r in res:
    if not r['ok']:
        print('FAIL', r)
