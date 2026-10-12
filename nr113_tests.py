"""iter_113 fixture 검사 (합성 사례 + 실제 입력 변조 거부). 결과: results/iter_113/tests/fixtures.json"""
import copy
import itertools
import json
import random
import shutil
import tempfile
from pathlib import Path

import nr107_geom as G
import nr107_spec as S
import nr113_core as C
import nr113_run as RUN

res = {}


def check(name, cond):
    res[name] = bool(cond)


def close(a, b, t=1e-12):
    return abs(a - b) < t


# --- 기하: 정확한 면적
A = [0, 0, .5, .5]
check("iou_identical", close(G.union_iou([A], [A]), 1.0))
check("iou_disjoint", close(G.union_iou([A], [[.6, .6, .9, .9]]), 0.0))
check("iou_partial", close(G.union_iou([A], [[.25, 0, .75, .5]]), 0.125 / 0.375))
check("iou_duplicate_boxes", close(G.union_iou([A, A], [A]), 1.0))
check("iou_nonsquare_union_exact", close(G.union_area([[0, 0, .5, .2], [.25, 0, .75, .2]]), .75 * .2))
check("empty_pred_iou0", G.union_iou([], [A]) == 0.0)
check("risk_d_both_empty", C.risk_d([], []) == 0.0)
check("risk_d_one_empty", C.risk_d([A], []) == 1.0 and C.risk_d([], [A]) == 1.0)
check("risk_b_empty_is_1", C.risk_b([]) == 1.0 and close(C.risk_b([.9, .8]), .2))
check("error_empty_M", C.is_error([], [A]) == 1 and C.is_error([A], [A]) == 0 and C.is_error([[.9, .9, 1, 1]], [A]) == 1)
check("error_threshold_boundary", C.is_error([[0, 0, .5, .3]], [[0, 0, .5, 1.0]]) == 0 and C.is_error([[0, 0, .5, .29]], [[0, 0, .5, 1.0]]) == 1)
# --- 좌표 경계
check("box_ok", C.box_ok([0, 0, 1, 1]) and not C.box_ok([0, 0, 0, 1]) and not C.box_ok([float("nan"), 0, 1, 1]) and not C.box_ok([0, 0, 1.01, 1]) and not C.box_ok([0, 0, 1]) and not C.box_ok([-.1, 0, .5, .5]))
# --- CURE parser
check("parse_valid", S.parse_pg("x: [0.5,0.5,0.2,0.2]", True)["status"] == "valid_nonempty")
check("parse_truncated", S.parse_pg("x: [0.5,0.5,0.2,0.2]", False)["status"] == "truncated")
check("parse_malformed_3", S.parse_pg("[0.5,0.5,0.2]", True)["status"] == "malformed")
check("parse_nan", S.parse_pg("[nan,0.5,0.2,0.2]", True)["status"] == "coord_invalid")
check("parse_out_of_range", S.parse_pg("[0.95,0.5,0.2,0.2]", True)["status"] == "coord_invalid")
check("parse_no_box", S.parse_pg("no finding", True)["status"] == "no_box")
check("parse_unbalanced", S.parse_pg("[0.5,0.5,0.2,0.2] [", True)["status"] == "malformed")
# --- MG 결함
check("mg_scores_len", C.mg_defects({"boxes_orig_xyxy": [A, A], "scores": [.9]}) == ["mg_scores_length"])
check("mg_below_thr", C.mg_defects({"boxes_orig_xyxy": [A], "scores": [.5]}) == ["mg_score_below_thr"])
check("mg_ok", C.mg_defects({"boxes_orig_xyxy": [A], "scores": [.8]}) == [] and C.mg_defects({"boxes_orig_xyxy": [], "scores": []}) == [])
# --- 순위·K
check("k_of", [C.k_of(n) for n in (1, 4, 5, 47, 36)] == [1, 1, 2, 12, 9])
check("min_gain", -(-5 * 47 // 100) == 3)


def ent(i, D, B, e, p=None):
    return {"item_key": f"k{i}", "patient": p or f"p{i}", "tk": C.tie_key(f"k{i}"), "D": D, "B": B, "e": e}


# GT(e) 와 무관한 동률 처리: e 를 뒤집어도 선택 집합 동일
E1 = [ent(i, 1.0, 1.0, i % 2) for i in range(8)]
E2 = [dict(x, e=1 - x["e"]) for x in E1]
check("tie_break_independent_of_gt", C.select(E1, "D")[0] == C.select(E2, "D")[0] and C.select(E1, "B")[0] == C.select(E2, "B")[0])
check("tie_hash_deterministic", C.tie_key("a") == C.tie_key("a") and C.tie_key("a") != C.tie_key("b") and C.tie_key("a", 1) > C.tie_key("a", 0))
# --- 경계 동률 범위·미확정 공유 배정: 전수 brute force 와 대조 (무작위 소규모)
rng = random.Random(7)
ok_bounds = True
ok_side = True
for trial in range(300):
    n = rng.randint(4, 9)
    ents = [ent(i, rng.choice([0.0, 0.5, 1.0]), rng.choice([0.0, 0.5, 1.0]), rng.randint(0, 1)) for i in range(n)]
    und = [rng.random() < .4 for _ in range(n)]
    K = C.k_of(n)

    def sets(f):
        vals = sorted((x[f] for x in ents), reverse=True)
        rk = vals[K - 1]
        forced = [i for i, x in enumerate(ents) if x[f] > rk]
        tied = [i for i, x in enumerate(ents) if x[f] == rk]
        return [set(forced) | set(c) for c in itertools.combinations(tied, K - len(forced))]
    SD, SB = sets("D"), sets("B")

    def brute(sdl, sbl, free_mask):
        vals = []
        fr = [i for i in range(n) if free_mask[i]]
        for sd in sdl:
            for sb in sbl:
                for bits in itertools.product((0, 1), repeat=len(fr)):
                    e = [x["e"] for x in ents]
                    for i, b in zip(fr, bits):
                        e[i] = b
                    vals.append(sum(e[i] * ((i in sd) - (i in sb)) for i in range(n)))
        return (min(vals), max(vals))
    b = C.bounds(ents, und)
    sd0, _ = C.select(ents, "D")
    sb0, _ = C.select(ents, "B")
    ok_bounds &= tuple(b["tie_only"]) == brute(SD, SB, [False] * n)
    ok_bounds &= tuple(b["tie_and_annot"]) == brute(SD, SB, und)
    ok_bounds &= tuple(b["annot_only"]) == brute([sd0], [sb0], und)
    cD = [sum(ents[i]["e"] for i in s) for s in SD]
    cB = [sum(ents[i]["e"] for i in s) for s in SB]
    ok_side &= tuple(b["D_capture_tie_range"]) == (min(cD), max(cD)) and tuple(b["B_capture_tie_range"]) == (min(cB), max(cB))
check("bounds_vs_bruteforce_300", ok_bounds)
check("side_ranges_vs_bruteforce_300", ok_side)
# --- bootstrap 환자 복제: 같은 환자 두 번 뽑히면 항목이 복제되고 N_b 가 변한다
P = [ent(0, .9, .1, 1, "pA"), ent(1, .8, .2, 0, "pA"), ent(2, .1, .9, 1, "pB")]
diffs = C.bootstrap(P, n_boot=50, seed=3)
check("bootstrap_deterministic", diffs == C.bootstrap(P, n_boot=50, seed=3) and len(diffs) == 50)
check("loo_recomputes_K", C.leave_one_patient_out(P)["pA"]["N"] == 1 and C.leave_one_patient_out(P)["pA"]["K"] == 1 and C.leave_one_patient_out(P)["pB"]["K"] == 1)
# --- 주석 모호성 분류
check("annot_status", [C.annot_status(1, 1), C.annot_status(0, 0), C.annot_status(1, 0), C.annot_status(0, None)] == ["confirmed_error", "confirmed_ok", "undetermined_disagree", "undetermined_no_alt"])
# --- 실제 입력 변조 거부 (복사본)
tmp = Path(tempfile.mkdtemp())
try:
    def clone(sub):
        dst = tmp / sub
        dst.mkdir()
        P2 = dict(RUN.PATHS)
        for k in ("items", "cohort", "raw_manifest", "cure_completion", "mg_completion", "selection", "manifest_private"):
            shutil.copy(RUN.PATHS[k], dst / RUN.PATHS[k].name) if RUN.PATHS[k].name not in {p.name for p in dst.iterdir()} else None
            P2[k] = dst / RUN.PATHS[k].name
        # name collision: both completion.json -> store separately
        (dst / "cure").mkdir(); (dst / "mg").mkdir()
        shutil.copy(RUN.PATHS["cure_completion"], dst / "cure_completion.json"); P2["cure_completion"] = dst / "cure_completion.json"
        shutil.copy(RUN.PATHS["mg_completion"], dst / "mg_completion.json"); P2["mg_completion"] = dst / "mg_completion.json"
        shutil.copytree(RUN.PATHS["cure_dir"], dst / "cure", dirs_exist_ok=True); P2["cure_dir"] = dst / "cure"
        for fn in ("raw_worker0.jsonl", "raw_worker1.jsonl"):
            shutil.copy(RUN.PATHS["mg_dir"] / fn, dst / "mg" / fn)
        P2["mg_dir"] = dst / "mg"
        return P2

    P0 = clone("ok")
    led, excl, g = C.link(P0)
    check("real_link_clean_copy", len(led) + len(excl) == 47)

    def expect_fail(sub, mutate):
        P2 = clone(sub)
        mutate(P2)
        try:
            C.link(P2)
            return False
        except C.LinkError:
            return True
    check("tamper_cure_output_rejected", expect_fail("t1", lambda p: (p["cure_dir"] / "shard0" / "outputs.jsonl").write_text((p["cure_dir"] / "shard0" / "outputs.jsonl").read_text() + "\n")))

    def dup_line(p):
        f = p["mg_dir"] / "raw_worker0.jsonl"
        f.write_text(f.read_text() + f.read_text().splitlines()[0] + "\n")
    check("tamper_mg_duplicate_rejected", expect_fail("t2", dup_line))

    def items_mut(p):
        it = json.load(open(p["items"]))
        it[0]["sentence"] = "changed"
        json.dump(it, open(p["items"], "w"))
    check("tamper_items_rejected", expect_fail("t3", items_mut))
    # 연결 결함 항목은 제외 사유가 남고 조용히 통과하지 않는다: items 의 mg_request_id 교체 + cohort hash 갱신
    P3 = clone("t4")
    it = json.load(open(P3["items"]))
    it[0]["mg_request_id"] = "deadbeef"
    json.dump(it, open(P3["items"], "w"))
    co = json.load(open(P3["cohort"]))
    co["items_sha256"] = C.sha256_file(P3["items"])
    json.dump(co, open(P3["cohort"], "w"))
    led3, ex3, _ = C.link(P3)
    check("missing_mg_record_excluded_with_reason", len(ex3) == 1 and ex3[0]["reason"] == ["mg_record_missing"] and len(led3) == 46)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

out = {"checks": res, "n": len(res), "n_pass": sum(res.values()), "all_pass": all(res.values())}
p = Path("results/iter_113/tests/fixtures.json")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in res.items() if not v}), out["n_pass"], "/", out["n"])
