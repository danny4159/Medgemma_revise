"""Parallel chunked HTTPS download with resume, for SPIDER Zenodo assets.

Uses Range requests via urllib (no external binaries). Each worker writes
disjoint byte ranges to the target file with os.pwrite, so partial progress
survives interruption: a JSON sidecar records which chunks are confirmed
written, and re-running skips those chunks after verifying the file's
current size matches the expected total.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import time
import urllib.request

CHUNK = 64 * 1024 * 1024


def _progress_path(dest):
    return dest + ".progress.json"


def _load_progress(dest, total_size):
    p = _progress_path(dest)
    if not os.path.exists(p):
        return set()
    try:
        with open(p) as f:
            d = json.load(f)
    except Exception:
        return set()
    if d.get("total_size") != total_size:
        return set()
    return set(tuple(x) for x in d.get("done", []))


def _save_progress(dest, total_size, done):
    p = _progress_path(dest)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"total_size": total_size, "done": sorted(list(done))}, f)
    os.replace(tmp, p)


def _fetch_chunk(url, start, end, max_retries=6):
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status not in (200, 206):
                    raise RuntimeError(f"unexpected status {r.status}")
                data = r.read()
            if len(data) != (end - start + 1):
                raise RuntimeError(f"short read {len(data)} != {end - start + 1}")
            return data
        except Exception as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"chunk {start}-{end} failed after {max_retries} attempts: {last_err}")


def download(url, dest, total_size, workers=8, chunk_size=CHUNK, log_every=10):
    """Download url to dest (exactly total_size bytes) using parallel Range GETs.

    Resumable: chunks already recorded as done in the progress sidecar are
    skipped, provided dest already has the correct total_size on disk.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd = os.open(dest, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        cur_size = os.fstat(fd).st_size
        if cur_size != total_size:
            os.ftruncate(fd, total_size)

        chunks = []
        start = 0
        while start < total_size:
            end = min(start + chunk_size, total_size) - 1
            chunks.append((start, end))
            start = end + 1

        done = _load_progress(dest, total_size) if cur_size == total_size else set()
        remaining = [c for c in chunks if c not in done]
        t0 = time.time()
        completed = len(done)

        def work(c):
            s, e = c
            data = _fetch_chunk(url, s, e)
            os.pwrite(fd, data, s)
            return c

        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(work, c): c for c in remaining}
            for fut in cf.as_completed(futs):
                c = fut.result()
                done.add(c)
                completed += 1
                if completed % log_every == 0 or completed == len(chunks):
                    elapsed = time.time() - t0
                    print(
                        f"[mi19_fetch] {completed}/{len(chunks)} chunks, "
                        f"{elapsed:.1f}s elapsed",
                        flush=True,
                    )
                    _save_progress(dest, total_size, done)
        _save_progress(dest, total_size, done)
    finally:
        os.close(fd)

    final_size = os.path.getsize(dest)
    if final_size != total_size:
        raise RuntimeError(f"final size mismatch: {final_size} != {total_size}")
    return final_size


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
