"""iter_137 전용 경로·출처 유틸리티 (i136_common 파생). 결과는 results/iter_137에만 쓰고 iter_136 자료는 읽기 전용으로만 쓴다."""
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RES = HERE / 'results/iter_137'
DATA = RES / 'data'
OLD136 = HERE / 'results/iter_136'   # 읽기 전용 입력(manifest·PNG)
GEN_SEED = 136     # 생성 seed (계획: 원 실행과 동일)
BOOT_SEED = 137    # bootstrap seed (계획)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def now(): return datetime.now(timezone.utc).isoformat()
def digest(x): return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def save(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'x') as f:
        json.dump(x, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
