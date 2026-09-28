"""iter_021 mi19_manifest.check_coregistration 검사: 부동소수 잡음(0.9999999999999999 vs 1.0)은
통과시키고 실제 방향 불일치(다른 부호/축)는 여전히 DataQualityError로 거부하는지 확인한다.
이 검사는 실제 195명 gate 중 21명이 direction 필드의 정확 일치(==) 비교 때문에 잘못
제외됐던 버그의 회귀 방지용이다."""
import json

from rsna_diag import mi19_manifest as MAN

RESULT_DIR = "results/iter_021/tests"
results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def base_hdr():
    return {"dim_size_xyz": [512, 512, 17], "spacing_xyz": [1.0, 1.0, 4.0], "offset_xyz": [1.0, 2.0, 3.0],
            "direction": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]}


def test_float_noise_direction_accepted():
    mask_hdr = base_hdr()
    img_meta = base_hdr()
    img_meta["direction"] = [[0.9999999999999999, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    try:
        MAN.check_coregistration(mask_hdr, img_meta, "p1")
        check("float_noise_direction_accepted", True)
    except MAN.DataQualityError as e:
        check("float_noise_direction_accepted", False, str(e))


def test_real_direction_mismatch_rejected():
    mask_hdr = base_hdr()
    img_meta = base_hdr()
    img_meta["direction"] = [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]  # swapped axes, real mismatch
    try:
        MAN.check_coregistration(mask_hdr, img_meta, "p2")
        check("real_direction_mismatch_rejected", False)
    except MAN.DataQualityError:
        check("real_direction_mismatch_rejected", True)


def test_dimsize_mismatch_still_rejected():
    mask_hdr = base_hdr()
    img_meta = base_hdr()
    img_meta["dim_size_xyz"] = [512, 512, 18]
    try:
        MAN.check_coregistration(mask_hdr, img_meta, "p3")
        check("dimsize_mismatch_rejected", False)
    except MAN.DataQualityError:
        check("dimsize_mismatch_rejected", True)


def test_exact_match_accepted():
    mask_hdr = base_hdr()
    img_meta = base_hdr()
    try:
        MAN.check_coregistration(mask_hdr, img_meta, "p4")
        check("exact_match_accepted", True)
    except MAN.DataQualityError as e:
        check("exact_match_accepted", False, str(e))


for fn in [test_float_noise_direction_accepted, test_real_direction_mismatch_rejected,
           test_dimsize_mismatch_still_rejected, test_exact_match_accepted]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
out = {"n": len(results), "n_pass": n_pass, "results": results}
print(json.dumps(out, indent=1, default=str))
import os
os.makedirs(RESULT_DIR, exist_ok=True)
json.dump(out, open(f"{RESULT_DIR}/fixtures_manifest021.json", "w"), indent=1, default=str)
assert n_pass == len(results), "some fixtures failed"
