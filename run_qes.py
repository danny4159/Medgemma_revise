"""iter_004 GPU runner: calibration / full scoring / verification (1 GPU, 1 process).

실행:
  python research/run_qes.py --out research/results/iter_004 --phase calib
  python research/run_qes.py --out research/results/iter_004 --phase full
  python research/run_qes.py --out research/results/iter_004 --phase verify
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qes.data import DATA_DIR, SCORER_VERSION, ImageInputs, file_sha256, pixel_hash  # noqa: E402
from qes.preflight import PreflightError, check_manifest  # noqa: E402
from qes.store import (Ledger, append_jsonl, plan_queue, read_jsonl, validate_predictions,  # noqa: E402
                       write_json_atomic)

DEFAULT_REQ_MIN = 0.5  # 관측 전 1요청 추정 (보수적)
VERIFY_FORWARDS_PER_GEN = 8


def load_manifest(out, data_dir=DATA_DIR):
    """공통 preflight: 완료된 요청을 포함한 manifest 전체를 현재 실제 입력에서 재계산해 대조한다."""
    try:
        return check_manifest(out, data_dir=data_dir)
    except PreflightError as e:
        raise SystemExit(f"preflight failed -> not resuming: {e}")


class InputCache:
    """실제 파일에서 입력을 다시 만들고 manifest hash와 대조한다."""

    def __init__(self, info, data_dir=DATA_DIR):
        self.info = info
        self.data_dir = data_dir
        self.cur_name, self.cur = None, None

    def get(self, r):
        if r["image"] != self.cur_name:
            path = os.path.join(self.data_dir, r["image"])
            inf = self.info[r["image"]]
            if file_sha256(path) != inf["source_file_sha256"]:
                raise RuntimeError(f"source file hash changed: {path}")
            ii = ImageInputs(path)
            if pixel_hash(ii.orig) != inf["source_pixel_sha256"]:
                raise RuntimeError(f"source pixel hash changed: {path}")
            self.cur_name, self.cur = r["image"], ii
        img = self.cur.make(r["kind"], r["tile"])
        h = pixel_hash(img)
        if h != r["input_pixel_sha256"]:
            raise RuntimeError(f"input pixel hash mismatch: {r['id']}")
        return img, h


def pick_gpu():
    if os.environ.get("CUDA_VISIBLE_DEVICES"):
        return os.environ["CUDA_VISIBLE_DEVICES"], "preset"
    q = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, check=True).stdout
    free = {int(a): int(b) for a, b in (ln.split(",") for ln in q.strip().splitlines())}
    best = max(free, key=lambda k: (free[k], -k))
    if free[best] < 12000:
        raise SystemExit(f"not enough free GPU memory: {free}")
    os.environ["CUDA_VISIBLE_DEVICES"] = str(best)
    return str(best), f"auto(free MiB={free})"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--phase", choices=["calib", "full", "verify"], required=True)
    ap.add_argument("--cap", type=float, default=45.0, help="누적 device-minute 상한")
    ap.add_argument("--target", type=float, default=40.0, help="calibration 예상 총량 허용치")
    ap.add_argument("--data-dir", default=DATA_DIR)
    args = ap.parse_args(argv)

    cfg, chash, reqs, info, subsets = load_manifest(args.out, data_dir=args.data_dir)
    pred_path = os.path.join(args.out, "predictions.jsonl")
    ledger = Ledger(os.path.join(args.out, "budget.json"))
    used0 = ledger.total_minutes()
    print(f"[budget] used so far {used0:.3f} device-min (cap {args.cap})", flush=True)
    if used0 >= args.cap:
        raise SystemExit("budget cap reached; not starting")

    v = validate_predictions(reqs, read_jsonl(pred_path), chash, SCORER_VERSION)
    print(f"[cache] valid={len(v['valid'])} rejected={len(v['rejected'])} conflicts={len(v['conflicts'])} "
          f"missing={len(v['missing'])}", flush=True)
    if v["conflicts"]:
        raise SystemExit(f"conflicting duplicate results: {v['conflicts'][:3]}")

    if args.phase == "calib":
        queue = plan_queue(reqs, set(v["valid"]), allowed_ids=subsets["calibration"])
    elif args.phase == "full":
        cal = json.load(open(os.path.join(args.out, "calibration.json")))
        if cal["projected_total_device_min"] > args.target:
            raise SystemExit(f"calibration projection {cal['projected_total_device_min']:.1f} > {args.target}")
        queue = plan_queue(reqs, set(v["valid"]))
    else:
        missing_ver = [i for i in subsets["verification"] if i not in v["valid"]]
        if missing_ver:
            raise SystemExit(f"verification inputs lack main results: {missing_ver}")
        queue = [r for r in reqs if r["id"] in set(subsets["verification"])]
    print(f"[queue] phase={args.phase} n={len(queue)}", flush=True)
    if not queue:
        print("[queue] nothing to do", flush=True)
        return

    gpu, how = pick_gpu()
    ledger.start(f"{args.phase} gpu={gpu}")
    how_closed = "exception"
    times, n_err = [], 0
    stopped_reason = None
    try:
        t_load = time.time()
        from qes.scorer import Scorer
        sc = Scorer()
        env = sc.load()
        env["gpu_select"] = how
        env["load_seconds"] = time.time() - t_load
        write_json_atomic(os.path.join(args.out, f"env_{args.phase}_{int(time.time())}.json"), env)
        ledger.checkpoint(load_seconds=env["load_seconds"])
        print(f"[load] {env['load_seconds']:.1f}s  gpu={gpu}", flush=True)
        inputs = InputCache(info, data_dir=args.data_dir)
        import torch

        if args.phase in ("calib", "full"):
            for i, r in enumerate(queue):
                est = max(times) / 60.0 if times else DEFAULT_REQ_MIN
                if ledger.total_minutes() + est > args.cap:
                    stopped_reason = f"budget: next request est {est:.3f} min exceeds remaining"
                    break
                ledger.mark_inflight(r["id"])
                t0 = time.time()
                try:
                    img, h = inputs.get(r)
                    out = sc.score(img, r["prompt"])
                    rec = {"id": r["id"], "status": "ok", **out}
                except torch.cuda.OutOfMemoryError as e:
                    rec = {"id": r["id"], "status": "oom", "error": str(e)[:300]}
                    stopped_reason = "oom"
                except Exception as e:  # 형식·hash 오류 등은 error로 기록
                    rec = {"id": r["id"], "status": "error", "error": repr(e)[:300]}
                    n_err += 1
                dt = time.time() - t0
                rec.update({"request_sha256": r["request_sha256"], "config_sha256": chash,
                            "input_pixel_sha256": r["input_pixel_sha256"], "scorer_version": SCORER_VERSION,
                            "phase": args.phase, "seconds": dt, "ts": time.time()})
                append_jsonl(pred_path, rec)
                if rec["status"] == "ok":
                    times.append(dt)
                ledger.cur["inflight"] = None
                ledger.checkpoint(n_done_delta=1)
                if (i + 1) % 100 == 0 or i < 3:
                    print(f"[score] {i + 1}/{len(queue)} {r['id']} m={rec.get('m')} {dt:.2f}s "
                          f"used={ledger.total_minutes():.2f}", flush=True)
                if stopped_reason == "oom" or n_err > 5:
                    stopped_reason = stopped_reason or "too many errors"
                    break
        else:
            valid = v["valid"]
            ver_path = os.path.join(args.out, "verification.jsonl")
            session = int(time.time())
            for r in queue:
                if ledger.total_minutes() + 1.0 > args.cap:
                    stopped_reason = "budget"
                    break
                ledger.mark_inflight("verify:" + r["id"])
                img, h = inputs.get(r)
                t0 = time.time()
                rep = sc.score(img, r["prompt"])
                t1 = time.time()
                tf = sc.teacher_forced(img, r["prompt"])
                t2 = time.time()
                gen = sc.generate(img, r["prompt"], max_new_tokens=8)
                t3 = time.time()
                main_m = valid[r["id"]]["m"]
                rec = {"id": r["id"], "session": session, "m_main": main_m, "m_repeat": rep["m"],
                       "repeat_abs_diff": abs(rep["m"] - main_m), **tf, "tf_abs_diff": abs(tf["m_tf"] - main_m),
                       **gen, "score_decision": "Yes" if main_m > 0 else "No",
                       "gen_agrees": gen["gen_parsed"] == ("Yes" if main_m > 0 else "No"),
                       "sec_repeat": t1 - t0, "sec_tf": t2 - t1, "sec_gen": t3 - t2,
                       "request_sha256": r["request_sha256"], "config_sha256": chash}
                append_jsonl(ver_path, rec)
                ledger.cur["inflight"] = None
                ledger.checkpoint(n_done_delta=1)
                print(f"[verify] {r['id']} main={main_m:.4f} rep={rep['m']:.4f} tf={tf['m_tf']:.4f} "
                      f"gen={gen['gen_text']!r}", flush=True)
        how_closed = "normal" if stopped_reason is None else f"stopped:{stopped_reason}"
    except KeyboardInterrupt:
        how_closed = "interrupted"
        raise
    finally:
        ledger.close(how_closed)
        print(f"[budget] session closed ({how_closed}); total {ledger.total_minutes():.3f} device-min", flush=True)

    if args.phase == "calib":
        v2 = validate_predictions(reqs, read_jsonl(pred_path), chash, SCORER_VERSION)
        per_req_min = statistics.median(times) / 60.0 if times else DEFAULT_REQ_MIN
        load_min = env["load_seconds"] / 60.0
        remaining = len(v2["missing"])
        verify_min = 12 * per_req_min * (1 + 2 + VERIFY_FORWARDS_PER_GEN)
        projected = ledger.total_minutes() + 2 * load_min + remaining * per_req_min * 1.2 + verify_min
        cal = {"n_calibration_done": len(times), "median_sec_per_request": per_req_min * 60,
               "max_sec_per_request": max(times) if times else None, "load_min": load_min,
               "used_device_min": ledger.total_minutes(), "remaining_requests": remaining,
               "verify_est_min": verify_min, "projected_total_device_min": projected,
               "target": args.target, "proceed": projected <= args.target,
               "formula": "used + 2*load + remaining*median*1.2 + 12*median*(1+2+8)"}
        write_json_atomic(os.path.join(args.out, "calibration.json"), cal)
        print(json.dumps(cal, indent=1), flush=True)
    if stopped_reason:
        print(f"[status] incomplete: {stopped_reason}", flush=True)


if __name__ == "__main__":
    main()
