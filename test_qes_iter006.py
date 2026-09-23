"""iter_006: QES 고정 부분집합 재생성 검사와 평가 상태 전이(fail-closed) 결함 주입 테스트 (CPU, 모델 없음).

실행: python research/test_qes_iter006.py --out research/results/iter_006/qes_iter006_tests

A. subsets.json 변형(verification 목록과 기록의 동시 축소·공집합·동일 크기 교체·필수 key 누락 등)을
   runner resume·selector·evaluator 세 진입점 모두에서 거부하는지.
B. 평가 성공 → 입력 변형·필수 파일 손상·예외로 재평가 실패 → 원상복구 후 재평가의 상태 전이.
   실패 뒤에는 현재 complete metrics·표·overlay·투자 판정이 남지 않아야 한다.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate_qes  # noqa: E402
import run_qes  # noqa: E402
import select_qes  # noqa: E402
from qes import data as D  # noqa: E402
from qes import store as ST  # noqa: E402
from test_qes_preflight import build_fixture, exits, write_jsonl  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": str(detail)[:500]})
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {str(detail)[:200]}", flush=True)


def status(out):
    p = os.path.join(out, evaluate_qes.STATUS_FILE)
    return json.load(open(p)) if os.path.exists(p) else None


def no_current_outputs(out):
    """현재 위치에 complete metrics·표·overlay가 없고 상태가 complete가 아님."""
    st = status(out)
    return (not any(os.path.lexists(os.path.join(out, n)) for n in evaluate_qes.EVAL_ARTIFACTS)
            and st is not None and st["evaluation"] == "incomplete" and st["complete"] is False
            and st["investment_decision"] is None and evaluate_qes.load_complete_metrics(out) is None)


def is_complete(out):
    st = status(out)
    m = evaluate_qes.load_complete_metrics(out)
    return (st is not None and st["evaluation"] == "complete" and st["complete"] is True
            and st["investment_decision"] is not None and m is not None and m["completion"] == "complete"
            and st["prediction_collection"]["status"] == "complete")


def all_entry_points_refuse(out, sdir):
    # phase full: preflight가 (잘못) 통과해도 모든 prediction이 있어 GPU 작업 없이 끝난다
    ex1, m1 = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
    ex2, m2 = exits(select_qes.main, ["--out", out, "--data-dir", sdir])
    ex3, m3 = exits(evaluate_qes.main, ["--out", out, "--data-dir", sdir])
    ok = ex1 and "preflight" in m1 and ex2 and "preflight" in m2 and ex3 and no_current_outputs(out)
    gate_p = os.path.join(out, evaluate_qes.GATE_FILE)
    whats = []
    if os.path.exists(gate_p):
        g = json.load(open(gate_p))
        whats = sorted({p["what"] for p in g["stages"].get("manifest", {}).get("problems", [])})
    return ok, {"runner": m1[:150], "selector": m2[:150], "evaluator": m3[:150], "manifest_problems": whats}


def fresh(base, name):
    sdir, out, reqs, preds, ver, subsets = build_fixture(os.path.join(base, name))
    select_qes.main(["--out", out, "--data-dir", sdir])
    evaluate_qes.main(["--out", out, "--data-dir", sdir])
    return sdir, out, reqs, preds, ver, subsets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    base = os.path.join(args.out, "fixtures")
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(base)

    # ---------------- A. 고정 부분집합 변형
    sdir, out, reqs, preds, ver, subsets = fresh(base, "valid")
    check("A0 valid fixture: complete, subsets == fixed_subsets(reqs)",
          is_complete(out) and subsets == D.fixed_subsets(reqs), status(out)["evaluation"])
    ex, msg = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
    check("A0 valid fixture: runner preflight passes", not ex, msg)

    def subset_case(name, mut_subsets, mut_ver=None, expect_refuse=True):
        sdir, out, reqs, preds, ver, subsets = fresh(base, f"subset_{name}")
        s2 = mut_subsets(json.loads(json.dumps(subsets)), reqs)
        if s2 is None:
            os.remove(os.path.join(out, "subsets.json"))
        else:
            ST.write_json_atomic(os.path.join(out, "subsets.json"), s2)
        if mut_ver is not None:
            write_jsonl(os.path.join(out, "verification.jsonl"), mut_ver([dict(x) for x in ver], reqs, s2))
        if expect_refuse:
            ok, d = all_entry_points_refuse(out, sdir)
            check(f"A subsets {name}: runner/selector/evaluator refuse, no current complete", ok, d)
        else:
            ex1, m1 = exits(run_qes.main, ["--out", out, "--phase", "full", "--data-dir", sdir])
            evaluate_qes.main(["--out", out, "--data-dir", sdir])
            check(f"A subsets {name}: accepted (order not meaningful)", not ex1 and is_complete(out), m1)

    keep_ver = lambda v, r, s: [x for x in v if x["id"] in set(s["verification"])]  # noqa: E731
    # 목록과 기록의 동시 축소 (verification 검사 자체는 통과하는 조작)
    subset_case("verification_shrunk_with_records",
                lambda s, r: {**s, "verification": s["verification"][:-3]}, keep_ver)
    subset_case("verification_empty_with_records", lambda s, r: {**s, "verification": []}, keep_ver)

    def swap(s, r):
        allv = set(s["verification"]) | set(s["calibration"])
        other = [x["id"] for x in r if x["id"] not in allv][0]
        return {**s, "verification": s["verification"][:-1] + [other]}

    def swap_ver(v, r, s):
        # 교체된 ID에도 형식상 유효한 verification 기록을 만든다 (기록만으로는 통과하도록)
        preds = {p["id"]: p for p in ST.read_jsonl(os.path.join(base, "subset_same_size_swap", "out",
                                                                "predictions.jsonl"))}
        new = s["verification"][-1]
        tmpl = dict(v[0])
        m = preds[new]["m"]
        tmpl.update({"id": new, "m_main": m, "m_repeat": m, "m_tf": m, "tf_lp_no": -1.0 - m,
                     "request_sha256": {x["id"]: x for x in r}[new]["request_sha256"]})
        return [x for x in v if x["id"] in set(s["verification"])] + [tmpl]

    subset_case("same_size_swap", swap, swap_ver)
    subset_case("missing_verification_key", lambda s, r: {"calibration": s["calibration"]})
    subset_case("missing_calibration_key", lambda s, r: {"verification": s["verification"]})
    subset_case("unexpected_extra_key", lambda s, r: {**s, "verification_extra": []})
    subset_case("duplicate_id", lambda s, r: {**s, "verification": s["verification"] + [s["verification"][0]]})
    subset_case("calibration_shrunk", lambda s, r: {**s, "calibration": s["calibration"][:-1]})
    subset_case("not_a_list", lambda s, r: {**s, "verification": ",".join(s["verification"])})
    subset_case("file_missing", lambda s, r: None)
    subset_case("permuted_order_only", lambda s, r: {"verification": s["verification"][::-1],
                                                     "calibration": s["calibration"][::-1]}, expect_refuse=False)
    # subsets.json 파싱 실패
    sdir, out, reqs, preds, ver, subsets = fresh(base, "subset_unparseable")
    with open(os.path.join(out, "subsets.json"), "w") as f:
        f.write("{not json")
    ok, d = all_entry_points_refuse(out, sdir)
    check("A subsets unparseable JSON: all entry points refuse", ok, d)

    # ---------------- B. 평가 상태 전이
    sdir, out, reqs, preds, ver, subsets = fresh(base, "transition")
    check("B1 initial evaluation complete (status+hash-validated metrics)", is_complete(out), status(out))
    orig = {n: open(os.path.join(out, n)).read() for n in ("subsets.json", "verification.jsonl",
                                                           "predictions.jsonl", "selections.json")}

    def restore():
        for n, t in orig.items():
            with open(os.path.join(out, n), "w") as f:
                f.write(t)

    def reeval_fails(label):
        # evaluator는 gate 실패 시 SystemExit, 그 밖의 예외는 상태를 incomplete로 기록한 뒤 다시 올린다
        try:
            ex, msg = exits(evaluate_qes.main, ["--out", out, "--data-dir", sdir])
        except Exception as e:  # noqa: BLE001
            ex, msg = True, f"raised {e!r}"
        inv = os.path.join(out, "invalidated")
        n_inv = sum(os.path.exists(os.path.join(inv, d, "metrics.json")) for d in os.listdir(inv)) \
            if os.path.isdir(inv) else 0
        check(f"B {label}: re-evaluation incomplete, no current metrics/table/overlays/decision",
              ex and no_current_outputs(out) and n_inv >= 1, {"msg": msg[:120], "reason": status(out)["reason"][:150]})

    def reeval_complete(label):
        evaluate_qes.main(["--out", out, "--data-dir", sdir])
        check(f"B {label}: restored -> complete again", is_complete(out), status(out)["evaluation"])

    # 입력 변형: verification 목록과 기록 동시 축소
    s2 = json.loads(orig["subsets.json"])
    s2["verification"] = s2["verification"][:6]
    ST.write_json_atomic(os.path.join(out, "subsets.json"), s2)
    write_jsonl(os.path.join(out, "verification.jsonl"), [x for x in ver if x["id"] in set(s2["verification"])])
    reeval_fails("B2 shrunk verification set")
    restore()
    reeval_complete("B3")
    # verification 기록 하나 변형 (gate 단계 실패)
    write_jsonl(os.path.join(out, "verification.jsonl"),
                [{**x, "tf_abs_diff": 0.5} if i == 0 else x for i, x in enumerate(ver)])
    reeval_fails("B4 verification record tf failure")
    restore()
    reeval_complete("B5")
    # 필수 파일 손상: predictions.jsonl JSON 파싱 실패 (gate 도중 예외)
    with open(os.path.join(out, "predictions.jsonl"), "a") as f:
        f.write("{broken json\n")
    reeval_fails("B6 corrupted predictions.jsonl (JSON parse error)")
    restore()
    reeval_complete("B7")
    # 필수 파일 누락: selections.json
    os.remove(os.path.join(out, "selections.json"))
    reeval_fails("B8 missing selections.json")
    restore()
    reeval_complete("B9")
    # 필수 파일 누락: requests.jsonl (manifest 단계)
    rq = open(os.path.join(out, "requests.jsonl")).read()
    os.remove(os.path.join(out, "requests.jsonl"))
    reeval_fails("B10 missing requests.jsonl")
    with open(os.path.join(out, "requests.jsonl"), "w") as f:
        f.write(rq)
    reeval_complete("B11")
    # 평가 계산 도중 예외
    real_overlays = evaluate_qes.overlays

    def boom(*a, **k):
        raise RuntimeError("injected failure during overlays")

    evaluate_qes.overlays = boom
    try:
        reeval_fails("B12 exception during metric computation")
    finally:
        evaluate_qes.overlays = real_overlays
    stages = [d for d in os.listdir(out) if d.startswith(".eval_staging_")]
    check("B12 staging outputs never published", not any(
        os.path.lexists(os.path.join(out, n)) for n in evaluate_qes.EVAL_ARTIFACTS), stages)
    reeval_complete("B13")
    # 게시 도중(완료 상태 기록 직전) 예외: 이미 옮긴 산출물도 무효화해야 한다
    real_ws = evaluate_qes.write_status

    def ws_fail_on_complete(o, st):
        if st.get("evaluation") == "complete":
            raise OSError("injected failure writing complete status")
        return real_ws(o, st)

    evaluate_qes.write_status = ws_fail_on_complete
    try:
        reeval_fails("B14 exception while publishing complete status")
    finally:
        evaluate_qes.write_status = real_ws
    reeval_complete("B15")
    # 게시된 산출물을 사후 변조하면 load_complete_metrics가 거부
    with open(os.path.join(out, "eval_table.md"), "a") as f:
        f.write("tampered\n")
    check("B16 post-hoc tampered artifact: load_complete_metrics returns None",
          evaluate_qes.load_complete_metrics(out) is None)
    # 원시 prediction은 무효화 대상이 아니다
    check("B17 raw predictions/verification never moved by invalidation",
          open(os.path.join(out, "predictions.jsonl")).read() == orig["predictions.jsonl"]
          and not any(os.path.exists(os.path.join(out, "invalidated", d, "predictions.jsonl"))
                      for d in os.listdir(os.path.join(out, "invalidated"))))

    n_fail = sum(not r["pass"] for r in RESULTS)
    ST.write_json_atomic(os.path.join(args.out, "qes_iter006_tests.json"),
                         {"n": len(RESULTS), "n_fail": n_fail, "results": RESULTS})
    print(f"QES iter006 tests: {len(RESULTS) - n_fail}/{len(RESULTS)} pass")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
