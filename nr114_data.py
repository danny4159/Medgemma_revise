"""iter_114 새 환자 표본 구성 (CPU only, 모델 미사용). 결과는 results/iter_114/data 아래 새 파일로만 쓴다(기존 파일 있으면 거부).

규칙(모델 출력 전에 잠금):
- metadata: pg39_data.load_inputs (pinned sha·연결 검사) → image_pool(split='test') 기존 규칙 그대로(seed 20260930, 시간 문구 제외, 문장쌍·환자당 영상 hash 선택).
- 선택된 두 문장 중 공식 box>=2 인 항목만 포함. 좋은 사례·합의 사례 선택 없음.
- 과거 사용 이력 제외: results/ 의 json/jsonl/csv/txt/md/tsv 와 파일명에서 후보의 PatientID/StudyID/ImageID(+ImageID 해시부)가 나타나면 그 환자 전체 제외(보수적).
  추출한 영상의 raw_png/u16/u8 pixel sha256 이 과거 결과 파일에 나타나도 제외한다.
- 순서: sha256('iter114|PatientID') 오름차순. 초기=앞 36명(가용 시), 최종=전체. 같은 환자는 단계 간 나누지 않는다.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

import nr107_spec as S
import pg39_data as P
from report86_common import ROOT, sha, sha_obj, save

OUT = ROOT / "results/iter_114/data"
INIT_N = 36
SCAN_EXT = ["--include=*.json", "--include=*.jsonl", "--include=*.csv", "--include=*.txt", "--include=*.md", "--include=*.tsv"]
SCAN_EXCL = ["--exclude-dir=iter_114", "--exclude-dir=datasets", "--exclude-dir=environments", "--exclude-dir=hf", "--exclude-dir=runtime_cache"]
CODE = ["nr114_data.py", "pg39_data.py", "nr107_spec.py", "nr107_geom.py", "report86_common.py"]


def hh(*p):
    return hashlib.sha256("|".join(str(x) for x in p).encode()).hexdigest()


def candidates(reports, links):
    pool, excl = P.image_pool(reports, links, "test")
    by = {r["ImageID"]: r for r in reports}
    out = []
    for c in pool:
        fs = by[c["ImageID"]]["findings"]
        keep = [x for x in (c["i"], c["j"]) if len(fs[x]["boxes"]) >= 2]
        if keep:
            out.append({**c, "keep_idx": sorted(keep)})
    return out, excl


def pats_for(c):
    return {c["PatientID"], c["ImageID"], c["StudyID"], c["ImageID"].split("_")[0]}


def grep_scan(patterns, tag):
    """results/ 전체에서 patterns(고정 문자열)이 나타나는 (file, match) 목록."""
    pf = OUT / f"scan_patterns_{tag}.txt"
    with pf.open("x") as f:
        f.write("\n".join(sorted(patterns)) + "\n")
    r = subprocess.run(["grep", "-rHoF", "-f", str(pf), "results"] + SCAN_EXT + SCAN_EXCL, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr[:500]
    hits = set()
    for ln in r.stdout.splitlines():
        fn, _, m = ln.partition(":")
        hits.add((fn, m))
    # 파일명에 나타나는 경우
    for root, _, files in os.walk(ROOT / "results"):
        rel = os.path.relpath(root, ROOT)
        if rel.startswith(("results/iter_114", "results/datasets", "results/environments")):
            continue
        for fn in files:
            for p in patterns:
                if p in fn:
                    hits.add((os.path.join(rel, fn), p))
    return sorted(hits)


def extract(z, idx, iid):
    zi = idx[iid]
    raw = z.read(zi)
    a = np.asarray(Image.open(io.BytesIO(raw)))
    assert a.dtype == np.uint16 and a.ndim == 2, (iid, a.dtype, a.shape)
    b = (a >> 8).astype(np.uint8)
    rp, up = OUT / "raw" / iid, OUT / "u8" / iid
    with rp.open("xb") as f:
        f.write(raw)
    Image.fromarray(b).save(up)
    h, w = a.shape
    # 저장한 파일을 다시 읽어 hash 확인
    assert hashlib.sha256(np.asarray(Image.open(up)).tobytes()).hexdigest() == hashlib.sha256(b.tobytes()).hexdigest()
    return {"path": str(up.relative_to(ROOT)), "raw_path": str(rp), "zip_member": zi.filename, "zip_crc": zi.CRC,
            "raw_png_sha256": hashlib.sha256(raw).hexdigest(), "u16_pixel_sha256": hashlib.sha256(a.tobytes()).hexdigest(),
            "u8_pixel_sha256": hashlib.sha256(b.tobytes()).hexdigest(), "h": int(h), "w": int(w), "u16_min": int(a.min()), "u16_max": int(a.max())}


def main():
    if (OUT / "selection_lock.json").exists():
        raise SystemExit("selection_lock.json exists: refuse to rebuild")
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    (OUT / "u8").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    reports, master, links = P.load_inputs()
    cands, excl_counts = candidates(reports, links)
    all_pat = set()
    for c in cands:
        all_pat |= pats_for(c)
    hits = grep_scan(all_pat, "cand")
    by_pat_files = {}
    for fn, m in hits:
        for c in cands:
            if m in pats_for(c):
                by_pat_files.setdefault(c["PatientID"], set()).add(fn)
    exposed = {p: sorted(v) for p, v in by_pat_files.items()}
    rest = [c for c in cands if c["PatientID"] not in exposed]
    rest.sort(key=lambda c: hh("iter114", c["PatientID"]))
    z = P.open_image_zip()
    idx = P.zip_index(z)
    metas, dropped_zip = {}, []
    for c in rest:
        if c["ImageID"] not in idx:
            dropped_zip.append(c["PatientID"])
    rest = [c for c in rest if c["PatientID"] not in dropped_zip]
    for c in rest:
        metas[c["ImageID"]] = extract(z, idx, c["ImageID"])
    # 영상 pixel/raw hash 가 과거 결과 파일에 나타나면 제외
    hs = set()
    for m in metas.values():
        hs |= {m["raw_png_sha256"], m["u16_pixel_sha256"], m["u8_pixel_sha256"]}
    hh_hits = grep_scan(hs, "pixel")
    hash_exposed = {}
    for fn, m in hh_hits:
        for iid, mt in metas.items():
            if m in (mt["raw_png_sha256"], mt["u16_pixel_sha256"], mt["u8_pixel_sha256"]):
                hash_exposed.setdefault(iid, set()).add(fn)
    # 이번 집단 내부 pixel 중복
    seen, internal_dup = {}, []
    for c in rest:
        k = metas[c["ImageID"]]["u16_pixel_sha256"]
        if k in seen:
            internal_dup.append((seen[k], c["PatientID"]))
        seen[k] = c["PatientID"]
    drop_pix = {c["PatientID"] for c in rest if c["ImageID"] in hash_exposed} | {b for _, b in internal_dup}
    final = [c for c in rest if c["PatientID"] not in drop_pix]
    by_rep = {r["ImageID"]: r for r in reports}
    items = []
    for n, c in enumerate(final):
        fs = by_rep[c["ImageID"]]["findings"]
        for fi in c["keep_idx"]:
            f = fs[fi]
            gt, extra = f["boxes"], f.get("extra_boxes") or []
            core, pairing = S.core_status(gt, extra)
            items.append({"item_key": hh("item", c["ImageID"], fi)[:16], "ImageID": c["ImageID"], "PatientID": c["PatientID"],
                          "StudyID": c["StudyID"], "split": "test", "finding_index": fi, "sentence": f["sentence_en"],
                          "sentence_sha256": hashlib.sha256(f["sentence_en"].encode()).hexdigest(), "labels": f["labels"],
                          "locations": f["locations"], "gt": gt, "extra": extra, "n_gt": len(gt), "n_extra": len(extra),
                          "core": core, "pairing": pairing, "image_meta": metas[c["ImageID"]],
                          "patient_rank": n, "stage": "init" if n < INIT_N else "expand"})
    assert len({it["item_key"] for it in items}) == len(items)
    # 영상 추출했지만 최종에서 빠진 환자의 파일은 보존(삭제 금지)하되 manifest 에는 넣지 않는다.
    init_items = [it for it in items if it["stage"] == "init"]
    raw_manifest = [{"ImageID": c["ImageID"], "raw_path": metas[c["ImageID"]]["raw_path"], "sha256": metas[c["ImageID"]]["raw_png_sha256"]} for c in final]
    summary = {
        "n_candidates_patients": len(cands), "n_candidates_items": sum(len(c["keep_idx"]) for c in cands),
        "n_exposed_patients": len(exposed), "exposed_files": exposed, "dropped_missing_zip": dropped_zip,
        "pixel_hash_exposed": {k: sorted(v) for k, v in hash_exposed.items()}, "internal_pixel_dup": internal_dup,
        "n_final_patients": len(final), "n_final_items": len(items), "n_init_patients": min(INIT_N, len(final)), "n_init_items": len(init_items),
        "patient_order": [{"PatientID": c["PatientID"], "rank": n, "order_hash": hh("iter114", c["PatientID"]),
                           "stage": "init" if n < INIT_N else "expand"} for n, c in enumerate(final)],
        "pool_exclusion_counts": excl_counts, "metadata_sha256": links["inputs_sha256"], "pg39_seed": P.SEED,
        "n_gt_dist": {str(k): sum(1 for it in items if it["n_gt"] == k) for k in sorted({it["n_gt"] for it in items})},
        "n_core": sum(it["core"] for it in items), "no_alt_items": sum(1 for it in items if not it["extra"]),
        "label": "unused-by-our-pipeline patients of the official PadChest-GR test split; NOT claimed unexposed to public models",
        "build_seconds": time.time() - t0,
    }
    save(OUT / "items.json", items)
    save(OUT / "raw_manifest.json", raw_manifest)
    save(OUT / "exposure_ledger.json", {"exposed_patients": exposed, "scan_hits": [[a, b] for a, b in hits], "pixel_hits": [[a, b] for a, b in hh_hits]})
    summary["items_sha256"] = sha(OUT / "items.json")
    summary["raw_manifest_sha256"] = sha(OUT / "raw_manifest.json")
    save(OUT / "cohort_summary.json", summary)
    save(OUT / "selection_lock.json", {"locked_at_unix": time.time(), "locked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                       "items_sha256": summary["items_sha256"], "raw_manifest_sha256": summary["raw_manifest_sha256"],
                                       "cohort_summary_sha256": sha(OUT / "cohort_summary.json"), "code_sha256": {f: sha(ROOT / f) for f in CODE},
                                       "note": "locked before any iter_114 model output"})
    print(json.dumps({k: summary[k] for k in ("n_candidates_patients", "n_candidates_items", "n_exposed_patients", "n_final_patients",
                                              "n_final_items", "n_init_patients", "n_init_items", "n_gt_dist", "n_core", "no_alt_items",
                                              "dropped_missing_zip", "internal_pixel_dup", "build_seconds")}, indent=1))
    print("pixel_hash_exposed", len(hash_exposed))


if __name__ == "__main__":
    sys.exit(main())
