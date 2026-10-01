"""iter_045 CPU fixture/regression 검사. 결과: results/iter_045/tests/fixtures_mg45.json (기존 파일은 덮어쓰지 않는다).

python test_mg45.py
"""
import glob
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time

import numpy as np

import mg45_eval as E
import mg45_report as RP
import mg45_verify as V
import pg39_spec as S39
import pg43_run as R

OUT = sys.argv[1] if len(sys.argv) > 1 else "results/iter_045/tests/fixtures_mg45.json"
RES = []


def check(name, ok, detail=None):
    RES.append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, detail if not ok else "")


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return True, str(e)[:120]
    except Exception as e:
        return False, f"wrong exception {type(e).__name__}: {e}"
    return False, "no exception"


def copy_dir(src, tag):
    dst = f"results/iter_045/tests/tmp_{tag}_{int(time.time()*1000)%10**9}"
    shutil.copytree(src, dst)
    return dst


def main():
    if os.path.exists(OUT):
        sys.exit("fixture output exists")
    man = json.load(open(E.MAN))
    # ---- A. 반입 blob 일치 ----
    files = ["pg43_run.py", "pg43_eval.py", "pg43_retrieval.py", "pg39_spec.py", "pg39_data.py", "pg41_verify.py", "rsna_diag/__init__.py", "rsna_diag/generate.py",
             "rsna_diag/geometry.py", "rsna_diag/metrics.py", "rsna_diag/parse.py", "rsna_diag/prompts.py", "rsna_diag/lora.py", "rsna_diag/queue_lock.py"]
    src = "b50aa230a86c6d5b6c6b280fe718170ce4ecf220"
    bad = []
    for f in files:
        h = subprocess.run(["git", "hash-object", "--", f], capture_output=True, text=True).stdout.strip()
        b = subprocess.run(["git", "rev-parse", f"{src}:{f}"], capture_output=True, text=True).stdout.strip()
        if h != b:
            bad.append(f)
    check("A1 reused 14 files == source blobs", not bad, bad)
    # ---- B. MG dir 변조 거부 ----
    base = "results/iter_045/mg/D24_P_w1b1"
    ok_recs, _, _ = E.verify_mg_dir(base, "D24", "P", man)
    check("B0 clean D24_P verifies (48 records)", len(ok_recs) == 48)
    d = copy_dir(base, "edit_logit")
    f = d + "/raw_worker0.jsonl"
    rows = [json.loads(l) for l in open(f)]
    rows[0]["logits"][0][0] += 0.5
    open(f, "w").write("".join(json.dumps(r) + "\n" for r in rows))
    ok, msg = raises(lambda: E.verify_mg_dir(d, "D24", "P", man), E.EvalError)
    check("B1 edited raw row rejected (file hash)", ok, msg)
    d = copy_dir(base, "drop_row")
    f = d + "/raw_worker0.jsonl"
    lines = open(f).read().splitlines(True)
    open(f, "w").write("".join(lines[:-1]))
    ok, msg = raises(lambda: E.verify_mg_dir(d, "D24", "P", man), E.EvalError)
    check("B2 dropped row rejected", ok, msg)
    d = copy_dir(base, "dup_row")
    f = d + "/raw_worker0.jsonl"
    lines = open(f).read().splitlines(True)
    open(f, "w").write("".join(lines + lines[:1]))
    ok, msg = raises(lambda: E.verify_mg_dir(d, "D24", "P", man), E.EvalError)
    check("B3 duplicated row rejected", ok, msg)
    d = copy_dir(base, "proto")
    p = json.load(open(d + "/launch_protocol.json"))
    p["code"]["mg45_mg.py"] = "0" * 64
    json.dump(p, open(d + "/launch_protocol.json", "w"))
    ok, msg = raises(lambda: E.verify_mg_dir(d, "D24", "P", man), E.EvalError)
    check("B4 edited launch protocol rejected", ok, msg)
    d = copy_dir(base, "comp")
    c = json.load(open(d + "/completion.json"))
    c["exit_codes"] = [1]
    json.dump(c, open(d + "/completion.json", "w"))
    ok, msg = raises(lambda: E.verify_mg_dir(d, "D24", "P", man), E.EvalError)
    check("B5 nonzero exit code in completion rejected", ok, msg)
    ok, msg = raises(lambda: E.verify_mg_dir(base, "D24", "MS", man), E.EvalError)
    check("B6 wrong ckpt label rejected (ckpt sha/identity)", ok, msg)
    # ---- C. 재개/torn row ----
    rd = "results/iter_045/tests/resume_D24_P"
    rr, rc, _ = E.verify_mg_dir(rd, "D24", "P", man)
    same = all(rr[k]["logits"] == ok_recs[k]["logits"] and rr[k]["detections"] == ok_recs[k]["detections"] for k in ok_recs)
    parts = glob.glob(rd + "/raw_worker0.jsonl.partial.*.bin")
    check("C1 kill(137)+torn-row resume: 48 unique, outputs identical to uninterrupted run", len(rr) == 48 and same, {"n": len(rr)})
    check("C2 torn bytes preserved in .partial file", len(parts) == 1 and open(parts[0], "rb").read().startswith(b'{"request_id": "torn'), parts)
    # ---- D. matching 독립 구현 대조 ----
    rng = random.Random(7)

    def rb():
        x0, y0 = rng.random() * 0.6, rng.random() * 0.6
        return [x0, y0, x0 + 0.05 + rng.random() * 0.35, y0 + 0.05 + rng.random() * 0.35]
    mism = 0
    for _ in range(400):
        pred = [rb() for _ in range(rng.randint(0, 5))]
        gt = [rb() for _ in range(rng.randint(0, 5))]
        if rng.random() < 0.3 and pred and gt:
            gt[0] = list(pred[0])  # 동일 box (동점/완전일치)
        for thr in (0.3, 0.5):
            a = S39.sent_metrics(pred, gt, thr)
            f1b, fpb, _ = V.f1(pred, gt, thr)
            mism += int(abs(a["f1"] - f1b) > 1e-12 or a["fp"] != fpb)
    check("D1 match_fast == independent exhaustive matching (400 random x2 thr)", mism == 0, mism)
    tie_pred = [[0.0, 0.0, 0.5, 0.5], [0.0, 0.0, 0.5, 0.5]]
    tie_gt = [[0.0, 0.0, 0.5, 0.5]]
    check("D2 duplicate-box tie: one TP one FP", S39.sent_metrics(tie_pred, tie_gt, 0.3)["fp"] == 1 and V.f1(tie_pred, tie_gt, 0.3)[1] == 1)
    # ---- E. 선택 규칙 ----
    tb = {0.2: {"f1_03": .5, "f1_05": .2, "fp_per_sentence": .3}, 0.4: {"f1_03": .5, "f1_05": .2, "fp_per_sentence": .3},
          0.6: {"f1_03": .4, "f1_05": .3, "fp_per_sentence": .1}, 0.8: {"f1_03": .5, "f1_05": .25, "fp_per_sentence": .4}}
    check("E1 threshold pick: F1@0.3 tie -> F1@0.5 higher (0.8)", E.pick_threshold(tb) == 0.8)
    tb[0.8]["f1_05"] = 0.2
    tb[0.8]["fp_per_sentence"] = 0.2
    check("E2 tie F1@0.3,F1@0.5 -> lower FP (0.8)", E.pick_threshold(tb) == 0.8)
    tb[0.8]["fp_per_sentence"] = 0.3
    check("E3 full tie -> higher threshold (0.8)", E.pick_threshold(tb) == 0.8)
    sel = json.load(open("results/iter_045/decisions/D24_select.json"))
    cand = {ck: sel["ckpts"][ck]["table"][str(sel["ckpts"][ck]["selected_threshold"])] for ck in ("P", "MS")}
    check("E4 stored selection reproduces from stored tables", sel["selected"]["ckpt"] == sorted(["MS", "P"], key=lambda ck: (-round(cand[ck]["f1_03"], 12), -round(cand[ck]["f1_05"], 12), round(cand[ck]["fp_per_sentence"], 12)))[0])
    # ---- F. 비용 통계 helper ----
    iv = [(0, 4), (2, 6), (10, 12)]
    check("F1 interval union != request wall sum (gap and overlap handled)", abs(RP.PE_union(iv) - 8.0) < 1e-12 and sum(e - s for s, e in iv) == 10)
    r = RP.ratio_ci([2, 2, 2, 2, 2, 2], [1, 1, 1, 1, 1, 1])
    check("F2 constant ratio CI collapses", abs(r["geo_mean"] - 2) < 1e-12 and abs(r["ci95_hi"] - 2) < 1e-9)
    ok, msg = raises(lambda: RP.ratio_ci([1, 2, 3], [1, 1, 1]), ValueError)
    check("F3 ratio CI refuses n != 6 (t(5) fixed)", ok, msg)
    r = RP.ratio_ci([1, 2, 3, 4, 5, 6], [1, 1, 1, 1, 1, 1])
    x = np.log(np.arange(1, 7, dtype=float))
    chk = float(np.exp(x.mean() + 2.5705818366147395 * x.std(ddof=1) / np.sqrt(6)))
    check("F4 ratio CI equals independent log-t formula", abs(r["ci95_hi"] - chk) < 1e-9)
    # ---- G. C import 변조 거부 (복사본 + 모듈 상수 교체) ----
    ents = {e["PatientID"]: e for e in man["V96"]}
    base_c = RP.C_GEN
    try:
        RP.verify_c_import(ents)
        check("G0 clean C import verifies (192)", True)
    except Exception as e:
        check("G0 clean C import verifies (192)", False, str(e))
    d = copy_dir(base_c, "c_clean")
    # records 편집: suffix_ids 변경 -> record digest 불일치
    fw = sorted(glob.glob(d + "/gen_worker*.jsonl"))[0]
    rows = [json.loads(l) for l in open(fw)]
    rows[0]["suffix_ids"] = rows[0]["suffix_ids"][:-1] + [1]
    open(fw, "w").write("".join(json.dumps(r) + "\n" for r in rows))
    RP.C_GEN = d
    ok, msg = raises(lambda: RP.verify_c_import(ents), R.RunError)
    check("G1 edited C record rejected (worker file hash/record digest)", ok, msg)
    d2 = copy_dir(base_c, "c_comp")
    c = json.load(open(d2 + "/completion.json"))
    c["protocol_digest"] = "0" * 64
    json.dump(c, open(d2 + "/completion.json", "w"))
    RP.C_GEN = d2
    ok, msg = raises(lambda: RP.verify_c_import(ents), R.RunError)
    check("G2 completion protocol digest != original protocol rejected", ok, msg)
    d3 = copy_dir(base_c, "c_drop")
    fw = sorted(glob.glob(d3 + "/gen_worker*.jsonl"))[0]
    lines = open(fw).read().splitlines(True)
    open(fw, "w").write("".join(lines[:-1]))
    RP.C_GEN = d3
    ok, msg = raises(lambda: RP.verify_c_import(ents), R.RunError)
    check("G3 dropped C record rejected", ok, msg)
    RP.C_GEN = base_c
    # ---- H. lock 변조 거부 ----
    if os.path.exists("results/iter_045/eval/eval_lock.json"):
        lk = json.load(open("results/iter_045/eval/eval_lock.json"))
        lk["files"]["mg45_eval.py"] = "0" * 64
        tmp = "results/iter_045/tests/tmp_lock_%d.json" % (int(time.time() * 1000) % 10**9)
        json.dump(lk, open(tmp, "w"))
        ok, msg = raises(lambda: RP.check_lock(tmp), E.EvalError)
        check("H1 changed eval source vs lock rejected", ok, msg)
    # ---- I. verifier가 불일치를 PASS로 만들지 않는다 (독립 parser 단위) ----
    check("I1 own parser rejects trailing prose / non-list", V.own_parse_list('[{"box_2d":[1,2,3,4],"label":"qA"}] extra') is None and V.own_parse_list('{"a":1}') is None)
    check("I2 own parser accepts clean EOS list", V.own_parse_list('[{"box_2d": [10, 20, 30, 40], "label": "qA"}]<end_of_turn>') == [[10.0, 20.0, 30.0, 40.0]])
    n_pass = sum(r["pass"] for r in RES)
    json.dump({"n": len(RES), "n_pass": n_pass, "results": RES}, open(OUT, "x"), indent=1)
    print(f"{n_pass}/{len(RES)} pass")
    sys.exit(0 if n_pass == len(RES) else 1)


if __name__ == "__main__":
    main()
