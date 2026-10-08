"""iter_101: 별도 PadChest-GR 공식 train 환자의 흉수 명시 양성/음성 자료 선정 (CPU only, 모델 출력 미사용).

단계:
  enumerate : train 전체에서 문장 whitelist(수동 검토 규칙)로 영상 단위 흉수 상태 후보를 만들고 hash 순서·제외 근거·노출 기록을 저장.
  extract   : 각 상태 앞 20명(D4 2 + S24 12 + 시각 제외 예비 6)의 영상을 uint16>>8 uint8 PNG로 추출하고 contact sheet를 만든다.
  lock      : visual_audit.json(눈으로 확인한 제외 ID) 반영 후 D4/S24 입력·정답·잠금을 쓴다.
영상 규약은 report86_build_E와 동일(uint16 -> uint8 right shift 8). 새 산출물은 results/iter_101 아래에만 쓴다.
문장 whitelist는 원문을 사람(assistant)이 검토해 정한 것이며 전문의 검토가 아니다. 자동 정규식은 후보 열거에만 쓴다.
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
from PIL import Image

import pg39_data as D
from report86_common import ROOT, sha, sha_obj, save

R101 = ROOT / "results/iter_101"
DATA = R101 / "data"
TAG = "101"
N_POOL = 20          # 상태별 추출 풀(앞 20): D4 2 + S24 12 + 시각 제외 예비 6
N_D, N_S = 2, 12

# 수동 검토로 정한 whitelist(원문 sentence_en 정확 일치). 시간 비교·완화(probable/could/suspicion/signs of)·크기 제한 부정·
# 위치 불명확(ipsilateral)·fissure 국한·known·다른 부위(pericardial) 문장은 주상태 정답으로 쓰지 않는다.
POS_OK = {
    "Left pleural effusion.", "Bilateral pleural effusion.", "Pleural effusion.", "Right pleural effusion.",
    "Small pleural effusion.", "Small left pleural effusion.", "Small right pleural effusion.", "Slight left pleural effusion.",
    "Minimal left pleural effusion.", "Moderate right pleural effusion.", "Presence of left pleural effusion.",
    "Scant bilateral pleural effusion.", "Significant bilateral pleural effusion.", "Slight component of left pleural effusion.",
    "Small amount of bilateral pleural effusion.", "Small pleural effusion located in the left posterior costophrenic angle.",
    "Massive right pleural effusion, which displaces the mediastinum contralaterally.",
}
NEG_OK = {
    "There is no evidence of effusion.", "No pleural effusion.", "There is no pleural effusion.", "No pleural effusion is appreciated.",
    "No pleural effusion is observed.", "There is no evidence of pleural effusion or thickening.", "No pleural effusion or thickening.",
    "No signs suggestive of pleural effusion.", "There are no signs of pleural effusion.",
    "No condensations or pleural effusion are visualized.", "No infiltrates or pleural effusion in the current study.",
    "I do not appreciate pleural effusion.", "There is no evidence of consolidation or effusion.",
}
# 영상 안에 이 용어가 하나라도 whitelist 밖 문장으로 있으면 해당 영상은 모호하므로 제외(양·음 공통).
RELATED = re.compile(r"effusion|pleural fluid|fluid|hydrothorax|blunting|costophrenic|pleural (collection|liquid)|empyema", re.I)


def hkey(pid, iid):
    return hashlib.sha256(f"{TAG}|{pid}|{iid}".encode()).hexdigest()


def prior_id_sets():
    """이전 반복 산출물에서 ImageID/PatientID/StudyID를 모아 제외·노출 기록에 쓴다."""
    pats = {"E96": set(), "D8_iter085": set(), "iter100": set()}
    E = json.load(open(ROOT / "results/iter_086/E/inputs_E96.json"))
    E2 = json.load(open(ROOT / "results/iter_086/E/inputs_E192x.json"))
    D8 = json.load(open(ROOT / "results/iter_085/D8/inputs.json"))
    ex = {"patients": set(), "studies": set(), "images": set()}
    for name, rows in (("E96", E), ("E192x", E2), ("D8", D8)):
        for r in rows:
            ex["patients"].add(r["PatientID"]); ex["studies"].add(r["StudyID"]); ex["images"].add(r["ImageID"])
    # iter_100 선정 환자(D8 4명 + main 환자) 이미지 ID
    for p in (ROOT / "results/iter_100/data").rglob("requests.json"):
        for r in json.load(open(p)):
            ex["images"].add(r["id"].split("|")[0])
    # 보호된 확인 manifest: iter_040 manifest_eval(V96 + H192 held 192), iter_039 D24/E96/F 계열 manifest
    protected = list((ROOT / "results/iter_040/data").glob("manifest_eval_private.jsonl")) + \
        list((ROOT / "results/iter_039/data").glob("manifest*.jsonl"))
    assert protected, "protected manifests not found"
    ex["protected_files"] = [str(p.relative_to(ROOT)) for p in protected]
    for p in protected:
        for ln in open(p):
            d = json.loads(ln)
            ex["patients"].add(d["PatientID"]); ex["studies"].add(d["StudyID"]); ex["images"].add(d["ImageID"])
    return ex


def scan_exposure(target_ids):
    """results/iter_0*의 json/jsonl/csv/txt에서 target ImageID가 등장한 모든 파일(과거 사용·학습 노출 기록용). {id: [files]}"""
    pat = re.compile(r"[0-9]{20,}_[0-9a-z]+\.png")
    seen = {}
    for dirpath, dns, fns in os.walk(ROOT / "results"):
        dns[:] = [d for d in dns if d not in ("runtime_cache", "models", "hf", "images", "raw", "environments", "external", "datasets", "iter_101")]
        for fn in fns:
            if not fn.endswith((".json", ".jsonl", ".csv", ".txt")):
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > 60 << 20:
                    continue
                txt = p.read_text(errors="ignore")
            except OSError:
                continue
            for m in set(pat.findall(txt)):
                if m in target_ids:
                    seen.setdefault(m, []).append(str(p.relative_to(ROOT)))
    return seen


def image_status(r, links):
    """영상 단위 흉수 상태. returns (status, reason, sentences)."""
    pos, neg, other = [], [], []
    for f in r["findings"]:
        s = f["sentence_en"]
        if s in POS_OK:
            pos.append(s)
        elif s in NEG_OK:
            neg.append(s)
        elif RELATED.search(s):
            other.append(s)
    if other:
        return None, "related_nonwhitelist_sentence", other
    if pos and neg:
        return None, "pos_and_neg_in_image", pos + neg
    if pos:
        return "POS", "", pos
    if neg:
        return "NEG", "", neg
    return None, "no_effusion_statement", []


def do_enumerate():
    reports, m, links = D.load_inputs()
    ex = prior_id_sets()
    train = [r for r in reports if links["img2split"][r["ImageID"]] == "train"]
    per_img, excl = {}, Counter()
    for r in train:
        iid = r["ImageID"]
        st, why, sents = image_status(r, links)
        if st is None:
            if why != "no_effusion_statement":
                excl[why] += 1
            continue
        pid = links["img2patient"][iid]
        if pid in ex["patients"] or links["img2study"][iid] in ex["studies"] or iid in ex["images"]:
            excl["overlap_prior_selected_sets"] += 1
            continue
        per_img[iid] = {"ImageID": iid, "PatientID": pid, "StudyID": r["StudyID"], "status": st, "sentences": sents,
                        "has_previous": r["PreviousImageID"] is not None, "n_findings": len(r["findings"]), "hash": hkey(pid, iid)}
    # 환자 내 상태 혼재 제외
    by_pat = defaultdict(list)
    for v in per_img.values():
        by_pat[v["PatientID"]].append(v)
    mixed = {p for p, vs in by_pat.items() if len({v["status"] for v in vs}) > 1}
    excl["patient_mixed_states"] = len(mixed)
    reps = []
    for p, vs in by_pat.items():
        if p in mixed:
            continue
        reps.append(min(vs, key=lambda v: v["hash"]))
    order = {s: sorted([v for v in reps if v["status"] == s], key=lambda v: v["hash"]) for s in ("POS", "NEG")}
    pool_ids = {v["ImageID"] for s in order for v in order[s][:N_POOL]}
    expo = scan_exposure(pool_ids)
    for s in order:
        for v in order[s][:N_POOL]:
            v["earlier_use_files"] = expo.get(v["ImageID"], [])
    out = {"rule": "train only; image-level whitelist state; patient representative = min sha256('101|PatientID|ImageID') among qualifying images; "
                   "patients with both states excluded; order by representative hash; D4=first2, S24=next12 per state; spare=next6 (visual exclusion only)",
           "pos_ok": sorted(POS_OK), "neg_ok": sorted(NEG_OK), "related_regex": RELATED.pattern,
           "n_train_images": len(train), "exclusions": dict(excl),
           "n_images_with_status": Counter(v["status"] for v in per_img.values()),
           "n_patients_by_status": {s: len(order[s]) for s in order},
           "sentence_counts": {s: Counter(x for v in per_img.values() if v["status"] == s for x in v["sentences"]) for s in ("POS", "NEG")},
           "ordered_pool": {s: order[s][:N_POOL] for s in order},
           "protected_files": ex["protected_files"], "n_excluded_ids": {k: len(ex[k]) for k in ("patients", "studies", "images")},
           "raw_sha256": D.PINNED, "code_sha256": sha(__file__)}
    save(DATA / "enumeration.json", out)
    print(json.dumps({k: out[k] for k in ("n_train_images", "exclusions", "n_images_with_status", "n_patients_by_status")}, default=dict, indent=1))


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
            "u8_pixel_sha256": hashlib.sha256(b.tobytes()).hexdigest(), "file_sha256": sha(pu8), "h": int(h), "w": int(w),
            "u16_min": int(a.min()), "u16_max": int(a.max())}


def do_extract():
    en = json.loads((DATA / "enumeration.json").read_text())
    z = D.open_image_zip()
    idx = D.zip_index(z)
    meta = {}
    for s in ("POS", "NEG"):
        for rank, v in enumerate(en["ordered_pool"][s]):
            meta[v["ImageID"]] = {**extract_one(z, idx[v["ImageID"]], v["ImageID"]), "status": s, "rank": rank,
                                  "PatientID": v["PatientID"], "StudyID": v["StudyID"]}
    pix = Counter(m["u16_pixel_sha256"] for m in meta.values())
    dups = [k for k, c in pix.items() if c > 1]
    # 이전 manifest와의 pixel 중복
    prior_pix = set()
    for p in (ROOT / "results").glob("iter_0*/data/manifest*.jsonl"):
        for ln in open(p):
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            h = (d.get("image_meta") or {}).get("u16_pixel_sha256")
            if h:
                prior_pix.add(h)
    for q in (ROOT / "results").glob("iter_*/*/inputs*.json"):
        try:
            for d in json.load(open(q)):
                if isinstance(d, dict) and d.get("u16_pixel_sha256"):
                    prior_pix.add(d["u16_pixel_sha256"])
        except (ValueError, OSError):
            pass
    ov = {"within_pool_duplicate_pixel_hashes": len(dups),
          "pixel_overlap_with_prior_manifests": sum(m["u16_pixel_sha256"] in prior_pix for m in meta.values()),
          "n_prior_pixel_hashes_checked": len(prior_pix)}
    save(DATA / "extract_meta.json", {"meta": meta, "overlaps": ov, "convention": "uint16>>8 -> uint8 (iter_039/042/086과 동일)",
                                      "projection_note": "PadChest-GR 공개 metadata(report json, master_table)에 projection 필드 없음 — 시각 점검으로만 확인"})
    order = sorted((m["status"], m["rank"], k) for k, m in meta.items())
    from PIL import ImageDraw
    sheets = []
    for s in range(0, len(order), 20):
        part = order[s:s + 20]
        sheet = Image.new("L", (5 * 300, 4 * 320), 0)
        dr = ImageDraw.Draw(sheet)
        for i, (st, rank, k) in enumerate(part):
            im = Image.open(DATA / "images" / k).convert("L")
            im.thumbnail((300, 296))
            x, y = (i % 5) * 300, (i // 5) * 320
            sheet.paste(im, (x, y + 22))
            dr.text((x + 4, y + 4), f"{st}{rank} {k[:6]}", fill=255)
        p = DATA / "contact" / f"sheet_{s // 20:02d}.png"
        p.parent.mkdir(exist_ok=True)
        sheet.save(p)
        sheets.append({"file": str(p), "items": [f"{st}{rank}:{k}" for st, rank, k in part]})
    save(DATA / "contact_sheets.json", sheets)
    print(json.dumps(ov), len(sheets), "sheets")


def do_lock():
    en = json.loads((DATA / "enumeration.json").read_text())
    meta = json.loads((DATA / "extract_meta.json").read_text())["meta"]
    audit = json.loads((DATA / "visual_audit.json").read_text())
    excluded = {x["ImageID"] for x in audit["excluded"]}
    rows, raws, refs, sel = [], [], {}, {}
    for s in ("POS", "NEG"):
        keep = [v for v in en["ordered_pool"][s] if v["ImageID"] not in excluded]
        assert len(keep) >= N_D + N_S, (s, len(keep))
        sel[s] = {"D4": keep[:N_D], "S24": keep[N_D:N_D + N_S]}
    for stage in ("D4", "S24"):
        rr, rw = [], []
        for s in ("POS", "NEG"):
            for v in sel[s][stage]:
                m = meta[v["ImageID"]]
                rr.append({"PatientID": v["PatientID"], "StudyID": v["StudyID"], "ImageID": v["ImageID"], "image": m["image"],
                           "file_sha256": m["file_sha256"], "mode": "L", "size": [m["w"], m["h"]], "source": "iter_101 PadChest-GR train",
                           "split": "train", "stratum": s, "order_hash": v["hash"], "u16_pixel_sha256": m["u16_pixel_sha256"]})
                rw.append({"ImageID": v["ImageID"], "raw_path": m["raw_path"], "sha256": m["raw_png_sha256"]})
                refs[v["ImageID"]] = {"ImageID": v["ImageID"], "PatientID": v["PatientID"], "StudyID": v["StudyID"], "status": s, "stage": stage,
                                      "reference_sentences": v["sentences"], "earlier_use_files": v.get("earlier_use_files")}
        rr.sort(key=lambda r: r["order_hash"])  # 두 상태를 섞어 처리 순서를 고정
        order = {r["ImageID"]: i for i, r in enumerate(rr)}
        rw.sort(key=lambda r: order[r["ImageID"]])
        save(DATA / f"inputs_{stage}.json", rr)
        save(DATA / f"raw_manifest_{stage}.json", rw)
    save(DATA / "reference_private.json", refs)
    lock = {"enumeration_sha256": sha(DATA / "enumeration.json"), "extract_meta_sha256": sha(DATA / "extract_meta.json"),
            "visual_audit_sha256": sha(DATA / "visual_audit.json"), "inputs_D4_sha256": sha(DATA / "inputs_D4.json"),
            "inputs_S24_sha256": sha(DATA / "inputs_S24.json"), "reference_sha256": sha(DATA / "reference_private.json"),
            "counts": {st: Counter(r["stratum"] for r in json.loads((DATA / f"inputs_{st}.json").read_text())) for st in ("D4", "S24")},
            "code_sha256": sha(__file__), "n_excluded_visual": len(excluded)}
    # 환자/영상/study/pixel 교차 중복 검사
    allrows = json.loads((DATA / "inputs_D4.json").read_text()) + json.loads((DATA / "inputs_S24.json").read_text())
    for k in ("PatientID", "StudyID", "ImageID", "u16_pixel_sha256"):
        assert len({r[k] for r in allrows}) == len(allrows), k
    ex = prior_id_sets()
    prot_pix = set()
    for f in ex["protected_files"]:
        for ln in open(ROOT / f):
            h = (json.loads(ln).get("image_meta") or {}).get("u16_pixel_sha256")
            if h:
                prot_pix.add(h)
    assert prot_pix, "no protected pixel hashes"
    lock["protected_pixel_overlap"] = sum(r["u16_pixel_sha256"] in prot_pix for r in allrows)
    lock["n_protected_pixel_hashes"] = len(prot_pix)
    assert lock["protected_pixel_overlap"] == 0
    assert not any(r["PatientID"] in ex["patients"] or r["ImageID"] in ex["images"] or r["StudyID"] in ex["studies"] for r in allrows)
    save(DATA / "selection_lock.json", lock)
    print(json.dumps(lock, indent=1, default=dict))


if __name__ == "__main__":
    {"enumerate": do_enumerate, "extract": do_extract, "lock": do_lock}[sys.argv[1]]()
