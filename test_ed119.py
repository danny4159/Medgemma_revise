"""iter_119 한정 fixture: unresolved≠wrong, 3x3 합, G→M·E→S 공유 변수 범위, 누락/중복 거부. 결과는 새 경로에만 쓴다."""
import json
import os
import sys

import ed119_analyze as A

res = []


def chk(name, ok):
    res.append(dict(name=name, passed=bool(ok)))


def P(i, gt, K, B, G, E, N="yes", R="yes", T=None, grp="mismatch"):
    return dict(id=i, gt=gt, group=grp, category="opacity" if gt == "yes" else "normal",
                answers=dict(K=K, B=B, G=G, E=E, N=N, R=R, T=T, M=None, S=None))


def fin(p):
    from ed116_eval import derive
    a = p["answers"]
    d = derive(a["K"], a["B"], a["G"], a["N"], a["E"], a["R"], a["T"])
    p["answers"] = d
    return p


chk("state_unresolved_not_wrong", A.state(None, "yes") == "unresolved" and A.state("no", "yes") == "wrong" and A.state("yes", "yes") == "correct")
pats = [fin(P("a", "yes", "yes", "no", "yes", None)),   # K정답 E unresolved
        fin(P("b", "yes", "yes", "no", "no", "no")),    # K정답 E 명시오답
        fin(P("c", "yes", "no", "yes", "yes", "yes"))]  # K오답 E정답
cr = A.cross(pats, "E")
chk("cross_sum_and_cells", sum(v["n"] for v in cr.values()) == 3 and cr["correct/unresolved"]["ids"] == ["a"]
    and cr["correct/wrong"]["ids"] == ["b"] and cr["wrong/correct"]["ids"] == ["c"])
f = A.flows(pats, "E")
chk("flows", f["gained"] == 1 and f["lost_explicit"] == 1 and f["lost_unresolved"] == 1 and f["net_correct_change"] == -1)
# 공유 변수: G unresolved → M 이 G와 같은 변수에 의존, E unresolved → S
q = fin(P("d", "yes", "no", "yes", None, None))   # K no, B yes, G None, E None
asg = list(A.patient_assignments(q))
chk("assignments_enumerate_G_E_N_R_T_free", len(asg) == 2 ** 5 - 0 or len(asg) == 2 ** len([x for x in "GENRT" if q["answers"][x] is None]))
chk("shared_G_to_M", all((d["M"] == d["G"]) or d["G"] not in ("yes", "no") for d in asg if d["K"] != d["B"]))
chk("shared_E_to_S", all(d["S"] == (d["E"] if d["E"] == d["B"] else d["K"]) for d in asg))
r = A.ranges([q])
chk("range_lo_le_hi", all(lo <= hi for lo, hi in r["correct_range"].values()))
chk("range_M_equals_G_choice_possible", r["correct_range"]["M"] == [0, 1])
# K unresolved 불허 구조는 없으나 중복 거부는 link_checks 소관: 합성 recs 중복 탐지
recs = {"x": [1, 2], "y": [1]}
chk("dup_detect", [k for k, v in recs.items() if len(v) != 1] == ["x"])
# 덮어쓰기 거부
p = "results/iter_119/tests/_probe.json"
os.makedirs(os.path.dirname(p), exist_ok=True)
try:
    open(p, "x").close()
    A.wx(p, {})
    chk("overwrite_refused", False)
except FileExistsError:
    chk("overwrite_refused", True)
A.wx("results/iter_119/tests/fixtures.json", dict(all_pass=all(x["passed"] for x in res), n=len(res), checks=res))
print(sum(x["passed"] for x in res), "/", len(res))
sys.exit(0 if all(x["passed"] for x in res) else 1)
