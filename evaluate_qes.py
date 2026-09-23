"""Evaluation after selections are frozen (reads annotations).

실행: python research/evaluate_qes.py --out research/results/iter_004
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qes.data import DATA_DIR, FINDINGS, SCORER_VERSION  # noqa: E402
from qes.evaluation import (build_geometry, classify_pairs, criteria, evaluate, load_annotations,  # noqa: E402
                            pair_scores, positive_combos)
from qes.preflight import PreflightError, check_manifest, check_selection, check_verification  # noqa: E402
from qes.selection import MAIN_METHODS  # noqa: E402
from qes.store import read_jsonl, validate_predictions, write_json_atomic  # noqa: E402


def scoring_checks(reqs, valid, ver):
    recs = list(valid.values())
    chk = {
        "n_image_tokens": sorted({r["n_image_tokens"] for r in recs}),
        "pixel_values_shapes": sorted({str(r["pixel_values_shape"]) for r in recs}),
        "prompt_intact_all": all(r["prompt_intact"] for r in recs),
        "p_yes_plus_no_min": min(r["p_yes_plus_no"] for r in recs),
        "top1_tokens": {},
        "fp32head_abs_diff_max": max(abs(r["m"] - r["m_fp32head"]) for r in recs),
        "seconds_per_request_median": float(np.median([r["seconds"] for r in recs])),
    }
    for r in recs:
        chk["top1_tokens"][r["top1_token"]] = chk["top1_tokens"].get(r["top1_token"], 0) + 1
    if ver:
        chk["verification"] = {
            "n": len(ver),
            "tf_abs_diff_max": max(x["tf_abs_diff"] for x in ver),
            "tf_pass_1e-3": all(x["tf_abs_diff"] <= 1e-3 for x in ver),
            "repeat_abs_diff_max": max(x["repeat_abs_diff"] for x in ver),
            "gen_parsed": sum(x["gen_parsed"] is not None for x in ver),
            "gen_agrees": sum(bool(x["gen_agrees"]) for x in ver),
            "gen_truncated": sum(bool(x["gen_truncated"]) for x in ver),
            "gen_forward_total": sum(x["gen_n_forward"] for x in ver),
            "sec_gen_total": sum(x["sec_gen"] for x in ver),
            "disagreements": [{"id": x["id"], "gen_text": x["gen_text"], "m_main": x["m_main"]}
                              for x in ver if not x["gen_agrees"]],
        }
    return chk


def overlays(sel, geo, ann, out_dir, data_dir=DATA_DIR):
    os.makedirs(out_dir, exist_ok=True)
    colors = {"C_blur": (255, 0, 0), "D_blur": (0, 128, 255), "crop_conf": (255, 200, 0)}
    for img, q in positive_combos(geo):
        with Image.open(os.path.join(data_dir, img)) as im:
            base = im.convert("RGB")
        s = 600 / base.size[0]
        base = base.resize((600, int(round(base.size[1] * s))))
        d = ImageDraw.Draw(base)
        for t in geo[img].tiles:
            d.rectangle([c * s for c in t], outline=(128, 128, 128), width=1)
        for b in ann[img]["boxes"][q]:
            d.rectangle([c * s for c in b], outline=(0, 255, 0), width=3)
        for k, (meth, col) in enumerate(colors.items()):
            t = geo[img].tiles[sel[img][q][meth]]
            inset = 4 + 5 * k
            d.rectangle([t[0] * s + inset, t[1] * s + inset, t[2] * s - inset, t[3] * s - inset],
                        outline=col, width=3)
        d.text((5, 5), f"{img} {q}  GT=green C_blur=red D_blur=blue crop=yellow", fill=(255, 255, 255))
        base.save(os.path.join(out_dir, f"{img[:-4]}_{q.replace(' ', '_')}.png"))


def gate(out, data_dir=DATA_DIR):
    """평가 전 공통 검사. 모든 검사를 수행하고 (ok, report, 필요 객체)를 돌려준다.

    manifest 재해시 → prediction 완결성 → verification(지정 ID·중복·충돌·hash·수치 기준) →
    selection–prediction digest 연결. 하나라도 실패하면 ok=False이며 complete·투자 판정을 만들지 않는다.
    """
    report = {"completion": "incomplete", "stages": {}}
    try:
        cfg, chash, reqs, info, subsets = check_manifest(out, data_dir=data_dir)
        report["stages"]["manifest"] = {"pass": True}
    except PreflightError as e:
        report["stages"]["manifest"] = {"pass": False, "problems": e.problems[:50], "n_problems": len(e.problems)}
        return False, report, None
    v = validate_predictions(reqs, read_jsonl(os.path.join(out, "predictions.jsonl")), chash, SCORER_VERSION)
    rej = {}
    for x in v["rejected"]:
        rej[x["reason"]] = rej.get(x["reason"], 0) + 1
    report["stages"]["predictions"] = {"pass": v["status"] == "complete", "n_valid": len(v["valid"]),
                                       "n_missing": len(v["missing"]), "n_conflicts": len(v["conflicts"]),
                                       "rejected_reasons": rej, "conflicts": v["conflicts"][:10]}
    ver = read_jsonl(os.path.join(out, "verification.jsonl"))
    vp = check_verification(ver, subsets["verification"], reqs, v["valid"], chash)
    report["stages"]["verification"] = {"pass": not vp, "n_records": len(ver),
                                        "n_expected": len(subsets["verification"]), "problems": vp[:50]}
    sel_path = os.path.join(out, "selections.json")
    sel_all = json.load(open(sel_path)) if os.path.exists(sel_path) else None
    sp = check_selection(sel_all, v["valid"], chash, reqs) if sel_all is not None else [{"what": "selection_missing"}]
    report["stages"]["selection"] = {"pass": not sp, "problems": sp}
    ok = all(s["pass"] for s in report["stages"].values())
    report["completion"] = "gate_passed" if ok else "incomplete"
    return ok, report, (reqs, v, ver, sel_all)


# ---------------------------------------------------------------- 평가 상태 (iter_006)
# `evaluation_status.json`이 평가 완료의 유일한 근거다. 상태 전이:
#   시작 → running(incomplete, 이전 평가 산출물 무효화) → [gate 실패·예외] incomplete
#                                                   → [모든 산출물 staging 기록 → 게시] complete
# prediction 수집 완료(`prediction_collection`)와 평가 완료(`evaluation`)는 별도 필드다.
# 무효화는 현재 평가 산출물만 `invalidated/<run_id>/`로 옮긴다. 원시 prediction·과거 반복 결과는 건드리지 않는다.
STATUS_FILE = "evaluation_status.json"
GATE_FILE = "evaluation_gate.json"
EVAL_ARTIFACTS = ["metrics.json", "eval_table.md", "overlays"]


def write_status(out, status):
    write_json_atomic(os.path.join(out, STATUS_FILE), status)


def invalidate_eval_outputs(out, run_id, tag):
    """현재 평가 산출물(metrics·표·overlay·gate 기록)을 삭제하지 않고 무효화 디렉터리로 옮긴다."""
    moved = []
    dst = os.path.join(out, "invalidated", f"{run_id}_{tag}")
    for name in EVAL_ARTIFACTS + [GATE_FILE]:
        p = os.path.join(out, name)
        if os.path.lexists(p):
            os.makedirs(dst, exist_ok=True)
            os.replace(p, os.path.join(dst, name))
            moved.append(name)
    return moved


def _sha256_path(p):
    import hashlib
    h = hashlib.sha256()
    if os.path.isdir(p):
        for root, _, files in sorted(os.walk(p)):
            for f in sorted(files):
                h.update(os.path.relpath(os.path.join(root, f), p).encode())
                with open(os.path.join(root, f), "rb") as fh:
                    h.update(fh.read())
    else:
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def load_complete_metrics(out):
    """상태가 complete이고 게시된 산출물 hash가 기록과 일치할 때만 metrics를 돌려준다 (아니면 None)."""
    sp = os.path.join(out, STATUS_FILE)
    if not os.path.exists(sp):
        return None
    st = json.load(open(sp))
    if st.get("evaluation") != "complete":
        return None
    for name, h in st.get("artifacts_sha256", {}).items():
        p = os.path.join(out, name)
        if not os.path.lexists(p) or _sha256_path(p) != h:
            return None
    if set(st.get("artifacts_sha256", {})) != set(EVAL_ARTIFACTS):
        return None
    return json.load(open(os.path.join(out, "metrics.json")))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default=DATA_DIR)
    args = ap.parse_args(argv)
    import time
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}-{time.time_ns() % 10 ** 9:09d}"
    status = {"evaluation": "running", "complete": False, "run_id": run_id, "investment_decision": None,
              "prediction_collection": None, "reason": "evaluation started; previous outputs invalidated"}
    write_status(args.out, status)
    status["invalidated_previous"] = invalidate_eval_outputs(args.out, run_id, "start")
    write_status(args.out, status)
    try:
        _evaluate(args, run_id, status)
    except SystemExit as e:
        _fail(args.out, run_id, status, f"exit: {e}")
        raise
    except BaseException as e:
        _fail(args.out, run_id, status, f"exception: {e!r}"[:500])
        raise


def _fail(out, run_id, status, reason):
    """실패 시 게시 도중 남은 산출물도 무효화하고 incomplete를 기록한다 (gate 기록은 보존)."""
    moved = []
    dst = os.path.join(out, "invalidated", f"{run_id}_failed")
    for name in EVAL_ARTIFACTS:
        p = os.path.join(out, name)
        if os.path.lexists(p):
            os.makedirs(dst, exist_ok=True)
            os.replace(p, os.path.join(dst, name))
            moved.append(name)
    status.update({"evaluation": "incomplete", "complete": False, "investment_decision": None,
                   "reason": reason, "invalidated_on_failure": moved})
    status.pop("artifacts_sha256", None)
    write_status(out, status)


def _evaluate(args, run_id, status):
    import shutil
    ok, report, objs = gate(args.out, data_dir=args.data_dir)
    write_json_atomic(os.path.join(args.out, GATE_FILE), report)
    if objs is not None:
        status["prediction_collection"] = {"status": objs[1]["status"], "n_valid": len(objs[1]["valid"]),
                                           "n_missing": len(objs[1]["missing"])}
    if not ok:
        print(json.dumps(report, indent=1, default=str)[:4000])
        raise SystemExit("evaluation gate failed: metrics/criteria not computed (incomplete)")
    stage = os.path.join(args.out, f".eval_staging_{run_id}")
    os.makedirs(stage)
    crit = _compute(args, objs, report, stage)
    # 모든 산출물이 staging에 기록된 뒤에만 게시한다. 게시 도중 예외는 main()이 _fail로 되돌린다.
    status["evaluation"] = "publishing"
    write_status(args.out, status)
    hashes = {}
    for name in EVAL_ARTIFACTS:
        os.replace(os.path.join(stage, name), os.path.join(args.out, name))
        hashes[name] = _sha256_path(os.path.join(args.out, name))
    shutil.rmtree(stage)
    status.update({"evaluation": "complete", "complete": True, "investment_decision": crit,
                   "artifacts_sha256": hashes, "reason": "all artifacts published"})
    write_status(args.out, status)


def _compute(args, objs, report, stage):
    """metrics·표·overlay를 staging 디렉터리에 기록하고 사전 고정 기준(crit)을 돌려준다."""
    reqs, v, ver, sel_all = objs
    ann = load_annotations(data_dir=args.data_dir)
    geo = build_geometry(ann)
    sel = sel_all["main"]["selection"]
    scores = sel_all["main"]["scores"]
    pairs = classify_pairs(geo)

    ev = evaluate(sel, geo, MAIN_METHODS)
    ps = pair_scores(sel, geo, pairs, MAIN_METHODS)
    crit = criteria(ev, ps)

    # 민감도 (주결과 대체 금지)
    sel32 = sel_all["sensitivity_fp32head"]["selection"]
    ev32 = evaluate(sel32, geo, MAIN_METHODS)
    ps32 = pair_scores(sel32, geo, pairs, MAIN_METHODS)
    loqo = {}
    for drop in FINDINGS:
        s2 = {img: {q: {"C_blur": sel[img][q]["C_blur_loqo"].get(drop, sel[img][q]["C_blur"])}
                    for q in FINDINGS} for img in sel}
        e2 = evaluate(s2, geo, ["C_blur"])
        loqo[drop] = {"U_macro": e2["methods"]["C_blur"]["U"]["macro"],
                      "S_distinct": pair_scores(s2, geo, pairs, ["C_blur"])["C_blur"]["distinct"]["macro_S"]}

    # 선택 영역의 D·C 부호, 질문별 D 분포, 실패 사례
    combos = positive_combos(geo)
    sign_rows, fails = [], []
    for row in ev["per_combo"]:
        img, q = row["image"], row["finding"]
        sc = scores[img][q]
        tc, td = sel[img][q]["C_blur"], sel[img][q]["D_blur"]
        sign_rows.append({"image": img, "finding": q, "m_orig": sc["m_orig"],
                          "C_blur_tile": tc, "C_at_sel": sc["C_blur"][tc], "D_at_Csel": sc["D_blur"][tc],
                          "D_blur_tile": td, "D_at_Dsel": sc["D_blur"][td],
                          "U_C": row["C_blur"]["U"], "U_D": row["D_blur"]["U"], "U_crop": row["crop_conf"]["U"],
                          "best_tile": row["best_tile"]})
        if row["C_blur"]["U"] < row["D_blur"]["U"]:
            fails.append(sign_rows[-1])
    d_dist = {}
    for q in FINDINGS:
        allD = np.array([scores[img][q]["D_blur"] for img in scores]).ravel()
        allDm = np.array([scores[img][q]["D_mean"] for img in scores]).ravel()
        d_dist[q] = {"D_blur_mean": float(allD.mean()), "D_blur_std": float(allD.std()),
                     "D_blur_min": float(allD.min()), "D_blur_max": float(allD.max()),
                     "D_mean_mean": float(allDm.mean()), "D_mean_std": float(allDm.std())}
    orig_m = {img: {q: scores[img][q]["m_orig"] for q in FINDINGS} for img in scores}
    aux = {img: {q: {"m_orig": scores[img][q]["m_orig"], "crop_mean": scores[img][q]["crop_mean"],
                     "crop_max": scores[img][q]["crop_max"]} for q in FINDINGS} for img in scores}
    # 공유 bbox 쌍 (distinct가 아닌 쌍) 사례
    shared = [p for p in ps["C_blur"]["pairs"] if not p["distinct"]]

    metrics = {
        "completion": "complete",
        "authoritative_status_file": STATUS_FILE,
        "gate": report,
        "scoring_checks": scoring_checks(reqs, v["valid"], ver),
        "n_combos": ev["n_combos"], "n_images": ev["n_images"],
        "methods_macro": {m: {k: ev["methods"][m][k]["macro"] for k in ("U", "iou", "cov")}
                          for m in MAIN_METHODS + ["uniform", "location_prior"]},
        "oracle_iou_macro": ev["methods"]["oracle_iou"]["macro"],
        "image_swap_macro": {m: {k: ev["methods"][m]["image_swap"][k]["macro"] for k in ("U", "iou")}
                             for m in MAIN_METHODS},
        "question_swap_macro": {m: {k: ev["methods"][m]["question_swap"][k]["macro"] for k in ("U", "iou")}
                                for m in MAIN_METHODS},
        "question_swap_n": ev["methods"]["C_blur"]["question_swap"]["U"]["n_combos"],
        "per_image_U": {m: ev["methods"][m]["U"]["per_image"] for m in MAIN_METHODS + ["uniform", "location_prior"]},
        "pair_S": {m: {s: {k: ps[m][s][k] for k in ("n_pairs", "n_images", "macro_S", "frac_same_tile")}
                       for s in ("distinct", "other")} for m in MAIN_METHODS},
        "criteria": crit,
        "sensitivity_fp32head": {"methods_macro_U": {m: ev32["methods"][m]["U"]["macro"] for m in MAIN_METHODS},
                                 "S_distinct": {m: ps32[m]["distinct"]["macro_S"] for m in MAIN_METHODS},
                                 "criteria": criteria(ev32, ps32)},
        "sensitivity_leave_one_question_out_C_blur": loqo,
        "ties_main": sel_all["main"]["ties"],
        "selected_sign": sign_rows,
        "failure_cases_C_lt_D": fails,
        "D_distribution_by_question": d_dist,
        "orig_margin": orig_m,
        "aux_orig_crop_mean_max": aux,
        "shared_pairs_C_blur": shared,
        "pair_details": {m: ps[m]["pairs"] for m in MAIN_METHODS},
        "per_combo": ev["per_combo"],
    }
    write_json_atomic(os.path.join(stage, "metrics.json"), metrics)
    overlays(sel, geo, ann, os.path.join(stage, "overlays"), data_dir=args.data_dir)

    M = metrics["methods_macro"]
    f3 = lambda x: "NA" if x is None else f"{x:.3f}"
    lines = ["| method | macro U | macro IoU | macro coverage | image-swap U | question-swap U | S distinct | S other |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for m in MAIN_METHODS:
        lines.append(f"| {m} | {M[m]['U']:.3f} | {M[m]['iou']:.3f} | {M[m]['cov']:.3f} | "
                     f"{metrics['image_swap_macro'][m]['U']:.3f} | {metrics['question_swap_macro'][m]['U']:.3f} | "
                     f"{f3(ps[m]['distinct']['macro_S'])} | {f3(ps[m]['other']['macro_S'])} |")
    for m in ("uniform", "location_prior"):
        lines.append(f"| {m} | {M[m]['U']:.3f} | {M[m]['iou']:.3f} | {M[m]['cov']:.3f} | | | | |")
    lines.append(f"\noracle IoU macro = {metrics['oracle_iou_macro']:.3f}")
    with open(os.path.join(stage, "eval_table.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps(crit, indent=1))
    print(json.dumps(metrics["scoring_checks"], indent=1, default=str))
    return crit


if __name__ == "__main__":
    main()
