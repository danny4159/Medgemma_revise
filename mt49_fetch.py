"""iter_049: MedThinkVQA 공식 자료 확보 (revision 고정, sha256 검증, 원자적 저장).

- HF dataset revision, GitHub commit을 고정하고 파일 목록·LFS oid를 results/iter_049/acq/ 에 보존한다.
- train.jsonl 만 받는다 (test.jsonl/test.parquet 은 열지 않는다).
- 파일은 .part 에 받은 뒤 sha256(LFS oid가 있으면 oid, 없으면 기록만) 검증 후 rename. 기존 파일은 덮어쓰지 않는다.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

HF = "bio-nlp-umass/MedThinkVQA"
HF_REV = "5555b80e167c4796efab92fe709fb05914077dc0"
GH = "benluwang/MedThinkVQA"
GH_REV = "efa12d09024dbe458782059bc7a2d9fa41d28821"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "iter_049")
UA = {"User-Agent": "mt49-fetch/1.0"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.load(r)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(url, dest, expect_sha=None, expect_size=None, retries=4):
    """공식 URL -> dest. dest가 이미 있으면 검증만 하고 재사용(덮어쓰지 않음)."""
    if os.path.exists(dest):
        s = sha256_file(dest)
        if expect_sha and s != expect_sha:
            raise RuntimeError(f"existing file hash mismatch {dest}")
        return {"path": dest, "sha256": s, "size": os.path.getsize(dest), "reused": True}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + f".part.{os.getpid()}"
    last = None
    for k in range(retries):
        try:
            h = hashlib.sha256()
            n = 0
            t0 = time.time()
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
                final_url = r.geturl()
                etag = r.headers.get("ETag")
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
                    h.update(b)
                    n += len(b)
            if expect_size is not None and n != expect_size:
                raise RuntimeError(f"size {n} != {expect_size}")
            if expect_sha and h.hexdigest() != expect_sha:
                raise RuntimeError("sha256 mismatch")
            os.link(part, dest)  # 이미 존재하면 FileExistsError -> 덮어쓰기 방지
            os.unlink(part)
            return {"path": dest, "sha256": h.hexdigest(), "size": n, "url": url, "final_url": final_url,
                    "etag": etag, "seconds": time.time() - t0, "reused": False}
        except FileExistsError:
            os.unlink(part)
            return {"path": dest, "sha256": sha256_file(dest), "reused": True}
        except Exception as e:  # noqa
            last = repr(e)
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def main():
    acq = os.path.join(OUT, "acq")
    os.makedirs(acq, exist_ok=True)
    log = {"hf_repo": HF, "hf_revision": HF_REV, "gh_repo": GH, "gh_revision": GH_REV, "files": []}
    info = get_json(f"https://huggingface.co/api/datasets/{HF}/revision/{HF_REV}")
    log["hf_card_license"] = (info.get("cardData") or {}).get("license")
    log["hf_lastModified"] = info.get("lastModified")
    top = get_json(f"https://huggingface.co/api/datasets/{HF}/tree/{HF_REV}")
    json.dump(top, open(os.path.join(acq, "hf_top_tree.json"), "w"), indent=1)
    meta = {x["path"]: x for x in top if x["type"] == "file"}
    tr = meta["train.jsonl"]
    assert tr["lfs"]["oid"] == "7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a"
    for name in ["README.md", ".gitattributes"]:
        log["files"].append(fetch(f"https://huggingface.co/datasets/{HF}/resolve/{HF_REV}/{name}",
                                  os.path.join(acq, "hf_" + name.lstrip(".")), None, meta[name]["size"]))
    log["files"].append(fetch(f"https://huggingface.co/datasets/{HF}/resolve/{HF_REV}/train.jsonl",
                              os.path.join(OUT, "raw", "train.jsonl"), tr["lfs"]["oid"], tr["size"]))
    gh_tree = get_json(f"https://api.github.com/repos/{GH}/git/trees/{GH_REV}?recursive=1")
    json.dump(gh_tree, open(os.path.join(acq, "gh_tree.json"), "w"), indent=1)
    for x in gh_tree["tree"]:
        p = x["path"]
        if x["type"] == "blob" and (p in ("LICENSE", "README.md") or p.startswith("model/")
                                    or p.startswith("data_processing/") or p.startswith("tools/")):
            r = fetch(f"https://raw.githubusercontent.com/{GH}/{GH_REV}/{p}",
                      os.path.join(OUT, "code_gh", p), None, x["size"])
            r["git_blob_sha"] = x["sha"]
            log["files"].append(r)
    json.dump(log, open(os.path.join(acq, "acquisition_log.json"), "w"), indent=1)
    print("ok", len(log["files"]))


if __name__ == "__main__":
    sys.exit(main())
