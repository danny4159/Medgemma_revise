"""iter_057 검사: fixture(순수 함수) + 변조 거부 + 원시 jsonl 직접 count 독립 검산. 결과: results/iter_057/tests/fixtures_msd57.json"""
import glob
import json
import os
import shutil
import sys

import numpy as np

import msd56_run as R
import msd57_analysis as M

res = {}


def check(name, cond):
    res[name] = bool(cond)
    print("PASS" if cond else "FAIL", name)


# 1) parser: invalid는 None (ABSENT로 바꾸지 않음)
check("parse_invalid_none", R.parse_answer("The lesion is present") is None and R.parse_answer("PRESENT<end_of_turn>") == "PRESENT"
      and R.parse_answer("absent.") == "ABSENT")

# 2) counts: invalid는 해당 class 오답, 단일 class 위치 BA는 nan
rows = [{"case": "a", "slab": 0, "present": True, "answer": None}, {"case": "a", "slab": 0, "present": False, "answer": None},
        {"case": "a", "slab": 1, "present": True, "answer": "PRESENT"}, {"case": "b", "slab": 1, "present": True, "answer": "ABSENT"}]
A = M.counts_by_case(rows, ["a", "b"], lambda t: t["answer"])
check("invalid_is_wrong_both_classes", A[0, 0, 0] == 0 and A[0, 0, 1] == 1 and A[0, 0, 2] == 0 and A[0, 0, 3] == 1)
S = A.sum(0)
check("single_class_slab_nan", np.isnan(M.ba_std(S[None], [1])[0]))
check("support_positions", M.support_positions(A) == [0])

# 3) 위치 규칙: 동률(전부 같은 BA)이면 PRESENT 위치 수 작은 규칙. D가 slab별 P=N 대칭인 경우
D = [{"slab": s, "present": p} for s in range(6) for p in (True, False)]
r = M.rule_search(D)
check("tie_break_fewest_present", r["rule_present_by_slab"] == [0] * 6 and r["n_tied"] == 64)
D2 = [{"slab": 1, "present": True}, {"slab": 1, "present": True}, {"slab": 2, "present": False}, {"slab": 3, "present": False}]
check("rule_selects_D_only", M.rule_search(D2)["rule_present_by_slab"][1] == 1)
try:
    M.rule_search([{"slab": 0, "present": True}])
    check("single_class_D_rejected", False)
except R.RunError:
    check("single_class_D_rejected", True)

# 4) bootstrap: case 단위 동일 재표집, class 소실 replicate는 undefined (재가중 없음)
Aone = np.zeros((3, 6, 4))
Aone[0, 0] = [1, 1, 0, 0]   # case0: slab0 양성만
Aone[1, 0] = [0, 0, 1, 1]   # case1: slab0 음성만
Aone[2, 0] = [1, 1, 1, 1]
out = M.cluster_boot_stats({"x": Aone, "y": Aone}, {"std": lambda S: M.ba_std(S["x"], [0]), "d": lambda S: M.ba_overall(S["x"]) - M.ba_overall(S["y"])}, b=200)
check("boot_undefined_counted", out["std"][2] < 200 and out["d"][2] <= 200)
check("boot_shared_draw_diff_zero", out["d"][0] == 0 and out["d"][1] == 0)
check("boot_deterministic", M.cluster_boot_stats({"x": Aone}, {"s": lambda S: M.ba_std(S["x"], [0])}, b=50) == M.cluster_boot_stats({"x": Aone}, {"s": lambda S: M.ba_std(S["x"], [0])}, b=50))
# 위치-only 규칙은 지원 위치마다 BA=0.5 -> 표준화 BA=0.5
rowsx = [{"case": c, "slab": s, "present": (s + i) % 2 == 0, "answer": None} for i, c in enumerate("abcd") for s in range(6)]
Ar = M.counts_by_case(rowsx, list("abcd"), M.rule_pred_fn([1, 0, 1, 0, 1, 0]))
check("position_only_std_BA_half", abs(M.ba_std(Ar.sum(0)[None], M.support_positions(Ar))[0] - 0.5) < 1e-12)

# 5) 변조 거부: 입력 복사본을 만들어 SRC를 임시 경로로 바꿔 호출
tmp = "results/iter_057/tests/tamper_src"
if os.path.exists(tmp):
    shutil.rmtree(tmp)
os.makedirs(tmp + "/data")
os.makedirs(tmp + "/gen/E")
gt_rows = json.load(open("results/iter_056/data/gt_slabs.json"))["rows"]
for n in ("requests_E.jsonl", "cond_map_E.json", "protocol_E.json"):
    shutil.copy(f"results/iter_056/data/{n}", f"{tmp}/data/{n}")
for f in glob.glob("results/iter_056/gen/E/gen_worker[0-9]*.jsonl"):
    shutil.copy(f, f"{tmp}/gen/E/")
# 요청 파일 경로(images)는 상대 경로라 그대로 유효. SRC 교체
orig = M.SRC
M.SRC = tmp


def expect_fail(name, mutate):
    mutate()
    try:
        M.load_split("E", gt_rows)
        check(name, False)
    except (R.RunError, KeyError, AssertionError):
        check(name, True)


M.SRC = tmp
try:
    M.load_split("E", gt_rows)
    check("tamper_baseline_loads_clean", True)
except Exception as e:
    check("tamper_baseline_loads_clean", False)
    print(e)
w0 = f"{tmp}/gen/E/gen_worker0.jsonl"
lines = open(w0).read().splitlines(True)
backup = list(lines)


def restore():
    open(w0, "w").writelines(backup)


# (a) 저장 answer를 raw와 다르게
rec = json.loads(lines[0])
rec["answer"] = "ABSENT" if rec["answer"] == "PRESENT" else "PRESENT"
open(w0, "w").writelines([json.dumps(rec) + "\n"] + lines[1:])
expect_fail("tamper_answer_vs_raw_rejected", lambda: None)
restore()
# (b) record 누락
open(w0, "w").writelines(lines[1:])
expect_fail("tamper_missing_record_rejected", lambda: None)
restore()
# (c) 중복 record
open(w0, "w").writelines(lines + [lines[0]])
expect_fail("tamper_duplicate_record_rejected", lambda: None)
restore()
# (d) protocol digest 변조
pj = json.load(open(f"{tmp}/data/protocol_E.json"))
pj["n_requests"] = 765
json.dump(pj, open(f"{tmp}/data/protocol_E.json", "w"))
expect_fail("tamper_protocol_rejected", lambda: None)
shutil.copy("results/iter_056/data/protocol_E.json", f"{tmp}/data/protocol_E.json")
# (e) cond_map rid 교체(다른 slab 요청으로) -> slices 불일치
cm = json.load(open(f"{tmp}/data/cond_map_E.json"))
cm[0]["rid"], cm[3]["rid"] = cm[3]["rid"], cm[0]["rid"]
json.dump(cm, open(f"{tmp}/data/cond_map_E.json", "w"))
expect_fail("tamper_cond_map_swap_rejected", lambda: None)
shutil.copy("results/iter_056/data/cond_map_E.json", f"{tmp}/data/cond_map_E.json")
# (f) cond_map 행 삭제
cm = json.load(open(f"{tmp}/data/cond_map_E.json"))
json.dump(cm[1:], open(f"{tmp}/data/cond_map_E.json", "w"))
expect_fail("tamper_cond_row_missing_rejected", lambda: None)
shutil.copy("results/iter_056/data/cond_map_E.json", f"{tmp}/data/cond_map_E.json")
# (g) manifest hash 변조
mf = "results/iter_057/tests/manifest_tamper"
os.makedirs(mf, exist_ok=True)
M.SRC = orig
json.dump({"files": {"x": "0"}}, open(mf + "/input_manifest.json", "w"))
try:
    M.lock_inputs(mf)
    check("tamper_manifest_hash_rejected", False)
except R.RunError:
    check("tamper_manifest_hash_rejected", True)

# 6) 독립 직접 count (M 함수 미사용): 원시 jsonl+cond_map+gt에서 dict로 센다
gt = {(g["case"], g["slab"]): g["present"] for g in gt_rows if g["split"] == "E"}
raw = {}
for f in glob.glob("results/iter_056/gen/E/gen_worker[0-9]*.jsonl"):
    for ln in open(f):
        r = json.loads(ln)
        t = r["suffix_text_raw"].replace("<end_of_turn>", "").strip().upper().rstrip(".!?,;: ")
        raw[r["rid"]] = t if t in ("PRESENT", "ABSENT") else None
cm = json.load(open("results/iter_056/data/cond_map_E.json"))
rep = json.load(open("results/iter_057/analysis/report.json"))
okall = True
for cn in M.CONDS:
    for s in range(6):
        tp = sum(1 for c in cm if c["cond"] == cn and c["slab"] == s and gt[(c["case"], s)] and raw[c["rid"]] == "PRESENT")
        fp = sum(1 for c in cm if c["cond"] == cn and c["slab"] == s and not gt[(c["case"], s)] and raw[c["rid"]] != "ABSENT")
        e = rep["cond"][cn]["by_slab"][str(s)]
        okall &= (tp == e["TP"] and fp == e["FP"])
check("independent_count_TP_FP_by_cond_slab", okall)
rv = rep["rule_D"]["rule_present_by_slab"]
tpr = sum(1 for (c, s), p in gt.items() if p and rv[s])
tnr = sum(1 for (c, s), p in gt.items() if (not p) and not rv[s])
P = sum(gt.values())
N = len(gt) - P
check("independent_rule_BA", abs((tpr / P + tnr / N) / 2 - rep["cond"]["RULE_D"]["BA_all"]) < 1e-12)
# DENSE 표준화 BA 독립 계산
sup = rep["support_positions_from_E_GT"]
bs = []
for s in sup:
    d = [c for c in cm if c["cond"] == "DENSE" and c["slab"] == s]
    p_ = [c for c in d if gt[(c["case"], s)]]
    n_ = [c for c in d if not gt[(c["case"], s)]]
    bs.append((sum(raw[c["rid"]] == "PRESENT" for c in p_) / len(p_) + sum(raw[c["rid"]] == "ABSENT" for c in n_) / len(n_)) / 2)
check("independent_DENSE_std_BA", abs(np.mean(bs) - rep["cond"]["DENSE"]["BA_std"]) < 1e-12)
check("support_from_E_GT", sup == [s for s in range(6) if any(gt[(c, s)] for c in {k[0] for k in gt}) and any(not gt[(c, s)] for c in {k[0] for k in gt})])

os.makedirs("results/iter_057/tests", exist_ok=True)
json.dump(res, open("results/iter_057/tests/fixtures_msd57.json", "w"), indent=1)
print(sum(res.values()), "/", len(res))
sys.exit(0 if all(res.values()) else 1)
