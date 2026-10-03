"""iter_062: Qwen2.5-VL-7B-Instruct 공식 checkpoint를 별도 캐시에 확보하고 revision/digest를 기록한다.
기존 hf_cache는 건드리지 않는다. 사용: python q62_fetch.py
"""
import hashlib, json, os, sys
os.environ.pop('HF_HUB_OFFLINE', None)
from huggingface_hub import HfApi, snapshot_download

REPO = 'Qwen/Qwen2.5-VL-7B-Instruct'
CACHE = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_cache'
OUT = 'results/iter_062/env/qwen_fetch.json'

os.makedirs(os.path.dirname(OUT), exist_ok=True)
info = HfApi().model_info(REPO)
rev = info.sha
print('revision', rev, 'license', (info.card_data or {}).get('license') if info.card_data else None)
path = snapshot_download(REPO, revision=rev, cache_dir=CACHE,
                         allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', '*.jinja'])
files = {}
for root, _, fs in os.walk(path):
    for f in sorted(fs):
        p = os.path.join(root, f)
        h = hashlib.sha256()
        with open(os.path.realpath(p), 'rb') as fh:
            for ch in iter(lambda: fh.read(1 << 24), b''):
                h.update(ch)
        files[os.path.relpath(p, path)] = {'sha256': h.hexdigest(), 'bytes': os.path.getsize(os.path.realpath(p))}
json.dump({'repo': REPO, 'revision': rev, 'snapshot_path': path, 'cache_dir': CACHE,
           'license': getattr(info.card_data, 'license', None), 'files': files}, open(OUT, 'w'), indent=1)
print('files', len(files), 'total GB', sum(v['bytes'] for v in files.values()) / 2**30)
