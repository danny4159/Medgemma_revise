"""detector 추론·완료 검증·threshold scan (natten_py310 env).

원본: results/iter_034/eval_on_manifest.py (sha256 c9b346b1...), results/iter_034/eval_confirm800.py (sha256 df0b9375...),
그 원본인 iter_033 eval_on_manifest.py/eval_confirm800.py. THRESHOLDS·preds_to_norm_yxyx·summarize 계산은 유지한다.
iter_035 변경:
- 추론을 record 단위 JSONL(worker shard)로 저장하고 재개한다. 각 record에 checkpoint sha256·source digest·
  manifest digest·영상 file sha256을 남기고, 재개 시 기존 record의 provenance가 다르면 거부한다.
- 마지막 줄 손상(tail)은 원본 bytes를 별도 파일로 보존한 뒤 잘라내고 재계산한다. 중간 줄 손상·중복은 오류.
- run: worker 프로세스를 띄우고(PDEATHSIG) SIGTERM을 전달하며, 모두 성공하면 finalize로 정확한 ID 집합·중복·
  provenance를 검증해 raw_preds.json과 completion.json을 원자적으로 쓴다. 누락 record는 점수화하지 않는다.
- scan: completion을 재검증한 raw_preds에서만 threshold별 요약을 만든다. FP/환자는 전체 N 기준(detector는
  모든 요청이 valid)이며, IoU 0.3·0.5의 lesion recall을 함께 기록한다.
"""
import argparse
import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)

THRESHOLDS = [0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
              0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.975, 0.99, 1.0]
SOURCE_FILES = [f"{BASE}/rsna_diag/det_eval.py", f"{BASE}/rsna_diag/det_lib.py", f"{BASE}/rsna_diag/geometry.py"]
_STOP = {"flag": False}


def _h(s, f):
    _STOP["flag"] = True


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def jd(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()


def source_digest():
    ent = {os.path.relpath(p, BASE): sha_file(p) for p in SOURCE_FILES}
    if os.environ.get("DET_TEST_SOURCE_SALT"):
        ent["_salt"] = os.environ["DET_TEST_SOURCE_SALT"]
    return jd(ent)


def manifest_ids(name):
    from rsna_diag import det_train as T
    if name == "confirm800":
        p = f"{BASE}/results/iter_010/manifests/confirm_ids.json"
        return json.load(open(p)), p
    p = T.find_manifest(name)
    return json.load(open(p))["ids"], p


def provenance(args, ids):
    return {"checkpoint": os.path.abspath(args.checkpoint), "checkpoint_sha256": sha_file(args.checkpoint),
            "source_digest": source_digest(), "manifest": args.manifest, "manifest_digest": jd(ids),
            "batch_size": args.batch_size}


def read_shard(path, prov, repair):
    """반환: {id: record}. 마지막 줄 손상은 repair=True일 때 보존·절단, 그 외 손상은 예외."""
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        data = f.read()
    cut = data.rfind(b"\n") + 1  # 개행으로 끝난 완전한 줄까지
    complete, tail_frag = data[:cut], data[cut:]
    if tail_frag:
        if not repair:
            raise ValueError(f"corrupt (unterminated) tail in {path}")
        keep = f"{path}.corrupt_tail.{int(time.time() * 1000)}"
        with open(keep, "wb") as f:
            f.write(tail_frag)
        with open(path, "r+b") as f:
            f.truncate(cut)
    recs = {}
    for k, ln in enumerate(complete.split(b"\n")[:-1] if complete else []):
        try:
            r = json.loads(ln)
        except Exception:
            raise ValueError(f"corrupt internal line {k} in {path}")
        for key in ("checkpoint_sha256", "source_digest", "manifest_digest", "batch_size"):
            if r.get(key) != prov[key]:
                raise ValueError(f"provenance mismatch ({key}) in existing record {r.get('id')} of {path}")
        if r["id"] in recs:
            raise ValueError(f"duplicate id {r['id']} in {path}")
        recs[r["id"]] = r
    return recs


def cmd_worker(args):
    import torch
    from rsna_diag import det_lib as D
    libc = ctypes.CDLL("libc.so.6")
    libc.prctl(1, signal.SIGTERM)  # 부모가 죽으면 SIGTERM
    signal.signal(signal.SIGTERM, _h)
    ids, _ = manifest_ids(args.manifest)
    mine = [i for k, i in enumerate(ids) if k % args.n_workers == args.worker]
    prov = provenance(args, ids)
    out = os.path.join(args.out_dir, f"preds_w{args.worker:02d}.jsonl")
    done = read_shard(out, prov, repair=True)
    todo = [i for i in mine if i not in done]
    extra = set(done) - set(mine)
    if extra:
        raise ValueError(f"shard has ids outside its assignment: {sorted(extra)[:3]}")
    gt, infer = D.load_gt_infer()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    t_load = time.time()
    model = D.build_model().to(device)
    ck = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(ck["model"])
    model.eval()
    del ck
    t_load = time.time() - t_load
    t0 = time.time()
    n = 0
    with open(out, "a") as f:
        for s in range(0, len(todo), args.batch_size):
            if _STOP["flag"]:
                break
            bid = todo[s:s + args.batch_size]
            raw = D.run_inference(model, device, bid, gt, infer, batch_size=args.batch_size)
            for i in bid:
                r = {"id": i, **raw[i], "file_sha256": infer[i].get("file_sha256"), **{k: prov[k] for k in (
                    "checkpoint_sha256", "source_digest", "manifest_digest", "batch_size")}}
                f.write(json.dumps(r) + "\n")
                f.flush()
                n += 1
    el = time.time() - t0
    meta = {"worker": args.worker, "n_new": n, "n_prev": len(done), "elapsed_s": el, "model_load_s": t_load,
            "images_per_sec": n / el if el > 0 and n else None, "stopped": _STOP["flag"],
            "peak_alloc_mib": torch.cuda.max_memory_allocated() / 2**20 if torch.cuda.is_available() else None,
            "peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20 if torch.cuda.is_available() else None}
    with open(os.path.join(args.out_dir, f"worker{args.worker:02d}_meta_{int(time.time())}.json"), "w") as f:
        json.dump(meta, f)
    print(json.dumps(meta), flush=True)
    return 3 if _STOP["flag"] else 0


def finalize(args):
    ids, mpath = manifest_ids(args.manifest)
    prov = provenance(args, ids)
    allrec = {}
    files = {}
    for w in range(args.n_workers):
        p = os.path.join(args.out_dir, f"preds_w{w:02d}.jsonl")
        recs = read_shard(p, prov, repair=False)
        for i in recs:
            if i in allrec:
                raise ValueError(f"id {i} in multiple shards")
        allrec.update(recs)
        files[os.path.basename(p)] = sha_file(p)
    if set(allrec) != set(ids) or len(allrec) != len(ids):
        miss = sorted(set(ids) - set(allrec))
        raise ValueError(f"incomplete: missing {len(miss)} e.g. {miss[:3]}, extra {len(set(allrec) - set(ids))}")
    raw = {i: {k: allrec[i][k] for k in ("boxes_xyxy_px", "scores", "labels", "img_hw")} for i in ids}
    tmp = os.path.join(args.out_dir, "raw_preds.json.tmp")
    with open(tmp, "w") as f:
        json.dump(raw, f)
    os.replace(tmp, os.path.join(args.out_dir, "raw_preds.json"))
    comp = {**prov, "manifest_path": mpath, "n_ids": len(ids), "n_workers": args.n_workers, "shard_sha256": files,
            "raw_preds_sha256": sha_file(os.path.join(args.out_dir, "raw_preds.json")), "t": time.time()}
    tmp = os.path.join(args.out_dir, "completion.json.tmp")
    with open(tmp, "w") as f:
        json.dump(comp, f, indent=2)
    os.replace(tmp, os.path.join(args.out_dir, "completion.json"))
    return comp


def load_verified(out_dir, expect_manifest=None, expect_ckpt=None):
    """completion.json과 raw_preds·shard·checkpoint·manifest를 대조한 뒤 raw_preds를 반환한다."""
    comp = json.load(open(os.path.join(out_dir, "completion.json")))
    rp = os.path.join(out_dir, "raw_preds.json")
    if sha_file(rp) != comp["raw_preds_sha256"]:
        raise ValueError("raw_preds sha256 mismatch with completion")
    for fn, h in comp["shard_sha256"].items():
        if sha_file(os.path.join(out_dir, fn)) != h:
            raise ValueError(f"shard {fn} changed after completion")
    if sha_file(comp["checkpoint"]) != comp["checkpoint_sha256"]:
        raise ValueError("checkpoint changed after completion")
    ids, _ = manifest_ids(comp["manifest"])
    if jd(ids) != comp["manifest_digest"]:
        raise ValueError("manifest changed after completion")
    if expect_manifest and comp["manifest"] != expect_manifest:
        raise ValueError("unexpected manifest")
    if expect_ckpt and os.path.abspath(expect_ckpt) != comp["checkpoint"]:
        raise ValueError("unexpected checkpoint")
    raw = json.load(open(rp))
    if list(raw.keys()) != ids:
        raise ValueError("raw_preds id order/set differs from manifest")
    return raw, comp, ids


def cmd_run(args):
    signal.signal(signal.SIGTERM, _h)
    os.makedirs(args.out_dir, exist_ok=True)
    ids, _ = manifest_ids(args.manifest)
    if os.path.exists(os.path.join(args.out_dir, "completion.json")):
        load_verified(args.out_dir, args.manifest, args.checkpoint)
        print(json.dumps({"already_complete": True}))
        return 0
    gpus = os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")
    wg = [int(x) for x in args.worker_gpus.split(",")]  # 논리 index(상속 집합 기준)
    if len(wg) != args.n_workers or any(g < 0 or g >= len(gpus) for g in wg):
        raise ValueError(f"worker_gpus {wg} invalid for inherited {gpus}")
    procs = []
    t0 = time.time()
    for w in range(args.n_workers):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpus[wg[w]], PYTHONUNBUFFERED="1")
        logf = open(os.path.join(args.out_dir, f"worker{w:02d}.log"), "a")
        cmd = [sys.executable, os.path.abspath(__file__), "worker", "--manifest", args.manifest, "--checkpoint",
               args.checkpoint, "--out_dir", args.out_dir, "--batch_size", str(args.batch_size),
               "--worker", str(w), "--n_workers", str(args.n_workers)]
        procs.append((subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT), logf))
    signalled = set()
    while any(p.poll() is None for p, _ in procs):
        if _STOP["flag"]:
            for k, (p, _) in enumerate(procs):
                if p.poll() is None and k not in signalled:  # worker당 한 번만 전달(안전 종료 경계 보존)
                    p.send_signal(signal.SIGTERM)
                    signalled.add(k)
        time.sleep(0.5)
    rcs = [p.wait() for p, _ in procs]
    for _, lf in procs:
        lf.close()
    wall = time.time() - t0
    with open(os.path.join(args.out_dir, f"run_{int(time.time())}.json"), "w") as f:
        json.dump({"worker_rcs": rcs, "wall_s": wall, "n_workers": args.n_workers, "worker_gpus": wg,
                   "physical": [gpus[g] for g in wg], "batch_size": args.batch_size, "stopped": _STOP["flag"]}, f)
    if _STOP["flag"] or any(rc != 0 for rc in rcs):
        print(json.dumps({"incomplete": True, "worker_rcs": rcs}))
        return 3 if _STOP["flag"] and all(rc in (0, 3) for rc in rcs) else 1
    comp = finalize(args)
    print(json.dumps({"complete": True, "n": comp["n_ids"], "wall_s": wall, "images_per_sec": len(ids) / wall}))
    return 0


def cmd_check(args):
    load_verified(args.out_dir)
    print(json.dumps({"verified": True}))
    return 0


def scan_table(raw, gt, ids, edges):
    from rsna_diag import det_lib as D, sft_eval as SE, metrics as M
    table, fp_table, lr_table = {}, {}, {}
    for thr in THRESHOLDS:
        preds = D.preds_to_norm_yxyx(raw, gt, threshold=thr)
        summ = SE.summarize(preds, gt, ids, edges=edges)
        table[str(thr)] = summ
        fps, tp3, tp5, n_gt = [], 0, 0, 0
        for i in ids:
            pb = preds[i]["boxes"]
            g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            t3 = M.patient_metrics(pb, g, 0.3)["tp"] if pb and g else 0
            t5 = M.patient_metrics(pb, g, 0.5)["tp"] if pb and g else 0
            fps.append(len(pb) - t3)
            tp3 += t3; tp5 += t5; n_gt += len(g)
        fp_table[str(thr)] = {"fp_per_patient_all_n": sum(fps) / len(ids), "n": len(ids),
                              "frac_patients_with_fp": sum(1 for x in fps if x > 0) / len(ids)}
        lr_table[str(thr)] = {"lesion_recall@0.3": tp3 / n_gt if n_gt else None,
                              "lesion_recall@0.5": tp5 / n_gt if n_gt else None, "tp@0.3": tp3, "n_gt": n_gt}
    return table, fp_table, lr_table


def cmd_scan(args):
    from rsna_diag import det_lib as D
    raw, comp, ids = load_verified(args.out_dir, args.manifest)
    gt, _ = D.load_gt_infer()
    edges = json.load(open(f"{BASE}/results/iter_033/data/area_edges.json"))["train_positive_area_tertile_edges"]
    table, fp_table, lr_table = scan_table(raw, gt, ids, edges)
    # 모든 threshold의 필수 수치가 유한해야 한다
    for t in table:
        for key in ("utility", "f1@0.3", "f1@0.5"):
            v = table[t][key]
            if v is None or v != v:
                raise ValueError(f"missing/nonfinite {key} at threshold {t}")
    max_n = max((len(r["scores"]) for r in raw.values()), default=0)
    out = {"completion": comp, "manifest": args.manifest, "n_ids": len(ids), "thresholds": table,
           "fp_per_patient": fp_table, "lesion_recall": lr_table, "max_candidates_per_image": max_n,
           "n_images_at_cap100": sum(1 for r in raw.values() if len(r["scores"]) >= 100),
           "min_score_at_cap": min((min(r["scores"]) for r in raw.values() if len(r["scores"]) >= 100), default=None)}
    with open(os.path.join(args.out_dir, "threshold_scan.json"), "w") as f:
        json.dump(out, f, indent=2)
    best = max(THRESHOLDS, key=lambda t: (table[str(t)]["utility"], table[str(t)]["f1@0.5"], -fp_table[str(t)]["fp_per_patient_all_n"], t))
    print(json.dumps({"n_ids": len(ids), "best_threshold_by_utility": best, "utility": table[str(best)]["utility"],
                      "f1@0.3": table[str(best)]["f1@0.3"], "f1@0.5": table[str(best)]["f1@0.5"],
                      "fp_per_patient": fp_table[str(best)]["fp_per_patient_all_n"],
                      "n_images_at_cap100": out["n_images_at_cap100"]}, indent=1))
    return 0


def cmd_latency(args):
    """단독 resident batch1 latency: 모델 로드 시간, warmup 8, manifest 전체를 순서대로 1건씩.
    end-to-end = 영상 읽기·전처리·GPU 전송·forward·CPU 반환(synchronize 포함), model = forward 구간."""
    import numpy as np
    import torch
    from rsna_diag import det_lib as D
    ids, _ = manifest_ids(args.manifest)
    gt, infer = D.load_gt_infer()
    dev = torch.device("cuda:0")
    torch.cuda.synchronize()
    t = time.time()
    model = D.build_model().to(dev)
    model.load_state_dict(torch.load(args.checkpoint, map_location="cpu", weights_only=False)["model"])
    model.eval()
    torch.cuda.synchronize()
    load_s = time.time() - t
    ds = D.RSNADetDataset(ids, gt, infer, train_aug=False)
    rows = []
    torch.cuda.reset_peak_memory_stats()
    with torch.no_grad():
        for k, i in enumerate(ids[:8] + ids):
            torch.cuda.synchronize()
            t0 = time.time()
            img, _, hw = ds[ds.ids.index(i)]
            x = img.to(dev)
            torch.cuda.synchronize()
            t1 = time.time()
            pr = model([x])[0]
            torch.cuda.synchronize()
            t2 = time.time()
            _ = pr["boxes"].cpu().numpy(), pr["scores"].cpu().numpy()
            t3 = time.time()
            if k >= 8:
                rows.append({"id": i, "end_to_end_s": t3 - t0, "model_s": t2 - t1})
    e2e = [r["end_to_end_s"] for r in rows]; mo = [r["model_s"] for r in rows]
    out = {"model": "detector", "checkpoint": args.checkpoint, "checkpoint_sha256": sha_file(args.checkpoint),
           "load_s": load_s, "n": len(rows), "warmup": 8, "precision": "fp32",
           "end_to_end": {"mean": float(np.mean(e2e)), "p50": float(np.percentile(e2e, 50)), "p95": float(np.percentile(e2e, 95))},
           "model_only": {"mean": float(np.mean(mo)), "p50": float(np.percentile(mo, 50)), "p95": float(np.percentile(mo, 95))},
           "peak_alloc_mib": torch.cuda.max_memory_allocated() / 2**20, "peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20,
           "gpu": torch.cuda.get_device_name(0), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "rows": rows}
    json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("latency")
    p.add_argument("--manifest", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_latency)
    for name, fn in (("run", cmd_run), ("worker", cmd_worker)):
        p = sub.add_parser(name)
        p.add_argument("--manifest", required=True)
        p.add_argument("--checkpoint", required=True)
        p.add_argument("--out_dir", required=True)
        p.add_argument("--batch_size", type=int, default=4)
        p.add_argument("--n_workers", type=int, default=1)
        if name == "run":
            p.add_argument("--worker_gpus", default="0")
        else:
            p.add_argument("--worker", type=int, required=True)
        p.set_defaults(func=fn)
    p = sub.add_parser("check")
    p.add_argument("--out_dir", required=True)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("scan")
    p.add_argument("--out_dir", required=True)
    p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_scan)
    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()
