"""iter_043 입력 연결·잠금 (CPU only, 모델 미사용). 출력 생성 전에 실행한다.

- T305/V96(=iter_039 E96 = iter_040 V96)/D24를 기존 manifest에서 읽어 iter_043 manifest로 합친다. H192/F120/test/MRI 항목은 manifest에 넣지 않는다
  (iter_040 eval manifest 파일에는 H192 행이 들어 있으므로 PatientID/StudyID 비중복 확인에만 ID로 사용하고 내용은 저장하지 않는다).
- 원본 파일·기존 요청 hash, 영상 file/pixel hash, 환자/study/영상/pixel 비중복, T305 문장 일치 층, 동일 문장 환자쌍(seed 4301), D8을 고정한다.
python pg43_prep.py --out-dir results/iter_043/data   (기존 파일 덮어쓰기 거부)
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

import pg39_data as D39
import pg39_spec as S39
from rsna_diag import generate as G

OUT_SEED_PAIR = 4301
SEED_D8 = 4303
PATHS = {
    "train_manifest": "results/iter_040/data/manifest_train_private.jsonl",
    "eval_manifest": "results/iter_040/data/manifest_eval_private.jsonl",
    "d_manifest": "results/iter_039/data/manifest_private.jsonl",
    "selection_lock_040": "results/iter_040/data/selection_lock.json",
    "req_V96": "results/iter_040/requests/requests_V96.jsonl",
    "req_D": "results/iter_039/requests_v2/requests_D.jsonl",
    "req_E96_039": "results/iter_039/requests/requests_E96.jsonl",
}


def fsha(p):
    return D39.sha256_file(p)


def norm_sentence(s):
    return " ".join(s.lower().split())


def read_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def entry(m, set_name, req_by_pt):
    meta = m["image_meta"]
    h, w = meta["h"], meta["w"]
    rq = req_by_pt[(m["PatientID"], "I-short")]
    for t in ("qA", "qB"):
        assert (t in rq), t
    e = {"set": set_name, "PatientID": m["PatientID"], "ImageID": m["ImageID"], "StudyID": m["StudyID"], "stratum": m["stratum"],
         "h": h, "w": w, "pad_top_left_side": m["pad_top_left_side"], "raw_png_sha256": meta["raw_png_sha256"],
         "u8_pixel_sha256": meta["u8_pixel_sha256"], "sentences": m["sentences"], "gt_boxes_xyxy_norm": m["gt_boxes_xyxy_norm"],
         "gt_canvas_yxyx": {t: S39.gt_to_canvas(m["gt_boxes_xyxy_norm"][t], h, w) for t in ("qA", "qB")},
         "labels": m["labels"], "finding_index": m["finding_index"]}
    e["image"] = rq["qA"]["image"]
    e["image_file_sha256"] = rq["qA"]["image_file_sha256"]
    e["input_pixel_sha256"] = rq["qA"]["input_pixel_sha256"]
    e["image_ids_match_request"] = rq["qA"]["image"] == rq["qB"]["image"] and rq["qA"]["input_pixel_sha256"] == rq["qB"]["input_pixel_sha256"]
    return e


def index_requests(rows, cond):
    out = defaultdict(dict)
    for r in rows:
        if r["cond"] == cond:
            assert len(r["targets"]) == 1
            assert r["targets"][0] not in out[(r["patient"], cond)], "dup request"
            out[(r["patient"], cond)][r["targets"][0]] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    if os.path.exists(os.path.join(a.out_dir, "manifest_private.json")):
        sys.exit("output exists")
    os.makedirs(a.out_dir, exist_ok=True)
    src_sha = {k: fsha(v) for k, v in PATHS.items()}
    lock40 = json.load(open(PATHS["selection_lock_040"]))
    assert lock40["manifest_train_sha256"] == src_sha["train_manifest"], "train manifest hash != iter_040 selection lock"
    assert lock40["manifest_eval_sha256"] == src_sha["eval_manifest"], "eval manifest hash != iter_040 selection lock"
    tr = read_jsonl(PATHS["train_manifest"])
    ev = read_jsonl(PATHS["eval_manifest"])
    dm = [m for m in read_jsonl(PATHS["d_manifest"]) if m["set"] == "D"]
    v96 = [m for m in ev if m["eval_set"] == "V96"]
    held = [m for m in ev if m["eval_set"] != "V96"]
    assert len(tr) == 305 and len(dm) == 24 and len(v96) == 96
    f120_ids = {(m["PatientID"], m["StudyID"], m["ImageID"]) for m in read_jsonl(PATHS["d_manifest"]) if m["set"] == "F"}
    h192_ids = {(m["PatientID"], m["StudyID"], m["ImageID"]) for m in held}
    req_v = index_requests(read_jsonl(PATHS["req_V96"]), "I-short")
    req_d = index_requests(read_jsonl(PATHS["req_D"]), "I-short")
    E = {"V96": [entry(m, "V96", req_v) for m in v96], "D24": [entry(m, "D24", req_d) for m in dm]}
    T = []
    for m in tr:
        T.append({"PatientID": m["PatientID"], "ImageID": m["ImageID"], "StudyID": m["StudyID"], "sentences": m["sentences"],
                  "gt_boxes_xyxy_norm": m["gt_boxes_xyxy_norm"], "u8_pixel_sha256": m["image_meta"]["u8_pixel_sha256"],
                  "raw_png_sha256": m["image_meta"]["raw_png_sha256"], "h": m["image_meta"]["h"], "w": m["image_meta"]["w"]})
    # ---- 비중복 검사 (환자/study/영상/pixel) ----
    groups = {"T305": T, "D24": E["D24"], "V96": E["V96"]}
    ov = {}
    for key in ("PatientID", "StudyID", "ImageID", "u8_pixel_sha256", "raw_png_sha256"):
        sets = {g: [x[key] for x in v] for g, v in groups.items()}
        for g, v in sets.items():
            assert len(v) == len(set(v)), f"duplicate {key} inside {g}"
        names = list(sets)
        for i in range(3):
            for j in range(i + 1, 3):
                ov[f"{key}:{names[i]}&{names[j]}"] = len(set(sets[names[i]]) & set(sets[names[j]]))
    ov["vs_H192(patient,study,image)"] = sum((x["PatientID"], x["StudyID"], x["ImageID"]) in h192_ids
                                            for g in groups.values() for x in g)
    ov["vs_F120(patient,study,image)"] = sum((x["PatientID"], x["StudyID"], x["ImageID"]) in f120_ids
                                            for g in groups.values() for x in g)
    ov["H192_patient_overlap"] = len({x["PatientID"] for g in groups.values() for x in g} & {h[0] for h in h192_ids})
    ov["F120_patient_overlap"] = len({x["PatientID"] for g in groups.values() for x in g} & {h[0] for h in f120_ids})
    assert all(v == 0 for v in ov.values()), ov
    # ---- 현재 영상 file/pixel hash ----
    for g in ("D24", "V96"):
        for e in E[g]:
            assert e["image_ids_match_request"]
            assert fsha(e["image"]) == e["image_file_sha256"], e["image"]
            assert G.load_image(e["image"])[2] == e["input_pixel_sha256"], e["image"]
    # ---- 문장 ----
    tr_norm = Counter(norm_sentence(s) for x in T for s in x["sentences"].values())
    v_sents = [(e["PatientID"], t, e["sentences"][t]) for e in E["V96"] for t in ("qA", "qB")]
    in_train = [norm_sentence(s) in tr_norm for _, _, s in v_sents]
    d_sents = [(e["PatientID"], t, e["sentences"][t]) for e in E["D24"] for t in ("qA", "qB")]
    d_in_train = [norm_sentence(s) in tr_norm for _, _, s in d_sents]
    # ---- 동일 문장 환자쌍 (원문 완전 일치, 서로 다른 환자, greedy, seed 4301) ----
    by_sent = defaultdict(list)
    for pid, t, s in v_sents:
        by_sent[s].append((pid, t))
    edges = []
    for s, eps in by_sent.items():
        for i in range(len(eps)):
            for j in range(i + 1, len(eps)):
                if eps[i][0] == eps[j][0]:
                    continue
                ea, eb = sorted([eps[i], eps[j]])
                key = hashlib.sha256(f"{OUT_SEED_PAIR}|{s}|{ea}|{eb}".encode()).hexdigest()
                edges.append((key, s, ea, eb))
    edges.sort()
    used, pairs = set(), []
    for key, s, ea, eb in edges:
        if ea[0] in used or eb[0] in used:
            continue
        used.update([ea[0], eb[0]])
        pairs.append({"pair_id": len(pairs), "sentence": s, "a": {"PatientID": ea[0], "qID": ea[1]},
                      "b": {"PatientID": eb[0], "qID": eb[1]}, "edge_hash": key})
    ev_by = {e["PatientID"]: e for e in E["V96"]}
    for p in pairs:
        for side in ("a", "b"):
            e = ev_by[p[side]["PatientID"]]
            assert e["sentences"][p[side]["qID"]] == p["sentence"]
            assert e["gt_boxes_xyxy_norm"][p[side]["qID"]], "empty GT"
    clusters = sorted({p["sentence"] for p in pairs})
    for p in pairs:
        p["cluster"] = clusters.index(p["sentence"])
    # ---- D8: 층 비례(largest remainder), 층 내 hash 순 ----
    by_st = defaultdict(list)
    for e in E["D24"]:
        by_st[e["stratum"]].append(e)
    for k in by_st:
        by_st[k].sort(key=lambda e: D39.h(SEED_D8, "D8", e["PatientID"]))
    cnt = {k: len(v) for k, v in by_st.items()}
    q = D39.apportion(cnt, 8)
    d8 = [e["PatientID"] for k in sorted(by_st) for e in by_st[k][:q.get(k, 0)]]
    assert len(d8) == 8
    man = {"T305": T, "D24": E["D24"], "V96": E["V96"], "pairs": pairs, "D8": d8}
    summ = {"source_files_sha256": src_sha, "overlap_checks": ov,
            "n": {"T305": len(T), "D24": 24, "V96": 96, "T305_sentences": 610},
            "V96_sentences_exact_in_T305_normalized": [sum(in_train), len(in_train)],
            "D24_sentences_in_T305_normalized": [sum(d_in_train), len(d_in_train)],
            "n_edges": len(edges), "n_pairs": len(pairs), "n_pair_patients": 2 * len(pairs), "n_clusters": len(clusters),
            "cluster_sizes": Counter(p["cluster"] for p in pairs), "D8_quota": q, "D8": d8,
            "V96_repeated_sentence_types": sum(1 for v in by_sent.values() if len(v) > 1),
            "pair_seed": OUT_SEED_PAIR, "d8_seed": SEED_D8,
            "hash_check_note": "D24/V96 current image file & padded-pixel hashes equal request rows (iter_039/iter_040)",
            "excluded_sets_note": "H192/F120 rows are not copied into the iter_043 manifest; only IDs were compared for non-overlap."}
    tmp = os.path.join(a.out_dir, f"manifest_private.{os.getpid()}.tmp")
    json.dump(man, open(tmp, "w"), indent=0)
    os.replace(tmp, os.path.join(a.out_dir, "manifest_private.json"))
    summ["manifest_sha256"] = fsha(os.path.join(a.out_dir, "manifest_private.json"))
    json.dump(summ, open(os.path.join(a.out_dir, "selection_summary.json"), "x"), indent=1, default=str)
    lock = {"manifest_sha256": summ["manifest_sha256"], "source_files_sha256": src_sha, "prep_source_sha256": fsha("pg43_prep.py"),
            "pairs_sha256": hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest(), "d8": d8}
    json.dump(lock, open(os.path.join(a.out_dir, "selection_lock.json"), "x"), indent=1)
    print(json.dumps({k: summ[k] for k in ("n_pairs", "n_pair_patients", "n_clusters", "V96_sentences_exact_in_T305_normalized",
                                          "overlap_checks", "D8_quota")}, default=str))


if __name__ == "__main__":
    main()
