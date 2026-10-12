"""iter_107 고정 집단 구성 (CPU only, 모델 미사용).

iter_039 manifest_private(공식 GT/extra, 원문) 와 iter_046 V96 MedGrounder 저장 출력(환자·target 연결)을 대조해
공식 box 2개 이상인 소견 전부를 선택한다. 핵심 집단 규칙은 출력과 무관한 metadata 조건이다.
CURE는 공식 transform이 원본 uint16 PNG를 읽으므로 분할 zip에서 해당 영상만 추출해 CRC·raw hash를 대조한다.
모든 출력은 results/iter_107/data 아래 새 파일로만 쓴다(기존 파일이 있으면 FileExistsError).
"""
import hashlib
import json
import sys
from pathlib import Path

from report86_common import ROOT, sha, sha_obj, save
import nr107_geom as G
import nr107_spec as S

OUT = ROOT / "results/iter_107/data"
MANIFEST = ROOT / "results/iter_039/data/manifest_private.jsonl"
MG_DIR = ROOT / "results/iter_046/mg/V96_A_w2b4"
SEL = ROOT / "results/iter_046/decisions/final_selection.json"
THRS = ("0.8", "0.4")


def h(*p):
    return hashlib.sha256("|".join(str(x) for x in p).encode()).hexdigest()


def build_items():
    man = {}
    for l in MANIFEST.read_text().splitlines():
        r = json.loads(l)
        assert r["PatientID"] not in man
        man[r["PatientID"]] = r
    raw = []
    for w in (0, 1):
        raw += [json.loads(l) for l in (MG_DIR / f"raw_worker{w}.jsonl").read_text().splitlines() if l]
    assert len(raw) == 192 and len({r["request_id"] for r in raw}) == 192
    sel = json.loads(SEL.read_text())
    assert sel["label"] == "A_U_e5" and sel["selected_threshold"] == 0.8 and sel["fixed_threshold"] == 0.4
    comp = json.loads((MG_DIR / "completion.json").read_text())
    assert comp["complete"] and comp["n_unique"] == 192 and comp["exit_codes"] == [0, 0]
    for w in (0, 1):
        assert sha(MG_DIR / f"raw_worker{w}.jsonl") == comp["raw_file_sha256"][f"raw_worker{w}.jsonl"], "MG raw changed"
    assert all(r["ckpt_sha256"] == sel["ckpt_sha256"] for r in raw)
    items, link_problems = [], []
    for r in raw:
        m = man.get(r["patient"])
        if m is None:
            link_problems.append(("no_manifest", r["patient"]))
            continue
        t = r["target"]
        s = m["sentences"][t]
        if h_sha(s) != r["sentence_sha256"]:
            link_problems.append(("sentence_sha", r["patient"], t))
        if r["u8_pixel_sha256"] != m["image_meta"]["u8_pixel_sha256"] or r["image"] != m["image_meta"]["path"]:
            link_problems.append(("image_link", r["patient"], t))
        gt, extra = m["gt_boxes_xyxy_norm"][t], m["extra_boxes_xyxy_norm"][t]
        if len(gt) < 2:
            continue
        fi = m["finding_index"][t]
        core, pairing = S.core_status(gt, extra)
        det = {}
        for th in THRS:
            d = r["detections"][th]
            det[th] = {"boxes": d["boxes_orig_xyxy"], "scores": d["scores"]}
        items.append({"item_key": h("item", m["ImageID"], fi)[:16], "ImageID": m["ImageID"], "PatientID": m["PatientID"], "StudyID": m["StudyID"],
                      "split": m["split"], "set": m["set"], "target": t, "finding_index": fi, "sentence": s, "sentence_sha256": r["sentence_sha256"],
                      "labels": m["labels"][t], "locations": m["locations"][t], "gt": gt, "extra": extra, "n_gt": len(gt), "n_extra": len(extra),
                      "core": core, "pairing": pairing, "mg_request_id": r["request_id"], "mg": det, "image_meta": m["image_meta"],
                      "u8_image": str(ROOT / m["image_meta"]["path"]) if not Path(m["image_meta"]["path"]).is_absolute() else m["image_meta"]["path"]})
    return items, link_problems, sel, comp


def h_sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def extract_raw(items):
    """분할 zip에서 필요한 영상만 추출. CRC·raw_png_sha256·uint16 hash 대조 후 새 파일로 저장."""
    import numpy as np
    from PIL import Image
    import io
    import pg39_data as P
    z = P.open_image_zip()
    idx = P.zip_index(z)
    raw_dir = OUT / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for iid in sorted({it["ImageID"] for it in items}):
        meta = next(it["image_meta"] for it in items if it["ImageID"] == iid)
        zi = idx[iid]
        assert zi.CRC == meta["zip_crc"], f"zip crc differs {iid}"
        data = z.read(zi)
        assert hashlib.sha256(data).hexdigest() == meta["raw_png_sha256"], f"raw png hash differs {iid}"
        a = np.asarray(Image.open(io.BytesIO(data)))
        assert a.dtype == np.uint16, a.dtype
        assert hashlib.sha256(a.tobytes()).hexdigest() == meta["u16_pixel_sha256"], f"u16 pixel hash differs {iid}"
        assert a.shape == (meta["h"], meta["w"])
        p = raw_dir / iid
        with p.open("xb") as f:
            f.write(data)
        out.append({"ImageID": iid, "raw_path": str(p), "sha256": meta["raw_png_sha256"]})
    return out


def main():
    items, probs, sel, comp = build_items()
    assert not probs, probs
    n_pat = len({it["PatientID"] for it in items})
    core = [it for it in items if it["core"]]
    summary = {"n_items": len(items), "n_patients": n_pat, "n_core": len(core), "n_core_patients": len({it["PatientID"] for it in core}),
               "expected": {"items": 47, "patients": 36, "core": 10},
               "n_gt_dist": {str(k): sum(1 for it in items if it["n_gt"] == k) for k in sorted({it["n_gt"] for it in items})},
               "n_extra_dist": {str(k): sum(1 for it in items if it["n_extra"] == k) for k in sorted({it["n_extra"] for it in items})},
               "mg_selection": {k: sel[k] for k in ("label", "ckpt_sha256", "selected_threshold", "fixed_threshold")},
               "mg_raw_sha256": comp["raw_file_sha256"], "manifest_sha256": sha(MANIFEST), "all_set": sorted({it["set"] for it in items}),
               "all_split": sorted({it["split"] for it in items}), "label": "repeated development material (PadChest-GR train split V96); not independent"}
    if (summary["n_items"], summary["n_patients"], summary["n_core"]) != (47, 36, 10):
        print(json.dumps(summary, indent=1))
        raise SystemExit("cohort size differs from plan: investigate; do not relax rules or replace patients")
    items.sort(key=lambda it: (it["ImageID"], it["finding_index"]))
    order = sorted(items, key=lambda it: h(it["ImageID"], it["finding_index"]))
    summary["tech_first4_item_keys"] = [it["item_key"] for it in order[:4]]
    raw_manifest = extract_raw(items)
    save(OUT / "items.json", items)
    save(OUT / "raw_manifest.json", raw_manifest)
    summary["items_sha256"] = sha(OUT / "items.json")
    summary["raw_manifest_sha256"] = sha(OUT / "raw_manifest.json")
    save(OUT / "cohort_summary.json", summary)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.exit(main())
