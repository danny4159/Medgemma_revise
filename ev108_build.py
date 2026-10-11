"""iter_108: crop 영상·요청 파일·기술 표본을 만든다 (GPU 불필요, 정답은 요청 구성에 쓰지 않는다).

stage: TECH(P180 nonempty 기술 6명), P180R(P180 nonempty 나머지), E600R(E600 nonempty 중 P180 밖).
출력은 results/iter_108 아래에만 쓰며 기존 파일은 덮어쓰지 않는다.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import ev108_data as D
import ev108_spec as S
from rsna_diag import generate as G

ROOT = D.ROOT
R108 = ROOT / "results/iter_108"
DATA = R108 / "data"
IMG = DATA / "images"
TECH_TAKE = {"opacity": 3, "normal": 1, "not_normal_no_opacity": 2}


def save_new(path, obj):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{__import__('os').getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
    tmp.replace(path)


def load_canvas(path):
    """원본 PNG -> 값 보존 RGB -> 정사각 padding canvas (generate.load_image와 같은 경로)."""
    img, aff, px = G.load_image(path)
    return np.asarray(img), aff, px


def save_png_new(arr, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    Image.fromarray(arr).save(path)


def patient_geometry(pid, infer, bb):
    """저장 bbox가 ok인 환자의 crop 기하. returns dict (GT 미사용)."""
    st, boxes = S.parse_saved_bbox(bb["suffix_text_raw"], bb["ended_eos"])
    assert st == "ok", (pid, st)
    canvas, aff, px = load_canvas(infer["image"])
    side = canvas.shape[0]
    enc = S.enclosing(boxes)
    rect = S.crop_rect(enc, side)
    assert rect is not None, (pid, enc)
    h, w = rect[3] - rect[1], rect[2] - rect[0]
    crect = S.center_rect(h, w, side)
    assert crect[0] >= 0 and crect[1] >= 0 and crect[2] <= side and crect[3] <= side
    return {"id": pid, "orig_image": infer["image"], "orig_file_sha256": infer["file_sha256"], "orig_pixel_sha256": px,
            "side": side, "pad_affine": list(aff), "n_boxes": len(boxes), "boxes_yxyx": boxes, "enclosing_yxyx": enc,
            "rect_T": list(rect), "rect_C": list(crect), "crop_hw": [h, w], "area_ratio": S.rect_area_ratio(rect, side),
            "T_equals_C": list(rect) == list(crect)}, canvas


def make_images(geo, canvas):
    pid = geo["id"]
    out = {}
    for tag, key in (("T", "rect_T"), ("C", "rect_C")):
        if tag == "C" and geo["T_equals_C"]:
            pass  # 동일한 경우도 그대로 별도 파일로 보존한다
        arr, aff = S.crop_square_padded(canvas, tuple(geo[key]))
        p = IMG / f"{pid}_{tag}.png"
        save_png_new(arr, p)
        rel = str(p.relative_to(ROOT))
        _, _, px = load_canvas(rel)
        out[tag] = {"path": rel, "file_sha256": D.file_sha(p), "pixel_sha256": px, "crop_pad_affine": list(aff)}
    return out


def request_row(stage, geo, imgs, cond, target, order):
    orig = {"role": "orig", "path": geo["orig_image"], "file_sha256": geo["orig_file_sha256"], "pixel_sha256": geo["orig_pixel_sha256"]}
    if cond == "D":
        images = [orig, dict(orig, role="orig_dup")]
    elif cond == "T":
        images = [orig, dict(imgs["T"], role="crop_pred")]
        images[1].pop("crop_pad_affine", None)
    elif cond == "C":
        images = [orig, dict(imgs["C"], role="crop_center")]
        images[1].pop("crop_pad_affine", None)
    elif cond == "L":
        images = [dict(imgs["T"], role="crop_pred")]
        images[0].pop("crop_pad_affine", None)
    elif cond == "F":
        images = [orig]
    else:
        raise ValueError(cond)
    prompt = S.core_prompt(target) if cond == "F" else S.prompt_for(cond, target)
    fields = {"patient": geo["id"], "cond": cond, "target": target, "prompt_sha256": S.sha(prompt), "caps": S.CAPS,
              "images": [(i["role"], i["pixel_sha256"]) for i in images], "model_revision": G.MODEL_REVISION}
    return {"request_id": S.sha(S.canon(fields))[:32], "stage": stage, "patient": geo["id"], "cond": cond, "target": target,
            "kind": {"L": "single_crop", "F": "single_orig"}.get(cond, "multi"), "images": images, "prompt": prompt,
            "prompt_sha256": S.sha(prompt), "caps": S.CAPS, "order_key": order, "fmt": S.FMT}


def conds_for():
    return [("D", "O"), ("D", "A"), ("T", "O"), ("T", "A"), ("C", "O"), ("C", "A"), ("L", "O")]


def main():
    sets, labels, infer, ckpt, bbox = D.load_assets()
    rep, problems = D.audit(sets, labels, infer, ckpt, bbox)
    if problems:
        print("AUDIT PROBLEMS", problems[:10])
        sys.exit(2)
    DATA.mkdir(parents=True, exist_ok=True)
    save_new(DATA / "audit.json", {"report": rep, "locked_inputs": {str(p.relative_to(ROOT)): D.file_sha(p) for p in D.LOCKED_INPUTS}})
    # 환자 목록
    p180 = {c: sorted(i for i in sets["P180"][c] if S.parse_saved_bbox(bbox[i]["suffix_text_raw"], bbox[i]["ended_eos"])[0] == "ok") for c in S.CATS}
    e600 = {c: sorted(i for i in sets["E600"][c] if S.parse_saved_bbox(bbox[i]["suffix_text_raw"], bbox[i]["ended_eos"])[0] == "ok") for c in S.CATS}
    tech = [i for c in S.CATS for i in p180[c][:TECH_TAKE[c]]]
    p180_all = [i for c in S.CATS for i in p180[c]]
    rest_p = [i for i in p180_all if i not in tech]
    e_rest = [i for c in S.CATS for i in e600[c] if i not in set(p180_all)]
    assert len(tech) == 6 and len(p180_all) == 72 and len(e_rest) == 164
    stages = {"TECH": tech, "P180R": rest_p, "E600R": e_rest}
    cat_of = {i: labels[i]["category"] for i in labels}
    geos, rows = {}, {k: [] for k in stages}
    order = 0
    for stage, ids in stages.items():
        for pid in ids:
            geo, canvas = patient_geometry(pid, infer[pid], bbox[pid])
            geos[pid] = geo
            imgs = make_images(geo, canvas)
            geo["images"] = imgs
            for cond, target in conds_for():
                rows[stage].append(request_row(stage, geo, imgs, cond, target, order))
                order += 1
    for stage, rs in rows.items():
        p = DATA / f"requests_{stage}.jsonl"
        if p.exists():
            raise FileExistsError(p)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rs))
    save_new(DATA / "geometry.json", geos)
    save_new(DATA / "stage_patients.json", {"stages": stages, "n_requests": {k: len(v) for k, v in rows.items()}, "category_note": "정답은 평가에서만 사용",
                                            "n_by_category_tech": {c: sum(cat_of[i] == c for i in tech) for c in S.CATS}})
    print({k: len(v) for k, v in rows.items()})


def build_frepro():
    """기술 6명의 원본 직접(F) 12요청: iter_016 저장 F와 token 재현 확인용 (과학 요청 아님)."""
    st = json.load(open(DATA / "stage_patients.json"))
    geos = json.load(open(DATA / "geometry.json"))
    rows, order = [], 0
    for pid in st["stages"]["TECH"]:
        for tg in S.TARGETS:
            rows.append(request_row("FREPRO", geos[pid], geos[pid]["images"], "F", tg, order))
            order += 1
    p = DATA / "requests_FREPRO.jsonl"
    if p.exists():
        raise FileExistsError(p)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print({"FREPRO": len(rows)})


if __name__ == "__main__":
    build_frepro() if sys.argv[1:] == ["frepro"] else main()
