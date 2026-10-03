"""iter_056 MSD Task01_BrainTumour 공식 archive 다운로드(재개 가능) + md5 검증.

URL/md5는 MONAI DecathlonDataset 소스(monai/apps/datasets.py)의 값. 같은 ETag/크기가 아니면 중단한다.
사용: python msd56_fetch.py [--budget-s 540]   (시간 내 끝나지 않으면 같은 명령으로 재개)
"""
import argparse
import hashlib
import json
import os
import time
import urllib.request

URL = "https://msd-for-monai.s3-us-west-2.amazonaws.com/Task01_BrainTumour.tar"
MD5 = "240a19d752f0d9e9101544901065d872"
SIZE = 7608266240
ETAG = '"dfd1b5a5df62dadb48cad3d347148c70-907"'
OUT = "results/iter_056/source"
TAR = f"{OUT}/Task01_BrainTumour.tar"


def md5_file(path, bs=1 << 24):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(bs)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-s", type=float, default=540)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    have = os.path.getsize(TAR) if os.path.exists(TAR) else 0
    t0 = time.time()
    if have < SIZE:
        req = urllib.request.Request(URL, headers={"Range": f"bytes={have}-", "If-Match": ETAG})
        resp = urllib.request.urlopen(req)
        if resp.status not in (200, 206):
            raise SystemExit(f"unexpected status {resp.status}")
        if have and resp.status != 206:
            raise SystemExit("server ignored Range")
        with open(TAR, "ab") as f:
            while time.time() - t0 < a.budget_s:
                b = resp.read(1 << 22)
                if not b:
                    break
                f.write(b)
        have = os.path.getsize(TAR)
    print(f"bytes {have}/{SIZE} elapsed {time.time()-t0:.0f}s", flush=True)
    if have == SIZE:
        m = md5_file(TAR)
        ok = m == MD5
        json.dump({"url": URL, "etag": ETAG, "size": SIZE, "md5_expected": MD5, "md5_actual": m, "ok": ok,
                   "t": time.strftime("%Y-%m-%dT%H:%M:%S")}, open(f"{OUT}/fetch_verify.json", "w"), indent=1)
        print("md5", m, "OK" if ok else "MISMATCH")
        if not ok:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
