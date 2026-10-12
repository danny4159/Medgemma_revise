"""iter_107 CURE 단일 phrase grounding runner + launcher (lk105_run.py의 CURE 경로를 적용, M15/A·B 선택/평가 분기는 사용하지 않는다).

유지: 공식 processor/chat template, CURE CLAHE 448 transform, greedy, cap 1024→2048→4096 비EOS 재시도, 요청 단위 append·fsync,
부분 행 복구(pg43_run.repair_tail), shard completion, 전 shard 정확한 요청 ID 집합 검사, protocol/source/asset digest 잠금.
보완: 큰 가중치 sha256+size+mtime 잠금(launcher는 매번 전체 hash 재계산), admission 실패도 launch 기록에 저장.
출력은 results/iter_107 아래에만 쓴다. GT/extra는 요청에 들어가지 않는다(요청에는 원문 문장만).
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import nr107_spec as S
from report86_common import (ROOT, CAPS, SEED, sha, sha_obj, save, read_jsonl_complete, record_digest, adapter_path_C, base_path, CURE_PY, R85,
                             BASE_REV, ADAPTER_REV)

R107 = ROOT / "results/iter_107"
DATA = R107 / "data"
LOCKFILE = R107 / "protocol/weights_lock.json"
EXEC_SOURCES = ["nr107_run.py", "nr107_spec.py", "nr107_geom.py", "nr107_data.py", "report86_common.py", "pg43_run.py", "rsna_diag/generate.py",
                "rsna_diag/geometry.py", "rsna_diag/parse.py"]
OFFICIAL_DIR = R85 / "official/minimal/vlm_research_kit"
MARGIN_MIB = 2048
PEAK_MIB = 10000  # iter_105 D4_w1f 실측 CURE GPU 점유 최대 9997 MiB(4096-token 재시도 포함). 이번 T4 실측으로 재확인한다.
STAGES = ("T4", "M47")


def all_items():
    return json.loads((DATA / "items.json").read_text())


def stage_items(stage):
    items = all_items()
    if stage == "T4":
        keys = json.loads((DATA / "cohort_summary.json").read_text())["tech_first4_item_keys"]
        m = {it["item_key"]: it for it in items}
        return [m[k] for k in keys]
    assert stage == "M47"
    return items


def raw_map():
    return {r["ImageID"]: r for r in json.loads((DATA / "raw_manifest.json").read_text())}


def requests(stage):
    return S.requests_for(stage_items(stage))


def small_asset_digests():
    d = {}
    snap = Path(base_path("C"))
    assert snap.name == BASE_REV and adapter_path_C().name == ADAPTER_REV
    for p in sorted(snap.iterdir()):
        if (p.suffix in (".json", ".jinja", ".model") and "safetensors.index" not in p.name) or p.name == "model.safetensors.index.json":
            d[f"base/{p.name}"] = sha(p)
    for p in sorted(adapter_path_C().iterdir()):
        if p.name != "adapter_model.safetensors" and p.suffix in (".json", ".jinja"):
            d[f"adapter/{p.name}"] = sha(p)
    for p in sorted(OFFICIAL_DIR.rglob("*.py")):
        d[f"official/{p.relative_to(OFFICIAL_DIR)}"] = sha(p)
    d["official/source_manifest.json"] = sha(R85 / "official/source_manifest.json")
    return d


def weights_files():
    fs = sorted(Path(base_path("C")).glob("*.safetensors"))
    fs.append(adapter_path_C() / "adapter_model.safetensors")
    return fs


def weight_stat(f):
    st = f.resolve().stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def make_weights_lock():
    """실제 base/adapter 가중치 sha256 을 새로 계산한다(이전 lock 계승 없음). 이미 있으면 FileExistsError."""
    w = {}
    for f in weights_files():
        w[f.resolve().name] = {"sha256": sha(f.resolve()), **weight_stat(f)}
    out = {"created": time.time(), "base_revision": BASE_REV, "adapter_revision": ADAPTER_REV, "weights": w, "small": small_asset_digests()}
    save(LOCKFILE, out)
    return out


def check_weights_lock(full=False):
    lock = json.loads(LOCKFILE.read_text())
    assert small_asset_digests() == lock["small"], "asset digest (processor/config/chat template/official transform) changed"
    for f in weights_files():
        n = f.resolve().name
        assert n in lock["weights"], f"unlocked weight {n}"
        st = weight_stat(f)
        assert st["size"] == lock["weights"][n]["size"] and st["mtime_ns"] == lock["weights"][n]["mtime_ns"], f"weight file changed {n}"
        if full:
            assert sha(f.resolve()) == lock["weights"][n]["sha256"], f"weight sha256 changed {n}"
    return lock


def scientific_protocol(stage, nshards):
    reqs = requests(stage)
    return {"system": "CURE", "stage": stage, "nshards": nshards, "seed": SEED, "caps": CAPS, "precision": "nf4_bf16_clahe448",
            "requests_sha256": sha_obj(reqs), "n_requests": len(reqs), "items_sha256": sha(DATA / "items.json"),
            "raw_sha256": sha(DATA / "raw_manifest.json"), "cohort_summary_sha256": sha(DATA / "cohort_summary.json"),
            "weights_lock_sha256": sha(LOCKFILE), "source_sha256": {f: sha(ROOT / f) for f in EXEC_SOURCES}}


def isolated_env():
    env = dict(os.environ)
    cache = R107 / "runtime_cache"
    for key, name in {"HF_HOME": "hf", "HF_HUB_CACHE": "hf/hub", "HF_XET_CACHE": "hf/xet", "XDG_CACHE_HOME": "xdg", "TORCH_HOME": "torch",
                      "TORCHINDUCTOR_CACHE_DIR": "inductor", "TRITON_CACHE_DIR": "triton", "CUDA_CACHE_PATH": "cuda",
                      "MPLCONFIGDIR": "matplotlib", "TMPDIR": "tmp"}.items():
        p = cache / name
        p.mkdir(parents=True, exist_ok=True)
        env[key] = str(p)
    env.update({"HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false", "NO_ALBUMENTATIONS_UPDATE": "1"})
    return env


def shard_dir(out, s):
    return Path(out) / "cure" / f"shard{s}"


def shard_target(stage, s, nshards):
    items = stage_items(stage)
    mine = {it["item_key"] for i, it in enumerate(items) if i % nshards == s}
    return [q for q in requests(stage) if q["item_key"] in mine]


def load_own(d, reqmap, sci_digest):
    mine = read_jsonl_complete(Path(d) / "outputs.jsonl")
    ids = [r["id"] for r in mine]
    assert len(ids) == len(set(ids)), "duplicate id in own output"
    for r in mine:
        q = reqmap.get(r["id"])
        assert q is not None, f"record outside request set {r['id']}"
        assert r["protocol_digest"] == sci_digest, "record protocol digest mismatch"
        assert r["record_digest"] == record_digest(r), "record digest mismatch (tampered)"
        for k in ("prompt", "ImageID", "modality", "kind", "cond", "item_key"):
            assert r[k] == q[k], f"record {k} differs from request"
        assert r["n_pixel_values"] > 0 and r["n_image_tokens"] > 0, "image request lacks image tokens/pixels"
    return mine


def verify_completion(d, stage, s, nshards, sci_digest):
    d = Path(d)
    c = json.loads((d / "completion.json").read_text())
    for name, h in c["files"].items():
        assert sha(d / name) == h, f"completion file hash differs: {d}/{name}"
    target = shard_target(stage, s, nshards)
    reqmap = {q["id"]: q for q in target}
    recs = load_own(d, reqmap, sci_digest)
    assert {r["id"] for r in recs} == set(reqmap), "record set != expected request set (missing/extra)"
    assert len(recs) == len(target) == c["n_own_records"]
    return c, recs


def worker(a):
    out = Path(a.out).resolve()
    out.relative_to(R107)
    allowed = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    assert a.gpu in allowed, f"gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}"
    os.environ["CUDA_VISIBLE_DEVICES"] = a.gpu
    check_weights_lock()
    raw = raw_map()
    for it in stage_items(a.stage):
        assert sha(raw[it["ImageID"]]["raw_path"]) == raw[it["ImageID"]]["sha256"], "raw image changed"
    sci = scientific_protocol(a.stage, a.nshards)
    sci_digest = sha_obj(sci)
    d = shard_dir(out, a.shard)
    d.mkdir(parents=True, exist_ok=True)
    lock = (d / "worker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail
    repair_tail(str(d / "outputs.jsonl"))
    meta = {"scientific": sci, "scientific_digest": sci_digest, "stage": a.stage, "shard": a.shard, "nshards": a.nshards}
    mypath = d / "scientific_protocol.json"
    if mypath.exists():
        assert json.loads(mypath.read_text()) == json.loads(json.dumps(meta)), "resume: protocol/source/shard mismatch (before model load)"
    else:
        save(mypath, meta)
    target = shard_target(a.stage, a.shard, a.nshards)
    reqmap = {q["id"]: q for q in target}
    if (d / "completion.json").exists():
        verify_completion(d, a.stage, a.shard, a.nshards, sci_digest)
        return 0
    mine = load_own(d, reqmap, sci_digest)
    done = {r["id"] for r in mine}
    todo = [q for q in target if q["id"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    events = (d / "executions.jsonl").open("a", buffering=1)
    execution = {"event": "start", "time": time.time(), "pid": os.getpid(), "gpu_physical": a.gpu, "python": sys.executable,
                 "n_todo": len(todo), "n_target": len(target), "n_done_before": len(done)}
    if todo:
        generate(a, d, events, execution, todo, raw, sci_digest)
    finish(d, a, target, reqmap, sci_digest)
    return 0


def load_model():
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
    from peft import PeftModel
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    base = base_path("C")
    processor = AutoProcessor.from_pretrained(base, local_files_only=True)
    kw = dict(torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True, attn_implementation="sdpa",
              quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
                                                     bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_storage=torch.bfloat16))
    model = AutoModelForImageTextToText.from_pretrained(base, **kw)
    model = PeftModel.from_pretrained(model, str(adapter_path_C()), local_files_only=True)
    assert set(model.peft_config["default"].modules_to_save) == {"lm_head", "embed_tokens"}
    processor.tokenizer.padding_side = "left"
    model.eval()
    assert not any(m.training for m in model.modules())
    return torch, processor, model


def generate(a, d, events, execution, todo, raw, sci_digest):
    import numpy as np
    from rsna_diag import generate as G
    t0 = time.monotonic()
    torch, processor, model = load_model()
    loading_s = time.monotonic() - t0
    sys.path.insert(0, str(OFFICIAL_DIR.parent))
    from vlm_research_kit.data.transforms_factory import create_image_transforms
    transform = create_image_transforms(use_model_specific_transforms=True, model_name="pil_with_augmentations", bbox_format="cxcywh",
                                        image_size=[448, 448], is_train=False, augmenter_override_params={"apply_clahe": True, "clahe_clip_limit": [3., 3.]})
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    img_tok = getattr(processor, "image_token_id", None)
    assert img_tok is not None
    import transformers
    events.write(json.dumps({**execution, "torch": torch.__version__, "transformers": transformers.__version__, "loading_s": loading_s}) + "\n")
    saved = 0
    t_start = time.monotonic()
    with (d / "outputs.jsonl").open("a", buffering=1) as f:
        for q in todo:
            img = q["ImageID"]
            im = transform(raw[img]["raw_path"])["pixel_values"]
            px_sha = hashlib.sha256(np.asarray(im).tobytes()).hexdigest()
            events.write(json.dumps({"event": "request_start", "id": q["id"], "time": time.time()}) + "\n")
            inp = G.build_inputs(processor, im, q["prompt"])
            official = processor.apply_chat_template([{"role": "user", "content": [{"type": "image", "image": im}, {"type": "text", "text": q["prompt"]}]}],
                                                     add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt", padding=True)
            assert set(inp) == set(official) and all(torch.equal(inp[k], official[k]) for k in inp), "builder != official chat template"
            n_img_tok = int((inp["input_ids"] == img_tok).sum())
            n_pix = int(inp["pixel_values"].shape[0])
            assert n_pix > 0 and n_img_tok > 0
            attempts = []
            for cap in CAPS:
                result = G.generate(torch, processor, model, inp, cap, eos)
                attempts.append(result)
                if result["ended_eos"]:
                    break
            rec = {"id": q["id"], "ImageID": img, "item_key": q["item_key"], "system": "CURE", "kind": q["kind"], "modality": q["modality"],
                   "cond": q["cond"], "order": q["order"], "prompt": q["prompt"], "protocol_digest": sci_digest, "image_sha256": raw[img]["sha256"],
                   "text": processor.decode(result["suffix_ids"], skip_special_tokens=True), "attempts": attempts,
                   "input_ids": inp["input_ids"][0].tolist(), "n_image_tokens": n_img_tok, "n_pixel_values": n_pix, "pixel_sha256": px_sha,
                   "exec": {"gpu": a.gpu, "shard": a.shard, "pid": os.getpid(), "torch": torch.__version__}}
            rec["record_digest"] = record_digest(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
            saved += 1
            events.write(json.dumps({"event": "request_saved", "id": q["id"], "time": time.time(), "seconds": result["runtime_s"],
                                     "n_new": result["n_new"], "attempts": len(attempts)}) + "\n")
            print(json.dumps({"saved": saved, "of": len(todo), "shard": a.shard, "tokens": result["n_new"], "seconds": round(result["runtime_s"], 2)}), flush=True)
    allrecs = read_jsonl_complete(d / "outputs.jsonl")
    events.write(json.dumps({"event": "end", "time": time.time(), "saved": saved, "wall_s": time.monotonic() - t_start,
                             "peak_reserved_gib_max": max(max(x["peak_mem_reserved_gb"] for x in r["attempts"]) for r in allrecs)}) + "\n")


def finish(d, a, target, reqmap, sci_digest):
    recs = load_own(d, reqmap, sci_digest)
    got = {r["id"] for r in recs}
    want = {q["id"] for q in target}
    cp = d / "completion.json"
    if want == got and not cp.exists():
        events = [json.loads(l) for l in (d / "executions.jsonl").read_text().splitlines() if l]
        save(cp, {"stage": a.stage, "system": "CURE", "shard": a.shard, "nshards": a.nshards, "n_own_records": len(recs), "n_expected_in_shard": len(want),
                  "files": {"scientific_protocol.json": sha(d / "scientific_protocol.json"), "outputs.jsonl": sha(d / "outputs.jsonl")},
                  "final_not_eos": sum(not r["attempts"][-1]["ended_eos"] for r in recs),
                  "executions": len([e for e in events if e["event"] == "start"]),
                  "generation_s_total": sum(sum(x["runtime_s"] for x in r["attempts"]) for r in recs),
                  "cost_scope": "generation seconds of records in this shard dir; loading/interrupted cost in executions.jsonl"})


def smi_free():
    raw = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.free,memory.used,memory.total", "--format=csv,noheader,nounits"], text=True)
    return {x.split(",")[0].strip(): [int(v) for v in x.split(",")[1:]] for x in raw.splitlines()}


def next_attempt(out):
    nums = [int(m.group(1)) for p in Path(out).glob("launch*_*.stdout.log") for m in [re.match(r"launch(\d+)_", p.name)] if m]
    nums += [int(m.group(1)) for p in Path(out).glob("launch_*.json") for m in [re.match(r"launch_(\d+)\.json", p.name)] if m]
    return max(nums) + 1 if nums else 0


def launch(a):
    out = Path(a.out).resolve()
    out.relative_to(R107)
    out.mkdir(parents=True, exist_ok=True)
    allowed = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    check_weights_lock(full=True)
    with (out / "launcher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sd = sha_obj(scientific_protocol(a.stage, a.workers))
        mp = out / "mapping.json"
        want_map = {"stage": a.stage, "workers": a.workers, "scientific_digest": sd}
        if mp.exists():
            assert json.loads(mp.read_text()) == want_map, "launcher mapping/protocol changed (source or inputs differ)"
        else:
            save(mp, want_map)
        jobs = list(range(a.workers))
        pending = [k for k in jobs if not (shard_dir(out, k) / "completion.json").exists()]
        for k in jobs:
            if k not in pending:
                verify_completion(shard_dir(out, k), a.stage, k, a.workers, sd)
        if not pending:
            return 0
        procs, logs, admission, codes, status, err = [], [], [], {}, "started", None
        attempt = next_attempt(out)
        start = time.monotonic()
        env = isolated_env()
        # worker -> GPU 배치: --placement "0,1,0,1" 형태(논리 index, 허용 집합 안에서만) 또는 여유 메모리 순 자동 배정
        placement = a.placement.split(",") if a.placement else None
        if placement:
            assert len(placement) >= len(pending) and set(placement) <= set(allowed), ("placement outside allowed GPUs", placement, allowed)

        def stop(*args):
            raise KeyboardInterrupt("supervisor stopped; terminating owned children")
        signal.signal(signal.SIGTERM, stop)
        try:
            for n, k in enumerate(pending):
                st = smi_free()
                apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"], text=True)
                actual = {int(x.split(",")[0]): int(x.split(",")[1]) for x in apps.splitlines() if x.strip()}
                choices = {g: st[g][0] - sum(max(0, PEAK_MIB - actual.get(p.pid, 0)) + MARGIN_MIB for kk, p, gg in procs if gg == g and p.poll() is None)
                           for g in allowed}
                gpu = placement[n] if placement else max(choices, key=choices.get)
                need = PEAK_MIB + MARGIN_MIB
                admission.append({"job": k, "choices_free_mib": choices, "chosen": gpu, "need_mib": need, "smi": st})
                assert choices[gpu] >= need, ("memory admission refused", choices)
                cmd = [sys.executable, str(ROOT / "nr107_run.py"), "worker", "--stage", a.stage, "--out", str(out), "--gpu", gpu, "--shard", str(k),
                       "--nshards", str(a.workers)] + (["--limit", str(a.limit)] if a.limit else [])
                cmd[0] = str(CURE_PY)
                so = (out / f"launch{attempt}_cure{k}.stdout.log").open("x")
                se = (out / f"launch{attempt}_cure{k}.stderr.log").open("x")
                logs.extend([so, se])
                procs.append((k, subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=so, stderr=se), gpu))
                time.sleep(a.stagger)
            with (out / f"launch{attempt}_resource.jsonl").open("x") as rf:
                while any(p.poll() is None for _, p, _ in procs):
                    rf.write(json.dumps({"t": time.time(), "smi": smi_free()}) + "\n")
                    rf.flush()
                    time.sleep(10)
            codes = {f"cure{k}": p.wait() for k, p, _ in procs}
            status = "finished"
        except BaseException as e:  # admission 거부·중단도 기록으로 남긴다
            status, err = "failed", repr(e)
            raise
        finally:
            for _, p, _ in procs:
                if p.poll() is None:
                    p.terminate()
            for _, p, _ in procs:
                p.wait()
            for f in logs:
                f.close()
            save(out / f"launch_{attempt:03}.json", dict(status=status, error=err, codes=codes, wall_s=time.monotonic() - start,
                                                          mapping={f"cure{k}": g for k, _, g in procs}, scientific_digest=sd, allowed=allowed,
                                                          admission=admission, peak_mib=PEAK_MIB, script_sha256=sha(__file__)))
        assert all(c == 0 for c in codes.values()), codes
        if all((shard_dir(out, k) / "completion.json").exists() for k in jobs):
            for k in jobs:
                verify_completion(shard_dir(out, k), a.stage, k, a.workers, sd)
            save(out / "completion.json", {"stage": a.stage, "workers": a.workers, "scientific_digest": sd,
                                           "files": {f"cure/shard{k}/completion.json": sha(shard_dir(out, k) / "completion.json") for k in jobs}})
            return 0
        return 0 if a.limit else 2


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["worker", "launch", "lock_weights"])
    p.add_argument("--stage", choices=STAGES)
    p.add_argument("--out")
    p.add_argument("--gpu")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--nshards", type=int, default=1)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--placement", default="", help="worker별 GPU 논리 index 쉼표 목록(허용 집합 안)")
    p.add_argument("--limit", type=int, default=0, help="통제된 중단 시험용: 이번 실행 저장 최대 요청 수")
    p.add_argument("--stagger", type=float, default=15.0)
    a = p.parse_args()
    if a.command == "lock_weights":
        lk = make_weights_lock()
        print(json.dumps({"weights": {k: v["sha256"] for k, v in lk["weights"].items()}}))
        raise SystemExit(0)
    raise SystemExit(worker(a) if a.command == "worker" else launch(a))
