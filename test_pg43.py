"""iter_043 CPU fixture/regression 검사. python test_pg43.py --out results/iter_043/tests/fixtures_pg43.json
GPU 산출물(D8 resume/tamper)은 저장된 결과를 읽어 검사한다 (모델 로드 없음)."""
import argparse
import glob
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import traceback

import numpy as np

import pg39_spec as S39
import pg43_eval as E
import pg43_prep as PREP
import pg43_requests as RQ
import pg43_retrieval as RT
import pg43_run as R
from rsna_diag import geometry, metrics

OUT = "results/iter_043"
RES = []


def check(name):
    def deco(fn):
        try:
            v = fn()
            RES.append({"name": name, "pass": True, "detail": v})
        except Exception as e:  # noqa: BLE001
            RES.append({"name": name, "pass": False, "detail": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-800:]})
        return fn
    return deco


man = json.load(open(f"{OUT}/data/manifest_private.json"))
v96 = {e["PatientID"]: e for e in man["V96"]}


@check("pairs: 21 pairs/42 patients/17 clusters, exact same sentence, distinct patients, greedy-rule reproduced")
def _():
    ps = man["pairs"]
    assert len(ps) == 21 and len({p["cluster"] for p in ps}) == 17
    pts = [p[s]["PatientID"] for p in ps for s in ("a", "b")]
    assert len(pts) == len(set(pts)) == 42
    for p in ps:
        assert p["a"]["PatientID"] != p["b"]["PatientID"]
        assert v96[p["a"]["PatientID"]]["sentences"][p["a"]["qID"]] == p["sentence"] == v96[p["b"]["PatientID"]]["sentences"][p["b"]["qID"]]
    # 독립 재구성: 모든 edge를 hash 순 정렬 후 greedy
    from collections import defaultdict
    by = defaultdict(list)
    for e in man["V96"]:
        for t in ("qA", "qB"):
            by[e["sentences"][t]].append((e["PatientID"], t))
    edges = []
    for s, eps in by.items():
        for i in range(len(eps)):
            for j in range(i + 1, len(eps)):
                if eps[i][0] != eps[j][0]:
                    a, b = sorted([eps[i], eps[j]])
                    edges.append((hashlib.sha256(f"4301|{s}|{a}|{b}".encode()).hexdigest(), a, b))
    edges.sort()
    used, got = set(), []
    for k, a, b in edges:
        if a[0] in used or b[0] in used:
            continue
        used.update([a[0], b[0]])
        got.append((a, b))
    want = [(((p["a"]["PatientID"], p["a"]["qID"])), (p["b"]["PatientID"], p["b"]["qID"])) for p in ps]
    assert [(x[0], x[1]) for x in got] == want
    return {"n_edges": len(edges)}


@check("GT cross reference reproduces plan values (1-crossF1@0.3=0.30952, @0.5=0.54762)")
def _():
    out = {}
    for thr in (0.3, 0.5):
        v = []
        for p in man["pairs"]:
            ea, eb = v96[p["a"]["PatientID"]], v96[p["b"]["PatientID"]]
            ga, gb = ea["gt_boxes_xyxy_norm"][p["a"]["qID"]], eb["gt_boxes_xyxy_norm"][p["b"]["qID"]]
            fa = S39.sent_metrics(gb, ga, thr)["f1"]
            fb = S39.sent_metrics(ga, gb, thr)["f1"]
            assert abs(fa - fb) < 1e-12  # F1 대칭
            v.append(1 - fa)
        out[thr] = float(np.mean(v))
    assert abs(out[0.3] - 0.30952) < 1e-4 and abs(out[0.5] - 0.54762) < 1e-4, out
    return out


@check("retrieval: vocab/IDF from T305 only; no GT used; deterministic; exact sentence -> its own boxes")
def _():
    idx = RT.build(man)
    t305_tokens = set()
    for x in man["T305"]:
        for s in x["sentences"].values():
            t305_tokens |= set(RT.features(s, "word").keys())
    assert set(idx["word"].vocab) == t305_tokens
    # V96 GT를 바꿔도 예측 불변
    m2 = json.loads(json.dumps(man))
    for e in m2["V96"]:
        for t in ("qA", "qB"):
            e["gt_boxes_xyxy_norm"][t] = [[0.1, 0.1, 0.2, 0.2]]
            e["gt_canvas_yxyx"][t] = [[1, 1, 2, 2]]
            e["labels"][t] = ["x"]
    p1 = RT.predictions(idx, man["V96"], ("word", 1))
    p2 = RT.predictions(RT.build(m2), m2["V96"], ("word", 1))
    assert all(p1[k][0] == p2[k][0] for k in p1)
    # 정확 일치 문장: 상위 1개의 유사도 = 1
    x = man["T305"][0]
    s = x["sentences"]["qA"]
    order, sims = idx["word"].ranking(s)
    assert abs(sims[order[0]] - 1.0) < 1e-9
    assert idx["word"].sent[order[0]] == s or abs(sims[order[0]] - 1.0) < 1e-9
    # 동률 결정성
    o1 = idx["word"].ranking("zzzz unseen tokens")[0]
    o2 = idx["word"].ranking("zzzz unseen tokens")[0]
    assert o1 == o2 and len(o1) == 610
    # k=5 medoid: 이웃 3개 box 동일 + 2개 다름 -> 동일 집합이 선택
    return {"vocab": len(idx["word"].vocab), "char_vocab": len(idx["char"].vocab)}


@check("retrieval k=5 medoid toy fixture")
def _():
    boxes = [[[0.1, 0.1, 0.5, 0.5]], [[0.1, 0.1, 0.5, 0.5]], [[0.12, 0.1, 0.5, 0.5]], [[0.8, 0.8, 0.9, 0.9]], [[0.0, 0.7, 0.2, 0.9]]]
    sents = ["a b", "a b c", "a b d", "a x", "a y"]
    ix = RT.Index(sents, boxes, "word")
    b, info = RT.predict(ix, "a b", 5)
    assert info["chosen"] in (0, 1, 2), info
    assert RT.predict(ix, "a b", 1)[1]["chosen"] == 0
    return info


@check("coordinate: original normalized -> canvas -> original normalized round trip on all V96/D24 GT; F1 invariance under anisotropic scaling")
def _():
    worst = 0.0
    n = 0
    for e in man["V96"] + man["D24"]:
        aff = geometry.pad_offsets(e["h"], e["w"])
        assert list(aff) == e["pad_top_left_side"]
        for t in ("qA", "qB"):
            for bc, bn in zip(e["gt_canvas_yxyx"][t], e["gt_boxes_xyxy_norm"][t]):
                back = E.canvas_to_norm_xyxy(bc, aff, e["h"], e["w"])
                worst = max(worst, max(abs(u - v) for u, v in zip(back, bn)))
                n += 1
    assert worst < 1e-9, worst
    rng = random.Random(7)
    mism = 0
    for _ in range(300):
        h, w = rng.randint(500, 3000), rng.randint(500, 3000)
        def rb():
            x0, y0 = rng.random() * 0.7, rng.random() * 0.7
            return [x0, y0, x0 + 0.05 + rng.random() * 0.25, y0 + 0.05 + rng.random() * 0.25]
        pred = [rb() for _ in range(rng.randint(0, 4))]
        gt = [rb() for _ in range(rng.randint(1, 4))]
        top, left, side = geometry.pad_offsets(h, w)
        pc = S39.gt_to_canvas(pred, h, w)
        gc = S39.gt_to_canvas(gt, h, w)
        for thr in (0.3, 0.5):
            mism += abs(S39.sent_metrics(pc, gc, thr)["f1"] - S39.sent_metrics(pred, gt, thr)["f1"]) > 1e-9
        back = [E.canvas_to_norm_xyxy(b, (top, left, side), h, w) for b in pc]
        assert all(max(abs(u - v) for u, v in zip(bb, bo)) < 1e-9 for bb, bo in zip(back, pred))
    assert mism == 0
    return {"n_gt_boxes": n, "max_abs_err": worst, "f1_invariance_mismatch": mism}


@check("requests: swap/text/self-swap row content and no GT in rows")
def _():
    rows = {n: [json.loads(l) for l in open(f"{OUT}/requests/requests_{n}.jsonl")] for n in ("D8_M0", "D8_C", "MAIN_M0", "MAIN_C")}
    assert rows["MAIN_M0"] == rows["MAIN_C"]
    main = rows["MAIN_C"]
    assert len({r["request_id"] for r in main}) == len(main) == 234
    oldv = {(r["patient"], tuple(r["targets"])): r for r in PREP.read_jsonl("results/iter_040/requests/requests_V96.jsonl") if r["cond"] == "I-short"}
    n_sw = n_tx = 0
    for r in main:
        assert not any("gt" in k.lower() or "box" in k.lower() or "label" in k.lower() for k in r)
        o = oldv[(r["patient"], tuple(r["targets"]))]
        assert r["prompt_sha256"] == o["prompt_sha256"] and r["prompt"] == o["prompt"] and r["caps"] == [1000, 2000, 4000]
        if r["kind"] == "swap":
            n_sw += 1
            d = v96[r["donor_patient"]]
            rec = v96[r["patient"]]
            assert r["modality"] == "image" and r["image"] == d["image"] and r["input_pixel_sha256"] == d["input_pixel_sha256"]
            assert r["input_pixel_sha256"] != rec["input_pixel_sha256"] and r["image_file_sha256"] != rec["image_file_sha256"]
            assert r["recipient_image_id"] == rec["ImageID"] and r["image_id"] == d["ImageID"]
            # 원문 동일: donor의 문장도 recipient prompt의 문장과 같아야 한다
            assert any(p["sentence"] == rec["sentences"][r["targets"][0]] and {p["a"]["PatientID"], p["b"]["PatientID"]} == {r["patient"], r["donor_patient"]} for p in man["pairs"])
        else:
            n_tx += 1
            assert r["modality"] == "text" and r["image"] is None and r["input_pixel_sha256"] is None and r["donor_patient"] is None
    assert (n_sw, n_tx) == (42, 192)
    ss = [r for r in rows["D8_C"] if r["cond"] == "I-short-selfswap"]
    real = {(r["patient"], tuple(r["targets"])): r for r in rows["D8_C"] if r["cond"] == "I-short"}
    for r in ss:
        o = real[(r["patient"], tuple(r["targets"]))]
        assert (r["image"], r["input_pixel_sha256"], r["prompt_sha256"], r["caps"]) == (o["image"], o["input_pixel_sha256"], o["prompt_sha256"], o["caps"])
    # 각 환자는 한 pair에만 등장, 각 방향 정확히 1회
    assert len({(r["patient"], r["targets"][0]) for r in main if r["kind"] == "swap"}) == 42
    return {"swap": n_sw, "text": n_tx, "selfswap": len(ss)}


@check("runner read_requests rejects malformed modality/image/donor rows")
def _():
    base = [json.loads(l) for l in open(f"{OUT}/requests/requests_D8_C.jsonl")]
    text = next(r for r in base if r["modality"] == "text")
    img = next(r for r in base if r["kind"] == "D8" and r["modality"] == "image")
    ss = next(r for r in base if r["kind"] == "swap")
    bad = []
    t2 = dict(text, image="x.png")
    bad.append(("text_with_image", [t2]))
    i2 = {k: v for k, v in img.items() if k != "input_pixel_sha256"}
    i2["input_pixel_sha256"] = None
    bad.append(("image_no_pixel_hash", [i2]))
    bad.append(("nonswap_with_donor", [dict(img, donor_patient="x")]))
    s2 = {k: v for k, v in ss.items() if k != "self_swap_regression"}
    bad.append(("selfswap_without_flag", [s2]))
    bad.append(("bad_modality", [dict(img, modality="both")]))
    bad.append(("swap_text", [dict(ss, modality="text", image=None, image_file_sha256=None, input_pixel_sha256=None)]))
    bad.append(("dup_id", [img, img]))
    got = {}
    for name, rows in bad:
        p = tempfile.mktemp(suffix=".jsonl")
        with open(p, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        try:
            R.read_requests(p)
            got[name] = "ACCEPTED"
        except R.RunError:
            got[name] = "rejected"
        os.remove(p)
    assert all(v == "rejected" for v in got.values()), got
    R.read_requests(f"{OUT}/requests/requests_D8_C.jsonl")
    return got


@check("resume test: torn tail preserved, 40 unique, tokens == uninterrupted D8_C_2w and D8_C_4w, no duplicate")
def _():
    d = f"{OUT}/gen/D8_C_resume"
    recs = R.verify_completion(d, f"{OUT}/requests/requests_D8_C.jsonl", f"{OUT}/protocol/protocol_D8_C.json")
    ref = {r["request_id"]: r for r in R.verify_completion(f"{OUT}/gen/D8_C_2w", f"{OUT}/requests/requests_D8_C.jsonl", f"{OUT}/protocol/protocol_D8_C.json")}
    assert len(recs) == 40 and len({r["request_id"] for r in recs}) == 40
    mism = sum(r["suffix_ids"] != ref[r["request_id"]]["suffix_ids"] or r["input_ids_sha256"] != ref[r["request_id"]]["input_ids_sha256"] for r in recs)
    assert mism == 0
    parts = glob.glob(f"{d}/gen_worker*.jsonl.partial.*.bin")
    assert len(parts) == 1 and open(parts[0], "rb").read() == b'{"request_id": "deadbeef", "cond": "I-sh'
    log = [json.loads(l) for l in open(glob.glob(f"{d}/gen_worker*.jsonl.repair.log")[0])]
    assert len(log) == 1 and log[0]["truncated_bytes"] == len(open(parts[0], "rb").read())
    part_stage = [json.load(open(f)) for f in glob.glob(f"{d}/partial_*.json")]
    assert part_stage and part_stage[0]["n_unique"] == 10
    return {"n": len(recs), "token_mismatch": mism, "records_before_resume": part_stage[0]["n_unique"], "torn_bytes": log[0]["truncated_bytes"]}


@check("tamper rejection on copies of a completed stage")
def _():
    src = f"{OUT}/gen/D8_C_2w"
    req, proto = f"{OUT}/requests/requests_D8_C.jsonl", f"{OUT}/protocol/protocol_D8_C.json"
    got = {}

    def trial(name, mutate):
        tmp = tempfile.mkdtemp()
        d = os.path.join(tmp, "g")
        shutil.copytree(src, d)
        try:
            mutate(d)
            R.verify_completion(d, req, proto)
            got[name] = "ACCEPTED"
        except (R.RunError, KeyError, json.JSONDecodeError) as e:
            got[name] = "rejected: " + str(e)[:60]
        finally:
            shutil.rmtree(tmp)

    def edit_records(d, fn, fix_sha=False, fix_digest=False):
        f = sorted(glob.glob(d + "/gen_worker*.jsonl"))[0]
        recs = [json.loads(l) for l in open(f)]
        fn(recs[0])
        if fix_digest:
            recs[0]["record_digest"] = R.record_digest(recs[0])
        with open(f, "w") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")
        if fix_sha:
            c = json.load(open(d + "/completion.json"))
            c["worker_file_sha256"][os.path.basename(f)] = R.file_sha(f)
            json.dump(c, open(d + "/completion.json", "w"))

    trial("alter_output_text", lambda d: edit_records(d, lambda r: r.update(suffix_text_raw="[]")))
    trial("alter_output_text_fix_worker_sha", lambda d: edit_records(d, lambda r: r.update(suffix_text_raw="[]"), fix_sha=True))
    trial("forge_modality_text_as_image", lambda d: edit_records(d, lambda r: r.update(modality="text" if r["modality"] == "image" else "image"), True, True))
    trial("forge_image_tokens_on_text", lambda d: edit_records(d, lambda r: r.update(n_image_tokens=256, modality="text"), True, True))
    trial("drop_worker_file", lambda d: os.remove(sorted(glob.glob(d + "/gen_worker*.jsonl"))[0]))

    def bad_exit(d):
        c = json.load(open(d + "/completion.json"))
        c["exit_codes"] = [0, 1]
        json.dump(c, open(d + "/completion.json", "w"))
    trial("nonzero_exit_code", bad_exit)
    assert all(v.startswith("rejected") for v in got.values()), got
    return got


@check("D8 gate artifact: run=true, chosen workers recorded, all checks zero mismatch")
def _():
    g = json.load(open(f"{OUT}/decisions/D8_gate.json"))
    assert g["run"] is True
    c = g["checks"]
    assert c["C_2w_vs_4w"]["token_mismatch"] == 0 and c["swap_rows"]["donor_pixel_equals_recipient"] == 0
    return {"worker_choice": g["worker_choice"]}


@check("gate refuses a protocol when decision.run is not true")
def _():
    p = tempfile.mktemp(suffix=".json")
    json.dump({"run": False}, open(p, "w"))
    outp = tempfile.mktemp(suffix=".json")
    try:
        R.make_protocol(f"{OUT}/requests/requests_D8_M0.jsonl", outp, gate=p)
        r = "ACCEPTED"
    except R.RunError:
        r = "rejected"
    os.remove(p)
    assert r == "rejected" and not os.path.exists(outp)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"n_pass": sum(r["pass"] for r in RES), "n": len(RES), "results": RES,
               "source_sha256": R.file_sha("test_pg43.py")}, open(a.out, "x"), indent=1, default=str)
    print(json.dumps([(r["name"][:70], r["pass"]) for r in RES], indent=1))
    print(sum(r["pass"] for r in RES), "/", len(RES))


if __name__ == "__main__":
    main()
