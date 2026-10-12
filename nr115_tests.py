"""iter_115 fixture: 유형 분류 경계, 원시 입력 변조 검출(stale PASS 방지), 기존 결과 덮어쓰기 거부."""
import json
import sys
import tempfile
from pathlib import Path

import nr115_core as K
import nr115_run as R
import nr115_verify as V

OUT = R.OUT
res = {}


def check(name, cond):
    res[name] = bool(cond)


B = lambda x0, y0, x1, y1: [x0, y0, x1, y1]
# ---- 분류 fixture
check("empty_pred", K.classify([], [B(.1, .1, .5, .5)]) == "empty_pred")
check("no_overlap", K.classify([B(.6, .6, .9, .9)], [B(.1, .1, .4, .4)]) == "no_overlap")
check("ALT_none_NA", K.classify([B(.1, .1, .4, .4)], []) == K.NA)
check("iou_ok", K.classify([B(.1, .1, .5, .5)], [B(.1, .1, .5, .5)]) == K.NON_ERR)
# 2개 GT 중 하나만 덮음: M=GT1 → IoU = 1/2 ≥0.3 이면 iou_ok. 3개 GT 중 하나만 덮으면 IoU=1/3→ok, 4개면 1/4 <0.3 → partial
g4 = [B(0, 0, .2, .2), B(.3, 0, .5, .2), B(.6, 0, .8, .2), B(.0, .5, .2, .7)]
check("partial_low_coverage", K.classify([g4[0]], g4) == "partial_low_coverage")
# 큰 예측: GT 하나(0.1x0.1)를 포함하는 큰 box → u=1, IoU=0.01/1.0 <0.3
check("large_pred_all_covered", K.classify([B(0, 0, 1, 1)], [B(.4, .4, .5, .5)]) == "all_covered_area_mismatch")
# 중첩 GT: 두 주석이 겹쳐도 u_j 원값 보존, 합집합 기반
ov = [B(0, 0, .5, .5), B(.25, .25, .75, .75)]
check("gt_overlap_flag", K.gt_boxes_overlap(ov) and not K.gt_boxes_overlap(g4))
# 0.3 경계: u 가 정확히 0.3 → 대응(≥). M=[0,0,0.3,1], GT=[0,0,1,1] u=0.3, IoU=0.3 → iou_ok(원 기준 <0.3 이 오류)
check("boundary_iou_0.3_is_ok", K.classify([B(0, 0, .3, 1)], [B(0, 0, 1, 1)]) == K.NON_ERR)
# u=0.29 단일 GT: IoU=0.29 → 오류, 겹침 양, u<0.3 → other_overlap
check("boundary_u_0.29_other", K.classify([B(0, 0, .29, 1)], [B(0, 0, 1, 1)]) == "other_overlap")
# 단일 GT 에서는 partial_low_coverage 로 분류되지 않는다
check("single_gt_never_partial", K.classify([B(0, 0, .29, 1), B(.8, .8, .9, .9)], [B(0, 0, 1, 1)]) != "partial_low_coverage")
# 독립 구현과 일치(합성 무작위 200개)
import random
rnd = random.Random(115)


def rb():
    x0, y0 = rnd.random() * .8, rnd.random() * .8
    return B(x0, y0, x0 + .05 + rnd.random() * (.95 - x0 - .05 + .05) * .5, y0 + .05 + rnd.random() * .3)


ok = True
for _ in range(200):
    m = [rb() for _ in range(rnd.randint(0, 3))]
    g = [rb() for _ in range(rnd.randint(0, 4))]
    m = [[a, b, min(c, 1), min(d, 1)] for a, b, c, d in m]
    g = [[a, b, min(c, 1), min(d, 1)] for a, b, c, d in g]
    if K.classify(m, g) != V.gtype(m, g):
        ok = False
check("random200_core_vs_independent_grid", ok)

# ---- 원시 입력 변조 검출 (stale PASS): 원시 worker 파일 hash 만 틀리게 하면 verify_final PASS 와 무관하게 problem 발생
real_sha = R.sha
prov, probs = R.provenance()
check("provenance_clean_on_real_inputs", probs == [])
check("verify_final_all_pass_is_true_stale_candidate", prov["verify_final_all_pass"] is True)


def tamper_sha(p):
    return "0" * 64 if str(p).endswith("raw_worker0.jsonl") and "INIT_A" in str(p) else real_sha(p)


R.sha = tamper_sha
_, probs2 = R.provenance()
R.sha = real_sha
check("tampered_raw_detected_despite_stale_pass", any("raw input digest" in p for p in probs2))


def tamper_ledger(p):
    return "1" * 64 if str(p).endswith("ledger_final.json") else real_sha(p)


R.sha = tamper_ledger
_, probs3 = R.provenance()
R.sha = real_sha
check("tampered_ledger_detected", any("ledger_final" in p for p in probs3))

# ---- 덮어쓰기 거부·중단 후 재개(기존 완료 파일 보존)
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "x.json"
    R.wjson(p, {"a": 1})
    try:
        R.wjson(p, {"a": 2})
        refused = False
    except SystemExit:
        refused = True
    check("overwrite_refused", refused and json.loads(p.read_text()) == {"a": 1})
    # 같은 입력으로 재실행해도 기존 결과를 보존(다시 쓰지 않고 digest 대조는 seal 이 수행)
    check("no_tmp_left", not list(Path(td).glob("*.tmp")))

out = {"all_pass": all(res.values()), "n": len(res), "checks": res}
(OUT / "tests").mkdir(parents=True, exist_ok=True)
tp = OUT / "tests/fixtures.json"
if tp.exists():
    print("fixtures.json exists; not overwriting")
else:
    tp.write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
sys.exit(0 if out["all_pass"] else 1)
