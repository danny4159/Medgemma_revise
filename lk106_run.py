"""iter_106 생성 runner + launcher (CURE 전용). iter_105 lk105_run.py(승인된 경로)를 복사해 요청 집합·출력 경로·timing 경계만 바꿨다.
입력(D4/E32 36명, 영상, raw)은 results/iter_105/data를 읽기 전용으로 쓰고 모든 출력은 results/iter_106 아래에만 쓴다.

report101_cure.py의 모델 로딩·입력·생성 경로(공식 processor/chat template, CURE는 CLAHE 448 transform, greedy, cap 1024→2048→4096,
요청 단위 append, 부분 행 복구, shard completion)를 유지하고 iter_101의 재사용 결함을 이번 경로에서 보완한다:
 - 전 shard 정확한 요청 ID 집합 검사(누락·잉여·중복 거부), completion 변조 거부, 요청 prompt/modality 대조.
 - protocol에 실행 소스 + 공식 transform 소스(vlm_research_kit) + base/adapter/processor 자산 digest(weights_lock.json) 잠금.
 - 완료 행이 있는 부분 실행의 재개: 기존 행 보존·중복 방지·완료 재실행 불변.
 - launcher: 허용 GPU 집합 검사, 단일 소유권, 시작 직전 실제 여유 메모리와 이미 살아 있는 worker 예약(peak+2GiB) 합산.
출력은 results/iter_105 아래에만 쓴다. GT는 요청 구성(C/W 제안 문장)에만 쓰이며 모델 입력에는 제안 외 정답이 들어가지 않는다.
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

import lk106_spec as S
from report86_common import (ROOT, CAPS, SEED, MODEL15_REV, sha, sha_obj, save, read_jsonl_complete, record_digest,
                             adapter_path_C, base_path, CURE_PY, R85)

R105 = ROOT / "results/iter_105"
R106 = ROOT / "results/iter_106"
DATA = R105 / "data"  # iter_105 고정 D4/E32 입력(읽기 전용)
LOCKFILE = R106 / "protocol/weights_lock.json"
EXEC_SOURCES = ["lk106_run.py", "lk106_spec.py", "report86_common.py", "pg43_run.py", "rsna_diag/generate.py", "rsna_diag/geometry.py",
                "rsna_diag/parse.py"]
OFFICIAL_DIR = R85 / "official/minimal/vlm_research_kit"
MARGIN_MIB = 2048
PEAK_MIB = {"CURE": 10000}  # iter_105 실측 CURE 최대 9997MiB(참고). 새 요청 peak는 D4에서 재측정한다.
PY = {"CURE": str(CURE_PY)}
TAGS = {"CURE": "cure"}
STAGE_CONDS = {"D4": ["I1", "I2", "J12", "J21", "R11", "R22"], "E32": ["J12", "J21", "R11", "R22"]}


def stage_rows(stage):
    rows = json.loads((DATA / f"inputs_{stage}.json").read_text())
    raw = {r["ImageID"]: r for r in json.loads((DATA / f"raw_manifest_{stage}.json").read_text())}
    return rows, raw


def requests(stage, system):
    rows, _ = stage_rows(stage)
    assert system == "CURE"
    return S.requests_for(rows, STAGE_CONDS[stage])


def small_asset_digests(system):
    """processor/tokenizer/config/chat template 및 (CURE) 공식 transform 소스 digest."""
    d = {}
    snap = Path(base_path("C"))
    for p in sorted(snap.iterdir()):
        if p.suffix in (".json", ".jinja", ".model") and "safetensors.index" not in p.name or p.name == "model.safetensors.index.json":
            d[f"base/{p.name}"] = sha(p)
    if system == "CURE":
        for p in sorted(adapter_path_C().iterdir()):
            if p.name != "adapter_model.safetensors" and p.suffix in (".json", ".jinja"):
                d[f"adapter/{p.name}"] = sha(p)
        for p in sorted(OFFICIAL_DIR.rglob("*.py")):
            d[f"official/{p.relative_to(OFFICIAL_DIR)}"] = sha(p)
        d["official/source_manifest.json"] = sha(R85 / "official/source_manifest.json")
    return d


def weights_files(system):
    snap = Path(base_path("C"))
    fs = sorted(snap.glob("*.safetensors"))
    if system == "CURE":
        fs.append(adapter_path_C() / "adapter_model.safetensors")
    return fs


def make_weights_lock():
    """iter_105 weights_lock의 큰 가중치 sha256을 상속하되 현재 파일 크기·작은 자산 digest가 모두 일치할 때만 새 lock을 만든다."""
    old = json.loads((R105 / "protocol/weights_lock.json").read_text())["CURE"]
    out = {"model15_revision": MODEL15_REV, "created": time.time(), "inherited_from": "results/iter_105/protocol/weights_lock.json",
           "inherited_sha256": sha(R105 / "protocol/weights_lock.json")}
    for system in ["CURE"]:
        w = {}
        for f in weights_files(system):
            f = f.resolve()
            st = f.stat()
            assert f.name in old["weights"] and old["weights"][f.name]["size"] == st.st_size, f"weight size differs from iter_105 lock {f.name}"
            w[f.name] = {"sha256": old["weights"][f.name]["sha256"], "size": st.st_size}
        small = small_asset_digests(system)
        assert small == old["small"], "small asset digests differ from iter_105 lock"
        out[system] = {"weights": w, "small": small}
    save(LOCKFILE, out)
    return out


def check_weights_lock(system):
    """작은 자산 digest 재계산 + 가중치 크기 대조(가중치 전체 hash는 lock 생성 시 계산)."""
    lock = json.loads(LOCKFILE.read_text())[system]
    assert small_asset_digests(system) == lock["small"], "asset digest (processor/config/official transform) changed"
    for f in weights_files(system):
        f = f.resolve()
        assert f.name in lock["weights"] and f.stat().st_size == lock["weights"][f.name]["size"], f"weight file changed {f.name}"
    return lock


def scientific_protocol(stage, system, nshards):
    reqs = requests(stage, system)
    return {"system": system, "stage": stage, "nshards": nshards, "seed": SEED, "caps": CAPS,
            "precision": "nf4_bf16_clahe448" if system == "CURE" else "bf16_pad_square",
            "requests_sha256": sha_obj(reqs), "n_requests": len(reqs),
            "stage_conds": STAGE_CONDS[stage], "input_sha256": sha(DATA / f"inputs_{stage}.json"), "raw_sha256": sha(DATA / f"raw_manifest_{stage}.json"),
            "selection_lock_sha256": sha(DATA / "selection_lock.json"), "weights_lock_sha256": sha(LOCKFILE),
            "source_sha256": {f: sha(ROOT / f) for f in EXEC_SOURCES}, "model15_revision": MODEL15_REV}


def isolated_env():
    env = dict(os.environ)
    cache = R106 / "runtime_cache"
    for key, name in {"HF_HOME": "hf", "HF_HUB_CACHE": "hf/hub", "HF_XET_CACHE": "hf/xet", "XDG_CACHE_HOME": "xdg", "TORCH_HOME": "torch",
                      "TORCHINDUCTOR_CACHE_DIR": "inductor", "TRITON_CACHE_DIR": "triton", "CUDA_CACHE_PATH": "cuda",
                      "MPLCONFIGDIR": "matplotlib", "TMPDIR": "tmp"}.items():
        p = cache / name
        p.mkdir(parents=True, exist_ok=True)
        env[key] = str(p)
    env.update({"HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false", "NO_ALBUMENTATIONS_UPDATE": "1"})
    return env


def shard_dir(out, system, s):
    return Path(out) / TAGS[system] / f"shard{s}"


def shard_target(stage, system, s, nshards):
    rows, _ = stage_rows(stage)
    mine = {r["ImageID"] for i, r in enumerate(rows) if i % nshards == s}
    return [q for q in requests(stage, system) if q["ImageID"] in mine]


def load_own(d, reqmap, sci_digest, image_ids):
    mine = read_jsonl_complete(Path(d) / "outputs.jsonl")
    ids = [r["id"] for r in mine]
    assert len(ids) == len(set(ids)), "duplicate id in own output"
    for r in mine:
        q = reqmap.get(r["id"])
        assert q is not None, f"record outside request set {r['id']}"
        assert r["ImageID"] in image_ids, "record belongs to another shard"
        assert r["protocol_digest"] == sci_digest, "record protocol digest mismatch"
        assert r["record_digest"] == record_digest(r), "record digest mismatch (tampered)"
        for k in ("prompt", "ImageID", "modality", "kind", "cond", "order"):
            assert r[k] == q[k], f"record {k} differs from request"
        if q["modality"] == "text":
            assert r["n_pixel_values"] == 0 and r["n_image_tokens"] == 0, "text request carried image tokens/pixels"
        else:
            assert r["n_pixel_values"] > 0 and r["n_image_tokens"] > 0, "image request lacks image tokens/pixels"
    return mine


def verify_completion(d, stage, system, s, nshards, sci_digest):
    """completion 파일 hash와 요청 집합(정확 일치)을 전수 재검증한다."""
    d = Path(d)
    c = json.loads((d / "completion.json").read_text())
    for name, h in c["files"].items():
        assert sha(d / name) == h, f"completion file hash differs: {d}/{name}"
    target = shard_target(stage, system, s, nshards)
    reqmap = {q["id"]: q for q in target}
    recs = load_own(d, reqmap, sci_digest, {q["ImageID"] for q in target})
    assert {r["id"] for r in recs} == set(reqmap), "record set != expected request set (missing/extra)"
    assert len(recs) == len(target) == c["n_own_records"]
    return c, recs


def worker(a):
    out = Path(a.out).resolve()
    out.relative_to(R106)
    allowed = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    assert a.gpu in allowed, f"gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}"
    os.environ["CUDA_VISIBLE_DEVICES"] = a.gpu
    check_weights_lock(a.system)
    rows, raw = stage_rows(a.stage)
    for row in rows:
        assert sha(row["image"]) == row["file_sha256"], f"input image changed {row['ImageID']}"
        assert sha(raw[row["ImageID"]]["raw_path"]) == raw[row["ImageID"]]["sha256"], "raw image changed"
    sci = scientific_protocol(a.stage, a.system, a.nshards)
    sci_digest = sha_obj(sci)
    d = shard_dir(out, a.system, a.shard)
    d.mkdir(parents=True, exist_ok=True)
    lock = (d / "worker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail
    repair_tail(str(d / "outputs.jsonl"))
    meta = {"scientific": sci, "scientific_digest": sci_digest, "stage": a.stage, "system": a.system, "shard": a.shard, "nshards": a.nshards}
    mypath = d / "scientific_protocol.json"
    if mypath.exists():
        assert json.loads(mypath.read_text()) == json.loads(json.dumps(meta)), "resume: protocol/source/shard mismatch (before model load)"
    else:
        save(mypath, meta)
    target = shard_target(a.stage, a.system, a.shard, a.nshards)
    reqmap = {q["id"]: q for q in target}
    image_ids = {q["ImageID"] for q in target}
    if (d / "completion.json").exists():
        verify_completion(d, a.stage, a.system, a.shard, a.nshards, sci_digest)
        return 0
    mine = load_own(d, reqmap, sci_digest, image_ids)
    done = {r["id"] for r in mine}
    todo = [q for q in target if q["id"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    events = (d / "executions.jsonl").open("a", buffering=1)
    execution = {"event": "start", "time": time.time(), "pid": os.getpid(), "gpu_physical": a.gpu, "python": sys.executable,
                 "n_todo": len(todo), "n_target": len(target), "n_done_before": len(done)}
    if todo:
        generate(a, d, events, execution, todo, rows, raw, sci_digest)
    finish(d, a, target, reqmap, sci_digest, image_ids)
    return 0


def load_model(system):
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    if system == "CURE":
        from transformers import BitsAndBytesConfig
        from peft import PeftModel
        base = base_path("C")
        processor = AutoProcessor.from_pretrained(base, local_files_only=True)
        kw = dict(torch_dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True, attn_implementation="sdpa",
                  quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
                                                         bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_storage=torch.bfloat16))
        model = AutoModelForImageTextToText.from_pretrained(base, **kw)
        model = PeftModel.from_pretrained(model, str(adapter_path_C()), local_files_only=True)
        assert set(model.peft_config["default"].modules_to_save) == {"lm_head", "embed_tokens"}
    else:
        base = base_path("M15")
        processor = AutoProcessor.from_pretrained(base, local_files_only=True)
        model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.bfloat16, device_map={"": 0}, local_files_only=True)
    processor.tokenizer.padding_side = "left"
    model.eval()
    assert not any(m.training for m in model.modules())
    return torch, processor, model


def generate(a, d, events, execution, todo, rows, raw, sci_digest):
    import numpy as np
    from rsna_diag import generate as G
    t0 = time.monotonic()
    torch, processor, model = load_model(a.system)
    loading_s = time.monotonic() - t0
    transform = None
    if a.system == "CURE":
        sys.path.insert(0, str(OFFICIAL_DIR.parent))
        from vlm_research_kit.data.transforms_factory import create_image_transforms
        transform = create_image_transforms(use_model_specific_transforms=True, model_name="pil_with_augmentations", bbox_format="cxcywh",
                                            image_size=[448, 448], is_train=False,
                                            augmenter_override_params={"apply_clahe": True, "clahe_clip_limit": [3., 3.]})
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    img_tok = getattr(processor, "image_token_id", None)
    assert img_tok is not None
    import transformers
    events.write(json.dumps({**execution, "torch": torch.__version__, "transformers": transformers.__version__, "loading_s": loading_s}) + "\n")
    by_img = {}
    for q in todo:
        by_img.setdefault(q["ImageID"], []).append(q)
    rowmap = {r["ImageID"]: r for r in rows}
    saved = 0
    t_start = time.monotonic()
    with (d / "outputs.jsonl").open("a", buffering=1) as f:
        for img in [r["ImageID"] for r in rows if r["ImageID"] in by_img]:
            row = rowmap[img]
            for q in by_img[img]:
                t_req = time.monotonic()
                events.write(json.dumps({"event": "request_start", "id": q["id"], "time": time.time()}) + "\n")
                # end-to-end 경계: 공식 CLAHE transform부터 저장 직전까지를 요청마다 포함한다(독립 2요청 vs 공동 1요청 비용 비교용).
                im = transform(raw[img]["raw_path"])["pixel_values"]
                px_sha = hashlib.sha256(np.asarray(im).tobytes()).hexdigest()
                if q["modality"] == "image":
                    inp = G.build_inputs(processor, im, q["prompt"])
                    official = processor.apply_chat_template([{"role": "user", "content": [{"type": "image", "image": im}, {"type": "text", "text": q["prompt"]}]}],
                                                             add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt", padding=True)
                else:
                    inp = G.build_inputs_text(processor, q["prompt"])
                    official = processor.apply_chat_template([{"role": "user", "content": [{"type": "text", "text": q["prompt"]}]}],
                                                             add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt", padding=True)
                assert set(inp) == set(official) and all(torch.equal(inp[k], official[k]) for k in inp), "builder != official chat template"
                n_img_tok = int((inp["input_ids"] == img_tok).sum())
                n_pix = int(inp["pixel_values"].shape[0]) if "pixel_values" in inp else 0
                if q["modality"] == "text":
                    assert n_pix == 0 and n_img_tok == 0, "text-only input has image token/pixel_values"
                else:
                    assert n_pix > 0 and n_img_tok > 0
                attempts = []
                for cap in CAPS:
                    result = G.generate(torch, processor, model, inp, cap, eos)
                    attempts.append(result)
                    if result["ended_eos"]:
                        break
                rec = {"id": q["id"], "ImageID": img, "system": a.system, "kind": q["kind"], "modality": q["modality"], "cond": q["cond"],
                       "order": q["order"], "prompt": q["prompt"], "protocol_digest": sci_digest,
                       "image_sha256": row["file_sha256"] if q["modality"] == "image" else None,
                       "text": processor.decode(result["suffix_ids"], skip_special_tokens=True),
                       "attempts": attempts, "input_ids": inp["input_ids"][0].tolist(), "n_image_tokens": n_img_tok, "n_pixel_values": n_pix,
                       "pixel_sha256": px_sha if q["modality"] == "image" else None,
                       "e2e_s": time.monotonic() - t_req,
                       "exec": {"gpu": a.gpu, "shard": a.shard, "pid": os.getpid(), "torch": torch.__version__}}
                rec["record_digest"] = record_digest(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
                saved += 1
                events.write(json.dumps({"event": "request_saved", "id": q["id"], "time": time.time(), "seconds": result["runtime_s"], "e2e_s": rec["e2e_s"],
                                         "n_new": result["n_new"], "attempts": len(attempts)}) + "\n")
                print(json.dumps({"saved": saved, "of": len(todo), "shard": a.shard, "system": a.system, "tokens": result["n_new"],
                                  "seconds": round(result["runtime_s"], 2)}), flush=True)
    allrecs = read_jsonl_complete(d / "outputs.jsonl")
    events.write(json.dumps({"event": "end", "time": time.time(), "saved": saved, "wall_s": time.monotonic() - t_start,
                             "peak_reserved_gib_max": max(max(x["peak_mem_reserved_gb"] for x in r["attempts"]) for r in allrecs)}) + "\n")


def finish(d, a, target, reqmap, sci_digest, image_ids):
    recs = load_own(d, reqmap, sci_digest, image_ids)
    got = {r["id"] for r in recs}
    want = {q["id"] for q in target}
    cp = d / "completion.json"
    if want == got and not cp.exists():
        events = [json.loads(l) for l in (d / "executions.jsonl").read_text().splitlines() if l]
        save(cp, {"stage": a.stage, "system": a.system, "shard": a.shard, "nshards": a.nshards, "n_own_records": len(recs),
                  "n_expected_in_shard": len(want),
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
    return max(nums) + 1 if nums else 0


def launch(a):
    out = Path(a.out).resolve()
    out.relative_to(R106)
    out.mkdir(parents=True, exist_ok=True)
    allowed = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    systems = a.systems.split(",")
    assert set(systems) <= {"CURE"}
    for system in systems:
        check_weights_lock(system)
    with (out / "launcher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sds = {s: sha_obj(scientific_protocol(a.stage, s, a.workers)) for s in systems}
        mp = out / f"mapping_{'_'.join(systems)}.json"
        want_map = {"stage": a.stage, "workers": a.workers, "systems": systems, "scientific_digests": sds}
        if mp.exists():
            assert json.loads(mp.read_text()) == want_map, "launcher mapping/protocol changed (source or inputs differ)"
        else:
            save(mp, want_map)
        jobs = [(s, k) for s in systems for k in range(a.workers)]
        pending = [(s, k) for s, k in jobs if not (shard_dir(out, s, k) / "completion.json").exists()]
        for s, k in jobs:
            if (s, k) not in pending:
                verify_completion(shard_dir(out, s, k), a.stage, s, k, a.workers, sds[s])
        if not pending:
            return 0
        procs, logs, admission = [], [], []
        attempt = next_attempt(out)
        start = time.monotonic()
        env = isolated_env()

        def stop(*args):
            raise KeyboardInterrupt("supervisor stopped; terminating owned children")
        signal.signal(signal.SIGTERM, stop)
        try:
            for s, k in pending:
                st = smi_free()
                apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"], text=True)
                actual = {int(x.split(",")[0]): int(x.split(",")[1]) for x in apps.splitlines() if x.strip()}
                choices = {g: st[g][0] - sum(max(0, PEAK_MIB[ss] - actual.get(p.pid, 0)) + MARGIN_MIB
                                              for ss, _, p, gg in procs if gg == g and p.poll() is None) for g in allowed}
                gpu = max(choices, key=choices.get)
                need = PEAK_MIB[s] + MARGIN_MIB
                admission.append({"job": [s, k], "choices_free_mib": choices, "chosen": gpu, "need_mib": need, "smi": st})
                assert choices[gpu] >= need, ("memory admission refused", choices)
                cmd = [PY[s], str(ROOT / "lk106_run.py"), "worker", "--stage", a.stage, "--system", s, "--out", str(out), "--gpu", gpu,
                       "--shard", str(k), "--nshards", str(a.workers)] + (["--limit", str(a.limit)] if a.limit else [])
                so = (out / f"launch{attempt}_{TAGS[s]}{k}.stdout.log").open("x")
                se = (out / f"launch{attempt}_{TAGS[s]}{k}.stderr.log").open("x")
                logs.extend([so, se])
                procs.append((s, k, subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=so, stderr=se), gpu))
                time.sleep(a.stagger)
            with (out / f"launch{attempt}_resource.jsonl").open("x") as rf:
                while any(p.poll() is None for _, _, p, _ in procs):
                    rf.write(json.dumps({"t": time.time(), "smi": smi_free()}) + "\n")
                    rf.flush()
                    time.sleep(10)
            codes = {f"{s}{k}": p.wait() for s, k, p, _ in procs}
        finally:
            for _, _, p, _ in procs:
                if p.poll() is None:
                    p.terminate()
            for _, _, p, _ in procs:
                p.wait()
            for f in logs:
                f.close()
        save(out / f"launch_{attempt:03}.json", dict(codes=codes, wall_s=time.monotonic() - start, mapping={f"{s}{k}": g for s, k, _, g in procs},
                                                      scientific_digests=sds, allowed=allowed, admission=admission, peak_mib=PEAK_MIB,
                                                      script_sha256=sha(__file__)))
        assert all(c == 0 for c in codes.values()), codes
        if all((shard_dir(out, s, k) / "completion.json").exists() for s, k in jobs):
            for s, k in jobs:
                verify_completion(shard_dir(out, s, k), a.stage, s, k, a.workers, sds[s])
            save(out / f"completion_{'_'.join(systems)}.json", {"stage": a.stage, "workers": a.workers, "systems": systems, "scientific_digests": sds,
                                                               "files": {f"{TAGS[s]}/shard{k}/completion.json": sha(shard_dir(out, s, k) / "completion.json")
                                                                         for s, k in jobs}})
            return 0
        return 0 if a.limit else 2


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["worker", "launch", "lock_weights"])
    p.add_argument("--stage", choices=["D4", "E32"])
    p.add_argument("--system", choices=["CURE"])
    p.add_argument("--systems", default="CURE")
    p.add_argument("--out")
    p.add_argument("--gpu")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--nshards", type=int, default=1)
    p.add_argument("--workers", type=int, default=1, help="system당 worker 수")
    p.add_argument("--limit", type=int, default=0, help="통제된 중단 시험용: 이번 실행 저장 최대 요청 수")
    p.add_argument("--stagger", type=float, default=15.0)
    a = p.parse_args()
    if a.command == "lock_weights":
        print(json.dumps({k: (v if k != "weights" else None) for k, v in make_weights_lock().items() if k in ("model15_revision",)}))
        raise SystemExit(0)
    raise SystemExit(worker(a) if a.command == "worker" else launch(a))
