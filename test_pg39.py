"""iter_039 CPU fixture 검사. 결과: results/iter_039/tests/fixtures_pg39_v2.json (새 경로, 존재하면 거부)."""
import hashlib
import json
import os
import random
import sys
import tempfile

import numpy as np

import pg39_data as D
import pg39_run as R
import pg39_spec as S
from rsna_diag import geometry, metrics, parse

OUT = "results/iter_039/tests/fixtures_pg39_v2.json"
res = {}


def check(name, cond, info=None):
    res[name] = {"pass": bool(cond), "info": info}
    print(("PASS " if cond else "FAIL ") + name, info if not cond else "")


def blob(path):
    b = open(path, "rb").read()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


# 1. 반입 blob
EXPECT = {"rsna_diag/__init__.py": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
          "rsna_diag/geometry.py": "3d6521177f2ed3a081bf27be743597ac8750b836",
          "rsna_diag/parse.py": "5ea487198f08215c769ecdcdf9d00db670c4112a",
          "rsna_diag/metrics.py": "33c5131f7696fe9b0a1cb4266ecfc8b48f2e1fb8",
          "rsna_diag/generate.py": "b5f1e61e7ba3602b4164062d29cdb8ce433c2e4a",
          "rsna_diag/prompts.py": "ccd14dbf03528c21cffb93c00cfc89c77fe4de19"}
check("imported_blobs_match", all(blob(k) == v for k, v in EXPECT.items()))
src = open("rsna_diag/generate.py").read()
check("legacy_cli_paths_not_called", "lock_protocol" in src and "lock_protocol" not in open("pg39_run.py").read()
      and "queue_lock" not in open("pg39_run.py").read() and "generate.main" not in open("pg39_run.py").read())

# 2. 좌표: 비정사각·홀수 padding·모서리
for (h, w, box) in [(1000, 1301, [0.0, 0.0, 1.0, 1.0]), (1301, 999, [0.25, 0.1, 0.75, 0.4]), (1200, 1200, [0.0, 0.5, 0.5, 1.0]),
                    (997, 1500, [0.9, 0.95, 1.0, 1.0])]:
    img = np.zeros((h, w), np.uint8)
    x0, y0, x1, y1 = box
    px0, py0, px1, py1 = int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h))
    img[py0:py1, px0:px1] = 200
    rgb = geometry.to_uint8_rgb_preserving(img)
    pad, (top, left, side) = geometry.pad_square(rgb)
    ys, xs = np.where(pad[:, :, 0] == 200)
    got = [ys.min(), xs.min(), ys.max() + 1, xs.max() + 1]
    want = geometry.canvas_to_norm([px0, py0, px1, py1], top, left, side)
    ok = all(abs(g - wv * side / 1000) < 1e-6 for g, wv in zip(got, want))
    # gt_to_canvas 왕복
    c = S.gt_to_canvas([box], h, w)[0]
    back = geometry.norm_to_canvas(c, top, left, side)
    ok2 = all(abs(b - v) < 1e-6 for b, v in zip(back, [x0 * w, y0 * h, x1 * w, y1 * h]))
    check(f"geometry_{h}x{w}_{box}", ok and ok2 and side == max(h, w),
          {"top": top, "left": left, "side": side, "odd_pad": (abs(h - w) % 2) == 1})

# 3. parser
def suffix(items, think=""):
    return think + "Final Answer: " + json.dumps(items) + "<end_of_turn>"


B = [10, 10, 100, 100]
c = S.parse_ids(suffix([{"box_2d": B, "label": "qA"}, {"box_2d": [200, 200, 300, 300], "label": " QB "}]), True, {"qA", "qB"})
check("parse_two_groups", c["status"] == "valid_nonempty" and len(c["groups"]["qA"]) == 1 and len(c["groups"]["qB"]) == 1)
c = S.parse_ids(suffix([]), True, {"qA", "qB"})
check("parse_empty_valid", c["status"] == "valid_empty")
c = S.parse_ids(suffix([{"box_2d": B, "label": "opacity"}]), True, {"qA"})
check("parse_unknown_id_invalid", c["status"] == "unknown_id")
c = S.parse_ids(suffix([{"box_2d": B, "label": "qB"}]), True, {"qA"})
check("parse_other_known_id_flagged_not_pred", c["status"] == "valid_nonempty" and c["other_id_boxes"] == 1 and not c["groups"]["qA"])
raw = 'Final Answer: [{"box_2d": [1,2,3,4], "label": "qA", "label": "qB"}]<end_of_turn>'
check("parse_duplicate_key", S.parse_ids(raw, True, {"qA", "qB"})["status"] == "dup_key")
check("parse_truncated", S.parse_ids('Final Answer: [{"box_2d": [1,2', False, {"qA"})["status"] == "truncated")
check("parse_nonfinite", S.parse_ids('Final Answer: [{"box_2d": [1,2,NaN,4], "label": "qA"}]<end_of_turn>', True, {"qA"})["status"]
      in ("coord_invalid", "schema_error"))
check("parse_out_of_range", S.parse_ids(suffix([{"box_2d": [0, 0, 1200, 10], "label": "qA"}]), True, {"qA"})["status"] == "coord_invalid")
check("parse_thinking_then_answer", S.parse_ids(suffix([{"box_2d": B, "label": "qA"}], think="<unused94>x<unused95>"), True, {"qA"})["status"] == "valid_nonempty")
check("parse_unclosed_thinking", S.parse_ids("<unused94>abc<end_of_turn>", True, {"qA"})["status"] == "unclosed_thinking")
check("parse_no_gt_used", "gt" not in S.parse_ids.__code__.co_varnames)

# 4. matching: 빠른 구현 == 열거 구현 (cardinality, 총 IoU)
rng = random.Random(1)
bad = 0
ties = 0
for t in range(400):
    def rb():
        y0, x0 = rng.uniform(0, 800), rng.uniform(0, 800)
        return [y0, x0, y0 + rng.uniform(20, 200), x0 + rng.uniform(20, 200)]
    gt = [rb() for _ in range(rng.randint(0, 4))]
    pr = [rb() if rng.random() < .5 or not gt else [v + rng.uniform(-30, 30) for v in gt[rng.randrange(len(gt))]] for _ in range(rng.randint(0, 6))]
    pr = [[min(1000, max(0, v)) for v in b] for b in pr]
    pr = [b for b in pr if b[0] < b[2] and b[1] < b[3]]
    for thr in (0.3, 0.5):
        a = metrics.match(pr, gt, thr)
        b = S.match_fast(pr, gt, thr)
        ta = sum(metrics.iou(pr[p], gt[g]) for g, p in a)
        tb = sum(metrics.iou(pr[p], gt[g]) for g, p in b)
        if len(a) != len(b) or abs(ta - tb) > 1e-9:
            bad += 1
        elif sorted(a) != sorted(b):
            ties += 1
check("match_fast_equals_enumeration", bad == 0, {"mismatch": bad, "identity_differs_only_in_tie": ties, "trials": 800})
# 실제 동점: 동일 pred 두 개 / 동일 GT 두 개
check("match_true_tie_cardinality", len(S.match_fast([B, B], [B, B], .3)) == 2 == len(metrics.match([B, B], [B, B], .3)))
big_gt = [[i * 10, i * 10, i * 10 + 200, i * 10 + 200] for i in range(8)]
big_pr = [[i * 10 + 3, i * 10, i * 10 + 200, i * 10 + 205] for i in range(40)]
import time
t0 = time.time()
S.match_fast(big_pr, big_gt, .3)
check("match_fast_scales_8gt_40pred", time.time() - t0 < 1.0)

# 5. 표본 규칙
pool = []
for k in range(600):
    pool.append({"PatientID": f"P{k}", "ImageID": f"I{k}", "share_group": k % 9 == 0, "multi_box": k % 3 == 0, "split": "train"})
sel = D.select(pool, "train", [("D", 24), ("E", 288)])
Dp = {c["PatientID"] for c in sel["D"]["chosen"]}
Ep = {c["PatientID"] for c in sel["E"]["chosen"]}
check("select_sizes_disjoint", len(Dp) == 24 and len(Ep) == 288 and not (Dp & Ep))
sel2 = D.select(pool, "train", [("D", 24), ("E", 288)])
check("select_deterministic", [c["PatientID"] for c in sel["E"]["chosen"]] == [c["PatientID"] for c in sel2["E"]["chosen"]])
q = D.apportion({"a": 100, "b": 30, "c": 5}, 24)
check("apportion_total_and_rare_kept", sum(q.values()) == 24 and q["c"] >= 1, q)
ids = {D.assign_ids("I1", 3, 5)["qA"], D.assign_ids("I1", 3, 5)["qB"]}
check("assign_ids_pure", ids == {3, 5})
par = sum(D.assign_ids(f"I{k}", 0, 1)["qA"] == 0 for k in range(2000)) / 2000
check("assign_ids_balanced", 0.45 < par < 0.55, par)

# 6. eligibility 경계
L2G = {"a": "G1"}
ok, why = D.eligibility({"abnormal": True, "sentence_en": "Nodule in the right upper lobe.", "boxes": [[.1, .1, .3, .3]], "labels": ["a"],
                         "locations": ["x"], "progression": None}, L2G)
check("eligible_basic", ok)
for name, patch, reason in [("temporal", {"sentence_en": "Nodule unchanged since prior."}, "temporal_phrase"),
                            ("progression", {"progression": "new"}, "progression_field"),
                            ("invalid_box", {"boxes": [[.5, .5, .4, .6]]}, "invalid_box"),
                            ("nonfinite_box", {"boxes": [[.1, .1, float("nan"), .3]]}, "invalid_box"),
                            ("no_box", {"boxes": []}, "no_box"), ("unmapped", {"labels": ["zz"]}, "label_unmapped")]:
    f = {"abnormal": True, "sentence_en": "Nodule in the right upper lobe.", "boxes": [[.1, .1, .3, .3]], "labels": ["a"],
         "locations": ["x"], "progression": None}
    f.update(patch)
    check(f"eligibility_reject_{name}", D.eligibility(f, L2G) == (False, reason))
# duplicate JSON key
try:
    json.loads('{"a":1,"a":2}', object_pairs_hook=D._no_dup_pairs)
    check("json_dup_key_rejected", False)
except ValueError:
    check("json_dup_key_rejected", True)

# 7. prompt 구성
sents = {"qA": "Sentence A here.", "qB": "Sentence B here."}
P = {(c[0], tuple(c[1])): c for c in S.build_prompts(sents)}
conds = [c[0] for c in S.build_prompts(sents)]
check("nine_requests_per_patient", conds == ["I-long", "I-long", "J-long", "J-reverse", "C-long", "C-long", "I-short", "I-short", "J-short"], conds)
jl, jr = P[("J-long", ("qA", "qB"))][2], P[("J-reverse", ("qA", "qB"))][2]
check("reverse_only_order_changes", jl != jr and sorted(jl.split()) != [] and
      jl.index("qA:") < jl.index("qB:") and jr.index("qB:") < jr.index("qA:") and len(jl) == len(jr))
check("long_keeps_official_instructions", "Final Answer" in jl and "[y0, x0, y1, x1]" in jl and "left" in jl)
check("caps", P[("J-long", ("qA", "qB"))][3] == [2000, 4000, 8000] and P[("I-long", ("qA",))][3] == [1000, 2000, 4000])
check("prompt_builder_takes_only_sentences", S.build_prompts.__code__.co_varnames[:S.build_prompts.__code__.co_argcount] == ("sents",))

# 8. run 보호: 변조·중복·잉여 거부
rows = [{"request_id": f"r{i}", "prompt_sha256": "p", "input_pixel_sha256": "x", "image": "img", "order_key": i, "caps": [10]}
        for i in range(3)]
rb = {r["request_id"]: r for r in rows}


def mk(i, **kw):
    r = {"request_id": f"r{i}", "row_digest": R.row_digest(rows[i]), "prompt_sha256": "p", "input_pixel_sha256": "x",
         "protocol_digest": "P", "config_digest": "C", "suffix_ids": [1]}
    r.update(kw)
    r["record_digest"] = R.record_digest(r)
    return r


px = lambda p: "x"
ok = R.validate_records({"f0": [mk(0), mk(1)]}, rb, "P", "C", px)
check("validate_accepts_partial", len(ok) == 2)


def rejects(files, pxf=px):
    try:
        R.validate_records(files, rb, "P", "C", pxf)
        return False
    except R.RunError:
        return True


t = mk(0)
t["suffix_ids"] = [9]
check("validate_rejects_tampered_content", rejects({"f": [t]}))
check("validate_rejects_duplicate", rejects({"f0": [mk(0)], "f1": [mk(0)]}))
check("validate_rejects_extra", rejects({"f": [dict(mk(0), request_id="zz")]}))
check("validate_rejects_changed_image", rejects({"f": [mk(0)]}, lambda p: "y"))
check("validate_rejects_other_protocol", rejects({"f": [mk(0, protocol_digest="Q")]}))
# 비복구: digest 없이 변조 후 digest 재계산해도 row_digest가 달라지면 거부
rows2 = dict(rb)
rows2["r0"] = dict(rows[0], prompt_sha256="other")
try:
    R.validate_records({"f": [mk(0)]}, rows2, "P", "C", px)
    check("validate_rejects_changed_request_row", False)
except R.RunError:
    check("validate_rejects_changed_request_row", True)

# 9. concat zip reader
import io, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
    z.writestr("d/a.bin", os.urandom(50000))
    z.writestr("d/b.bin", os.urandom(30000))
data = buf.getvalue()
with tempfile.TemporaryDirectory() as td:
    ps = []
    for i, off in enumerate(range(0, len(data), 7001)):
        p = os.path.join(td, f"p{i}")
        open(p, "wb").write(data[off:off + 7001])
        ps.append(p)
    cf = io.BufferedReader(D.ConcatFile(ps))
    zz = zipfile.ZipFile(cf)
    check("concat_zip_reads_members", zz.testzip() is None and set(zz.namelist()) == {"d/a.bin", "d/b.bin"})

os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT):
    sys.exit("fixtures output exists; use a new path")
json.dump(res, open(OUT, "w"), indent=1)
n_fail = sum(not v["pass"] for v in res.values())
print(f"{len(res) - n_fail}/{len(res)} passed")
sys.exit(1 if n_fail else 0)
