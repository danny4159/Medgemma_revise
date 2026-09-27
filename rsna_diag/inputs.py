"""입력 집합 provenance (iter_011): split ID 파일의 정확한 내용, manifest/GT, 현재 file/pixel hash를 하나의 digest로 묶는다.

- load_items: ID 파일이 manifest의 해당 split 전체와 정확히 일치하는지(exact=True) 검사하고 item을 id 순으로 반환한다.
  중복 ID·manifest에 없는 ID·다른 split의 ID·GT split/pixel hash 불일치는 예외 (조용히 고치지 않는다).
- inputs_digest: 각 영상의 현재 file sha와 디코드된 원본 uint8 pixel sha를 manifest와 대조하고, (id, split, hash들, GT box)의 digest를 만든다.
- load_verified: 학습/검증 시점마다 현재 pixel hash를 manifest와 대조하는 영상 로더 (generate.load_image와 같은 전처리).
"""
import hashlib
import json

import numpy as np
from PIL import Image

from . import generate, geometry


class InputError(RuntimeError):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_manifest(path):
    items = {}
    for ln in open(path):
        if ln.strip():
            r = json.loads(ln)
            if r["id"] in items:
                raise InputError(f"duplicate id in manifest: {r['id']}")
            items[r["id"]] = r
    return items


def load_items(manifest_path, gt_path, ids_path, split, exact=True):
    """returns (items sorted by id, gt dict). ids 파일 내용이 manifest의 split과 어긋나면 InputError."""
    man = load_manifest(manifest_path)
    gt = json.load(open(gt_path))
    ids = json.load(open(ids_path))
    if len(set(ids)) != len(ids):
        raise InputError(f"duplicate ids in {ids_path}")
    for i in ids:
        if i not in man:
            raise InputError(f"id {i} not in manifest")
        if split is not None and (man[i]["split"] != split or gt.get(i, {}).get("split") != split):
            raise InputError(f"id {i}: manifest/GT split != {split}")
        if gt[i].get("pixel_sha256") != man[i].get("pixel_sha256"):
            raise InputError(f"id {i}: GT and manifest pixel_sha256 differ")
    if exact and split is not None:
        whole = {i for i, r in man.items() if r["split"] == split}
        if set(ids) != whole:
            raise InputError(f"{ids_path} != all manifest items of split {split} ({len(ids)} vs {len(whole)})")
    return [man[i] for i in sorted(ids)], gt


def raw_pixel_sha(path):
    arr = np.asarray(Image.open(path))
    return sha(arr.tobytes())


def inputs_digest(items, gt, check_files=True):
    """현재 파일을 읽어 manifest hash와 대조하고 입력 집합 digest를 반환한다."""
    rows = []
    for it in items:
        if check_files:
            fs = sha(open(it["image"], "rb").read())
            if fs != it["file_sha256"]:
                raise InputError(f"file sha changed for {it['id']}")
            if raw_pixel_sha(it["image"]) != it["pixel_sha256"]:
                raise InputError(f"pixel sha changed for {it['id']}")
        rows.append([it["id"], it["split"], it["file_sha256"], it["pixel_sha256"], json.dumps(gt[it["id"]]["boxes"], sort_keys=True),
                     gt[it["id"]]["category"]])
    return sha(json.dumps(rows).encode())


def load_verified(item):
    """generate.load_image와 같은 전처리. 원본 pixel hash가 manifest와 다르면 예외. returns (PIL, affine, padded pixel sha)."""
    arr = np.asarray(Image.open(item["image"]))
    if sha(arr.tobytes()) != item["pixel_sha256"]:
        raise InputError(f"pixel sha differs from manifest for {item['id']}")
    rgb = geometry.to_uint8_rgb_preserving(arr)
    padded, aff = geometry.pad_square(rgb)
    return Image.fromarray(padded), aff, generate.sha(padded.tobytes())
