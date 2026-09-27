"""Parallel chunked HTTPS download with resume, for SPIDER Zenodo assets.

Uses Range requests via urllib (no external binaries). Each worker writes
disjoint byte ranges to the target file with os.pwrite, so partial progress
survives interruption: a JSON sidecar records which chunks are confirmed
written together with a sha256 of the chunk bytes actually on disk, and
re-running re-verifies each previously-recorded chunk against that hash
before skipping it (protects against silent corruption / a different run
having written stale/partial data at that offset).

Single ownership: a sidecar lock file records this process's pid and start
time; a second process refuses to run against the same dest while the
recorded pid is alive with a start time matching /proc.
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


def _lock_path(dest):
    return dest + ".lock.json"


def _proc_start_time(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().split(")")[-1].split()
        # stat fields after comm: state(0) ... starttime is field index 19 (0-based) of the
        # post-comm split, i.e. fields[19] since fields[0] is state.
        return fields[19]
    except Exception:
        return None


def acquire_lock(dest):
    """Raise RuntimeError if another live process holds the lock for dest."""
    lp = _lock_path(dest)
    if os.path.exists(lp):
        try:
            with open(lp) as f:
                prev = json.load(f)
            pid = prev.get("pid")
            start = prev.get("start_time")
            if pid is not None and _proc_start_time(pid) == start and start is not None:
                raise RuntimeError(f"dest {dest} locked by live pid {pid} (start_time {start})")
        except (json.JSONDecodeError, KeyError):
            pass
    pid = os.getpid()
    start = _proc_start_time(pid)
    tmp = lp + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"pid": pid, "start_time": start}, f)
    os.replace(tmp, lp)
    return lp


def release_lock(dest):
    lp = _lock_path(dest)
    try:
        with open(lp) as f:
            d = json.load(f)
        if d.get("pid") == os.getpid():
            os.remove(lp)
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _load_progress(dest, total_size, url):
    p = _progress_path(dest)
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            d = json.load(f)
    except Exception:
        return {}
    if d.get("total_size") != total_size or d.get("url") != url:
        return {}
    return {tuple(x["range"]): x["sha256"] for x in d.get("done", [])}


def _save_progress(dest, total_size, url, done):
    p = _progress_path(dest)
    tmp = p + ".tmp"
    rows = [{"range": list(k), "sha256": v} for k, v in sorted(done.items())]
    with open(tmp, "w") as f:
        json.dump({"total_size": total_size, "url": url, "done": rows}, f)
    os.replace(tmp, p)


def _fetch_chunk(url, start, end, max_retries=6):
    expected_len = end - start + 1
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=180) as r:
                if r.status != 206:
                    raise RuntimeError(f"expected 206 for range request, got {r.status}")
                cr = r.headers.get("Content-Range", "")
                expected_cr_prefix = f"bytes {start}-{end}/"
                if not cr.startswith(expected_cr_prefix):
                    raise RuntimeError(f"unexpected Content-Range {cr!r}, expected prefix {expected_cr_prefix!r}")
                cl = r.headers.get("Content-Length")
                if cl is not None and int(cl) != expected_len:
                    raise RuntimeError(f"Content-Length {cl} != expected {expected_len}")
                data = r.read()
            if len(data) != expected_len:
                raise RuntimeError(f"short read {len(data)} != {expected_len}")
            return data
        except Exception as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"chunk {start}-{end} failed after {max_retries} attempts: {last_err}")


def _read_and_hash(fd, start, length):
    remaining = length
    off = start
    buf = bytearray()
    while remaining > 0:
        b = os.pread(fd, min(remaining, 16 * 1024 * 1024), off)
        if not b:
            break
        buf += b
        off += len(b)
        remaining -= len(b)
    return hashlib.sha256(bytes(buf)).hexdigest(), len(buf)


def download(url, dest, total_size, workers=8, chunk_size=CHUNK, log_every=10):
    """Download url to dest (exactly total_size bytes) using parallel Range GETs.

    Resumable: chunks already recorded as done are re-verified (by hashing
    the bytes currently on disk at that offset) before being skipped.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    acquire_lock(dest)
    try:
        fd = os.open(dest, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            cur_size = os.fstat(fd).st_size
            if cur_size != total_size:
                os.ftruncate(fd, total_size)
                cur_size = total_size

            chunks = []
            start = 0
            while start < total_size:
                end = min(start + chunk_size, total_size) - 1
                chunks.append((start, end))
                start = end + 1

            recorded = _load_progress(dest, total_size, url)
            done = {}
            for c, expected_hash in recorded.items():
                actual_hash, n = _read_and_hash(fd, c[0], c[1] - c[0] + 1)
                if n == (c[1] - c[0] + 1) and actual_hash == expected_hash:
                    done[c] = expected_hash
            remaining = [c for c in chunks if c not in done]
            t0 = time.time()
            completed = len(done)

            def work(c):
                s, e = c
                data = _fetch_chunk(url, s, e)
                written = os.pwrite(fd, data, s)
                if written != len(data):
                    raise RuntimeError(f"short pwrite {written} != {len(data)} at offset {s}")
                h = hashlib.sha256(data).hexdigest()
                return c, h

            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(work, c): c for c in remaining}
                for fut in cf.as_completed(futs):
                    c, h = fut.result()
                    done[c] = h
                    completed += 1
                    if completed % log_every == 0 or completed == len(chunks):
                        elapsed = time.time() - t0
                        print(
                            f"[mi19_fetch] {completed}/{len(chunks)} chunks, "
                            f"{elapsed:.1f}s elapsed",
                            flush=True,
                        )
                        _save_progress(dest, total_size, url, done)
            _save_progress(dest, total_size, url, done)
        finally:
            os.close(fd)
    finally:
        release_lock(dest)

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
