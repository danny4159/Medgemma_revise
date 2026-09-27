"""iter_018 CPU 회귀 검사. 사용: python test_rsna_iter018.py results/iter_018/tests/fixtures_iter018.json"""
import hashlib
import json
import math
import os
import sys
import tempfile

import numpy as np
import pandas as pd
from PIL import Image

from rsna_diag import cx18_analysis as A, cx18_data as D, cx18_spec as CX, qa_requests as Q

RES = []


def check(name, cond, detail=""):
    RES.append({"name": name, "pass": bool(cond), "detail": str(detail)[:400]})


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return True, str(e)[:200]
    return False, ""


# --- cx18_spec: 질문·evidence·정답
check("question text", CX.question("PE", "plain") == "Is pleural effusion present in this chest radiograph? Answer only yes or no.")
q, ev = CX.prompt_and_evidence("main", "D", "plain", "absent_absent")
check("D has no evidence digest", ev is None)
check("D prompt is bare question", q == CX.question("PE", "plain"))
q, ev = CX.prompt_and_evidence("main", "U", "plain", "present_present")
check("U mentions unavailable", "Result: unavailable." in q and ev is not None)
check("U prompt ends with question", q.endswith(CX.question("PE", "plain")))
q, ev = CX.prompt_and_evidence("main", "T", "plain", "present_absent")
check("T uses actual cardiomegaly value (present)", "considered cardiomegaly. Result: present." in q)
q2, ev2 = CX.prompt_and_evidence("main", "T", "plain", "absent_present")
check("T uses actual cardiomegaly value (absent)", "considered cardiomegaly. Result: absent." in q2)
check("T evidence digest differs by ref value", ev != ev2)
q, ev = CX.prompt_and_evidence("main", "Tscope", "plain", "present_absent")
check("Tscope adds scope sentence", "concerns only cardiomegaly" in q and "Assess pleural effusion from the image." in q)
check("Tscope does not leak pleural effusion truth", "considered pleural effusion" not in q)
# 역방향: 이름 교환
q, ev = CX.prompt_and_evidence("aux", "Tscope", "plain", "present_absent")
check("aux question asks cardiomegaly", q.strip().startswith("A separate assessment") and "Is cardiomegaly present" in q)
check("aux Tscope references pleural effusion (swapped)", "considered pleural effusion" in q and "concerns only pleural effusion" in q)
check("aux does not leak cardiomegaly truth text via ref", "considered cardiomegaly" not in q)

check("gt_answer main uses PE", CX.gt_answer("main", "present_present") == "yes" and CX.gt_answer("main", "absent_present") == "yes"
      and CX.gt_answer("main", "present_absent") == "no" and CX.gt_answer("main", "absent_absent") == "no")
check("gt_answer aux uses CM", CX.gt_answer("aux", "present_absent") == "yes" and CX.gt_answer("aux", "absent_absent") == "no")
check("ref_value main uses CM", CX.ref_value("main", "present_absent") == "present" and CX.ref_value("main", "absent_present") == "absent")
check("ref_value aux uses PE", CX.ref_value("aux", "present_absent") == "absent" and CX.ref_value("aux", "absent_present") == "present")
check("bad category rejected", raises(lambda: CX.cat_values("weird"), ValueError)[0])
check("bad ref_val rejected for T", raises(lambda: CX.evidence_sentence("T", "CM", "PE", "maybe"), ValueError)[0])

# --- split_patients: 결정적, 중복 없음, D<E<F, 정확한 개수
cats = {"absent_absent": [f"p{i}" for i in range(30)], "present_absent": [f"q{i}" for i in range(24)]}
s1 = CX.split_patients(cats)
s2 = CX.split_patients(cats)
check("split deterministic", s1 == s2)
for c in cats:
    d16, e48, f = set(s1["D16"][c]), set(s1["E48"][c]), set(s1["F"][c])
    check(f"split sizes {c}", len(d16) == 4 and len(e48) == 12)
    check(f"split disjoint {c}", not (d16 & e48) and not (d16 & f) and not (e48 & f))
    check(f"split covers all {c}", d16 | e48 | f == set(cats[c]))
check("split rejects duplicate id", raises(lambda: CX.split_patients({"absent_absent": ["p1", "p1"]}), ValueError)[0])

# --- cx18_data: cross_check, study grouping, dedup, label encoding gate
def mkrow(path, cm, pe, ap_pa=0, extra=None):
    base = {"Path": path, "AP/PA": ap_pa, "Cardiomegaly": cm, "Pleural Effusion": pe, "Lung Opacity": 2, "Edema": 2,
            "Atelectasis": 2, "Consolidation": 2, "Pneumothorax": 2}
    if extra:
        base.update(extra)
    return base


hf_rows = [
    mkrow("CheXpert-v1.0-small/valid/patient00001/study1/view1_frontal.jpg", 3, 2),
    mkrow("CheXpert-v1.0-small/valid/patient00002/study1/view1_frontal.jpg", 2, 3),
    mkrow("CheXpert-v1.0-small/valid/patient00003/study1/view1_frontal.jpg", 3, 3),
    mkrow("CheXpert-v1.0-small/valid/patient00004/study1/view1_lateral.jpg", 2, 2),   # lateral-only study -> excluded
    mkrow("CheXpert-v1.0-small/valid/patient00005/study1/view1_frontal.jpg", 2, 2),
    mkrow("CheXpert-v1.0-small/valid/patient00005/study1/view2_lateral.jpg", 2, 2),   # 2-view study -> excluded
]
hf = pd.DataFrame(hf_rows)
csv_by_path = {r["Path"]: {"Path": r["Path"], "Cardiomegaly": 1.0 if r["Cardiomegaly"] == 3 else 0.0,
                            "Pleural Effusion": 1.0 if r["Pleural Effusion"] == 3 else 0.0, "Lung Opacity": 0.0,
                            "Edema": 0.0, "Atelectasis": 0.0, "Consolidation": 0.0, "Pneumothorax": 0.0} for r in hf_rows}
cross = D.cross_check(hf, csv_by_path)
check("cross_check ok on consistent synthetic data", cross["n_images"] == 6)
bad_csv = dict(csv_by_path)
p0 = hf_rows[0]["Path"]
bad_csv[p0] = dict(bad_csv[p0], Cardiomegaly=0.0)   # HF present(3) vs CSV absent(0.0) mismatch
check("cross_check rejects label mismatch", raises(lambda: D.cross_check(hf, bad_csv), D.DataGateError)[0])
missing_csv = {k: v for k, v in csv_by_path.items() if k != p0}
check("cross_check rejects missing Path", raises(lambda: D.cross_check(hf, missing_csv), D.DataGateError)[0])
uncertain_csv = dict(csv_by_path)
hf2 = hf.copy()
hf2.loc[hf2["Path"] == p0, "Cardiomegaly"] = 1  # uncertain code, not absent/present
check("cross_check rejects non-absent/present HF code", raises(lambda: D.cross_check(hf2, csv_by_path), D.DataGateError)[0])

studies = D.group_studies(hf)
check("group_studies count", len(studies) == 5)
single, dropped = D.select_single_frontal(studies)
check("select_single_frontal picks frontal-only single-view studies", set(single) == {"patient00001", "patient00002", "patient00003"})
check("select_single_frontal drops lateral-only and multi-view", "patient00004" not in single and "patient00005" not in single)
check("select_single_frontal no dropped-multi-study in this fixture", dropped == [])

# 동일 환자 두 study(둘 다 single frontal) -> study명 정렬로 첫 study만
hf3 = pd.DataFrame(hf_rows[:3] + [mkrow("CheXpert-v1.0-small/valid/patient00001/study2/view1_frontal.jpg", 2, 2)])
studies3 = D.group_studies(hf3)
single3, dropped3 = D.select_single_frontal(studies3)
check("multi-study patient picks first study by name", single3["patient00001"][0] == "study1")
check("multi-study patient flagged", dropped3 == ["patient00001"])
check("bad path format rejected", raises(lambda: D.group_studies(pd.DataFrame([mkrow("weird/path.jpg", 2, 2)])), D.DataGateError)[0])

# ahash dedup: 동일 영상은 거리 0(중복 경보), 완전히 다른 노이즈 영상은 먼 거리
rng = np.random.default_rng(0)
im_a = Image.fromarray((rng.random((64, 64)) * 255).astype("uint8"), mode="L")
buf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
im_a.save(buf.name)
im_b = Image.fromarray(np.zeros((64, 64), dtype="uint8"), mode="L")   # 전혀 다른 영상(상수 검정)
h_a, h_b = D.ahash(im_a), D.ahash(im_b)
check("ahash same image distance 0", int((h_a != h_a).sum()) == 0)
check("ahash different image distance > threshold", int((h_a != h_b).sum()) >= D.DEDUP_HAMMING_THRESHOLD)
os.unlink(buf.name)

# --- cx18_requests: row 생성·재검증·oracle 누출 방지
labels = {"p1": {"category": "present_absent", "path": "x", "study": "s", "view": "v", "ap_pa": 0,
                 "cardiomegaly": "present", "pleural_effusion": "absent", "file_sha256": "f" * 64, "pixel_sha256": "g" * 64}}
man = {"p1": {"id": "p1", "split": "present_absent", "image": "img.jpg", "file_sha256": "f" * 64, "pixel_sha256": "g" * 64}}
from rsna_diag import qa_protocol as QP
cfg, _ = QP.static_cfg()
from rsna_diag import cx18_requests as CR
rows = CR.build_rows(["p1"], labels, man, "plain", "test_stage", cfg)
check("8 rows per patient", len(rows) == 8)
ids = {r["request_id"] for r in rows}
check("8 unique request ids", len(ids) == 8)
for r in rows:
    ok = Q.verify_row(r, cfg)
    check(f"verify_row ok {r['target']}:{r['condition']}", ok)
d_rows = [r for r in rows if r["condition"] == "D"]
check("D rows have no evidence digest", all(r["evidence_digest"] is None for r in d_rows))
tscope_main = [r for r in rows if r["target"] == "main" and r["condition"] == "Tscope"][0]
check("Tscope(main) prompt reveals only cardiomegaly (present), not pleural effusion", "considered cardiomegaly. Result: present." in tscope_main["prompt"]
      and "considered pleural effusion" not in tscope_main["prompt"].lower())
check("Tscope(main) prompt does not assert a pleural effusion result (only the generic scope caveat)",
      "pleural effusion. result:" not in tscope_main["prompt"].lower())
check("mismatched split rejected", raises(lambda: CR.build_rows(["p1"], {"p1": dict(labels["p1"], category="absent_absent")}, man, "plain", "s2", cfg),
                                           Q.RequestError)[0])

# --- cx18_analysis: clopper_pearson·exp_half_width·bootstrap·flips
lo, hi = A.clopper_pearson(0, 10)
check("clopper_pearson k=0 lower is 0", lo == 0.0 and hi > 0)
lo, hi = A.clopper_pearson(10, 10)
check("clopper_pearson k=n upper is 1", hi == 1.0 and lo < 1.0)
lo, hi = A.clopper_pearson(5, 10)
check("clopper_pearson symmetric case brackets 0.5", lo < 0.5 < hi)
# 알려진 값 대조 (Clopper-Pearson 95% CI for 5/10 는 대략 [0.1871, 0.8129])
check("clopper_pearson 5/10 matches known reference", abs(lo - 0.1871) < 0.01 and abs(hi - 0.8129) < 0.01, (lo, hi))

hw, detail = A.expected_half_width({"c": 0}, {"c": 12}, {"c": 56})
check("expected_half_width zero-discordant still positive (smoothing)", hw > 0)
hw2, _ = A.expected_half_width({"c": 6}, {"c": 12}, {"c": 56})
check("expected_half_width increases with discordant rate", hw2 > hw)

vec_a = {"c1": np.array([1.0, 1.0, 1.0, 1.0]), "c2": np.array([1.0, 1.0, 1.0, 1.0])}
vec_b = {"c1": np.array([1.0, 1.0, 1.0, 1.0]), "c2": np.array([1.0, 1.0, 1.0, 1.0])}
boot = A.paired_diff_bootstrap(vec_a, vec_b, n=200, seed=1)
check("degenerate bootstrap all zero", boot["point"] == 0.0 and boot["ci"] == [0.0, 0.0])
vec_c = {"c1": np.array([1.0, 1.0, 0.0, 0.0])}
boot2 = A.paired_diff_bootstrap(vec_c, {"c1": np.array([0.0, 0.0, 0.0, 0.0])}, n=200, seed=1)
check("nonzero paired diff bootstrap point", abs(boot2["point"] - 0.5) < 1e-9)

cbound = A.conservative_macro_diff_bound({"c1": 0, "c2": 0}, {"c1": 0, "c2": 0}, {"c1": 12, "c2": 12})
check("conservative bound is non-degenerate (not exactly [0,0])", cbound["macro_bound"][0] != 0.0 or cbound["macro_bound"][1] != 0.0, cbound["macro_bound"])
check("conservative bound centered near 0", abs((cbound["macro_bound"][0] + cbound["macro_bound"][1]) / 2) < 0.2)

tab = {("main", "D", "plain", "p1"): {"status": "valid", "answer": "yes", "ended_eos": True, "n_out": 1},
       ("main", "Tscope", "plain", "p1"): {"status": "valid", "answer": "no", "ended_eos": True, "n_out": 1},
       ("main", "D", "plain", "p2"): {"status": "valid", "answer": "no", "ended_eos": True, "n_out": 1},
       ("main", "Tscope", "plain", "p2"): {"status": "truncated", "answer": None, "ended_eos": False, "n_out": 999}}
labels2 = {"p1": {"category": "absent_present"}, "p2": {"category": "absent_absent"}}
neg, pos = A.flips(tab, "main", "D", "Tscope", "plain", ["p1", "p2"], labels2)
check("negative flip detected (correct->wrong, incl. correct->truncated)", neg == ["p1", "p2"] and pos == [])
vb = A.valid_both(tab, "main", "D", "Tscope", "plain", ["p1", "p2"])
check("valid_both excludes truncated", vb == ["p1"])

want = {("main", "D", "plain", "p1"), ("main", "Tscope", "plain", "p1")}
check("require_complete passes on exact set", A.require_complete({k: v for k, v in tab.items() if k in want}, ["main"], ["D", "Tscope"], "plain", ["p1"]))
check("require_complete rejects missing", raises(lambda: A.require_complete({}, ["main"], ["D"], "plain", ["p1"]), A.AnalysisError)[0])
dup_pairs = [({"target": "main", "condition": "D", "fmt": "plain", "id": "p1"}, {"suffix_text_raw": "yes<end_of_turn>", "ended_eos": True, "n_output_tokens": 1})] * 2
check("answer_table rejects duplicate request", raises(lambda: A.answer_table(dup_pairs), A.AnalysisError)[0])

n_pass = sum(r["pass"] for r in RES)
out = {"n": len(RES), "passed": n_pass, "results": RES}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(f"{n_pass}/{len(RES)} passed")
for r in RES:
    if not r["pass"]:
        print("FAIL", r["name"], r["detail"])
sys.exit(0 if n_pass == len(RES) else 1)
