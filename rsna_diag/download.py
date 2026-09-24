"""RSNA 2018 공식 배포 파일을 전체 다운로드한다 (iter_009).

- 비공식 미러로 대체하지 않는다. 재개는 .part 크기에서 Range로 이어받되, 완료 시 전체 SHA256과
  ETag/Content-Length를 sidecar json에 기록한다. sidecar가 현재 파일 크기/해시와 다르면 재다운로드한다.
- 예산(bytes/time) 상한은 없다. 실제 크기는 HEAD Content-Length로 확인하고 디스크 여유를 검사한다.
"""
import hashlib
import json
import os
import shutil
import sys
import time

import requests

BASE = "https://s3.amazonaws.com/east1.public.rsna.org/AI/2018/"
FILES = [
    "pneumonia-challenge-annotations-adjudicated-kaggle_2018.json",
    "pneumonia-challenge-dataset-mappings_2018.json",
    "pneumonia-challenge-dataset-adjudicated-kaggle_2018.zip",
]
TIMEOUT = 60
MAX_RETRY = 5


def sha256_file(path, bufsize=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fetch(name, out_dir):
    url = BASE + name
    dst = os.path.join(out_dir, name)
    side = dst + ".provenance.json"
    head = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
    head.raise_for_status()
    size = int(head.headers["Content-Length"])
    etag = head.headers.get("ETag")
    if head.headers.get("Accept-Ranges") != "bytes":
        print(f"[warn] {name}: Accept-Ranges 미지원, 재개 불가", flush=True)
    if os.path.exists(dst) and os.path.exists(side):
        p = json.load(open(side))
        if (os.path.getsize(dst) == size and p.get("size") == size and p.get("etag") == etag
                and p.get("sha256") == sha256_file(dst)):
            print(f"[ok-cached] {name}", flush=True)
            return p
    free = shutil.disk_usage(out_dir).free
    if free < size * 2:
        raise RuntimeError(f"disk free {free} < 2x size {size}")
    part = dst + ".part"
    h_started = time.time()
    n_req = 0
    for attempt in range(MAX_RETRY):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have > size:
            os.remove(part)
            have = 0
        if have == size:
            break
        hdr = {"Range": f"bytes={have}-"} if have else {}
        try:
            n_req += 1
            with requests.get(url, headers=hdr, stream=True, timeout=TIMEOUT) as r:
                if have and r.status_code != 206:
                    raise RuntimeError(f"resume requires 206, got {r.status_code}")
                r.raise_for_status()
                if r.headers.get("ETag") != etag:
                    raise RuntimeError("ETag changed during download")
                with open(part, "ab") as f:
                    last = time.time()
                    for c in r.iter_content(1 << 20):
                        f.write(c)
                        if time.time() - last > 30:
                            print(f"  {name}: {f.tell()/1e6:.0f}/{size/1e6:.0f} MB", flush=True)
                            last = time.time()
        except Exception as e:
            print(f"[retry {attempt+1}] {name}: {e!r}", flush=True)
            time.sleep(3)
    if os.path.getsize(part) != size:
        raise RuntimeError(f"{name}: incomplete {os.path.getsize(part)}/{size}")
    os.replace(part, dst)
    prov = {"url": url, "size": size, "etag": etag, "sha256": sha256_file(dst),
            "last_modified": head.headers.get("Last-Modified"),
            "downloaded_at_epoch": time.time(), "seconds": time.time() - h_started, "n_requests": n_req,
            "accept_ranges": head.headers.get("Accept-Ranges")}
    json.dump(prov, open(side, "w"), indent=1)
    print(f"[done] {name} {size} bytes sha256={prov['sha256']}", flush=True)
    return prov


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for n in FILES:
        fetch(n, out)
