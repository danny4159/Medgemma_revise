"""iter_019 SPIDER 자료 gate: T2 series 선택, mask 기반 slice-pair·인스턴스 선택, 표시 영상 렌더링.

정답 규약: vertebra instance label은 0<label<100 (저자 GenerateMetadataFile.py 범위와 실제 mask 값 대조로 확인).
슬라이스 축: DimSize=[nx,ny,nz] (AnatomicalOrientation RAI 확인 시 x=R축=sagittal slice index,
y=A축, z=I축). read_mha 배열은 (z,y,x); 슬라이스 2D 배열은 arr[:, :, x_idx] shape (nz, ny) = (row=z, col=y).
"""
import csv
import hashlib
import io
import json
import os
import re
import zipfile

import numpy as np
from PIL import Image

from . import geometry, mi19_mha as M

SOURCE = "results/iter_019/source"
DATA_DIR = "results/iter_019/data"
VERT_MAX_LABEL = 99  # 0 < label < 100
SLICE_SPACING_MIN_MM = 6.0
SLICE_SPACING_MAX_MM = 15.0
MIN_AREA_PX = 128
MIN_AREA_FRAC_OF_MAX = 0.20
MIN_BBOX_SIDE_PX = 8
MIN_COMMON_INSTANCES = 2
SALT = "iter019-reference-v1"


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def load_overview(path=f"{SOURCE}/overview.csv"):
    with open(path) as f:
        return list(csv.DictReader(f))


def t2_patients(rows):
    """returns sorted list of patient_id with 정확히 1개 regular t2 series (t1/t2_SPACE 제외)."""
    pat = {}
    for row in rows:
        m = re.match(r"^(.+?)_(t1|t2|t2_SPACE)$", row["new_file_name"])
        if not m:
            raise RuntimeError(f"unexpected new_file_name {row['new_file_name']!r}")
        pid, suf = m.group(1), m.group(2)
        if suf == "t2":
            pat.setdefault(pid, []).append(row)
    dup = {k: v for k, v in pat.items() if len(v) > 1}
    if dup:
        raise RuntimeError(f"duplicate regular t2 series for patients: {list(dup)[:5]}")
    return sorted(pat)


class ZipCache:
    """masks.zip/images.zip 멤버를 sha256과 함께 읽는다 (원저자 checksum과 별개로 매 멤버 자체 검증용)."""

    def __init__(self, path):
        self.zf = zipfile.ZipFile(path)

    def read(self, name):
        data = self.zf.read(name)
        return data, sha_bytes(data)


def instance_bboxes_per_slice(mask_vol):
    """mask_vol: (nz,ny,nx). returns {x_idx: {label: (row0,col0,row1,col1,area_px)}} for 0<label<=VERT_MAX_LABEL only.
    half-open bbox convention (row1,col1 = max index + 1)."""
    nz, ny, nx = mask_vol.shape
    labels = [int(v) for v in np.unique(mask_vol) if 0 < v <= VERT_MAX_LABEL]
    out = {x: {} for x in range(nx)}
    max_area = {}
    for lab in labels:
        lab_mask = mask_vol == lab
        for x in range(nx):
            sl = lab_mask[:, :, x]
            if not sl.any():
                continue
            rows = np.where(sl.any(axis=1))[0]
            cols = np.where(sl.any(axis=0))[0]
            r0, r1, c0, c1 = int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1
            area = int(sl.sum())
            out[x][lab] = (r0, c0, r1, c1, area)
            max_area[lab] = max(max_area.get(lab, 0), area)
    return out, max_area


def eligible_instances(per_slice_x, max_area, x):
    """x slice에서 최소 크기 조건을 만족하는 label 목록."""
    ok = []
    for lab, (r0, c0, r1, c1, area) in per_slice_x.get(x, {}).items():
        if area < MIN_AREA_PX:
            continue
        if max_area.get(lab, 0) <= 0 or area < MIN_AREA_FRAC_OF_MAX * max_area[lab]:
            continue
        if (r1 - r0) < MIN_BBOX_SIDE_PX or (c1 - c0) < MIN_BBOX_SIDE_PX:
            continue
        ok.append(lab)
    return sorted(ok)


def deterministic_choice(seq, salt_key):
    """salt_key의 sha256 정수값으로 seq(정렬된 list)에서 하나를 결정적으로 고른다."""
    h = int(hashlib.sha256(salt_key.encode()).hexdigest(), 16)
    return seq[h % len(seq)]


def candidate_pairs(per_slice_x, max_area, spacing_x, nx):
    """물리 간격 6-15mm, 공통 eligible instance>=2인 (x1,x2) 쌍과 공통 instance 목록. x1<x2로 정규화."""
    elig = {x: set(eligible_instances(per_slice_x, max_area, x)) for x in range(nx)}
    pairs = []
    for x1 in range(nx):
        for x2 in range(x1 + 1, nx):
            dist_mm = abs(x2 - x1) * spacing_x
            if not (SLICE_SPACING_MIN_MM <= dist_mm <= SLICE_SPACING_MAX_MM):
                continue
            common = sorted(elig[x1] & elig[x2])
            if len(common) >= MIN_COMMON_INSTANCES:
                pairs.append((x1, x2, common, dist_mm))
    return pairs


def select_patient_pair(pid, mask_vol, spacing_x):
    nz, ny, nx = mask_vol.shape
    per_slice_x, max_area = instance_bboxes_per_slice(mask_vol)
    pairs = candidate_pairs(per_slice_x, max_area, spacing_x, nx)
    if not pairs:
        return None, {"n_candidate_pairs": 0}
    # 결정적 선택: (x1,x2) 쌍 -> salt로 하나 선택, 그 다음 공통 instance 중 2개를 salt로 선택
    pair_keys = [f"{pid}|pair|{x1}|{x2}" for x1, x2, _, _ in pairs]
    idx = int(hashlib.sha256(f"{pid}|pairsel".encode()).hexdigest(), 16) % len(pairs)
    x1, x2, common, dist_mm = pairs[idx]
    if len(common) > 2:
        # 두 인스턴스를 salt 순서로 선택 (SHA256(salt|label) 오름차순 상위 2개)
        common_sorted = sorted(common, key=lambda lab: hashlib.sha256(f"{SALT}|{pid}|{lab}".encode()).hexdigest())
        inst2 = sorted(common_sorted[:2])
    else:
        inst2 = common
    # R/T 역할: salt로 x1/x2 중 하나를 R로
    r_is_x1 = int(hashlib.sha256(f"{pid}|rrole".encode()).hexdigest(), 16) % 2 == 0
    r_idx, t_idx = (x1, x2) if r_is_x1 else (x2, x1)
    info = {"n_candidate_pairs": len(pairs), "chosen_pair": [x1, x2], "dist_mm": dist_mm,
            "common_instances_all": common, "chosen_instances": inst2, "r_idx": r_idx, "t_idx": t_idx}
    return (r_idx, t_idx, inst2, per_slice_x), info


def gate_patients(overview_rows, out_dir=DATA_DIR):
    """모든 t2 patients에 대해 mask 기반 적격성 검사. returns (eligible list of dict, excluded list of dict)."""
    zc = ZipCache(f"{SOURCE}/masks.zip")
    pids = t2_patients(overview_rows)
    eligible, excluded = [], []
    for pid in pids:
        name = f"masks/{pid}_t2.mha"
        try:
            data, filesha = zc.read(name)
        except KeyError:
            excluded.append({"patient": pid, "reason": "mask_file_missing"})
            continue
        try:
            m = M.read_mha(data)
        except M.MhaError as e:
            excluded.append({"patient": pid, "reason": f"mha_parse_error: {e}"})
            continue
        vol = m["array"]
        nz, ny, nx = vol.shape
        sx, sy, sz = m["spacing_xyz"]
        if nx < 2:
            excluded.append({"patient": pid, "reason": "single_slice_volume"})
            continue
        sel, info = select_patient_pair(pid, vol, sx)
        info.update({"patient": pid, "mask_file_sha256": filesha, "dim_size_xyz": m["dim_size_xyz"],
                     "spacing_xyz": m["spacing_xyz"], "offset_xyz": m["offset_xyz"], "direction": m["direction"]})
        if sel is None:
            excluded.append({**info, "reason": "no_candidate_slice_pair"})
            continue
        r_idx, t_idx, inst2, per_slice_x = sel
        eligible.append({**info, "per_slice_boxes": {
            "r": {str(lab): per_slice_x[r_idx][lab][:4] for lab in inst2},
            "t": {str(lab): per_slice_x[t_idx][lab][:4] for lab in inst2},
            "t_all_others": {str(lab): box[:4] for lab, box in per_slice_x[t_idx].items() if lab not in inst2},
        }})
    return eligible, excluded


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = load_overview()
    eligible, excluded = gate_patients(rows)
    out = {"n_t2_patients": len(t2_patients(rows)), "n_eligible": len(eligible), "n_excluded": len(excluded),
           "excluded_reason_counts": {}, }
    for e in excluded:
        r = e["reason"].split(":")[0]
        out["excluded_reason_counts"][r] = out["excluded_reason_counts"].get(r, 0) + 1
    json.dump({"eligible": eligible, "excluded": excluded, "summary": out}, open(f"{DATA_DIR}/gate.json", "w"), indent=1, default=str)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
