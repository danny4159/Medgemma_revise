"""iter_069: MedThinkVQA 후보 case 영상의 공식 revision 선택 다운로드 (mt49_fetch/mt49_images의 보완판).

mt49 대비 보완
 - 모든 쓰기는 results/iter_069 아래로 제한: realpath 검사 + 경로 구성요소 symlink 거부 (iter_049 산출물은 읽기만).
 - 이미 존재하는 파일·FileExistsError 경합 경로에서도 공식 크기와 LFS sha256 / git blob sha1을 검증한다. 불일치 시 재사용 거부.
 - .part 는 검증 후에만 링크; 실패 시 정리.
 - 영상별 file sha256 / decode pixel sha256 / PIL 버전을 manifest에 기록.
test/ 경로는 열거하지 않는다 (train revision만).
"""
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

HF = "bio-nlp-umass/MedThinkVQA"
HF_REV = "5555b80e167c4796efab92fe709fb05914077dc0"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "iter_069")
UA = {"User-Agent": "dd69-fetch/1.0"}


def safe_dest(rel):
    """ROOT 아래 상대 경로만 허용. 상위 이탈·절대 경로·구성요소 symlink 거부. 절대 경로를 돌려준다."""
    if rel.startswith("/") or "\\" in rel or ".." in rel.split("/"):
        raise ValueError("unsafe path " + rel)
    root = os.path.realpath(ROOT)
    cur = ROOT
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ValueError("symlink in path " + cur)
    dest = os.path.join(ROOT, rel)
    if os.path.commonpath([os.path.realpath(dest), root]) != root:
        raise ValueError("path escapes ROOT " + rel)
    return dest


def safe_remote(p):
    if p.startswith("/") or ".." in p.split("/") or "\\" in p or not p.startswith("images/case"):
        raise ValueError("unsafe remote path " + p)
    return p


def get_json(url):
    last = None
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.load(r)
        except Exception as e:  # noqa
            last = repr(e)
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"get_json failed {url}: {last}")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git_blob_sha1(path):
    n = os.path.getsize(path)
    h = hashlib.sha1(b"blob %d\0" % n)
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verify_file(path, size, lfs_oid, blob_oid):
    """공식 크기 + (LFS면 sha256, 아니면 git blob sha1) 모두 일치해야 True 대신 예외 없이 (ok, why)."""
    if os.path.islink(path):
        return False, "symlink"
    if os.path.getsize(path) != size:
        return False, f"size {os.path.getsize(path)} != {size}"
    if lfs_oid:
        s = sha256_file(path)
        return (s == lfs_oid), "lfs sha256 " + ("ok" if s == lfs_oid else "mismatch")
    s = git_blob_sha1(path)
    return (s == blob_oid), "git blob sha1 " + ("ok" if s == blob_oid else "mismatch")


def fetch_verified(url, rel, size, lfs_oid, blob_oid, retries=4):
    """공식 URL -> ROOT/rel. 기존 파일은 공식 크기·hash 검증을 통과해야만 재사용 (아니면 RuntimeError, 덮어쓰지 않음)."""
    dest = safe_dest(rel)
    if os.path.exists(dest):
        ok, why = verify_file(dest, size, lfs_oid, blob_oid)
        if not ok:
            raise RuntimeError(f"existing file failed verification {rel}: {why}")
        return {"rel": rel, "reused": True, "verify": why}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + f".part.{os.getpid()}"
    last = None
    for k in range(retries):
        try:
            t0 = time.time()
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(part, "wb") as f:
                final_url = r.geturl()
                etag = r.headers.get("ETag")
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            ok, why = verify_file(part, size, lfs_oid, blob_oid)
            if not ok:
                raise RuntimeError("download verification failed: " + why)
            try:
                os.link(part, dest)  # 이미 존재하면 FileExistsError
            except FileExistsError:
                ok2, why2 = verify_file(dest, size, lfs_oid, blob_oid)  # 경합 승자도 검증
                if not ok2:
                    raise RuntimeError(f"race winner failed verification {rel}: {why2}")
                return {"rel": rel, "reused": True, "verify": why2, "race": True}
            return {"rel": rel, "reused": False, "verify": why, "url": url, "final_url": final_url, "etag": etag,
                    "seconds": time.time() - t0}
        except RuntimeError as e:
            if "race winner" in str(e):
                raise
            last = repr(e)
            time.sleep(2 * (k + 1))
        except Exception as e:  # noqa
            last = repr(e)
            time.sleep(2 * (k + 1))
        finally:
            if os.path.exists(part):
                os.unlink(part)
    raise RuntimeError(f"fetch failed {url}: {last}")


def list_case(case_dir):
    u = f"https://huggingface.co/api/datasets/{HF}/tree/{HF_REV}/" + urllib.parse.quote(case_dir)
    return {x["path"]: x for x in get_json(u) if x["type"] == "file"}


def fetch_image(remote_path):
    """case 영상 1장 -> results/iter_069/images/... . 공식 listing으로 size/oid 확보 후 검증 다운로드."""
    from PIL import Image
    p = safe_remote(remote_path)
    ent = list_case(os.path.dirname(p)).get(p)
    if ent is None:
        raise RuntimeError("not in official listing " + p)
    lfs = (ent.get("lfs") or {}).get("oid")
    url = f"https://huggingface.co/datasets/{HF}/resolve/{HF_REV}/" + urllib.parse.quote(p)
    r = fetch_verified(url, p, ent["size"], lfs, ent.get("oid"))
    dest = safe_dest(p)
    im = Image.open(dest)
    im.load()
    r.update({"remote_path": p, "size": ent["size"], "lfs": bool(lfs), "official_oid": ent.get("oid"),
              "file_sha256": sha256_file(dest), "mode": im.mode, "wh": list(im.size),
              "pixel_sha256": hashlib.sha256(im.mode.encode() + str(im.size).encode() + im.tobytes()).hexdigest(),
              "PIL": __import__("PIL").__version__})
    return r
