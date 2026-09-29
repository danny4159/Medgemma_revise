"""RSNA detector 학습 실행기 (natten_py310 env 전용).

이력:
- iter_033 results/iter_033/run_detector.py (sha256 994b061dee66d48436f08606dc551d4f47329f9719dc5d270e38800ec6ddf18c) 원본.
- iter_034 수정본 (sha256 6c1898c5bfe9750747142641e339b9b9189e5304f27ac6403d4cc9e67c11b49b, commit bc80f2d):
  augmentation RNG를 epoch 시작에만 시딩, ds_rng_state 저장, update별 sample/flip 로그, flock lock, SIGTERM 경계 저장.
- iter_035 수정 (이 파일):
  1. 재개 LR: 원본은 optimizer state를 로드한 뒤 LambdaLR을 생성해 생성자의 _initial_step()이 group lr을
     lambda(0)×base로 덮어썼다. scheduler.load_state_dict는 group lr을 되돌리지 않으므로 재개 첫 update가
     warmup 첫 LR(0.005/300)로 적용됐다. 이제 scheduler를 먼저 만들고 optimizer→scheduler 순으로 state를
     복원한 뒤, 모든 param group의 실제 lr이 저장값·lr_lambda(last_epoch)×initial_lr과 같은지 검사한다.
  2. 로그의 lr_applied는 opt.step() 직전 param group의 실제 lr이다(원본은 sched.step() 뒤 다음 LR). lr_next를 따로 기록한다.
  3. checkpoint(format 2): 실제 epoch permutation, cursor, update, dataset RNG, Python/NumPy/CPU/CUDA RNG,
     model/optimizer/scheduler, config·input·source digest, 적용 예정 lr, canonical 로그 수를 저장한다.
     재개 시 필수 상태 누락·digest 불일치·permutation 불일치를 거부한다(조용한 재시딩 없음).
  4. 비유한 loss/gradient는 optimizer.step 전에 nonfinite.json을 남기고 실패 종료한다(update를 소비하지 않음).
  5. 로그는 프로세스(segment)별 파일로 쓰고 segments.json에 시작 update를 기록한다. checkpoint 이후 기록은
     orphan으로 보존되며 canonical_log()가 중복·누락을 거부한다.
  6. 완료 marker(complete.json)와 verify 명령, 기존 경로 fresh 실행 거부, lock 소유 metadata(pid/starttime/attempt).
  7. --init_from: 다른 run의 checkpoint(동일 state)에서 새 run_dir로 이어간다(재개 검사·구버전 이관 공용).
     구버전(format 1) checkpoint는 --migration manifest가 원본 sha256·검증 근거를 연결할 때만 허용한다.
  8. 재개 검사 전용: --save_at(지정 update의 전체 snapshot), --stop_after, --trace(입력·parameter digest),
     --deterministic(torch 결정적 알고리즘).
"""
import argparse
import fcntl
import hashlib
import json
import os
import signal
import socket
import sys
import time

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
if "--deterministic" in sys.argv:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, BASE)
from rsna_diag import det_lib as D  # noqa: E402

FORMAT_VERSION = 2
DATA_DIRS = [f"{BASE}/results/iter_033/data", f"{BASE}/results/iter_034/data", f"{BASE}/results/iter_035/data"]
SOURCE_FILES = [f"{BASE}/rsna_diag/det_train.py", f"{BASE}/rsna_diag/det_lib.py", f"{BASE}/rsna_diag/geometry.py"]
# 학습 trajectory를 정의하는 설정. device·stop_after·save_at·trace·deterministic은 실행 제어로 digest에서 제외한다.
CONFIG_KEYS = ["manifest", "effective_batch", "microbatch", "lr", "momentum", "weight_decay", "lr_drop_epochs",
               "seed", "warmup_epochs", "trainable_backbone_layers", "flip_p", "min_size", "max_size"]
EXIT_STOPPED = 3  # SIGTERM/stop_after로 안전 저장 후 종료(재개 가능)


def find_manifest(name):
    for d in DATA_DIRS:
        p = f"{d}/{name}.json"
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def jdigest(obj):
    return sha256_bytes(json.dumps(obj, sort_keys=True).encode())


def source_digest():
    ent = {os.path.relpath(p, BASE): D.sha256_file(p) for p in SOURCE_FILES}
    salt = os.environ.get("DET_TEST_SOURCE_SALT")  # 변조 거부 검사 전용
    if salt:
        ent["_test_salt"] = salt
    return jdigest(ent), ent


def input_digest(ids, gt, infer):
    """manifest ID 순서, 영상 file sha256, GT box(xyxy_px)를 묶은 digest."""
    rows = []
    for i in ids:
        rows.append([i, infer[i]["image"], infer[i].get("file_sha256"), gt[i].get("pixel_sha256"),
                     gt[i]["category"], [b["xyxy_px"] for b in gt[i]["boxes"]]])
    salt = os.environ.get("DET_TEST_INPUT_SALT")  # 변조 거부 검사 전용
    if salt:
        rows.append(["_test_salt", salt])
    return jdigest(rows)


def config_of(args):
    return {k: getattr(args, k) for k in CONFIG_KEYS}


def proc_starttime(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return int(f.read().rsplit(")", 1)[1].split()[19])
    except Exception:
        return None


class FlockLock:
    """fcntl.flock 기반 exclusive lock(프로세스 종료 시 OS가 해제). 소유 metadata를 남긴다."""

    def __init__(self, run_dir, attempt_id):
        os.makedirs(run_dir, exist_ok=True)
        self.path = os.path.join(run_dir, "train.lock")
        self.fh = open(self.path, "a+")
        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.seek(0)
            owner = self.fh.read()
            self.fh.close()
            raise RuntimeError(f"run_dir {run_dir} is locked by another live process (flock held): {owner}")
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(json.dumps({"pid": os.getpid(), "starttime": proc_starttime(os.getpid()),
                                  "host": socket.gethostname(), "attempt_id": attempt_id, "t": time.time(),
                                  "argv": sys.argv}))
        self.fh.flush()

    def release(self):
        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


_STOP_REQUESTED = {"flag": False}


def _sigterm_handler(signum, frame):
    _STOP_REQUESTED["flag"] = True


def epoch_perm(seed, epoch_idx, n):
    rng = np.random.default_rng(seed * 100000 + epoch_idx)
    return rng.permutation(n).tolist()


# ---------------------------------------------------------------- log segments
def read_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def load_segments(run_dir):
    p = os.path.join(run_dir, "segments.json")
    return json.load(open(p)) if os.path.exists(p) else []


def save_json_atomic(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def canonical_log(run_dir):
    """segments.json 순서대로 각 segment의 [start, 다음 segment start) 구간만 canonical로 채택한다.
    외부 prefix(init_from 원본)도 segment로 참조한다. 중복·누락·순서 오류는 ValueError.
    반환 record는 첫 segment 시작 update부터 연속이어야 한다(완료 판정은 0부터 전체를 따로 요구)."""
    segs = load_segments(run_dir)
    recs = []
    orphans = 0
    for k, s in enumerate(segs):
        end = segs[k + 1]["start_update"] if k + 1 < len(segs) else None
        path = s["path"] if os.path.isabs(s["path"]) else os.path.join(run_dir, s["path"])
        if s.get("sha256_at_link") and D.sha256_file(path) != s["sha256_at_link"]:
            raise ValueError(f"external log segment changed since link: {path}")
        seg_recs = [r for r in read_jsonl(path) if r["update"] >= s["start_update"]]
        if s.get("prefix_end") is not None:
            seg_recs = [r for r in seg_recs if r["update"] < s["prefix_end"]]
        for r in seg_recs:
            if end is None or r["update"] < end:
                recs.append(r)
            else:
                orphans += 1
    ups = [r["update"] for r in recs]
    if len(ups) != len(set(ups)):
        raise ValueError("duplicate update in canonical log")
    if ups and ups != list(range(ups[0], ups[0] + len(ups))):
        raise ValueError(f"canonical log gap/order error: first={ups[:3]} last={ups[-3:]} n={len(ups)}")
    return recs, orphans


# ---------------------------------------------------------------- checkpoint
REQUIRED = ["format_version", "model", "optimizer", "scheduler", "rng", "ds_rng_state", "epoch_of_next",
            "update_idx", "cursor_in_epoch", "perm", "config", "config_digest", "input_digest", "source_digest",
            "lr_next", "n_canonical_log", "attempt_id", "train_device_index"]


def make_checkpoint(model, opt, sched, ds, update_idx, updates_per_epoch, perm_next, args, attempt_id, dig, n_log):
    return {
        "format_version": FORMAT_VERSION,
        "model": model.state_dict(),
        "optimizer": opt.state_dict(),
        "scheduler": sched.state_dict(),
        "rng": D.full_rng_state(),
        "ds_rng_state": ds.rng.getstate(),
        "epoch_of_next": update_idx // updates_per_epoch,
        "update_idx": update_idx,
        "cursor_in_epoch": update_idx % updates_per_epoch,
        "perm": perm_next,
        "config": config_of(args),
        "config_digest": jdigest(config_of(args)),
        "input_digest": dig["input"],
        "source_digest": dig["source"],
        "lr_next": [g["lr"] for g in opt.param_groups],
        "n_canonical_log": n_log,
        "attempt_id": attempt_id,
        "train_device_index": int(args.device),
        "saved_t": time.time(),
    }


def params_digest(model):
    h = hashlib.sha256()
    for _, p in sorted(model.state_dict().items()):
        h.update(p.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def opt_state_digest(opt):
    h = hashlib.sha256()
    for gi, g in enumerate(opt.param_groups):
        for p in g["params"]:
            st = opt.state.get(p, {})
            for k in sorted(st):
                v = st[k]
                if torch.is_tensor(v):
                    h.update(v.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def validate_and_load(ck, model, opt, sched, args, dig, updates_per_epoch, n_ids, migration=None):
    """재개 checkpoint 검증. 실패는 RuntimeError. migration은 format 1 이관 기록(dict)."""
    fmt = ck.get("format_version", 1)
    if fmt == 1:
        if migration is None:
            raise RuntimeError("format-1 checkpoint requires --migration manifest")
        # 구버전: 이관 manifest가 원본 sha256·설정·input·scheduler·RNG·permutation 복원 근거를 보증해야 한다.
        for k in ("source_checkpoint_sha256", "config", "input_digest", "update_idx", "source_code_sha256"):
            if k not in migration:
                raise RuntimeError(f"migration manifest missing {k}")
        if migration["config"] != config_of(args):
            raise RuntimeError(f"migration config mismatch: {migration['config']} vs {config_of(args)}")
        if migration["input_digest"] != dig["input"]:
            raise RuntimeError("migration input digest mismatch")
        for k in ("model", "optimizer", "scheduler", "rng", "update_idx", "sample_cursor", "epoch"):
            if k not in ck:
                raise RuntimeError(f"format-1 checkpoint missing {k}")
        if ck.get("extra", {}).get("ds_rng_state") is None:
            raise RuntimeError("format-1 checkpoint missing ds_rng_state")
        u = ck["update_idx"]
        if u != migration["update_idx"]:
            raise RuntimeError("migration update_idx mismatch")
        # 구버전 cursor 규약: epoch=마지막 완료 update의 epoch, sample_cursor=그 epoch 내 완료 update 수
        if ck["epoch"] != (u - 1) // updates_per_epoch or ck["sample_cursor"] != (u - 1) % updates_per_epoch + 1:
            raise RuntimeError("format-1 epoch/cursor inconsistent with update_idx")
        ds_state = ck["extra"]["ds_rng_state"]
        if u % updates_per_epoch == 0:
            ds_state = None  # epoch 경계: 다음 epoch 시작에서 새로 시딩(원 코드와 동일)
        norm = {"ds_rng_state": ds_state, "update_idx": u, "lr_expected_next": None,
                "perm": epoch_perm(args.seed, u // updates_per_epoch, n_ids)}
    else:
        miss = [k for k in REQUIRED if k not in ck]
        if miss:
            raise RuntimeError(f"checkpoint missing required state: {miss}")
        if ck["config"] != config_of(args) or ck["config_digest"] != jdigest(config_of(args)):
            raise RuntimeError(f"config mismatch: saved={ck['config']} now={config_of(args)}")
        if ck["input_digest"] != dig["input"]:
            raise RuntimeError("input digest mismatch")
        if ck["source_digest"] != dig["source"]:
            raise RuntimeError("source digest mismatch (code changed since checkpoint)")
        u = ck["update_idx"]
        if ck["epoch_of_next"] != u // updates_per_epoch or ck["cursor_in_epoch"] != u % updates_per_epoch:
            raise RuntimeError("epoch/cursor inconsistent with update_idx")
        if ck["perm"] != epoch_perm(args.seed, u // updates_per_epoch, n_ids):
            raise RuntimeError("saved permutation differs from deterministic epoch permutation")
        norm = {"ds_rng_state": ck["ds_rng_state"] if u % updates_per_epoch != 0 else None, "update_idx": u,
                "lr_expected_next": ck["lr_next"], "perm": ck["perm"]}
    model.load_state_dict(ck["model"])
    # 순서: scheduler 생성(이미 완료) → optimizer state → scheduler state. 이후 실제 group lr을 검사한다.
    opt.load_state_dict(ck["optimizer"])
    sched.load_state_dict(ck["scheduler"])
    if sched.last_epoch != u:
        raise RuntimeError(f"scheduler last_epoch {sched.last_epoch} != update_idx {u}")
    for gi, g in enumerate(opt.param_groups):
        exp = sched.lr_lambdas[gi](sched.last_epoch) * g["initial_lr"]
        if abs(g["lr"] - exp) > 1e-15 * max(1.0, abs(exp)):
            raise RuntimeError(f"group {gi} lr {g['lr']} != scheduled {exp}")
        if norm["lr_expected_next"] is not None and g["lr"] != norm["lr_expected_next"][gi]:
            raise RuntimeError(f"group {gi} lr {g['lr']} != saved lr_next {norm['lr_expected_next'][gi]}")
        if g["initial_lr"] != args.lr:
            raise RuntimeError("initial_lr differs from configured lr")
    # 학습 장치의 CUDA generator만 복원(저장 process가 본 GPU 수와 무관). 구버전은 migration의 old_args.device.
    saved_dev = int(migration["old_args"]["device"]) if fmt == 1 else ck["train_device_index"]
    D.restore_rng_state(ck["rng"], (saved_dev, int(args.device)))
    return norm


# ---------------------------------------------------------------- train
def has_train_artifacts(run_dir):
    if not os.path.isdir(run_dir):
        return False
    names = set(os.listdir(run_dir))
    return bool(names & {"ckpt_latest.pt", "segments.json", "complete.json", "train_log.jsonl"}) or any(
        n.startswith("log_seg") for n in names)


def cmd_train(args):
    if args.deterministic:
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    manifest = json.load(open(find_manifest(args.manifest)))
    ids = manifest["ids"]
    gt, infer = D.load_gt_infer()
    device = torch.device(f"cuda:{args.device}" if torch.cuda.is_available() else "cpu")
    run_dir = args.run_dir
    latest_path = os.path.join(run_dir, "ckpt_latest.pt")
    complete_path = os.path.join(run_dir, "complete.json")
    attempt_id = f"{socket.gethostname()}-{os.getpid()}-{int(time.time())}"

    existing = has_train_artifacts(run_dir)
    if args.fresh and existing:
        raise RuntimeError(f"--fresh refused: {run_dir} already has training artifacts")
    if args.init_from and existing:
        raise RuntimeError(f"--init_from refused: {run_dir} already has training artifacts")
    if not args.fresh and not args.init_from and not os.path.exists(latest_path):
        raise RuntimeError(f"no checkpoint in {run_dir}; use --fresh or --init_from")
    lock = FlockLock(run_dir, attempt_id)
    signal.signal(signal.SIGTERM, _sigterm_handler)
    try:
        updates_per_epoch = len(ids) // args.effective_batch
        target_updates = updates_per_epoch * args.epochs
        warmup_updates = updates_per_epoch * args.warmup_epochs
        milestone_updates = [updates_per_epoch * m for m in args.lr_drop_epochs]
        dig = {"source": source_digest()[0], "input": input_digest(ids, gt, infer)}

        if os.path.exists(complete_path):
            comp = json.load(open(complete_path))
            verify_complete(run_dir, comp)
            if not args.extend or target_updates <= comp["total_updates"]:
                raise RuntimeError(f"run already complete at {comp['total_updates']} updates; "
                                   f"use --extend with larger --epochs to continue")

        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        model = D.build_model(trainable_backbone_layers=args.trainable_backbone_layers,
                              min_size=args.min_size, max_size=args.max_size).to(device)
        opt = D.build_optimizer(model, lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)
        sched = D.linear_warmup_then_multistep(opt, warmup_updates, milestone_updates)
        ds = D.RSNADetDataset(ids, gt, infer, train_aug=True, seed=args.seed, flip_p=args.flip_p)

        segs = load_segments(run_dir)
        if args.fresh:
            start_update = 0
            resume_ds_state = None
            init_info = {"mode": "fresh"}
        else:
            src = args.init_from if args.init_from else latest_path
            ck = torch.load(src, map_location="cpu", weights_only=False)
            migration = json.load(open(args.migration)) if args.migration else None
            if migration is not None and D.sha256_file(src) != migration["source_checkpoint_sha256"]:
                raise RuntimeError("init checkpoint sha256 differs from migration manifest")
            norm = validate_and_load(ck, model, opt, sched, args, dig, updates_per_epoch, len(ids), migration)
            D.optimizer_state_to_device(opt, device)
            start_update = norm["update_idx"]
            resume_ds_state = norm["ds_rng_state"]
            if args.init_from:
                init_info = {"mode": "init_from", "source": os.path.abspath(src),
                             "source_sha256": D.sha256_file(src), "update_idx": start_update,
                             "migration": os.path.abspath(args.migration) if args.migration else None}
                # 원본 run의 canonical 로그 prefix를 외부 segment로 연결(원본은 수정하지 않는다).
                if args.prefix_log:
                    segs.append({"path": os.path.abspath(args.prefix_log), "start_update": 0,
                                 "prefix_end": start_update, "sha256_at_link": D.sha256_file(args.prefix_log),
                                 "attempt_id": "external_prefix", "kind": "external_prefix"})
            else:
                init_info = {"mode": "resume", "update_idx": start_update}
                # 최신 checkpoint의 canonical 로그 수 확인: 이후 기록은 orphan으로 남는다.
                if ck.get("n_canonical_log") is not None and ck["n_canonical_log"] != start_update:
                    raise RuntimeError("checkpoint n_canonical_log != update_idx")
            if start_update >= target_updates:
                raise RuntimeError(f"checkpoint at {start_update} >= target {target_updates}")
            del ck

        D.set_train_mode(model)
        seg_name = f"log_seg{len(segs):03d}.jsonl"
        segs.append({"path": seg_name, "start_update": start_update, "attempt_id": attempt_id,
                     "pid": os.getpid(), "starttime": proc_starttime(os.getpid()), "t": time.time(),
                     "init": init_info, "target_updates": target_updates, "deterministic": args.deterministic,
                     "device": args.device, "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")})
        save_json_atomic(segs, os.path.join(run_dir, "segments.json"))
        save_json_atomic({"config": config_of(args), "config_digest": jdigest(config_of(args)),
                          "source_digest": dig["source"], "source_files": source_digest()[1],
                          "input_digest": dig["input"], "n_ids": len(ids), "updates_per_epoch": updates_per_epoch},
                         os.path.join(run_dir, "run_config.json"))
        seg_path = os.path.join(run_dir, seg_name)
        stop_after = args.stop_after if args.stop_after is not None else target_updates
        end_update = min(target_updates, stop_after)
        save_at = set(args.save_at or [])

        t0 = time.time()
        n_images = 0
        cur_epoch = None
        perm = None
        update_idx = start_update
        for update_idx in range(start_update, end_update):
            epoch_idx = update_idx // updates_per_epoch
            pos = update_idx % updates_per_epoch
            if epoch_idx != cur_epoch:
                if update_idx == start_update and resume_ds_state is not None:
                    ds.rng.setstate(resume_ds_state)
                else:
                    if pos != 0:
                        raise RuntimeError("mid-epoch start without dataset RNG state")
                    ds.set_epoch_rng(args.seed * 1000 + epoch_idx)
                perm = epoch_perm(args.seed, epoch_idx, len(ids))
                cur_epoch = epoch_idx
            bidx = perm[pos * args.effective_batch:(pos + 1) * args.effective_batch]
            imgs, targets, pids, flips = [], [], [], []
            for bi in bidx:
                img, target, hw = ds[bi]
                imgs.append(img.to(device))
                targets.append({"boxes": target["boxes"].to(device), "labels": target["labels"].to(device)})
                pids.append(ds.ids[bi])
                flips.append(bool(target["flip"]))
            in_digest = None
            if args.trace:
                h = hashlib.sha256()
                for im, tg in zip(imgs, targets):
                    h.update(im.cpu().numpy().tobytes()); h.update(tg["boxes"].cpu().numpy().tobytes())
                in_digest = h.hexdigest()
            opt.zero_grad()
            total_loss = 0.0
            parts = {}
            for s in range(0, len(imgs), args.microbatch):
                sub_i, sub_t = imgs[s:s + args.microbatch], targets[s:s + args.microbatch]
                loss_dict = model(sub_i, sub_t)
                w = len(sub_i) / len(imgs)
                loss = sum(loss_dict.values()) * w
                loss.backward()
                total_loss += float(loss.item())
                for k, v in loss_dict.items():
                    parts[k] = parts.get(k, 0.0) + float(v.item()) * w
            gn = float(torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1e6))
            if os.environ.get("DET_TEST_NAN_AT") == str(update_idx):  # 비유한 중단 검사 전용
                total_loss = float("nan")
            if not (np.isfinite(total_loss) and np.isfinite(gn) and all(np.isfinite(v) for v in parts.values())):
                save_json_atomic({"update": update_idx, "loss": total_loss, "grad_norm": gn, "parts": parts,
                                  "sample_ids": pids, "attempt_id": attempt_id, "t": time.time()},
                                 os.path.join(run_dir, "nonfinite.json"))
                raise FloatingPointError(f"non-finite loss/grad at update {update_idx}; aborting before step")
            lr_applied = [g["lr"] for g in opt.param_groups]
            opt.step()
            sched.step()
            n_images += len(bidx)
            rec = {"update": update_idx, "epoch": epoch_idx, "pos": pos, "loss": total_loss, "grad_norm": gn,
                   "lr_applied": lr_applied[0], "lr_applied_all_equal": len(set(lr_applied)) == 1,
                   "lr_next": opt.param_groups[0]["lr"], "sample_ids": pids, "flips": flips,
                   "attempt_id": attempt_id, "t": time.time(), **parts}
            if args.trace:
                rec["input_digest"] = in_digest
                rec["params_digest"] = params_digest(model)
            with open(seg_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            done = update_idx + 1
            if update_idx % 50 == 0 or done == end_update:
                el = time.time() - t0
                rate = n_images / el if el > 0 else 0.0
                eta = (target_updates - done) * args.effective_batch / rate if rate > 0 else None
                print(json.dumps({"update": update_idx, "epoch": epoch_idx, "loss": round(total_loss, 5),
                                  "lr_applied": lr_applied[0], "images_per_sec": round(rate, 3),
                                  "eta_s": round(eta) if eta else None,
                                  "gpu_alloc_mib": round(torch.cuda.max_memory_allocated(device) / 2**20) if torch.cuda.is_available() else None}),
                      flush=True)
            epoch_end = done % updates_per_epoch == 0
            stop_now = _STOP_REQUESTED["flag"] or done == end_update
            if epoch_end or done % 100 == 0 or stop_now or done in save_at:
                perm_next = perm if not epoch_end else epoch_perm(args.seed, done // updates_per_epoch, len(ids))
                ck = make_checkpoint(model, opt, sched, ds, done, updates_per_epoch, perm_next, args, attempt_id,
                                     dig, done)
                if done in save_at:
                    D.atomic_save(ck, os.path.join(run_dir, f"ckpt_u{done:05d}.pt"))
                    if args.trace:
                        with open(os.path.join(run_dir, f"ckpt_u{done:05d}.digest.json"), "w") as f:
                            json.dump({"update": done, "params_digest": params_digest(model),
                                       "opt_state_digest": opt_state_digest(opt), "lr_next": ck["lr_next"],
                                       "sched_last_epoch": sched.last_epoch}, f)
                D.atomic_save(ck, latest_path)
                if epoch_end:
                    ep_dir = os.path.join(run_dir, f"epoch_{done // updates_per_epoch:02d}")
                    os.makedirs(ep_dir, exist_ok=True)
                    D.atomic_save({"model": model.state_dict(), "update_idx": done, "config_digest": ck["config_digest"],
                                   "source_digest": dig["source"], "input_digest": dig["input"]},
                                  os.path.join(ep_dir, "model.pt"))
                del ck
            if _STOP_REQUESTED["flag"]:
                print(json.dumps({"sigterm_stop": True, "saved_update": done}), flush=True)
                return EXIT_STOPPED
        if end_update < target_updates:
            print(json.dumps({"stop_after_reached": True, "saved_update": end_update}), flush=True)
            return EXIT_STOPPED
        el = time.time() - t0
        recs, orphans = canonical_log(run_dir)
        if len(recs) != target_updates or recs[0]["update"] != 0:
            raise RuntimeError(f"canonical log has {len(recs)} records from {recs[0]['update'] if recs else None}; "
                               f"expected 0..{target_updates - 1}")
        if os.path.exists(complete_path):  # --extend: 이전 완료 marker를 보존
            prev = json.load(open(complete_path))
            save_json_atomic(prev, os.path.join(run_dir, f"complete_u{prev['total_updates']:05d}.json"))
        comp = {"total_updates": target_updates, "epochs": args.epochs, "ckpt_sha256": D.sha256_file(latest_path),
                "canonical_log_digest": jdigest([[r["update"], r["loss"], r["sample_ids"], r["flips"]] for r in recs]),
                "n_orphan_records": orphans, "config_digest": jdigest(config_of(args)), "source_digest": dig["source"],
                "input_digest": dig["input"], "attempt_id": attempt_id, "t": time.time()}
        save_json_atomic(comp, complete_path)
        print(json.dumps({"done": True, "total_updates": target_updates, "elapsed_s": el,
                          "images_per_sec": n_images / el if el > 0 else None,
                          "peak_allocated_mib": torch.cuda.max_memory_allocated(device) / 2**20 if torch.cuda.is_available() else None,
                          "peak_reserved_mib": torch.cuda.max_memory_reserved(device) / 2**20 if torch.cuda.is_available() else None}),
              flush=True)
        return 0
    finally:
        lock.release()


def verify_complete(run_dir, comp=None):
    comp = comp or json.load(open(os.path.join(run_dir, "complete.json")))
    latest = os.path.join(run_dir, "ckpt_latest.pt")
    if D.sha256_file(latest) != comp["ckpt_sha256"]:
        raise RuntimeError("complete.json ckpt_sha256 mismatch")
    recs, _ = canonical_log(run_dir)
    if len(recs) != comp["total_updates"] or recs[0]["update"] != 0:
        raise RuntimeError("complete.json total_updates mismatch with canonical log")
    d = jdigest([[r["update"], r["loss"], r["sample_ids"], r["flips"]] for r in recs])
    if d != comp["canonical_log_digest"]:
        raise RuntimeError("complete.json canonical_log_digest mismatch")
    rc = json.load(open(os.path.join(run_dir, "run_config.json")))
    if rc["config_digest"] != comp["config_digest"]:
        raise RuntimeError("complete.json config digest mismatch")
    return True


def cmd_verify(args):
    verify_complete(args.run_dir)
    print(json.dumps({"verified": True, "run_dir": args.run_dir}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("train")
    p.add_argument("--manifest", required=True)
    p.add_argument("--run_dir", required=True)
    p.add_argument("--device", default="0")
    p.add_argument("--epochs", type=int, required=True)
    p.add_argument("--effective_batch", type=int, default=8)
    p.add_argument("--microbatch", type=int, default=2)
    p.add_argument("--lr", type=float, default=0.005)
    p.add_argument("--momentum", type=float, default=0.9)
    p.add_argument("--weight_decay", type=float, default=1e-4)
    p.add_argument("--lr_drop_epochs", type=int, nargs="*", default=[])
    p.add_argument("--warmup_epochs", type=int, default=1)
    p.add_argument("--trainable_backbone_layers", type=int, default=5)
    p.add_argument("--flip_p", type=float, default=0.5)
    p.add_argument("--min_size", type=int, default=800)
    p.add_argument("--max_size", type=int, default=1333)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--init_from", default=None)
    p.add_argument("--migration", default=None)
    p.add_argument("--prefix_log", default=None)
    p.add_argument("--extend", action="store_true")
    p.add_argument("--stop_after", type=int, default=None)
    p.add_argument("--save_at", type=int, nargs="*", default=None)
    p.add_argument("--trace", action="store_true")
    p.add_argument("--deterministic", action="store_true")
    p.set_defaults(func=cmd_train)
    p = sub.add_parser("verify")
    p.add_argument("--run_dir", required=True)
    p.set_defaults(func=cmd_verify)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
