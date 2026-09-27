"""iter_017 CPU 회귀 검사. 사용: python test_rsna_iter017.py results/iter_017/tests/fixtures_iter017.json"""
import hashlib
import json
import os
import sys
import tempfile

from rsna_diag import ev17_spec as V, qa_eval, qa_gen, qa_protocol, qa_requests as Q, qa_run, qa_spec as S

RES = []


def check(name, cond, detail=""):
    RES.append({"name": name, "pass": bool(cond), "detail": str(detail)[:300]})


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return True, str(e)[:120]
    return False, ""


B1 = [[10, 20, 30, 40]]
B2 = [[10, 20, 30, 40], [50, 60, 70, 80]]

# --- packet 표 (계획 §1)
for cond in V.ALL_CONDS:
    p = V.packet(cond, "valid_empty", [])
    check(f"empty:{cond}", p == ({"detection": V.NP, "count": V.NP, "boxes": V.NP} if cond == "U" else {"detection": "none", "count": 0, "boxes": []}), p)
    p = V.packet(cond, "other", None)
    check(f"invalid:{cond}", p == {"detection": V.NP, "count": V.NP, "boxes": V.NP}, p)
check("nonempty:U", V.packet("U", "valid_nonempty", B2) == {"detection": V.NP, "count": V.NP, "boxes": V.NP})
check("nonempty:B", V.packet("B", "valid_nonempty", B2) == {"detection": "present", "count": V.NP, "boxes": V.NP})
check("nonempty:K", V.packet("K", "valid_nonempty", B2) == {"detection": "present", "count": 2, "boxes": V.NP})
check("nonempty:L", V.packet("L", "valid_nonempty", B2)["boxes"] == [{"box_2d": b} for b in B2])
check("packet key order", list(V.packet("L", "valid_nonempty", B1)) == ["detection", "count", "boxes"])
# 빈 예측/invalid에서 B/K/L/X prompt 동일 (invalid는 U도 동일)
for t in S.TARGETS:
    pe = {c: V.prompt(t, c, "valid_empty", []) for c in V.ALL_CONDS}
    check(f"empty prompt B=K=L=X {t}", len({pe[c] for c in "BKLX"}) == 1 and pe["U"] != pe["B"])
    pi = {c: V.prompt(t, c, "other", None) for c in V.ALL_CONDS}
    check(f"invalid prompt all same {t}", len(set(pi.values())) == 1)
check("common text once", V.prompt("O", "L", "valid_nonempty", B1).count(V.COMMON) == 1)
check("old evidence text untouched", S.EVIDENCE_TEXT["unavailable"].startswith("No localization proposal"))
check("no GT/category token in prompt", all(w not in V.prompt("O", "L", "valid_nonempty", B1).lower() for w in ("normal image", "category", "ground truth", "annotation")))
try:
    V.packet("L", "valid_nonempty", [])
    check("nonempty without boxes rejected", False)
except ValueError:
    check("nonempty without boxes rejected", True)

# --- donor mapping
items = {f"p{i}": [[i, i, i + 1, i + 1]] for i in range(7)}
items.update({f"q{i}": [[i, 0, i + 1, 1], [0, i, 1, i + 1]] for i in range(4)})
items["solo"] = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
m = V.donor_map(items)
check("donor same k", all(len(items[v["donor"]]) == v["k"] == len(items[i]) for i, v in m.items()))
check("donor not self (group>1)", all(v["donor"] != i for i, v in m.items() if v["group_n"] > 1))
check("donor is permutation per group", all(sorted(d["donor"] for i, d in m.items() if d["k"] == k) == sorted(i for i in m if m[i]["k"] == k) for k in (1, 2, 3)))
check("singleton group keeps self (recorded)", m["solo"]["donor"] == "solo" and m["solo"]["same_coords"] and m["solo"]["group_n"] == 1)
check("mapping deterministic", V.donor_map(items) == m)
check("mapping independent of dict order", V.donor_map(dict(reversed(list(items.items())))) == m)

# --- completion 내용 검증 (존재만으로 완료 아님)
with tempfile.TemporaryDirectory() as td:
    rp = os.path.join(td, "req.jsonl")
    open(rp, "w").write("x\n")
    rows = [{"adapter_digest": None}] * 2
    good = {"protocol_digest": "P", "n_expected": 2, "n_actual_unique": 2, "n_missing": 0, "n_duplicate": 0, "n_extra": 0, "returncodes": [0, 0],
            "requests_sha256": hashlib.sha256(b"x\n").hexdigest(), "adapter_digest": None, "config_digest": "C", "verify_error": None}

    def run(c):
        json.dump(c, open(os.path.join(td, "completion.json"), "w"))
        return qa_run.verify_completion(td, rows, "C", "P", rp, 2)

    check("completion good", run(good)["n_expected"] == 2)
    for k, v in (("returncodes", [0, 1]), ("returncodes", []), ("n_missing", 1), ("n_extra", 1), ("n_duplicate", 1), ("n_expected", 3),
                 ("n_actual_unique", 1), ("protocol_digest", "Q"), ("requests_sha256", "0"), ("config_digest", "X"), ("verify_error", "boom"),
                 ("adapter_digest", "a")):
        ok, msg = raises(lambda: run(dict(good, **{k: v})), qa_gen.QAError)
        check(f"completion rejects bad {k}={v}", ok, msg)
    d = dict(good)
    d.pop("returncodes")
    check("completion rejects missing returncodes", raises(lambda: run(d), qa_gen.QAError)[0])
    check("completion.json '{}' rejected", raises(lambda: run({}), qa_gen.QAError)[0])

# --- bbox 출처: pin, completion 내용, 중복/충돌
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "b.jsonl")
    recs = [{"id": f"a{i}", "checkpoint": "B0", "condition": "bbox", "suffix_text_raw": "[]", "ended_eos": True} for i in range(3)]
    open(p, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
    sha = Q._file_sha(p)
    check("pinned ok", len(Q.bbox_records("B0", [("reuse", p)], {p: sha})) == 3)
    check("changed source rejected", raises(lambda: Q.bbox_records("B0", [("reuse", p)], {p: "0" * 64}), Q.RequestError)[0])
    check("unpinned source rejected", raises(lambda: Q.bbox_records("B0", [("reuse", p)], {"other": sha}), Q.RequestError)[0])
    open(p, "a").write(json.dumps(recs[0]) + "\n")
    check("duplicate record rejected", raises(lambda: Q.bbox_records("B0", [("reuse", p)], {p: Q._file_sha(p)}), Q.RequestError)[0])
    g = os.path.join(td, "gen")
    os.makedirs(g)
    check("gen without completion rejected", raises(lambda: Q.bbox_records("B0", [("gen", g)], {"x": "y"}), Q.RequestError)[0])
    for bad in ({}, {"n_missing": 1, "n_duplicate": 0, "n_extra": 0, "n_expected": 1, "n_actual_unique": 0, "returncodes": [0]},
                {"n_missing": 0, "n_duplicate": 0, "n_extra": 0, "n_expected": 1, "n_actual_unique": 1, "returncodes": [1]}):
        json.dump(bad, open(f"{g}/completion.json", "w"))
        check(f"gen bad completion rejected {sorted(bad)[:2]}", raises(lambda: Q.bbox_records("B0", [("gen", g)], {"x": "y"}), Q.RequestError)[0])

# --- protocol: 파일명 우회 제거·명시적 허용만
with tempfile.TemporaryDirectory() as td:
    pp = os.path.join(td, "prot.json")
    qa_protocol.create(pp, [], "test")
    d0 = qa_protocol.verify(pp)
    check("protocol verifies now", isinstance(d0, str))
    check("no ALLOW_CHANGED symbol in qa_eval", not hasattr(qa_eval, "ALLOW_CHANGED") and qa_eval.ALLOWED_EDITS == {})
    js = json.load(open(pp))
    f = "rsna_diag/qa_eval.py"
    cur = js["locked"]["files"][f]
    js["locked"]["files"][f] = "0" * 64      # 잠금 이후 이 파일이 바뀐 상황
    json.dump(js, open(pp, "w"))
    check("changed file rejected without allow", raises(lambda: qa_protocol.verify(pp), RuntimeError)[0])
    check("filename-only allow is not accepted (tuple arg)", raises(lambda: qa_protocol.verify(pp, (f,)), Exception)[0])
    check("allow with wrong after-hash rejected", raises(lambda: qa_protocol.verify(pp, {f: {"before": "0" * 64, "after": "1" * 64, "reason": "r"}}), RuntimeError)[0])
    check("allow with wrong before-hash rejected", raises(lambda: qa_protocol.verify(pp, {f: {"before": "1" * 64, "after": cur, "reason": "r"}}), RuntimeError)[0])
    check("allow without reason rejected", raises(lambda: qa_protocol.verify(pp, {f: {"before": "0" * 64, "after": cur}}), RuntimeError)[0])
    check("exact before/after/reason accepted", qa_protocol.verify(pp, {f: {"before": "0" * 64, "after": cur, "reason": "test"}}) is not None)
    js["locked"]["files"][f] = cur
    js["locked"]["files"].pop("rsna_diag/ev17_analysis.py")
    json.dump(js, open(pp, "w"))
    check("protocol missing required analysis file rejected", raises(lambda: qa_protocol.verify(pp), RuntimeError)[0])

# --- request row 변조 감지·direct 재사용
row = json.loads(open("results/iter_017/requests/d12_ev17__M0.jsonl").readline())
cfg = row["config_digest"]
check("request row verifies", Q.verify_row(row, cfg))
for k, v in (("prompt", "changed"), ("adapter_digest", "abc"), ("file_sha256", "0" * 64), ("pixel_sha256", "0" * 64)):
    bad = dict(row, **{k: v})
    check(f"row tamper {k}", raises(lambda: Q.verify_row(bad, cfg), Q.RequestError)[0])
rows = [json.loads(ln) for ln in open("results/iter_017/requests/d12_ev17__M0.jsonl")]
check("D12 96 rows unique ids", len(rows) == 96 and len({r["request_id"] for r in rows}) == 96)
check("D12 rows carry no category/GT", all("category" not in r and "gt" not in json.dumps(r).lower() for r in rows))
by = {}
for r in rows:
    by.setdefault((r["id"], r["target"]), {})[r["condition"]] = r
emp = [k for k, v in by.items() if v["ev17_L"]["extra"]["source_status"] == "valid_empty"]
check("D12 empty: B/K/L prompt identical", all(len({by[k][c]["prompt"] for c in ("ev17_B", "ev17_K", "ev17_L")}) == 1 for k in emp) and len(emp) > 0)
check("D12 empty: U differs from B", all(by[k]["ev17_U"]["prompt"] != by[k]["ev17_B"]["prompt"] for k in emp))

n_pass = sum(r["pass"] for r in RES)
out = {"n": len(RES), "passed": n_pass, "results": RES}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(f"{n_pass}/{len(RES)} passed")
for r in RES:
    if not r["pass"]:
        print("FAIL", r["name"], r["detail"])
sys.exit(0 if n_pass == len(RES) else 1)
