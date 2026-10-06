"""iter_085 D8 부분 출력의 계승 검증. 원본 파일·protocol은 수정하지 않고 iter_086에 manifest만 만든다.

- 구버전(record_digest 없음): protocol 과학적 설정 일치 + completion.json의 파일 봉인(hash) 일치가 있을 때만 수용.
- 신버전(record_digest 있음): 행별 digest 재계산 + protocol 일치. completion이 없으면 '부분 결과'로만 수용.
- 근거 부족·불일치 행은 삭제하지 않고 quarantined로 기록하며 새로 생성한다.
python report86_inherit.py build   # inheritance_manifest.json 작성(이미 있으면 거부)
python report86_inherit.py verify  # 현재 원본 파일이 manifest와 같은지 재확인
"""
import json
import sys
import time
from pathlib import Path

from report86_common import (R85, R86, SYSTEMS, sha, sha_obj, save, read_jsonl_complete, record_digest,
                             scientific_protocol, expected_ids)

SOURCES = {'M15': R85 / 'D8/M15', 'B0': R85 / 'D8/B0', 'M1': R85 / 'D8/M1', 'M1G': R85 / 'D8/M1G_official', 'C': R85 / 'D8/C'}
SCI_KEYS = ['system', 'base', 'adapter_digest', 'seed', 'caps', 'prompts', 'input_sha256', 'raw_sha256']
EXEC_KEYS = ['gpu', 'logical_gpu', 'python', 'torch']
MANIFEST = R86 / 'inheritance_manifest.json'


def verify_source(system, d, rows_in):
    """returns dict with accepted ids / quarantined / provenance. 원본 파일은 읽기만 한다."""
    out = {'system': system, 'dir': str(d), 'accepted_ids': [], 'quarantined': [], 'problems': []}
    proto_p = d / 'protocol.json'
    old = json.loads(proto_p.read_text())
    new = scientific_protocol(system, 'D8')
    sci_diff = {k: {'old': old.get(k), 'new': new[k]} for k in SCI_KEYS if json.loads(json.dumps(old.get(k))) != json.loads(json.dumps(new[k]))}
    out['protocol_sha256'] = sha(proto_p)
    out['scientific_differences'] = sci_diff
    out['execution_old'] = {k: old.get(k) for k in EXEC_KEYS}
    out['source_sha256_old'] = old.get('source_sha256')
    out['outputs_sha256'] = sha(d / 'outputs.jsonl')
    out['outputs_bytes'] = (d / 'outputs.jsonl').stat().st_size
    if sci_diff:
        out['problems'].append('scientific protocol differs: ' + ','.join(sci_diff))
    recs = read_jsonl_complete(d / 'outputs.jsonl')
    ids = [r['id'] for r in recs]
    out['n_rows'] = len(recs)
    if len(ids) != len(set(ids)):
        out['problems'].append('duplicate ids')
    exp = expected_ids(rows_in, system)
    img_sha = {r['ImageID']: r['file_sha256'] for r in rows_in}
    comp_p = d / 'completion.json'
    seal_ok = None
    if comp_p.exists():
        comp = json.loads(comp_p.read_text())
        seal_ok = all(sha(d / n) == h for n, h in comp['files'].items())
        out['completion_sha256'] = sha(comp_p)
        out['completion_files_match'] = seal_ok
        out['completion_experiment_complete_flag'] = comp.get('experiment_complete')
    has_digest = [('record_digest' in r) for r in recs]
    out['record_digest_present'] = sum(has_digest)
    for r in recs:
        why = []
        if r['id'] not in exp:
            why.append('id not in expected set')
        if r.get('image_sha256') != img_sha.get(r.get('ImageID')):
            why.append('image sha mismatch')
        if r.get('protocol_digest') != out['protocol_sha256']:
            why.append('protocol digest mismatch')
        if not r['attempts'][-1]['ended_eos']:
            why.append('last attempt not EOS (kept? no: quarantined for regeneration)')
        if 'record_digest' in r:
            if r['record_digest'] != record_digest(r):
                why.append('record digest mismatch')
            method = 'record_digest'
        else:
            if not seal_ok:
                why.append('legacy row without record_digest and no matching completion file seal')
            method = 'legacy_file_seal'
        if sci_diff:
            why.append('scientific protocol differs')
        if why:
            out['quarantined'].append({'id': r['id'], 'reasons': why})
        else:
            out['accepted_ids'].append(r['id'])
            out.setdefault('methods', {})[method] = out.setdefault('methods', {}).get(method, 0) + 1
    out['partial_without_completion'] = not comp_p.exists()
    return out


def build():
    if MANIFEST.exists():
        sys.exit('inheritance_manifest.json exists; use a new attempt path')
    from report86_common import STAGES
    rows_in = json.loads(STAGES['D8']['inputs'].read_text())
    res = {'created': time.time(), 'stage': 'D8', 'input_sha256': sha(STAGES['D8']['inputs']),
           'rule': 'accepted only with protocol-scientific equality + (row digest | completion file seal); originals never modified',
           'systems': {s: verify_source(s, d, rows_in) for s, d in SOURCES.items()}}
    res['n_accepted'] = sum(len(v['accepted_ids']) for v in res['systems'].values())
    res['n_quarantined'] = sum(len(v['quarantined']) for v in res['systems'].values())
    res['reference_files'] = {
        'iter_085_handoff_final': sha(R85 / 'handoff_final.json'),
        'iter_085_plan': sha(Path('/SSD1_1TB/home/milab/daniel/08_medgemma/agent/runs/iter_085/plan.md'))}
    save(MANIFEST, res)
    print(json.dumps({s: {'n': v['n_rows'], 'accepted': len(v['accepted_ids']), 'quarantined': len(v['quarantined']),
                          'methods': v.get('methods'), 'problems': v['problems'], 'complete_seal': v.get('completion_files_match')}
                      for s, v in res['systems'].items()}, indent=1, ensure_ascii=False))


def load_verified(system):
    """원본 파일이 manifest 작성 시점과 같을 때만 수용된 행을 {id: record}로 돌려준다. 다르면 예외."""
    m = json.loads(MANIFEST.read_text())
    v = m['systems'][system]
    d = Path(v['dir'])
    # 원본이 이후 커지면(다른 프로세스 추가 기록) 앞 outputs_bytes까지의 prefix만 신뢰한다.
    data = (d / 'outputs.jsonl').read_bytes()[:v['outputs_bytes']]
    import hashlib
    if hashlib.sha256(data).hexdigest() != v['outputs_sha256']:
        raise RuntimeError(f'{system}: inherited outputs prefix hash mismatch')
    acc = set(v['accepted_ids'])
    recs = {}
    for ln in data.split(b'\n')[:-1]:
        if ln.strip():
            r = json.loads(ln)
            if r['id'] in acc:
                recs[r['id']] = r
    assert set(recs) == acc
    return recs, v


def verify():
    for s in SYSTEMS:
        recs, v = load_verified(s)
        print(s, len(recs), 'ok')


if __name__ == '__main__':
    {'build': build, 'verify': verify}[sys.argv[1]]()
