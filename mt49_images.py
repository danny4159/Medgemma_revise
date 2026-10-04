"""iter_049: 적격 train case의 전체 영상만 공식 HF revision에서 선택 다운로드하고 검증한다.

- 입력: audit_v2/eligible_cases.jsonl (train 적격 case만; test 경로는 열거하지 않는다)
- case 디렉터리 listing(공식 tree API)으로 객체 oid 확보 -> 받은 bytes 의 git blob sha1(비LFS) 또는 sha256(LFS) 검증
- 각 영상: 파일 sha256, 크기, PIL decode 성공 여부, mode/size, decode pixel sha256 기록. 경로 이탈 거부.
- 결과: images/ (git 제외 대형 자산), image_manifest.json. 기존 파일은 덮어쓰지 않는다.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image

from mt49_fetch import HF, HF_REV, OUT, UA, fetch, get_json

AUD = os.path.join(OUT, "audit_v2")
IMG = os.path.join(OUT, "images")


def safe_rel(p):
    if p.startswith("/") or ".." in p.split("/") or "\\" in p or not p.startswith("images/case"):
        raise ValueError("unsafe path " + p)
    return p


def git_blob_sha1(path):
    n = os.path.getsize(path)
    h = hashlib.sha1(b"blob %d\0" % n)
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def list_case(case_dir):
    u = f"https://huggingface.co/api/datasets/{HF}/tree/{HF_REV}/" + urllib.parse.quote(case_dir)
    for k in range(4):
        try:
            return {x["path"]: x for x in get_json(u) if x["type"] == "file"}
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError("list failed " + case_dir)


def do_case(c):
    out = []
    paths = [safe_rel(i["path"]) for i in c["images"]]
    cdir = os.path.dirname(paths[0])
    assert all(os.path.dirname(p) == cdir for p in paths)
    lst = list_case(cdir)
    for p in paths:
        if p not in lst:
            out.append({"case_key": c["case_key"], "path": p, "error": "not_in_official_listing"})
            continue
        ent = lst[p]
        dest = os.path.join(OUT, p)
        exp_sha = (ent.get("lfs") or {}).get("oid")
        url = f"https://huggingface.co/datasets/{HF}/resolve/{HF_REV}/" + urllib.parse.quote(p)
        rec = {"case_key": c["case_key"], "path": p, "listing_size": ent.get("size"), "lfs": bool(exp_sha)}
        try:
            r = fetch(url, dest, exp_sha, ent.get("size"))
            rec.update({"file_sha256": r["sha256"], "size": r["size"]})
            if not exp_sha:
                rec["git_blob_sha1"] = git_blob_sha1(dest)
                rec["git_blob_ok"] = rec["git_blob_sha1"] == ent.get("oid")
            im = Image.open(dest)
            im.load()
            rec.update({"decode_ok": True, "mode": im.mode, "wh": list(im.size),
                        "pixel_sha256": hashlib.sha256(im.mode.encode() + str(im.size).encode() + im.tobytes()).hexdigest()})
        except Exception as e:  # noqa
            rec.update({"decode_ok": False, "error": repr(e)})
        out.append(rec)
    return out


def main():
    cases = [json.loads(l) for l in open(os.path.join(AUD, "eligible_cases.jsonl"))]
    t0 = time.time()
    recs = []
    with cf.ThreadPoolExecutor(8) as ex:
        for k, r in enumerate(ex.map(do_case, cases), 1):
            recs += r
            if k % 25 == 0:
                print(k, len(recs), round(time.time() - t0), "s", flush=True)
    bad = [r for r in recs if not r.get("decode_ok") or r.get("git_blob_ok") is False or "error" in r]
    man = {"hf_revision": HF_REV, "n_cases": len(cases), "n_images": len(recs), "n_bad": len(bad),
           "seconds": time.time() - t0, "bytes": sum(r.get("size", 0) for r in recs), "records": recs}
    with open(os.path.join(OUT, "image_manifest.json"), "x") as f:
        json.dump(man, f, indent=1)
    print("images", len(recs), "bad", len(bad), "seconds", round(time.time() - t0), "bytes", man["bytes"])


if __name__ == "__main__":
    sys.exit(main())
