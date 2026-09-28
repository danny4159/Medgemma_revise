"""iter_023 stage 실행기. 각 stage는 이전 stage의 decision·현재 파일 hash·요청 집합을 재검증한 뒤에만 진행한다.

사용:
  python -m rsna_diag.roi23_pipeline manifests
  python -m rsna_diag.roi23_pipeline requests --stage D24
  python -m rsna_diag.roi23_pipeline requests --stage E60
  python -m rsna_diag.roi23_pipeline requests --stage E200
  python -m rsna_diag.roi23_pipeline score --stage D24
  python -m rsna_diag.roi23_pipeline score --stage E60
  python -m rsna_diag.roi23_pipeline score --stage E200
"""
import argparse
import json
import os

import numpy as np

from . import prompts as P, roi23_data as D, roi23_eval as E, roi23_requests as Q, roi23_spec as R

OUT = Q.OUT


def atomic_json(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def build_manifests():
    os.makedirs(f"{OUT}/manifests", exist_ok=True)
    val_items, val_gts = D.load_val_pool()
    conf_items, conf_gts = D.load_confirm_pool()
    D.check_disjoint(val_items.keys(), conf_items.keys())
    vpix = {v["pixel_sha256"] for v in val_items.values()}
    cpix = {v["pixel_sha256"] for v in conf_items.values()}
    if vpix & cpix:
        raise D.DataError(f"pixel overlap between val/confirm pools: {len(vpix & cpix)}")

    d24, d24_counts = D.select_d24(val_items, val_gts)
    e60_prim, e60_bnd = D.e_set("E180", conf_gts)
    e200_prim, e200_bnd = D.e_set("E600", conf_gts)
    if not (set(e60_prim) <= set(e200_prim) and set(e60_bnd) <= set(e200_bnd)):
        raise D.DataError("E60 is not a subset of E200 (unexpected sets.json change)")

    all_items = {}
    all_items.update({i: val_items[i] for i in d24})
    all_items.update({i: conf_items[i] for i in set(e200_prim) | set(e200_bnd)})
    gray = D.ensure_gray_image(f"{OUT}/data")

    src_path = f"{OUT}/manifests/source_manifest.jsonl"
    if not os.path.exists(src_path):
        with open(src_path, "w") as f:
            for i in sorted(all_items):
                f.write(json.dumps(all_items[i]) + "\n")

    def gt_row(i, gts):
        boxes = [b["yxyx_norm"] for b in gts[i]["boxes"]]
        return {"id": i, "category": gts[i]["category"], "boxes": gts[i]["boxes"],
                "answers": R.answers(boxes), "margin_ok": R.margin_ok(boxes) if boxes else None}

    labels_path = f"{OUT}/manifests/labels.json"
    if not os.path.exists(labels_path):
        labels = {i: gt_row(i, val_gts) for i in d24}
        labels.update({i: gt_row(i, conf_gts) for i in set(e200_prim) | set(e200_bnd)})
        atomic_json(labels, labels_path)

    sets_path = f"{OUT}/manifests/sets.json"
    if not os.path.exists(sets_path):
        sets = {"D24": {"primary": d24, "boundary": [], "layer_counts": d24_counts},
                "E60": {"primary": e60_prim, "boundary": e60_bnd},
                "E200": {"primary": e200_prim, "boundary": e200_bnd},
                "gray": gray}
        atomic_json(sets, sets_path)

    tab = Q.checkpoints()
    print(json.dumps({"d24_n": len(d24), "e60_primary": len(e60_prim), "e60_boundary": len(e60_bnd),
                      "e200_primary": len(e200_prim), "e200_boundary": len(e200_bnd),
                      "ckpts": {k: v.get("digest") for k, v in tab.items()}}))


def _load_sets():
    return json.load(open(f"{OUT}/manifests/sets.json"))


def _load_labels():
    return json.load(open(f"{OUT}/manifests/labels.json"))


def _load_source_items():
    items = {}
    for ln in open(f"{OUT}/manifests/source_manifest.jsonl"):
        if ln.strip():
            r = json.loads(ln)
            items[r["id"]] = r
    return items


def stage_patients(stage, sets_):
    if stage == "D24":
        return sets_["D24"]["primary"] + sets_["D24"]["boundary"]
    if stage in ("E60", "E200"):
        return sets_[stage]["primary"] + sets_[stage]["boundary"]
    raise ValueError(stage)


def bbox_pred_for(ckpt, prompt_name, ids, conf_only=True):
    """M0/B0 predicted bbox for ids from iter_012 confirm raw output (con_* only; D24 val_* patients need fresh
    generation and are handled separately by the D24-bbox request/gen path)."""
    recs, n_total = D.source_bbox_records(ckpt, prompt_name)
    out = {}
    for i in ids:
        boxes, status = D.predicted_boxes(recs.get(i))
        out[i] = (boxes, status)
    return out, recs


def cmd_requests(stage, cfg):
    sets_ = _load_sets()
    labels = _load_labels()
    items = _load_source_items()
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    fmt = "plain"
    patients = stage_patients(stage, sets_)
    gts = {i: {"boxes": labels[i]["boxes"]} for i in patients}
    written = []

    if stage == "D24":
        d24_items = {i: items[i] for i in patients}
        rows_bbox_m0 = Q.build_bbox_rows(d24_items, "M0", tab, cfg, "D24_bbox")
        rows_bbox_b0 = Q.build_bbox_rows(d24_items, "B0", tab, cfg, "D24_bbox")
        written.append(Q.write_rows("D24_bbox", "M0", rows_bbox_m0))
        written.append(Q.write_rows("D24_bbox", "B0", rows_bbox_b0))
        print(json.dumps({"stage": "D24_bbox", "written": written, "n_m0": len(rows_bbox_m0), "n_b0": len(rows_bbox_b0)}))
        return

    if stage in ("E60", "E200"):
        b0_recs, _ = D.source_bbox_records("B0", "concise")
        bbox_pred_b0 = {i: D.predicted_boxes(b0_recs.get(i)) for i in patients}
        d24_items = {i: items[i] for i in patients}
        row_sets = Q.build_stage(d24_items, gts, tab, fmt, cfg, stage, bbox_pred_b0)
        for k, rows in row_sets.items():
            written.append(Q.write_rows(stage, k, rows))
        print(json.dumps({"stage": stage, "written": written, "counts": {k: len(v) for k, v in row_sets.items()}}))
        return
    raise ValueError(stage)


def cmd_qa_requests_d24(cfg):
    """D24 bbox 완료 후 호출: B0 예측 bbox를 D24 원시 결과에서 읽어 6조건 QA 요청(576)을 만든다."""
    sets_ = _load_sets()
    labels = _load_labels()
    items = _load_source_items()
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    fmt = "plain"
    patients = stage_patients("D24", sets_)
    gts = {i: {"boxes": labels[i]["boxes"]} for i in patients}
    b0_dir = f"{OUT}/gen/D24_bbox__B0"
    recs = {}
    import glob
    for f in sorted(glob.glob(f"{b0_dir}/gen_worker*.jsonl")):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r.get("condition") == "bbox_concise":
                    recs[r["id"]] = r
    bbox_pred_b0 = {i: D.predicted_boxes(recs.get(i)) for i in patients}
    d24_items = {i: items[i] for i in patients}
    row_sets = Q.build_stage(d24_items, gts, tab, fmt, cfg, "D24", bbox_pred_b0)
    written = [Q.write_rows("D24", k, rows) for k, rows in row_sets.items()]
    gray = sets_["gray"]
    gray_rows = Q.build_gray(gray, tab, fmt, cfg)
    for k, rows in gray_rows.items():
        written.append(Q.write_rows("gray", k, rows))
    print(json.dumps({"written": written, "counts": {k: len(v) for k, v in row_sets.items()}}))


ROW_KEYS = ("D_M0", "D_B0", "L", "U", "O_M0", "O_B0")


def _load_rows(stage, key):
    return Q.load_rows(f"{OUT}/requests/{stage}__{key}.jsonl")


def _verify_and_collect(stage, key, fmt):
    from . import roi23_gen
    rows = _load_rows(stage, key)
    gen_dir = f"{OUT}/gen/{stage}__{key}"
    cp = os.path.join(gen_dir, "completion.json")
    if not os.path.exists(cp):
        raise RuntimeError(f"no completion.json in {gen_dir} (stage {stage}/{key} not finished)")
    c = json.load(open(cp))
    if (c.get("n_expected") != len(rows) or c.get("n_actual_unique") != len(rows) or c.get("n_missing") != 0
            or c.get("n_duplicate") != 0 or c.get("n_extra") != 0 or not c.get("returncodes")
            or any(x != 0 for x in c["returncodes"])):
        raise RuntimeError(f"completion.json content invalid in {gen_dir}: {c}")
    from . import generate
    cache = {}

    def px(p):
        if p not in cache:
            cache[p] = generate.load_image(p)[2]
        return cache[p]

    import glob
    files = {f: roi23_gen.read_strict(f) for f in sorted(glob.glob(f"{gen_dir}/gen_worker*.jsonl"))}
    adapter_digest = rows[0]["adapter_digest"]
    cdig = rows[0]["config_digest"]
    pdig = files and next(iter(files.values()))[0]["protocol_digest"] if any(files.values()) else None
    done = roi23_gen.validate_records(files, rows, cdig, adapter_digest, pdig, px)
    per_patient = E.collect(rows, done, fmt)
    return rows, per_patient, c


def _rule_series(bbox_by_id, gt, patients):
    vals, detail, n_invalid = E.rule_q4_series(bbox_by_id, gt, patients)
    return vals, detail, n_invalid


def cmd_score(stage):
    sets_ = _load_sets()
    labels = _load_labels()
    fmt = "plain"
    primary = sets_[stage]["primary"]
    boundary = sets_[stage]["boundary"]
    gt = {i: labels[i]["answers"] for i in primary + boundary}

    per_by_key, completion_by_key = {}, {}
    for key in ROW_KEYS:
        rows, per_patient, c = _verify_and_collect(stage, key, fmt)
        per_by_key[key] = per_patient
        completion_by_key[key] = {"n": len(rows), "wall_s": None}

    q4 = {}
    for key in ROW_KEYS:
        vals_p, det_p = E.q4_series(per_by_key[key], gt, primary)
        vals_b, det_b = E.q4_series(per_by_key[key], gt, boundary) if boundary else (None, None)
        q4[key] = {"primary": vals_p, "boundary": vals_b, "detail_primary": det_p, "detail_boundary": det_b}

    if stage == "D24":
        import glob
        def load_bbox_dir(gen_dir, cond):
            recs = {}
            for f in sorted(glob.glob(f"{gen_dir}/gen_worker*.jsonl")):
                for ln in open(f):
                    if ln.strip():
                        r = json.loads(ln)
                        if r.get("condition") == cond:
                            recs[r["id"]] = r
            return recs
        m0_off = load_bbox_dir(f"{OUT}/gen/D24_bbox__M0", "bbox_official_long")
        m0_con = load_bbox_dir(f"{OUT}/gen/D24_bbox__M0", "bbox_concise")
        b0_con = load_bbox_dir(f"{OUT}/gen/D24_bbox__B0", "bbox_concise")
        bbox_m0_off = {i: D.predicted_boxes(m0_off.get(i)) for i in primary + boundary}
        bbox_m0_con = {i: D.predicted_boxes(m0_con.get(i)) for i in primary + boundary}
        bbox_b0_con = {i: D.predicted_boxes(b0_con.get(i)) for i in primary + boundary}
    else:
        m0_recs, _ = D.source_bbox_records("M0", "official_long")
        m0c_recs, _ = D.source_bbox_records("M0", "concise")
        b0_recs, _ = D.source_bbox_records("B0", "concise")
        bbox_m0_off = {i: D.predicted_boxes(m0_recs.get(i)) for i in primary + boundary}
        bbox_m0_con = {i: D.predicted_boxes(m0c_recs.get(i)) for i in primary + boundary}
        bbox_b0_con = {i: D.predicted_boxes(b0_recs.get(i)) for i in primary + boundary}

    r_m0_off_p, r_m0_off_det, r_m0_off_inv = _rule_series(bbox_m0_off, gt, primary)
    r_m0_con_p, _, r_m0_con_inv = _rule_series(bbox_m0_con, gt, primary)
    r_b0_p, r_b0_det, r_b0_inv = _rule_series(bbox_b0_con, gt, primary)

    cmp_ = {}
    cmp_["delta_direct"] = E.paired_ci(q4["D_B0"]["primary"], q4["D_M0"]["primary"])
    cmp_["G_official"] = E.paired_ci(r_b0_p, r_m0_off_p)
    cmp_["G_concise"] = E.paired_ci(r_b0_p, r_m0_con_p)
    cmp_["reader_L_minus_U"] = E.paired_ci(q4["L"]["primary"], q4["U"]["primary"])
    cmp_["RB0_minus_DB0"] = E.paired_ci(r_b0_p, q4["D_B0"]["primary"])
    cmp_["L_minus_DB0"] = E.paired_ci(q4["L"]["primary"], q4["D_B0"]["primary"])

    valid_rates = {key: E.valid_rate(per_by_key[key], primary + boundary) for key in ROW_KEYS}
    oracle_acc = {}
    for key in ("O_M0", "O_B0"):
        n_correct, n_tot = 0, 0
        for i in primary + boundary:
            d = per_by_key[key].get(i, {})
            for t in R.TARGETS:
                if d.get(t, {}).get("status") == "valid":
                    n_tot += 1
                    n_correct += int(d[t]["answer"] == gt[i][t])
        oracle_acc[key] = {"n_correct": n_correct, "n_question_valid": n_tot,
                            "acc_on_valid": (n_correct / n_tot if n_tot else None)}

    boxcount = {}
    for i in primary:
        n = len(labels[i]["boxes"])
        boxcount.setdefault(n, {"n": 0, "DM0_correct": 0, "DB0_correct": 0})
        boxcount[n]["n"] += 1
        boxcount[n]["DM0_correct"] += int(q4["D_M0"]["detail_primary"][i]["correct"])
        boxcount[n]["DB0_correct"] += int(q4["D_B0"]["detail_primary"][i]["correct"])

    perm = {}
    gt_ids, gt_mat = None, None
    ids_gt = primary
    gt_mat_full = np.array([[1 if gt[i][t] == "yes" else 0 for t in R.TARGETS] for i in ids_gt])
    for key in ("D_M0", "D_B0", "L"):
        kept, pm = E.to_bool_matrix(per_by_key[key], ids_gt)
        if len(kept) >= 2:
            idxmap = [ids_gt.index(i) for i in kept]
            gtm = gt_mat_full[idxmap]
            perm[key] = E.permutation_association(pm, gtm, seed=23023, B=10000)
            perm[key]["n_valid_patients"] = len(kept)

    gray_report = {}
    try:
        gray_rows_m0 = _load_rows("gray", "D_M0")
        gray_rows_b0 = _load_rows("gray", "D_B0")
        _, per_gray_m0, _ = _verify_and_collect("gray", "D_M0", fmt)
        _, per_gray_b0, _ = _verify_and_collect("gray", "D_B0", fmt)
        gray_report = {"M0": per_gray_m0.get("control_gray"), "B0": per_gray_b0.get("control_gray")}
    except (FileNotFoundError, RuntimeError):
        gray_report = {"note": "gray control not generated yet"}

    report = {
        "stage": stage, "n_primary": len(primary), "n_boundary": len(boundary),
        "q4_mean": {k: {"primary": float(np.mean(v["primary"])), "boundary": (float(np.mean(v["boundary"])) if v["boundary"] is not None else None)} for k, v in q4.items()},
        "comparisons": cmp_,
        "rule_coverage": {"R_M0_official_invalid": r_m0_off_inv, "R_M0_concise_invalid": r_m0_con_inv, "R_B0_invalid": r_b0_inv,
                          "R_M0_official_q4_mean": float(np.mean(r_m0_off_p)), "R_M0_concise_q4_mean": float(np.mean(r_m0_con_p)),
                          "R_B0_q4_mean": float(np.mean(r_b0_p))},
        "valid_rates": {k: {"n_valid": v[0], "n_total": v[1], "rate": v[0] / v[1]} for k, v in valid_rates.items()},
        "oracle_accuracy": oracle_acc,
        "boxcount_breakdown": boxcount,
        "permutation_association": perm,
        "gray_control": gray_report,
        "fixed_pattern_baseline": _fixed_pattern_baseline(gt, primary),
    }
    os.makedirs(f"{OUT}/eval", exist_ok=True)
    atomic_json(report, f"{OUT}/eval/report_{stage}.json")
    print(json.dumps({"stage": stage, "q4_mean": report["q4_mean"], "delta_direct": cmp_["delta_direct"],
                      "G_official": cmp_["G_official"]}, default=str))


def _fixed_pattern_baseline(gt, patients):
    from collections import Counter
    vecs = [tuple(gt[i][t] for t in R.TARGETS) for i in patients]
    cnt = Counter(vecs)
    most_common_vec, most_common_n = cnt.most_common(1)[0]
    always_yes_correct = sum(1 for v in vecs if v == ("yes",) * 4)
    always_no_correct = sum(1 for v in vecs if v == ("no",) * 4)
    majority_per_quadrant = {t: Counter(gt[i][t] for i in patients).most_common(1)[0] for t in R.TARGETS}
    maj_vec = tuple(majority_per_quadrant[t][0] for t in R.TARGETS)
    maj_correct = sum(1 for v in vecs if v == maj_vec)
    return {"n": len(patients), "most_common_vector": most_common_vec, "most_common_vector_n": most_common_n,
            "always_yes_q4_correct": always_yes_correct, "always_no_q4_correct": always_no_correct,
            "per_quadrant_majority_vector": maj_vec, "per_quadrant_majority_q4_correct": maj_correct}


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("manifests")
    r = sp.add_parser("requests")
    r.add_argument("--stage", required=True)
    r.add_argument("--cfg", required=True)
    d24r = sp.add_parser("d24-qa-requests")
    d24r.add_argument("--cfg", required=True)
    s = sp.add_parser("score")
    s.add_argument("--stage", required=True)
    a = ap.parse_args()
    if a.cmd == "manifests":
        build_manifests()
    elif a.cmd == "requests":
        cmd_requests(a.stage, a.cfg)
    elif a.cmd == "d24-qa-requests":
        cmd_qa_requests_d24(a.cfg)
    elif a.cmd == "score":
        cmd_score(a.stage)


if __name__ == "__main__":
    main()
