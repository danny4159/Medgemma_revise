"""iter_015 CPU fixture 검사. 사용: python test_rsna_iter015.py  -> results/iter_015/tests/fixtures_iter015.json"""
import copy
import json
import os
import subprocess
import sys
import tempfile

from rsna_diag import generate, qa_data, qa_gen, qa_protocol, qa_requests as Q, qa_run, qa_spec as S

OUT = "results/iter_015"
res = []


def check(name, cond, detail=""):
    res.append({"name": name, "pass": bool(cond), "detail": str(detail)[:300]})
    print(("PASS " if cond else "FAIL ") + name, detail if not cond else "")


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return str(e)[:200]
    return None


# ---- 0. 반입 blob 일치·import
man = json.load(open("/SSD1_1TB/home/milab/daniel/08_medgemma/agent/runs/iter_015/reuse_manifest.json"))["files"]
bad = []
for f, m in man.items():
    h = subprocess.run(["git", "hash-object", f], capture_output=True, text=True).stdout.strip()
    if h != m["blob"]:
        bad.append(f)
check("imported 16 files match source blobs", not bad and len(man) == 16, bad)
import importlib
imp = {m: importlib.import_module("rsna_diag." + m) for m in ("geometry", "parse", "metrics", "sft_eval", "lora", "generate", "prompts",
                                                               "queue_lock", "lock_protocol", "inputs", "eval_gate", "run_shards", "on_gpu",
                                                               "rsna_data", "dicom_min")}
check("all imported modules import", len(imp) == 15)

# ---- 1. parser
pp = lambda raw, eos=True: S.parse_plain(raw + S.EOT, eos)
check("plain yes/no + case/space/punct", [pp(" Yes. ")[1], pp("NO")[1], pp("no!")[1]] == ["yes", "no", "no"])
check("plain rejects extra punct/explanations", [pp("yes..")[0], pp("Yes, there is")[0], pp("")[0]] == ["explanation", "explanation", "empty"])
check("plain bbox list is not answer; [] not converted to no", [pp("[]")[0], pp('[{"box_2d":[1,2,3,4],"label":"x"}]')[0]] == ["bbox_list", "bbox_list"])
check("plain contradictory/truncated", pp("yes and no")[0] == "contradictory" and S.parse_plain("yes", False)[0] == "truncated")
pj = lambda raw, eos=True: S.parse_json(raw + S.EOT, eos)
check("json valid", pj('{"answer":"yes"}') == ("valid", "yes") and pj('{"answer": "no"}') == ("valid", "no"))
check("json rejects extra key/dup key/fence/case/list",
      [pj('{"answer":"yes","x":1}')[0], pj('{"answer":"yes","answer":"no"}')[0], pj('```json\n{"answer":"yes"}\n```')[0],
       pj('{"answer":"Yes"}')[0], pj("[]")[0]] == ["schema_error", "contradictory", "explanation", "schema_error", "schema_error"],
      [pj('{"answer":"yes","answer":"no"}'), pj("[]")])
check("json truncated", S.parse_json('{"answer":"y', False)[0] == "truncated")

# ---- 2. 정답 mapping, 원본 label 대조, 일반 manifest에 정답 없음
gt = json.load(open(qa_data.GT))
rep, probs = qa_data.audit(gt)
check("audit: Calculated label/category/bbox 대조 (val+confirm 1,200명), 문제 0", rep["n_checked"] == 1200 and not probs and rep["annotation_hash_match"], (rep["n_checked"], probs[:2]))
check("GT pair: NoOpacity/NotNormal=(no,yes) != Normal=(no,no)", S.GT_PAIR["not_normal_no_opacity"] == ("no", "yes") and S.GT_PAIR["normal"] == ("no", "no")
      and S.GT_PAIR["opacity"] == ("yes", "yes"))
check("NoOpacity and Normal are separate categories in manifest",
      sum(g["category"] == "normal" for g in gt.values() if g["split"] == "confirm") == 200
      and sum(g["category"] == "not_normal_no_opacity" for g in gt.values() if g["split"] == "confirm") == 200)
mf = [json.loads(ln) for ln in open(f"{OUT}/manifests/infer_manifest.jsonl")]
check("infer manifest has no category/GT fields", all(set(m) == {"id", "split", "image", "file_sha256", "pixel_sha256"} for m in mf))
reqs = [json.loads(ln) for f in os.listdir(f"{OUT}/requests") for ln in open(f"{OUT}/requests/{f}")]
check("request rows contain no category/GT keys", all(not ({"category", "boxes", "gt", "label"} & set(r)) for r in reqs))
check("direct prompts contain no box text", all("box" not in r["prompt"].lower() for r in reqs if r["condition"] in ("direct",)))

# ---- 3. split
sets = json.load(open(f"{OUT}/manifests/sets.json"))
sz = qa_data.checks(sets, gt, mf)
check("set sizes and disjointness", sz == {"D36": 36, "E180": 180, "E600": 600, "P60": 60, "P180": 180, "D12": 12}, sz)
ok = all(sets["E180"][c] == sorted(sets["E600"][c], key=lambda i: qa_data.order_key(c, gt[i]["patient"]))[:60] for c in S.CATEGORIES)
check("E180 = first 60 per category of hash order (E600 prefix)", ok)

# ---- 4. request id / 변조
cfg, _ = qa_protocol.static_cfg()
item = mf[0]
row = Q.make_row(item, "B0", "a" * 64, "O", "plain", "direct", S.qa_prompt("O", "plain"), None, cfg, "t")
check("verify_row passes untouched", Q.verify_row(row, cfg))
tam = {"prompt": row["prompt"] + " ", "adapter_digest": "b" * 64, "file_sha256": "c" * 64, "pixel_sha256": "d" * 64, "target": "A", "fmt": "json",
       "condition": "bbox", "evidence_digest": "e" * 64, "config_digest": "f" * 64, "model_revision": "x", "id": "zzz", "split": "train"}
allc = True
det = {}
for k, v in tam.items():
    r2 = copy.deepcopy(row)
    r2[k] = v
    if k == "prompt":  # prompt만 바꾸고 prompt_sha를 갱신하면 id가 바뀌어 기존 id와 불일치
        r2["prompt_sha256"] = generate.sha(v.encode()) if False else __import__("rsna_diag.prompts", fromlist=["x"]).digest(v)
    changed = Q.compute_id(r2) != row["request_id"]
    rej = raises(lambda: Q.verify_row(r2, cfg), Q.RequestError) is not None
    det[k] = (changed, rej)
    allc &= changed and rej
check("tampering any id field changes request_id and verify_row rejects", allc, det)
r3 = copy.deepcopy(row)
r3["prompt"] = "different"
check("prompt text edit without sha update rejected", raises(lambda: Q.verify_row(r3, cfg), Q.RequestError))
dup = tempfile.mktemp(suffix=".jsonl", dir=f"{OUT}/tests")
open(dup, "w").write(json.dumps(row) + "\n" + json.dumps(row) + "\n")
check("duplicate request_id in request file rejected", raises(lambda: Q.load_rows(dup), Q.RequestError))
ev1 = S.evidence_text("predicted", [[10, 20, 30, 40]])
ev2 = S.evidence_text("predicted", [])
ev3 = S.evidence_text("unavailable")
ev4 = S.evidence_text("oracle", [[10, 20, 30, 40]])
check("evidence texts differ and empty != Normal", len({ev1, ev2, ev3, ev4}) == 4 and "does not mean the image is Normal" in ev2 and "does not mean the image is Normal" in ev3)
check("invalid predicted evidence -> unavailable text", S.evidence_text("predicted", None) == ev3)
ra = Q.make_row(item, "M0", None, "O", "plain", "ev_predicted", S.qa_prompt("O", "plain", ev1), S.sha(ev1), cfg, "t")
rb = Q.make_row(item, "M0", None, "O", "plain", "ev_predicted", S.qa_prompt("O", "plain", ev2), S.sha(ev2), cfg, "t")
check("evidence content changes request_id", ra["request_id"] != rb["request_id"])

# ---- 5. protocol
tdir = tempfile.mkdtemp(dir=f"{OUT}/tests")
check("protocol create rejects missing extra file", raises(lambda: qa_protocol.create(f"{tdir}/p0.json", [f"{tdir}/nonexistent.txt"]), RuntimeError))
ex = f"{tdir}/req.txt"
open(ex, "w").write("a")
pth = f"{tdir}/p1.json"
qa_protocol.create(pth, [ex], "fixture")
check("protocol verify ok", bool(qa_protocol.verify(pth)))
open(ex, "w").write("b")
check("protocol verify rejects changed locked file", raises(lambda: qa_protocol.verify(pth), RuntimeError))
p = json.load(open(pth))
del p["locked"]["files"]["rsna_diag/geometry.py"]
json.dump(p, open(f"{tdir}/p2.json", "w"))
check("protocol verify rejects one dropped required file", raises(lambda: qa_protocol.verify(f"{tdir}/p2.json"), RuntimeError))
check("protocol create does not overwrite", raises(lambda: qa_protocol.create(pth, [ex]), RuntimeError))
check("protocol file path missing rejected", raises(lambda: qa_protocol.verify(f"{tdir}/none.json"), RuntimeError))

# ---- 6. validate_records (중복·누락·잉여·변경 입력·잘못된 adapter·오래된 record)
rows = [Q.make_row(mf[k], "M0", None, "O", "plain", "direct", S.qa_prompt("O", "plain"), None, cfg, "t") for k in range(3)]


def rec(r, **kw):
    d = {"request_id": r["request_id"], "id": r["id"], "condition": r["condition"], "checkpoint": r["checkpoint"], "target": r["target"],
         "fmt": r["fmt"], "prompt_sha256": r["prompt_sha256"], "adapter_digest": None, "config_digest": cfg, "protocol_digest": "P",
         "image_file_sha256": r["file_sha256"], "input_pixel_sha256": "px_" + r["id"]}
    d.update(kw)
    return d


px = lambda path: "px_" + [r for r in rows if r["image"] == path][0]["id"]
ok_ = qa_gen.validate_records({"f": [rec(rows[0]), rec(rows[1])]}, rows, cfg, None, "P", px)
check("validate: partial (missing) allowed for resume", len(ok_) == 2)
E = qa_gen.QAError
check("validate: duplicate rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0])], "g": [rec(rows[0])]}, rows, cfg, None, "P", px), E))
check("validate: extra rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0], request_id="zz")]}, rows, cfg, None, "P", px), E))
check("validate: wrong adapter rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0], adapter_digest="x")]}, rows, cfg, None, "P", px), E))
check("validate: stale protocol rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0], protocol_digest="OLD")]}, rows, cfg, None, "P", px), E))
check("validate: changed prompt rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0], prompt_sha256="0")]}, rows, cfg, None, "P", px), E))
check("validate: changed input image rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0], input_pixel_sha256="OLD")]}, rows, cfg, None, "P", px), E))
check("validate: config mismatch rejected", raises(lambda: qa_gen.validate_records({"f": [rec(rows[0], config_digest="c")]}, rows, cfg, None, "P", px), E))
tj = f"{tdir}/gen_worker0.jsonl"
open(tj, "w").write(json.dumps(rec(rows[0])) + "\n" + '{"request_id": "abc", "id"')
check("truncated JSONL tail rejected", raises(lambda: qa_gen.read_strict(tj), E))
check("truncated tail tolerated only for other live workers", len(qa_gen.read_strict(tj, tolerate_tail=True)) == 1)
qa_gen.read_strict(tj, repair_tail=True)
check("--repair-tail quarantines tail (not deleted)", len(qa_gen.read_strict(tj)) == 1 and os.path.getsize(tj + ".partial") > 0)
open(f"{tdir}/bad.jsonl", "w").write("{not json}\n" + json.dumps(rec(rows[0])) + "\n")
check("corrupt middle line rejected", raises(lambda: qa_gen.read_strict(f"{tdir}/bad.jsonl"), E))

# ---- 7. GPU 계획
snap = {0: {"uuid": "u0", "used_mib": 100, "total_mib": 24576}, 1: {"uuid": "u1", "used_mib": 15000, "total_mib": 24576}}
check("plan: 2 workers/GPU fits", len(qa_run.plan_gpus([0], 2, 8.0, [0, 1], snap)) == 2)
check("plan: outside allowed set rejected", raises(lambda: qa_run.plan_gpus([2], 1, 8.0, [0, 1], snap), qa_run.GpuError))
check("plan: insufficient free memory rejected (other process 15GB)", raises(lambda: qa_run.plan_gpus([1], 1, 8.0, [0, 1], snap), qa_run.GpuError))
check("plan: worker sum + 2GiB each enforced", raises(lambda: qa_run.plan_gpus([0], 3, 8.0, [0, 1], snap), qa_run.GpuError) is not None)
check("plan: worker->gpu mapping round robin", qa_run.plan_gpus([0, 1], 4, 8.0, [0, 1], {0: {"uuid": "a", "used_mib": 0, "total_mib": 24576}, 1: {"uuid": "b", "used_mib": 0, "total_mib": 24576}}) == [(0, 0), (1, 1), (2, 0), (3, 1)])
_orig = subprocess.run


class _F:
    returncode, stdout, stderr = 9, "", "boom"


subprocess.run = lambda *a, **k: _F()
try:
    r_ = raises(lambda: qa_run.query_gpus([0]), qa_run.GpuError)
finally:
    subprocess.run = _orig
check("nvidia-smi failure rejected", r_)
old_env = os.environ.pop("CUDA_VISIBLE_DEVICES", None)
check("missing CUDA_VISIBLE_DEVICES rejected", raises(qa_run.allowed_gpus, qa_run.GpuError))
if old_env is not None:
    os.environ["CUDA_VISIBLE_DEVICES"] = old_env

# ---- 8. qa_eval 함수 (합성 fixture) + 입력 기하
import numpy as np
from rsna_diag import qa_eval as EV
tabf = {}
mk = lambda o, a: {"O": ("valid", o, True, 3), "A": ("valid", a, True, 3)}
ids_c = {"opacity": ["o1", "o2"], "normal": ["n1", "n2"], "not_normal_no_opacity": ["x1", "x2"]}
ans = {"o1": ("yes", "yes"), "o2": ("yes", "no"), "n1": ("no", "no"), "n2": ("no", "no"), "x1": ("no", "no"), "x2": ("no", "yes")}
for i, (o, a_) in ans.items():
    tabf[("M", "direct", "plain", i)] = mk(o, a_)
tabf[("M", "direct", "plain", "n2")] = {"O": ("truncated", None, False, 1000), "A": ("valid", "no", True, 3)}
vec = EV.score_vectors(tabf, "M", "direct", "plain", ids_c)
sc, per = EV.s_scope(vec)
check("S_scope: both targets needed, invalid counts as failure, category equal weight",
      per == {"opacity": 0.5, "normal": 0.5, "not_normal_no_opacity": 0.5} and abs(sc - 0.5) < 1e-12, per)
b0 = EV.bootstrap_diff(vec, vec, n=500)
check("paired bootstrap of identical vectors is exactly 0 (patient resampling shared)", b0["S_scope"]["ci"] == [0.0, 0.0] and b0["S_scope"]["point"] == 0.0)
check("bootstrap unit is patient (vector length = patients, not requests)", all(len(v) == 2 for v in vec.values()))
cb = EV.constant_baselines(ids_c)
check("constant answer-pair baselines (no,yes)=1/3, (yes,yes)=1/3", abs(cb["no/yes"]["S_scope"] - 1 / 3) < 1e-12 and abs(cb["yes/yes"]["S_scope"] - 1 / 3) < 1e-12)
ba = EV.balanced_accuracy(tabf, "M", "direct", "plain", "A", {i: c for c, v in ids_c.items() for i in v})
check("balanced accuracy uses abnormal(pos)=opacity+NoOpacity/NotNormal", ba["n_pos"] == 4 and ba["n_neg"] == 2, ba)
pc = EV.pair_confusion(tabf, "M", "direct", "plain", {i: c for c, v in ids_c.items() for i in v})
check("pair confusion keeps invalid separate", pc["normal"].get("invalid/no") == 1, pc["normal"])
import numpy as _np
from PIL import Image
sq = True
gtn = True
for m in mf:
    im = _np.asarray(Image.open(m["image"]))
    sq &= im.shape == (1024, 1024)
lab = json.load(open(f"{OUT}/manifests/labels.json"))
for i, l in lab.items():
    for b in l["boxes"]:
        x0, y0, x1, y1 = b["xyxy_px"]
        gtn &= all(abs(u - v * 1000 / 1024) < 1e-3 for u, v in zip(b["yxyx_norm"], [y0, x0, y1, x1]))
check("all 636 images are 1024x1024 (square padding is identity) and GT yxyx_norm = px/1024*1000", sq and gtn and len(mf) == 636, (sq, gtn, len(mf)))
from rsna_diag import generate as G
im0, aff0, _ = G.load_image(mf[0]["image"])
check("load_image: padded pixels equal original replicated RGB", _np.array_equal(_np.asarray(im0)[..., 0], _np.asarray(Image.open(mf[0]["image"]))) and aff0[2] == 1024, aff0)

# ---- 8. 정답 metric 함수는 qa_eval 검사(별도)에서
n_fail = sum(not r["pass"] for r in res)
json.dump({"n": len(res), "n_pass": len(res) - n_fail, "results": res}, open(f"{OUT}/tests/fixtures_iter015.json", "w"), indent=1)
print(f"{len(res) - n_fail}/{len(res)} passed")
sys.exit(1 if n_fail else 0)
