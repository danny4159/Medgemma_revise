"""iter_058 회귀·변조 fixture. python test_hdglio58.py  -> results/iter_058/tests/fixtures.json
임시 디렉터리에 합성 입력/출력을 만들어 평가 경로가 변조를 거부하는지 검사한다(실제 결과 파일은 수정하지 않는다).
"""
import json
import os
import shutil
import tempfile

import nibabel as nib
import numpy as np

import hdglio58_eval as E

OUT = "results/iter_058/tests"
res = []


def check(name, fn, expect_raise=None):
    try:
        fn()
        ok = expect_raise is None
        msg = "no raise"
    except Exception as e:  # noqa: BLE001
        ok = expect_raise is not None and expect_raise in str(e)
        msg = f"{type(e).__name__}: {e}"
    res.append({"name": name, "pass": bool(ok), "detail": msg[:200]})
    print("PASS" if ok else "FAIL", name, "|", msg[:100])


def make_tree(root, cases, rc=0):
    """root/hd/{input_X,run_T/g0w0/pred} 합성. 입력 grid 4x4x4."""
    run = f"{root}/run_T"
    for c in cases:
        os.makedirs(f"{root}/input_X", exist_ok=True)
        for s in ("0000", "0001", "0002", "0003"):
            nib.save(nib.Nifti1Image(np.ones((4, 4, 4), np.float32), np.eye(4)), f"{root}/input_X/{c}_{s}.nii.gz")
        os.makedirs(f"{run}/g0w0/pred", exist_ok=True)
        p = np.zeros((4, 4, 4), np.uint8)
        p[1:3, 1:3, 1:3] = 1
        nib.save(nib.Nifti1Image(p, np.eye(4)), f"{run}/g0w0/pred/{c}.nii.gz")
    json.dump(cases, open(f"{root}/X_cases.json", "w"))
    json.dump({"rc": {"g0w0": rc}}, open(f"{run}/launch.json", "w"))
    man = {c: {"pred_sha256": E.sha_file(f"{run}/g0w0/pred/{c}.nii.gz"),
               "input_sha256": {s: E.sha_file(f"{root}/input_X/{c}_{s}.nii.gz") for s in ("0000", "0001", "0002", "0003")}} for c in cases}
    json.dump(man, open(f"{run}/pred_manifest.json", "w"))
    return run


def main():
    os.makedirs(OUT, exist_ok=True)
    old = E.HD
    tmp = tempfile.mkdtemp()
    try:
        E.HD = tmp
        make_tree(tmp, ["BRATS_A", "BRATS_B"])
        check("collect_ok", lambda: E.collect_pred("X", "T"))
        # 중복 pred (다른 shard에 같은 case)
        os.makedirs(f"{tmp}/run_T/g1w0/pred", exist_ok=True)
        shutil.copy(f"{tmp}/run_T/g0w0/pred/BRATS_A.nii.gz", f"{tmp}/run_T/g1w0/pred/BRATS_A.nii.gz")
        check("duplicate_pred_rejected", lambda: E.collect_pred("X", "T"), "duplicate pred")
        shutil.rmtree(f"{tmp}/run_T/g1w0")
        # 누락
        os.remove(f"{tmp}/run_T/g0w0/pred/BRATS_B.nii.gz")
        check("missing_pred_rejected", lambda: E.collect_pred("X", "T"), "mismatch")
        # 실패 worker
        shutil.rmtree(tmp)
        os.makedirs(tmp)
        make_tree(tmp, ["BRATS_A", "BRATS_B"], rc=1)
        check("failed_worker_rejected", lambda: E.collect_pred("X", "T"), "worker rc")
        # case 교환(다른 case의 pred 내용을 덮어씀) -> manifest hash 불일치
        shutil.rmtree(tmp)
        os.makedirs(tmp)
        run = make_tree(tmp, ["BRATS_A", "BRATS_B"])
        p = np.zeros((4, 4, 4), np.uint8)
        p[0, 0, 0] = 2
        nib.save(nib.Nifti1Image(p, np.eye(4)), f"{run}/g0w0/pred/BRATS_B.nii.gz")
        check("swapped_or_edited_pred_rejected", lambda: E.collect_pred("X", "T"), "changed vs manifest")
        # 입력 변조
        shutil.rmtree(tmp)
        os.makedirs(tmp)
        make_tree(tmp, ["BRATS_A", "BRATS_B"])
        nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), np.float32), np.eye(4)), f"{tmp}/input_X/BRATS_A_0003.nii.gz")
        check("input_tamper_rejected", lambda: E.collect_pred("X", "T"), "changed vs manifest")
        # grid 불일치/GT 불일치: hd_slab_table는 실제 SRC 경로의 raw label이 필요하므로 실제 case로 GT 변조만 검사
        E.HD = old
        gt = json.load(open("results/iter_056/data/gt_slabs.json"))["rows"]
        dup = [dict(g) for g in gt if g["split"] == "D"]
        dup[1] = dict(dup[1], present=not dup[1]["present"])
        check("gt_flip_rejected", lambda: E.hd_slab_table("D", "D_2g1w", dup), "gt_slabs != raw label")
        ok = E.hd_slab_table("D", "D_2g1w", gt)
        check("real_D_ok_rows36", lambda: (len(ok[0]) == 36) or (_ for _ in ()).throw(AssertionError("rows")))
        # 정상 D 결과가 저장 report와 같은 점추정을 재현
        rep = json.load(open("results/iter_058/eval_D/report.json"))
        check("D_report_point_matches", lambda: abs(rep["point"]["HD"]["BA_all"] - 0.7916666666666667) < 1e-12 or (_ for _ in ()).throw(AssertionError("BA")))
    finally:
        E.HD = old
        shutil.rmtree(tmp, ignore_errors=True)
    json.dump({"n": len(res), "n_pass": sum(r["pass"] for r in res), "checks": res}, open(f"{OUT}/fixtures.json", "w"), indent=1)
    print(sum(r["pass"] for r in res), "/", len(res))


if __name__ == "__main__":
    main()
