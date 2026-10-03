"""iter_058: 공식 hd_glio_predict(단일 case CLI) 출력과 wrapper(predict_from_folder) 출력의 일치 검사. 사용: python hdglio58_cli_check.py CASE"""
import json
import os
import subprocess
import sys

import nibabel as nib
import numpy as np

ROOT = os.path.abspath(".")
cid = sys.argv[1]
out = f"{ROOT}/results/iter_058/hd/cli_check"
os.makedirs(out, exist_ok=True)
inp = f"{ROOT}/results/iter_058/hd/input_D"
env = dict(os.environ, HD_GLIO_PARAMS=f"{ROOT}/results/iter_058/external/weights/params", CUDA_VISIBLE_DEVICES="1")
cmd = [f"{ROOT}/results/environments/hdglio58/bin/hd_glio_predict", "-t1", f"{inp}/{cid}_0000.nii.gz", "-t1c", f"{inp}/{cid}_0001.nii.gz",
       "-t2", f"{inp}/{cid}_0002.nii.gz", "-flair", f"{inp}/{cid}_0003.nii.gz", "-o", f"{out}/{cid}_cli.nii.gz"]
r = subprocess.run(cmd, env=env, capture_output=True, text=True)
open(f"{out}/{cid}_cli.log", "w").write(r.stdout + r.stderr)
a = np.asarray(nib.load(f"{out}/{cid}_cli.nii.gz").dataobj)
b = np.asarray(nib.load(f"{ROOT}/results/iter_058/hd/run_D_1w/g0w0/pred/{cid}.nii.gz").dataobj)
res = {"case": cid, "rc": r.returncode, "shape_equal": a.shape == b.shape, "n_diff_voxels": int((a != b).sum()),
       "n_fg_cli": int((a > 0).sum()), "n_fg_wrapper": int((b > 0).sum()), "labels_cli": np.unique(a).tolist(),
       "note": "CLI는 GPU1, wrapper는 GPU0에서 실행"}
json.dump(res, open(f"{out}/{cid}_compare.json", "w"), indent=1)
print(res)
