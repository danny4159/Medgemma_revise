"""iter_005 grounding 데이터 준비·검증 entry point (CPU 전용, GPU 0, 모델 로딩 없음).

실행: python research/prepare_grounding_data.py --out research/results/iter_005

단계
  env   : interpreter·package·경로·네트워크 확인
  nih   : 고정 revision 미러의 metadata 다운로드 → bbox/patient/공식 split 파싱·연결 →
          ZIP central directory(HTTP Range) → 고정 8개 접근 검증 → patient 단위 개발 split(160명) 영상 확보 →
          file/pixel/annotation hash, canvas 검증, split 간 중복 검사
  scr   : Zenodo 원저자 배포 jpg.zip·masks.zip 다운로드(md5 검증) → 파일명·해상도·mask 형식·organ 대응
  out   : manifest, ledger, overlay(train/validation만, 최대 12), target npz, readiness JSON
다운로드 예산: 누적 256 MiB, 네트워크 20분, 파일(범위 요청)별 최대 2회 시도 (grounding_data/net.py).
이미 받은 파일은 hash가 맞으면 다시 받지 않는다.
"""
import argparse
import hashlib
import importlib.metadata as md
import io
import json
import os
import platform
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grounding_data import net, nih, scr  # noqa: E402
from grounding_data import targets as T  # noqa: E402

NIH_REVISION = "36778e3b0e4f4b4fad31d1728d6190f3eda5b543"  # 2026-09-24 조회한 HF dataset commit
NIH_BASE = f"https://huggingface.co/datasets/{nih.HF_REPO}/resolve/{NIH_REVISION}/"
NIH_META_FILES = ["README.md", "data/BBox_List_2017.csv", "data/Data_Entry_2017_v2020.csv",
                  "data/test_list.txt", "data/train_val_list.txt"]
N_ACCESS_CHECK = 8
ZENODO_API = f"https://zenodo.org/api/records/{scr.ZENODO_RECORD}"
SCR_FILES = ["jpg.zip", "masks.zip"]
MAX_OVERLAYS = 12


def dump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def pixel_sha256(a):
    a = np.ascontiguousarray(a)
    h = hashlib.sha256()
    h.update(f"{a.dtype}|{a.shape}|".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def env_stage(out):
    pk = {}
    for p in ["numpy", "pillow", "requests", "huggingface_hub", "torch", "transformers", "pandas", "scipy"]:
        try:
            pk[p] = md.version(p)
        except md.PackageNotFoundError:
            pk[p] = None
    rec = {"sys_executable": sys.executable, "python": platform.python_version(), "packages": pk,
           "expected_env": "conda env medgemma (python 3.11)",
           "env_matches_expected": "/envs/medgemma/" in sys.executable and platform.python_version().startswith("3.11"),
           "cwd": os.getcwd(), "out": os.path.abspath(out), "gpu_used": False,
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    return rec


# ---------------------------------------------------------------- NIH

def nih_fetch_meta(ledger, meta_dir, prov):
    from huggingface_hub import HfApi
    info = HfApi().dataset_info(nih.HF_REPO, revision=NIH_REVISION, files_metadata=True)
    sib = {s.rfilename: s for s in info.siblings}
    prov["hf_dataset"] = {"repo": nih.HF_REPO, "revision_requested": NIH_REVISION, "revision_resolved": info.sha,
                          "card_source_note": "미러. NIH 원배포(Box)와의 파일 동일성은 이번에 검증하지 않음 (unverified)"}
    out = {}
    for f in NIH_META_FILES:
        s = sib[f]
        local = os.path.join(meta_dir, f.replace("/", "__"))
        blob = getattr(s, "blob_id", None)
        if os.path.exists(local) and blob and net.git_blob_sha1(open(local, "rb").read()) == blob:
            body = open(local, "rb").read()
            fetched = "cached"
        else:
            body = ledger.get(NIH_BASE + f, f"nih_meta:{f}", expect_bytes=s.size or 0)
            with open(local, "wb") as fh:
                fh.write(body)
            fetched = "downloaded"
        out[f] = body.decode("utf-8")
        prov.setdefault("nih_meta_files", {})[f] = {
            "url": NIH_BASE + f, "listed_size": s.size, "bytes": len(body), "sha256": net.sha256_bytes(body),
            "listed_git_blob_id": blob, "git_blob_sha1": net.git_blob_sha1(body),
            "git_blob_verified": (blob == net.git_blob_sha1(body)) if blob else "unverified",
            "public_checksum": "HF git blob id (mirror 내부 무결성; 원본 동일성은 아님)" if blob else None,
            "local": local, "fetch": fetched}
    zips = {f: {"size": sib[f].size, "lfs_sha256": sib[f].lfs.sha256 if sib[f].lfs else None}
            for f in sib if f.startswith("data/images/") and f.endswith(".zip")}
    return out, zips


def nih_stage(ledger, out, prov, problems):
    meta_dir = os.path.join(out, "data", "nih", "meta")
    img_dir = os.path.join(out, "data", "nih", "images")
    os.makedirs(meta_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    res = {"status": "started"}
    meta, zips = nih_fetch_meta(ledger, meta_dir, prov)
    readme = meta["README.md"]
    res["readme_canvas_mentions"] = [ln.strip() for ln in readme.splitlines() if "1024" in ln][:10]
    boxes, bbox_rep = nih.parse_bbox_csv(meta["data/BBox_List_2017.csv"])
    entries, entry_rep = nih.parse_data_entry(meta["data/Data_Entry_2017_v2020.csv"])
    test_list = nih.parse_list(meta["data/test_list.txt"])
    trainval_list = nih.parse_list(meta["data/train_val_list.txt"])
    link_rep, split_of = nih.link_boxes(boxes, entries, test_list, trainval_list)
    res["bbox_csv"] = bbox_rep
    res["data_entry"] = {k: v for k, v in entry_rep.items() if k != "duplicate_image_ids"}
    res["data_entry"]["n_duplicate_image_ids"] = len(entry_rep["duplicate_image_ids"])
    res["official_lists"] = {"n_test": len(test_list), "n_train_val": len(trainval_list),
                             "overlap": len(set(test_list) & set(trainval_list))}
    res["link"] = link_rep
    # 좌표 canvas 가설(1024x1024)은 실제 영상으로 검증하기 전까지 가설이다
    res["bbox_out_of_canvas_1024_raw"] = nih.canvas_checks(boxes)
    orig_sizes = {}
    for b in boxes:
        e = entries.get(b["image"], {})
        orig_sizes[e.get("OriginalImage[Width", "?")] = orig_sizes.get(e.get("OriginalImage[Width", "?"), 0) + 1
    res["data_entry_original_width_values_for_bbox_images_top"] = sorted(orig_sizes.items(), key=lambda x: -x[1])[:5]

    # ZIP central directory (HTTP Range)
    zip_index, zip_objs = {}, {}
    res["zip_access"] = {}
    for zname in sorted(zips):
        cd_cache = os.path.join(out, "data", "nih", "zip_central_dir_cache")
        os.makedirs(cd_cache, exist_ok=True)
        rf = net.HTTPRangeFile(ledger, NIH_BASE + zname, zips[zname]["size"], f"nih_zip:{zname.split('/')[-1]}",
                               disk_cache_dir=cd_cache)
        try:
            zi = nih.ZipIndex(rf)
        except net.RangeNotSupported as e:
            res["zip_access"][zname] = {"ok": False, "error": str(e)}
            res["status"] = "blocked_range_not_supported"
            problems.append({"stage": "nih_zip", "zip": zname, "error": str(e)})
            return res, None
        zip_objs[zname] = zi
        for m in zi.members:
            if m in zip_index:
                problems.append({"stage": "nih_zip", "what": "member_in_multiple_zips", "member": m})
            zip_index[m] = zname
        res["zip_access"][zname] = {"ok": True, "n_members": len(zi.members), "size": zips[zname]["size"],
                                    "archive_sha256_listed": zips[zname]["lfs_sha256"],
                                    "archive_sha256_verified": "unverified (partial range read)"}
    res["n_zip_members_total"] = len(zip_index)
    bbox_imgs = sorted({b["image"] for b in boxes})
    res["bbox_images_found_in_zips"] = sum(1 for i in bbox_imgs if i in zip_index)
    res["bbox_images_missing_in_zips"] = [i for i in bbox_imgs if i not in zip_index]
    all_entry_in_zips = sum(1 for i in entries if i in zip_index)
    res["data_entry_images_found_in_zips"] = all_entry_in_zips

    fetched = {}

    def fetch(img):
        if img in fetched:
            return fetched[img]
        rec = {"image": img, "zip": zip_index.get(img)}
        local = os.path.join(img_dir, img)
        if rec["zip"] is None:
            rec["status"] = "join_failed_not_in_zip"
            fetched[img] = rec
            return rec
        zi = zip_objs[rec["zip"]]
        info = zi.members[img]
        try:
            if os.path.exists(local) and os.path.getsize(local) == info.file_size:
                data = open(local, "rb").read()
                import zlib
                if f"{zlib.crc32(data) & 0xffffffff:08x}" != f"{info.CRC:08x}":
                    raise IOError("cached file CRC mismatch")
                meta_m = {"member": info.filename, "crc32": f"{info.CRC:08x}", "file_size": info.file_size,
                          "compress_size": info.compress_size, "cached": True}
            else:
                data, meta_m = zi.read_member(img)
                with open(local, "wb") as fh:
                    fh.write(data)
        except (net.BudgetExceeded, net.RangeNotSupported):
            raise
        except Exception as e:
            rec["status"] = "download_failed"
            rec["error"] = repr(e)[:200]
            fetched[img] = rec
            return rec
        rec.update({"zip_member": meta_m, "local": local, "bytes": len(data), "file_sha256": net.sha256_bytes(data),
                    "crc32_verified": True, "source_url": NIH_BASE + rec["zip"]})
        try:
            im, a = nih.decode_png(data)
            rec.update({"width": im.size[0], "height": im.size[1], "mode": im.mode, "dtype": str(a.dtype),
                        "shape": list(a.shape), "pixel_sha256": pixel_sha256(a)})
            rec["status"] = "ok"
        except Exception as e:
            rec["status"] = "decode_failed"
            rec["error"] = repr(e)[:200]
        fetched[img] = rec
        return rec

    # 1) 고정 8개 접근 검증: bbox CSV 등장 순서의 첫 8개 영상
    first8 = []
    for b in boxes:
        if b["image"] not in first8:
            first8.append(b["image"])
        if len(first8) == N_ACCESS_CHECK:
            break
    res["access_check_ids"] = first8
    acc = [fetch(i) for i in first8]
    res["access_check"] = [{k: r.get(k) for k in ("image", "status", "width", "height", "mode", "bytes")} for r in acc]
    if not all(r["status"] == "ok" for r in acc):
        res["status"] = "blocked_access_check_failed"
        return res, None

    # 2) 분할 고정 (영상 내용·모델 출력과 무관한 metadata 규칙) → 선택 영상 확보
    assign, split_info = nih.make_dev_split(boxes, entries)
    res["split_info"] = split_info
    for pid in sorted(assign, key=int):
        img = assign[pid]["image"]
        r = fetch(img)
        if r["status"] != "ok":
            problems.append({"stage": "nih_fetch", "image": img, "status": r["status"], "error": r.get("error")})
    res["ledger_after_nih_bytes"] = ledger.data["bytes_total"]
    return res, {"boxes": boxes, "entries": entries, "assign": assign, "fetched": fetched, "split_of": split_of}


def nih_manifest(ctx, res, out, problems):
    boxes, entries, assign, fetched, split_of = (ctx[k] for k in ("boxes", "entries", "assign", "fetched", "split_of"))
    by_img = {}
    for b in boxes:
        by_img.setdefault(b["image"], []).append(b)
    rows, targets_fine, target_ids = [], [], []
    canvas_sizes = {}
    for r in fetched.values():
        if r["status"] == "ok":
            k = f"{r['width']}x{r['height']}|{r['mode']}"
            canvas_sizes[k] = canvas_sizes.get(k, 0) + 1
    res["fetched_image_canvas_sizes"] = canvas_sizes
    all_1024 = set(canvas_sizes) <= {"1024x1024|L"} or all(k.startswith("1024x1024|") for k in canvas_sizes)
    readme_1024 = any("1024" in ln for ln in res.get("readme_canvas_mentions", []))
    for pid in sorted(assign, key=int):
        a = assign[pid]
        img = a["image"]
        f = fetched.get(img, {"status": "not_fetched"})
        bl = by_img[img]
        ann = [{"line": b["line"], "label": b["label"], "xywh": b["xywh"], "xyxy": b["xyxy"]} for b in bl]
        e = entries[img]
        row = {"patient_id": pid, "patient_id_source": "Data_Entry_2017_v2020.csv:Patient ID",
               "filename_prefix_check": int(nih.filename_patient_prefix(img)) == int(e["Patient ID"]),
               "split": a["split"], "stratum": a["stratum"], "image": img, "bbox_classes": a["classes"],
               "data_entry_finding_labels": e["Finding Labels"].split("|"),
               "unannotated_findings_note": "bbox 없는 finding은 음성 GT가 아님 (위치 미상)",
               "official_split": split_of[img], "annotation": ann,
               "annotation_sha256": hashlib.sha256(json.dumps(ann, sort_keys=True).encode()).hexdigest(),
               "annotation_type": "bbox (xywh→xyxy, 배포 PNG canvas pixel)",
               "status": f["status"]}
        for k in ("zip", "zip_member", "bytes", "file_sha256", "pixel_sha256", "width", "height", "mode", "source_url"):
            row[k] = f.get(k)
        row["original_identity"] = "unverified (mirror)"
        if f["status"] == "ok":
            W, H = f["width"], f["height"]
            oob = nih.canvas_checks(bl, W, H)
            row["out_of_canvas"] = oob
            if not oob:
                t = T.bbox_union_occupancy([b["xyxy"] for b in bl], W, H)
                targets_fine.append(t)
                target_ids.append(img)
                row["target_area_fraction"] = float(t.mean())
        rows.append(row)
    # join·hash 100% 검사
    sel_ok = [r for r in rows if r["status"] == "ok" and not r["out_of_canvas"]]
    res["selected_join_ok"] = len(sel_ok)
    res["selected_total"] = len(rows)
    # split 간 중복
    dup = {"patient": [], "file_sha256": [], "pixel_sha256": [], "image": []}
    for key in list(dup):
        field = {"patient": "patient_id", "file_sha256": "file_sha256", "pixel_sha256": "pixel_sha256", "image": "image"}[key]
        seen = {}
        for r in rows:
            v = r.get(field)
            if v is None:
                continue
            seen.setdefault(v, set()).add(r["split"])
        dup[key] = [v for v, s in seen.items() if len(s) > 1]
        dup[key + "_within_any"] = sum(1 for r in rows if r.get(field) is not None) - len(seen)
    # 같은 patient의 다른 영상이 다른 split에 없는지 (1명당 1영상이므로 구조적으로 0)
    res["split_overlap"] = dup
    cc = nih.split_class_counts(assign)
    res["split_class_counts"] = cc
    res["readiness_counts"] = nih.lesion_readiness(assign, cc)
    res["canvas_verification"] = {
        "all_fetched_images_1024x1024": all_1024, "readme_mentions_1024": readme_1024,
        "selected_boxes_out_of_canvas": sum(len(r.get("out_of_canvas") or []) for r in rows),
        "all_bbox_rows_out_of_1024": len(res["bbox_out_of_canvas_1024_raw"]),
        "all_bbox_max_x1_y1": [max(b["xyxy"][2] for b in boxes), max(b["xyxy"][3] for b in boxes)],
        "all_bbox_min_x0_y0": [min(b["xyxy"][0] for b in boxes), min(b["xyxy"][1] for b in boxes)],
        "readme_evidence_note": "미러 README의 1024 언급은 datasets 로딩 예시 출력(PIL size=1024x1024) 한 줄이다. "
                                "canvas 근거는 실제 영상 해상도와 bbox 좌표 범위를 함께 본다.",
        "note": "bbox 좌표는 배포 PNG(1024x1024) pixel 좌표로 해석. OriginalImage 크기는 사용하지 않음."}
    np.savez_compressed(os.path.join(out, "nih_targets_fine64.npz"), ids=np.array(target_ids),
                        fine=np.array(targets_fine) if targets_fine else np.zeros((0, 64, 64)))
    return rows


# ---------------------------------------------------------------- SCR

def scr_stage(ledger, out, prov, problems):
    d = os.path.join(out, "data", "scr")
    os.makedirs(d, exist_ok=True)
    rec_body = ledger.get(ZENODO_API, "zenodo_record_json")
    rec = json.loads(rec_body)
    files = {f["key"]: f for f in rec["files"]}
    prov["scr_zenodo"] = {"api": ZENODO_API, "doi": rec.get("doi"), "title": rec["metadata"].get("title"),
                          "creators": [c.get("name") for c in rec["metadata"].get("creators", [])],
                          "license": (rec["metadata"].get("license") or {}).get("id"),
                          "publication_date": rec["metadata"].get("publication_date"),
                          "version": rec["metadata"].get("version"), "revision": rec.get("revision"),
                          "files": {k: {"size": v["size"], "checksum": v["checksum"]} for k, v in files.items()}}
    blobs = {}
    for f in SCR_FILES:
        meta = files[f]
        local = os.path.join(d, f)
        want = meta["checksum"].split(":", 1)[1]
        if os.path.exists(local) and net.md5_bytes(open(local, "rb").read()) == want:
            body, how = open(local, "rb").read(), "cached"
        else:
            body = ledger.get(meta["links"]["self"], f"scr:{f}", expect_bytes=meta["size"])
            with open(local, "wb") as fh:
                fh.write(body)
            how = "downloaded"
        ok = net.md5_bytes(body) == want
        prov.setdefault("scr_files", {})[f] = {"url": meta["links"]["self"], "bytes": len(body), "listed_size": meta["size"],
                                               "md5_listed": want, "md5_verified": ok, "sha256": net.sha256_bytes(body),
                                               "local": local, "fetch": how}
        if not ok:
            problems.append({"stage": "scr", "file": f, "what": "md5_mismatch"})
        blobs[f] = body
    imgs, p_img = scr.inspect_images(blobs["jpg.zip"])
    masks, p_mask, organs = scr.inspect_masks(blobs["masks.zip"])
    res = {"image_problems": p_img, "mask_problems": p_mask, "organs": organs, "n_images": len(imgs)}
    res["image_sizes"] = _count(f"{v['size'][0]}x{v['size'][1]}|{v['mode']}|{v['format']}" for v in imgs.values())
    res["mask_sizes"] = _count(f"{v['size'][0]}x{v['size'][1]}|{v['mode']}|{v['format']}" for v in masks.values())
    res["mask_unique_value_sets"] = _count(str(v["unique_values"]) for v in masks.values())
    res["image_name_examples"] = sorted(v["member"] for v in imgs.values())[:3]
    res["mask_name_examples"] = sorted(v["member"] for v in masks.values())[:5]
    cases = sorted(imgs)
    res["n_nodule_cases_JPCLN"] = sum(c.startswith("JPCLN") for c in cases)
    res["n_non_nodule_cases_JPCNN"] = sum(c.startswith("JPCNN") for c in cases)
    corr = {}
    rows, tgt, tgt_ids = [], [], []
    for o in organs:
        have = [c for c in cases if (c, o) in masks]
        orphan = sorted({c for c, oo in masks if oo == o and c not in imgs})
        corr[o] = {"cases_with_mask": len(have), "cases_total": len(cases), "rate": len(have) / max(1, len(cases)),
                   "masks_without_image": orphan}
    res["organ_correspondence"] = corr
    for c in cases:
        im = imgs[c]
        row = {"case_id": c, "image_member": im["member"], "image_size": im["size"], "image_mode": im["mode"],
               "image_bytes": im["bytes"], "image_pixel_sha256": pixel_sha256(im["array"]),
               "subject_id": "unknown (근거 없음; case-disjoint만 확인)", "split": "anatomy_dev_unassigned",
               "annotation_type": "manual anatomy mask (SCR)", "masks": {}}
        for o in organs:
            m = masks.get((c, o))
            if m is None:
                row["masks"][o] = {"status": "missing"}
                continue
            ent = {"member": m["member"], "size": m["size"], "mode": m["mode"],
                   "pixel_sha256": pixel_sha256(m["array"]),
                   "same_size_as_image": m["size"] == im["size"],
                   "burned_contour": scr.burned_contour_score(im["array"], m["array"])}
            ys, xs = np.nonzero(np.asarray(m["array"]) > 0)
            ent["centroid_xy_frac"] = [float(xs.mean() / m["size"][0]), float(ys.mean() / m["size"][1])] if len(xs) else None
            try:
                b = scr.binarize(m["array"])
                t = T.mask_occupancy(b)
                ent.update({"status": "ok", "area_fraction": float(b.mean()),
                            "target_mean_minus_area": float(t.mean() - b.mean())})
                tgt.append(t)
                tgt_ids.append(f"{c}|{o}")
            except ValueError as e:
                ent.update({"status": "mask_format_error", "error": str(e)[:200]})
            row["masks"][o] = ent
        rows.append(row)
    res["image_mask_same_size_frac"] = _frac(e["same_size_as_image"] for r in rows for e in r["masks"].values()
                                             if e.get("status") == "ok")
    res["mask_ok"] = sum(1 for r in rows for e in r["masks"].values() if e.get("status") == "ok")
    res["mask_expected"] = len(rows) * len(organs)
    res["max_abs_target_area_error"] = max((abs(e["target_mean_minus_area"]) for r in rows for e in r["masks"].values()
                                            if e.get("status") == "ok"), default=None)
    bc = [e["burned_contour"] for r in rows for e in r["masks"].values() if e.get("burned_contour")]
    burned = [b for b in bc if b["edge_hit_rate"] >= 0.5 and b["edge_hit_rate"] >= 3 * b["shifted_hit_rate"]]
    res["burned_contour"] = {
        "rule": "mask 경계 3x3 이웃에 극값(>=235와 <=20)이 모두 있는 비율 >= 0.5 이고 x+12px 이동 기준선의 3배 이상",
        "n_cases_checked": len(bc), "n_cases_burned": len(burned),
        "edge_hit_rate_median": float(np.median([b["edge_hit_rate"] for b in bc])) if bc else None,
        "shifted_hit_rate_median": float(np.median([b["shifted_hit_rate"] for b in bc])) if bc else None,
        "interpretation": "jpg.zip 영상에 annotation 윤곽선이 그려져 있으면 모델 입력으로 쓸 수 없다 (정답 노출)."}
    cxs = [e["centroid_xy_frac"][0] for r in rows for e in r["masks"].values() if e.get("centroid_xy_frac")]
    res["mask_semantics"] = {
        "documented": False,
        "n_masks_per_case": len(organs),
        "centroid_x_frac_min_median_max": [min(cxs), float(np.median(cxs)), max(cxs)] if cxs else None,
        "inferred": "case당 단일 구조. 모든 mask의 무게중심이 영상 왼쪽 0.22-0.35 → 영상 왼쪽 폐(환자 우폐)로 보임 "
                    "(overlay 육안 확인 포함; 배포 문서로 확인되지 않음)",
        "image_vs_mask_resolution": "영상 256x256 JPEG, mask 1024x1024 TIFF (명시적 4배 관계; 정규화 좌표 target에는 영향 없음)"}
    dups = {}
    for r in rows:
        dups.setdefault(r["image_pixel_sha256"], []).append(r["case_id"])
    res["duplicate_image_pixels"] = [v for v in dups.values() if len(v) > 1]
    res["subject_relationship"] = "근거 없음: case ID만 서로 다름(case-disjoint). patient 독립성은 확인하지 않음."
    res["nodule_location_metadata"] = {
        "in_scr_archive": False,
        "jsrt_official": "http://db.jsrt.or.jp/eng.php — 등록 양식 제출 후 이메일로 비밀번호를 받는 방식. "
                         "명시적 공개 파일 경로가 아니므로 이번에는 연결하지 않음.",
        "status": "blocked_data"}
    np.savez_compressed(os.path.join(out, "scr_targets_fine64.npz"), ids=np.array(tgt_ids),
                        fine=np.array(tgt) if tgt else np.zeros((0, 64, 64)))
    return res, rows, imgs, masks


def _count(it):
    out = {}
    for k in it:
        out[k] = out.get(k, 0) + 1
    return out


def _frac(it):
    v = list(it)
    return sum(bool(x) for x in v) / len(v) if v else None


# ---------------------------------------------------------------- overlays

def overlays(nih_rows, scr_rows, scr_imgs, scr_masks, out):
    """사전 규칙: NIH train 첫 4 + validation 첫 4 (image ID 정렬), SCR 첫 4 case (ID 정렬). test는 그리지 않는다."""
    od = os.path.join(out, "overlays")
    os.makedirs(od, exist_ok=True)
    made = []
    for split in ("train", "validation"):
        rs = sorted([r for r in nih_rows if r["split"] == split and r["status"] == "ok"], key=lambda r: r["image"])[:4]
        for r in rs:
            im = Image.open(r["local"] if "local" in r else os.path.join(out, "data", "nih", "images", r["image"]))
            im = im.convert("RGB")
            d = ImageDraw.Draw(im)
            for a in r["annotation"]:
                d.rectangle(a["xyxy"], outline=(255, 0, 0), width=4)
                d.text((a["xyxy"][0] + 4, a["xyxy"][1] + 4), a["label"], fill=(255, 255, 0))
            t = T.bbox_union_occupancy([a["xyxy"] for a in r["annotation"]], r["width"], r["height"])
            # 64x64 target을 canvas로 nearest 확대해 초록 채널에 반투명 표시
            tt = np.kron(t, np.ones((r["height"] // 64, r["width"] // 64)))
            arr = np.asarray(im).astype(np.float64)
            arr[..., 1] = np.clip(arr[..., 1] * (1 - 0.35 * tt) + 255 * 0.35 * tt, 0, 255)
            im = Image.fromarray(arr.astype(np.uint8)).resize((512, 512))
            p = os.path.join(od, f"nih_{split}_{r['image'][:-4]}.png")
            im.save(p)
            made.append(p)
    colors = [(255, 0, 0), (0, 255, 0), (0, 128, 255), (255, 200, 0), (255, 0, 255)]
    for c in sorted(r["case_id"] for r in scr_rows)[:max(0, MAX_OVERLAYS - len(made))][:4]:
        im = Image.fromarray(scr_imgs[c]["array"]).convert("RGB")
        arr = np.asarray(im).astype(np.float64)
        for k, o in enumerate(sorted({oo for (cc, oo) in scr_masks if cc == c})):
            m = scr_masks[(c, o)]["array"]
            if m.shape != arr.shape[:2]:
                m = np.asarray(Image.fromarray(m).resize((arr.shape[1], arr.shape[0]), Image.NEAREST))
            mm = (m > 0)[..., None]
            arr = np.where(mm, arr * 0.6 + np.array(colors[k % len(colors)]) * 0.4, arr)
        im = Image.fromarray(arr.astype(np.uint8)).resize((512, 512))
        p = os.path.join(od, f"scr_{c}.png")
        im.save(p)
        made.append(p)
    return made


def test_schema_checks(nih_rows):
    """test split은 자동 schema·범위 검사에만 사용 (시각화 없음)."""
    t = [r for r in nih_rows if r["split"] == "test"]
    return {"n": len(t), "all_status_ok": all(r["status"] == "ok" for r in t),
            "all_have_hashes": all(r.get("file_sha256") and r.get("pixel_sha256") and r.get("annotation_sha256") for r in t),
            "no_out_of_canvas": all(not r.get("out_of_canvas") for r in t),
            "all_boxes_positive_size": all(a["xywh"][2] > 0 and a["xywh"][3] > 0 for r in t for a in r["annotation"])}


# ---------------------------------------------------------------- main

def nih_readiness_from_outputs(out, evidence_dir=None):
    """기록된 manifest·provenance·영상으로 iter_006 fail-closed 감사를 적용한다 (읽기 전용).

    좌표 근거 디렉터리가 없으면 canvas는 `undocumented`로 두어 엄격한 readiness가 false가 된다.
    """
    from grounding_data import coord_evidence, nih_audit
    canvas = "undocumented"
    if evidence_dir and os.path.exists(os.path.join(evidence_dir, "fetch_summary.json")):
        canvas = coord_evidence.judge(evidence_dir)["coordinate_canvas_status"]
    checks, warnings, _ = nih_audit.run_checks(nih_audit.load_inputs(out))
    return {**nih_audit.readiness(checks, canvas), "checks": {k: v["pass"] for k, v in checks.items()},
            "warnings": warnings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--evidence", default=None, help="fetch_nih_coord_evidence.py 출력 (좌표 근거)")
    args = ap.parse_args()
    out = args.out
    os.makedirs(out, exist_ok=True)
    problems, prov = [], {}
    env = env_stage(out)
    dump(os.path.join(out, "env.json"), env)
    ledger = net.DownloadLedger(os.path.join(out, "download_ledger.json"))
    blocked_env, blocked_data = [], []
    t0 = time.time()

    nih_res, nih_rows, ctx = {"status": "not_run"}, [], None
    try:
        nih_res, ctx = nih_stage(ledger, out, prov, problems)
        if ctx is not None:
            nih_rows = nih_manifest(ctx, nih_res, out, problems)
            nih_res["status"] = "done"
    except net.BudgetExceeded as e:
        nih_res["status"] = "budget_exceeded"
        nih_res["error"] = str(e)
        blocked_env.append({"what": "download_budget", "error": str(e)})
    except net.RangeNotSupported as e:
        nih_res["status"] = "blocked_range_not_supported"
        blocked_env.append({"what": "nih_range", "error": str(e)})
    except Exception as e:
        nih_res["status"] = "error"
        nih_res["error"] = repr(e)[:500]
        blocked_env.append({"what": "nih_stage_exception", "error": repr(e)[:500]})
    dump(os.path.join(out, "nih_audit.json"), nih_res)
    dump(os.path.join(out, "nih_manifest.json"), nih_rows)

    scr_res, scr_rows, scr_imgs, scr_masks = {"status": "not_run"}, [], {}, {}
    try:
        scr_res, scr_rows, scr_imgs, scr_masks = scr_stage(ledger, out, prov, problems)
        scr_res["status"] = "done"
    except net.BudgetExceeded as e:
        scr_res = {"status": "budget_exceeded", "error": str(e)}
        blocked_env.append({"what": "download_budget", "error": str(e)})
    except Exception as e:
        scr_res = {"status": "error", "error": repr(e)[:500]}
        blocked_env.append({"what": "scr_stage_exception", "error": repr(e)[:500]})
    dump(os.path.join(out, "scr_audit.json"), scr_res)
    dump(os.path.join(out, "scr_manifest.json"), scr_rows)

    made = overlays(nih_rows, scr_rows, scr_imgs, scr_masks, out) if (nih_rows or scr_rows) else []
    test_chk = test_schema_checks(nih_rows) if nih_rows else None
    dump(os.path.join(out, "provenance.json"), prov)

    # ---- readiness
    rc = nih_res.get("readiness_counts", {})
    cv = nih_res.get("canvas_verification", {})
    so = nih_res.get("split_overlap", {})
    nih_checks = {
        "stage_done": nih_res.get("status") == "done",
        "patients_160_and_split_80_32_48": bool(rc.get("sizes_met")),
        "min_2_classes_meet_per_split_minimum": bool(rc.get("classes_met")),
        # iter_006: 영상 크기·README 문자열·좌표 범위는 canvas 근거가 아니다 (가정과의 일관성만 확인)
        "canvas_consistent_with_1024_assumption": bool(cv.get("all_fetched_images_1024x1024")
                                                       and cv.get("selected_boxes_out_of_canvas") == 0),
        "selected_join_and_hash_100pct": nih_res.get("selected_join_ok") == nih_res.get("selected_total") and
                                         bool(nih_res.get("selected_total")),
        "patient_disjoint_splits": so.get("patient") == [] and so.get("patient_within_any") == 0,
        "no_file_or_pixel_dup_across_splits": so.get("file_sha256") == [] and so.get("pixel_sha256") == [],
        "patient_id_from_data_entry_prefix_consistent": all(r["filename_prefix_check"] for r in nih_rows) if nih_rows else False,
        "test_split_schema_ok": bool(test_chk and all(v for k, v in test_chk.items() if k != "n")),
    }
    # iter_006: 엄격한 readiness는 공통 fail-closed 감사(nih_audit)로 결정한다
    strict = nih_readiness_from_outputs(out, args.evidence) if nih_rows else None
    nih_checks["iter006_strict_readiness"] = bool(strict and strict["lesion_probe_ready"])
    lesion_ready = all(v is True for v in nih_checks.values())
    scr_checks = {
        "stage_done": scr_res.get("status") == "done",
        "md5_verified": all(v.get("md5_verified") for v in prov.get("scr_files", {}).values()) and bool(prov.get("scr_files")),
        "all_images_decoded": scr_res.get("n_images", 0) > 0 and not scr_res.get("image_problems"),
        "all_masks_connected_and_binary": scr_res.get("mask_ok") == scr_res.get("mask_expected") and scr_res.get("mask_ok", 0) > 0,
        "no_duplicate_image_pixels": scr_res.get("duplicate_image_pixels") == [],
        "images_free_of_burned_annotation": scr_res.get("burned_contour", {}).get("n_cases_burned", 1) == 0,
        "mask_semantics_documented": bool(scr_res.get("mask_semantics", {}).get("documented")),
    }
    anatomy_ready = all(scr_checks.values())
    if not anatomy_ready:
        blocked_data.append({"what": "scr_anatomy_not_ready",
                             "failed_checks": [k for k, v in scr_checks.items() if not v],
                             "detail": "원시 JSRT 영상(윤곽선 없는 원본)은 JSRT 등록 후 배포. 공개 jpg.zip은 윤곽선이 그려진 "
                                       "256x256 시각화 영상이고 masks.zip은 case당 단일 구조."})
    if not lesion_ready:
        blocked_data.append({"what": "nih_lesion_probe_not_ready",
                             "failed_checks": [k for k, v in nih_checks.items() if not v]})
    blocked_data.append({"what": "jsrt_nodule_location_metadata",
                         "detail": scr_res.get("nodule_location_metadata", {}).get("jsrt_official")})
    readiness = {
        "iteration": "iter_005",
        "gpu_device_minutes": 0.0,
        "lesion_probe_ready": lesion_ready,
        "lesion_probe_checks": nih_checks,
        "anatomy_only_ready": anatomy_ready,
        "anatomy_only_checks": scr_checks,
        "anatomy_to_lesion_transfer_ready": False,
        "anatomy_to_lesion_note": "SCR 수동 anatomy mask와 NIH bbox는 서로 다른 데이터·annotation 유형. "
                                  "SCR에는 병변 위치가 연결되지 않아 전이 평가 가능 상태로 승격하지 않음.",
        "blocked_data": blocked_data,
        "blocked_environment": blocked_env,
        "nih_split_name": "NIH supervised development split (seed 20260924; 공식 benchmark test 아님)",
        "caveats": ["NIH 영상·CSV는 HF 미러(고정 revision)에서 받음. NIH 원배포와의 동일성은 unverified.",
                    "bbox는 병변 경계 mask가 아니며 occupancy는 bbox 일치도 target.",
                    "SCR subject 관계 근거 없음: case-disjoint만 확인.",
                    "MedGemma 사전학습 노출 여부는 이 split으로 해결되지 않음."],
        "download": {"bytes_total": ledger.data["bytes_total"], "MiB_total": ledger.data["bytes_total"] / 2 ** 20,
                     "network_seconds": ledger.data["seconds_total"], "n_requests": ledger.data["n_requests"],
                     "budget_MiB": net.BUDGET_BYTES / 2 ** 20, "budget_seconds": net.BUDGET_SECONDS},
        "overlays": made,
        "test_split_schema_checks": test_chk,
        "problems": problems[:100],
        "n_problems": len(problems),
        "wall_seconds": time.time() - t0,
    }
    readiness["nih_strict_readiness"] = strict
    # iter_006: package_complete 대신 실행 완료와 데이터 준비 완료를 분리한다
    readiness["audit_run_complete"] = (nih_res.get("status") == "done" and scr_res.get("status") == "done"
                                       and not blocked_env)
    readiness["audit_run_complete_meaning"] = "모든 단계 실행 완료. 데이터 준비 완료는 lesion_probe_ready로 본다"
    dump(os.path.join(out, "readiness.json"), readiness)
    print(json.dumps({k: readiness[k] for k in ("lesion_probe_ready", "anatomy_only_ready", "audit_run_complete",
                                                  "lesion_probe_checks", "anatomy_only_checks", "download",
                                                  "blocked_environment", "n_problems")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
