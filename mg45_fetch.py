"""iter_045: MedGrounder 공식 코드(고정 SHA)를 results/iter_045/external/ 에 받아 digest를 기록한다.

기존 파일은 덮어쓰지 않는다. 가중치(Google Drive)는 mg45_weights.py 에서 따로 받는다.
"""
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
import zipfile

SHA = "a0aad98d67018838fe160acbe1f7c3851fddeacc"
REPO = "aehrc/MedGrounder"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "iter_045", "external")
CODE = os.path.join(OUT, "MedGrounder")


def main():
    if os.path.exists(CODE):
        print("exists, not overwriting:", CODE)
        return
    os.makedirs(OUT, exist_ok=True)
    url = f"https://codeload.github.com/{REPO}/zip/{SHA}"
    t = time.time()
    data = urllib.request.urlopen(url, timeout=300).read()
    digest = hashlib.sha256(data).hexdigest()
    zf = zipfile.ZipFile(io.BytesIO(data))
    root = os.path.realpath(OUT)
    tmp = os.path.join(OUT, "_extract_tmp")
    os.makedirs(tmp)
    files = {}
    for info in zf.infolist():
        dest = os.path.realpath(os.path.join(tmp, info.filename))
        if not dest.startswith(os.path.realpath(tmp) + os.sep) and dest != os.path.realpath(tmp):
            raise RuntimeError("path escape: " + info.filename)
        if info.is_dir():
            os.makedirs(dest, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        b = zf.read(info)
        with open(dest, "wb") as f:
            f.write(b)
        files[info.filename.split("/", 1)[1]] = hashlib.sha256(b).hexdigest()
    os.rename(os.path.join(tmp, f"MedGrounder-{SHA}"), CODE)
    os.rmdir(tmp)
    man = {"repo": f"https://github.com/{REPO}", "sha": SHA, "archive_url": url, "archive_sha256": digest,
           "n_files": len(files), "files_sha256": files, "elapsed_s": round(time.time() - t, 2)}
    with open(os.path.join(OUT, "code_manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    print("ok", len(files), "files", digest)


if __name__ == "__main__":
    sys.exit(main())
