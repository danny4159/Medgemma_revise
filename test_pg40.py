"""iter_040 CPU 검사: 분할 무결성, 요청 재구성, 단계 gate, 부분 행 복구, 변조 거부, 대조 적격성, target/ID 규칙.
python test_pg40.py --out results/iter_040/tests/fixtures_pg40.json
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

import pg39_spec as S
import pg40_requests as RQ
import pg40_run as R
import pg40_train as T
from rsna_diag import sft_data

RES = []


def check(name, ok, detail=None):
    RES.append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:300], flush=True)


def raises(fn, exc=Exception, match=None):
    try:
        fn()
    except exc as e:
        return match is None or match in str(e)
    return False


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", required=True)
    a = a.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    tr = [json.loads(l) for l in open(T.TRAIN_MANIFEST)]
    ev = [json.loads(l) for l in open(T.EVAL_MANIFEST)]
    summ = json.load(open("results/iter_040/data/selection_summary.json"))
    lock = json.load(open("results/iter_040/data/selection_lock.json"))
    check("manifest_hashes_match_lock", T.sha_file(T.TRAIN_MANIFEST) == lock["manifest_train_sha256"] and T.sha_file(T.EVAL_MANIFEST) == lock["manifest_eval_sha256"])
    sets = {"T305": tr, "V96": [r for r in ev if r["eval_set"] == "V96"], "H192": [r for r in ev if r["eval_set"] == "H192"]}
    m39 = [json.loads(l) for l in open("results/iter_039/data/manifest_private.jsonl")]
    sets["D24"] = [r for r in m39 if r["subset"] == "D"]
    sets["F120"] = [r for r in m39 if r["subset"] == "F"]
    names = list(sets)
    inter = {}
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            for key, fn in (("patient", lambda r: r["PatientID"]), ("image", lambda r: r["ImageID"]), ("study", lambda r: r["StudyID"]),
                            ("pixel", lambda r: r["image_meta"]["u16_pixel_sha256"])):
                inter[f"{x}&{y}:{key}"] = len({fn(r) for r in sets[x]} & {fn(r) for r in sets[y]})
    check("no_patient_image_study_pixel_overlap_between_all_sets", all(v == 0 for v in inter.values()), {"n_pairs_checked": len(inter)})
    check("set_sizes", [len(sets[k]) for k in ("T305", "V96", "H192")] == [305, 96, 192] and sum(r["is_V48"] for r in sets["V96"]) == 48)
    ok_img = True
    for r in tr:
        h_ = hashlib.sha256(open(r["image_meta"]["path"], "rb").read()).hexdigest()
        ok_img &= os.path.exists(r["image_meta"]["path"])
    check("train_images_exist", ok_img)
    # 학습 target: GT 좌표에서 결정적 재구성, 라벨=ID
    bad = 0
    for r in tr:
        for p in ("qA", "qB"):
            t = json.loads(T.target_text(r["gt_canvas_yxyx"][p], p))
            if not t or any(e["label"] != p or not (0 <= e["box_2d"][0] < e["box_2d"][2] <= 1000 and 0 <= e["box_2d"][1] < e["box_2d"][3] <= 1000) for e in t):
                bad += 1
            if len(t) != len(r["gt_boxes_xyxy_norm"][p]):
                bad += 1
    check("train_targets_reconstruct_from_gt_all_positive_boxes", bad == 0)
    # canvas 좌표 재계산 일치
    from rsna_diag import geometry
    mism = 0
    for r in tr:
        m = r["image_meta"]
        for p in ("qA", "qB"):
            ref = S.gt_to_canvas(r["gt_boxes_xyxy_norm"][p], m["h"], m["w"])
            mism += ref != r["gt_canvas_yxyx"][p]
    check("stored_canvas_gt_equals_recomputation", mism == 0)
    # 대조 적격성 재계산
    el = sum(S.cross_iou_max(r["gt_canvas_yxyx"]["qA"], r["gt_canvas_yxyx"]["qB"]) < 0.1 for r in tr)
    check("contrast_eligibility_recomputed", el == sum(r["contrast_eligible"] for r in tr) == summ["contrast_eligibility"]["n_eligible"], {"eligible": el})
    # 요청 재구성 (V96/V48)
    rows96 = [json.loads(l) for l in open("results/iter_040/requests/requests_V96.jsonl")]
    rec_ok = True
    by = {r["PatientID"]: r for r in sets["V96"]}
    for q in rows96:
        m = by[q["patient"]]
        pid = q["targets"][0]
        prompt = S.prompt_I_short(m["sentences"][pid], pid)
        rec_ok &= prompt == q["prompt"] and S.sha(prompt) == q["prompt_sha256"] and q["cond"] == "I-short"
        rec_ok &= S.request_id(q["kind"], q["patient"], q["cond"], q["targets"], q["prompt_sha256"], m["image_meta"]["u8_pixel_sha256"]) == q["request_id"]
    check("V96_requests_reconstruct_from_manifest", rec_ok and len(rows96) == 192)
    check("V48_is_subset_of_V96", {json.loads(l)["request_id"] for l in open("results/iter_040/requests/requests_V48.jsonl")} <=
          {q["request_id"] for q in rows96})
    # gate: decision 없이는 protocol/요청 생성 거부
    td = tempfile.mkdtemp()
    g_no = os.path.join(td, "d_no.json")
    g_yes = os.path.join(td, "d_yes.json")
    json.dump({"run": False}, open(g_no, "w"))
    json.dump({"run": True}, open(g_yes, "w"))
    check("protocol_creation_rejected_when_gate_false", raises(lambda: R.make_protocol("results/iter_040/requests/requests_V48.jsonl", os.path.join(td, "p1.json"), gate=g_no), R.RunError, "gate"))
    p_ok = os.path.join(td, "p2.json")
    R.make_protocol("results/iter_040/requests/requests_V48.jsonl", p_ok, gate=g_yes)
    check("protocol_ok_with_gate_true", R.verify_protocol(p_ok, "results/iter_040/requests/requests_V48.jsonl")[1]["gate"]["decision_sha256"] == R.file_sha(g_yes))
    json.dump({"run": False}, open(g_yes, "w"))
    check("protocol_verify_rejects_changed_gate_decision", raises(lambda: R.verify_protocol(p_ok, "results/iter_040/requests/requests_V48.jsonl"), R.RunError, "gate"))
    check("h192_request_generation_rejected_without_run_true", os.system("python pg40_requests.py h192 --decision " + g_no + " > /dev/null 2>&1") != 0)
    check("h192_request_generation_rejected_without_decision_arg", os.system("python pg40_requests.py h192 > /dev/null 2>&1") != 0)
    check("no_H192_request_file_created_by_rejected_call", not os.path.exists("results/iter_040/requests/requests_H192.jsonl"))
    # 요청 파일 변조 거부
    p3 = os.path.join(td, "p3.json")
    R.make_protocol("results/iter_040/requests/requests_V48.jsonl", p3)
    rq2 = os.path.join(td, "req_mod.jsonl")
    shutil.copy("results/iter_040/requests/requests_V48.jsonl", rq2)
    with open(rq2, "a") as f:
        f.write("\n")
    check("protocol_verify_rejects_modified_requests", raises(lambda: R.verify_protocol(p3, rq2), R.RunError, "requests file changed"))
    # 부분 행: 읽기는 무시, 복구는 절단
    fp = os.path.join(td, "gen_worker0.jsonl")
    with open(fp, "w") as f:
        f.write(json.dumps({"request_id": "a"}) + "\n" + json.dumps({"request_id": "b"}) + "\n" + '{"request_id": "c", "x": ')
    check("read_records_ignores_partial_trailing_line", [r["request_id"] for r in R.read_records(fp)] == ["a", "b"])
    n = R.repair_tail(fp)
    check("repair_tail_truncates_partial_line_and_logs", n > 0 and open(fp).read().endswith("\n") and os.path.exists(fp + ".repair.log") and R.repair_tail(fp) == 0)
    with open(fp, "w") as f:
        f.write("{bad json}\n" + json.dumps({"request_id": "z"}) + "\n")
    check("corrupted_middle_line_raises", raises(lambda: R.read_records(fp), Exception))
    # validate_records: 잉여/중복/adapter 불일치 거부
    rows = [json.loads(l) for l in open("results/iter_040/requests/requests_V48.jsonl")]
    rb = {r["request_id"]: r for r in rows}
    row0 = rows[0]
    rec = {"request_id": row0["request_id"], "row_digest": R.row_digest(row0), "prompt_sha256": row0["prompt_sha256"], "protocol_digest": "P",
           "config_digest": "C", "input_pixel_sha256": row0["input_pixel_sha256"], "adapter_digest": None}
    rec["record_digest"] = R.record_digest(rec)
    px = lambda p: row0["input_pixel_sha256"]
    check("validate_records_accepts_good_record", len(R.validate_records({"f": [rec]}, rb, "P", "C", px, None)) == 1)
    check("validate_records_rejects_duplicate", raises(lambda: R.validate_records({"f": [rec, rec]}, rb, "P", "C", px, None), R.RunError, "duplicate"))
    check("validate_records_rejects_adapter_mismatch", raises(lambda: R.validate_records({"f": [rec]}, rb, "P", "C", px, "adapterdigest"), R.RunError, "adapter"))
    bad = dict(rec, request_id="nope")
    bad["record_digest"] = R.record_digest(bad)
    check("validate_records_rejects_unexpected_request", raises(lambda: R.validate_records({"f": [bad]}, rb, "P", "C", px, None), R.RunError, "unexpected"))
    tam = dict(rec, extra=1)
    check("validate_records_rejects_tampered_digest", raises(lambda: R.validate_records({"f": [tam]}, rb, "P", "C", px, None), R.RunError, "digest"))
    # 학습 데이터 규칙: 교차 target의 ID/길이
    r0 = [r for r in tr if r["contrast_eligible"]][0]
    tx = T.patient_texts(r0, True)
    same = tx["cross"]["qA"][1] == tx["pos"]["qA"][1] and tx["cross"]["qB"][1] == tx["pos"]["qB"][1]
    diff_prompt = tx["cross"]["qA"][0] != tx["pos"]["qA"][0] and r0["sentences"]["qB"] in tx["cross"]["qA"][0] and '"qA"' in tx["cross"]["qA"][0]
    check("cross_prompt_uses_other_sentence_and_same_id_target", same and diff_prompt)
    nonel = [r for r in tr if not r["contrast_eligible"]][0]
    check("non_eligible_patient_has_no_cross_texts", T.patient_texts(nonel, nonel["contrast_eligible"])["cross"] is None)
    # eval manifest 행(canvas GT 미저장)에서도 canvas GT를 원본에서 같은 함수로 재구성해 같은 target을 만든다 (valce 경로 회귀)
    v0 = sets["V96"][0]
    txv = T.patient_texts(v0, False)
    ref = S.gt_to_canvas(v0["gt_boxes_xyxy_norm"]["qA"], v0["image_meta"]["h"], v0["image_meta"]["w"])
    check("eval_row_target_from_original_gt_matches_recomputation", txv["targets"]["qA"] == T.target_text(ref, "qA") and "qA" in txv["pos"]["qA"][0])
    # protocol 변조 거부 (학습)
    tp = os.path.join(td, "tp.json")
    T.make_protocol(tp)
    p = json.load(open(tp))
    p["manifest_train_sha256"] = "0" * 64
    json.dump(p, open(tp + ".bad", "w"))
    check("train_protocol_rejects_manifest_change", raises(lambda: T.verify_protocol(tp + ".bad"), T.TrainError, "manifest changed"))
    A = type("A", (), {"schedule": "cosine8", "lr": 2e-4})
    lrs = [T.lr_for(A, s_, 39) for s_ in range(195 + 117)]
    warm = 10
    check("lr_schedule_warmup10_peak_then_cosine_to_zero_then_ext_floor0.1",
          abs(lrs[0] - 2e-4 / 10) < 1e-12 and abs(lrs[warm] - 2e-4) < 1e-9 and lrs[194] < 1e-7 and abs(lrs[195] - 2e-5) < 1e-9 and lrs[311] < 1e-6,
          {"lr0": lrs[0], "lr10": lrs[10], "lr194": lrs[194], "lr195": lrs[195]})
    Ac = type("A", (), {"schedule": "const", "lr": 2e-5})
    check("const_schedule_constant", len({T.lr_for(Ac, s_, 39) for s_ in range(200)}) == 1)
    n_pass = sum(r["pass"] for r in RES)
    json.dump({"results": RES, "n_pass": n_pass, "n": len(RES), "intersections": inter}, open(a.out, "w"), indent=1)
    print(f"{n_pass}/{len(RES)} PASS")


if __name__ == "__main__":
    main()
