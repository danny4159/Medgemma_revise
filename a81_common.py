"""iter_081 고정 실험의 불변 입력·원자적 출력·출처 검사."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('results/iter_081')
ADAPTER = 'results/iter_077/train/R_lr2e-4/epoch_16'
ADAPTER_DIGEST = '72417dc383a99d36b797f77d12d050124749abf370b220c70108cc51b88cfc2c'
CONFIG = {'model_revision': '91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b', 'adapter_digest': ADAPTER_DIGEST,
          'dtype': 'bfloat16', 'do_sample': False, 'max_new_tokens': 32, 'batch': 1, 'seed': 0,
          'parser': 'sp75_vlm.parse; non-EOS invalid'}


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    """기존 산출물은 덮어쓰지 않는다. link의 EEXIST로 경합도 거부한다."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f'.{os.getpid()}.pending')
    with open(tmp, 'x') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.link(tmp, p)
    tmp.unlink()


def check_hashes(files):
    for p, h in files.items():
        if sha(p) != h:
            raise ValueError(f'provenance mismatch: {p}')


def request_key(r):
    return digest({'request': r, 'config': CONFIG})


def check_request(r):
    fields = {'id', 'patient', 'ordinal', 'split', 'cond', 'automated_grade', 'donor', 'images', 'prompt'}
    if set(r) != fields:
        raise ValueError('request allowlist / GT leakage')
    if r['cond'] not in ('Q', 'A', 'T', 'X') or r['automated_grade'] not in range(1, 6):
        raise ValueError('condition/grade')
    if len(r['images']) != (0 if r['cond'] == 'T' else 3):
        raise ValueError('image count')
    for e in r['images']:
        if set(e) != {'path', 'file_sha256', 'pixel_sha256_padded'}:
            raise ValueError('image allowlist')
        if sha(e['path']) != e['file_sha256']:
            raise ValueError('image hash')


def code_files():
    return sorted(set([str(p) for p in Path('.').glob('a81_*.py')] +
                      ['rf78_gen.py', 'rf78_vlm.py', 'rf78_launch.py', 'sp75_gen.py', 'sp75_vlm.py',
                       'sp75_data.py', 'sp75_metrics.py', 'sp67_data.py', 'g71_data.py'] +
                      [str(p) for p in Path('rsna_diag').glob('*.py')]))
