"""iter_005: QES 진입점(run_qes / select_qes / evaluate_qes) 수준의 preflight·gate 검증 (CPU, 모델 없음).

실행: python research/test_qes_preflight.py --out research/results/iter_005/qes_entry_tests

각 사례는 새 fixture 디렉터리에서 실제 진입점 main()을 호출한다. manifest는 다시 만들지 않는다
(iter_004 리뷰 결함 1: 오래된 manifest를 그대로 재사용하는 경로를 직접 검사).
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate_qes  # noqa: E402
import run_qes  # noqa: E402
import select_qes  # noqa: E402
from qes import data as D  # noqa: E402
from qes import store as ST  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": str(detail)[:500]})
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {str(detail)[:200]}", flush=True)


def write_jsonl(path, recs):
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def build_fixture(root, seed=0):
    if os.path.exists(root):
        shutil.rmtree(root)
    sdir, out = os.path.join(root, "data"), os.path.join(root, "out")
    os.makedirs(sdir)
    os.makedirs(out)
    rng = np.random.default_rng(seed)
    meta = []
    f1, f2 = D.FINDINGS[0], D.FINDINGS[1]
    for i in range(3):
        a = rng.integers(0, 256, size=(90, 90), dtype=np.uint8)
        name = f"s{i}.png"
        Image.fromarray(a, mode="L").save(os.path.join(sdir, name))
        meta.append({"file": name, "orig_width": 90, "orig_height": 90, "bounding_boxes_pixel_xyxy": [
            {"class_name": f1, "x_min": 2, "y_min": 2, "x_max": 25, "y_max": 25},
            {"class_name": f2, "x_min": 65, "y_min": 65, "x_max": 88, "y_max": 88}]})
    json.dump(meta, open(os.path.join(sdir, "meta.json"), "w"))
    cfg = D.build_config()
    chash = D.config_hash(cfg)
    reqs, info = D.build_requests(data_dir=sdir, cfg=cfg)
    write_jsonl(os.path.join(out, "requests.jsonl"), reqs)
    ST.write_json_atomic(os.path.join(out, "config.json"), {**cfg, "config_sha256": chash})
    ST.write_json_atomic(os.path.join(out, "image_info.json"), info)
    subsets = D.fixed_subsets(reqs)
    ST.write_json_atomic(os.path.join(out, "subsets.json"), subsets)
    preds = []
    for r in reqs:
        m = float(rng.normal())
        preds.append({"id": r["id"], "status": "ok", "m": m, "m_fp32head": m + 1e-4, "lp_yes": -1.0,
                      "lp_no": -1.0 - m, "p_yes_plus_no": 0.9, "top1_token": "Yes", "n_tokens": 300,
                      "n_image_tokens": 1, "pixel_values_shape": [1, 3, 896, 896], "prompt_intact": True,
                      "request_sha256": r["request_sha256"], "config_sha256": chash,
                      "input_pixel_sha256": r["input_pixel_sha256"], "scorer_version": D.SCORER_VERSION,
                      "phase": "full", "seconds": 0.1, "ts": 0.0})
    write_jsonl(os.path.join(out, "predictions.jsonl"), preds)
    by = {p["id"]: p for p in preds}
    req_by = {r["id"]: r for r in reqs}
    ver = []
    for rid in subsets["verification"]:
        m = by[rid]["m"]
        ver.append({"id": rid, "session": 0, "m_main": m, "m_repeat": m, "repeat_abs_diff": 0.0,
                    "tf_lp_yes": -1.0, "tf_lp_no": -1.0 - m, "m_tf": m, "tf_abs_diff": 0.0,
                    "gen_text": "Yes", "gen_token_ids": [1], "gen_n_forward": 1, "gen_truncated": False,
                    "gen_parsed": "Yes" if m > 0 else "No", "score_decision": "Yes" if m > 0 else "No",
                    "gen_agrees": True, "sec_repeat": 0.1, "sec_tf": 0.1, "sec_gen": 0.1,
                    "request_sha256": req_by[rid]["request_sha256"], "config_sha256": chash})
    write_jsonl(os.path.join(out, "verification.jsonl"), ver)
    ST.write_json_atomic(os.path.join(out, "calibration.json"), {"projected_total_device_min": 0.0})
    return sdir, out, reqs, preds, ver, subsets


def exits(fn, argv):
    try:
        fn(argv)
        return False, "no exit"
    except SystemExit as e:
        return True, str(e)


def eval_refuses(out, sdir):
    """evaluate_qes 진입점이 거부하고 metrics.json·complete·criteria를 만들지 않는지."""
    ex, msg = exits(evaluate_qes.main, ["--out", out, "--data-dir", sdir])
    gate = json.load(open(os.path.join(out, "evaluation_gate.json")))
    return (ex and not os.path.exists(os.path.join(out, "metrics.json"))
            and gate["completion"] == "incomplete" and "criteria" not in gate), gate


def select_ok(out, sdir):
    select_qes.main(["--out", out, "--data-dir", sdir])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    base = os.path.join(args.out, "fixtures")
    os.makedirs(base, exist_ok=True)

    # 0) 유효 fixture: select → evaluate 통과, complete
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, "valid"))
    select_ok(out, sdir)
    evaluate_qes.main(["--out", out, "--data-dir", sdir])
    met = json.load(open(os.path.join(out, "metrics.json")))
    check("valid fixture: evaluate complete", met["completion"] == "complete" and "criteria" in met
          and met["gate"]["completion"] == "gate_passed")
    ex, msg = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
    check("valid fixture: runner preflight passes, nothing to do (no GPU)",
          not ex and not os.path.exists(os.path.join(out, "env_full_0.json")), msg)

    # 1) 실제 이미지 변경 + 기존 manifest 유지
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, "image_changed"))
    select_ok(out, sdir)
    p = os.path.join(sdir, "s1.png")
    a = np.array(Image.open(p))
    a[5, 5] = (int(a[5, 5]) + 1) % 256
    Image.fromarray(a, mode="L").save(p)
    ex, msg = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
    check("image change: runner resume refuses (completed requests included)", ex and "preflight" in msg, msg)
    ex, msg = exits(select_qes.main, ["--out", out, "--data-dir", sdir])
    check("image change: selector refuses", ex and "preflight" in msg, msg)
    ok, gate = eval_refuses(out, sdir)
    check("image change: evaluator refuses, no complete", ok and not gate["stages"]["manifest"]["pass"])

    # 2) request 본문 변경 (hash를 본문에 맞게 다시 쓴 경우 / 쓰지 않은 경우)
    for variant in ("rehashed", "stale_hash"):
        sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, f"request_{variant}"))
        select_ok(out, sdir)
        r2 = [dict(r) for r in reqs]
        r2[0]["prompt"] = r2[0]["prompt"] + " "
        if variant == "rehashed":
            r2[0]["request_sha256"] = D.sha256_json({k: v for k, v in r2[0].items() if k != "request_sha256"})
        write_jsonl(os.path.join(out, "requests.jsonl"), r2)
        ex1, m1 = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
        ex2, m2 = exits(select_qes.main, ["--out", out, "--data-dir", sdir])
        ok, gate = eval_refuses(out, sdir)
        check(f"request body change ({variant}): runner/selector/evaluator refuse", ex1 and ex2 and ok, (m1, m2))

    # 3) verification 결함
    def ver_case(name, mutate):
        sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, f"ver_{name}"))
        select_ok(out, sdir)
        write_jsonl(os.path.join(out, "verification.jsonl"), mutate([dict(x) for x in ver], reqs))
        ok, gate = eval_refuses(out, sdir)
        whats = sorted({p_["what"] for p_ in gate["stages"]["verification"].get("problems", [])})
        check(f"verification {name}: evaluator refuses", ok and not gate["stages"]["verification"]["pass"], whats)

    ver_case("missing_file", lambda v, r: [])
    ver_case("missing_one", lambda v, r: v[1:])
    ver_case("tf_fail", lambda v, r: [{**x, "m_tf": x["m_tf"] + 0.01, "tf_abs_diff": 0.01} if i == 0 else x
                                      for i, x in enumerate(v)])
    ver_case("repeat_fail", lambda v, r: [{**x, "m_repeat": x["m_repeat"] + 0.5, "repeat_abs_diff": 0.5}
                                          if i == 0 else x for i, x in enumerate(v)])
    ver_case("conflicting_duplicate", lambda v, r: v + [{**v[0], "m_repeat": v[0]["m_repeat"] + 1e-6,
                                                         "repeat_abs_diff": 1e-6}])
    ver_case("identical_duplicate", lambda v, r: v + [dict(v[0])])
    ver_case("unexpected_id", lambda v, r: v + [{**v[0], "id": [x["id"] for x in r if x["id"] not in
                                                                {y["id"] for y in v}][0]}])
    ver_case("request_hash_mismatch", lambda v, r: [{**x, "request_sha256": "0" * 64} if i == 0 else x
                                                    for i, x in enumerate(v)])
    ver_case("m_main_stale", lambda v, r: [{**x, "m_main": x["m_main"] + 0.1} if i == 0 else x
                                           for i, x in enumerate(v)])
    ver_case("nan", lambda v, r: [{**x, "tf_abs_diff": float("nan")} if i == 0 else x for i, x in enumerate(v)])

    # 4) 오래된 selection: selection 후 prediction 하나를 (verification 대상이 아닌 것) 바꿈
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, "stale_selection"))
    select_ok(out, sdir)
    vset = set(subsets["verification"])
    p2 = [dict(x) for x in preds]
    k = [i for i, x in enumerate(p2) if x["id"] not in vset][0]
    p2[k]["m_fp32head"] += 0.25  # m은 그대로, 민감도 필드만 변경
    write_jsonl(os.path.join(out, "predictions.jsonl"), p2)
    ok, gate = eval_refuses(out, sdir)
    check("stale selection (only m_fp32head changed): evaluator refuses",
          ok and [x["what"] for x in gate["stages"]["selection"]["problems"]] == ["stale_selection_predictions_digest"],
          gate["stages"]["selection"])
    # 구형식 selection (requests_digest 없음, m만의 digest) → 거부
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, "old_format_selection"))
    select_ok(out, sdir)
    s = json.load(open(os.path.join(out, "selections.json")))
    s.pop("requests_digest")
    ST.write_json_atomic(os.path.join(out, "selections.json"), s)
    ok, gate = eval_refuses(out, sdir)
    check("old-format selection: evaluator refuses", ok, gate["stages"]["selection"])

    # 5) m은 같고 m_fp32head만 다른 중복 prediction
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, "dup_fp32head"))
    dup = {**preds[7], "m_fp32head": preds[7]["m_fp32head"] + 0.5, "seconds": 9.9}
    with open(os.path.join(out, "predictions.jsonl"), "a") as f:
        f.write(json.dumps(dup) + "\n")
    ex1, m1 = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
    ex2, m2 = exits(select_qes.main, ["--out", out, "--data-dir", sdir])
    ok, gate = eval_refuses(out, sdir)
    check("duplicate differing only in m_fp32head: runner/selector/evaluator refuse",
          ex1 and "conflicting" in m1 and ex2 and ok and gate["stages"]["predictions"]["n_conflicts"] == 1, (m1, m2))
    # 비결과 metadata만 다른 중복은 일관된 중복
    v = ST.validate_predictions(reqs, preds + [{**preds[7], "seconds": 5.0, "ts": 1.0, "phase": "calib"}],
                                D.config_hash(D.build_config()), D.SCORER_VERSION)
    check("duplicate differing only in metadata (seconds/ts/phase): consistent",
          v["status"] == "complete" and v["duplicates_consistent"] == 1)

    # 6) NaN/Inf 결과 거부
    for bad in (float("nan"), float("inf")):
        v = ST.validate_predictions(reqs, [({**x, "m": bad} if i == 3 else x) for i, x in enumerate(preds)],
                                    D.config_hash(D.build_config()), D.SCORER_VERSION)
        check(f"non-finite m ({bad}) rejected", v["status"] == "incomplete"
              and v["rejected"] == [{"id": preds[3]["id"], "reason": "non_finite_result"}])
    v = ST.validate_predictions(reqs, [({k: val for k, val in x.items() if k != "m_fp32head"} if i == 3 else x)
                                       for i, x in enumerate(preds)], D.config_hash(D.build_config()), D.SCORER_VERSION)
    check("missing result field rejected", v["rejected"] == [{"id": preds[3]["id"], "reason": "missing_result_field"}])
    # NaN이 파일로 들어간 경우 selector 진입점도 결과를 만들지 않는다
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, "nan_file"))
    p2 = [dict(x) for x in preds]
    p2[4]["m"] = float("nan")
    write_jsonl(os.path.join(out, "predictions.jsonl"), p2)
    ex, msg = exits(select_qes.main, ["--out", out, "--data-dir", sdir])
    check("NaN prediction in file: selector refuses", ex and "incomplete" in msg
          and not os.path.exists(os.path.join(out, "selections.json")), msg)

    n_fail = sum(not r["pass"] for r in RESULTS)
    ST.write_json_atomic(os.path.join(args.out, "qes_entry_tests.json"),
                         {"n": len(RESULTS), "n_fail": n_fail, "results": RESULTS})
    print(f"QES entry-point tests: {len(RESULTS) - n_fail}/{len(RESULTS)} pass")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
