"""CPU checks for iter_004 (no GPU, no model).

실행: python research/test_qes.py --out research/results/iter_004
합성 이미지는 --out/cpu_test/ 아래에 만든다.
"""
import argparse
import copy
import inspect
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_qes  # noqa: E402  (import-time GPU 부작용이 없어야 한다)
from qes import data as D  # noqa: E402
from qes import evaluation as E  # noqa: E402
from qes import selection as S  # noqa: E402
from qes import store as ST  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": str(detail)})
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)


def fake_preds(reqs, chash, seed=0):
    rng = np.random.default_rng(seed)
    return [{"id": r["id"], "status": "ok", "m": float(rng.normal()), "m_fp32head": 0.0,
             "lp_yes": -1.0, "lp_no": -1.0, "p_yes_plus_no": 0.9, "top1_token": "Yes", "n_tokens": 300,
             "n_image_tokens": 1, "pixel_values_shape": [1, 3, 896, 896], "prompt_intact": True,
             "request_sha256": r["request_sha256"], "config_sha256": chash,
             "input_pixel_sha256": r["input_pixel_sha256"], "scorer_version": D.SCORER_VERSION} for r in reqs]


def make_synth(dirpath, n=2, seed=0):
    os.makedirs(dirpath, exist_ok=True)
    rng = np.random.default_rng(seed)
    for i in range(n):
        a = rng.integers(0, 256, size=(61 + i, 47 + i), dtype=np.uint8)
        Image.fromarray(a, mode="L").save(os.path.join(dirpath, f"s{i}.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tdir = os.path.join(args.out, "cpu_test")
    sdir = os.path.join(tdir, "synth")
    make_synth(sdir)

    check("no torch import at module import", "torch" not in sys.modules, sorted(k for k in sys.modules if k.startswith("torch"))[:3])

    cfg = D.build_config()
    chash = D.config_hash(cfg)
    reqs, info = D.build_requests(data_dir=sdir, cfg=cfg)
    check("request count synth", len(reqs) == 2 * 6 * 28, len(reqs))
    preds = fake_preds(reqs, chash)
    v = ST.validate_predictions(reqs, preds, chash, D.SCORER_VERSION)
    check("valid cache accepted", v["status"] == "complete" and len(v["valid"]) == len(reqs))

    # 1) 실제 이미지 변경 -> manifest 재생성 시 해당 이미지 결과 거부, runner input check도 실패
    p = os.path.join(sdir, "s1.png")
    a = np.array(Image.open(p))
    a2 = a.copy()
    a2[0, 0] = (int(a2[0, 0]) + 1) % 256
    Image.fromarray(a2, mode="L").save(p)
    reqs_mod, info_mod = D.build_requests(data_dir=sdir, cfg=cfg)
    v = ST.validate_predictions(reqs_mod, preds, chash, D.SCORER_VERSION)
    n_rej = sum(1 for x in v["rejected"] if x["reason"] == "request_hash_mismatch")
    check("image change -> cache rejected", n_rej == 6 * 28 and v["status"] == "incomplete", n_rej)
    cache = run_qes.InputCache(info, data_dir=sdir)
    r1 = [r for r in reqs if r["image"] == "s1.png"][0]
    try:
        cache.get(r1)
        ok = False
    except RuntimeError as e:
        ok = "hash changed" in str(e)
    check("runner detects changed source file", ok)
    Image.fromarray(a, mode="L").save(p)
    reqs_back, _ = D.build_requests(data_dir=sdir, cfg=cfg)
    check("restored image -> same requests", [r["request_sha256"] for r in reqs_back] == [r["request_sha256"] for r in reqs])
    img, h = run_qes.InputCache(info, data_dir=sdir).get(r1)
    check("runner input hash matches manifest", h == r1["input_pixel_sha256"])

    # 2) config 변경
    cfg2 = copy.deepcopy(cfg)
    cfg2["blur"]["radius_frac_of_min_side"] = 0.06
    reqs_c, _ = D.build_requests(data_dir=sdir, cfg=cfg2)
    v = ST.validate_predictions(reqs_c, preds, D.config_hash(cfg2), D.SCORER_VERSION)
    check("config change -> all rejected", len(v["valid"]) == 0 and len(v["missing"]) == len(reqs_c))

    # 3) 요청 변경 (prompt)
    reqs_p = copy.deepcopy(reqs)
    reqs_p[0]["prompt"] = reqs_p[0]["prompt"] + " "
    reqs_p[0]["request_sha256"] = D.sha256_json({k: v_ for k, v_ in reqs_p[0].items() if k != "request_sha256"})
    v = ST.validate_predictions(reqs_p, preds, chash, D.SCORER_VERSION)
    check("request change -> that result rejected", v["missing"] == [reqs_p[0]["id"]])

    # scorer version 변경
    v = ST.validate_predictions(reqs, preds, chash, "other")
    check("scorer version change -> rejected", len(v["valid"]) == 0)

    # 4) conflicting duplicate / consistent duplicate
    dup = dict(preds[3])
    dup["m"] += 0.5
    v = ST.validate_predictions(reqs, preds + [dup], chash, D.SCORER_VERSION)
    check("conflicting duplicate -> not adopted, incomplete",
          v["status"] == "incomplete" and preds[3]["id"] not in v["valid"] and len(v["conflicts"]) == 1)
    v = ST.validate_predictions(reqs, preds + [dict(preds[3])], chash, D.SCORER_VERSION)
    check("consistent duplicate -> ok", v["status"] == "complete" and v["duplicates_consistent"] == 1)

    # 5) 누락/오류 결과
    err = dict(preds[5])
    err["status"] = "error"
    v = ST.validate_predictions(reqs, preds[:5] + [err] + preds[6:], chash, D.SCORER_VERSION)
    check("missing/error -> incomplete", v["status"] == "incomplete" and v["missing"] == [preds[5]["id"]])

    # 6) queue 축소가 실제 실행 목록을 바꾸는지
    done = {preds[0]["id"]}
    allowed = [r["id"] for r in reqs[:10]]
    q = ST.plan_queue(reqs, done, allowed_ids=allowed, limit=4)
    executed = []
    for r in q:  # runner와 같은 순회 방식
        executed.append(r["id"])
    check("explicit queue filter respected", executed == allowed[1:5], executed)
    q_full = ST.plan_queue(reqs, done)
    check("unfiltered queue", len(q_full) == len(reqs) - 1)

    # 7) Ledger: 비정상 종료 세션 보수 계상
    lp = os.path.join(tdir, "budget_test.json")
    L = ST.Ledger(lp)
    L.start("t")
    L.mark_inflight("x")  # close하지 않고 버림 (강제 종료 모사)
    L2 = ST.Ledger(lp)
    check("unclosed session penalized",
          L2.data["sessions"][-1]["closed_by"] == "recovered_unclosed" and L2.total_minutes() >= ST.UNCOUNTED_SESSION_PENALTY_MIN)
    L2.start("t2")
    L2.close("normal")
    L3 = ST.Ledger(lp)
    check("closed session not penalized again", sum(s.get("uncounted_penalty_min", 0) for s in L3.data["sessions"]) == ST.UNCOUNTED_SESSION_PENALTY_MIN)
    ST.write_json_atomic(lp, {"sessions": [], "cap_minutes": None})

    # 8) GT 변경이 후보·선택에 영향 없음
    src_ok = all("meta.json" not in inspect.getsource(m) and "bounding" not in inspect.getsource(m)
                 for m in (D, S))
    check("data/selection modules never read annotations", src_ok)
    with open(os.path.join(sdir, "meta.json"), "w") as f:
        json.dump([{"file": "s0.png", "bounding_boxes_pixel_xyxy": [{"class_name": "Cardiomegaly", "x_min": 0, "y_min": 0, "x_max": 5, "y_max": 5}]}], f)
    ra, _ = D.build_requests(data_dir=sdir, cfg=cfg)
    sel_a = S.select_all(ra, {p_["id"]: p_ for p_ in fake_preds(ra, chash)})
    with open(os.path.join(sdir, "meta.json"), "w") as f:
        json.dump([{"file": "s1.png", "bounding_boxes_pixel_xyxy": [{"class_name": "Atelectasis", "x_min": 9, "y_min": 9, "x_max": 30, "y_max": 30}]}], f)
    rb, _ = D.build_requests(data_dir=sdir, cfg=cfg)
    sel_b = S.select_all(rb, {p_["id"]: p_ for p_ in fake_preds(rb, chash)})
    check("GT change -> identical requests and selections",
          [r["request_sha256"] for r in ra] == [r["request_sha256"] for r in rb] and sel_a == sel_b)

    # 9) 입력 변형 정확성: blur/mean은 tile 밖 pixel 불변, crop 크기 = tile
    ii = D.ImageInputs(os.path.join(sdir, "s0.png"))
    t = 4
    x0, y0, x1, y1 = ii.tiles[t]
    o = np.asarray(ii.orig)
    for kind in ("blur", "mean"):
        z = np.asarray(ii.make(kind, t))
        mask = np.ones(o.shape[:2], bool)
        mask[y0:y1, x0:x1] = False
        check(f"{kind}: outside tile unchanged", np.array_equal(z[mask], o[mask]))
    check("mean fill value", np.all(np.asarray(ii.make("mean", t))[y0:y1, x0:x1] == np.array(ii.means)))
    check("crop size", ii.make("crop", t).size == (x1 - x0, y1 - y0))
    tb = D.tile_boxes(10, 10)
    check("tile bounds rule", [b[0] for b in tb[:3]] == [0, 3, 7] and tb[8] == (7, 7, 10, 10), tb[:3])
    check("tiles partition image", sum((b[2] - b[0]) * (b[3] - b[1]) for b in D.tile_boxes(2144, 2561)) == 2144 * 2561)

    # 10) C 대수: C(q) = attribution of F_q = m_q - mean_{q'!=q} m_q', sum_q C = 0, tie rule
    rng = np.random.default_rng(1)
    tab = {q: {"orig": float(rng.normal()), "blur": list(rng.normal(size=9))} for q in D.FINDINGS}
    Dd, Cc = S.removal_scores(tab, "blur")
    q0 = D.FINDINGS[0]
    F = lambda get: get(q0) - np.mean([get(q) for q in D.FINDINGS if q != q0], axis=0)
    attr = F(lambda q: tab[q]["orig"]) - F(lambda q: np.array(tab[q]["blur"]))
    check("C equals contrastive-score occlusion attribution", np.allclose(attr, Cc[q0]))
    check("sum_q C = 0", np.allclose(sum(Cc[q] for q in D.FINDINGS), 0))
    check("tie -> smallest tile id", S.argmax_tie_low([1, 3, 3, 0]) == (1, 2))

    # 11) bbox union / metric 수작업 예제 (9x9 영상, tile 3x3 pixel)
    g = E.GeomImage(9, 9, {"A": [(0, 0, 3, 3), (3, 0, 6, 3)], "B": [(0, 0, 3, 3), (1, 1, 3, 3)],
                           "C": [(6, 6, 9, 9)]})
    sa = g.stats["A"]
    check("union of disjoint boxes", sa["area_g"] == 18 and abs(sa["iou"][0] - 0.5) < 1e-12 and abs(sa["U"][1] - 1) < 1e-12
          and abs(sa["cov"][0] - 0.5) < 1e-12 and sa["best_tile"] == 0, (sa["area_g"], sa["iou"][:2]))
    check("union of overlapping boxes", g.stats["B"]["area_g"] == 9 and g.stats["B"]["iou"][0] == 1.0)
    check("region IoU", abs(g.region_iou("A", "B") - 0.5) < 1e-12 and g.region_iou("A", "C") == 0)
    geo = {"i1.png": g}
    sel_good = {"i1.png": {q: {"X": 0 if q != "C" else 8} for q in ("A", "B", "C")}}
    ps = E.pair_scores(sel_good, geo, [{"image": "i1.png", "a": "A", "b": "C", "distinct": True}], ["X"])
    check("pair S correct = 1", abs(ps["X"]["distinct"]["macro_S"] - 1.0) < 1e-12)
    sel_bad = {"i1.png": {q: {"X": 8 if q != "C" else 0} for q in ("A", "B", "C")}}
    ps = E.pair_scores(sel_bad, geo, [{"image": "i1.png", "a": "A", "b": "C", "distinct": True}], ["X"])
    check("pair S swapped = -1", abs(ps["X"]["distinct"]["macro_S"] + 1.0) < 1e-12)
    sel_same = {"i1.png": {q: {"X": 0} for q in ("A", "B", "C")}}
    ps = E.pair_scores(sel_same, geo, [{"image": "i1.png", "a": "A", "b": "C", "distinct": True}], ["X"])
    check("pair S same tile = 0", ps["X"]["distinct"]["macro_S"] == 0)

    # image swap / question swap / uniform / macro 예제 (FINDINGS 이름 사용)
    f1, f2 = D.FINDINGS[0], D.FINDINGS[1]
    gA = E.GeomImage(9, 9, {f1: [(0, 0, 3, 3)], f2: [(6, 6, 9, 9)]})
    gB = E.GeomImage(9, 9, {f1: [(0, 0, 3, 3)], f2: [(6, 6, 9, 9)]})
    geo2 = {"a.png": gA, "b.png": gB}
    sel2 = {"a.png": {q: {"X": 0 if q == f1 else 8} for q in D.FINDINGS},
            "b.png": {q: {"X": 4} for q in D.FINDINGS}}
    ev = E.evaluate(sel2, geo2, ["X"])
    rows = {(r["image"], r["finding"]): r for r in ev["per_combo"]}
    check("self U", rows[("a.png", f1)]["X"]["U"] == 1 and rows[("b.png", f1)]["X"]["U"] == 0)
    check("image swap U", rows[("a.png", f1)]["X"]["image_swap"]["U"] == 0 and rows[("b.png", f1)]["X"]["image_swap"]["U"] == 1)
    check("question swap U", rows[("a.png", f1)]["X"]["question_swap"]["U"] == 0 and rows[("a.png", f2)]["X"]["question_swap"]["U"] == 0)
    check("uniform expectation", abs(rows[("a.png", f1)]["uniform"]["U"] - 1 / 9) < 1e-12)
    check("macro within image then images", abs(ev["methods"]["X"]["U"]["macro"] - (1.0 + 0.0) / 2) < 1e-12)
    check("location prior leaves image out", rows[("a.png", f1)]["location_prior"]["tile"] == 0
          and rows[("a.png", f1)]["location_prior"]["U"] == 1)

    # 12) 실제 VinDr geometry: 사전 등록 층 (20 조합/9 영상, distinct 13쌍/6 영상)
    geo_real = E.build_geometry(E.load_annotations())
    combos = E.positive_combos(geo_real)
    pairs = E.classify_pairs(geo_real)
    dist = [p_ for p_ in pairs if p_["distinct"]]
    check("VinDr positives 20/9", len(combos) == 20 and len({c[0] for c in combos}) == 9)
    check("VinDr distinct pairs 13/6", len(dist) == 13 and len({p_["image"] for p_ in dist}) == 6)

    n_fail = sum(not r["pass"] for r in RESULTS)
    ST.write_json_atomic(os.path.join(args.out, "cpu_tests.json"), {"n": len(RESULTS), "n_fail": n_fail, "results": RESULTS})
    print(f"CPU tests: {len(RESULTS) - n_fail}/{len(RESULTS)} pass")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
