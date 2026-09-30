"""iter_042 자료 확정: 후보 열거 -> 눈가림 검토 반영 -> 환자당 1영상 -> 영상 추출·hash -> manifest·요청·잠금. (CPU only)

결과: results/iter_042/{data,requests}/ (Git 제외, private). 모델 출력은 사용하지 않는다.
영상 규약은 iter_039와 동일(uint16 >> 8, 값 보존 RGB 복제, 중앙 square padding). 기존 결과·manifest는 읽기만 한다.
E는 양성>=24 & 음성>=32일 때만 요청을 만든다. 미달이면 gate만 기록하고 종료(exit 3).
python pg42_build.py
"""
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter

import numpy as np
from PIL import Image

import pg39_data as D
import pg39_spec as S39
import pg42_data as P
import pg42_spec as S
from rsna_diag import generate as G
from rsna_diag import geometry

OUT = "results/iter_042"
CONVENTION = "uint16 -> uint8 by right shift 8 (skimage.util.img_as_ubyte equivalent); no window/min-max/flip (iter_039와 동일)"
HEDGE_RE = re.compile(r"probabl|could|suspicion|possible|rule out|cannot be excluded|compatible|suggest", re.I)
MODELS = ["M0", "C"]
MIN_POS, MIN_NEG = 24, 32
N_D_POS, N_D_NEG = 3, 3


def sha(b):
    return hashlib.sha256(b).hexdigest()


def extract(z, idx, iid, img_dir):
    zi = idx[iid]
    raw = z.read(zi)
    a = np.asarray(Image.open(io.BytesIO(raw)))
    if a.dtype != np.uint16 or a.ndim != 2:
        raise D.InputError(f"{iid}: unexpected image dtype/shape {a.dtype} {a.shape}")
    b = (a >> 8).astype(np.uint8)
    path = os.path.join(img_dir, iid)
    if not os.path.exists(path):
        tmp = path + f".{os.getpid()}.tmp.png"
        Image.fromarray(b).save(tmp)
        os.replace(tmp, path)
    h, w = a.shape
    return {"path": path, "zip_member": zi.filename, "zip_crc": zi.CRC, "raw_png_sha256": sha(raw),
            "u16_pixel_sha256": sha(a.tobytes()), "u8_pixel_sha256": sha(b.tobytes()), "h": int(h), "w": int(w),
            "u16_min": int(a.min()), "u16_max": int(a.max())}


def resolve_prefix(pref, cands):
    hit = [c for c in cands if c["ImageID"].startswith(pref)]
    if len(hit) != 1:
        raise RuntimeError(f"review prefix {pref} matches {len(hit)} candidates")
    return hit[0]["ImageID"]


def one_per_patient(cands):
    by = {}
    for c in cands:
        by.setdefault(c["PatientID"], []).append(c)
    return sorted([min(v, key=lambda c: P.sel_hash(c["PatientID"], c["ImageID"])) for v in by.values()],
                  key=lambda c: P.sel_hash(c["PatientID"], c["ImageID"]))


def prior_pixel_hashes():
    s = set()
    for p in P.EXCLUDE_MANIFESTS:
        for ln in open(p):
            d = json.loads(ln)
            s.add(d["image_meta"]["u16_pixel_sha256"])
    return s


def main():
    if os.path.exists(f"{OUT}/data/selection_lock.json"):
        sys.exit("selection_lock.json exists: refuse to rebuild (new attempt path required)")
    review = json.load(open(f"{OUT}/data/review_private.json"))
    reports, m, links = D.load_inputs()
    rep_by = {r["ImageID"]: r for r in reports}
    exclude = P.load_excluded()
    all_c = P.enumerate_candidates(reports, links, exclude=exclude)
    # D: T305/D24 환자 (iter_039 D + iter_040 train)
    d_pats = set()
    for pth in P.EXCLUDE_MANIFESTS[:2]:
        for ln in open(pth):
            d = json.loads(ln)
            if pth.endswith("manifest_private.jsonl") and d["set"] != "D":
                continue
            d_pats.add(d["PatientID"])
    d_c = P.enumerate_candidates(reports, links, restrict_patients=d_pats)
    ex_neg = {resolve_prefix(k, all_c["neg"] + d_c["neg"]): v for k, v in review["negative_excluded_prefix"].items()}
    ex_pos = {resolve_prefix(k, all_c["pos"] + d_c["pos"]): v for k, v in review["positive_excluded_prefix"].items()}
    counts = {"E_neg_enumerated": len(all_c["neg"]), "E_pos_enumerated": len(all_c["pos"]),
              "D_neg_enumerated": len(d_c["neg"]), "D_pos_enumerated": len(d_c["pos"])}

    def apply(cs, ex):
        return [c for c in cs if c["ImageID"] not in ex]
    E_neg = one_per_patient(apply(all_c["neg"], ex_neg))
    E_pos = one_per_patient(apply(all_c["pos"], ex_pos))
    D_neg = one_per_patient(apply(d_c["neg"], ex_neg))
    D_pos = one_per_patient(apply(d_c["pos"], ex_pos))
    overlap = ({c["PatientID"] for c in E_neg} & {c["PatientID"] for c in E_pos}) | \
              ({c["PatientID"] for c in D_neg} & {c["PatientID"] for c in D_pos})
    if overlap:
        sys.exit(f"patient in both groups: {len(overlap)}")
    if {c["PatientID"] for c in D_neg + D_pos} & {c["PatientID"] for c in E_neg + E_pos}:
        sys.exit("D/E patient overlap")
    D_sel = [("pos", c) for c in D_pos[:N_D_POS]] + [("neg", c) for c in D_neg[:N_D_NEG]]
    E_sel = [("pos", c) for c in E_pos] + [("neg", c) for c in E_neg]
    n_pos, n_neg = len(E_pos), len(E_neg)
    gate = {"n_pos": n_pos, "n_neg": n_neg, "min_pos": MIN_POS, "min_neg": MIN_NEG, "run": n_pos >= MIN_POS and n_neg >= MIN_NEG}
    os.makedirs(f"{OUT}/data", exist_ok=True)
    os.makedirs(f"{OUT}/requests", exist_ok=True)
    json.dump({"counts": counts, "gate": gate, "excluded_by_review": {"neg": len(ex_neg), "pos": len(ex_pos)},
               "D_n": {"pos": min(N_D_POS, len(D_pos)), "neg": min(N_D_NEG, len(D_neg))}},
              open(f"{OUT}/data/preselect_summary.json", "w"), indent=1)
    if not gate["run"] or not D_pos or not D_neg:
        print("GATE FAIL", json.dumps(gate))
        sys.exit(3)
    z = D.open_image_zip()
    zidx = D.zip_index(z)
    missing = [c["ImageID"] for _, c in D_sel + E_sel if c["ImageID"] not in zidx]
    if missing:
        sys.exit(f"{len(missing)} selected images missing in zip")
    img_dir = f"{OUT}/data/images"
    os.makedirs(img_dir, exist_ok=True)
    prior_px = prior_pixel_hashes()
    manifest, seen_px = [], {}
    for name, sel in (("D", D_sel), ("E", E_sel)):
        for grp, c in sel:
            meta = extract(z, zidx, c["ImageID"], img_dir)
            r = rep_by[c["ImageID"]]
            px = meta["u16_pixel_sha256"]
            if px in seen_px:
                sys.exit(f"duplicate pixel hash within iter_042 set: {c['PatientID']}")
            seen_px[px] = c["PatientID"]
            top, left, side = geometry.pad_offsets(meta["h"], meta["w"])
            rec = {"set": name, "group": grp, "PatientID": c["PatientID"], "ImageID": c["ImageID"], "StudyID": c["StudyID"],
                   "image_meta": meta, "pad_top_left_side": [top, left, side], "pixel_seen_in_prior_iters": px in prior_px}
            if grp == "pos":
                rec["gt_boxes_xyxy_norm"] = {"qA": c["boxes"]}
                rec["target_sentences"] = c["target_sentences"]
                rec["flags"] = {"hedged": any(HEDGE_RE.search(s) for s in c["target_sentences"])}
            else:
                sents = [s[1] for s in c["neg_sentences"]]
                rec["neg_sentences_en"] = sents
                rec["neg_sentences_es"] = [s[2] for s in c["neg_sentences"]]
                rec["flags"] = {"bare_effusion": not any(re.search(r"pleural", s, re.I) for s in sents),
                                "hedged_neg": any(s.startswith("I do not") for s in sents)}
            manifest.append(rec)
    if E_ := [r for r in manifest if r["set"] == "E" and r["pixel_seen_in_prior_iters"]]:
        sys.exit(f"E image pixel hash seen in prior iter manifests: {len(E_)}")
    mp = f"{OUT}/data/manifest_private.jsonl"
    with open(mp, "w") as f:
        for r in manifest:
            f.write(json.dumps(r) + "\n")
    prompts = S.build_prompts()
    rows_by = {}
    for r in manifest:
        meta = r["image_meta"]
        fsha = sha(open(meta["path"], "rb").read())
        psha_img = G.load_image(meta["path"])[2]
        for model in MODELS:
            kind = f"{r['set']}_{model}"
            for cond in S.CONDS:
                prompt = prompts[cond]
                psha = S39.sha(prompt)
                rows_by.setdefault(kind, []).append({
                    "request_id": S.request_id(kind, r["PatientID"], cond, psha, meta["u8_pixel_sha256"]), "kind": kind,
                    "patient": r["PatientID"], "image_id": r["ImageID"], "cond": cond, "targets": [S.TARGET_ID],
                    "prompt": prompt, "prompt_sha256": psha, "caps": S.CAPS, "image": meta["path"], "image_file_sha256": fsha,
                    "input_pixel_sha256": psha_img, "order_key": D.h(D.SEED, "order42", r["PatientID"], cond)})
    for k, rows in rows_by.items():
        rows.sort(key=lambda x: x["order_key"])
        with open(f"{OUT}/requests/requests_{k}.jsonl", "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
    summ = {"spec": S.SPEC_VERSION, "convention": CONVENTION, "raw_inputs_sha256": links["inputs_sha256"], "counts": counts,
            "gate": gate, "D_n": {"pos": sum(1 for g, _ in D_sel if g == "pos"), "neg": sum(1 for g, _ in D_sel if g == "neg")},
            "E_n": {"pos": n_pos, "neg": n_neg},
            "E_flags": {"pos_hedged": sum(1 for r in manifest if r["set"] == "E" and r["group"] == "pos" and r["flags"]["hedged"]),
                        "neg_bare_effusion": sum(1 for r in manifest if r["set"] == "E" and r["group"] == "neg" and r["flags"]["bare_effusion"])},
            "excluded_by_review": {"neg": len(ex_neg), "pos": len(ex_pos)},
            "n_requests": {k: len(v) for k, v in rows_by.items()}, "manifest_sha256": D.sha256_file(mp),
            "request_files_sha256": {k: D.sha256_file(f"{OUT}/requests/requests_{k}.jsonl") for k in rows_by},
            "review_private_sha256": D.sha256_file(f"{OUT}/data/review_private.json"),
            "prompts_sha256": {k: S39.sha(v) for k, v in prompts.items()}}
    json.dump(summ, open(f"{OUT}/data/selection_summary.json", "w"), indent=1)
    json.dump({"manifest_sha256": summ["manifest_sha256"], "request_files_sha256": summ["request_files_sha256"],
               "review_private_sha256": summ["review_private_sha256"]}, open(f"{OUT}/data/selection_lock.json", "w"), indent=1)
    print(json.dumps({k: summ[k] for k in ("D_n", "E_n", "E_flags", "n_requests", "gate")}, indent=1))


if __name__ == "__main__":
    main()
