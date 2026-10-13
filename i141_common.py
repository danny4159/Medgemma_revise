"""iter_141 출처·배타 저장 유틸리티. i136_common.py의 작은 hash/save 경로를 파생."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RES = HERE / 'results/iter_141'


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
