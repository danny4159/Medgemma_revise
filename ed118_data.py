"""iter_118 자료 선별: 미사용 RSNA 환자 (reserve) → 공식 Calculated 정답 연결 → 값 보존 PNG → ledger(정답 없음) + private(정답).

- 결과는 results/iter_118 아래에만 쓰며 기존 파일을 덮어쓰지 않는다 ('x' 모드).
- 정답(category, box)은 results/iter_118/private/ 에만 둔다. 생성 worker는 이 경로를 열 수 없다(ed118_gen의 audit hook).
- 환자: mapping img_id의 NIH 8자리 접두어. 미표기는 음성으로 바꾸지 않는다 (Calculated 라벨이 정확히 1개인 영상만).
- 선택: category별 sha256('iter118|'+patient) 오름차순 → 적격 영상이 있는 환자 순서로 TECH 2명, 그 다음 MAIN.
  환자당 영상은 해당 category와 Calculated가 일치하는 적격 SOP 중 SOP 문자열 오름차순 첫 번째.
- 모델 출력·detector 정오는 선택에 사용하지 않는다 (이 모듈은 모델을 실행하지 않는다).
"""
import hashlib
import json
import os
import sys
import time

import numpy as np
from PIL import Image

from rsna_diag import dicom_min, geometry, rsna_data

R = "results"
OUT = f"{R}/iter_118"
RAW = f"{R}/iter_009/source/raw"
ANN = f"{RAW}/pneumonia-challenge-annotations-adjudicated-kaggle_2018.json"
MAP = f"{RAW}/pneumonia-challenge-dataset-mappings_2018.json"
ZIP = f"{RAW}/pneumonia-challenge-dataset-adjudicated-kaggle_2018.zip"
RESERVE = f"{R}/iter_010/manifests/reserve_patients.json"
EXCL_SOURCES = [f"{R}/iter_010/manifests/gt_manifest.json", f"{R}/iter_010/manifests/exclusion_previous_patients.json",
                f"{R}/iter_009/manifests/gt_manifest.json", f"{R}/iter_009/manifests/exclusion_previous_nih_patients.json"]
OLD_INFER = [f"{R}/iter_010/manifests/infer_manifest.jsonl", f"{R}/iter_009/manifests/infer_manifest.jsonl"]
CATS = [rsna_data.CAT_POS, rsna_data.CAT_NORMAL, rsna_data.CAT_NLONN]
N_TECH_PER_CAT = 2
N_MAIN = {rsna_data.CAT_POS: 96, rsna_data.CAT_NORMAL: 48, rsna_data.CAT_NLONN: 48}
AUDIT_WINDOW = {rsna_data.CAT_POS: 520, rsna_data.CAT_NORMAL: 260, rsna_data.CAT_NLONN: 260}
SALT = "iter118|"


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def sel_key(p):
    return sha(SALT + p)


def wr(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def excluded_patients():
    used, by_src = set(), {}
    for p in EXCL_SOURCES:
        d = json.load(open(p))
        if p.endswith("gt_manifest.json"):
            ids = {v["patient"] for v in d.values()}
        else:
            ids = set(d)
        by_src[p] = len(ids)
        used |= ids
    return used, by_src


def old_hashes():
    pix, sops = set(), set()
    for p in OLD_INFER:
        for ln in open(p):
            if ln.strip():
                r = json.loads(ln)
                pix.add(r["pixel_sha256"])
                sops.add(os.path.basename(r["image"])[:-4])
    for p in EXCL_SOURCES[:1] + EXCL_SOURCES[2:3]:
        for v in json.load(open(p)).values():
            sops.add(v["sop"])
    return pix, sops


def padded_pixel_sha(arr):
    rgb = geometry.to_uint8_rgb_preserving(arr)
    padded, aff = geometry.pad_square(rgb)
    return sha(padded.tobytes()), aff


def build():
    t0 = time.monotonic()
    if os.path.exists(f"{OUT}/private/labels.json"):
        sys.exit("이미 선별됨: 덮어쓰지 않는다")
    reserve = json.load(open(RESERVE))
    used, excl_by_src = excluded_patients()
    old_pix, old_sop = old_hashes()
    label, ann = rsna_data.load_annotations(ANN)
    sop_map, dups = rsna_data.load_mapping(MAP)
    rz = rsna_data.RsnaZip(ZIP)
    if dups or rz.collisions:
        raise rsna_data.AuditError(f"mapping 중복 {len(dups)} / ZIP 충돌 {len(rz.collisions)} → 중단")
    by_patient = {}
    for sop, m in sop_map.items():
        mm = rsna_data.IMG_RE.fullmatch(m["img_id"])
        if mm and sop in ann:
            by_patient.setdefault(mm.group(1), []).append(sop)
    cand, cand_info = {}, {}
    for c in CATS:
        allc = list(reserve[c])
        free = [p for p in allc if p not in used]
        cand[c] = sorted(free, key=sel_key)[:AUDIT_WINDOW[c]]
        cand_info[c] = dict(reserve=len(allc), excluded_by_prior_use=len(allc) - len(free), unused=len(free),
                            audit_window=len(cand[c]))
    chosen, skipped, seen_pix, seen_sop = {}, {}, set(), set()
    os.makedirs(f"{OUT}/data/images", exist_ok=True)
    need = {c: N_TECH_PER_CAT + N_MAIN[c] for c in CATS}
    eligible = {c: [] for c in CATS}
    for c in CATS:
        for p in cand[c]:
            if len(eligible[c]) >= need[c]:
                break
            sops = sorted(by_patient.get(p, []))
            if not sops:
                skipped[p] = "no_annotated_images"
                continue
            recs, _ = rsna_data.audit_all(label, {s: ann[s] for s in sops}, sop_map, [], rz)
            ok = [s for s in sops if not recs[s]["reasons"] and recs[s]["category"] == c and recs[s]["patient"] == p]
            if not ok:
                skipped[p] = "no_eligible_image_in_category:" + ";".join(sorted({r for s in sops for r in recs[s]["reasons"]})[:3])
                continue
            sop = ok[0]
            if sop in old_sop or sop in seen_sop:
                skipped[p] = "sop_duplicate"
                continue
            meta, arr = dicom_min.read_pixels(rz.read(sop))
            psha, aff = padded_pixel_sha(arr)
            rsha = sha(arr.tobytes())  # 기존 manifest의 pixel_sha256은 padding 전 raw uint8 array hash다 (iter_118 정정)
            if rsha in old_pix or rsha in seen_pix:
                skipped[p] = "pixel_duplicate"
                continue
            png = f"{OUT}/data/images/{sop}.png"
            Image.fromarray(arr).save(png)
            rb = np.asarray(Image.open(png))
            if not np.array_equal(rb, arr) or padded_pixel_sha(rb)[0] != psha:
                raise RuntimeError(f"PNG 왕복 불일치 {sop}")
            seen_pix.add(rsha)
            seen_sop.add(sop)
            r = recs[sop]
            eligible[c].append(dict(patient=p, sop=sop, category=c, image=png, file_sha256=fsha(png), pixel_sha256=psha,
                                    size_hw=[int(arr.shape[0]), int(arr.shape[1])], zip=rz.info(sop), img_id=r["img_id"],
                                    boxes_xyxy_px=[[b["xywh"][0], b["xywh"][1], b["xywh"][0] + b["xywh"][2], b["xywh"][1] + b["xywh"][3]]
                                                   for b in r["boxes"]], dicom_tags={k: meta.get(k) for k in
                                    ("TransferSyntaxUID", "PhotometricInterpretation", "Rows", "Columns", "BitsStored", "ViewPosition")}))
    tech = [e for c in CATS for e in eligible[c][:N_TECH_PER_CAT]]
    rest = {c: eligible[c][N_TECH_PER_CAT:] for c in CATS}
    m = min(48, len(rest[CATS[0]]) // 2, len(rest[CATS[1]]), len(rest[CATS[2]]))
    n_main = {CATS[0]: 2 * m, CATS[1]: m, CATS[2]: m}
    main = [e for c in CATS for e in rest[c][:n_main[c]]]
    if m == 0 or any(len(eligible[c]) < N_TECH_PER_CAT for c in CATS):
        raise RuntimeError("표본 부족: m=0 또는 TECH 불가 — 생성하지 않는다")
    unused_extra = {c: len(rest[c]) - n_main[c] for c in CATS}
    # PNG는 사용하지 않는 추가 환자 몫도 만들었을 수 있다 → 선택에 포함되지 않은 파일은 selection에서 제외 표시
    selected = {e["patient"] for e in tech + main}
    for c in CATS:
        for e in eligible[c]:
            if e["patient"] not in selected:
                e["unused_extra"] = True
    ledger_rows, labels = [], {}
    for stage, lst in (("TECH", tech), ("MAIN", main)):
        for rank, e in enumerate(lst):
            ledger_rows.append(dict(id=e["patient"], stage=stage, rank=rank, image=e["image"], file_sha256=e["file_sha256"],
                                    pixel_sha256=e["pixel_sha256"], size_hw=e["size_hw"], sop=e["sop"]))
            labels[e["patient"]] = dict(category=e["category"], sop=e["sop"], boxes_xyxy_px=e["boxes_xyxy_px"],
                                        gt_answer="yes" if e["category"] == rsna_data.CAT_POS else "no", zip=e["zip"],
                                        img_id=e["img_id"], dicom_tags=e["dicom_tags"])
    wr(f"{OUT}/private/labels.json", labels)
    wr(f"{OUT}/data/ledger_nogt.json", dict(rows=ledger_rows, rule=f"category별 sha256('{SALT}'+patient) 오름차순, 적격 영상이 있는 환자 순서; "
                                           "TECH=각 category 앞 2명, MAIN=그 다음. 환자당 영상=적격 SOP 오름차순 첫째."))
    prov = dict(created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), n_tech=len(tech), n_main=len(main), m=m,
                n_main_by_category=n_main, candidates=cand_info, excluded_sources=excl_by_src, n_excluded_union=len(used),
                skipped_candidates=skipped, unused_extra_eligible=unused_extra,
                inputs=dict(annotation=fsha(ANN), mapping=fsha(MAP), zip=fsha(ZIP), reserve=fsha(RESERVE),
                            **{os.path.basename(p): fsha(p) for p in EXCL_SOURCES + OLD_INFER}),
                checks=dict(mapping_duplicates=len(dups), zip_collisions=len(rz.collisions), n_old_pixel_hashes=len(old_pix),
                            n_old_sops=len(old_sop), note="legacy 익명 영상 중복은 검사하지 않았다(미검증)."),
                elapsed_s=time.monotonic() - t0)
    wr(f"{OUT}/data/data_provenance.json", prov)
    print(json.dumps({k: prov[k] for k in ("n_tech", "n_main", "m", "n_main_by_category", "n_excluded_union")}), len(skipped), "skipped")


if __name__ == "__main__":
    if sys.argv[1:] != ["build"]:
        sys.exit("usage: ed118_data.py build")
    build()
