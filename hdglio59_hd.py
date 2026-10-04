"""iter_059: HD-GLIO+OR 전체 경로 실행기 (venv hdglio58의 python으로 실행).
경계: 원본 4D NIfTI 읽기 -> channel 분리·쓰기(새 경로) -> 공식 predict_from_folder(fold0, TTA) -> native grid 복원 pred 읽기 ->
      FLAIR 비영 범위 기반 6구간 foreground OR -> 답변 JSON 원자적 저장. GT(label)는 읽지 않는다.
모델 loading(load_model_and_checkpoint_files)은 predict 모듈의 해당 함수를 감싸 sync 후 직접 계측한다(계산·인자 불변).
python hdglio59_hd.py CASES.json OUT_DIR   (OUT_DIR는 존재하면 거부; CUDA_VISIBLE_DEVICES는 호출자가 지정)
"""
import json
import os
import sys
import time

T_PROC_START = time.time()

import nibabel as nib  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

import msd56_data as D  # noqa: E402
from hd_glio.paths import folder_with_parameter_files  # noqa: E402
from nnunet.inference import predict as nnpredict  # noqa: E402

SRC = "results/iter_056"
HD_CH = {"0000": 1, "0001": 2, "0002": 3, "0003": 0}  # HD suffix -> MSD channel (hdglio58_prep와 동일)
EV = []


def ev(name, **kw):
    EV.append({"event": name, "t": time.time(), **kw})


def main():
    case_json, out = sys.argv[1:3]
    cases = json.load(open(case_json))
    if os.path.exists(out):
        raise FileExistsError(out)
    os.makedirs(out)
    procs = int(os.environ.get("HDG_PROCS", "2"))
    meta = {c["case"]: c for c in json.load(open(f"{SRC}/data/cases.json"))["chosen"]}
    assert os.path.isdir(folder_with_parameter_files), folder_with_parameter_files
    ev("proc_start", t_proc_start=T_PROC_START, cuda_visible=os.environ.get("CUDA_VISIBLE_DEVICES"))

    orig_load = nnpredict.load_model_and_checkpoint_files

    def timed_load(*a, **k):
        torch.cuda.synchronize()
        ev("load_model_start")
        r = orig_load(*a, **k)
        torch.cuda.synchronize()
        ev("load_model_end")
        return r

    nnpredict.load_model_and_checkpoint_files = timed_load

    ev("pipeline_start")
    indir = f"{out}/in"
    os.makedirs(indir)
    flair = {}
    for cid in cases:
        ev("case_read_start", case=cid)
        img = nib.load(f"{SRC}/data/raw/{cid}_img.nii.gz")
        assert img.ndim == 4 and img.shape[3] == 4 and "".join(nib.aff2axcodes(img.affine)) == "RAS"
        assert np.allclose(img.affine, np.eye(4), atol=1e-4), (cid, img.affine)
        data = np.asarray(img.dataobj)
        assert np.isfinite(data).all(), cid
        ev("case_read_end", case=cid)
        for suf, ch in HD_CH.items():
            vol = data[..., ch].astype(np.float32)
            if suf == "0003":
                flair[cid] = vol
            h = img.header.copy()
            h.set_data_dtype(np.float32)
            p = f"{indir}/{cid}_{suf}.nii.gz"
            nib.save(nib.Nifti1Image(vol, img.affine, h), p + ".tmp.nii.gz")
            os.replace(p + ".tmp.nii.gz", p)
        ev("case_split_end", case=cid)
    ev("predict_start")
    nnpredict.predict_from_folder(folder_with_parameter_files, indir, f"{out}/pred", (0,), False, procs, procs, None, 0, 1, True,
                                  overwrite_existing=True, checkpoint_name="model_final_checkpoint")
    torch.cuda.synchronize()
    ev("predict_end")
    for cid in cases:
        ev("or_start", case=cid)
        pr = np.asarray(nib.load(f"{out}/pred/{cid}.nii.gz").dataobj) > 0
        assert pr.shape == flair[cid].shape
        z0, z1 = D.nonzero_range(flair[cid])
        slabs = D.make_slabs(z0, z1)
        assert slabs == meta[cid]["slabs"], f"{cid}: slab mismatch vs iter_056 (FLAIR-only definition)"
        ans = []
        for si, (a, b) in enumerate(slabs):
            n = int(pr[:, :, a:b + 1].sum())
            ans.append({"slab": si, "z0": a, "z1": b, "answer": "PRESENT" if n > 0 else "ABSENT", "hd_fg_voxels": n})
        rec = {"case": cid, "answers": ans, "pred_voxels": int(pr.sum())}
        tmp = f"{out}/hd_{cid}.json.tmp"
        with open(tmp, "w") as f:
            json.dump(rec, f, indent=1)
        os.replace(tmp, f"{out}/hd_{cid}.json")
        ev("answer_saved", case=cid)
    ev("pipeline_end")
    summ = {"cases": cases, "events": EV, "procs": procs, "peak_alloc_MiB": torch.cuda.max_memory_allocated() / 2**20,
            "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20, "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "t_end": time.time()}
    tmp = f"{out}/summary.json.tmp"
    json.dump(summ, open(tmp, "w"), indent=1)
    os.replace(tmp, f"{out}/summary.json")
    print("done", len(cases))


if __name__ == "__main__":
    main()
