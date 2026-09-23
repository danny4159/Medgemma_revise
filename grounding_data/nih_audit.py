"""NIH 개발 split 재감사와 fail-closed readiness (iter_006, CPU 전용, 네트워크 없음).

입력은 모두 읽기 전용이다 (iter_005가 받은 metadata·영상·manifest·provenance). 새 자료를 받거나
표본을 바꾸지 않는다.

- `run_checks()`는 필수 검사마다 {"pass": bool, "detail": ...}를 만든다. 검사 도중 예외도 실패로 기록한다.
- `readiness()`는 REQUIRED_CHECKS의 모든 key가 존재하고 값이 정확히 True일 때만 integrity gate를 통과시킨다
  (누락·None·문자열 등은 실패). 엄격한 `lesion_probe_ready`는 여기에 좌표 canvas의 직접 문서 근거를 더 요구한다.
- 경고(warnings)는 readiness를 바꾸지 않는다. 미러와 원배포의 동일성 미확인은 provenance 한계로 따로 남긴다.
"""
import hashlib
import io
import json
import math
import os

import numpy as np
from PIL import Image

from . import nih
from .net import git_blob_sha1, sha256_bytes

META_FILES = ["README.md", "data/BBox_List_2017.csv", "data/Data_Entry_2017_v2020.csv",
              "data/test_list.txt", "data/train_val_list.txt"]
CANVAS = (1024, 1024)
MAIN_CLASSES = ["Atelectasis", "Effusion", "Cardiomegaly", "Pneumonia"]

REQUIRED_CHECKS = [
    "meta_blob_integrity",          # metadata 파일의 git blob id·sha256이 기록과 일치
    "bbox_header_format",           # header core·trailing 빈 열, 행 형식(열 수·trailing 값·빈 행)
    "bbox_coords_finite_positive",  # 유한 좌표, 양의 w/h, 음수 원점 없음
    "bbox_within_assumed_canvas",   # 1024 canvas 가정 아래 범위 밖 좌표 없음 (가정의 반증 검사)
    "metadata_ids_unique",          # Data_Entry·공식 목록의 ID 중복 없음, test/train_val 겹침 없음
    "finding_link",                 # bbox 영상이 Data_Entry에 있고 bbox 클래스가 해당 영상 finding에 포함
    "patient_link",                 # filename prefix = Patient ID, manifest patient = Data_Entry patient
    "annotation_matches_csv",       # manifest annotation = CSV에서 재구성한 annotation (hash 포함)
    "split_reproducible",           # metadata 규칙으로 재생성한 split = manifest split
    "split_sizes_160_80_32_48",
    "main_classes_meet_minimum",    # 주분석 4클래스가 split별 최소 인원 충족
    "images_hash_size",             # 실제 영상 file·pixel hash, 1024x1024 크기
    "split_no_overlap",             # split 간 patient·image·file·pixel 중복 없음 (실제 영상 기준)
]

_IMG_CACHE = {}


def _fail(detail):
    return {"pass": False, "detail": detail}


def _ok(detail=None):
    return {"pass": True, "detail": detail}


def image_facts(path):
    """(abs path, size, mtime) memo. 값: file sha256, pixel sha256, 크기, mode."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if key not in _IMG_CACHE:
        data = open(path, "rb").read()
        im = Image.open(io.BytesIO(data))
        im.load()
        a = np.ascontiguousarray(np.asarray(im))
        h = hashlib.sha256()
        h.update(f"{a.dtype}|{a.shape}|".encode())
        h.update(a.tobytes())
        _IMG_CACHE[key] = {"file_sha256": sha256_bytes(data), "pixel_sha256": h.hexdigest(),
                           "width": im.size[0], "height": im.size[1], "mode": im.mode}
    return _IMG_CACHE[key]


def load_inputs(src):
    """iter_005 결과 디렉터리에서 감사 입력을 읽는다 (읽기 전용)."""
    meta_dir = os.path.join(src, "data", "nih", "meta")
    meta = {f: open(os.path.join(meta_dir, f.replace("/", "__")), "rb").read() for f in META_FILES}
    prov = json.load(open(os.path.join(src, "provenance.json")))
    manifest = json.load(open(os.path.join(src, "nih_manifest.json")))
    img_dir = os.path.join(src, "data", "nih", "images")
    paths = {r["image"]: os.path.join(img_dir, r["image"]) for r in manifest}
    return {"meta": meta, "prov_meta": prov.get("nih_meta_files", {}), "manifest": manifest, "image_paths": paths}


def _check(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # 검사 도중 예외 = 실패
        return _fail({"exception": repr(e)[:300]})


def c_meta_blob(meta, prov_meta):
    bad = []
    for f in META_FILES:
        p = prov_meta.get(f) or {}
        body = meta.get(f)
        if body is None:
            bad.append({"file": f, "what": "missing_file"})
            continue
        blob = p.get("listed_git_blob_id")
        if not blob:
            bad.append({"file": f, "what": "no_listed_blob_id"})
        elif git_blob_sha1(body) != blob:
            bad.append({"file": f, "what": "git_blob_mismatch"})
        if p.get("sha256") != sha256_bytes(body):
            bad.append({"file": f, "what": "sha256_mismatch_vs_recorded"})
    return _ok({"n_files": len(META_FILES)}) if not bad else _fail(bad)


def c_bbox_header(rep):
    bad = []
    if not rep["header_core_matches_expected"]:
        bad.append({"what": "header_core_mismatch", "header": rep["raw_header"]})
    if not rep["trailing_header_all_empty"]:
        bad.append({"what": "trailing_header_not_empty", "trailing": rep["trailing_header_cols"]})
    short = {k: v for k, v in rep["row_col_counts"].items() if k < 6}
    if short:
        bad.append({"what": "rows_with_fewer_than_6_cols", "counts": short})
    if rep["problems"]:
        bad.append({"what": "row_problems", "problems": rep["problems"][:10], "n": len(rep["problems"])})
    if rep["n_boxes"] != rep["n_rows"]:
        bad.append({"what": "rows_not_parsed", "n_rows": rep["n_rows"], "n_boxes": rep["n_boxes"]})
    return _ok({"n_rows": rep["n_rows"], "row_col_counts": rep["row_col_counts"]}) if not bad else _fail(bad)


def c_coords(boxes):
    bad = []
    for b in boxes:
        x, y, w, h = b["xywh"]
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            bad.append({"line": b["line"], "what": "non_finite", "xywh": [str(v) for v in b["xywh"]]})
        elif w <= 0 or h <= 0:
            bad.append({"line": b["line"], "what": "non_positive_size", "xywh": b["xywh"]})
        elif x < 0 or y < 0:
            bad.append({"line": b["line"], "what": "negative_origin", "xywh": b["xywh"]})
    return _ok({"n_boxes": len(boxes)}) if not bad else _fail(bad[:20])


def c_canvas(boxes):
    oob = [b for b in boxes if all(math.isfinite(v) for v in b["xyxy"])
           and (b["xyxy"][2] > CANVAS[0] or b["xyxy"][3] > CANVAS[1])]
    fin = [b["xyxy"] for b in boxes if all(math.isfinite(v) for v in b["xyxy"])]
    det = {"max_x1_y1": [max(v[2] for v in fin), max(v[3] for v in fin)] if fin else None,
           "min_x0_y0": [min(v[0] for v in fin), min(v[1] for v in fin)] if fin else None,
           "note": "가정한 1024 canvas의 반증 검사일 뿐 canvas 근거가 아니다"}
    if oob:
        return _fail({**det, "out_of_canvas_lines": [b["line"] for b in oob][:20]})
    return _ok(det)


def c_ids_unique(entry_rep, test_list, trainval_list):
    bad = []
    if entry_rep["duplicate_image_ids"]:
        bad.append({"what": "data_entry_duplicate_ids", "ids": entry_rep["duplicate_image_ids"][:10]})
    for name, lst in (("test_list", test_list), ("train_val_list", trainval_list)):
        if len(lst) != len(set(lst)):
            bad.append({"what": f"{name}_duplicate_ids", "n": len(lst) - len(set(lst))})
    ov = set(test_list) & set(trainval_list)
    if ov:
        bad.append({"what": "test_trainval_overlap", "n": len(ov)})
    return _ok({"n_data_entry": entry_rep["n_unique_images"], "n_test": len(test_list),
                "n_train_val": len(trainval_list)}) if not bad else _fail(bad)


def c_finding(link_rep):
    bad = []
    if link_rep["images_missing_in_data_entry"]:
        bad.append({"what": "bbox_images_missing_in_data_entry", "ids": link_rep["images_missing_in_data_entry"][:10]})
    if link_rep["bbox_label_not_in_entry_labels"]:
        bad.append({"what": "bbox_label_not_in_image_findings", "rows": link_rep["bbox_label_not_in_entry_labels"][:10],
                    "n": len(link_rep["bbox_label_not_in_entry_labels"])})
    unmapped = [l for l in link_rep["bbox_labels_not_in_entry_vocab"] if l not in nih.BBOX_TO_ENTRY_LABEL]
    if unmapped:
        bad.append({"what": "bbox_label_outside_vocab_without_mapping", "labels": unmapped})
    return _ok({"n_consistent": link_rep["bbox_label_in_entry_labels"],
                "mapping": nih.BBOX_TO_ENTRY_LABEL}) if not bad else _fail(bad)


def c_patient(link_rep, manifest, entries):
    bad = []
    if link_rep["patient_id_prefix_mismatch"]:
        bad.append({"what": "filename_prefix_vs_patient_id", "rows": link_rep["patient_id_prefix_mismatch"][:10]})
    for r in manifest:
        e = entries.get(r["image"])
        if e is None or int(e["Patient ID"]) != int(r["patient_id"]):
            bad.append({"what": "manifest_patient_vs_data_entry", "image": r["image"], "manifest": r["patient_id"],
                        "data_entry": e and e["Patient ID"]})
    return _ok({"n_manifest": len(manifest)}) if not bad else _fail(bad[:20])


def _ann(bl):
    return [{"line": b["line"], "label": b["label"], "xywh": b["xywh"], "xyxy": b["xyxy"]} for b in bl]


def c_annotation(manifest, boxes):
    by = {}
    for b in boxes:
        by.setdefault(b["image"], []).append(b)
    bad = []
    for r in manifest:
        ann = _ann(by.get(r["image"], []))
        h = hashlib.sha256(json.dumps(ann, sort_keys=True).encode()).hexdigest()
        if ann != r.get("annotation") or h != r.get("annotation_sha256"):
            bad.append({"image": r["image"], "what": "annotation_differs_from_csv"})
        if sorted({a["label"] for a in ann}) != r.get("bbox_classes"):
            bad.append({"image": r["image"], "what": "bbox_classes_differs"})
    return _ok({"n": len(manifest)}) if not bad else _fail(bad[:20])


def c_split_repro(manifest, boxes, entries):
    assign, info = nih.make_dev_split(boxes, entries)
    want = {pid: (a["split"], a["image"], a["stratum"]) for pid, a in assign.items()}
    got = {}
    dup = []
    for r in manifest:
        if r["patient_id"] in got:
            dup.append(r["patient_id"])
        got[r["patient_id"]] = (r["split"], r["image"], r["stratum"])
    diff = sorted(set(want) ^ set(got)) + sorted(p for p in set(want) & set(got) if want[p] != got[p])
    if diff or dup:
        return _fail({"n_diff": len(diff), "examples": diff[:10], "duplicate_patient_rows": dup[:10]})
    return _ok({"seed": info["seed"], "strata": info["strata"]}), assign


def c_sizes(manifest):
    sizes = {s: sum(1 for r in manifest if r["split"] == s) for s in nih.SPLIT_SIZES}
    n_pat = len({r["patient_id"] for r in manifest})
    ok = sizes == nih.SPLIT_SIZES and len(manifest) == nih.N_PATIENTS and n_pat == nih.N_PATIENTS
    return (_ok if ok else _fail)({"sizes": sizes, "n_rows": len(manifest), "n_patients": n_pat})


def c_classes(manifest):
    cc = {c: {s: 0 for s in nih.SPLIT_SIZES} for c in MAIN_CLASSES}
    for r in manifest:
        for c in set(a["label"] for a in r["annotation"]):
            if c in cc:
                cc[c][r["split"]] += 1
    short = {c: v for c, v in cc.items() if any(v[s] < nih.MIN_PER_CLASS[s] for s in nih.MIN_PER_CLASS)}
    return (_ok if not short else _fail)({"counts": cc, "min": nih.MIN_PER_CLASS, "short": short})


def c_images(manifest, image_paths):
    bad, facts = [], {}
    for r in manifest:
        p = image_paths.get(r["image"])
        if p is None or not os.path.exists(p):
            bad.append({"image": r["image"], "what": "missing_file"})
            continue
        f = image_facts(p)
        facts[r["image"]] = f
        for k in ("file_sha256", "pixel_sha256"):
            if f[k] != r.get(k):
                bad.append({"image": r["image"], "what": f"{k}_mismatch"})
        if (f["width"], f["height"]) != CANVAS or (r.get("width"), r.get("height")) != CANVAS:
            bad.append({"image": r["image"], "what": "size_not_1024", "actual": [f["width"], f["height"]]})
    modes = {}
    for f in facts.values():
        modes[f["mode"]] = modes.get(f["mode"], 0) + 1
    return ((_ok({"n": len(facts), "modes": modes}) if not bad else _fail(bad[:20])), facts)


def c_overlap(manifest, facts):
    bad = {}
    for key, get in (("patient", lambda r: r["patient_id"]), ("image", lambda r: r["image"]),
                     ("file_sha256", lambda r: facts.get(r["image"], {}).get("file_sha256")),
                     ("pixel_sha256", lambda r: facts.get(r["image"], {}).get("pixel_sha256"))):
        seen = {}
        for r in manifest:
            v = get(r)
            if v is None:
                bad.setdefault("missing_values", []).append({"key": key, "image": r["image"]})
                continue
            seen.setdefault(v, []).append(r["split"])
        cross = [v for v, s in seen.items() if len(set(s)) > 1]
        within = [v for v, s in seen.items() if len(s) > 1 and len(set(s)) == 1]
        if cross:
            bad[f"{key}_across_splits"] = len(cross)
        if within:
            bad[f"{key}_within_split"] = len(within)
    return _ok({"n": len(manifest)}) if not bad else _fail(bad)


def run_checks(inp):
    """필수 검사 결과(dict)와 경고, 재생성 산출물(ctx)을 돌려준다."""
    meta, man = inp["meta"], inp["manifest"]
    checks, warnings, ctx = {}, [], {}
    checks["meta_blob_integrity"] = _check(c_meta_blob, meta, inp["prov_meta"])
    try:
        boxes, bbox_rep = nih.parse_bbox_csv(meta["data/BBox_List_2017.csv"].decode("utf-8"))
        entries, entry_rep = nih.parse_data_entry(meta["data/Data_Entry_2017_v2020.csv"].decode("utf-8"))
        test_list = nih.parse_list(meta["data/test_list.txt"].decode("utf-8"))
        trainval_list = nih.parse_list(meta["data/train_val_list.txt"].decode("utf-8"))
        link_rep, split_of = nih.link_boxes(boxes, entries, test_list, trainval_list)
    except Exception as e:  # 파싱 불가 = 이후 검사 모두 실패
        for k in REQUIRED_CHECKS:
            checks.setdefault(k, _fail({"parse_exception": repr(e)[:300]}))
        return checks, warnings, ctx
    checks["bbox_header_format"] = _check(c_bbox_header, bbox_rep)
    checks["bbox_coords_finite_positive"] = _check(c_coords, boxes)
    checks["bbox_within_assumed_canvas"] = _check(c_canvas, boxes)
    checks["metadata_ids_unique"] = _check(c_ids_unique, entry_rep, test_list, trainval_list)
    checks["finding_link"] = _check(c_finding, link_rep)
    checks["patient_link"] = _check(c_patient, link_rep, man, entries)
    checks["annotation_matches_csv"] = _check(c_annotation, man, boxes)
    try:
        res = c_split_repro(man, boxes, entries)
        checks["split_reproducible"] = res[0] if isinstance(res, tuple) else res
    except Exception as e:
        checks["split_reproducible"] = _fail({"exception": repr(e)[:300]})
    checks["split_sizes_160_80_32_48"] = _check(c_sizes, man)
    checks["main_classes_meet_minimum"] = _check(c_classes, man)
    try:
        checks["images_hash_size"], facts = c_images(man, inp["image_paths"])
    except Exception as e:
        checks["images_hash_size"], facts = _fail({"exception": repr(e)[:300]}), {}
    checks["split_no_overlap"] = _check(c_overlap, man, facts)
    # 경고 (readiness 불변)
    if link_rep["exact_duplicate_box_lines"]:
        warnings.append({"what": "exact_duplicate_box_lines", "lines": link_rep["exact_duplicate_box_lines"][:10]})
    if link_rep["bbox_labels_not_in_entry_vocab"]:
        warnings.append({"what": "bbox_label_spelling_mapped", "labels": link_rep["bbox_labels_not_in_entry_vocab"],
                         "mapping": nih.BBOX_TO_ENTRY_LABEL})
    off = {split_of.get(r["image"]) for r in man}
    warnings.append({"what": "selected_images_official_split", "values": sorted(v for v in off if v),
                     "note": "bbox 영상은 모두 공식 test 소속: 공식 benchmark test 성능이 아닌 개발 split"})
    ctx.update({"boxes": boxes, "entries_n": len(entries), "link": link_rep, "bbox_rep": bbox_rep, "facts": facts})
    return checks, warnings, ctx


def readiness(checks, canvas_status):
    """fail-closed: 필수 key 누락·값이 정확히 True가 아닌 경우 모두 실패."""
    failed = [k for k in REQUIRED_CHECKS if not (isinstance(checks.get(k), dict) and checks[k].get("pass") is True)]
    missing = [k for k in REQUIRED_CHECKS if k not in checks]
    integrity = not failed
    blockers = [{"what": "required_check_failed", "check": k} for k in failed]
    if canvas_status != "documented_direct":
        blockers.append({"what": "coordinate_canvas_not_directly_documented", "canvas_status": canvas_status,
                         "detail": "영상 해상도 1024와 xywh 의미는 문서화되어 있으나 bbox 좌표계를 1024 PNG로 "
                                   "지정하는 직접 문장이 없다. 영상 크기·좌표 범위·overlay로 승격하지 않는다."})
    return {"integrity_gate_pass": integrity, "failed_required_checks": failed, "missing_required_checks": missing,
            "coordinate_canvas_status": canvas_status,
            "lesion_probe_ready": bool(integrity and canvas_status == "documented_direct"),
            "lesion_probe_ready_definition": "integrity_gate_pass AND coordinate_canvas_status == documented_direct",
            "blockers": blockers}
