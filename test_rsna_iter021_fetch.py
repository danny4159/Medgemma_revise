"""iter_021: mi19_fetch downloader 검증. Content-Range 강제, 손상 chunk 재검출,
short pwrite 방어(모의), 단일 소유권 lock을 실제 로컬 HTTP 서버로 검사한다.
결과는 results/iter_021/tests/fixtures_fetch.json에 기록한다.
"""
import hashlib
import http.server
import json
import os
import socketserver
import threading
import time

from rsna_diag import mi19_fetch as F

RESULT_DIR = "results/iter_021/tests"


def _make_body(n, seed=0):
    import random
    r = random.Random(seed)
    return bytes(r.randrange(256) for _ in range(n))


class RangeHandler(http.server.BaseHTTPRequestHandler):
    body = b""
    mode = "ok"  # ok | bad_content_range | short_body | plain200 | flaky_once

    _flaky_seen = set()

    def log_message(self, *a):
        pass

    def do_GET(self):
        total = len(self.body)
        rng = self.headers.get("Range")
        if rng is None:
            self.send_response(200)
            self.send_header("Content-Length", str(total))
            self.end_headers()
            self.wfile.write(self.body)
            return
        assert rng.startswith("bytes=")
        s, e = rng[6:].split("-")
        s, e = int(s), int(e)
        chunk = self.body[s:e + 1]
        if self.mode == "plain200":
            self.send_response(200)
            self.send_header("Content-Length", str(total))
            self.end_headers()
            self.wfile.write(self.body)
            return
        if self.mode == "bad_content_range":
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {s}-{e - 1}/{total}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
            return
        if self.mode == "short_body":
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {s}-{e}/{total}")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk[:-1])
            return
        if self.mode == "flaky_once":
            key = (s, e)
            if key not in RangeHandler._flaky_seen:
                RangeHandler._flaky_seen.add(key)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {s}-{e}/{total}")
                self.send_header("Content-Length", str(len(chunk) - 1))
                self.end_headers()
                self.wfile.write(chunk[:-1])
                return
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {s}-{e}/{total}")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


def _serve(body, mode):
    RangeHandler.body = body
    RangeHandler.mode = mode
    RangeHandler._flaky_seen = set()
    httpd = socketserver.TCPServer(("127.0.0.1", 0), RangeHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, f"http://127.0.0.1:{port}/f"


def run():
    os.makedirs(RESULT_DIR, exist_ok=True)
    results = []
    orig_sleep = time.sleep
    time.sleep = lambda s: None

    def check(name, cond, detail=""):
        results.append({"name": name, "pass": bool(cond), "detail": detail})

    # 1. ok path, small chunk_size to force many chunks
    body = _make_body(300)
    httpd, url = _serve(body, "ok")
    dest = "/tmp/mi19_fetch_test_ok.bin" if False else "results/iter_021/tests/_fetch_ok.bin"
    for p in (dest, dest + ".progress.json", dest + ".lock.json"):
        if os.path.exists(p):
            os.remove(p)
    final = F.download(url, dest, len(body), workers=3, chunk_size=100, log_every=1000)
    with open(dest, "rb") as f:
        got = f.read()
    check("ok_download_matches", got == body, f"len={len(got)}")
    check("ok_final_size", final == len(body))
    httpd.shutdown()

    # 2. resume: truncate progress to drop one chunk's record, verify re-fetch works
    with open(dest + ".progress.json") as f:
        prog = json.load(f)
    assert len(prog["done"]) == 3
    prog["done"] = prog["done"][:-1]
    with open(dest + ".progress.json", "w") as f:
        json.dump(prog, f)
    httpd, url = _serve(body, "ok")
    final2 = F.download(url, dest, len(body), workers=3, chunk_size=100, log_every=1000)
    with open(dest, "rb") as f:
        got2 = f.read()
    check("resume_after_progress_truncate", got2 == body)
    httpd.shutdown()

    # 3. corrupted on-disk bytes for a recorded-done chunk must be re-fetched, not trusted
    with open(dest, "r+b") as f:
        f.seek(0)
        f.write(b"\x00" * 50)
    httpd, url = _serve(body, "ok")
    final3 = F.download(url, dest, len(body), workers=3, chunk_size=100, log_every=1000)
    with open(dest, "rb") as f:
        got3 = f.read()
    check("corrupted_chunk_redetected_and_refetched", got3 == body)
    httpd.shutdown()

    # 4. bad Content-Range must raise, not silently accept
    dest4 = "results/iter_021/tests/_fetch_badrange.bin"
    for p in (dest4, dest4 + ".progress.json", dest4 + ".lock.json"):
        if os.path.exists(p):
            os.remove(p)
    httpd, url = _serve(body, "bad_content_range")
    raised = False
    try:
        F.download(url, dest4, len(body), workers=1, chunk_size=100, log_every=1000)
    except RuntimeError:
        raised = True
    check("bad_content_range_rejected", raised)
    httpd.shutdown()

    # 5. short body must raise
    dest5 = "results/iter_021/tests/_fetch_short.bin"
    for p in (dest5, dest5 + ".progress.json", dest5 + ".lock.json"):
        if os.path.exists(p):
            os.remove(p)
    httpd, url = _serve(body, "short_body")
    raised = False
    try:
        F.download(url, dest5, len(body), workers=1, chunk_size=100, log_every=1000)
    except RuntimeError:
        raised = True
    check("short_body_rejected", raised)
    httpd.shutdown()

    # 6. plain 200 in range path must raise (no silent accept as range chunk)
    dest6 = "results/iter_021/tests/_fetch_200.bin"
    for p in (dest6, dest6 + ".progress.json", dest6 + ".lock.json"):
        if os.path.exists(p):
            os.remove(p)
    httpd, url = _serve(body, "plain200")
    raised = False
    try:
        F.download(url, dest6, len(body), workers=1, chunk_size=100, log_every=1000)
    except RuntimeError:
        raised = True
    check("plain_200_in_range_path_rejected", raised)
    httpd.shutdown()

    # 7. transient failure (short read once) is retried and eventually succeeds
    dest7 = "results/iter_021/tests/_fetch_flaky.bin"
    for p in (dest7, dest7 + ".progress.json", dest7 + ".lock.json"):
        if os.path.exists(p):
            os.remove(p)
    httpd, url = _serve(body, "flaky_once")
    F.download(url, dest7, len(body), workers=1, chunk_size=100, log_every=1000)
    with open(dest7, "rb") as f:
        got7 = f.read()
    check("flaky_retry_succeeds", got7 == body)
    httpd.shutdown()

    # 8. single ownership lock: second acquire on same dest while first "process" alive must fail.
    # Simulate liveness by pointing the lock at this test process's own pid (which is alive).
    dest8 = "results/iter_021/tests/_fetch_lock.bin"
    lp = dest8 + ".lock.json"
    if os.path.exists(lp):
        os.remove(lp)
    my_pid = os.getpid()
    start = F._proc_start_time(my_pid)
    with open(lp, "w") as f:
        json.dump({"pid": my_pid, "start_time": start}, f)
    raised = False
    try:
        F.acquire_lock(dest8)
    except RuntimeError:
        raised = True
    check("lock_rejects_live_owner", raised)
    os.remove(lp)

    # 9. stale lock (pid alive but start_time mismatch => different process reused pid) is not trusted
    with open(lp, "w") as f:
        json.dump({"pid": my_pid, "start_time": "not-a-real-starttime"}, f)
    raised = False
    try:
        F.acquire_lock(dest8)
        F.release_lock(dest8)
    except RuntimeError:
        raised = True
    check("stale_lock_start_time_mismatch_not_trusted", not raised)

    # 10. sha256_of / md5_of correctness
    tmp = "results/iter_021/tests/_hashtest.bin"
    with open(tmp, "wb") as f:
        f.write(body)
    check("sha256_of_matches", F.sha256_of(tmp) == hashlib.sha256(body).hexdigest())
    check("md5_of_matches", F.md5_of(tmp) == hashlib.md5(body).hexdigest())

    time.sleep = orig_sleep
    n_pass = sum(1 for r in results if r["pass"])
    out = {"n_pass": n_pass, "n_total": len(results), "results": results}
    with open(f"{RESULT_DIR}/fixtures_fetch.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    assert n_pass == len(results), f"{n_pass}/{len(results)} passed"


if __name__ == "__main__":
    run()
