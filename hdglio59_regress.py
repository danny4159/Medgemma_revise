"""iter_059: 기존 E48 정확도 결과의 불변성 확인과 정확도 세 조건 재현 (CPU only, 새 생성·학습 0).
python hdglio59_regress.py results/iter_059/regress
- iter_058 고정 입력/출력 hash를 protocol과 대조 -> GT 중복·case/split 검사 -> hdglio58_eval.run을 새 경로에 재실행 -> iter_058 report와 비교.
- 과거 보고서는 수정하지 않는다. 정정값(FN 600 voxel 미만 개수, 단일 worker D6 launch wall)은 원자료에서 계산해 출처와 함께 기록한다.
"""
import json
import sys

import hdglio59_common as C
import hdglio58_eval as E

OLD = "results/iter_058/eval_E/report.json"


def main():
    out = sys.argv[1]
    lk = json.load(open("results/iter_059/protocol.json"))
    C.check_locked(lk["iter058_fixed"], {f: C.sha_file(f) for f in lk["iter058_fixed"]})
    cs = json.load(open("results/iter_056/data/cases.json"))["chosen"]
    gt_rows = json.load(open("results/iter_056/data/gt_slabs.json"))["rows"]
    C.check_gt_rows(gt_rows, cs, "E")
    C.check_gt_rows(gt_rows, cs, "D")
    E.run("E", "E_main", out)
    new, old = json.load(open(f"{out}/report.json")), json.load(open(OLD))
    keys = ["HD.BA_all", "U8.BA_all", "HD-U8.BA_all", "HD-U8.sens", "HD-U8.spec"]
    same = {k: new["bootstrap"]["ci95_lo_hi_nvalid"][k] == old["bootstrap"]["ci95_lo_hi_nvalid"][k] for k in keys}
    same["point_equal"] = all(new["point"][a][m] == old["point"][a][m] for a in ("HD", "U8") for m in ("BA", "sens", "spec", "TP", "FN", "TN", "FP"))
    d = new["diff_point"]
    ci = new["bootstrap"]["ci95_lo_hi_nvalid"]["HD-U8.BA_all"]
    cond = {"ba_diff_ge_0.05": d["BA_all"] >= 0.05, "ci_lo_gt_0": ci[0] > 0, "sens_diff_ge_-0.05": d["sens"] >= -0.05}
    fn = new["errors"]["FN_ann_voxels"]
    small = sorted(k for k, v in fn.items() if v < 600)
    launch = json.load(open("results/iter_058/hd/run_D_1w/launch.json"))
    res = {"invariance": "iter058_fixed hashes match protocol", "gt_checks": "no duplicate key; case/split sets consistent (D, E)",
           "reproduced_equal_to_iter058": same, "BA": {k: new["point"][k]["BA"] for k in ("HD", "U8")}, "diff_point": d, "ci95_BA_diff": ci,
           "accuracy_conditions": cond, "accuracy_conditions_all": all(cond.values()),
           "correction_FN_total": len(fn), "correction_FN_lt_600_voxels": len(small), "correction_FN_lt_600_ids": small,
           "correction_source_FN": f"{out}/report.json errors.FN_ann_voxels",
           "correction_single_worker_D6_launch_wall_s": launch["wall_s"], "correction_source_wall": "results/iter_058/hd/run_D_1w/launch.json"}
    C.atomic_json(f"{out}/regress.json", res)
    print(json.dumps(res, indent=1))
    if not (all(same.values()) and res["accuracy_conditions_all"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
