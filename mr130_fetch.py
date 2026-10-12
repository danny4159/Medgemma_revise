"""iter_130: pinned BrainTRACE metadata only; never downloads MRI or models."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests

HF_REV = '1861efc91c93e1de87f607c8d4a973dee1f9e898'
CODE_REV = '7c1d81753e7bfee50917dbb56fcabc5d1ee2679a'
PARQUET_SHA = '9fb3d82729f4de24e3b9f794496c4bcc50edf45ce9ed0b7f2b9b23c0c731d737'
ROOT = Path('/home/test/.local/share/medgemma/mr_rate/braintrace') / HF_REV
OUT = Path('results/iter_130')
HF_FILES = ['README.md', 'ATTRIBUTION.md', 'cohort/README.md',
            'cohort/braintrace_cohort_patients_1778.csv',
            'cohort/braintrace_cohort_studies_7299.csv', 'data/test.parquet']
CODE_FILES = ['README.md', 'LICENSE', 'DUA_NOTICE.md', 'docs/TAXONOMY.md',
              'docs/SCORING.md', 'reproduction/README.md',
              'reproduction/render_images.py', 'reproduction/render_volume_utils.py']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def clean_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, '', ''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if (OUT / 'fetch.json').exists():
        manifest = json.loads((OUT / 'fetch.json').read_text())
        assert manifest['hf_revision'] == HF_REV and manifest['code_revision'] == CODE_REV
        for entry in manifest['files']:
            assert sha(entry['path']) == entry['sha256'], entry['path']
        assert sha(ROOT / 'data/test.parquet') == PARQUET_SHA
        print(json.dumps({'state': 'verified_existing', 'n_files': len(manifest['files'])}))
        return
    if args.verify:
        raise RuntimeError('fetch.json missing')
    start = time.monotonic()
    attempt = {'started_at': datetime.now(timezone.utc).isoformat(), 'files': [], 'errors': []}
    OUT.mkdir(parents=True, exist_ok=True)
    attempt_n = len(list(OUT.glob('fetch_started*.json'))) + 1
    save(OUT / f'fetch_started_{attempt_n:02d}.json', {'hf_revision': HF_REV, 'code_revision': CODE_REV,
                                     'source_sha256': sha(__file__), **attempt})
    session = requests.Session()
    # Public metadata works without authentication; stored tokens are never read.
    def get(url):
        for trial in range(2):
            try:
                r = session.get(url, timeout=(15, 90))
                r.raise_for_status()
                if len(r.content) > 4_000_000:
                    raise ValueError('metadata-only per-object budget exceeded')
                return r
            except requests.RequestException as e:
                attempt['errors'].append({'url': clean_url(url), 'trial': trial + 1,
                                           'error_type': type(e).__name__})
                if trial == 1:
                    raise RuntimeError(f'public metadata request failed: {clean_url(url)}') from None
    api_url = f'https://huggingface.co/api/datasets/lanqz7766/BrainTRACE/revision/{HF_REV}'
    api = get(api_url).json()
    assert api['sha'] == HF_REV
    assert api['cardData']['license'] == 'cc-by-nc-sa-4.0'
    if (OUT / 'hf_repository.json').exists():
        assert json.loads((OUT / 'hf_repository.json').read_text()) == api
    else:
        save(OUT / 'hf_repository.json', api)
    total = 0
    for source, names in [('hf', HF_FILES), ('code', CODE_FILES)]:
        for name in names:
            url = (f'https://huggingface.co/datasets/lanqz7766/BrainTRACE/resolve/{HF_REV}/{name}'
                   if source == 'hf' else
                   f'https://raw.githubusercontent.com/lanqz7766/BrainTRACE/{CODE_REV}/{name}')
            t = time.monotonic()
            r = get(url)
            content = r.content
            total += len(content)
            assert total < 4_000_000, 'total metadata budget exceeded'
            digest = hashlib.sha256(content).hexdigest()
            if name == 'data/test.parquet':
                assert digest == PARQUET_SHA, 'published parquet digest mismatch'
            dest = ROOT / (name if source == 'hf' else f'official_code/{CODE_REV}/{name}')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                assert not dest.is_symlink() and sha(dest) == digest, 'existing asset mismatch'
                state = 'verified_existing_bytes'
            else:
                with dest.open('xb') as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                state = 'downloaded'
            attempt['files'].append({'source': source, 'name': name, 'url': url,
                                     'final_url_without_signed_query': clean_url(r.url),
                                     'path': str(dest), 'bytes': len(content), 'sha256': digest,
                                     'etag': r.headers.get('ETag'), 'state': state,
                                     'wall_s': time.monotonic() - t})
    attempt.update({'hf_revision': HF_REV, 'code_revision': CODE_REV, 'total_bytes': total,
                    'wall_s': time.monotonic() - start, 'source_sha256': sha(__file__),
                    'finished_at': datetime.now(timezone.utc).isoformat(),
                    'python': sys.executable, 'cuda_visible_devices': os.getenv('CUDA_VISIBLE_DEVICES'),
                    'packages': {p: importlib.metadata.version(p) for p in ['requests', 'pyarrow', 'pandas']},
                    'authentication': 'public requests; token not read',
                    'license': {'metadata': 'CC-BY-NC-SA-4.0', 'code': 'Apache-2.0',
                                'imagery_reports_derivatives': 'upstream MR-RATE DUA applies'},
                    'gpu_requests': 0, 'model_requests': 0, 'mri_download_bytes': 0,
                    'recovery': [{'attempt': 1, 'error': 'HTTP 404: docs/RUBRICS.md does not exist',
                                  'fix': 'pinned GitHub tree verified; rubric protocol is docs/SCORING.md; rendering guide is reproduction/README.md',
                                  'preservation': 'downloaded assets verified against fresh pinned bytes; initial fetch_started.json retained'}]})
    save(OUT / 'fetch.json', attempt)
    print(json.dumps({'state': 'complete', 'files': len(attempt['files']), 'bytes': total,
                      'wall_s': attempt['wall_s']}))


if __name__ == '__main__':
    main()
