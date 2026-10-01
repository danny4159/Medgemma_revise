"""iter_045 MedGrounder worker (venv 실행). 한 프로세스 = 모델 1개 = GPU 1장(CUDA_VISIBLE_DEVICES로 지정됨).

python mg45_vrun.py mg45_worker.py --set D24 --ckpt P --out-dir DIR --worker K --n-workers N --batch B
        [--post-thr 0.4]  (지정하면 해당 threshold만 inline 후처리: timing 용 / 미지정이면 THRESHOLDS 전부 후처리해 저장)
        [--warmup-d8] [--barrier DIR]  (barrier: ready.K 작성 후 go 파일 대기. timing block 용)

작업 할당: 환자를 PatientID 순으로 정렬해 i % n_workers == worker 인 환자를 담당(정적 분할, 겹침/누락 없음).
출력: DIR/raw_worker{K}.jsonl (환자×문장 1행; 완결 행만 인정, 재개 시 이미 있는 행은 건너뜀), DIR/worker{K}.meta.json.
GT는 읽지 않는다 (manifest의 sentences/image/hash만 사용).
"""
import argparse
import json
import os
import sys
import time

import mg45_mg as M

MAN = "results/iter_043/data/manifest_private.json"


def sha_s(s):
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def load_set(name):
    man = json.load(open(MAN))
    ents = sorted(man[name], key=lambda e: e["PatientID"])
    return man, ents


def rid(setname, ckpt, patient, t):
    return sha_s(f"{setname}|{ckpt}|{patient}|{t}")[:32]


def read_done(path):
    out = {}
    if os.path.exists(path):
        data = open(path, "rb").read()
        for ln in data.split(b"\n")[:-1]:
            if ln.strip():
                r = json.loads(ln)
                out[r["request_id"]] = r
    return out


def repair_tail(path):
    if not os.path.exists(path):
        return 0
    data = open(path, "rb").read()
    if data and not data.endswith(b"\n"):
        tail = data.rsplit(b"\n", 1)[-1]
        keep = f"{path}.partial.{int(time.time())}.{os.getpid()}.bin"
        with open(keep, "xb") as f:
            f.write(tail)
        with open(path, "r+b") as f:
            f.truncate(len(data) - len(tail))
        return len(tail)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=["D8", "D24", "V96"])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ckpt-path", default=None, help="iter_046: P/MS 이외 key의 명시적 checkpoint 경로")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--worker", type=int, default=0)
    ap.add_argument("--n-workers", type=int, default=1)
    ap.add_argument("--batch", type=int, default=1, help="forward 1회당 (영상,문장) 항목 수")
    ap.add_argument("--post-thr", type=float, default=None)
    ap.add_argument("--warmup-d8", action="store_true")
    ap.add_argument("--barrier", default=None)
    ap.add_argument("--max-items", type=int, default=None, help="재개 시험용: 새 항목 N개 후 정상 종료")
    ap.add_argument("--stop-after-items", type=int, default=None, help="재개 시험용: N개 기록 직후 SIGKILL 유사 중단(os._exit)")
    a = ap.parse_args()
    import torch
    t_proc = time.time()
    dev = torch.device("cuda:0")
    man, ents = load_set("D24" if a.set == "D8" else a.set)
    if a.set == "D8":
        keep = set(man["D8"])
        ents = [e for e in ents if e["PatientID"] in keep]
    mine = [e for i, e in enumerate(ents) if i % a.n_workers == a.worker]
    os.makedirs(a.out_dir, exist_ok=True)
    out = os.path.join(a.out_dir, f"raw_worker{a.worker}.jsonl")
    repair_tail(out)
    done = read_done(out)
    model, cfg, load = M.load_model(a.ckpt, dev, a.ckpt_path)
    if load["missing"] or load["unexpected"]:
        sys.exit(f"state dict mismatch {load}")
    tf = M.val_transform()
    t_ready_model = time.time()
    ckpt_sha = M.file_sha(M.resolve_ckpt(a.ckpt, a.ckpt_path))
    gpu_uuid = None
    try:
        gpu_uuid = str(torch.cuda.get_device_properties(0).uuid)
    except Exception:
        pass
    thrs = [a.post_thr] if a.post_thr is not None else M.THRESHOLDS

    def run_group(group, record):
        """group: list of (entry, target). returns list of records."""
        t0 = time.time()
        imgs, affs, shas, cache = [], [], [], {}
        for e, t in group:
            if e["PatientID"] not in cache:
                ten, aff, u8 = M.prepare(e["image"], tf)
                if u8 != e["u8_pixel_sha256"]:
                    raise RuntimeError(f"decoded pixel hash != manifest {e['PatientID']}")
                cache[e["PatientID"]] = (ten, aff, u8)
            ten, aff, u8 = cache[e["PatientID"]]
            imgs.append(ten)
            affs.append(aff)
            shas.append(u8)
        t1 = time.time()
        lg, bx = M.forward(model, imgs, [e["sentences"][t] for e, t in group], dev)
        t2 = time.time()
        dets = {thr: M.postprocess(lg, bx, thr) for thr in thrs}
        t3 = time.time()
        recs = []
        if record:
            for i, (e, t) in enumerate(group):
                det = {}
                for thr in thrs:
                    d = dets[thr][i]
                    det[f"{thr}"] = {"boxes_orig_xyxy": M.canvas_cxcywh_to_orig_xyxy(d["boxes"], affs[i]), "scores": d["scores"],
                                     "pre_wbf_n": d["pre_wbf_n"]}
                recs.append({"request_id": rid(a.set, a.ckpt, e["PatientID"], t), "set": a.set, "ckpt": a.ckpt, "patient": e["PatientID"],
                             "target": t, "sentence_sha256": sha_s(e["sentences"][t]), "image": e["image"],
                             "u8_pixel_sha256": shas[i], "aff": affs[i], "logits": lg[i].tolist(), "pred_boxes_cxcywh": bx[i].tolist(),
                             "detections": det, "batch": a.batch, "group_n": len(group), "worker": a.worker, "n_workers": a.n_workers,
                             "t_dispatch": t0, "t_loaded": t1, "t_forward_done": t2, "t_done": t3,
                             "load_s": t1 - t0, "forward_s": t2 - t1, "post_s": t3 - t2,
                             "ckpt_sha256": ckpt_sha, "post_thr_mode": a.post_thr, "gpu_uuid": gpu_uuid,
                             "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
                             "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30})
        t4 = time.time()  # iter_046: 원본 정규화 좌표 변환·record 구성 완료 시각 (timing 종료 경계)
        for r in recs:
            r["t_orig_done"] = t4
        return recs

    if a.warmup_d8:
        man8 = set(man["D8"])
        d24 = {e["PatientID"]: e for e in man["D24"]}
        wu = [(d24[p], t) for p in sorted(man8) for t in ("qA", "qB")]
        for s in range(0, len(wu), a.batch):
            run_group(wu[s:s + a.batch], record=False)
        torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t_warm = time.time()
    if a.barrier:
        open(os.path.join(a.barrier, f"ready.{a.worker}"), "w").write(json.dumps({"t": time.time(), "pid": os.getpid()}))
        gof = os.path.join(a.barrier, "go")
        while not os.path.exists(gof):
            time.sleep(0.005)
        t_go = json.load(open(gof))["t"]
    else:
        t_go = None
    # 작업 목록: 환자 순서 유지, 환자의 두 문장을 연속 배치
    items = [(e, t) for e in mine for t in ("qA", "qB") if rid(a.set, a.ckpt, e["PatientID"], t) not in done]
    n_new = 0
    t_first = None
    with open(out, "a") as f:
        for s in range(0, len(items), a.batch):
            if a.max_items is not None and n_new >= a.max_items:
                break
            group = items[s:s + a.batch]
            recs = run_group(group, record=True)
            if t_first is None:
                t_first = recs[0]["t_dispatch"]
            for r in recs:
                f.write(json.dumps(r) + "\n")
                f.flush()
                os.fsync(f.fileno())
                n_new += 1
                if a.stop_after_items is not None and n_new >= a.stop_after_items:
                    os._exit(137)
    t_end = time.time()
    if a.barrier:
        open(os.path.join(a.barrier, f"done.{a.worker}"), "w").write(json.dumps({"t": t_end, "n_new": n_new}))
    json.dump({"worker": a.worker, "n_workers": a.n_workers, "set": a.set, "ckpt": a.ckpt, "batch": a.batch, "post_thr": a.post_thr,
               "n_assigned": len(mine) * 2, "n_new": n_new, "t_proc_start": t_proc, "t_model_ready": t_ready_model, "t_warm_done": t_warm,
               "t_go": t_go, "t_first_dispatch": t_first, "t_end": t_end, "load_s": t_ready_model - t_proc,
               "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30, "peak_reserved_gb": torch.cuda.max_memory_reserved() / 2**30,
               "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "gpu_uuid": gpu_uuid, "ckpt_sha256": ckpt_sha},
              open(os.path.join(a.out_dir, f"worker{a.worker}.meta.{int(t_proc)}.json"), "x"), indent=1)
    print(f"worker {a.worker}: done, {n_new} new items", flush=True)


if __name__ == "__main__":
    main()
