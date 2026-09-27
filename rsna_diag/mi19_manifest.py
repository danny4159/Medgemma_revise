"""iter_019 최종 manifest: images.zip 영상 co-registration 검사, R/T 렌더링·PNG 저장, bbox/point normalized 변환, split 배정.

실행: python -m rsna_diag.mi19_manifest
입력: results/iter_019/data/gate.json (mi19_data.gate_patients 결과), results/iter_019/source/{images,masks}.zip
출력: results/iter_019/data/images/{pid}_{R,T}.png, results/iter_019/data/manifest.json, results/iter_019/data/split.json
"""
import hashlib
import json
import os

import numpy as np

from . import geometry, mi19_data as D, mi19_mha as M, mi19_render as R

DATA_DIR = D.DATA_DIR
SOURCE = D.SOURCE
SPLIT_SALT = "iter019-split-v1"
D_SIZE, E_SIZE = 8, 48


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


class DataQualityError(RuntimeError):
    """자료 자체의 문제(공동등록 불일치, 이미지 멤버 누락 등)로 인한 build_one 예외.
    build_one을 호출하는 쪽은 이 예외만 '적격 자료 제외'로 취급하고 조용히 넘어간다.
    그 외 예외(구현 버그: KeyError/AttributeError/TypeError 등)는 전체 manifest 생성을 중단시킨다."""
    pass


def check_coregistration(mask_hdr, img_meta, patient):
    for k in ("dim_size_xyz",):
        if list(mask_hdr[k]) != list(img_meta[k]):
            raise DataQualityError(f"{patient}: mask/image {k} differ: {mask_hdr[k]} != {img_meta[k]}")
    for k in ("spacing_xyz", "offset_xyz"):
        a, b = mask_hdr[k], img_meta[k]
        if len(a) != len(b) or any(abs(float(x) - float(y)) > 1e-4 for x, y in zip(a, b)):
            raise DataQualityError(f"{patient}: mask/image {k} differ: {a} != {b}")
    if mask_hdr["direction"] != img_meta["direction"]:
        raise DataQualityError(f"{patient}: mask/image direction differ: {mask_hdr['direction']} != {img_meta['direction']}")


def instance_point_native(mask_vol, sag_idx, axes, label):
    """centroid에 가장 가까운 foreground pixel (row,col), half-open bbox 아님, 정확한 pixel 좌표."""
    array_axis_sag, array_axis_row, array_axis_col = axes
    sl = M.take_slice(mask_vol, array_axis_sag, array_axis_row, array_axis_col, sag_idx) == label
    rows, cols = np.where(sl)
    if rows.size == 0:
        raise RuntimeError("empty instance slice (should not happen for eligible instance)")
    cy, cx = rows.mean(), cols.mean()
    d2 = (rows - cy) ** 2 + (cols - cx) ** 2
    k = int(np.argmin(d2))
    return int(rows[k]), int(cols[k])


def build_one(pid, gate_entry, images_zc, masks_zc):
    mask_data, mask_sha = masks_zc.read(f"masks/{pid}_t2.mha")
    if mask_sha != gate_entry["mask_file_sha256"]:
        raise DataQualityError(f"{pid}: mask sha changed since gate")
    mask_m = M.read_mha(mask_data)
    mask_vol = mask_m["array"]
    try:
        img_data, img_sha = images_zc.read(f"images/{pid}_t2.mha")
    except KeyError as e:
        raise DataQualityError(f"{pid}: image zip member missing: {e}") from e
    try:
        img_m = M.read_mha(img_data)
    except M.MhaError as e:
        raise DataQualityError(f"{pid}: image mha parse error: {e}") from e
    img_meta = {"dim_size_xyz": img_m["dim_size_xyz"], "spacing_xyz": img_m["spacing_xyz"],
                "offset_xyz": img_m["offset_xyz"], "direction": img_m["direction"]}
    check_coregistration(gate_entry, img_meta, pid)
    img_vol = img_m["array"]
    axes = tuple(gate_entry["axes_sag_row_col"])
    array_axis_sag, array_axis_row, array_axis_col = axes
    idx_row, idx_col = 2 - array_axis_row, 2 - array_axis_col
    spacing_row, spacing_col = gate_entry["spacing_xyz"][idx_row], gate_entry["spacing_xyz"][idx_col]
    lo, hi = R.volume_window(img_vol)
    r_idx, t_idx = gate_entry["r_idx"], gate_entry["t_idx"]
    rgb_r, sr, sc, shape = R.render_slice(img_vol, r_idx, axes, spacing_row, spacing_col, lo, hi)
    rgb_t, sr_t, sc_t, shape_t = R.render_slice(img_vol, t_idx, axes, spacing_row, spacing_col, lo, hi)
    if shape != shape_t:
        raise RuntimeError(f"{pid}: R/T rendered shape differ {shape} vs {shape_t} (same volume expected identical)")
    top, left, side = geometry.pad_offsets(*shape)
    padded_r, aff_r = geometry.pad_square(rgb_r)
    padded_t, aff_t = geometry.pad_square(rgb_t)
    assert aff_r == (top, left, side) and aff_t == (top, left, side)

    img_dir = f"{DATA_DIR}/images"
    os.makedirs(img_dir, exist_ok=True)
    from PIL import Image
    path_r, path_t = f"{img_dir}/{pid}_R.png", f"{img_dir}/{pid}_T.png"
    Image.fromarray(padded_r).save(path_r)
    Image.fromarray(padded_t).save(path_t)
    file_sha_r = sha_bytes(open(path_r, "rb").read())
    file_sha_t = sha_bytes(open(path_t, "rb").read())
    pixel_sha_r = sha_bytes(padded_r.tobytes())
    pixel_sha_t = sha_bytes(padded_t.tobytes())

    instances = []
    for lab in gate_entry["chosen_instances"]:
        r_box_native = gate_entry["per_slice_boxes"]["r"][str(lab)]  # (r0,c0,r1,c1)
        t_box_native = gate_entry["per_slice_boxes"]["t"][str(lab)]
        ref_norm = R.native_bbox_to_norm(r_box_native, sr, sc, shape, (top, left, side))
        target_gt_norm = R.native_bbox_to_norm(t_box_native, sr, sc, shape, (top, left, side))
        pr, pc = instance_point_native(mask_vol, t_idx, axes, lab)
        point_norm = R.native_point_to_norm((pr, pc), sr, sc, shape, (top, left, side))
        instances.append({"label": lab, "ref_box_norm": ref_norm, "target_gt_norm": target_gt_norm,
                          "point_norm": point_norm})
    other_boxes_norm = []
    for lab, box_native in gate_entry["per_slice_boxes"]["t_all_others"].items():
        other_boxes_norm.append({"label": int(lab), "box_norm": R.native_bbox_to_norm(box_native, sr, sc, shape, (top, left, side))})

    return {
        "patient": pid, "r_idx": r_idx, "t_idx": t_idx, "dist_mm": gate_entry["dist_mm"],
        "mask_file_sha256": mask_sha, "image_file_sha256_source": img_sha,
        "spacing_xyz": gate_entry["spacing_xyz"], "volume_window": [lo, hi],
        "resize_scale_row_col": [sr, sc], "rendered_shape_hw": list(shape), "pad_top_left_side": [top, left, side],
        "R": {"path": path_r, "file_sha256": file_sha_r, "pixel_sha256": pixel_sha_r},
        "T": {"path": path_t, "file_sha256": file_sha_t, "pixel_sha256": pixel_sha_t},
        "instances": instances, "other_gt_boxes_in_T_norm": other_boxes_norm,
    }


def assign_split(patients):
    order = sorted(patients, key=lambda p: hashlib.sha256(f"{SPLIT_SALT}|{p}".encode()).hexdigest())
    d = order[:D_SIZE]
    e = order[D_SIZE:D_SIZE + E_SIZE]
    f = order[D_SIZE + E_SIZE:]
    return {"D": d, "E": e, "F": f, "order_salt": SPLIT_SALT}


def main():
    gate = json.load(open(f"{DATA_DIR}/gate.json"))
    eligible = {e["patient"]: e for e in gate["eligible"]}
    n = len(eligible)
    if n < 56:
        json.dump({"status": "insufficient_eligible", "n_eligible": n},
                  open(f"{DATA_DIR}/manifest_status.json", "w"), indent=1)
        print(json.dumps({"status": "insufficient_eligible", "n_eligible": n}))
        return
    images_zc = D.ZipCache(f"{SOURCE}/images.zip")
    masks_zc = D.ZipCache(f"{SOURCE}/masks.zip")
    manifest = {}
    errors = {}
    for pid in sorted(eligible):
        try:
            manifest[pid] = build_one(pid, eligible[pid], images_zc, masks_zc)
        except DataQualityError as e:
            # 자료상 부적격만 errors에 모아 조용히 제외한다. 그 외 예외(구현 버그)는 여기서
            # 잡지 않고 전파시켜 전체 자료 gate를 막는다 (fail-closed).
            errors[pid] = str(e)
    # split은 build 성공 환자에서만 배정한다: gate-eligible이어도 build_one이 실패하면
    # 조용히 제외하는 것이 아니라 errors.json에 남기고 split 대상에서 빠지게 한다.
    if len(manifest) < 56:
        json.dump({"status": "insufficient_built", "n_eligible": n, "n_built": len(manifest), "n_errors": len(errors)},
                  open(f"{DATA_DIR}/manifest_status.json", "w"), indent=1)
        json.dump(manifest, open(f"{DATA_DIR}/manifest.json", "w"), indent=1, default=str)
        json.dump(errors, open(f"{DATA_DIR}/manifest_errors.json", "w"), indent=1)
        print(json.dumps({"status": "insufficient_built", "n_eligible": n, "n_built": len(manifest)}))
        return
    split = assign_split(sorted(manifest))
    json.dump(split, open(f"{DATA_DIR}/split.json", "w"), indent=1)
    json.dump(manifest, open(f"{DATA_DIR}/manifest.json", "w"), indent=1, default=str)
    json.dump(errors, open(f"{DATA_DIR}/manifest_errors.json", "w"), indent=1)
    status = {"n_eligible": n, "n_built": len(manifest), "n_errors": len(errors),
              "split_sizes": {k: len(v) for k, v in split.items() if k != "order_salt"}}
    json.dump(status, open(f"{DATA_DIR}/manifest_status.json", "w"), indent=1)
    print(json.dumps(status, indent=1))


if __name__ == "__main__":
    main()
