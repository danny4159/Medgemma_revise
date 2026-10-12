"""iter_119 독립 검산: per_patient.json 의 answers/gt만 읽어 분석 모듈(ed119_*)·ed116 함수를 쓰지 않고 단순 반복문으로 재계산해 report/extra와 대조."""
import json

pp = json.load(open("results/iter_117/eval/per_patient.json"))
rep = json.load(open("results/iter_119/eval/report.json"))
ext = json.load(open("results/iter_119/eval/extra_tables.json"))
checks = []


def ck(name, ok):
    checks.append(dict(name=name, passed=bool(ok)))


def S(a, y):
    if a is None:
        return "u"
    return "c" if a == y else "w"


for g in ("mismatch", "control"):
    sub = [p for p in pp if p["group"] == g]
    ck(f"{g}_n87", len(sub) == 87)
    for q in "KBGEMNRST":
        c = w = u = 0
        for p in sub:
            s = S(p["answers"][q], p["gt"])
            c += s == "c"
            w += s == "w"
            u += s == "u"
        sc = rep["tables"][g]["state_counts"][q]
        ck(f"{g}_{q}_counts", (c, w, u) == (sc["correct"], sc["wrong"], sc["unresolved"]) and c + w + u == 87)
    for a in "BGEMSNR":
        cells = {}
        for p in sub:
            k = S(p["answers"]["K"], p["gt"]) + S(p["answers"][a], p["gt"])
            cells[k] = cells.get(k, 0) + 1
        names = {"c": "correct", "w": "wrong", "u": "unresolved"}
        got = {k: v["n"] for k, v in rep["tables"][g]["K_vs"][a].items() if v["n"]}
        mine = {names[k[0]] + "/" + names[k[1]]: v for k, v in cells.items()}
        ck(f"{g}_cross_K_{a}", got == mine and sum(mine.values()) == 87)
    # 정책 재도출 (M, S) from K,B,G,E 저장값
    ok = True
    for p in sub:
        a = p["answers"]
        votes = [a["K"], a["B"], a["G"]]
        m = a["K"] if a["G"] is None else max(votes, key=votes.count)
        s = a["E"] if (a["E"] is not None and a["E"] == a["B"]) else a["K"]
        ok = ok and m == a["M"] and s == a["S"]
    ck(f"{g}_M_S_rederived", ok)

mm = [p for p in pp if p["group"] == "mismatch"]
ck("user_check_Kc_Ewrong_2", sum(S(p["answers"]["K"], p["gt"]) == "c" and S(p["answers"]["E"], p["gt"]) == "w" for p in mm) == 2)
ck("user_check_Kw_Ec_8", sum(S(p["answers"]["K"], p["gt"]) == "w" and S(p["answers"]["E"], p["gt"]) == "c" for p in mm) == 8)
ck("user_check_Kc_Eu_24", sum(S(p["answers"]["K"], p["gt"]) == "c" and S(p["answers"]["E"], p["gt"]) == "u" for p in mm) == 24)
ck("orig_counts_K47_B40_G54_M54_E29_S53",
   [sum(p["answers"][q] == p["gt"] for p in mm) for q in "KBGMES"] == [47, 40, 54, 54, 29, 53])
# 범위: 전수 배정 독립 구현 (E 미해결 환자의 E∈{yes,no}에서 S, G 미해결에서 M)
lo = hi = 0
for p in mm:
    a = p["answers"]
    opts = ["yes", "no"] if a["E"] is None else [a["E"]]
    vals = [(1 if (e if e == a["B"] else a["K"]) == p["gt"] else 0) for e in opts]
    lo += min(vals)
    hi += max(vals)
ck("S_range_independent", [lo, hi] == rep["tables"]["mismatch"]["ranges"]["correct_range"]["S"])
# extra
u = [p for p in mm if p["answers"]["K"] == p["gt"] and all(p["answers"][q] != p["gt"] for q in "BGE")]
ck("draft_unique_ids", sorted(p["id"] for p in u) == sorted(ext["draft_unique"]["ids"]) and len(u) == 10)
ck("draft_unique_S9", sum(p["answers"]["S"] == p["gt"] for p in u) == ext["draft_unique"]["S_correct"] == 9)
kg = [p for p in mm if p["answers"]["K"] != p["answers"]["G"]]
ck("KG_disagree_33_13_20", len(kg) == 33 and sum(p["answers"]["K"] == p["gt"] for p in kg) == 13)
ck("KG_E_resolved_9", sum(p["answers"]["E"] is not None for p in kg) == 9)
ck("key_case_count", sum(1 for _ in json.load(open("results/iter_119/eval/key_cases.json"))) >= 34)
ck("cases174_unique", len({c["id"] for c in json.load(open("results/iter_119/eval/cases174.json"))}) == 174)
res = dict(all_pass=all(c["passed"] for c in checks), n=len(checks), n_pass=sum(c["passed"] for c in checks), checks=checks)
import ed119_analyze as A  # 쓰기 도우미만 사용
A.wx("results/iter_119/eval/verify.json", res)
print(res["n_pass"], "/", res["n"], [c["name"] for c in checks if not c["passed"]])
