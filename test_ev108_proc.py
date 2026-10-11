"""iter_108 공식 processor tensor 대조 (모델 weight 불필요, CPU). 기술 6명의 F/D/T/C/L 입력을 두 경로로 구성해 비교한다.

경로 A: processor.apply_chat_template(messages, tokenize=True) (runner가 쓰는 공식 경로)
경로 B: tokenizer 쪽 chat template 문자열 + processor(text=..., images=[...]) (독립 구성)
결과: results/iter_108/tests/proc_check.json (새 파일만).
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

import ev108_build as B
import ev108_data as D
import ev108_run as RUN
import ev108_spec as S
from rsna_diag import generate as G

os.environ.setdefault("HF_HOME", G.HF_HOME)
os.environ.setdefault("HF_HUB_OFFLINE", "1")


def sha_t(t):
    return hashlib.sha256(np.ascontiguousarray(t.float().numpy()).tobytes()).hexdigest()


def main():
    out = Path(sys.argv[1])
    if out.exists():
        sys.exit(f"exists {out}")
    import torch
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION)
    rows = {}
    for st in ("FREPRO", "TECH"):
        for r in RUN.read_requests(str(B.DATA / f"requests_{st}.jsonl")):
            rows[(r["patient"], r["cond"], r["target"])] = r
    F, _ = D.load_F()
    checks = []

    def chk(name, ok, detail=None):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    img_tok = proc.tokenizer.convert_tokens_to_ids("<image_soft_token>")
    chk("soft_token_id_is_config_262144", img_tok == json.load(open(RUN.SNAP / "config.json"))["image_token_index"] == 262144, img_tok)
    for (pid, cond, tg), r in sorted(rows.items()):
        imgs = [RUN.load_img(i["path"])[0] for i in r["images"]]
        a = RUN.build_inputs_multi(proc, imgs, r["prompt"])
        text = proc.apply_chat_template([{"role": "user", "content": [{"type": "image"} for _ in imgs] + [{"type": "text", "text": r["prompt"]}]}],
                                        add_generation_prompt=True, tokenize=False)
        b = proc(text=text, images=imgs, return_tensors="pt", add_special_tokens=False)  # 문자열에 <bos>가 이미 있음
        same = set(a) == set(b) and all(torch.equal(a[k], b[k]) for k in a)
        n_tok = int((a["input_ids"] == img_tok).sum())
        chk(f"pathA==pathB_{pid}_{cond}_{tg}", same and n_tok == 256 * len(imgs) and a["pixel_values"].shape[0] == len(imgs),
            {"keys": sorted(a), "n_img_tok": n_tok, "pv": list(a["pixel_values"].shape)})
        if cond == "F":
            fr = F[(pid, tg)]
            chk(f"F_input_ids_match_iter016_{pid}_{tg}", S.sha(json.dumps(a["input_ids"][0].tolist())) == fr["input_ids_sha256"]
                and r["prompt_sha256"] == fr["prompt_sha256"] and r["images"][0]["pixel_sha256"] == fr["input_pixel_sha256"],
                {"n_in": a["input_ids"].shape[1], "n_in_saved": fr["n_input_tokens"]})
    # 조건 간 tensor 관계
    for pid in sorted({k[0] for k in rows if k[1] != "F"}):
        t = {}
        for cond in ("F", "D", "T", "C", "L"):
            r = rows[(pid, cond, "O")]
            imgs = [RUN.load_img(i["path"])[0] for i in r["images"]]
            t[cond] = RUN.build_inputs_multi(proc, imgs, r["prompt"])["pixel_values"]
        chk(f"orig_tensor_same_F_D_T_C_{pid}", torch.equal(t["F"][0], t["D"][0]) and torch.equal(t["D"][0], t["T"][0]) and torch.equal(t["T"][0], t["C"][0]))
        chk(f"D_two_tensors_identical_{pid}", torch.equal(t["D"][0], t["D"][1]))
        chk(f"T_second_differs_from_orig_{pid}", not torch.equal(t["T"][0], t["T"][1]))
        chk(f"L_tensor_equals_T_second_{pid}", torch.equal(t["L"][0], t["T"][1]))
        chk(f"C_second_differs_from_T_second_{pid}", not torch.equal(t["C"][1], t["T"][1]))
    # 영상 순서: T의 두 영상을 교환하면 입력이 달라지고 앞 영상 tensor가 원본이다 (순서 연결 확인)
    r = rows[(sorted({k[0] for k in rows})[0], "T", "O")]
    imgs = [RUN.load_img(i["path"])[0] for i in r["images"]]
    x = RUN.build_inputs_multi(proc, imgs, r["prompt"])
    y = RUN.build_inputs_multi(proc, imgs[::-1], r["prompt"])
    chk("order_swap_changes_pixel_order", torch.equal(x["pixel_values"][0], y["pixel_values"][1]) and not torch.equal(x["pixel_values"][0], y["pixel_values"][0]))
    ip = proc.image_processor
    meta = {"do_pan_and_scan": getattr(ip, "do_pan_and_scan", None), "size": str(getattr(ip, "size", None)), "image_seq_length": proc.image_seq_length,
            "transformers": transformers.__version__}
    json.dump({"n": len(checks), "n_pass": sum(c["pass"] for c in checks), "meta": meta, "checks": checks}, open(out, "x"), indent=1, default=str)
    print(f"{sum(c['pass'] for c in checks)}/{len(checks)} pass", meta)
    for c in checks:
        if not c["pass"]:
            print("FAIL", c["name"], str(c["detail"])[:200])


if __name__ == "__main__":
    main()
