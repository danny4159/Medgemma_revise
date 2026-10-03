"""iter_058: 공식 HD-GLIO v2.0 predict_from_folder 호출 wrapper (venv hdglio58의 python으로 실행).
설정은 공식 hd_glio_predict_folder와 동일: fold (0,), TTA 사용(tta=True), mixed precision 기본값, checkpoint model_final_checkpoint.
case 단위 shard를 입력 폴더 하위 symlink 없이 case 목록 파일로 받아 임시 폴더에 hard-link하여 호출한다.
사용: HD_GLIO_PARAMS=... CUDA_VISIBLE_DEVICES=k hdglio58 python hdglio58_pred.py IN_DIR OUT_DIR CASE_LIST.json TIMING.json
출력: OUT_DIR/{case}.nii.gz (label 0/1/2), TIMING.json: 단계별 wall(sync) 기록
"""
import json
import os
import shutil
import sys
import time

import torch

from hd_glio.paths import folder_with_parameter_files
from nnunet.inference.predict import predict_from_folder


def main():
    in_dir, out_dir, case_json, timing = sys.argv[1:5]
    cases = json.load(open(case_json))
    procs = int(os.environ.get("HDG_PROCS", "2"))
    assert os.path.isdir(folder_with_parameter_files), folder_with_parameter_files
    work = out_dir + ".in_tmp"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    os.makedirs(out_dir, exist_ok=True)
    for c in cases:
        for s in ("0000", "0001", "0002", "0003"):
            os.link(f"{in_dir}/{c}_{s}.nii.gz", f"{work}/{c}_{s}.nii.gz")
    t0 = time.time()
    predict_from_folder(folder_with_parameter_files, work, out_dir, (0,), False, procs, procs, None, 0, 1, True,
                        overwrite_existing=True, checkpoint_name="model_final_checkpoint")
    torch.cuda.synchronize()
    t1 = time.time()
    shutil.rmtree(work, ignore_errors=True)
    json.dump({"cases": cases, "t_start": t0, "t_end": t1, "wall_s": t1 - t0, "procs": procs,
               "peak_alloc_MiB": torch.cuda.max_memory_allocated() / 2**20,
               "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20,
               "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")}, open(timing, "w"), indent=1)
    print("done", len(cases), t1 - t0)


if __name__ == "__main__":
    main()
