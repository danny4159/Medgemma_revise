"""iter_054: MediConfusion figure 확보. 공식 download.py(NCBI oa_package tar.gz; 2026-10 현재 404)와 달리
PMC Open Access AWS 공개 버킷(pmc-oa-opendata)에서 image_dict의 file_name figure 하나씩만 받는다.
- 기존 파일 덮어쓰기 금지(xb), basename만 허용(경로 이탈 거부), 전송 MD5(ETag/media_urls)와 크기 검증.
- 출력: results/iter_054/data/images/<local>.jpg, results/iter_054/data/fetch_manifest.json
"""
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SRC = "results/iter_054/source/data__image_dict.json"
OUT = "results/iter_054/data"
S3 = "https://pmc-oa-opendata.s3.amazonaws.com"


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read(), dict(r.headers)


def pmcid(dlink):
    m = re.search(r"/(PMC\d+)\.tar\.gz$", dlink)
    if not m:
        raise ValueError(dlink)
    return m.group(1)


def article(pmc):
    """S3에서 PMC 문서 prefix의 object 목록과 json 메타를 읽는다."""
    xml, _ = get(f"{S3}/?prefix={pmc}.&max-keys=1000")
    keys = re.findall(r"<Key>(.*?)</Key>.*?<ETag>&quot;(.*?)&quot;</ETag>.*?<Size>(\d+)</Size>", xml.decode(), flags=re.S)
    return {k: (e, int(s)) for k, e, s in keys}


def fetch_one(item):
    path, v = item
    local, fname, pmc = v["local"], v["file_name"], pmcid(v["dlink"])
    if os.path.basename(fname) != fname or fname.startswith("."):
        raise ValueError(f"unsafe file_name {fname}")
    keys = article(pmc)
    cand = [k for k in keys if k.endswith("/" + fname)]
    if len(cand) != 1:
        return {"roco_path": path, "local": local, "pmc": pmc, "file_name": fname, "status": "not_found", "candidates": cand}
    key = cand[0]
    etag, size = keys[key]
    data, hdr = get(f"{S3}/{urllib.parse.quote(key)}")
    md5 = hashlib.md5(data).hexdigest()
    ok = (len(data) == size) and (md5 == etag or "-" in etag)
    dst = os.path.join(OUT, "images", f"{local}.jpg")
    rec = {"roco_path": path, "local": local, "pmc": pmc, "file_name": fname, "s3_key": key, "etag": etag, "size": size,
           "md5": md5, "sha256": hashlib.sha256(data).hexdigest(), "status": "ok" if ok else "checksum_mismatch"}
    if ok:
        with open(dst, "xb") as f:
            f.write(data)
        rec["saved"] = dst
    return rec


def main():
    d = json.load(open(SRC))
    os.makedirs(os.path.join(OUT, "images"), exist_ok=True)
    items = sorted(d.items(), key=lambda kv: kv[1]["local"])
    locals_ = [v["local"] for _, v in items]
    if len(set(locals_)) != len(locals_):
        sys.exit("duplicate local ids in image_dict")
    todo = [it for it in items if not os.path.exists(os.path.join(OUT, "images", f"{it[1]['local']}.jpg"))]
    print("to fetch", len(todo), "of", len(items))
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(fetch_one, todo))
    mf = os.path.join(OUT, "fetch_manifest.json")
    prev = json.load(open(mf)) if os.path.exists(mf) else []
    json.dump(prev + res, open(mf + ".tmp", "w"), indent=1)
    os.replace(mf + ".tmp", mf)
    from collections import Counter
    print(Counter(r["status"] for r in res))


if __name__ == "__main__":
    main()
