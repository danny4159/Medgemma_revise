"""iter_141 고정 ISLES22 후보의 공식 자료를 확인하고 원본을 보존한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results/iter_141'
REV = '0348ba42fad134da57b50e736ba858a8e73eb086'
IDS = ['sub-strokecase' + x for x in ['0001', '0003', '0004', '0006', '0007', '0008', '0009', '0010']]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def save(p, obj):
    with Path(p).open('x') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def fetch():
    import requests
    if OUT.exists():
        raise FileExistsError('기존 결과 보존: ' + str(OUT))
    OUT.mkdir(parents=True)
    official = OUT / 'official'
    official.mkdir()
    session = requests.Session()
    session.trust_env = False
    records = []
    for name in ['ISLES22/modal_wise_finding.json', 'ISLES22/global_finding.json',
                 'ISLES22/impression.json', 'train_val_test_split.json', 'README.md']:
        url = f'https://huggingface.co/datasets/JiayuLei/RadGenome-Brain_MRI/resolve/{REV}/{name}'
        dest = official / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        start = now()
        r = session.get(url, timeout=60)
        rec = {'path': name, 'requested_at': start, 'url': url, 'final_url': r.url,
               'status_code': r.status_code, 'bytes': len(r.content),
               'response_sha256': hashlib.sha256(r.content).hexdigest()}
        records.append(rec)
        if r.status_code == 200:
            with dest.open('xb') as f:
                f.write(r.content)
        else:
            with (official / (name.replace('/', '__') + '.error.txt')).open('x') as f:
                f.write(r.text)
    save(OUT / 'fetch_manifest.json', {'created_at': now(), 'revision': REV, 'records': records})
    print(json.dumps({'downloads': len(records), 'statuses': [x['status_code'] for x in records]}))


def inspect():
    official = OUT / 'official'
    split = json.loads((official / 'train_val_test_split.json').read_text())
    docs = {name: json.loads((official / f'ISLES22/{name}.json').read_text())
            for name in ['modal_wise_finding', 'global_finding', 'impression']}
    train = split['train']
    rows = []
    for pid in IDS:
        # 공식 key를 그대로 보존하며 문자열 유사 연결은 하지 않는다.
        keys = [k for k in train if k.startswith(pid + '_') or k.startswith(pid + '-') or k == pid]
        row = {'patient_id': pid, 'role': 'technical' if pid in IDS[:2] else 'exploration',
               'train_keys': keys, 'documents': {}}
        for name, d in docs.items():
            matches = {k: v for k, v in d.items() if k.startswith(pid + '_') or k.startswith(pid + '-') or k == pid}
            row['documents'][name] = matches
        rows.append(row)
    result = {'created_at': now(), 'schema': {n: {'type': type(d).__name__, 'count': len(d),
              'value_types': sorted(set(type(v).__name__ for v in d.values()))} for n, d in docs.items()},
              'candidate_order': IDS, 'rows': rows}
    save(OUT / 'report_schema_candidates.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def archive():
    import requests
    import shutil
    import zipfile
    session = requests.Session()
    session.trust_env = False
    meta_path = ROOT / 'results/iter_140/preflight_a2/isles_zenodo_metadata.json'
    prior = json.loads(meta_path.read_text())
    meta = json.loads(prior['body'])
    info = next(f for f in meta['files'] if f['key'] == 'ISLES-2022.zip')
    dest = OUT / 'official/ISLES-2022.zip'
    if dest.exists():
        raise FileExistsError('기존 archive 보존')
    assert shutil.disk_usage(OUT).free > info['size'] + 2 * 1024 ** 3
    started = time.monotonic()
    url = info['links']['self']
    response = session.get(url, stream=True, timeout=(30, 120))
    response.raise_for_status()
    md5 = hashlib.md5()
    count = 0
    with dest.open('xb') as f:
        for b in response.iter_content(4 << 20):
            f.write(b)
            md5.update(b)
            count += len(b)
        f.flush()
        os.fsync(f.fileno())
    record = {'created_at': now(), 'metadata_path': str(meta_path), 'metadata_sha256': sha(meta_path),
              'url': url, 'final_url': response.url, 'status_code': response.status_code,
              'bytes': count, 'expected_bytes': info['size'], 'md5': md5.hexdigest(),
              'expected_checksum': info['checksum'], 'sha256': sha(dest),
              'elapsed_seconds': time.monotonic() - started}
    save(OUT / 'archive_download.json', record)
    assert count == info['size'] and 'md5:' + md5.hexdigest() == info['checksum']
    selected = []
    with zipfile.ZipFile(dest) as z:
        catalog = [{'name': i.filename, 'bytes': i.file_size, 'compressed_bytes': i.compress_size,
                    'crc': i.CRC} for i in z.infolist()]
        save(OUT / 'archive_catalog.json', catalog)
        for i in z.infolist():
            parts = Path(i.filename).parts
            if not (any(pid in parts for pid in IDS) or Path(i.filename).name in
                    ['dataset_description.json', 'README', 'README.md', 'participants.tsv']):
                continue
            if not (i.filename.endswith(('_dwi.nii.gz', '_dwi.json', '_msk.nii.gz')) or
                    Path(i.filename).name in ['dataset_description.json', 'README', 'README.md', 'participants.tsv']):
                continue
            assert not Path(i.filename).is_absolute() and '..' not in parts
            target = OUT / 'data' / i.filename
            assert target.resolve().is_relative_to((OUT / 'data').resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as source, target.open('xb') as f:
                shutil.copyfileobj(source, f)
            selected.append({'member': i.filename, 'path': str(target), 'bytes': i.file_size,
                             'sha256': sha(target)})
    save(OUT / 'extraction_manifest.json', {'created_at': now(), 'files': selected,
         'archive_sha256': record['sha256'], 'total_selected_bytes': sum(x['bytes'] for x in selected)})
    print(json.dumps({'archive_bytes': count, 'selected_files': len(selected),
                      'elapsed_seconds': record['elapsed_seconds']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['fetch', 'inspect', 'archive'])
    args = p.parse_args()
    if args.stage == 'fetch':
        fetch()
    elif args.stage == 'inspect':
        inspect()
    else:
        archive()
