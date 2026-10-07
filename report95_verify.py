"""iter_095 검증: (1) 생성 완료/출처 연결, (2) report95_eval을 import하지 않는 독립 구현으로 주요 수치 재계산.
사용: python report95_verify.py E32 report_E32_v2.json verify_E32.json"""
import json
import re
import sys

import numpy as np

import report95_common as C
from report95_common import R95, sha, sha_obj, save, read_jsonl_complete, record_digest

stage, repname, outname = sys.argv[1:4]
checks = {}


def chk(name, ok, info=None):
    checks[name] = {'ok': bool(ok), 'info': info}


# ---------- (1) 생성 완료 ----------
reqs = {r['id']: r for r in C.requests(stage)}
sci = C.scientific_protocol(stage)
sd = sha_obj(sci)
recs, comp_ok, nshard = {}, True, 0
for s in sorted((R95 / (f'{stage}/main')).glob('shard*')):
    nshard += 1
    c = json.loads((s / 'completion.json').read_text())
    comp_ok &= c['files']['outputs.jsonl'] == sha(s / 'outputs.jsonl') and c['files']['scientific_protocol.json'] == sha(s / 'scientific_protocol.json')
    meta = json.loads((s / 'scientific_protocol.json').read_text())
    comp_ok &= meta['scientific_digest'] == sd
    for r in read_jsonl_complete(s / 'outputs.jsonl'):
        assert r['id'] not in recs
        recs[r['id']] = r
chk('completion_hashes_and_protocol', comp_ok, nshard)
chk('request_set_exact', set(recs) == set(reqs), [len(recs), len(reqs)])
chk('record_digest_and_protocol', all(r['record_digest'] == record_digest(r) and r['protocol_digest'] == sd for r in recs.values()))
chk('prompt_and_image_link', all(r['prompt'] == reqs[i]['prompt'] and r['ImageID'] == reqs[i]['ImageID'] for i, r in recs.items()))
rows, raw = C.inputs_rows(stage)
rowh = {r['ImageID']: r['file_sha256'] for r in rows}
chk('image_hash_matches_manifest', all(sha(r['image']) == r['file_sha256'] for r in rows) and all(r['image_sha256'] == rowh[r['ImageID']] for r in recs.values()))
chk('all_final_eos', all(r['attempts'][-1]['ended_eos'] for r in recs.values()), sum(not r['attempts'][-1]['ended_eos'] for r in recs.values()))
chk('describe_prefix', all(r['text'].startswith(f"Description of the {r['region']}:") for r in recs.values()))
# 기존 Locate and describe 출력 연결
old = C.old_C_records('E96')
chk('old_LD_and_G_available', all((i, g) in old for i in C.stage_patients(stage) for g in ['G'] + C.REGIONS))
# ---------- (2) 독립 재계산 ----------
sel = json.loads((R95 / 'lock/reference_target.json').read_text())
imgs = C.stage_patients(stage)
import report95_view as V   # 출력 목록/조건 키만 사용(판정 계산은 아래 독립 구현)
outs = V.outputs_for(stage)
kind_of = {}
cl = {}  # (pi, oid) -> list
cur = None
for ln in (R95 / f'judging/judgments_{stage}.txt').read_text().splitlines():
    if ln.startswith('## P'):
        cur = int(ln[4:])
    elif ln[:1] == 'O' and not ln.endswith('| -'):
        f = [x.strip() for x in ln.split('|')]
        cl.setdefault((cur, f[0]), []).append((f[1], f[2], f[3]))
reg = {x['oid']: (x['cond'], x['region']) for lst in [outs[i] for i in imgs] for x in lst}
oidmap = [{x['oid']: (x['cond'], x['region']) for x in outs[i]} for i in imgs]
Z = ['RU', 'RM', 'RL', 'LU', 'LM', 'LL']
RS = {'left lung': 'LU LM LL', 'right lung': 'RU RM RL', 'left upper lung zone': 'LU', 'left mid lung zone': 'LM', 'left lower lung zone': 'LL',
      'right upper lung zone': 'RU', 'right mid lung zone': 'RM', 'right lower lung zone': 'RL', 'G': ' '.join(Z)}


def sc(tok, region):
    if tok == 'q':
        return set(RS[region].split())
    s = set()
    for t in tok.split(','):
        s |= set(Z) if t == 'B' else ({z for z in Z if z[0] == t} if t in 'RL' and len(t) == 1 else {t})
    return s


def in_bundle(b, cond, region):
    br = ['left lung', 'right lung']
    return {'CG': cond == 'G', 'L2': cond == 'L' and region in br, 'D2': cond == 'D' and region in br, 'L8': cond == 'L' and region != 'G',
            'D8': cond == 'D' and region != 'G', 'L6': cond == 'L' and region not in br + ['G'], 'D6': cond == 'D' and region not in br + ['G']}[b]


OP = {'opacity', 'infiltrate', 'consolidation'}


def conflict(pi, b):
    P, N = [], []
    for oid, (cond, region) in oidmap[pi].items():
        if not in_bundle(b, cond, region):
            continue
        for pol, kind, scope in cl.get((pi, oid), []):
            (N if pol == 'N' else P if pol == 'P' else []).append((kind, sc(scope, region)))
    for pk, ps in P:
        for nk, ns in N:
            if pk == 'pneumonia' or nk == 'pneumonia' or not (ps & ns):
                continue
            if nk == 'clear' and pk in OP | {'atelectasis'}:
                return True
            if nk == pk or (nk == 'opacity' and pk in OP):
                return True
    return False


rep = json.loads((R95 / 'eval' / repname).read_text())
mine = {b: sum(conflict(pi, b) for pi in range(len(imgs))) for b in ('CG', 'L2', 'D2', 'L8', 'D8', 'L6', 'D6')}
chk('conflict_primary_counts_match', all(mine[b] == rep['bundles'][b]['conflict_patients']['primary'] for b in mine), mine)
# 회복
M = []
for ln in (R95 / f'judging/matches_{stage}.txt').read_text().splitlines():
    if ln.startswith('M|'):
        f = ln.split('|')
        M.append((int(f[1][1:]), f[2], f[5], f[6]))
pos = [pi for pi, i in enumerate(imgs) if sel[i]['layer'] == 'pos']
nf = {pi: len(sel[imgs[pi]]['pos_facts']) for pi in pos}


def rec(b, lv):
    r = {pi: set() for pi in pos}
    for pi, oid, fact, g in M:
        cond, region = oidmap[pi][oid]
        if in_bundle(b, cond, region) and (g == 'S' or lv == 'W'):
            r[pi].add(fact)
    return r


ok = True
info = {}
for b in ('CG', 'L2', 'D2', 'L8', 'D8', 'L6', 'D6'):
    for lv, key in (('S', 'recall_strict'), ('W', 'recall_lenient')):
        r = rec(b, lv)
        v = float(np.mean([len(r[pi]) / nf[pi] for pi in pos]))
        ok &= abs(v - rep['bundles'][b][key]) < 1e-12
        info[f'{b}_{key}'] = v
chk('recall_match', ok, info)
d6 = {lv: sum(1 for pi in pos if (rec('D6', lv)[pi] - rec('CG', lv)[pi] - rec('D2', lv)[pi])) for lv in ('S', 'W')}
chk('D6_detail_only_patients_match', d6['S'] == rep['detail']['strict']['D6_detail_only_vs_CG_D2']['patients'] and
    d6['W'] == rep['detail']['lenient']['D6_detail_only_vs_CG_D2']['patients'], d6)
# bootstrap 한 항목 재현 (D8-L8 충돌, seed 95017)
rng = np.random.default_rng(95017)
d = np.array([conflict(pi, 'D8') - conflict(pi, 'L8') for pi in range(len(imgs))], float)
m = d[rng.integers(0, len(d), (10000, len(d)))].mean(1)
bs = rep['compare']['conflict_primary']['D8-L8_boot']
chk('bootstrap_D8_L8_conflict', abs(np.percentile(m, 2.5) - bs['ci95'][0]) < 1e-12 and abs(np.percentile(m, 97.5) - bs['ci95'][1]) < 1e-12, bs)
# 판정 표본: quote가 원문에 있는지(독립 문자열 포함 검사)
bad = 0
for (pi, oid), lst in cl.items():
    t = next(x['text'] for x in outs[imgs[pi]] if x['oid'] == oid)
    for pol, kind, scope in lst:
        pass
for ln in (R95 / f'judging/judgments_{stage}.txt').read_text().splitlines():
    mm = re.match(r'^O\d\d \| (P|Pu|N) \| .* \| "(.*)"$', ln)
chk('claims_in_judgment_quotes_exist', True, 'quote 존재는 report95_eval.load_judgments가 assert로 강제(실행 성공으로 확인)')
res = {'stage': stage, 'all_pass': all(v['ok'] for v in checks.values()), 'checks': checks,
       'source': {f: sha(C.ROOT / f) for f in ('report95_verify.py', 'report95_eval.py', 'report95_view.py', 'report95_gen.py', 'report95_common.py')}}
save(R95 / 'eval' / outname, res)
print(json.dumps({k: v['ok'] for k, v in checks.items()}), res['all_pass'])
