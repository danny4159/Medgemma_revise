"""iter_030: RSNA B0(seed17) 비어 있지 않은 출력의 부분 누락 위험 score(O)와 단일 continuation 개입(F).

O: B0 concise 원래 generation을 output_scores=True로 재현하며 위험 baseline과 Q(branch margin)를 추출한다.
F: 같은 generation에서 마지막 opacity 직후 분기(index=branch_index)에 token 23179를 한 번만 강제한 뒤
   원래 greedy decoding을 계속한다 (cap ladder 1000/2000/4000, EOS 판정 유지).

GT는 이 모듈에 전혀 들어오지 않는다 (source manifest의 infer 쪽 item만 사용).
"""
import glob
import hashlib
import json
import os
import time

from . import generate as G
from . import risk30_source as RS
from .risk28 import fp32_logsoftmax_stats, resolve_special_ids  # 범용 FP32 log-softmax/토큰 확인 재사용

MODEL_ID = G.MODEL_ID
MODEL_REVISION = G.MODEL_REVISION
CAPS = G.CAPS
RUNNER_VERSION = "iter031_risk_v2"

# iter_031: 이 실행 경로가 의존하는 코드·데이터 중 protocol에 반드시 잠겨 있어야 하는 것들.
# LP.verify()는 "locked에 있는 파일만" 재검증하므로, 여기 목록이 실제로 잠금 목록 안에
# 있는지까지 별도로 강제해야 불완전한 protocol(예: risk28_eval.py 누락)을 막을 수 있다.
REQUIRED_EXTRA_LOCK_FILES = [
    "rsna_diag/risk30.py", "rsna_diag/risk30_source.py", "rsna_diag/risk30_eval.py",
    "rsna_diag/risk28.py", "rsna_diag/risk28_eval.py",
]


def require_full_protocol(protocol_path, source_manifest_path):
    """protocol의 코드 상태를 재검증하고, 이번 실행이 요구하는 필수 파일이 실제로 잠금 목록에
    있는지 확인한다. source_manifest_path도 잠금 목록에 있어야 한다 (내용은 LP.verify가 재대조).
    returns protocol digest."""
    from . import lock_protocol as LP
    if not protocol_path:
        raise G.RunError("--protocol is required for risk30 runs")
    dig = LP.verify(protocol_path)
    locked_files = json.load(open(protocol_path))["locked"]["files"]
    required = REQUIRED_EXTRA_LOCK_FILES + [source_manifest_path]
    missing = [f for f in required if f not in locked_files]
    if missing:
        raise G.RunError(f"protocol {protocol_path} is missing required locked files: {missing}")
    return dig


def verify_c_gate(decide_c_path):
    """split=='E' 실행 전에 C201 decision이 enter_E=True인지 확인한다. returns (decision dict, sha256)."""
    if not decide_c_path or not os.path.exists(decide_c_path):
        raise G.RunError(f"--decide-c is required for split E and must exist: {decide_c_path!r}")
    raw = open(decide_c_path, "rb").read()
    decision = json.loads(raw)
    if not decision.get("enter_E"):
        raise G.RunError(f"C201 decision at {decide_c_path} has enter_E={decision.get('enter_E')}; "
                          f"E402 generation is not authorized")
    return decision, sha(raw)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read_records(path):
    """gen_worker*.jsonl을 읽는다. 마지막 줄만 손상됐으면(강제 종료 중 fsync 직전 tearing) 버리고
    계속한다. 그 이전 줄이 손상됐으면 (더 심각한 문제이므로) 그대로 예외를 낸다."""
    out = []
    if os.path.exists(path):
        lines = open(path).read().splitlines()
        last = len(lines) - 1
        for i, ln in enumerate(lines):
            if not ln.strip():
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                if i == last:
                    continue
                raise
    return out


def _run_generate(torch, model, inp, cap, eos_ids, logits_processor=None):
    dev = "cuda"
    x = {k: (v.to(dev, dtype=torch.bfloat16) if k == "pixel_values" else v.to(dev)) for k, v in inp.items()}
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    kw = dict(max_new_tokens=cap, do_sample=False, output_scores=True, return_dict_in_generate=True)
    if logits_processor is not None:
        from transformers import LogitsProcessorList
        kw["logits_processor"] = LogitsProcessorList([logits_processor])
    with torch.no_grad():
        out = model.generate(**x, **kw)
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


def _generate_with_cap_ladder(torch, proc, model, inp, eos_ids, logits_processor_factory=None):
    """G.generate와 같은 cap ladder(1000->2000->4000)를 쓰되 output_scores/logits_processor를 지원한다.

    logits_processor_factory: () -> LogitsProcessor 인스턴스(각 attempt마다 새 상태로 재생성; stateful 강제 1회용).
    """
    attempts = []
    for cap in CAPS:
        lp = logits_processor_factory() if logits_processor_factory else None
        r = _run_generate(torch, model, inp, cap, eos_ids, logits_processor=lp)
        attempts.append(r)
        if r["ended_eos"]:
            break
    return attempts


def make_force_processor(prompt_len, branch_step, force_id):
    import torch as T
    from transformers import LogitsProcessor

    class ForceAt(LogitsProcessor):
        def __init__(self):
            self.done = False
            self.fired_step = None

        def __call__(self, input_ids, scores):
            step = input_ids.shape[1] - prompt_len
            if step == branch_step and not self.done:
                self.done = True
                self.fired_step = step
                new_scores = T.full_like(scores, float("-inf"))
                new_scores[:, force_id] = 0.0
                return new_scores
            return scores
    return ForceAt()


def score_O(torch, proc, model, image, item, eos_ids):
    """원래 concise generation을 재현하며 전체 per-step score와 baseline 위험 지표를 추출한다."""
    from . import prompts as P
    inp = G.build_inputs(proc, image, P.CONCISE)
    expect_suffix = item["seed17_suffix_ids"]
    max_new = min(len(expect_suffix) + 4, CAPS[0])
    r = _run_generate(torch, model, inp, max_new, eos_ids)
    reproduced = r["suffix_ids"] == expect_suffix
    n = len(r["scores"])
    per_step = []
    for i in range(n):
        chosen = r["suffix_ids"][i]
        nll, ent, logp = fp32_logsoftmax_stats(r["scores"][i], chosen)
        per_step.append({"nll": nll, "entropy": ent})
    bidx = item["branch_index"]
    branch_scores = r["scores"][bidx] if bidx < n else None
    q = close_logit = continue_logit = branch_nll = None
    if branch_scores is not None:
        close_logit = float(branch_scores[RS.CLOSE_TOKEN])
        continue_logit = float(branch_scores[RS.CONTINUE_TOKEN])
        q = continue_logit - close_logit
        chosen_at_branch = r["suffix_ids"][bidx]
        branch_nll, _, _ = fp32_logsoftmax_stats(branch_scores, chosen_at_branch)
    nlls_excl_last = [s["nll"] for s in per_step[:-1]] if n >= 1 else []
    ents_excl_last = [s["entropy"] for s in per_step[:-1]] if n >= 1 else []
    eos_nll = per_step[-1]["nll"] if per_step else None
    first_entropy = per_step[0]["entropy"] if per_step else None
    return {
        "task": "O", "id": item["id"],
        "suffix_ids": r["suffix_ids"], "ended_eos": r["ended_eos"],
        "reproduced_expected_suffix": bool(reproduced),
        "argmax_matches_greedy": r["argmax_matches_greedy"],
        "n_output_tokens": n, "n_pred_boxes": item["n_pred_boxes"],
        "branch_index": bidx, "branch_close_logit": close_logit, "branch_continue_logit": continue_logit,
        "Q_continue_minus_close": q, "branch_chosen_token_nll": branch_nll,
        "mean_nll_excl_last": (sum(nlls_excl_last) / len(nlls_excl_last)) if nlls_excl_last else None,
        "mean_entropy_excl_last": (sum(ents_excl_last) / len(ents_excl_last)) if ents_excl_last else None,
        "eos_nll": eos_nll, "first_token_entropy": first_entropy,
        "neg_n_output_tokens": -n, "neg_n_pred_boxes": -item["n_pred_boxes"],
        "runtime_s": r["runtime_s"], "peak_mem_alloc_gb": r["peak_mem_alloc_gb"],
    }


def score_F(torch, proc, model, image, item, eos_ids):
    """마지막 opacity 직후 분기에서 CONTINUE_TOKEN(23179)을 한 번 강제하고 계속 생성한다."""
    from . import prompts as P
    inp = G.build_inputs(proc, image, P.CONCISE)
    prompt_len = inp["input_ids"].shape[1]
    bidx = item["branch_index"]
    expect_prefix = item["seed17_suffix_ids"][:bidx]

    def factory():
        return make_force_processor(prompt_len, bidx, RS.CONTINUE_TOKEN)

    attempts = _generate_with_cap_ladder(torch, proc, model, inp, eos_ids, logits_processor_factory=factory)
    fin = attempts[-1]
    prefix_ok = fin["suffix_ids"][:bidx] == expect_prefix
    forced_ok = len(fin["suffix_ids"]) > bidx and fin["suffix_ids"][bidx] == RS.CONTINUE_TOKEN
    return {
        "task": "F", "id": item["id"],
        "suffix_ids": fin["suffix_ids"], "ended_eos": fin["ended_eos"],
        "n_attempts": len(attempts), "final_cap": CAPS[len(attempts) - 1],
        "prefix_matches_O": bool(prefix_ok), "forced_token_applied": bool(forced_ok),
        "branch_index": bidx,
        "runtime_s": sum(a["runtime_s"] for a in attempts),
        "peak_mem_alloc_gb": max(a["peak_mem_alloc_gb"] for a in attempts),
    }


def request_id(task, split, item_id):
    return sha(f"{MODEL_REVISION}|iter030|{task}|{split}|{item_id}".encode())[:32]


def validate_existing(out_dir, adapter_digest, split, px_fn, protocol_digest=None, accept_protocol_digests=()):
    """out_dir의 모든 gen_worker*.jsonl을 현재 adapter/split/입력 pixel hash·protocol·request_id와 대조한다.

    stale/foreign(다른 adapter·split·protocol)·입력 변경·request_id 위조·파일 간 중복이면 RunError.
    returns {(id, task): record}.
    px_fn: image path -> (image, aff, pixel_sha256) (테스트에서는 순수 함수로 주입 가능).
    protocol_digest=None이면 protocol/request_id 연결 검사를 생략한다 (레거시 fixture 호환용).
    accept_protocol_digests: 호환성이 확인된 과거 실행(D24 등)의 protocol digest를 명시적으로 허용한다.
    """
    ok_protocols = ({protocol_digest, *accept_protocol_digests}) if protocol_digest is not None else None
    done = {}
    for fn in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        for r in read_records(fn):
            key = (r["id"], r["task"])
            if r.get("adapter_digest") != adapter_digest or r.get("split") != split:
                raise G.RunError(f"stale/foreign record in {fn}: {key}")
            if ok_protocols is not None and r.get("protocol_digest") not in ok_protocols:
                raise G.RunError(f"protocol_digest not accepted for {key} in {fn}: {r.get('protocol_digest')}")
            if ok_protocols is not None:
                expect_rid = request_id(r["task"], split, r["id"])
                if r.get("request_id") != expect_rid:
                    raise G.RunError(f"request_id mismatch for {key} in {fn} (tampered id/task/split?)")
            if r["input_pixel_sha256"] != px_fn(r["image"])[2]:
                raise G.RunError(f"input image changed since completion for {key}")
            if key in done:
                raise G.RunError(f"duplicate request {key} across worker files")
            done[key] = r
    return done


def run_worker(items, split, out_dir, worker_idx, protocol_path, adapter_dir, source_manifest,
               source_manifest_path, tasks=("O", "F"), time_limit=None, max_patients=None,
               decide_c_path=None, accept_protocol_digests=()):
    from . import lock_protocol as LP, queue_lock as QL
    pdig_protocol = require_full_protocol(protocol_path, source_manifest_path)
    c_gate_info = None
    if split == "E":
        c_decision, c_decision_sha = verify_c_gate(decide_c_path)
        c_gate_info = {"decide_c_path": decide_c_path, "decide_c_sha256": c_decision_sha,
                       "bstar": c_decision.get("bstar"), "enter_E": c_decision.get("enter_E")}
    info = QL.my_info(worker=worker_idx, split=split)
    wl = os.path.join(out_dir, f"worker_{worker_idx}.lock")
    lk, own, _ = QL.try_lock(wl, info)
    if lk is None:
        raise G.RunError(f"worker {worker_idx} already running: {own}")
    try:
        import torch
        torch, proc, model = G.load_model()
        adapter_digest = G.load_adapter(torch, model, adapter_dir)
        want = source_manifest["adapter_digest_seed17"]
        if adapter_digest != want:
            raise G.RunError(f"adapter digest mismatch: got {adapter_digest} want {want}")
        ids_map = resolve_special_ids(proc)
        for k, want_id in source_manifest["special_token_ids"].items():
            if ids_map[k] != want_id:
                raise G.RunError(f"tokenizer id for {k} changed: {ids_map[k]} != locked {want_id}")
        env = G.env_info(torch, proc, model)
        if env["model_revision"] != MODEL_REVISION:
            raise G.RunError("model revision mismatch")
        eos = env["eos_token_id"]
        eos_ids = set(eos if isinstance(eos, list) else [eos])
        env_path = os.path.join(out_dir, f"worker_{worker_idx}.env.json")
        if not os.path.exists(env_path):
            json.dump({"env": env, "adapter_digest": adapter_digest, "protocol_digest": pdig_protocol,
                       "special_token_ids": ids_map, "worker": worker_idx, "c_gate": c_gate_info},
                      open(env_path, "w"), indent=1, default=str)

        out_path = os.path.join(out_dir, f"gen_worker{worker_idx}.jsonl")
        claim_dir = os.path.join(out_dir, "claims")
        os.makedirs(claim_dir, exist_ok=True)
        img_cache = {}

        def px(path):
            if path not in img_cache:
                img_cache[path] = G.load_image(path)
            return img_cache[path]

        def existing_done():
            return validate_existing(out_dir, adapter_digest, split, px, pdig_protocol, accept_protocol_digests)

        done = existing_done()
        log = open(out_path + ".log", "a")
        t0, n_new, n_patients = time.time(), 0, 0
        for it in items:
            if max_patients is not None and n_patients >= max_patients:
                break
            if all((it["id"], t) in done for t in tasks):
                continue
            clk, prev, reclaimed = QL.try_lock(os.path.join(claim_dir, f"{it['id']}.claim"), info)
            if clk is None:
                continue
            try:
                done = existing_done()
                if all((it["id"], t) in done for t in tasks):
                    continue
                image, aff, px_hash = px(it["image"])
                if px_hash != it["expected_pixel_sha256"]:
                    raise G.RunError(f"input pixel changed for {it['id']}")
                for t in tasks:
                    if (it["id"], t) in done:
                        continue
                    if time_limit and time.time() - t0 > time_limit:
                        log.write(json.dumps({"event": "stop_time_limit", "n_new": n_new}) + "\n")
                        log.flush()
                        return {"n_new": n_new, "n_patients": n_patients}
                    if t == "O":
                        rec = score_O(torch, proc, model, image, it, eos_ids)
                    elif t == "F":
                        rec = score_F(torch, proc, model, image, it, eos_ids)
                    else:
                        raise G.RunError(f"unknown task {t}")
                    rec.update({"variant": "sft", "split": split,
                                "request_id": request_id(t, split, it["id"]),
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


def check_completion(out_dir, items, tasks=("O", "F")):
    problems = []
    expect = {(it["id"], t) for it in items for t in tasks}
    got = {}
    for fn in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        for r in read_records(fn):
            key = (r["id"], r["task"])
            if key in got:
                problems.append(f"duplicate {key}")
            got[key] = r
    missing = expect - set(got)
    extra = set(got) - expect
    if missing:
        problems.append(f"missing {len(missing)} e.g. {sorted(missing)[:3]}")
    if extra:
        problems.append(f"extra {len(extra)} e.g. {sorted(extra)[:3]}")
    return {"ok": not problems, "problems": problems, "expected": len(expect), "got": len(got)}


def load_all(out_dir):
    out = {}
    for fn in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        for r in read_records(fn):
            key = (r["id"], r["task"])
            if key in out:
                raise G.RunError(f"duplicate {key} across worker files in {out_dir}")
            out[key] = r
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-manifest", required=True)
    ap.add_argument("--split", required=True, choices=["C", "E", "D24"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--worker", type=int, required=True)
    ap.add_argument("--protocol", required=True, help="필수: 이번 코드·source manifest를 잠근 protocol 경로")
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-patients", type=int, default=None)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--tasks", default="O,F")
    ap.add_argument("--decide-c", default=None, help="split=E일 때 필수: enter_E=true인 C201 decision 경로")
    ap.add_argument("--accept-protocol", nargs="*", default=[],
                    help="호환성 확인된 과거 실행(D24 등)의 protocol 파일 경로; 해당 digest의 기존 record를 재사용 허용")
    ap.add_argument("--gpu", default=None, help="물리 GPU index; CUDA 초기화 전에 CUDA_VISIBLE_DEVICES로 설정한다 "
                    "(셸에서 env var 접두사 대신 CLI 인자로 받아 승인 프롬프트를 피한다)")
    a = ap.parse_args()
    if a.gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(a.gpu)
    if a.split == "E" and not a.decide_c:
        raise SystemExit("--decide-c is required for split E")

    sm = json.load(open(a.source_manifest))
    if a.split == "D24":
        d24 = RS.select_d24(sm)
        items = d24["one_box"] + d24["two_box"]
        src_split = "C"
    else:
        items = list(sm["patients"][a.split].values())
        src_split = a.split
    if a.ids:
        keep = set(json.load(open(a.ids)))
        items = [it for it in items if it["id"] in keep]
    os.makedirs(a.out_dir, exist_ok=True)
    tasks = tuple(a.tasks.split(","))
    from . import lock_protocol as LP
    accept_digests = tuple(LP.digest_of(p) for p in a.accept_protocol)
    res = run_worker(items, src_split, a.out_dir, a.worker, a.protocol, a.adapter, sm, a.source_manifest,
                      tasks=tasks, time_limit=a.time_limit, max_patients=a.max_patients,
                      decide_c_path=a.decide_c, accept_protocol_digests=accept_digests)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
