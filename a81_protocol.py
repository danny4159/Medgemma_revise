"""실행 전 입력·checkpoint·관련 code·gate 잠금."""
import argparse
import sys
import importlib.metadata
from pathlib import Path
import a81_common as C


def make(name, split, conds, tech=False):
    source = C.read(C.ROOT / 'data/source_audit.json')
    C.check_hashes(source['source_files'])
    rp = C.ROOT / f'data/requests_{split}.json'
    ids = C.read(C.ROOT / 'data/tech_ids.json') if tech else None
    req = [r for r in C.read(rp) if r['cond'] in conds and (ids is None or r['id'] in ids)]
    files = {p: C.sha(p) for p in C.code_files()}
    files.update(source['source_files'])
    for p in [rp, C.ROOT / f'data/baseline_{split}.json', C.ROOT / 'data/source_audit.json']:
        files[str(p)] = C.sha(p)
    if not tech:
        gate = C.read(C.ROOT / 'tests/technical_gate.json')
        assert gate['passed']
        for p, h in gate['files'].items():
            assert C.sha(p) == h
            files[p] = h
        files[str(C.ROOT / 'tests/technical_gate.json')] = C.sha(C.ROOT / 'tests/technical_gate.json')
        files[str(C.ROOT / 'selection.json')] = C.sha(C.ROOT / 'selection.json')
    if split == 'E24':
        v = C.read(C.ROOT / 'eval/V8.json')
        assert v['proceed_E24']
        files[str(C.ROOT / 'eval/V8.json')] = C.sha(C.ROOT / 'eval/V8.json')
    env = {k: importlib.metadata.version(k) for k in ['torch', 'transformers', 'numpy', 'Pillow']}
    out = C.ROOT / f'protocol_{name}.json'
    C.save(out, {'files': files, 'config': C.CONFIG, 'requests_path': str(rp), 'conds': conds, 'ids': ids,
                 'request_keys': [C.request_key(r) for r in req], 'split': split,
                 'environment': env, 'python': sys.executable, 'technical': tech})
    print(str(out), len(req))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('name'); ap.add_argument('--split', default='V8')
    ap.add_argument('--conds', default='Q,A,T,X'); ap.add_argument('--tech', action='store_true')
    a = ap.parse_args(); make(a.name, a.split, a.conds.split(','), a.tech)
