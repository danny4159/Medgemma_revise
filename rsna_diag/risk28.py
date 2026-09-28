"""iter_028: RSNA grounding SFT(B0=seed17)의 빈 bbox 출력에서 미검출 위험을 구분하는 score 진단.

핵심 설계 결정 (계획서 Implementation task 4의 대체 경로를 채택):
별도 teacher-forced replay를 구현하지 않는다. `model.generate(..., output_scores=True,
return_dict_in_generate=True)`가 반환하는 score는 실제 generation이 각 step에서 사용한
processed logits 그 자체이며 (greedy decoding에서는 정의상 argmax(scores[t]) == 선택 token),
"검증된 동일 generation/cache 경로에서 score를 얻는" 계획의 요구를 그대로 만족한다.
이 경로에서 얻은 raw logits를 FP32로 올려 log_softmax를 직접 계산한다 (bf16 softmax 금지).
"""
import glob
import hashlib
import json
import math
import os
import time

import numpy as np

from . import geometry, parse, prompts as P
from . import generate as G

MODEL_ID = G.MODEL_ID
MODEL_REVISION = G.MODEL_REVISION

BRACKET_TEXT = "[]"
PRESENCE_Q = "Is any pulmonary opacity suspicious for pneumonia visible in this chest radiograph? Answer Yes or No."
PTRUE_Q = "Is the proposed answer correct for this medical image? Respond with a single word: Yes or No."
TASKS_BASE = ("presence", "ptrue")
TASKS_SFT = ("token_score", "presence", "ptrue")
RUNNER_VERSION = "iter028_risk_v1"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def ptrue_prompt():
    return f"{P.CONCISE}\n\nProposed answer: {BRACKET_TEXT}\n\n{PTRUE_Q}"


def presence_prompt():
    return PRESENCE_Q


def token_ids_for(proc, text):
    return proc.tokenizer(text, add_special_tokens=False)["input_ids"]


def check_single_token(proc, text):
    ids = token_ids_for(proc, text)
    if len(ids) != 1:
        raise G.RunError(f"{text!r} is not a single token under current tokenizer: {ids}")
    return ids[0]


def resolve_special_ids(proc):
    bracket = check_single_token(proc, BRACKET_TEXT)
    yes = check_single_token(proc, "Yes")
    no = check_single_token(proc, "No")
    return {"bracket": bracket, "yes": yes, "no": no}


def fp32_logsoftmax_stats(logits_row, token_id):
    """logits_row: 1D torch tensor(vocab,), 임의 dtype. FP32 log_softmax. returns (nll, entropy, logp_tensor fp32)."""
    import torch
    x = logits_row.to(torch.float32)
    m = x.max()
    lse = torch.log(torch.exp(x - m).sum()) + m
    logp = x - lse
    nll = float(-logp[token_id])
    p = torch.exp(logp)
    ent = float(-(p * logp).sum())
    return nll, ent, logp


def cpu_independent_logsoftmax_stats(logits_np_fp32, token_id):
    """numpy float64 기반 독립 재계산 (torch 미사용). returns (nll, entropy)."""
    x = np.asarray(logits_np_fp32, dtype=np.float64)
    m = x.max()
    lse = math.log(np.sum(np.exp(x - m))) + m
    logp = x - lse
    nll = float(-logp[token_id])
    p = np.exp(logp)
    ent = float(-np.sum(p * logp))
    return nll, ent


def load_image_for(item):
    image, aff, px = G.load_image(item["image"])
    return image, aff, px


def build_image_inputs(proc, image, prompt):
    return G.build_inputs(proc, image, prompt)


def generate_scored(torch, model, inp, max_new, eos_ids):
    dev = "cuda"
    x = {k: (v.to(dev, dtype=torch.bfloat16) if k == "pixel_values" else v.to(dev)) for k, v in inp.items()}
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**x, max_new_tokens=max_new, do_sample=False,
                              output_scores=True, return_dict_in_generate=True)
    torch.cuda.synchronize()
    dt = time.time() - t0
    n_in = x["input_ids"].shape[1]
    seq = out.sequences[0, n_in:].tolist()
    ended = len(seq) > 0 and seq[-1] in eos_ids
    scores = [s[0].detach().to(torch.float32).cpu() for s in out.scores]
    argmax_ok = all(int(scores[i].argmax()) == seq[i] for i in range(len(seq)))
    return {"suffix_ids": seq, "ended_eos": bool(ended), "scores": scores, "runtime_s": dt,
            "argmax_matches_greedy": bool(argmax_ok),
            "peak_mem_alloc_gb": torch.cuda.max_memory_allocated() / 2**30}


def score_token_original(torch, proc, model, ids, image, eos_ids, expect_suffix=None, max_new=8):
    """B0 adapter로 concise bbox prompt를 다시 생성하며 raw score를 추출한다 (원래 [] + EOS 재현)."""
    inp = build_image_inputs(proc, image, P.CONCISE)
    r = generate_scored(torch, model, inp, max_new, eos_ids)
    reproduced = (expect_suffix is None) or (r["suffix_ids"] == expect_suffix)
    nll0 = ent0 = nll1 = None
    if len(r["scores"]) >= 1:
        nll0, ent0, _ = fp32_logsoftmax_stats(r["scores"][0], ids["bracket"])
    if len(r["scores"]) >= 2 and len(r["suffix_ids"]) >= 2:
        nll1, _, _ = fp32_logsoftmax_stats(r["scores"][1], r["suffix_ids"][1])
    return {
        "task": "token_score", "suffix_ids": r["suffix_ids"], "ended_eos": r["ended_eos"],
        "reproduced_expected_suffix": reproduced, "argmax_matches_greedy": r["argmax_matches_greedy"],
        "nll_bracket": nll0, "entropy_bracket": ent0, "nll_eos_step1": nll1,
        "runtime_s": r["runtime_s"], "peak_mem_alloc_gb": r["peak_mem_alloc_gb"],
    }


def score_yes_no(torch, proc, model, ids, image, prompt, eos_ids, task_name):
    inp = build_image_inputs(proc, image, prompt)
    r = generate_scored(torch, model, inp, 1, eos_ids)
    row = r["scores"][0]
    logit_yes = float(row[ids["yes"]])
    logit_no = float(row[ids["no"]])
    _, _, logp = fp32_logsoftmax_stats(row, ids["yes"])
    p_yes = float(math.exp(float(logp[ids["yes"]])))
    p_no = float(math.exp(float(logp[ids["no"]])))
    greedy_id = r["suffix_ids"][0] if r["suffix_ids"] else None
    return {
        "task": task_name, "logit_yes": logit_yes, "logit_no": logit_no, "risk_no_minus_yes": logit_no - logit_yes,
        "p_yes": p_yes, "p_no": p_no, "mass_yes_no": p_yes + p_no, "greedy_token_id": greedy_id,
        "runtime_s": r["runtime_s"], "peak_mem_alloc_gb": r["peak_mem_alloc_gb"],
    }


def request_id(variant, split, item_id, task):
    return sha(f"{MODEL_REVISION}|{variant}|{split}|{item_id}|{task}".encode())[:32]


def read_records(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for ln in f:
                if ln.strip():
                    out.append(json.loads(ln))
    return out


def expected_tasks(variant):
    return TASKS_SFT if variant == "sft" else TASKS_BASE


def run_worker(items, variant, split, out_dir, worker_idx, protocol_path, adapter_dir, source_manifest,
                time_limit=None, max_patients=None):
    """variant: 'base'(M0, adapter 없음) 또는 'sft'(B0, adapter_dir 로드). items: list of dict(id, image, file_sha256, expect_suffix)."""
    from . import lock_protocol as LP, queue_lock as QL
    pdig_protocol = LP.verify(protocol_path) if protocol_path else None
    info = QL.my_info(worker=worker_idx, variant=variant, split=split)
    wl = os.path.join(out_dir, f"worker_{variant}_{worker_idx}.lock")
    lk, own, _ = QL.try_lock(wl, info)
    if lk is None:
        raise G.RunError(f"worker {variant}/{worker_idx} already running: {own}")
    try:
        import torch
        torch, proc, model = G.load_model()
        adapter_digest = G.load_adapter(torch, model, adapter_dir) if adapter_dir else None
        if variant == "sft":
            want = source_manifest["adapter_digest_seed17"]
            if adapter_digest != want:
                raise G.RunError(f"adapter digest mismatch: got {adapter_digest} want {want}")
        elif adapter_digest is not None:
            raise G.RunError("base variant must not load an adapter")
        ids_map = resolve_special_ids(proc)
        for k, want in source_manifest["special_token_ids"].items():
            if ids_map[k] != want:
                raise G.RunError(f"tokenizer id for {k} changed: {ids_map[k]} != locked {want}")
        env = G.env_info(torch, proc, model)
        if env["model_revision"] != MODEL_REVISION:
            raise G.RunError("model revision mismatch")
        eos = env["eos_token_id"]
        eos_ids = set(eos if isinstance(eos, list) else [eos])
        env_path = os.path.join(out_dir, f"worker_{variant}_{worker_idx}.env.json")
        if not os.path.exists(env_path):
            json.dump({"env": env, "adapter_digest": adapter_digest, "protocol_digest": pdig_protocol,
                       "special_token_ids": ids_map, "worker": worker_idx, "variant": variant},
                      open(env_path, "w"), indent=1, default=str)

        out_path = os.path.join(out_dir, f"gen_{variant}_worker{worker_idx}.jsonl")
        claim_dir = os.path.join(out_dir, "claims")
        os.makedirs(claim_dir, exist_ok=True)
        tasks = expected_tasks(variant)
        img_cache = {}

        def px(path):
            if path not in img_cache:
                img_cache[path] = G.load_image(path)
            return img_cache[path]

        def existing_done():
            done = {}
            for fn in sorted(glob.glob(os.path.join(out_dir, f"gen_{variant}_worker*.jsonl"))):
                for r in read_records(fn):
                    key = (r["id"], r["task"])
                    if r.get("adapter_digest") != adapter_digest or r.get("split") != split:
                        raise G.RunError(f"stale/foreign record in {fn}: {key}")
                    if r["input_pixel_sha256"] != px(r["image"])[2]:
                        raise G.RunError(f"input image changed since completion for {key}")
                    if key in done:
                        raise G.RunError(f"duplicate request {key} across worker files")
                    done[key] = r
            return done

        done = existing_done()
        log = open(out_path + ".log", "a")
        t0, n_new, n_patients = time.time(), 0, 0
        for it in items:
            if max_patients is not None and n_patients >= max_patients:
                break
            if all((it["id"], t) in done for t in tasks):
                continue
            clk, prev, reclaimed = QL.try_lock(os.path.join(claim_dir, f"{variant}__{it['id']}.claim"), info)
            if clk is None:
                continue
            try:
                done = existing_done()
                if all((it["id"], t) in done for t in tasks):
                    continue
                image, aff, px_hash = px(it["image"])
                for t in tasks:
                    if (it["id"], t) in done:
                        continue
                    if time_limit and time.time() - t0 > time_limit:
                        log.write(json.dumps({"event": "stop_time_limit", "n_new": n_new}) + "\n")
                        log.flush()
                        return {"n_new": n_new, "n_patients": n_patients}
                    if t == "token_score":
                        rec = score_token_original(torch, proc, model, ids_map, image, eos_ids,
                                                     expect_suffix=it.get("expect_suffix"))
                    elif t == "presence":
                        rec = score_yes_no(torch, proc, model, ids_map, image, presence_prompt(), eos_ids, "presence")
                    elif t == "ptrue":
                        rec = score_yes_no(torch, proc, model, ids_map, image, ptrue_prompt(), eos_ids, "ptrue")
                    else:
                        raise G.RunError(f"unknown task {t}")
                    rec.update({"id": it["id"], "variant": variant, "split": split,
                                "request_id": request_id(variant, split, it["id"], t),
                                "adapter_digest": adapter_digest, "protocol_digest": pdig_protocol,
                                "image": it["image"], "image_file_sha256": it.get("file_sha256"),
                                "input_pixel_sha256": px_hash, "worker": worker_idx, "ts": time.time(),
                                "runner": RUNNER_VERSION})
                    with open(out_path, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                        f.flush()
                        os.fsync(f.fileno())
                    done[(it["id"], t)] = rec
                    n_new += 1
                    log.write(json.dumps({"event": "done", "id": it["id"], "task": t,
                                          "elapsed": round(time.time() - t0, 1)}) + "\n")
                    log.flush()
                n_patients += 1
            finally:
                clk.release()
        return {"n_new": n_new, "n_patients": n_patients}
    finally:
        lk.release()


def check_completion(out_dir, items, variants=("base", "sft")):
    """모든 (variant, id, task)가 정확히 한 번씩 존재하는지 검사. returns dict with per-variant counts and problems."""
    problems = []
    counts = {}
    for variant in variants:
        tasks = expected_tasks(variant)
        expect = {(it["id"], t) for it in items for t in tasks}
        got = {}
        for fn in sorted(glob.glob(os.path.join(out_dir, f"gen_{variant}_worker*.jsonl"))):
            for r in read_records(fn):
                key = (r["id"], r["task"])
                if key in got:
                    problems.append(f"duplicate {variant}:{key}")
                got[key] = r
        missing = expect - set(got)
        extra = set(got) - expect
        if missing:
            problems.append(f"{variant}: missing {len(missing)} e.g. {sorted(missing)[:3]}")
        if extra:
            problems.append(f"{variant}: extra {len(extra)} e.g. {sorted(extra)[:3]}")
        counts[variant] = {"expected": len(expect), "got": len(got), "missing": len(missing), "extra": len(extra)}
    return {"ok": not problems, "problems": problems, "counts": counts}


def load_all(out_dir, variant):
    out = {}
    for fn in sorted(glob.glob(os.path.join(out_dir, f"gen_{variant}_worker*.jsonl"))):
        for r in read_records(fn):
            out[(r["id"], r["task"])] = r
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-manifest", required=True)
    ap.add_argument("--split", required=True, choices=["C", "E", "D24"])
    ap.add_argument("--variant", required=True, choices=["base", "sft"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--worker", type=int, required=True)
    ap.add_argument("--protocol", default=None)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-patients", type=int, default=None)
    ap.add_argument("--ids", default=None, help="json list of patient ids to restrict to (기본: split 전체)")
    a = ap.parse_args()

    sm = json.load(open(a.source_manifest))
    if a.split == "D24":
        from . import risk28_source as RS
        d24 = RS.select_d24(sm)
        items = d24["empty"] + d24["nonempty"]
        src_split = "C"
    else:
        items = [p for p in sm["patients"][a.split].values() if p["seed17_empty"]]
        src_split = a.split
    if a.ids:
        keep = set(json.load(open(a.ids)))
        items = [it for it in items if it["id"] in keep]
    for it in items:
        it["expect_suffix"] = it.get("seed17_suffix_ids")
    os.makedirs(a.out_dir, exist_ok=True)
    res = run_worker(items, a.variant, a.split, a.out_dir, a.worker, a.protocol, a.adapter, sm,
                      time_limit=a.time_limit, max_patients=a.max_patients)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
