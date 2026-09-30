"""iter_039 PadChest-GR 본 영상 분할 zip(.001-.037) 재개형 다운로드.

- 접근 정보는 results/datasets/padchest_gr/ACCESS_PRIVATE.md 에서만 읽는다. URL/token은 로그·결과에 쓰지 않는다.
- PROPFIND로 파일별 size/etag를 받아 private 매니페스트에 기록하고, Range 재개 + 크기·Content-Range 검증을 한다.
- 단일 소유권: results/datasets/padchest_gr/images/fetch.lock (O_EXCL, pid 기록; 살아있는 pid면 거부).
- 과거 검사 영상(progression_prior_studies)은 받지 않는다.
"""
import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = "results/datasets/padchest_gr"
DEST = os.path.join(ROOT, "images")
EXPECT_TOTAL = 38531867282
PARTS = [f"PadChest_GR.zip.{i:03d}" for i in range(1, 38)]
SUBDIR = "Padchest_GR_files"


def access():
    txt = open(os.path.join(ROOT, "ACCESS_PRIVATE.md")).read()
    share = re.search(r"https://b2drop\.bsc\.es/nextcloud/s/([A-Za-z0-9_-]+)", txt).group(1)
    base = re.search(r"WebDAV root: (\S+)", txt).group(1).rstrip("/")
    return share, base


def acquire_lock():
    os.makedirs(DEST, exist_ok=True)
    p = os.path.join(DEST, "fetch.lock")
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            pid = int(open(p).read().strip())
            os.kill(pid, 0)
            print("another fetch owns the lock", pid)
            sys.exit(3)
        except (ValueError, ProcessLookupError):
            os.unlink(p)
            return acquire_lock()
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return p


def propfind(sess, base):
    r = sess.request("PROPFIND", f"{base}/{SUBDIR}/", headers={"Depth": "1"}, timeout=60)
    r.raise_for_status()
    ns = {"d": "DAV:"}
    out = {}
    for resp in ET.fromstring(r.content).findall("d:response", ns):
        href = resp.find("d:href", ns).text
        name = os.path.basename(href.rstrip("/"))
        ps = resp.find("d:propstat/d:prop", ns)
        sz = ps.find("d:getcontentlength", ns)
        et = ps.find("d:getetag", ns)
        if sz is not None:
            out[name] = {"size": int(sz.text), "etag": et.text if et is not None else None}
    return out


def fetch(sess, base, name, meta, log):
    path = os.path.join(DEST, name)
    part = path + ".part"
    size = meta["size"]
    if os.path.exists(path) and os.path.getsize(path) == size:
        return name, "exists"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    for attempt in range(20):
        try:
            hdr = {"Range": f"bytes={have}-"} if have else {}
            with sess.get(f"{base}/{SUBDIR}/{name}", headers=hdr, stream=True, timeout=(30, 120)) as r:
                if have:
                    if r.status_code != 206 or not r.headers.get("Content-Range", "").startswith(f"bytes {have}-"):
                        have = 0
                        if os.path.exists(part):
                            os.unlink(part)
                        continue
                    if not r.headers["Content-Range"].endswith(f"/{size}"):
                        raise RuntimeError("Content-Range total mismatch")
                else:
                    r.raise_for_status()
                with open(part, "ab" if have else "wb") as f:
                    for chunk in r.iter_content(1 << 22):
                        f.write(chunk)
                        have += len(chunk)
            if have == size:
                os.replace(part, path)
                return name, "ok"
            have = os.path.getsize(part)
        except (requests.RequestException, RuntimeError) as e:
            log(f"{name} attempt{attempt} {type(e).__name__}")
            time.sleep(min(60, 2 ** attempt))
            have = os.path.getsize(part) if os.path.exists(part) else 0
    return name, "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    lock = acquire_lock()
    logf = open(os.path.join(DEST, "fetch.log"), "a")

    def log(m):
        logf.write(f"{time.strftime('%F %T')} {m}\n")
        logf.flush()

    try:
        share, base = access()
        sess = requests.Session()
        sess.auth = (share, "")
        listing = propfind(sess, base)
        meta = {n: listing[n] for n in PARTS}
        tot = sum(m["size"] for m in meta.values())
        assert tot == EXPECT_TOTAL, (tot, EXPECT_TOTAL)
        json.dump(meta, open(os.path.join(DEST, "server_listing_private.json"), "w"), indent=1)
        st = os.statvfs(DEST)
        free = st.f_bavail * st.f_frsize
        log(f"listing ok total={tot} free={free}")
        assert free > tot * 1.2, "disk"
        t0 = time.time()
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(fetch, sess, base, n, meta[n], log) for n in PARTS]
            res = [f.result() for f in futs]
        log(f"done {res.count(res[0])} elapsed={time.time()-t0:.0f}s")
        fails = [n for n, s in res if s == "failed"]
        json.dump({"results": res, "failed": fails, "elapsed_s": time.time() - t0},
                  open(os.path.join(DEST, "fetch_result.json"), "w"), indent=1)
        print("failed:", fails)
        sys.exit(1 if fails else 0)
    finally:
        os.unlink(lock)


if __name__ == "__main__":
    main()
