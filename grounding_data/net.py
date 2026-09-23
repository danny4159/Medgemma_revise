"""예산 제한 다운로드 ledger와 HTTP Range seekable file.

규칙 (iter_005 계획):
- 실제 받은 bytes를 재시도 포함 누적 계상한다 (응답 본문 기준, HTTP header 제외).
- 누적 256 MiB, 네트워크 작업 시간 20분을 넘기지 않는다. 파일(또는 range 단위 작업)별 최대 2회 시도.
- Range 요청에 206이 아닌 응답(전체 응답)이 오면 즉시 중단하고 전체 archive 다운로드로 전환하지 않는다.
"""
import hashlib
import json
import os
import time

import requests

BUDGET_BYTES = 256 * 1024 * 1024
BUDGET_SECONDS = 20 * 60
MAX_ATTEMPTS = 2
TIMEOUT = 60


class BudgetExceeded(RuntimeError):
    pass


class RangeNotSupported(RuntimeError):
    pass


class DownloadLedger:
    def __init__(self, path, budget_bytes=BUDGET_BYTES, budget_seconds=BUDGET_SECONDS):
        self.path = path
        self.budget_bytes = budget_bytes
        self.budget_seconds = budget_seconds
        self.data = {"budget_bytes": budget_bytes, "budget_seconds": budget_seconds,
                     "bytes_total": 0, "seconds_total": 0.0, "n_requests": 0, "entries": []}
        if os.path.exists(path):
            self.data = json.load(open(path))
        self.session = requests.Session()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    def remaining_bytes(self):
        return self.budget_bytes - self.data["bytes_total"]

    def _check(self, expect_bytes):
        if self.data["bytes_total"] + expect_bytes > self.budget_bytes:
            raise BudgetExceeded(f"byte budget: used {self.data['bytes_total']} + {expect_bytes} > {self.budget_bytes}")
        if self.data["seconds_total"] > self.budget_seconds:
            raise BudgetExceeded(f"time budget: {self.data['seconds_total']:.0f}s > {self.budget_seconds}s")

    def get(self, url, label, rng=None, expect_bytes=0):
        """GET (선택적으로 Range). 최대 MAX_ATTEMPTS회. 모든 시도의 수신 bytes를 계상한다."""
        self._check(expect_bytes)
        last_err = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            got = 0
            ent = {"label": label, "url": url, "range": rng, "attempt": attempt, "ts": t0}
            try:
                headers = {"Range": f"bytes={rng[0]}-{rng[1]}"} if rng else {}
                with self.session.get(url, headers=headers, timeout=TIMEOUT, stream=True,
                                      allow_redirects=True) as r:
                    ent["status"] = r.status_code
                    ent["final_host"] = r.url.split("/")[2] if "://" in r.url else None
                    if rng and r.status_code != 206:
                        ent["error"] = "range_not_honored"
                        # 본문을 읽지 않고 닫는다 (전체 archive 다운로드로 전환하지 않음)
                        raise RangeNotSupported(f"{label}: status {r.status_code} for range request")
                    r.raise_for_status()
                    if rng:
                        cr = r.headers.get("Content-Range", "")
                        ent["content_range"] = cr
                        if not cr.startswith(f"bytes {rng[0]}-{rng[1]}/"):
                            ent["error"] = "unexpected_content_range"
                            raise RangeNotSupported(f"{label}: content-range {cr!r}")
                    chunks = []
                    for c in r.iter_content(1 << 16):
                        chunks.append(c)
                        got += len(c)
                        if self.data["bytes_total"] + got > self.budget_bytes:
                            ent["error"] = "byte_budget_hit_midstream"
                            raise BudgetExceeded("byte budget hit mid-stream")
                    body = b"".join(chunks)
                    if rng and len(body) != rng[1] - rng[0] + 1:
                        ent["error"] = "short_range_body"
                        raise IOError(f"{label}: got {len(body)} bytes for range {rng}")
                    ent["ok"] = True
                    return body
            except (RangeNotSupported, BudgetExceeded):
                raise
            except Exception as e:  # 네트워크 오류: 재시도 1회
                last_err = e
                ent.setdefault("error", repr(e)[:200])
            finally:
                dt = time.time() - t0
                ent["bytes"] = got
                ent["seconds"] = dt
                self.data["bytes_total"] += got
                self.data["seconds_total"] += dt
                self.data["n_requests"] += 1
                self.data["entries"].append(ent)
                self.save()
        raise IOError(f"{label}: failed after {MAX_ATTEMPTS} attempts: {last_err!r}")


class HTTPRangeFile:
    """zipfile이 읽을 수 있는 seekable read-only file. 명시적 prefetch 구간을 cache로 쓴다."""

    MIN_FETCH = 1 << 16

    def __init__(self, ledger, url, size, label, disk_cache_dir=None):
        self.ledger, self.url, self.size, self.label = ledger, url, size, label
        self.pos = 0
        self.cache = []  # (start, bytes)
        self.disk_cache_dir = disk_cache_dir  # 설정된 동안의 range만 디스크에 보관 (재실행 시 재요청 방지)

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        if whence == 0:
            self.pos = off
        elif whence == 1:
            self.pos += off
        else:
            self.pos = self.size + off
        return self.pos

    def prefetch(self, start, end):
        start, end = max(0, start), min(self.size - 1, end)
        cpath = None
        if self.disk_cache_dir:
            safe = self.label.replace(":", "_").replace("/", "_")
            cpath = os.path.join(self.disk_cache_dir, f"{safe}_{start}_{end}.bin")
            if os.path.exists(cpath) and os.path.getsize(cpath) == end - start + 1:
                self.cache.append((start, open(cpath, "rb").read()))
                return
        body = self.ledger.get(self.url, f"{self.label}[{start}-{end}]", rng=(start, end),
                               expect_bytes=end - start + 1)
        if cpath:
            with open(cpath, "wb") as f:
                f.write(body)
        self.cache.append((start, body))

    def _from_cache(self, start, n):
        for s, b in self.cache:
            if s <= start and start + n <= s + len(b):
                return b[start - s:start - s + n]
        return None

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        out = self._from_cache(self.pos, n)
        if out is None:
            end = min(self.size - 1, self.pos + max(n, self.MIN_FETCH) - 1)
            self.prefetch(self.pos, end)
            out = self._from_cache(self.pos, n)
        self.pos += len(out)
        return out

    def close(self):
        pass


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def git_blob_sha1(b):
    """HF git 저장소의 non-LFS 파일 blob id (sha1("blob <len>\\0" + content))."""
    h = hashlib.sha1()
    h.update(f"blob {len(b)}\0".encode())
    h.update(b)
    return h.hexdigest()
