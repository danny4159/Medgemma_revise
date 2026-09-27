"""iter_016 CPU fixture 검사. 사용: python test_rsna_iter016.py -> results/iter_016/tests/fixtures_iter016.json
semantic_v1 parser(독립 참조 구현과 D36 원문 432건 대조), 표본·요청 행렬, bbox 출처, 복구 소유권, 평가 계산, 확대 규칙을 검사한다."""
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np

from rsna_diag import (generate, qa_eval as E, qa_gen, qa_pilot, qa_protocol, qa_requests as Q, qa_reuse, qa_run, qa_scope as SC,
                       qa_spec as S, queue_lock)

OUT = Q.OUT
assert OUT == "results/iter_016", OUT
res = []


def check(name, cond, detail=""):
    res.append({"name": name, "pass": bool(cond), "detail": str(detail)[:300]})
    print(("PASS " if cond else "FAIL ") + name, detail if not cond else "")


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return str(e)[:200] or exc.__name__
    return None


# ---- 1. semantic_v1: 고정 규칙 fixture
EOT = S.EOT
ps = lambda t, f, r, eos=True: S.parse_semantic(t, f, r + EOT, eos)
check("strict parsers unchanged for previously-valid answers", S.parse_plain("Yes." + EOT, True) == ("valid", "yes") and S.parse_json('{"answer":"no"}' + EOT, True) == ("valid", "no"))
check("bare yes/no accepted for both formats, case and one trailing . or !",
      [ps("O", "plain", " Yes. ")[1], ps("O", "json", "NO!")[1], ps("A", "json", "yes")[1]] == ["yes", "no", "yes"]
      and ps("O", "json", "yes")[2] == "bare_yes_no")
check("double punctuation / internal space rejected", [ps("O", "plain", "yes..")[0], ps("O", "plain", "yes .")[0], ps("O", "plain", "y es")[0]] != ["valid"] * 3
      and all(ps("O", "plain", x)[0] != "valid" for x in ("yes..", "yes .", "yes!.", "ye s")))
check("JSON answer accepted in either format", ps("O", "plain", '{"answer":"yes"}') == ("valid", "yes", "json_answer") and ps("A", "json", '{"answer": "no"}')[1] == "no")
check("JSON: extra key/dup key/list/uppercase/Normal value rejected (status exact)",
      [ps("A", "json", x)[0] for x in ('{"answer":"yes","x":1}', '{"answer":"yes","answer":"yes"}', '["yes"]', '{"answer":"Yes"}', '{"answer":"Normal"}')]
      == ["schema_error", "explanation", "schema_error", "schema_error", "schema_error"])
check("JSON fence/trailing text/quoted string/trailing period rejected",
      all(ps("A", "json", x)[0] != "valid" for x in ('```json\n{"answer":"yes"}\n```', '{"answer":"yes"}.', '"yes"', '{"answer":"yes"} yes')))
check("Q_A: bare Normal/Abnormal mapped (no/yes), same case/punct rule",
      [ps("A", "plain", "Normal"), ps("A", "plain", "abnormal."), ps("A", "json", "Abnormal!")]
      == [("valid", "no", "bare_normal_abnormal"), ("valid", "yes", "bare_normal_abnormal"), ("valid", "yes", "bare_normal_abnormal")])
check("Q_O: Normal/Abnormal NOT mapped", ps("O", "plain", "Normal")[0] != "valid" and ps("O", "json", "Abnormal")[0] != "valid")
check("explanation/mixed/contradiction/bbox/[]/partial match rejected",
      all(ps("A", "plain", x)[0] != "valid" for x in ("Normal, abnormal", "yes no", "Yes, there is an opacity.", "[]", '[{"box_2d":[1,2,3,4]}]',
                                                       "The image is Normal", "Based on the image, no", "normal abnormal", "No opacity")))
check("[] is not converted to no", ps("A", "plain", "[]")[1] is None and ps("O", "plain", "[]")[1] is None)
check("truncated (no EOS) and empty rejected", ps("O", "plain", "yes", False)[0] == "truncated" and ps("O", "plain", "  ")[0] == "empty")
check("only one trailing <end_of_turn> removed", S.parse_semantic("O", "plain", "yes" + EOT + EOT, True)[0] != "valid")
check("semantic parser signature has no category/ground-truth argument", list(inspect.signature(S.parse_semantic).parameters) == ["target", "fmt", "raw", "ended_eos"])


def ref_semantic(target, fmt, raw, eos):
    """독립 참조 구현(정규식 기반). returns (valid?, answer)."""
    if not eos:
        return None
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    t = t.strip()
    m = re.fullmatch(r"([A-Za-z]+)[.!]?", t)
    if m:
        w = m.group(1).lower()
        if w in ("yes", "no"):
            return w
        if target == "A" and w in ("normal", "abnormal"):
            return {"normal": "no", "abnormal": "yes"}[w]
        return None
    if t.startswith("{"):
        try:
            v = json.loads(t, object_pairs_hook=lambda p: (_ for _ in ()).throw(ValueError()) if len({k for k, _ in p}) != len(p) else dict(p))
        except ValueError:
            return None
        if isinstance(v, dict) and set(v) == {"answer"} and v["answer"] in ("yes", "no"):
            return v["answer"]
    return None


pairs = []
for fmt in ("plain", "json"):
    for ck in ("M0", "B0", "C"):
        d = f"{Q.SRC}/gen/d36_{fmt}__{ck}"
        for f in sorted(os.listdir(d)):
            if f.startswith("gen_worker") and f.endswith(".jsonl"):
                pairs += [json.loads(ln) for ln in open(f"{d}/{f}") if ln.strip()]
check("D36 raw responses: 432", len(pairs) == 432, len(pairs))
mism = [r["request_id"] for r in pairs if (lambda s, ref: (s[1] if s[0] == "valid" else None) != ref)(S.parse_semantic(r["target"], r["fmt"], r["suffix_text_raw"], r["ended_eos"]),
                                                                                                    ref_semantic(r["target"], r["fmt"], r["suffix_text_raw"], r["ended_eos"]))]
check("semantic parser == independent reference on all 432 D36 raw responses", not mism, mism[:3])
# 합성 문자열 전수 비교
syn = ["yes", "No", "YES.", "no!", "yes.", "Normal", "normal.", "Abnormal!", "abnormal", "yes!!", "Normal ", " no", '{"answer":"yes"}', '{"answer": "no"}',
       '{"answer":"maybe"}', '{"answer":"yes","x":1}', "[]", "yes\nno", "no.", "N/A", "", "Yes, ", "The answer is yes"]
bad = []
for t in ("O", "A"):
    for f in ("plain", "json"):
        for x in syn:
            for eos in (True, False):
                s = S.parse_semantic(t, f, x + EOT if eos else x, eos)
                if (s[1] if s[0] == "valid" else None) != ref_semantic(t, f, x + EOT if eos else x, eos):
                    bad.append((t, f, x, eos))
check("semantic parser == reference on synthetic strings (2 targets x 2 fmts x eos)", not bad, bad[:3])

# ---- 2. D36 gate 산출 (실제 결과 파일)
g = json.load(open(f"{OUT}/d36/semantic_gate.json"))["decision"]
v = g["stats"]["semantic"]
check("D36 semantic: plain M0/B0/C valid A = 35/36, 36/36, 36/36 (원문 집계 예상과 일치)",
      [v[f"plain/{c}"]["A"]["valid"] for c in ("M0", "B0", "C")] == [35, 36, 36] and all(v[f"plain/{c}"]["O"]["valid"] == 36 for c in ("M0", "B0", "C")))
check("D36 gate: plain primary, json alternate, strict stats preserved (B0/C plain A strict 29/26)",
      g["primary_format"] == "plain" and g["stats"]["strict"]["plain/B0"]["A"]["valid"] == 29 and g["stats"]["strict"]["plain/C"]["A"]["valid"] == 26)
check("D36 conversion counts: 17 bare Normal/Abnormal (7+10) in plain A", g["conversion_counts"].get("plain/A/bare_normal_abnormal") == 17 and "plain/O/bare_normal_abnormal" not in g["conversion_counts"])

# ---- 3. 표본·요청 행렬
sets = json.load(open(f"{OUT}/manifests/sets.json"))
src_sets = json.load(open(f"{Q.SRC}/manifests/sets.json"))
check("sets.json identical to iter_015 (D36/E180/E600/P60/P180 order kept)", sets == src_sets)
check("D12 == first 4 per category of D36", all(sets["D12"][c] == sets["D36"][c][:4] for c in S.CATEGORIES))
check("E180 subset of E600, P60 subset of E180, P180==E180", all(sets["E180"][c] == sets["E600"][c][:60] and sets["P60"][c] == sets["E180"][c][:20] for c in S.CATEGORIES))
lab = json.load(open(f"{OUT}/manifests/labels.json"))
cfg, _ = qa_protocol.static_cfg()
for stage, n in (("d12_direct", 24), ("stress", 2)):
    rows = Q.load_rows(f"{OUT}/requests/{stage}__M0.jsonl", cfg)
    check(f"{stage} M0: {n} rows, verify_row ok, no category/GT keys, direct prompt has no box text",
          len(rows) == n and all(not ({"category", "boxes", "gt", "label"} & set(r)) and "box" not in r["prompt"].lower() for r in rows))
rows = Q.load_rows(f"{OUT}/requests/d12_direct__M0.jsonl", cfg)
cats = {c: len({r["id"] for r in rows if lab[r["id"]]["category"] == c}) for c in S.CATEGORIES}
check("d12_direct: category-first selection, 4 patients per category x 2 targets", cats == {c: 4 for c in S.CATEGORIES} and len(rows) == 24, cats)
ev = Q.load_rows(f"{OUT}/requests/d6_ev__M0.jsonl", cfg)
ecat = {c: len({r["id"] for r in ev if lab[r["id"]]["category"] == c}) for c in S.CATEGORIES}
check("d6_ev: 2 patients per category x 3 conditions x 2 targets = 36", len(ev) == 36 and ecat == {c: 2 for c in S.CATEGORIES}
      and {r["condition"] for r in ev} == {"ev_predicted", "ev_unavailable", "ev_oracle"}, (len(ev), ecat))
b0 = Q.bbox_records("B0")
okp = True
for r in ev:
    if r["condition"] == "ev_predicted":
        bx, st_ = Q.predicted_boxes(b0[r["id"]])
        okp &= r["prompt"].find(S.evidence_text("predicted", bx)) >= 0 and r["extra"]["source"] == "B0"
    if r["condition"] == "ev_oracle" and lab[r["id"]]["boxes"]:
        okp &= "Reference annotation boxes" in r["prompt"]
check("evidence prompts embed the exact B0 (predicted) / GT (oracle) boxes", okp)
check("stress request is the D36 M0 long-explanation patient", {r["id"] for r in Q.load_rows(f"{OUT}/requests/stress__M0.jsonl", cfg)} == {"val_00027331"})

# ---- 4. bbox 출처: 명시 목록, 충돌·중복·미완료 거부
check("bbox sources are explicit lists (no glob) and disjoint: M0 600, B0 600+12(D12), C 180+12(D12)+420(e600x)",
      len(Q.bbox_records("M0")) == 600 and len(Q.bbox_records("B0")) == 600 + 12 and len(Q.bbox_records("C")) == 180 + 12 + 420,
      (len(Q.bbox_records("M0")), len(Q.bbox_records("B0")), len(Q.bbox_records("C"))))
tdir = tempfile.mkdtemp(dir=f"{OUT}/tests")
rj = f"{tdir}/a.jsonl"
open(rj, "w").write(json.dumps({"id": "x", "suffix_text_raw": "[]", "ended_eos": True}) + "\n")
rj2 = f"{tdir}/b.jsonl"
open(rj2, "w").write(json.dumps({"id": "x", "suffix_text_raw": "[]", "ended_eos": True}) + "\n")
check("same id in two explicit sources rejected", raises(lambda: Q.bbox_records("M0", [("reuse", rj), ("reuse", rj2)]), Q.RequestError))
rj3 = f"{tdir}/c.jsonl"
open(rj3, "w").write(open(rj).read() * 2)
check("duplicate id inside one source rejected", raises(lambda: Q.bbox_records("M0", [("reuse", rj3)]), Q.RequestError))
check("gen source without completion.json rejected", raises(lambda: Q.bbox_records("C", [("gen", tdir)]), Q.RequestError))
man = json.load(open(f"{OUT}/reuse/reuse_manifest.json"))
check("reuse manifest: 9 old stages + M0/B0 bbox verified, set/label/hash checks recorded",
      len(man["stages"]) == 9 and set(man["bbox_reuse"]) == {"M0", "B0"} and man["manifests"]["_checks"]["n_images_hash_verified"] == 636)
check("reuse manifest records old (not re-locked) protocol digests", all(len(s["old_protocol_digest"]) == 64 for s in man["stages"].values()))

# ---- 5. 복구 소유권 (살아 있는 writer의 tail 보존, 죽은 writer의 tail 복구)
info = queue_lock.my_info(worker=9)
d5 = tempfile.mkdtemp(dir=f"{OUT}/tests")
good = json.dumps({"request_id": "a"}) + "\n"
tail = '{"request_id": "b", "x'
open(f"{d5}/gen_worker1.jsonl", "w").write(good + tail)
open(f"{d5}/gen_worker9.jsonl", "w").write(good)
holder = subprocess.Popen([sys.executable, "-c",
                           "import sys,time;from rsna_diag import queue_lock as q;lk,_,_=q.try_lock(sys.argv[1],q.my_info(worker=1));print('locked' if lk else 'FAIL',flush=True);time.sleep(60)",
                           f"{d5}/worker1.lock"], stdout=subprocess.PIPE, text=True)
try:
    check("holder process holds worker1.lock", holder.stdout.readline().strip() == "locked")
    before = open(f"{d5}/gen_worker1.jsonl", "rb").read()
    out_ = qa_gen.read_all_owned(d5, 9, True, False, info)  # repair 요청이 있어도 살아 있는 writer의 파일은 수정 금지
    check("live writer's partial tail is left untouched even with --repair-tail (read-only tolerate)",
          open(f"{d5}/gen_worker1.jsonl", "rb").read() == before and not os.path.exists(f"{d5}/gen_worker1.jsonl.partial") and len(out_[f"{d5}/gen_worker1.jsonl"]) == 1)
    check("live_workers() detects the surviving child lock", any("worker1.lock" in f for f, _ in qa_run.live_workers(d5)))
finally:
    holder.kill()
    holder.wait()
time.sleep(0.2)
check("no live worker after the holder died", not qa_run.live_workers(d5))
check("dead writer's tail without --repair-tail is an error", raises(lambda: qa_gen.read_all_owned(d5, 9, False, False, info), qa_gen.QAError))
recs_ = qa_gen.read_all_owned(d5, 9, True, False, info)
check("dead writer's tail quarantined (not deleted) when repair is requested and lock acquired",
      len(recs_[f"{d5}/gen_worker1.jsonl"]) == 1 and open(f"{d5}/gen_worker1.jsonl.partial").read().startswith(tail))
open(f"{d5}/gen_worker2.jsonl", "w").write(good + tail)
r_live = qa_gen.read_all_owned(d5, 9, False, True, info)
check("live=True read tolerates other tails and never repairs", len(r_live[f"{d5}/gen_worker2.jsonl"]) == 1 and open(f"{d5}/gen_worker2.jsonl").read().endswith("x"))
p_ = subprocess.Popen(["sleep", "300"])
p2_ = subprocess.Popen(["sleep", "300"])
fin = qa_run.stop_children([p_, p2_], grace=5)
check("stop_children terminates and reaps only given children", all(f["returncode"] is not None for f in fin) and p_.poll() is not None and p2_.poll() is not None, fin)

# ---- 6. 평가 계산: 독립 기준 구현과 대조
ids_c = {"opacity": ["o1", "o2", "o3"], "normal": ["n1", "n2"], "not_normal_no_opacity": ["x1", "x2", "x3", "x4"]}
ans = {"o1": ("yes", "yes"), "o2": ("yes", "no"), "o3": ("yes", "yes"), "n1": ("no", "no"), "n2": ("no", "no"), "x1": ("no", "yes"), "x2": ("no", "no"),
       "x3": ("no", "yes"), "x4": ("no", "yes")}
mk = lambda o, a: {"O": ("valid", o, True, 3), "A": ("valid", a, True, 3)}
tb = {("M", "direct", "plain", i): mk(*a) for i, a in ans.items()}
tb[("M", "direct", "plain", "n2")] = {"O": ("truncated", None, False, 1000), "A": ("valid", "no", True, 3)}
gt = {i: c for c, v in ids_c.items() for i in v}
vec = E.score_vectors(tb, "M", "direct", "plain", ids_c)
sc, per = E.s_scope(vec)
ref = {c: np.mean([tb[("M", "direct", "plain", i)]["O"][1] == S.GT_PAIR[c][0] and tb[("M", "direct", "plain", i)]["A"][1] == S.GT_PAIR[c][1] and tb[("M", "direct", "plain", i)]["O"][0] == "valid" for i in v]) for c, v in ids_c.items()}
check("S_scope equals independent reference (invalid=failure, category-equal average)", all(abs(per[c] - ref[c]) < 1e-12 for c in per) and abs(sc - np.mean(list(ref.values()))) < 1e-12, (per, ref))
check("require_complete passes when complete", E.require_complete(tb, ["M"], ["direct"], ["plain"], list(gt)))
tb2 = dict(tb)
del tb2[("M", "direct", "plain", "x4")]
check("require_complete rejects a missing patient", raises(lambda: E.require_complete(tb2, ["M"], ["direct"], ["plain"], list(gt)), qa_gen.QAError))
tb3 = dict(tb)
tb3[("M", "direct", "plain", "x4")] = {"O": ("valid", "no", True, 3)}
check("require_complete rejects a patient with one target only", raises(lambda: E.require_complete(tb3, ["M"], ["direct"], ["plain"], list(gt)), qa_gen.QAError))
tb4 = {**tb, ("M", "direct", "plain", "zz"): mk("yes", "yes")}
check("require_complete rejects extra patient", raises(lambda: E.require_complete(tb4, ["M"], ["direct"], ["plain"], list(gt)), qa_gen.QAError))
check("balanced_accuracy raises on a missing patient (no silent skip)", raises(lambda: E.balanced_accuracy(tb2, "M", "direct", "plain", "A", gt), KeyError))
check("pair_confusion raises on a missing patient", raises(lambda: E.pair_confusion(tb2, "M", "direct", "plain", gt), KeyError))
ba = E.balanced_accuracy(tb, "M", "direct", "plain", "A", gt)
ref_pos = np.mean([tb[("M", "direct", "plain", i)]["A"][1] == "yes" for i in gt if S.GT_PAIR[gt[i]][1] == "yes"])
ref_neg = np.mean([tb[("M", "direct", "plain", i)]["A"][1] == "no" for i in gt if S.GT_PAIR[gt[i]][1] == "no"])
check("balanced_accuracy(A) equals independent computation", abs(ba["balanced_accuracy"] - (ref_pos + ref_neg) / 2) < 1e-12 and ba["n_pos"] == 7 and ba["n_neg"] == 2, ba)
dup = raises(lambda: E.answer_table([({"target": "O", "fmt": "plain", "checkpoint": "M", "condition": "direct", "id": "a"}, {"suffix_text_raw": "yes" + EOT, "ended_eos": True, "n_output_tokens": 2})] * 2), qa_gen.QAError)
check("answer_table rejects a duplicated (ckpt,cond,fmt,id,target)", dup)

# ---- 7. bound·통계
tsem = {("a", "direct", "plain", "p1"): {"O": ("valid", "yes", True, 2), "A": ("valid", "yes", True, 2)},
        ("a", "direct", "plain", "p2"): {"O": ("truncated", None, False, 9), "A": ("valid", "yes", True, 2)},
        ("a", "direct", "plain", "p3"): {"O": ("valid", "no", True, 2), "A": ("truncated", None, False, 9)}}
lo, hi = SC.patient_bounds(tsem, ("a", "direct", "plain", "p1"), "opacity"), SC.patient_bounds(tsem, ("a", "direct", "plain", "p2"), "opacity")
lo3 = SC.patient_bounds(tsem, ("a", "direct", "plain", "p3"), "opacity")
check("patient bounds: all-correct=(1,1); one invalid other correct=(0,1); known wrong + invalid=(0,0)", lo == (1.0, 1.0) and hi == (0.0, 1.0) and lo3 == (0.0, 0.0), (lo, hi, lo3))
d0 = SC.discordant({"c": np.zeros(36)}, {"c": np.zeros(36)})
check("discordance k=0: exact one-sided 95% upper = 1-0.05^(1/n)", abs(d0["exact_one_sided_95_upper"] - (1 - 0.05 ** (1 / 36))) < 1e-12 and d0["discordant"] == 0, d0)
import math
d3 = SC.discordant({"c": np.array([1, 0, 0, 1, 1, 0, 0, 0, 0, 0.])}, {"c": np.zeros(10)})
u3 = d3["exact_one_sided_95_upper"]
cdf3 = sum(math.comb(10, j) * u3 ** j * (1 - u3) ** (10 - j) for j in range(4))
check("discordance k=3,n=10: Clopper-Pearson upper satisfies P(X<=3|p)=0.05 (~0.6066)", abs(cdf3 - 0.05) < 1e-9 and abs(u3 - 0.6066) < 1e-3, (u3, cdf3))
va = {"c1": np.array([1, 1, 0, 0.]), "c2": np.array([1, 0, 0, 0.]), "c3": np.array([0, 0, 0, 1.])}
vb = {"c1": np.array([0, 1, 0, 0.]), "c2": np.array([1, 1, 0, 0.]), "c3": np.array([0, 0, 0, 0.])}
se, sec = SC.paired_se(va, vb)
ref_se = np.sqrt(sum((np.std(va[c] - vb[c], ddof=1) / 2) ** 2 for c in va)) / 3
check("paired SE of S_scope difference = sqrt(sum se_c^2)/3", abs(se - ref_se) < 1e-12)
se2, _ = SC.paired_se(va, vb, n_target=16)
check("projected SE scales by sqrt(n/N)", abs(se2 - se * np.sqrt(4 / 16)) < 1e-12)
b = E.bootstrap_diff(va, vb, n=2000, ci=0.975)
check("bootstrap point equals mean(diff) and CI ordered", abs(b["S_scope"]["point"] - np.mean([va[c].mean() - vb[c].mean() for c in va])) < 1e-12 and b["S_scope"]["ci"][0] <= b["S_scope"]["ci"][1])

# ---- 8. 확대 규칙 (합성 입력)
mk_main = lambda pt, ci, flip=False, meets=False: {"point": pt, "ci97.5": ci, "bounds_can_flip": flip, "conservative_bounds": [pt - .01, pt + .01],
                                                   "projection": {"meets": meets, "halfwidth_975": .07}}
zero = {"B0-M0": {"diff": 0.0}, "C-B0": {"diff": 0.0}}
d = SC.decide_expand({"B0-M0": mk_main(0.12, [0.02, 0.22]), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, None, {})
check("expand when |S_scope diff|>=0.10", d["expand"] and d["reasons"])
d = SC.decide_expand({"B0-M0": mk_main(0.02, [-0.05, 0.05]), "C-B0": mk_main(0.0, [-0.05, 0.05])}, {"B0-M0": {"diff": -0.16}, "C-B0": {"diff": 0.0}}, None, {})
check("expand when NoOpacity/NotNormal pair accuracy diff <= -0.15", d["expand"])
d = SC.decide_expand({"B0-M0": mk_main(0.02, [-0.05, 0.05]), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, {"point": 0.12, "ci95": [0.0, 0.2], "projection": {"meets": True}}, {})
check("expand when evidence diff >= 0.10", d["expand"])
d = SC.decide_expand({"B0-M0": mk_main(0.02, [-0.05, 0.05]), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, None, {})
check("no expand when all inside thresholds and CI excludes +/-0.10", not d["expand"] and not d["reasons"])
d = SC.decide_expand({"B0-M0": mk_main(0.06, [-0.02, 0.14], meets=True), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, None, {})
check("expand when CI contains an important effect and projected precision meets target", d["expand"])
d = SC.decide_expand({"B0-M0": mk_main(0.06, [-0.02, 0.14], meets=False), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, None, {})
check("no expand when CI contains it but projected precision would not help", not d["expand"])
d = SC.decide_expand({"B0-M0": mk_main(0.12, [0.02, 0.22], flip=True), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, None, {})
check("hold when residual invalid can flip the conclusion", not d["expand"] and d["hold_reasons"])
d = SC.decide_expand({"B0-M0": mk_main(0.12, [0.02, 0.22]), "C-B0": mk_main(0.0, [-0.05, 0.05])}, zero, None, {"B0-M0": {"diff": -0.15}})
check("hold when json direction is importantly opposite", not d["expand"] and d["hold_reasons"])
check("flippable: bounds crossing 0.10 or sign", SC.flippable(0.12, 0.08, 0.16) and SC.flippable(0.0, -0.02, 0.02) is False and SC.flippable(0.05, -0.01, 0.11))

# ---- 9. protocol
p = f"{tdir}/p.json"
qa_protocol.create(p, [], "fixture")
check("iter016 protocol locks parser/eval/report/reuse/scope code", all(f in json.load(open(p))["locked"]["files"] for f in ("rsna_diag/qa_spec.py", "rsna_diag/qa_eval.py", "rsna_diag/qa_scope.py", "rsna_diag/qa_report.py", "rsna_diag/qa_reuse.py")))
old = json.load(open(f"{Q.SRC}/protocols/protocol_stage2.json"))
json.dump(old, open(f"{tdir}/old.json", "w"))
check("iter015 protocol rejected by iter016 verify (schema)", raises(lambda: qa_protocol.verify(f"{tdir}/old.json"), RuntimeError))

# ---- 10. 본평가 요청·원시 응답 독립 재계산 (E180 + E600 확대분)
import glob as _glob

STAGES = {"plain": ["e180_plain", "e600x_plain"], "json": ["p60_json", "p180x_json"]}
cfg_, _ = qa_protocol.static_cfg()
req_by_stage = {}
for st_, cks in (("e180_plain", ("M0", "B0", "C")), ("e600x_plain", ("M0", "B0", "C")), ("p60_json", ("M0", "B0", "C")), ("p180x_json", ("M0", "B0", "C")),
                 ("p60_ev", ("M0",)), ("p180x_ev", ("M0",)), ("e600x_bbox", ("C",))):
    for ck_ in cks:
        req_by_stage[(st_, ck_)] = Q.load_rows(f"{OUT}/requests/{st_}__{ck_}.jsonl", cfg_)
n_exp = {"e180_plain": 360, "e600x_plain": 840, "p60_json": 120, "p180x_json": 240, "p60_ev": 360, "p180x_ev": 720, "e600x_bbox": 420}
check("request counts per stage/ckpt as planned (1,800 E180 + 4,380 expansion = 6,180)",
      all(len(v) == n_exp[k[0]] for k, v in req_by_stage.items()) and sum(len(v) for v in req_by_stage.values()) == 1800 + 4380,
      sum(len(v) for v in req_by_stage.values()))
allrows = [r for v in req_by_stage.values() for r in v]
check("no request_id repeated across all stages (no overlap E180 vs expansion)", len({r["request_id"] for r in allrows}) == len(allrows))
e600ids = {i for c in S.CATEGORIES for i in sets["E600"][c]}
check("primary requests cover exactly E600 patients x 2 targets per checkpoint",
      all({(r["id"], r["target"]) for st_ in STAGES["plain"] for r in req_by_stage[(st_, ck_)]} == {(i, t) for i in e600ids for t in S.TARGETS} for ck_ in ("M0", "B0", "C")))
check("expansion requests exclude E180 patients", not ({r["id"] for r in req_by_stage[("e600x_plain", "M0")]} & {i for c in S.CATEGORIES for i in sets["E180"][c]}))
raw = {}
for (st_, ck_), rows_ in req_by_stage.items():
    d_ = f"{OUT}/gen/{st_}__{ck_}"
    recs_ = [json.loads(x) for f in sorted(_glob.glob(f"{d_}/gen_worker*.jsonl")) for x in open(f) if x.strip()]
    ids_ = [r["request_id"] for r in recs_]
    ok_ = (len(ids_) == len(set(ids_)) == len(rows_) and set(ids_) == {r["request_id"] for r in rows_} and all(r["ended_eos"] for r in recs_)
           and json.load(open(f"{d_}/completion.json"))["n_actual_unique"] == len(rows_))
    check(f"gen/{st_}__{ck_}: record set == request set, no duplicates, all EOS, completion.json", ok_)
    raw[(st_, ck_)] = {r["request_id"]: r for r in recs_}
rowmap = {r["request_id"]: r for r in allrows}
E6 = json.load(open(f"{OUT}/e600/report.json"))
gtcat = {i: lab[i]["category"] for i in e600ids}
ref_ok = {}
for ck_ in ("M0", "B0", "C"):
    ans_ = {}
    for st_ in STAGES["plain"]:
        for rid, rec_ in raw[(st_, ck_)].items():
            row_ = rowmap[rid]
            ans_[(row_["id"], row_["target"])] = ref_semantic(row_["target"], "plain", rec_["suffix_text_raw"], rec_["ended_eos"])
    ref_ok[ck_] = {i: float(ans_[(i, "O")] == S.GT_PAIR[gtcat[i]][0] and ans_[(i, "A")] == S.GT_PAIR[gtcat[i]][1]) for i in e600ids}
per_ref = {ck_: {c: float(np.mean([ref_ok[ck_][i] for i in sets["E600"][c]])) for c in S.CATEGORIES} for ck_ in ref_ok}
rep_ok = all(abs(E6["scores"][ck_]["semantic"]["per_category"][c] - per_ref[ck_][c]) < 1e-12 for ck_ in ref_ok for c in S.CATEGORIES)
check("E600 semantic per-category S_scope recomputed from raw records with the independent reference parser == report.json", rep_ok, per_ref)
sc_ref = {ck_: float(np.mean(list(per_ref[ck_].values()))) for ck_ in per_ref}
check("E600 S_scope (category-equal average) == report.json for M0/B0/C", all(abs(E6["scores"][ck_]["semantic"]["S_scope"] - sc_ref[ck_]) < 1e-12 for ck_ in sc_ref), sc_ref)
rng = np.random.default_rng(E.BOOT_SEED)
draw = []
for c in S.CATEGORIES:
    ids_c_ = sets["E600"][c]
    va_ = np.array([ref_ok["B0"][i] for i in ids_c_])
    vb_ = np.array([ref_ok["M0"][i] for i in ids_c_])
    idx_ = rng.integers(0, len(ids_c_), size=(E.BOOT_N, len(ids_c_)))
    draw.append(np.take(va_, idx_).mean(axis=1) - np.take(vb_, idx_).mean(axis=1))
tot_ = np.mean(draw, axis=0)
ci_ref = [float(np.percentile(tot_, 1.25)), float(np.percentile(tot_, 98.75))]
ci_rep = E6["main_semantic_plain_E180"]["B0-M0"]["ci97.5"]
check("B0-M0 97.5% patient-paired bootstrap CI recomputed independently == report.json", abs(ci_ref[0] - ci_rep[0]) < 1e-12 and abs(ci_ref[1] - ci_rep[1]) < 1e-12, (ci_ref, ci_rep))
ev_ref = {}
for st_ in ("p60_ev", "p180x_ev"):
    for rid, rec_ in raw[(st_, "M0")].items():
        row_ = rowmap[rid]
        ev_ref[(row_["condition"], row_["id"], row_["target"])] = ref_semantic(row_["target"], "plain", rec_["suffix_text_raw"], rec_["ended_eos"])
p180 = [i for c in S.CATEGORIES for i in sets["P180"][c]]
ev_sc = {cd: float(np.mean([np.mean([float(ev_ref[(cd, i, "O")] == S.GT_PAIR[lab[i]["category"]][0] and ev_ref[(cd, i, "A")] == S.GT_PAIR[lab[i]["category"]][1])
                                     for i in sets["P180"][c]]) for c in S.CATEGORIES])) for cd in ("ev_predicted", "ev_unavailable", "ev_oracle")}
er_ = E6["evidence_M0_P60"]["scores"]
check("evidence S_scope (P180) recomputed from raw records == report.json", all(abs(er_[cd]["S_scope"] - ev_sc[cd]) < 1e-12 for cd in ev_sc), ev_sc)
check("all E600/P180 requests are strict-parser + semantic-parser evaluated (both scores stored)", all("strict" in E6["scores"][c] and "semantic" in E6["scores"][c] for c in ("M0", "B0", "C")))

n_fail = sum(not r["pass"] for r in res)
json.dump({"n": len(res), "n_pass": len(res) - n_fail, "results": res}, open(f"{OUT}/tests/fixtures_iter016.json", "w"), indent=1)
print(f"{len(res) - n_fail}/{len(res)} passed")
sys.exit(1 if n_fail else 0)
