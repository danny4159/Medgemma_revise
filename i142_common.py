"""iter_142의 고정 자산 연결, 배타적 소유권과 보존 저장."""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RES = ROOT / 'results/iter_142'
OLD = ROOT / 'results/iter_141'
ENV = ROOT / 'results/environments/autorg70/bin/python'
MODELS = ROOT / 'results/iter_070/models'
SRC = ROOT / 'results/iter_070/external/src/AutoRG-Brain-9670703c88e8f599c0c7edc472a5ffce4dd72b0e'
SDK = RES / 'external/AutoRG_Brain'

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()

def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def read(p):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError('duplicate key: ' + k)
            d[k] = v
        return d
    return json.loads(Path(p).read_text(), object_pairs_hook=pairs)

def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        raise FileExistsError(p)
    tmp = p.with_name(p.name + '.tmp.' + str(os.getpid()))
    with open(tmp, 'x') as f:
        json.dump(x, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    # 배타 link는 존재 확인과 rename 사이 경합도 거부한다.
    os.link(tmp, p)
    tmp.unlink()

@contextlib.contextmanager
def ownership(p):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield

def verify_protocol(p):
    x = read(p)
    assert x['digest'] == digest({k:v for k,v in x.items() if k != 'digest'})
    for path, h in x['files'].items():
        assert sha(path) == h, 'protocol hash mismatch: ' + path
    return x

def verify_result(p, protocol, expected):
    x = read(p)
    assert x['status'] == 'ok'
    assert x['record_digest'] == digest({k:v for k,v in x.items() if k != 'record_digest'})
    assert x['protocol_digest'] == protocol['digest']
    assert x['input'] == expected
    for path, h in x['outputs'].items():
        assert sha(path) == h
    assert sha(expected['image']) == expected['image_sha256']
    return x
