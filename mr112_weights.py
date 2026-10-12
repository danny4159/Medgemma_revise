"""iter_112: MedRegA 가중치를 고정 revision으로 results/environments/medrega112_weights에 받고 크기/sha256을 기록한다.
기존 파일은 덮어쓰지 않고, 크기가 같은 파일만 건너뛴다. hf_cache는 건드리지 않는다."""
import hashlib, json, os, sys, time, urllib.request

REPO = "Luxuriant16/medrega"
REV = "ec1d98335322b2200f93b35562b681e05fc3a194"
DST = "results/environments/medrega112_weights"
LOG = "results/iter_112/weights_download.log"


def log(m):
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + m + "\n")


def fetch(name, size):
    dst = f"{DST}/{name}"
    part = dst + ".part"
    if os.path.exists(dst):
        assert os.path.getsize(dst) == size, (name, "size mismatch")
        return
    url = f"https://huggingface.co/{REPO}/resolve/{REV}/{name}"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    r = urllib.request.urlopen(req, timeout=120)
    if have:
        assert r.status == 206, r.status
        cr = r.headers["Content-Range"]
        assert cr.startswith(f"bytes {have}-") and cr.endswith(f"/{size}"), cr
    with open(part, "ab") as f:
        while True:
            b = r.read(1 << 24)
            if not b:
                break
            f.write(b)
    assert os.path.getsize(part) == size, (name, os.path.getsize(part), size)
    os.replace(part, dst)


def main():
    os.makedirs(DST, exist_ok=True)
    tree = json.load(open("results/iter_112/external/fetch_manifest.json"))["hf"]["tree"]
    files = [(t["path"], t["size"]) for t in tree if t["path"].endswith(".safetensors")]
    for n, s in files:
        for attempt in range(8):
            try:
                t0 = time.time()
                fetch(n, s)
                log(f"ok {n} {s} {time.time()-t0:.0f}s")
                break
            except Exception as e:
                log(f"retry {n} attempt{attempt} {e!r}")
                time.sleep(10)
        else:
            log(f"FAIL {n}")
            sys.exit(1)
    man = {}
    for n, s in files:
        h = hashlib.sha256()
        with open(f"{DST}/{n}", "rb") as f:
            for b in iter(lambda: f.read(1 << 24), b""):
                h.update(b)
        man[n] = {"bytes": s, "sha256": h.hexdigest()}
    lfs = {t["path"]: (t.get("lfs") or {}).get("oid") for t in tree}
    for n in man:
        man[n]["hf_lfs_oid"] = lfs[n]
        man[n]["sha256_matches_hf"] = man[n]["sha256"] == lfs[n]
    json.dump(man, open("results/iter_112/weights_manifest.json", "w"), indent=1)
    log("DONE all " + str(all(v["sha256_matches_hf"] for v in man.values())))


if __name__ == "__main__":
    main()
