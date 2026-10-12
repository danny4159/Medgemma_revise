"""iter_114: 공개 MedGrounder MSPC 가중치(PadChest+MS-CXR 적응본) 확보. 격리 venv(medgrounder_iter045)의 gdown 사용.

기존 iter_045 weights/hf_cache는 수정하지 않고 results/iter_114/external/weights 에만 새로 저장한다. 이미 있으면 덮어쓰지 않는다.
출처(Drive folder id/file id)·bytes·sha256·공식 README의 이용 조건 문구 위치를 weights_manifest.json 에 남긴다.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "results", "environments", "medgrounder_iter045", "bin", "python")
OUT = os.path.join(HERE, "results", "iter_114", "external", "weights")
LISTING = os.path.join(HERE, "results", "iter_045", "external", "weights", "drive_listing.json")
NAME = "medgrounder_finetune_mspc.pth"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    listing = json.load(open(LISTING))
    hit = [i for i in listing["items"] if i["path"] == NAME]
    assert len(hit) == 1
    dest = os.path.join(OUT, NAME)
    if os.path.exists(dest):
        print("exists, not overwriting", dest)
    else:
        tmp = dest + ".part"
        code = "import gdown,sys;gdown.download(id=sys.argv[1],output=sys.argv[2],quiet=True,use_cookies=False)"
        p = subprocess.run([PY, "-c", code, hit[0]["id"], tmp], capture_output=True, text=True)
        with open(os.path.join(OUT, "download.log"), "a") as f:
            f.write(f"{NAME} rc={p.returncode}\n{p.stderr[-3000:]}\n")
        if p.returncode != 0 or not os.path.exists(tmp):
            raise SystemExit(f"download failed: {p.stderr[-1500:]}")
        os.rename(tmp, dest)
    man = {NAME: {"drive_folder": listing["folder"], "drive_id": hit[0]["id"], "bytes": os.path.getsize(dest), "sha256": sha256(dest)}}
    mp = os.path.join(OUT, "weights_manifest.json")
    if os.path.exists(mp):
        assert json.load(open(mp)) == man, "manifest differs from existing"
    else:
        json.dump(man, open(mp, "x"), indent=1)
    print(json.dumps(man, indent=1))


if __name__ == "__main__":
    sys.exit(main())
