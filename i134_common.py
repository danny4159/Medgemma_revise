"""iter_134 전용 경로·출처 유틸리티 (i133_common 파생; 결과는 results/iter_134에만 쓴다)."""
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RES = HERE / 'results/iter_134'
OLD = HERE / 'results/iter_070/data'   # 읽기 전용 기존 자료(RadGenome 보고서·split·미러 listing)
DATA = RES / 'data'
BRATS = DATA / 'brats'
REPO = 'MedOtter/brats2023-gli-dataset'
REVISION = 'b032d353a3e80911a5f850bc54e6fb575298a354'
BASE = 'ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/'
SEED = 134


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
