"""iter_096 입력 잠금: E32 selection/reference/blind key, iter_086 C-G·Locate 원출력, iter_095 Describe 4 shard를 연결해
544개 출력(환자 32 x 17)의 ID·조건·영역·중복·누락·digest와 형식 상태(EOS)를 명시적으로 기록한다.
사용: python report96_lock.py   (새 파일만 쓰며 기존 iter_095 결과는 읽기 전용)"""
import hashlib
import json
from pathlib import Path

import report95_common as C95
import report95_view as V
import report86_common as C86
from report86_common import sha, sha_obj, save

ROOT = Path(__file__).resolve().parent
R96 = ROOT / 'results/iter_096'
R95 = C95.R95
PLAN95_SHA = '3e079003205374c9b841a9557b93bf64011f2152280d1d3e211bd9f655f3b4f7'
AUDIT_TAG = 'iter096-audit95017'


def audit_order(ids):
    return sorted(ids, key=lambda i: hashlib.sha256(f'{AUDIT_TAG}|{i}'.encode()).hexdigest())


def shard_files(stage_root):
    return sorted(str(p.relative_to(ROOT)) for s in Path(stage_root).glob('shard*') for p in (s / 'outputs.jsonl', s / 'completion.json'))


def build():
    plan95 = ROOT.parent / 'agent/runs/iter_095/plan.md'
    assert sha(plan95) == PLAN95_SHA, 'iter_095 plan sha differs'
    outs = V.outputs_for('E32')          # old_C_records가 completion/record digest를 검증한다
    key = json.loads((R95 / 'judging/blind_key_private_E32.json').read_text())
    sel = json.loads((R95 / 'lock/selection.json').read_text())
    ref = json.loads((R95 / 'lock/reference_target.json').read_text())
    pats = sel['E32']
    assert list(outs) == pats and len(pats) == 32
    rows, seen_ids = [], set()
    for pi, img in enumerate(pats):
        assert len(outs[img]) == 17
        for x in outs[img]:
            rid = x['rec']['id']
            assert rid not in seen_ids, rid
            seen_ids.add(rid)
            k = key[img][x['oid']]
            assert k[2] == rid and k[0] == x['cond'] and k[1] == x['region'], (img, x['oid'])
            assert x['rec']['record_digest'] == C86.record_digest(x['rec']), rid
            last = x['rec']['attempts'][-1]
            rows.append({'p': pi, 'ImageID': img, 'oid': x['oid'], 'cond': x['cond'], 'region': x['region'], 'request_id': rid,
                         'text_sha256': hashlib.sha256(x['text'].encode()).hexdigest(), 'raw_text_sha256': hashlib.sha256(x['rec']['text'].encode()).hexdigest(),
                         'ended_eos': bool(last['ended_eos']), 'n_new': last['n_new'], 'runtime_s_sum': sum(a['runtime_s'] for a in x['rec']['attempts'])})
    assert len(rows) == 544
    conds = {}
    for r in rows:
        conds[r['cond']] = conds.get(r['cond'], 0) + 1
    assert conds == {'G': 32, 'L': 256, 'D': 256}, conds
    non_eos = [(r['p'], r['oid'], r['cond'], r['region']) for r in rows if not r['ended_eos']]
    pos = [i for i in pats if ref[i]['layer'] == 'pos']
    # 결정 관련 집합(재판정 전 고정): 양성 reference 환자 + iter_095 판정에서 회복 match가 있거나 어떤 번들·변형에서든 충돌이 있던 환자
    import report95_eval as E95
    claims, outs_text, _ = E95.load_judgments(['E32'])
    matches = E95.load_matches(['E32'], outs_text, claims)
    B = E95.bundle_outputs(outs_text)
    old_conf = set()
    for b in B:
        for kw in ({'mode': 'question'}, {'mode': 'question', 'use_pu': True}, {'mode': 'global'}, {'mode': 'question', 'broad': True}):
            for img, pr in E95.conflicts(claims, B[b], **kw).items():
                if pr:
                    old_conf.add(img)
    old_match = {m['img'] for m in matches}
    decision = [i for i in pats if i in set(pos) | old_conf | old_match]
    rest_ids = [i for i in pats if i not in decision]
    manifest = {
        'baseline_plan': {'path': 'agent/runs/iter_095/plan.md', 'sha256': PLAN95_SHA},
        'selection_sha256': sha(R95 / 'lock/selection.json'), 'reference_target_sha256': sha(R95 / 'lock/reference_target.json'),
        'blind_key_sha256': sha(R95 / 'judging/blind_key_private_E32.json'),
        'iter086_C_E96_shards': shard_files(C86.R86 / 'E96/C') if (C86.R86 / 'E96/C').exists() else shard_files(C86.R86 / 'E/C'),
        'iter095_E32_describe_shards': shard_files(R95 / 'E32/main'),
        'file_sha256': {f: sha(ROOT / f) for f in (shard_files(R95 / 'E32/main') + (shard_files(C86.R86 / 'E96/C') if (C86.R86 / 'E96/C').exists() else shard_files(C86.R86 / 'E/C')))},
        'n_patients': 32, 'n_outputs': 544, 'cond_counts': conds, 'non_eos_final': non_eos,
        'strata': {k: sum(ref[i]['layer'] == k for i in pats) for k in ('pos', 'neg', 'rest')},
        'audit_tag': AUDIT_TAG, 'decision_relevant_prior': [pats.index(i) for i in decision], 'audit12_patient_idx': [pats.index(i) for i in audit_order(rest_ids)][:12],
        'rows': rows,
    }
    manifest['sha256'] = sha_obj({k: v for k, v in manifest.items() if k != 'rows'})
    return manifest


if __name__ == '__main__':
    m = build()
    save(R96 / 'lock/input_manifest.json', m)
    print(json.dumps({k: m[k] for k in ('n_patients', 'n_outputs', 'cond_counts', 'non_eos_final', 'strata', 'decision_relevant_prior', 'audit12_patient_idx')}))
