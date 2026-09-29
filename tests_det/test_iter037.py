"""iter_037 fixture: det37의 fail-closed loader, 출력 소유권·재개, criterion_a/b, 감사 행 규약 검사 (medgemma env, CPU).
원본 자료는 변조하지 않고 메모리/임시 복사본에서만 변조한다. 결과: 환경변수 DET37_FIXTURES_OUT (새 경로, 덮어쓰기 거부)."""
import copy
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det37 as T  # noqa: E402
from rsna_diag import det_error_audit as DA  # noqa: E402
from rsna_diag import metrics as M  # noqa: E402

res = {"pass": 0, "fail": 0, "details": []}


def check(name, cond, extra=None):
    ok = bool(cond)
    res["pass" if ok else "fail"] += 1
    res["details"].append({"name": name, "ok": ok, "extra": extra})
    if not ok:
        print("FAIL", name, extra)


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return True, str(e)[:120]
    return False, None


GOOD = {"boxes_xyxy_px": [[10.0, 20.0, 60.0, 80.0], [100.0, 100.0, 150.0, 160.0]], "scores": [0.9, 0.2], "labels": [1, 1], "img_hw": [256, 256]}


def test_validate_raw():
    T.validate_raw_record("ok", GOOD)
    check("raw_valid_passes", True)
    variants = {
        "scores_shorter": {**GOOD, "scores": [0.9]},
        "labels_longer": {**GOOD, "labels": [1, 1, 1]},
        "nan_box": {**GOOD, "boxes_xyxy_px": [[float("nan"), 20, 60, 80], GOOD["boxes_xyxy_px"][1]]},
        "inf_box": {**GOOD, "boxes_xyxy_px": [[10, 20, float("inf"), 80], GOOD["boxes_xyxy_px"][1]]},
        "nan_score": {**GOOD, "scores": [float("nan"), 0.2]},
        "score_gt1": {**GOOD, "scores": [1.5, 0.2]},
        "label0": {**GOOD, "labels": [1, 0]},
        "zero_size": {**GOOD, "boxes_xyxy_px": [[10, 20, 10, 80], GOOD["boxes_xyxy_px"][1]]},
        "outside_image": {**GOOD, "boxes_xyxy_px": [[10, 20, 400, 80], GOOD["boxes_xyxy_px"][1]]},
        "over_cap": {**GOOD, "boxes_xyxy_px": [[1.0, 1.0, 5.0, 5.0]] * 101, "scores": [0.5] * 101, "labels": [1] * 101},
    }
    for n, rec in variants.items():
        ok, msg = raises(lambda rec=rec: T.validate_raw_record("v", rec), ValueError)
        check(f"raw_reject_{n}", ok, msg)
    ok, msg = raises(lambda: T.validate_raw_record("hw", GOOD, img_hw=(300, 300)), ValueError)
    check("raw_reject_img_hw_mismatch", ok, msg)
    ok, msg = raises(lambda: T.candidates({**GOOD, "scores": [0.9]}, (256, 256)), ValueError)
    check("candidates_reject_length_mismatch", ok, msg)


def test_lock_tamper():
    lock = json.load(open(T.LOCK_PATH))
    T.verify_lock()
    check("lock_valid_passes", True)
    with tempfile.TemporaryDirectory() as td:
        bad = copy.deepcopy(lock)
        bad["files"]["seed17"]["sha256"] = "0" * 64
        p = os.path.join(td, "LOCK_bad.json")
        json.dump(bad, open(p, "w"))
        ok, msg = raises(lambda: T.verify_lock(p), ValueError)
        check("lock_reject_changed_hash", ok, msg)
        bad2 = copy.deepcopy(lock)
        bad2["seed_set"] = [17, 29, 43]
        p2 = os.path.join(td, "LOCK_bad2.json")
        json.dump(bad2, open(p2, "w"))
        ok, msg = raises(lambda: T.verify_lock(p2), ValueError)
        check("lock_reject_seed_set", ok, msg)
        bad3 = copy.deepcopy(lock)
        del bad3["files"]["extend29"]
        p3 = os.path.join(td, "LOCK_bad3.json")
        json.dump(bad3, open(p3, "w"))
        ok, msg = raises(lambda: T.verify_lock(p3), ValueError)
        check("lock_reject_missing_file_entry", ok, msg)
        # 잠기지 않은 선택 파일 (내용 복사본)
        sel_copy = os.path.join(td, "v400_selection.json")
        open(sel_copy, "w").write(open(T.SEL[17]).read())
        ok, msg = raises(lambda: T.verify_selection(sel_copy, lock), ValueError)
        check("selection_reject_unlocked_copy", ok, msg)
    T.verify_selection(T.SEL[17], lock)
    check("selection_locked_passes", True)


def test_shards_and_images():
    gt, infer = T.D.load_gt_infer()
    ids = ["a", "b"]
    inf = {"a": {"file_sha256": "fa", "image": "x"}, "b": {"file_sha256": "fb", "image": "x"}}
    comp = {"checkpoint_sha256": "c", "source_digest": "s", "manifest_digest": "m", "batch_size": 1}
    raw = {"a": GOOD, "b": GOOD}

    def mk(td, recs, fn="preds_w00.jsonl"):
        with open(os.path.join(td, fn), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        return {**comp, "shard_sha256": {fn: "x"}}

    def rec(i, **kw):
        return {"id": i, **GOOD, **{k: comp[k] for k in comp}, "file_sha256": inf[i]["file_sha256"], **kw}
    with tempfile.TemporaryDirectory() as td:
        c = mk(td, [rec("a"), rec("b")])
        T.check_shards(td, c, ids, raw, inf)
        check("shards_valid_passes", True)
    with tempfile.TemporaryDirectory() as td:
        c = mk(td, [rec("a"), rec("a"), rec("b")])
        ok, msg = raises(lambda: T.check_shards(td, c, ids, raw, inf), ValueError)
        check("shards_reject_duplicate_id", ok, msg)
    with tempfile.TemporaryDirectory() as td:
        c = mk(td, [rec("a")])
        ok, msg = raises(lambda: T.check_shards(td, c, ids, raw, inf), ValueError)
        check("shards_reject_missing_request", ok, msg)
    with tempfile.TemporaryDirectory() as td:
        c = mk(td, [rec("a"), rec("b", source_digest="other")])
        ok, msg = raises(lambda: T.check_shards(td, c, ids, raw, inf), ValueError)
        check("shards_reject_source_digest", ok, msg)
    with tempfile.TemporaryDirectory() as td:
        c = mk(td, [rec("a"), rec("b", file_sha256="zz")])
        ok, msg = raises(lambda: T.check_shards(td, c, ids, raw, inf), ValueError)
        check("shards_reject_file_hash_vs_infer", ok, msg)
    with tempfile.TemporaryDirectory() as td:
        c = mk(td, [rec("a"), rec("b", scores=[0.9, 0.3])])
        ok, msg = raises(lambda: T.check_shards(td, c, ids, raw, inf), ValueError)
        check("shards_reject_differs_from_raw_preds", ok, msg)
    # 영상 hash 연결: 실제 한 영상의 infer hash를 변조
    v = json.load(open(T.IDS_PATH["V400"]))[:2]
    bad = {i: dict(infer[i]) for i in v}
    bad[v[0]]["file_sha256"] = "0" * 64
    ok, msg = raises(lambda: T.verify_images(v, bad), ValueError)
    check("images_reject_hash_mismatch", ok, msg)
    hw = T.verify_images(v, infer)
    check("images_valid_returns_hw", len(hw) == 2 and all(len(x) == 2 for x in hw.values()))
    # source digest 변조는 실제 detector loader가 거부
    ids400 = json.load(open(T.IDS_PATH["V400"]))
    hw400 = {i: (1, 1) for i in ids400}  # 도달 전에 거부되므로 사용되지 않음
    os.environ["DET_TEST_SOURCE_SALT"] = "tamper"
    try:
        ok, msg = raises(lambda: T.load_detector("V400", 17, ids400, infer, hw400, T.verify_lock()), ValueError)
    finally:
        del os.environ["DET_TEST_SOURCE_SALT"]
    check("detector_loader_rejects_source_digest_mismatch", ok, msg)


def test_output_protection():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "x.json")
        T.write_json_new(p, {"a": 1})
        ok, msg = raises(lambda: T.write_json_new(p, {"a": 2}), FileExistsError)
        check("write_json_new_refuses_overwrite", ok and json.load(open(p)) == {"a": 1}, msg)
        check("write_json_new_no_tmp_left", [f for f in os.listdir(td) if ".tmp" in f] == [])
        o = T.OutputOwner(td)
        code = ("import sys;sys.path.insert(0,'%s');from rsna_diag import det37 as T\n"
                "try:\n    T.OutputOwner(sys.argv[1]);print('acquired')\nexcept RuntimeError as e:\n    print('refused')\n" % BASE)
        r = subprocess.run([sys.executable, "-c", code, td], capture_output=True, text=True)
        check("owner_lock_second_process_refused", r.stdout.strip() == "refused", (r.stdout, r.stderr[-200:]))
        o.release()
        r = subprocess.run([sys.executable, "-c", code, td], capture_output=True, text=True)
        check("owner_lock_reacquired_after_release", r.stdout.strip() == "acquired", (r.stdout, r.stderr[-200:]))


def test_criterion():
    n_gt = np.ones(300)
    idx = M.bootstrap_indices(300, B=2000, seed=1)
    # cap 없음: 영향 환자 30명(10%) → a 참, b 비해당
    r = np.zeros(300); r[:30] = 1
    out = T.criterion_ab(r, n_gt, np.zeros(300, bool), idx)
    check("crit_no_cap_a_true_b_na", out["criterion_a_met"] and not out["criterion_b_applicable"] and not out["criterion_b_met"] and out["escalate_to_gpu_trace"], out)
    # 관측 R 낮음(1명): a 거짓, cap 있어도 b 거짓, 승격 없음
    r = np.zeros(300); r[0] = 1
    cap = np.zeros(300, bool); cap[:5] = True
    out = T.criterion_ab(r, n_gt, cap, idx)
    check("crit_low_r_no_escalation", (not out["criterion_a_met"]) and (not out["criterion_b_met"]) and not out["escalate_to_gpu_trace"], out)
    # cap 있고 판단 유지: 영향 30명 중 cap 환자 3명 → 양극단 모두 a 참
    r = np.zeros(300); r[:30] = 1
    cap = np.zeros(300, bool); cap[:3] = True
    out = T.criterion_ab(r, n_gt, cap, idx)
    check("crit_cap_decision_unchanged", out["criterion_b_applicable"] and out["criterion_a_met"] and not out["criterion_b_met"], out)
    # cap 있고 판단이 바뀜: 영향 21명 전부 cap 환자 → 회복 가능 극단에서 0 → a 거짓
    r = np.zeros(300); r[:21] = 1
    cap = np.zeros(300, bool); cap[:21] = True
    out = T.criterion_ab(r, n_gt, cap, idx)
    check("crit_cap_decision_changes", out["criterion_b_met"] and out["criterion_a_met"] and not out["extreme_all_recoverable"]["met"], out)


def test_audit_rows_and_categories():
    gt = {"p": {"boxes": [{"yxyx_norm": [400, 400, 500, 500]}, {"yxyx_norm": [100, 100, 200, 200]}], "category": "opacity"}}
    cands = [{"idx": 0, "box": [405, 405, 505, 505], "score": 0.9},          # GT0에 잘 맞음(선택)
             {"idx": 1, "box": [102, 102, 202, 202], "score": 0.2},          # GT1에 맞음, 낮은 score(threshold 아래)
             {"idx": 2, "box": [102, 102, 202, 202], "score": 0.4},          # 같은 위치, 더 높은 score(threshold 아래)
             {"idx": 3, "box": [700, 700, 800, 800], "score": 0.8}]          # 어느 GT와도 무관(FP)
    sft = {17: {"p": {"status": "valid_nonempty", "boxes": [[400, 400, 500, 500], [100, 100, 200, 200]]}}}
    rows = T.gt_audit_rows(["p"], gt, {"p": cands}, 0.5, sft)
    r0, r1 = rows
    check("audit_det_pair_idx_selected", r0["det_pair_idx@0.3"] == 0 and r1["det_pair_idx@0.3"] is None, (r0["det_pair_idx@0.3"], r1["det_pair_idx@0.3"]))
    check("audit_top_score_over_thr_picks_highest_score_not_first", r1["top_score_cand_iou_ge_0.3"][:2] == [0.4, 2], r1["top_score_cand_iou_ge_0.3"])
    check("audit_max_iou_all_tie_lowest_idx", r1["max_iou_all_idx"] == 1, r1["max_iou_all_idx"])
    check("audit_max_iou_selected_of_missing_gt_is_low", r1["max_iou_selected"] < 0.3 and r1["max_iou_selected_idx"] in (0, 3), (r1["max_iou_selected"], r1["max_iou_selected_idx"]))
    check("audit_category_threshold_excluded", r1["sft17_only_category@0.3"] == "threshold_excluded" and r0["sft17_only_category@0.3"] is None, (r1["sft17_only_category@0.3"], r0["sft17_only_category@0.3"]))
    cands_far = [{"idx": 0, "box": [700, 700, 800, 800], "score": 0.9}]
    rows2 = T.gt_audit_rows(["p"], gt, {"p": cands_far}, 0.5, sft)
    check("audit_missing_is_none_not_zero", rows2[0]["top_score_cand_iou_ge_0.3"] is None and rows2[0]["top_score_cand_iou_ge_0.5"] is None, rows2[0]["top_score_cand_iou_ge_0.3"])
    check("audit_category_no_coverage_for_far_candidates", rows2[0]["sft17_only_category@0.3"] == "no_stored_candidate_coverage", rows2[0]["sft17_only_category@0.3"])
    empty = T.gt_audit_rows(["p"], gt, {"p": []}, 0.5, sft)
    check("audit_empty_candidates_max_iou_none", empty[0]["max_iou_all"] is None and empty[0]["max_iou_all_idx"] is None, empty[0]["max_iou_all"])
    cs, rn, ng = T.category_stats(rows2, ["p"], 17, 0.3, M.bootstrap_indices(1, B=50, seed=3))
    check("category_stats_r_numerator", cs["r_numerator"] == 2 and cs["total_gt"] == 2 and cs["r_n_affected_patients"] == 1, cs["r_numerator"])
    # FP 범주 합 == 전체, 두 IoU
    preds = {"p": {"status": "valid_nonempty", "boxes": [c["box"] for c in cands]}}
    for t in (0.3, 0.5):
        d = DA.fp_decompose(["p"], {"p": {"boxes": gt["p"]["boxes"]}}, preds, thr=t)
        check(f"fp_category_sum_equals_total_iou{t}", sum(v for k, v in d.items() if k != "n_fp_total") == d["n_fp_total"], d)
    # pair: IoU0.3 쌍의 IoU가 0.5 미만이어도 독립 재매칭(0.5)으로는 다른 후보가 GT를 검출하는 사례
    g = [[0, 0, 100, 100]]
    p1 = [[0, 0, 100, 40]]   # IoU 0.4 (0.3 대응, 0.5 실패)
    check("pair_fixed_pair_fail_at_0.5", T.pairs_orig([{"idx": 7, "box": p1[0]}], g, 0.3)[0][0] == 7 and T.pairs_orig([{"idx": 7, "box": p1[0]}], g, 0.5) == {})


def test_resume_and_real_d24():
    """실제 V400 D24: 단위 3개 후 강제 종료 → 재개 → 무중단 실행 결과와 단위별 동일, 다른 split 재개 거부."""
    ref_dir = f"{BASE}/results/iter_037/a1/d24_V400"
    if not os.path.exists(f"{ref_dir}/report.json"):
        check("d24_reference_exists", False, ref_dir)
        return
    ref = json.load(open(f"{ref_dir}/report.json"))
    check("d24_reference_n_ids_24", ref["n_ids"] == 24 and ref["n_positive"] == 8, (ref["n_ids"], ref["n_positive"]))
    cats = {}
    gt = json.load(open(f"{BASE}/results/iter_010/manifests/gt_manifest.json"))
    d24 = DA.stratified_d24(json.load(open(T.IDS_PATH["V400"])), gt)
    for i in d24:
        cats[gt[i]["category"]] = cats.get(gt[i]["category"], 0) + 1
    check("d24_category_counts_8_each", cats == {"opacity": 8, "normal": 8, "not_normal_no_opacity": 8}, cats)
    check("d24_gt_count_strata_present", len({len(gt[i]["boxes"]) for i in d24 if gt[i]["category"] == "opacity"}) >= 3)
    with tempfile.TemporaryDirectory(dir=f"{BASE}/results/iter_037") as td:
        out = os.path.join(td, "resume")
        cmd = [sys.executable, f"{BASE}/rsna_diag/det37.py", "--split", "V400", "--d24", "--out", out, "--workers", "1"]
        r1 = subprocess.run(cmd + ["--stop_after", "3"], capture_output=True, text=True)
        n_partial = len(os.listdir(os.path.join(out, "units")))
        check("resume_forced_stop_after_3_units", r1.returncode == 7 and n_partial == 3, (r1.returncode, n_partial))
        r2 = subprocess.run(cmd, capture_output=True, text=True)
        check("resume_completes", r2.returncode == 0 and os.path.exists(os.path.join(out, "report.json")), r2.stderr[-300:])
        same = True
        for n in ref["tables"]:
            same &= ref["tables"][n] == json.load(open(os.path.join(out, "report.json")))["tables"][n]
        rep2 = json.load(open(os.path.join(out, "report.json")))
        for n in ref["detector"]:
            a, b = dict(ref["detector"][n]), dict(rep2["detector"][n])
            a.pop("elapsed_s"); b.pop("elapsed_s")
            same &= a == b
        check("resume_result_equals_uninterrupted_run", same)
        full = [sys.executable, f"{BASE}/rsna_diag/det37.py", "--split", "V400", "--out", out, "--workers", "1"]
        r3 = subprocess.run(full, capture_output=True, text=True)  # 전체 분할(d24 아님) → 다른 입력
        check("rerun_with_different_inputs_refused", r3.returncode != 0 and "differs" in r3.stderr, r3.stderr[-200:])
        r4 = subprocess.run(cmd, capture_output=True, text=True)
        check("rerun_after_complete_refuses_report_overwrite", r4.returncode != 0 and "FileExistsError" in r4.stderr, r4.stderr[-200:])
        # unit 변조(입력 digest)가 있으면 재사용 거부
        up = os.path.join(out, "units", "sft17.json")
        u = json.load(open(up)); u["header"]["inputs_digest"] = "bad"; json.dump(u, open(up, "w"))
        os.unlink(os.path.join(out, "report.json"))
        r5 = subprocess.run(cmd, capture_output=True, text=True)
        check("stale_unit_reuse_refused", r5.returncode != 0 and "different config/inputs" in r5.stderr, r5.stderr[-200:])


if __name__ == "__main__":
    test_validate_raw()
    test_lock_tamper()
    test_shards_and_images()
    test_output_protection()
    test_criterion()
    test_audit_rows_and_categories()
    test_resume_and_real_d24()
    print(json.dumps({"pass": res["pass"], "fail": res["fail"]}))
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DET37_FIXTURES_OUT")
    if out_path:
        T.write_json_new(out_path, res)
    sys.exit(1 if res["fail"] else 0)
