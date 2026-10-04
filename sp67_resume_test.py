"""iter_067 재개·변조 검사(GPU, MedGemma): 8개 D 요청 subset에서 (1) worker가 3건 저장 후 정상 종료, (2) torn 꼬리 행 추가, (3) 2개 worker slot으로 재개,
(4) 중복·누락 0, 기존 D 본실행 점수와 일치, (5) 변조된 요청 파일로 worker 시작 거부. 결과: results/iter_067/tests/resume_test.json"""
import glob, json, os, subprocess, sys
import m65_run as M65

T = 'results/iter_067/tests/resume'
os.makedirs(T, exist_ok=True)
rows = M65.read_jsonl('results/iter_067/data/requests_D.jsonl')
sub = [r for r in rows if len(r['images']) <= 21 and r['cond'] in ('S1', 'J', 'T')][:8]
req = f'{T}/requests.jsonl'
open(req, 'w').write(''.join(json.dumps(r) + '\n' for r in sub))
lab, prot, out = 'results/iter_067/data/pairs_D.json', f'{T}/protocol.json', f'{T}/gen/medgemma'
if os.path.exists(prot):
    raise SystemExit('resume test dir already used; use a new path')
subprocess.run([sys.executable, 'sp67_run.py', 'lock', '--requests', req, '--labels', lab, '--out', prot], check=True)


def worker(widx, nw, limit=0, request=req):
    cmd = [sys.executable, 'sp67_run.py', 'worker', '--model', 'medgemma', '--requests', request, '--labels', lab, '--protocol', prot, '--out-dir', out,
           '--widx', str(widx), '--nworkers', str(nw)] + (['--limit', str(limit)] if limit else [])
    return subprocess.run(cmd, capture_output=True, text=True)


res = {}
r1 = worker(0, 1, limit=3)
res['phase1_rc'] = r1.returncode
n1 = len(M65.read_jsonl(f'{out}/worker0.jsonl'))
with open(f'{out}/worker0.jsonl', 'ab') as f:
    f.write(b'{"rid": "torn')   # 저장 도중 종료 모사
res['phase1_rows'] = n1
res['torn_tail_present'] = not open(f'{out}/worker0.jsonl', 'rb').read().endswith(b'\n')
ra = worker(0, 2); rb = worker(1, 2)
res['phase2_rc'] = [ra.returncode, rb.returncode]
res['repair_log'] = [l for l in ra.stdout.splitlines() if 'repaired' in l]
recs = {}
dup = 0
for f in glob.glob(f'{out}/worker*.jsonl'):
    for r in M65.read_jsonl(f):
        dup += r['rid'] in recs
        recs[r['rid']] = r
res['n_records'] = len(recs); res['duplicates'] = dup
res['missing'] = sorted({r['rid'] for r in sub} - set(recs))
res['corrupt_tail_preserved'] = len(glob.glob(f'{out}/worker0.jsonl.corrupt_*'))
main = {}
for l in open('results/iter_067/gen_D/medgemma/worker0.jsonl'):
    x = json.loads(l); main[x['rid']] = x
diffs = [max(abs(a - b) for a, b in zip(recs[r['rid']]['cand_logits'], main[r['rid']]['cand_logits'])) for r in sub]
res['max_logit_diff_vs_main'] = max(diffs); res['pred_equal_all'] = all(recs[r['rid']]['pred'] == main[r['rid']]['pred'] for r in sub)
tam = f'{T}/requests_tampered.jsonl'
open(tam, 'w').write(open(req).read().replace('Modic', 'Modik', 1))
rt = worker(0, 1, request=tam)
res['tamper_rc'] = rt.returncode; res['tamper_msg'] = (rt.stdout + rt.stderr).strip().splitlines()[-1][:200]
res['pass'] = bool(res['phase1_rc'] == 0 and n1 == 3 and res['torn_tail_present'] and res['phase2_rc'] == [0, 0] and dup == 0 and not res['missing']
                   and res['n_records'] == 8 and res['pred_equal_all'] and res['max_logit_diff_vs_main'] <= 0.5 and res['tamper_rc'] != 0 and res['corrupt_tail_preserved'] >= 1)
json.dump(res, open('results/iter_067/tests/resume_test.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
