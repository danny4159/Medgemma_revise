"""iter_045: MedGrounder 공개 가중치(Google Drive 폴더)에서 비적응 후보 두 개만 받는다.

사용: python mg45_weights.py list | get
venv python(medgrounder_iter045)에서 gdown을 실행한다. PadChest 적응(pc, mspc) 가중치는 받지 않는다.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "results", "environments", "medgrounder_iter045", "bin", "python")
OUT = os.path.join(HERE, "results", "iter_045", "external", "weights")
FOLDER = "https://drive.google.com/drive/folders/1fwr-Bi2ICb26-MIJVKPxwhHVWGJaaBvz"
WANT = ["medgrounder_pretrain_imagenome.pth", "medgrounder_finetune_ms.pth"]

LIST_CODE = """
import gdown, json, sys
fs = gdown.download_folder(url=sys.argv[1], skip_download=True, quiet=True, use_cookies=False)
print(json.dumps([{'id': f.id, 'path': f.path} for f in fs]))
"""


def listing():
    p = subprocess.run([PY, "-c", LIST_CODE, FOLDER], capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-3000:])
        sys.exit(1)
    items = json.loads(p.stdout.strip().splitlines()[-1])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "drive_listing.json"), "w") as f:
        json.dump({"folder": FOLDER, "items": items}, f, indent=1)
    print(json.dumps(items, indent=1))
    return items


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def get():
    items = listing()
    manifest = {}
    for name in WANT:
        hit = [i for i in items if os.path.basename(i["path"]) == name]
        if len(hit) != 1:
            raise SystemExit(f"{name}: {len(hit)} matches in listing")
        dest = os.path.join(OUT, name)
        if os.path.exists(dest):
            print("exists, not overwriting", dest)
        else:
            tmp = dest + ".part"
            code = "import gdown,sys;gdown.download(id=sys.argv[1],output=sys.argv[2],quiet=False,use_cookies=False)"
            p = subprocess.run([PY, "-c", code, hit[0]["id"], tmp], capture_output=True, text=True)
            with open(os.path.join(OUT, "download.log"), "a") as f:
                f.write(f"{name} rc={p.returncode}\n{p.stderr[-3000:]}\n")
            if p.returncode != 0 or not os.path.exists(tmp):
                raise SystemExit(f"download failed {name}: {p.stderr[-1500:]}")
            os.rename(tmp, dest)
        manifest[name] = {"drive_id": hit[0]["id"], "bytes": os.path.getsize(dest), "sha256": sha256(dest)}
    with open(os.path.join(OUT, "weights_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(json.dumps(manifest, indent=1))


TEXT_ENC = "thomas-sounack/BioClinical-ModernBERT-base"
TE_CODE = """
import sys, json
from huggingface_hub import HfApi, snapshot_download
repo, dest = sys.argv[1], sys.argv[2]
info = HfApi().model_info(repo)
p = snapshot_download(repo_id=repo, revision=info.sha, local_dir=dest)
print(json.dumps({'repo': repo, 'revision': info.sha, 'path': p, 'license': getattr(info, 'card_data', None) and info.card_data.to_dict().get('license')}))
"""


def textenc():
    dest = os.path.join(HERE, "results", "iter_045", "external", "text_encoder")
    if os.path.exists(dest):
        print("exists, not overwriting", dest)
        return
    p = subprocess.run([PY, "-c", TE_CODE, TEXT_ENC, dest], capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-3000:])
        sys.exit(1)
    info = json.loads(p.stdout.strip().splitlines()[-1])
    files = {}
    for r, _, fs in os.walk(dest):
        for fn in fs:
            fp = os.path.join(r, fn)
            if ".cache" in fp:
                continue
            files[os.path.relpath(fp, dest)] = sha256(fp)
    info["files_sha256"] = files
    with open(os.path.join(os.path.dirname(dest), "text_encoder_manifest.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(json.dumps({k: v for k, v in info.items() if k != "files_sha256"}, indent=1), len(files), "files")


CACHE_CODE = """
import sys
from huggingface_hub import snapshot_download
print(snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], cache_dir=sys.argv[3]))
"""


def textenc_cache():
    """공식 코드가 hub 이름('thomas-sounack/BioClinical-ModernBERT-base')으로 from_pretrained 하므로 고정 revision의 오프라인 cache를 만든다."""
    man = json.load(open(os.path.join(HERE, "results", "iter_045", "external", "text_encoder_manifest.json")))
    cache = os.path.join(HERE, "results", "iter_045", "external", "hf_cache")
    p = subprocess.run([PY, "-c", CACHE_CODE, TEXT_ENC, man["revision"], cache], capture_output=True, text=True)
    print(p.stdout, p.stderr[-1500:])
    if p.returncode != 0:
        sys.exit(1)
    refs = os.path.join(cache, "models--thomas-sounack--BioClinical-ModernBERT-base", "refs")
    os.makedirs(refs, exist_ok=True)
    with open(os.path.join(refs, "main"), "w") as f:
        f.write(man["revision"])


if __name__ == "__main__":
    {"list": listing, "get": get, "textenc": textenc, "textenc_cache": textenc_cache}[sys.argv[1]]()
