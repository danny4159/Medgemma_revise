"""Inputs, grid, pixel transforms, config and request manifest (label-free).

이 모듈은 annotation 파일을 읽지 않는다. 이미지 목록은 디렉터리의 PNG로만 만든다.
"""
import glob
import hashlib
import json
import os
import random

import numpy as np
from PIL import Image, ImageFilter

DATA_DIR = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/vindr_cxr"
MODEL_ID = "google/medgemma-1.5-4b-it"
MODEL_REVISION = "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"
SCORER_VERSION = "qes-scorer-1"
SEED = 0

FINDINGS = [
    "Cardiomegaly",
    "Calcification",
    "Pleural effusion",
    "Pulmonary fibrosis",
    "Pleural thickening",
    "Atelectasis",
]
PROMPT_TEMPLATE = "Is there evidence of {finding} in this chest X-ray? Answer Yes or No."
GRID = 3
BLUR_RADIUS_FRAC = 0.05
KINDS = ["orig", "crop", "blur", "mean"]


def build_config():
    return {
        "iteration": "iter_004",
        "seed": SEED,
        "data_dir": DATA_DIR,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "processor_revision": MODEL_REVISION,
        "dtype": "bfloat16",
        "scorer_version": SCORER_VERSION,
        "findings": FINDINGS,
        "prompt_template": PROMPT_TEMPLATE,
        "candidates": {"Yes": "Yes", "No": "No"},
        "margin": "m = log P(Yes|I,q) - log P(No|I,q), last-position logits, log_softmax over full vocab",
        "grid": GRID,
        "tile_bounds": "x_k = floor(k*W/3 + 0.5), y_k = floor(k*H/3 + 0.5), k=0..3; tile id row-major r*3+c",
        "blur": {"type": "PIL.ImageFilter.GaussianBlur on full RGB original, tile pasted back",
                 "radius_frac_of_min_side": BLUR_RADIUS_FRAC},
        "mean_fill": "per-channel mean of full original RGB (round half up to uint8), tile filled",
        "crop": "tile crop passed as separate image, no manual upscaling (processor resizes)",
        "transform_order": "all pixel transforms on original resolution before processor",
        "tie_rule": "argmax ties -> smallest row-major tile id",
    }


def config_hash(cfg):
    return sha256_json(cfg)


def sha256_json(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pixel_hash(img):
    """sha256 over mode, size and actual RGB bytes."""
    img = img.convert("RGB") if img.mode != "RGB" else img
    h = hashlib.sha256()
    h.update(f"{img.mode}|{img.size[0]}x{img.size[1]}|".encode())
    h.update(img.tobytes())
    return h.hexdigest()


def list_images(data_dir=DATA_DIR):
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(data_dir, "*.png")))


def load_rgb(path):
    with Image.open(path) as im:
        return im.convert("RGB")


def tile_boxes(W, H, n=GRID):
    xs = [int(np.floor(k * W / n + 0.5)) for k in range(n + 1)]
    ys = [int(np.floor(k * H / n + 0.5)) for k in range(n + 1)]
    return [(xs[c], ys[r], xs[c + 1], ys[r + 1]) for r in range(n) for c in range(n)]


def blur_full(orig):
    W, H = orig.size
    return orig.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS_FRAC * min(W, H)))


def channel_means(orig):
    a = np.asarray(orig, dtype=np.float64)
    return tuple(int(np.floor(a[..., c].mean() + 0.5)) for c in range(3))


class ImageInputs:
    """원본에서 모든 입력 변형을 결정적으로 만든다 (blur는 이미지당 한 번 계산)."""

    def __init__(self, path):
        self.path = path
        self.orig = load_rgb(path)
        self.W, self.H = self.orig.size
        self.tiles = tile_boxes(self.W, self.H)
        self._blur = None
        self._means = None

    @property
    def blurred(self):
        if self._blur is None:
            self._blur = blur_full(self.orig)
        return self._blur

    @property
    def means(self):
        if self._means is None:
            self._means = channel_means(self.orig)
        return self._means

    def make(self, kind, tile):
        if kind == "orig":
            return self.orig
        box = self.tiles[tile]
        if kind == "crop":
            return self.orig.crop(box)
        out = self.orig.copy()
        if kind == "blur":
            out.paste(self.blurred.crop(box), box[:2])
        elif kind == "mean":
            out.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), self.means), box[:2])
        else:
            raise ValueError(kind)
        return out


def request_id(image, finding, kind, tile):
    return f"{image}|{finding}|{kind}|{'-' if tile is None else tile}"


def build_requests(data_dir=DATA_DIR, images=None, cfg=None):
    cfg = cfg or build_config()
    chash = config_hash(cfg)
    images = images if images is not None else list_images(data_dir)
    reqs, image_info = [], {}
    for name in images:
        path = os.path.join(data_dir, name)
        ii = ImageInputs(path)
        info = {
            "file": name,
            "width": ii.W,
            "height": ii.H,
            "source_file_sha256": file_sha256(path),
            "source_pixel_sha256": pixel_hash(ii.orig),
            "tiles": [list(t) for t in ii.tiles],
            "tile_areas": [(t[2] - t[0]) * (t[3] - t[1]) for t in ii.tiles],
            "channel_means": list(ii.means),
            "blur_radius": BLUR_RADIUS_FRAC * min(ii.W, ii.H),
            "input_pixel_sha256": {},
        }
        inputs = [("orig", None)] + [(k, t) for k in ("crop", "blur", "mean") for t in range(GRID * GRID)]
        for kind, tile in inputs:
            info["input_pixel_sha256"][f"{kind}|{'-' if tile is None else tile}"] = pixel_hash(ii.make(kind, tile))
        image_info[name] = info
        for q in FINDINGS:
            for kind, tile in inputs:
                r = {
                    "id": request_id(name, q, kind, tile),
                    "image": name,
                    "finding": q,
                    "kind": kind,
                    "tile": tile,
                    "prompt": PROMPT_TEMPLATE.format(finding=q),
                    "source_file_sha256": info["source_file_sha256"],
                    "source_pixel_sha256": info["source_pixel_sha256"],
                    "input_pixel_sha256": info["input_pixel_sha256"][f"{kind}|{'-' if tile is None else tile}"],
                    "config_sha256": chash,
                }
                r["request_sha256"] = sha256_json(r)
                reqs.append(r)
    return reqs, image_info


def fixed_subsets(reqs):
    """모델 결과를 보기 전에 calibration(24)과 verification(12) 입력을 고정한다."""
    by = {(r["image"], r["finding"], r["kind"], r["tile"]): r["id"] for r in reqs}
    images = sorted({r["image"] for r in reqs})

    def pick(seed, n_per_kind):
        rng = random.Random(seed)
        ids = []
        for i in range(n_per_kind):
            for kind in KINDS:
                while True:
                    img = rng.choice(images)
                    q = FINDINGS[(i * len(KINDS) + KINDS.index(kind)) % len(FINDINGS)]
                    tile = None if kind == "orig" else rng.randrange(GRID * GRID)
                    rid = by[(img, q, kind, tile)]
                    if rid not in ids:
                        ids.append(rid)
                        break
        return ids

    return {"calibration": pick(SEED + 1, 6), "verification": pick(SEED + 2, 3)}
