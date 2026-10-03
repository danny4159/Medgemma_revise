"""iter_062 CPU 검사: protocol 변조 차단, claim 원자성, 손상 tail 보존·복구. 결과: results/iter_062/tests/cpu_tests.json"""
import json, os, shutil, sys
import q62_run as Q

T = 'results/iter_062/tests/cpu'
os.makedirs(T, exist_ok=True)
R = {}


def expect_exit(fn):
    try:
        fn()
    except SystemExit as e:
        return str(e)
    return None


rows = [json.loads(l) for l in open('results/iter_062/data/D3_requests.jsonl')][:4]
for i, r in enumerate(rows):
    pass
# 영상 복사본을 쓰는 mini 요청
img_src = next(r['images'][0] for r in rows if r['images'])
shutil.copy(img_src, f'{T}/img.png')
mini = []
for r in rows:
    r = dict(r)
    r['images'] = [f'{T}/img.png'] if r['images'] else []
    mini.append(r)
open(f'{T}/req.jsonl', 'w').write(''.join(json.dumps(r) + '\n' for r in mini))
shutil.copy('results/iter_062/data/D3_labels.json', f'{T}/labels.json')
if os.path.exists(f'{T}/prot.json'):
    os.remove(f'{T}/prot.json')
import argparse
Q.cmd_lock(argparse.Namespace(requests=f'{T}/req.jsonl', labels=f'{T}/labels.json', out=f'{T}/prot.json'))
chk = lambda: Q.check_protocol(f'{T}/req.jsonl', f'{T}/labels.json', f'{T}/prot.json')
R['baseline_ok'] = chk() is not None


def tamper(name, path, fn):
    orig = open(path, 'rb').read()
    try:
        open(path, 'wb').write(fn(orig))
        msg = expect_exit(chk)
    finally:
        open(path, 'wb').write(orig)
    R[name] = {'blocked': msg is not None, 'msg': msg}


tamper('tamper_requests', f'{T}/req.jsonl', lambda b: b + b'\n')
tamper('tamper_labels', f'{T}/labels.json', lambda b: b.replace(b'"gt_orig_index": ', b'"gt_orig_index":  ', 1))
tamper('tamper_image', f'{T}/img.png', lambda b: b + b'x')
# 코드/parser/manifest/annotation 변조: CODE·경로를 임시 사본으로 치환해 같은 검사 경로 사용
shutil.copy('mri61_parse.py', f'{T}/parse_copy.py')
oldcode, olddata, oldS = Q.CODE, Q.DATA, Q.S.DATA
Q.CODE = Q.CODE + [f'{T}/parse_copy.py']
if os.path.exists(f'{T}/prot2.json'):
    os.remove(f'{T}/prot2.json')
Q.cmd_lock(argparse.Namespace(requests=f'{T}/req.jsonl', labels=f'{T}/labels.json', out=f'{T}/prot2.json'))
chk2 = lambda: Q.check_protocol(f'{T}/req.jsonl', f'{T}/labels.json', f'{T}/prot2.json')
orig = open(f'{T}/parse_copy.py', 'rb').read()
open(f'{T}/parse_copy.py', 'ab').write(b'\n# changed\n')
R['tamper_parser_or_code'] = {'blocked': expect_exit(chk2) is not None}
open(f'{T}/parse_copy.py', 'wb').write(orig)
R['restored_ok'] = chk2() is not None
Q.CODE = oldcode
# claim 원자성 / stale
cd = f'{T}/claims'
shutil.rmtree(cd, ignore_errors=True); os.makedirs(cd)
a = Q.claim(cd, 'r1', {'pid': os.getpid()})
b = Q.claim(cd, 'r1', {'pid': os.getpid() + 0})
R['claim_second_rejected'] = a and not b
open(f'{cd}/r2.claim', 'w').write(json.dumps({'pid': 2 ** 22 + 12345}))  # 존재하지 않는 pid
R['claim_stale_taken_over'] = Q.claim(cd, 'r2', {'pid': os.getpid()})
# 손상 tail 보존
p = f'{T}/w.jsonl'
open(p, 'w').write(json.dumps({'rid': 'a'}) + '\n' + json.dumps({'rid': 'b'}) + '\n' + '{"rid": "c", "att')
n = Q.repair_tail(p)
cor = [f for f in os.listdir(T) if f.startswith('w.jsonl.corrupt_')]
R['tail_repair'] = {'dropped_bytes': n, 'kept_rids': [r['rid'] for r in Q.read_jsonl(p)], 'corrupt_preserved': len(cor) == 1,
                    'preserved_has_torn_line': b'att' in open(f'{T}/{cor[0]}', 'rb').read() if cor else False}
R['all_pass'] = (R['baseline_ok'] and all(R[k]['blocked'] for k in ('tamper_requests', 'tamper_labels', 'tamper_image', 'tamper_parser_or_code'))
                 and R['restored_ok'] and R['claim_second_rejected'] and R['claim_stale_taken_over']
                 and R['tail_repair']['kept_rids'] == ['a', 'b'] and R['tail_repair']['corrupt_preserved'])
json.dump(R, open('results/iter_062/tests/cpu_tests.json', 'w'), indent=1)
print(json.dumps(R, indent=1))
sys.exit(0 if R['all_pass'] else 1)
