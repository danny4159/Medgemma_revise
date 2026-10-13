"""공식 ZIP의 HTTP Range로 고정 후보 파일만 반입한다. 원 ZIP 전체 MD5 검증과 구분한다."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import struct
import time
import zipfile
import zlib
import requests
from i141_preflight import ROOT, OUT, IDS, now, save, sha

URL = 'https://zenodo.org/api/records/7960856/files/ISLES-2022.zip/content'
SIZE = 1692717470


def get_range(start, end):
    session = requests.Session()
    session.trust_env = False
    started = time.monotonic()
    r = session.get(URL, headers={'Range': f'bytes={start}-{end}'}, timeout=(30, 120), stream=True)
    assert r.status_code == 206, 'Range 서버 응답 오류: ' + str(r.status_code)
    assert r.headers.get('Content-Range') == f'bytes {start}-{end}/{SIZE}'
    data = r.content
    assert len(data) == end - start + 1
    record = {'requested_at': now(), 'url': URL, 'final_url': r.url,
              'range': [start, end], 'content_range': r.headers['Content-Range'],
              'status_code': r.status_code, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'etag': r.headers.get('ETag'), 'last_modified': r.headers.get('Last-Modified'),
              'elapsed_seconds': time.monotonic() - started}
    return data, record


def main():
    tail = (OUT / 'archive_tail.bin').read_bytes()
    end = struct.unpack('<4s4H2LH', tail[-22:])
    assert end[0] == b'PK\x05\x06' and end[1:3] == (0, 0) and end[-1] == 0
    count, central_size, central_offset = end[4:7]
    catalog, rec = get_range(central_offset, central_offset + central_size - 1)
    patched_end = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, count, count, central_size, 0, 0)
    with zipfile.ZipFile(io.BytesIO(catalog + patched_end)) as z:
        infos = z.infolist()
    save(OUT / 'range_catalog.json', {'created_at': now(), 'request': rec,
         'entries': [{'name': x.filename, 'bytes': x.file_size, 'compressed_bytes': x.compress_size,
                      'compression': x.compress_type, 'crc32': x.CRC, 'header_offset': x.header_offset}
                     for x in infos]})
    picked = []
    for x in infos:
        parts = Path(x.filename).parts
        selected_patient = any(pid in parts for pid in IDS)
        metadata = Path(x.filename).name in ['dataset_description.json', 'README', 'README.md', 'participants.tsv']
        if (selected_patient and x.filename.endswith(('_dwi.nii.gz', '_dwi.json', '_msk.nii.gz'))) or metadata:
            assert not Path(x.filename).is_absolute() and '..' not in parts
            picked.append(x)
    save(OUT / 'selected_members.json', {'created_at': now(), 'n_members': len(picked),
         'compressed_bytes': sum(x.compress_size for x in picked), 'uncompressed_bytes': sum(x.file_size for x in picked),
         'files': [x.filename for x in picked]})
    print(json.dumps({'selected_members': len(picked), 'compressed_bytes': sum(x.compress_size for x in picked)},ensure_ascii=False), flush=True)
    assert all(any(pid in x.filename and x.filename.endswith('_dwi.nii.gz') for x in picked) for pid in IDS)
    destination = OUT / 'data_selected'
    assert not destination.exists()
    destination.mkdir()
    ledger = OUT / 'range_download_ledger.jsonl'
    started = time.monotonic()

    def download(x):
        header, hrec = get_range(x.header_offset, x.header_offset + 29)
        h = struct.unpack('<4s5H3L2H', header)
        assert h[0] == b'PK\x03\x04' and not h[2] & 1 and h[3] == x.compress_type
        filename_len, extra_len = h[-2:]
        payload, prec = get_range(x.header_offset + 30, x.header_offset + 29 + filename_len + extra_len + x.compress_size)
        assert payload[:filename_len].decode('utf-8' if h[2] & 2048 else 'cp437') == x.filename
        compressed = payload[filename_len + extra_len:]
        assert x.compress_type in [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED]
        decoded = zlib.decompress(compressed, -15) if x.compress_type == zipfile.ZIP_DEFLATED else compressed
        assert len(decoded) == x.file_size and zlib.crc32(decoded) == x.CRC
        assert (hrec['etag'], hrec['last_modified']) == (rec['etag'], rec['last_modified'])
        assert (prec['etag'], prec['last_modified']) == (rec['etag'], rec['last_modified'])
        path = destination / x.filename
        assert path.resolve().is_relative_to(destination.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f:
            f.write(decoded)
        return {'member': x.filename, 'path': str(path), 'bytes': len(decoded), 'sha256': sha(path),
                'crc32_verified': True, 'crc32': x.CRC, 'requests': [hrec, prec]}

    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool, ledger.open('x') as f:
        for row in pool.map(download, picked):
            rows.append(row)
            f.write(json.dumps(row) + '\n')
            f.flush()
    save(OUT / 'selected_download_complete.json', {'created_at': now(), 'elapsed_seconds': time.monotonic()-started,
         'files': rows, 'catalog_sha256': sha(OUT / 'range_catalog.json'), 'ledger_sha256': sha(ledger),
         'source_archive_bytes': SIZE, 'source_archive_expected_md5': '302ee280373cdd5c190ab763d72a7a50',
         'full_archive_md5_verified': False, 'selected_members_crc32_verified': True,
         'downloaded_range_bytes': rec['bytes'] + sum(r['bytes'] for row in rows for r in row['requests'])})
    print(json.dumps({'download_complete': len(rows), 'elapsed_seconds': time.monotonic()-started}))


if __name__ == '__main__':
    main()
