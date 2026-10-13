"""iter_132 전용 보존·출처 유틸리티."""
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

RES = Path(__file__).resolve().parent / 'results/iter_132'
DATA = Path('/home/test/.local/share/medgemma/mr_rate/mr_art/iter_132')
REV = 'fb45b349f21faa4b65ad23089788bbea30d07d74'
IQREV = '82b3272d7fe73b2a1965625efd821128eb081be3'

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20), b''): h.update(b)
    return h.hexdigest()

def now(): return datetime.now(timezone.utc).isoformat()
def digest(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def save(p,x):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'x') as f:
        json.dump(x,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())

