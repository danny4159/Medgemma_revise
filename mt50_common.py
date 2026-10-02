"""iter_050 공통: 경로, 원본 검증(해시/크기/symlink/경로 이탈), 영상 로딩(RGB 변환·alpha 검사)."""
import hashlib
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
R49 = os.path.join(HERE, "results", "iter_049")
OUT = os.path.join(HERE, "results", "iter_050")
TRAIN_SHA = "7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a"
HF_REVISION = "5555b80e167c4796efab92fe709fb05914077dc0"
LETTERS = "ABCDE"


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_json(o):
    return sha_bytes(json.dumps(o, sort_keys=True, ensure_ascii=False).encode())


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def safe_image_path(rel):
    """images/caseNNNNN/xxx.jpg -> 절대 경로. symlink·경로 이탈 거부."""
    base = os.path.realpath(os.path.join(R49, "images"))
    p = os.path.join(R49, rel)
    if os.path.islink(p) or os.path.islink(os.path.dirname(p)):
        raise ValueError("symlink: " + rel)
    rp = os.path.realpath(p)
    if not rp.startswith(base + os.sep):
        raise ValueError("path escape: " + rel)
    return rp


def load_rgb(rel):
    """원본 전체 영상을 crop/padding 없이 RGB로 변환. returns (PIL RGB, info)."""
    p = safe_image_path(rel)
    im = Image.open(p)
    mode = im.mode
    im.load()
    amin = None
    if mode in ("RGBA", "LA"):
        a = im.getchannel("A")
        amin = a.getextrema()[0]
    native = sha_bytes(im.mode.encode() + str(im.size).encode() + im.tobytes())  # iter_049 정의와 동일
    rgb = im.convert("RGB")
    return rgb, {"mode": mode, "alpha_min": amin, "wh": list(rgb.size),
                 "native_pixel_sha256": native, "pixel_sha256": sha_bytes(rgb.tobytes())}
