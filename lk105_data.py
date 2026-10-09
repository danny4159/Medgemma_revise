"""iter_105: 소견–영역 연결 제안 진단용 PadChest-GR train 쌍 선정 (CPU only, 모델 출력 미사용).

단계:
  enumerate : train 전체에서 사전 규칙(환자당 1영상·1문장쌍)으로 후보를 열거하고 hash 순서·제외 사유·과거 노출을 기록한다.
  extract   : 앞 N_POOL(=D4 4 + E32 32 + reserve 64 + 시각/문장 제외 예비)명의 영상을 uint16>>8 uint8 PNG로 추출하고 contact sheet/overlay를 만든다.
  lock      : visual_audit.json(눈·문장 검토로 제외한 ID) 반영 후 D4/E32/reserve 입력·정답·잠금을 쓴다.
영상 규약은 report101_data와 동일(uint16 -> uint8 right shift 8). 새 산출물은 results/iter_105 아래에만 쓴다.
문장 원문은 변경하지 않는다. 제외 검토는 assistant의 문장/영상 점검이며 전문의 검토가 아니다.
"""
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import pg39_data as D
from report86_common import ROOT, sha, sha_obj, save

R105 = ROOT / "results/iter_105"
DATA = R105 / "data"
SEED = 105017
N_D, N_E, N_R = 4, 32, 64
N_POOL = 120   # hash 순서 앞 120명 추출: 100 사용 + 20 예비(문장/영상 제외용)
IMG_RE = re.compile(r"[0-9]{20,}_[0-9a-z]+\.png")


def hk(*parts):
    return hashlib.sha256("|".join(str(p) for p in (SEED,) + parts).encode()).hexdigest()


def inter_area(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def all_boxes(f):
    return [list(map(float, b)) for b in f["boxes"]] + [list(map(float, b)) for b in f.get("extra_boxes") or []]


def pair_ok(fi, fj):
    """(ok, reason). 두 문장: 서로 다른 문장·label 집합, boxes+extra_boxes 사이 양의 면적 교차 없음."""
    if fi["sentence_en"].strip().lower() == fj["sentence_en"].strip().lower():
        return False, "same_sentence"
    if set(fi["labels"]) == set(fj["labels"]):
        return False, "same_label_set"
    for a in all_boxes(fi):
        for b in all_boxes(fj):
            if inter_area(a, b) > 0:
                return False, "annotation_overlap"
    return True, ""


def finding_ok(f, lab2grp):
    ok, why = D.eligibility(f, lab2grp)
    if not ok:
        return False, why
    if len(f["boxes"]) != 1:
        return False, "not_single_box"
    eb = f.get("extra_boxes") or []
    if not all(D.valid_box(b) for b in eb):
        return False, "invalid_extra_box"
    return True, ""


def scan_prior_images():
    """results 안의 json/jsonl/csv/txt에서 PadChest ImageID가 등장한 파일 목록 {id: [files]} (과거 사용·노출 기록)."""
    seen = {}
    for dirpath, dns, fns in os.walk(ROOT / "results"):
        dns[:] = [d for d in dns if d not in ("runtime_cache", "models", "hf", "images", "raw", "environments", "external", "datasets", "iter_105")]
        for fn in fns:
            if not fn.endswith((".json", ".jsonl", ".csv", ".txt")):
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > 80 << 20:
                    continue
                txt = p.read_text(errors="ignore")
            except OSError:
                continue
            for m in set(IMG_RE.findall(txt)):
                seen.setdefault(m, []).append(str(p.relative_to(ROOT)))
    return seen


def do_enumerate():
    reports, m, links = D.load_inputs()
    lab2grp = links["lab2grp"]
    train = [r for r in reports if links["img2split"][r["ImageID"]] == "train"]
    excl = Counter()
    per_img = {}
    for r in train:
        iid = r["ImageID"]
        el = []
        for idx, f in enumerate(r["findings"]):
            ok, why = finding_ok(f, lab2grp)
            if ok:
                el.append(idx)
            else:
                excl["finding_" + why] += 1
        pairs = []
        for a, i in enumerate(el):
            for j in el[a + 1:]:
                ok, why = pair_ok(r["findings"][i], r["findings"][j])
                if ok:
                    pairs.append((i, j))
                else:
                    excl["pair_" + why] += 1
        if not pairs:
            excl["image_no_valid_pair"] += 1
            continue
        i, j = min(pairs, key=lambda p: hk(iid, p[0], p[1]))
        per_img[iid] = {"ImageID": iid, "PatientID": links["img2patient"][iid], "StudyID": r["StudyID"], "i": i, "j": j,
                        "n_valid_pairs": len(pairs), "hash": hk(links["img2patient"][iid], iid)}
    seen = scan_prior_images()
    prior_pat = {links["img2patient"][i] for i in seen if i in links["img2patient"]}
    prior_study = {links["img2study"][i] for i in seen if i in links["img2study"]}
    by_pat = defaultdict(list)
    n_prior = 0
    for v in per_img.values():
        # 제외하지 않고 기록한다: 두 모델은 frozen이며 이전 반복의 환자 사용은 LoRA 학습/개발 manifest이다 (v1 열거는 광범위 파일 언급까지
        # 제외해 254->29로 줄어 폐기: enumeration.json은 superseded로 보존)
        n_prior += v["PatientID"] in prior_pat or v["StudyID"] in prior_study or v["ImageID"] in seen
        by_pat[v["PatientID"]].append(v)
    reps = [min(vs, key=lambda v: v["hash"]) for vs in by_pat.values()]
    reps.sort(key=lambda v: v["hash"])
    pool = reps[:N_POOL]
    by_id = {r["ImageID"]: r for r in train}
    for v in pool:
        v["earlier_use_files"] = seen.get(v["ImageID"], [])
        f = by_id[v["ImageID"]]["findings"]
        v["s_i"], v["s_j"] = f[v["i"]]["sentence_en"], f[v["j"]]["sentence_en"]
        v["labels_i"], v["labels_j"] = f[v["i"]]["labels"], f[v["j"]]["labels"]
    out = {"rule": "train only; findings: abnormal, single valid box, no progression, no TEMPORAL_RE, labels mapped, valid extra_boxes; "
                   "pair: distinct sentence & label set, no positive-area intersection among boxes+extra_boxes of the two findings; "
                   "per image min hk(ImageID|i|j) pair; patient representative min hk(PatientID|ImageID); "
                   "no exclusion for earlier use (recorded only; frozen models); order by representative hash; "
                   f"pool=first {N_POOL}; D4=first {N_D}, E32 next {N_E}, reserve next {N_R} (after audit exclusions)",
           "seed": SEED, "n_train_images": len(train), "exclusion_counts": dict(excl), "n_images_with_valid_pair": len(per_img),
           "n_images_with_prior_use_recorded": n_prior, "n_prior_images_seen_in_results": len(seen),
           "n_candidate_patients": len(reps), "pool": pool, "raw_sha256": D.PINNED, "code_sha256": sha(__file__)}
    save(DATA / "enumeration_v2.json", out)
    print(json.dumps({k: out[k] for k in ("n_train_images", "exclusion_counts", "n_images_with_valid_pair", "n_images_with_prior_use_recorded",
                                           "n_candidate_patients")}, indent=1))


def extract_one(z, zi, iid):
    raw = z.read(zi)
    a = np.asarray(Image.open(io.BytesIO(raw)))
    if a.dtype != np.uint16 or a.ndim != 2:
        raise D.InputError(f"{iid}: unexpected dtype/shape {a.dtype} {a.shape}")
    b = (a >> 8).astype(np.uint8)
    (DATA / "images").mkdir(parents=True, exist_ok=True)
    (DATA / "raw").mkdir(parents=True, exist_ok=True)
    pu8, praw = DATA / "images" / iid, DATA / "raw" / iid
    if praw.exists():
        assert praw.read_bytes() == raw
    else:
        praw.write_bytes(raw)
    if not pu8.exists():
        tmp = str(pu8) + f".{os.getpid()}.tmp.png"
        Image.fromarray(b).save(tmp)
        os.replace(tmp, pu8)
    h, w = a.shape
    return {"image": str(pu8), "raw_path": str(praw), "zip_member": zi.filename, "zip_crc": zi.CRC,
            "raw_png_sha256": hashlib.sha256(raw).hexdigest(), "u16_pixel_sha256": hashlib.sha256(a.tobytes()).hexdigest(),
            "u8_pixel_sha256": hashlib.sha256(b.tobytes()).hexdigest(), "file_sha256": sha(pu8), "h": int(h), "w": int(w)}


def do_extract():
    en = json.loads((DATA / "enumeration_v2.json").read_text())
    reports, _, links = D.load_inputs()
    by_id = {r["ImageID"]: r for r in reports}
    z = D.open_image_zip()
    idx = D.zip_index(z)
    meta = {}
    for v in en["pool"]:
        meta[v["ImageID"]] = extract_one(z, idx[v["ImageID"]], v["ImageID"])
    pix = Counter(m["u16_pixel_sha256"] for m in meta.values())
    prior_pix = set()
    for q in (ROOT / "results").glob("iter_*/*/inputs*.json"):
        try:
            for d in json.load(open(q)):
                if isinstance(d, dict) and d.get("u16_pixel_sha256"):
                    prior_pix.add(d["u16_pixel_sha256"])
        except (ValueError, OSError):
            pass
    for p in (ROOT / "results").glob("iter_0*/data/manifest*.jsonl"):
        for ln in open(p):
            try:
                h = (json.loads(ln).get("image_meta") or {}).get("u16_pixel_sha256")
            except ValueError:
                continue
            if h:
                prior_pix.add(h)
    ov = {"within_pool_duplicate_pixel_hashes": sum(c > 1 for c in pix.values()),
          "pixel_overlap_with_prior_manifests": sum(m["u16_pixel_sha256"] in prior_pix for m in meta.values()),
          "n_prior_pixel_hashes_checked": len(prior_pix)}
    save(DATA / "extract_meta.json", {"meta": meta, "overlaps": ov, "convention": "uint16>>8 -> uint8 (iter_039/042/086/101과 동일)"})
    # overlay: 두 문장의 boxes(실선)와 extra_boxes(점선 대신 얇은 선) — 문장 번호별 색
    (DATA / "overlay").mkdir(exist_ok=True)
    sheets, items = [], []
    for k, v in enumerate(en["pool"]):
        f = by_id[v["ImageID"]]["findings"]
        im = Image.open(DATA / "images" / v["ImageID"]).convert("RGB")
        w, h = im.size
        dr = ImageDraw.Draw(im)
        lw = max(3, w // 300)
        for idx_f, col in ((v["i"], (255, 60, 60)), (v["j"], (60, 255, 60))):
            for b in f[idx_f]["boxes"]:
                dr.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h], outline=col, width=lw)
            for b in f[idx_f].get("extra_boxes") or []:
                dr.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h], outline=tuple(c // 2 for c in col), width=1)
        im.thumbnail((380, 380))
        items.append((k, v["ImageID"], im))
    for s in range(0, len(items), 12):
        part = items[s:s + 12]
        sheet = Image.new("RGB", (4 * 380, 3 * 400), 0)
        dr = ImageDraw.Draw(sheet)
        for n, (k, iid, im) in enumerate(part):
            x, y = (n % 4) * 380, (n // 4) * 400
            sheet.paste(im, (x, y + 18))
            dr.text((x + 4, y + 2), f"#{k} {iid[:8]}  red=S_i green=S_j", fill=(255, 255, 255))
        p = DATA / "overlay" / f"sheet_{s // 12:02d}.png"
        sheet.save(p)
        sheets.append({"file": str(p), "items": [f"#{k}:{iid}" for k, iid, _ in part]})
    save(DATA / "overlay_sheets.json", sheets)
    print(json.dumps(ov), len(sheets), "sheets")


def do_lock():
    en = json.loads((DATA / "enumeration_v2.json").read_text())
    meta = json.loads((DATA / "extract_meta.json").read_text())["meta"]
    audit = json.loads((DATA / "visual_audit.json").read_text())
    excluded = {x["ImageID"] for x in audit["excluded"]}
    keep = [v for v in en["pool"] if v["ImageID"] not in excluded]
    n_need = N_D + N_E + N_R
    use = keep[:n_need]
    reports, _, links = D.load_inputs()
    by_id = {r["ImageID"]: r for r in reports}
    stages = {"D4": use[:N_D], "E32": use[N_D:N_D + N_E], "R64": use[N_D + N_E:]}
    refs, rows_all = {}, {}
    for st, vs in stages.items():
        rows = []
        for v in vs:
            f = by_id[v["ImageID"]]["findings"]
            fi, fj = f[v["i"]], f[v["j"]]
            m = meta[v["ImageID"]]
            # 문장 ID(S1/S2)는 해시 parity로 무작위 배정 (원문 순서·위치와 독립)
            swap = int(hk(v["ImageID"], "assign"), 16) % 2 == 1
            a, b = (fj, fi) if swap else (fi, fj)
            rows.append({"PatientID": v["PatientID"], "StudyID": v["StudyID"], "ImageID": v["ImageID"], "image": m["image"],
                         "file_sha256": m["file_sha256"], "u16_pixel_sha256": m["u16_pixel_sha256"], "size": [m["w"], m["h"]],
                         "split": "train", "stage": st, "order_hash": v["hash"],
                         "S1": a["sentence_en"], "S2": b["sentence_en"], "box1": a["boxes"][0], "box2": b["boxes"][0],
                         "extra1": a.get("extra_boxes") or [], "extra2": b.get("extra_boxes") or [],
                         "labels1": a["labels"], "labels2": b["labels"], "finding_idx": [v["j"], v["i"]] if swap else [v["i"], v["j"]]})
        rows_all[st] = rows
        save(DATA / f"inputs_{st}.json", rows)
        save(DATA / f"raw_manifest_{st}.json", [{"ImageID": r["ImageID"], "raw_path": meta[r["ImageID"]]["raw_path"],
                                                  "sha256": meta[r["ImageID"]]["raw_png_sha256"]} for r in rows])
    allrows = [r for st in rows_all.values() for r in st]
    for k in ("PatientID", "StudyID", "ImageID", "u16_pixel_sha256"):
        assert len({r[k] for r in allrows}) == len(allrows), k
    assert len(allrows) == n_need, len(allrows)
    lock = {"enumeration_v2_sha256": sha(DATA / "enumeration_v2.json"), "extract_meta_sha256": sha(DATA / "extract_meta.json"),
            "visual_audit_sha256": sha(DATA / "visual_audit.json"), "n_excluded_audit": len(excluded),
            **{f"inputs_{st}_sha256": sha(DATA / f"inputs_{st}.json") for st in rows_all},
            "n": {st: len(r) for st, r in rows_all.items()}, "code_sha256": sha(__file__),
            "label": "all development material (train split); not an independent test"}
    save(DATA / "selection_lock.json", lock)
    print(json.dumps(lock, indent=1))


if __name__ == "__main__":
    {"enumerate": do_enumerate, "extract": do_extract, "lock": do_lock}[sys.argv[1]]()
