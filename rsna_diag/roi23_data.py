"""iter_023 데이터: source manifest 결합, D24/E60/E200 patient 선택, gray 대조 영상, 기존 bbox 원시 출력 연결.

두 원본 source-root를 읽기 전용으로 쓴다:
- iter_010 (validation split, val_*): D24 동작 확인용. bbox는 새로 생성한다 (기존 출력 없음).
- iter_015 (confirm split, con_*): E60/E200 가능성 탐색/확대용. M0/B0 bbox는 iter_012 confirm 원시 출력에서 연결한다.
"""
import glob
import hashlib
import json
import os

import numpy as np
from PIL import Image

from . import generate, parse as PA, prompts as P, roi23_spec as R

VAL_MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
VAL_GT = "results/iter_010/manifests/gt_manifest.json"
VAL_IDS = "results/iter_010/manifests/validation_ids.json"
CONFIRM_MANIFEST = "results/iter_015/manifests/infer_manifest.jsonl"
CONFIRM_LABELS = "results/iter_015/manifests/labels.json"
CONFIRM_SETS = "results/iter_015/manifests/sets.json"

BBOX_DIR = {"M0": "results/iter_012/confirm_base", "B0": "results/iter_012/confirm_sft_seed17",
            "B29": "results/iter_012/confirm_sft_seed29", "B43": "results/iter_012/confirm_sft_seed43"}
BBOX_PROMPT = {"M0": {"official_long": "official_long", "concise": "concise"}, "B0": {"concise": "concise"},
               "B29": {"concise": "concise"}, "B43": {"concise": "concise"}}


class DataError(RuntimeError):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def _load_manifest(path):
    out = {}
    for ln in open(path):
        if ln.strip():
            r = json.loads(ln)
            if r["id"] in out:
                raise DataError(f"duplicate id in {path}: {r['id']}")
            out[r["id"]] = r
    return out


def load_val_pool():
    """iter_010 validation split (val_*): items(id->row with image/file_sha256/pixel_sha256/split), gt(id->{category,boxes})."""
    man = _load_manifest(VAL_MANIFEST)
    gt = json.load(open(VAL_GT))
    ids = json.load(open(VAL_IDS))
    if len(set(ids)) != len(ids):
        raise DataError("duplicate ids in validation_ids.json")
    whole = {i for i, r in man.items() if r["split"] == "validation"}
    if set(ids) != whole:
        raise DataError(f"validation_ids.json != manifest validation split ({len(ids)} vs {len(whole)})")
    items, gts = {}, {}
    for i in ids:
        if gt[i].get("pixel_sha256") != man[i].get("pixel_sha256"):
            raise DataError(f"id {i}: GT/manifest pixel_sha256 differ")
        items[i] = man[i]
        gts[i] = {"category": gt[i]["category"], "boxes": gt[i]["boxes"]}
    return items, gts


def load_confirm_pool():
    """iter_015 confirm split (con_*) source manifest + labels. iter_015 infer_manifest.jsonl also carries a
    36-patient legacy 'validation' subset (D12) from an earlier diagnostic; that is excluded here so this pool
    stays disjoint from the iter_010 validation pool used for D24."""
    man = _load_manifest(CONFIRM_MANIFEST)
    labels = json.load(open(CONFIRM_LABELS))
    items, gts = {}, {}
    for i, r in man.items():
        if r["split"] != "confirm":
            continue
        if i not in labels:
            raise DataError(f"id {i} in confirm manifest has no label entry")
        items[i] = r
        gts[i] = {"category": labels[i]["category"], "boxes": labels[i]["boxes"]}
    return items, gts


def check_disjoint(*pools):
    ids = [set(p) for p in pools]
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            common = ids[a] & ids[b]
            if common:
                raise DataError(f"pool id overlap between source pools: {sorted(common)[:5]}")


def opacity_with_margin(gts, ids):
    """returns (primary ids margin-pass, boundary ids margin-fail) among opacity ids, sorted."""
    prim, bnd = [], []
    for i in ids:
        boxes = [b["yxyx_norm"] for b in gts[i]["boxes"]]
        if not boxes:
            raise DataError(f"opacity id {i} has no boxes")
        (prim if R.margin_ok(boxes) else bnd).append(i)
    return sorted(prim), sorted(bnd)


def select_d24(items, gts, seed_tag="iter023-D24-v1"):
    """iter_010 validation opacity, margin 통과 환자를 largest-box quadrant로 층화해 각 층 6명 선택 (SHA 순)."""
    opac = sorted([i for i, g in gts.items() if g["category"] == "opacity"])
    prim, _bnd = opacity_with_margin(gts, opac)
    layers = {t: [] for t in R.TARGETS}
    for i in prim:
        boxes = gts[i]["boxes"]
        q = R.largest_box_quadrant(boxes)
        layers[q].append(i)
    for q in layers:
        layers[q].sort(key=lambda i: R.d24_order_key(i))
    counts = {q: len(v) for q, v in layers.items()}
    chosen = sorted(i for q in R.TARGETS for i in layers[q][:6])
    if any(counts[q] < 6 for q in R.TARGETS):
        raise DataError(f"insufficient D24 candidates per layer: {counts}")
    return chosen, counts


def e_set(name, gts, sets_path=CONFIRM_SETS):
    sets = json.load(open(sets_path))
    opac = sets[name]["opacity"]
    prim, bnd = opacity_with_margin(gts, opac)
    return prim, bnd


GRAY_VALUE = 128
GRAY_SIDE = 1024


def ensure_gray_image(out_dir):
    path = os.path.join(out_dir, "gray_128.png")
    if not os.path.exists(path):
        os.makedirs(out_dir, exist_ok=True)
        arr = np.full((GRAY_SIDE, GRAY_SIDE), GRAY_VALUE, dtype=np.uint8)
        Image.fromarray(arr).save(path)
    raw = open(path, "rb").read()
    px = sha(np.asarray(Image.open(path)).tobytes())
    return {"id": "control_gray", "split": "control", "image": path, "file_sha256": sha(raw), "pixel_sha256": px}


def _completion_ok(gen_dir, expected_n):
    cp = os.path.join(gen_dir, "completion.json")
    if not os.path.exists(cp):
        raise DataError(f"no completion.json in {gen_dir}")
    c = json.load(open(cp))
    if (c.get("n_expected") != expected_n or c.get("n_actual_unique") != expected_n or c.get("n_missing") != 0
            or c.get("n_duplicate") != 0 or c.get("n_extra") != 0 or not c.get("returncodes")
            or any(x != 0 for x in c["returncodes"])):
        raise DataError(f"completion.json content invalid in {gen_dir}: {c}")
    return c


def source_bbox_records(ckpt, prompt_name, pinned=None):
    """ckpt(M0/B0/B29/B43)의 raw concise/official_long bbox record {id: record}, iter_012 confirm 원시 출력에서.

    pinned: {gen_worker 파일 경로: sha256}. 주어지면 파일 내용이 그 값과 같아야 한다 (변조 거부)."""
    d = BBOX_DIR[ckpt]
    if prompt_name not in BBOX_PROMPT.get(ckpt, {}):
        raise DataError(f"{ckpt} has no {prompt_name} bbox source")
    files = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))
    if not files:
        raise DataError(f"no gen_worker*.jsonl in {d}")
    if pinned:
        for f in files:
            got = sha(open(f, "rb").read())
            if f not in pinned:
                raise DataError(f"bbox source {f} is not pinned")
            if got != pinned[f]:
                raise DataError(f"bbox source {f} changed since verification")
    n_total = 0
    for f in files:
        n_total += sum(1 for ln in open(f) if ln.strip())
    n_this_prompt = 0
    out = {}
    for f in files:
        for ln in open(f):
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("prompt_name") != prompt_name:
                continue
            n_this_prompt += 1
            if r["id"] in out:
                raise DataError(f"duplicate bbox record for {r['id']} in {d} ({prompt_name})")
            out[r["id"]] = r
    return out, n_total


def predicted_boxes(rec):
    if rec is None:
        return None, "missing"
    pr = PA.parse_response(rec["suffix_text_raw"], rec["ended_eos"])
    if pr["status"] in PA.VALID:
        return [[float(v) for v in b] for b in pr["boxes"]], pr["status"]
    return None, pr["status"]
