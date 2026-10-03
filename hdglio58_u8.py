"""iter_058: U8 전체 pipeline(원본 4D NIfTI -> FLAIR 읽기·정규화·8-slice 렌더 -> processor -> 6 구간 생성 -> 저장) 비용 측정용 실행기.
iter_056의 prompt/모델 revision/caps/렌더 함수를 그대로 사용한다(msd56_run, msd56_data import). 렌더 결과는 PNG 저장 없이 메모리 PIL로 전달하며
iter_056 PNG와 pixel 동일성을 검사한다(--check-png).

python hdglio58_u8.py SPLIT CASES.json OUT_DIR  (CUDA_VISIBLE_DEVICES는 호출자가 지정)
출력 OUT_DIR/u8_{case}.json (case별 원자적 기록), OUT_DIR/summary.json
"""
import json
import os
import sys
import time

T_PROC_START = time.time()

import numpy as np  # noqa: E402

import msd56_data as D  # noqa: E402
import msd56_run as R  # noqa: E402

SRC = "results/iter_056"


def flair_only(cid):
    import nibabel as nib
    img = nib.load(f"{SRC}/data/raw/{cid}_img.nii.gz")
    can = nib.as_closest_canonical(img)
    assert "".join(nib.aff2axcodes(can.affine)) == "RAS"
    fl = np.asarray(can.dataobj[..., 0], dtype=np.float32)
    if not np.isfinite(fl).all():
        raise R.RunError(f"{cid}: non-finite FLAIR")
    return fl


def main():
    split, case_json, out = sys.argv[1:4]
    cases = json.load(open(case_json))
    os.makedirs(out, exist_ok=True)
    check_png = os.environ.get("U8_CHECK_PNG") == "1"
    from PIL import Image
    t = time.time()
    torch, proc, model = R.load_model()
    eos = set(model.generation_config.eos_token_id if isinstance(model.generation_config.eos_token_id, list) else [model.generation_config.eos_token_id])
    torch.cuda.synchronize()
    t_load = time.time() - t
    meta = {c["case"]: c for c in json.load(open(f"{SRC}/data/cases.json"))["chosen"]}
    summ = {"split": split, "cases": cases, "t_import_s": t - T_PROC_START, "t_load_model_s": t_load, "per_case": {}}
    for cid in cases:
        tc0 = time.time()
        fl = flair_only(cid)
        z0, z1 = D.nonzero_range(fl)
        slabs = D.make_slabs(z0, z1)
        ref = meta[cid]
        assert slabs == ref["slabs"] and float(fl.min()) == ref["vmin"] and float(fl.max()) == ref["vmax"], f"{cid}: slab/range mismatch vs iter_056"
        rows = []
        for si, (a, b) in enumerate(slabs):
            zs = [a + i for i in D.equi(b - a + 1, 8)]
            imgs = [Image.fromarray(D.render(fl, k, ref["vmin"], ref["vmax"])) for k in zs]
            if check_png:
                for k, im in zip(zs, imgs):
                    p = np.asarray(Image.open(f"{SRC}/data/png/{cid}_z{k:03d}.png").convert("RGB"))
                    assert np.array_equal(p, np.asarray(im)), f"{cid} z{k}: render != iter_056 png"
            rows.append((si, zs, imgs))
        t_prep = time.time() - tc0
        res, t_gen, t_proc = [], 0.0, 0.0
        for si, zs, imgs in rows:
            tp = time.time()
            content = [{"type": "image", "image": im} for im in imgs] + [{"type": "text", "text": R.PROMPT}]
            inp = proc.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True, tokenize=True,
                                           return_dict=True, return_tensors="pt")
            t_proc += time.time() - tp
            attempts = []
            for cap in R.CAPS:
                at = R.generate(torch, model, inp, cap, eos)
                attempts.append(at)
                if at["ended_eos"]:
                    break
            txt = proc.tokenizer.decode(attempts[-1]["suffix_ids"], skip_special_tokens=False)
            t_gen += sum(a_["runtime_s"] for a_ in attempts)
            res.append({"slab": si, "slices": zs, "answer": R.parse_answer(txt), "raw": txt, "ended_eos": attempts[-1]["ended_eos"],
                        "n_attempts": len(attempts)})
        rec = {"case": cid, "t_case_s": time.time() - tc0, "t_read_prep_s": t_prep, "t_processor_s": t_proc, "t_generate_s": t_gen,
               "answers": res, "t_start": tc0, "t_end": time.time()}
        tmp = f"{out}/u8_{cid}.json.tmp"
        json.dump(rec, open(tmp, "w"), indent=1)
        os.replace(tmp, f"{out}/u8_{cid}.json")
        summ["per_case"][cid] = {k: rec[k] for k in ("t_case_s", "t_read_prep_s", "t_processor_s", "t_generate_s")}
        print(cid, round(rec["t_case_s"], 2), flush=True)
    summ["t_total_s"] = time.time() - T_PROC_START
    summ["peak_alloc_MiB"] = torch.cuda.max_memory_allocated() / 2**20
    summ["peak_reserved_MiB"] = torch.cuda.max_memory_reserved() / 2**20
    summ["cuda_visible"] = os.environ.get("CUDA_VISIBLE_DEVICES")
    json.dump(summ, open(f"{out}/summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
