"""iter_059: U8 전체 경로 실행기 (iter_056 prompt/모델 revision/caps/렌더 함수 그대로; hdglio58_u8의 timer 종료점을 답변 저장 후로 수정).
경계: 원본 4D NIfTI 읽기 -> FLAIR 정규화·8-slice 렌더(메모리) -> processor -> 6구간 생성 -> parsing -> 답변 JSON 원자적 저장.
python hdglio59_u8.py CASES.json OUT_DIR  (OUT_DIR는 존재하면 거부; CUDA_VISIBLE_DEVICES는 호출자가 지정)
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
    case_json, out = sys.argv[1:3]
    cases = json.load(open(case_json))
    if os.path.exists(out):
        raise FileExistsError(out)
    os.makedirs(out)
    from PIL import Image
    ev = [{"event": "proc_start", "t": T_PROC_START, "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")}]
    ev.append({"event": "load_model_start", "t": time.time()})
    torch, proc, model = R.load_model()
    eos = set(model.generation_config.eos_token_id if isinstance(model.generation_config.eos_token_id, list) else [model.generation_config.eos_token_id])
    torch.cuda.synchronize()
    ev.append({"event": "load_model_end", "t": time.time()})
    meta = {c["case"]: c for c in json.load(open(f"{SRC}/data/cases.json"))["chosen"]}
    ev.append({"event": "pipeline_start", "t": time.time()})
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
            rows.append((si, zs, [Image.fromarray(D.render(fl, k, ref["vmin"], ref["vmax"])) for k in zs]))
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
        rec = {"case": cid, "t_read_prep_s": t_prep, "t_processor_s": t_proc, "t_generate_s": t_gen, "answers": res}
        tmp = f"{out}/u8_{cid}.json.tmp"
        with open(tmp, "w") as f:
            json.dump(rec, f, indent=1)
        os.replace(tmp, f"{out}/u8_{cid}.json")
        ev.append({"event": "answer_saved", "case": cid, "t_case_start": tc0, "t": time.time()})  # 저장 완료 후 종료
        print(cid, round(time.time() - tc0, 2), flush=True)
    ev.append({"event": "pipeline_end", "t": time.time()})
    summ = {"cases": cases, "events": ev, "peak_alloc_MiB": torch.cuda.max_memory_allocated() / 2**20,
            "peak_reserved_MiB": torch.cuda.max_memory_reserved() / 2**20, "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "t_end": time.time()}
    tmp = f"{out}/summary.json.tmp"
    json.dump(summ, open(tmp, "w"), indent=1)
    os.replace(tmp, f"{out}/summary.json")


if __name__ == "__main__":
    main()
