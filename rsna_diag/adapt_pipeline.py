"""iter_013 실행 파이프라인 (재개 가능, 단계별 근거 재검증). 사용: python -m rsna_diag.adapt_pipeline --stage explore|full_s17|full_s29|full_s43 [--conds C,D,H] [--lrs ...]

한 stage = 여러 trajectory(조건 x LR)의 추가 적응 학습 + V200 milestone 검증 + V400 완성(V200 응답을 부모로 재사용해 나머지 200만 생성) + 보고.
- 학습은 GPU lane별로 순차 실행한다 (학습 worker는 GPU당 1개: microbatch 실측 peak + 2GiB 여유로 한 장에 2개가 안 들어감; decisions/exec_config.json).
- 건너뛰기는 파일 존재가 아니라 select.verify_epoch / eval_gate.verify_gen 재검증을 통과할 때만이다. 불일치는 예외 (조용히 재사용하지 않음).
- 보고서 report.json은 원시 응답에서 재계산한 결정적 내용만 담고 write_or_verify로 기존 파일과 일치를 강제한다. 시간·자원은 usage.json에 따로 기록한다.
- pipeline.lock으로 stage당 단일 소유를 강제한다.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time

from . import adapt_eval as AE, eval_gate, inputs, lock_protocol, queue_lock, select as SEL, sft_eval
from .run_shards import gpu_snapshot

R = "results/iter_013"
PROT = f"{R}/protocols/main_protocol.json"
EXEC = f"{R}/decisions/exec_config.json"
MAN = AE.MANIFEST
FREE_BEFORE_MIB = 2000


def lrs(x):
    return f"{x:g}"


class Ctx:
    def __init__(self, stage):
        self.stage = stage
        self.cfg = json.load(open(f"{R}/stage/{stage}.json"))
        self.dir = f"{R}/{stage}"
        os.makedirs(self.dir, exist_ok=True)
        self.logp = f"{self.dir}/pipeline.log"
        self.ex = json.load(open(EXEC))
        self.pdig = lock_protocol.verify(PROT)
        self.val_items, self.gt = inputs.load_items(MAN, AE.GT, self.cfg["val_ids"], "validation", exact=False)
        self.v_in = inputs.inputs_digest(self.val_items, self.gt)
        self.v400_items, _ = inputs.load_items(MAN, AE.GT, AE.V400_IDS, "validation", exact=True)
        self.tr_ids = [i for i in self.gt if self.gt[i]["split"] == "train"]
        self.aed = sft_eval.area_edges(self.gt, self.tr_ids)
        self.bed = AE.box_edges_train(self.gt, self.tr_ids)
        self.spe = None

    def log(self, msg):
        line = f"[{time.strftime('%F %T')}] {msg}"
        print(line, flush=True)
        with open(self.logp, "a") as f:
            f.write(line + "\n")


def wait_gpu_free(ctx, gpu):
    while True:
        rows, apps = gpu_snapshot({gpu})
        if rows and rows[0]["mem_used_mib"] <= FREE_BEFORE_MIB:
            ctx.log(f"gpu {gpu} free: {rows[0]}")
            return
        ctx.log(f"waiting for gpu {gpu}: {rows} apps={apps}")
        time.sleep(120)


def run_dir(ctx, cond, lr, seedtag=""):
    return f"{ctx.dir}/{cond}_lr{lrs(lr)}"


def trained_ok(ctx, d):
    """done.json + epoch 1..E 전체 검증 (원시 응답 재계산). 파일이 없으면 False, 근거 불일치는 예외."""
    if not os.path.exists(os.path.join(d, "train_config.json")):
        return False
    tc = json.load(open(os.path.join(d, "train_config.json")))
    E = ctx.cfg["epochs"]
    if not os.path.exists(os.path.join(d, "done.json")):
        return False
    for e in range(1, E + 1):
        if not os.path.exists(os.path.join(d, f"epoch_{e:02d}", "val_metrics.json")):
            return False
        SEL.verify_epoch(d, e, tc, ctx.v_in, PROT, ctx.val_items, ctx.gt)
    return True


def train_cmd(ctx, cond, lr, d):
    return [sys.executable, "-m", "rsna_diag.adapt", "--run-dir", d, "--stage-config", f"{R}/stage/{ctx.stage}.json", "--loss", cond, "--lr", str(lr),
            "--protocol", PROT, "--microbatch", str(ctx.ex["train_microbatch"]), "--workers", "3"]


def train_traj(ctx, gpu, cond, lr):
    d = run_dir(ctx, cond, lr)
    if trained_ok(ctx, d):
        ctx.log(f"{d}: verified complete")
        return
    wait_gpu_free(ctx, gpu) if not os.path.exists(os.path.join(d, "train.lock")) else None
    ctx.log(f"train {cond} lr={lr} on gpu {gpu} -> {d}")
    t0 = time.time()
    rc = subprocess.run(train_cmd(ctx, cond, lr, d), env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)), stdout=open(f"{d}.log", "a"), stderr=subprocess.STDOUT).returncode
    ctx.log(f"train {cond} lr={lr} rc={rc} wall={time.time() - t0:.0f}s")
    if rc != 0 or not trained_ok(ctx, d):
        raise RuntimeError(f"{d}: training failed or not verified (rc={rc})")


def v200_detail(ctx, d, e):
    tc = json.load(open(os.path.join(d, "train_config.json")))
    SEL.verify_epoch(d, e, tc, ctx.v_in, PROT, ctx.val_items, ctx.gt)
    ed = os.path.join(d, f"epoch_{e:02d}")
    recs = eval_gate.verify_gen(os.path.join(ed, "val_gen"), ctx.val_items, ["concise"], ed, PROT)
    ids = [i["id"] for i in ctx.val_items]
    return AE.detail(AE.preds_of(recs, ids), ctx.gt, ids, ctx.aed, ctx.bed), tc["config"]["steps_per_epoch"]


def b0_details(ctx):
    recs = AE.b0_records(PROT, ctx.v400_items)
    ids400 = [i["id"] for i in ctx.v400_items]
    p400 = AE.preds_of(recs, ids400)
    v200 = [i["id"] for i in ctx.val_items]
    return p400, AE.detail(p400, ctx.gt, ids400, ctx.aed, ctx.bed), AE.detail({i: p400[i] for i in v200}, ctx.gt, v200, ctx.aed, ctx.bed)


def gen_v400(ctx, gpu_list, d, e):
    """epoch e adapter의 V400 완성. V200 val_gen을 부모로 재사용하고 나머지만 새로 생성한다. returns records."""
    ed = os.path.join(d, f"epoch_{e:02d}")
    out = os.path.join(d, f"v400_epoch{e:02d}")
    par = os.path.join(ed, "val_gen")
    try:
        return eval_gate.verify_gen(out, ctx.v400_items, ["concise"], ed, PROT, par, PROT)
    except (eval_gate.GateError, FileNotFoundError) as ex:
        ctx.log(f"{out}: not complete/verified ({str(ex)[:120]}) -> run_shards")
    for g in gpu_list:
        wait_gpu_free(ctx, g)
    nw = ctx.ex["gen_workers_per_gpu"] * len(gpu_list)
    cmd = [sys.executable, "-m", "rsna_diag.run_shards", "--manifest", MAN, "--ids", AE.V400_IDS, "--out-dir", out, "--protocol", PROT, "--prompts", "concise",
           "--workers", str(nw), "--gpus", ",".join(map(str, gpu_list)), "--adapter", ed, "--parent-dir", par, "--parent-protocol", PROT]
    rc = subprocess.run(cmd, env=dict(os.environ, CUDA_VISIBLE_DEVICES=",".join(map(str, gpu_list))), stdout=open(f"{out}.log", "a"), stderr=subprocess.STDOUT).returncode
    ctx.log(f"gen {out} rc={rc}")
    if rc != 0:
        raise RuntimeError(f"{out}: run_shards failed rc={rc}")
    return eval_gate.verify_gen(out, ctx.v400_items, ["concise"], ed, PROT, par, PROT)


def select_traj(ctx, d, b0_v200):
    """trajectory의 milestone(epoch 1..E)별 V200 detail과 guardrail 통과 최대 S_loc 선택 (동률은 이른 update)."""
    cands, det = {}, {}
    for e in range(1, ctx.cfg["epochs"] + 1):
        dt, spe = v200_detail(ctx, d, e)
        cands[e * spe], det[e] = dt, dt
    sel_upd, table = AE.select_checkpoint(cands, b0_v200)
    return {"update_to_epoch": {u: u // spe for u in cands}, "selected_update": sel_upd,
            "selected_epoch": (sel_upd // spe if sel_upd else None), "table": {str(u): t for u, t in table.items()}}, det, spe


def compare(preds_by, gt, ids, pairs):
    return {f"{a}-{b}": AE.paired_ci(preds_by[a], preds_by[b], gt, ids) for a, b in pairs if a in preds_by and b in preds_by}


def report(ctx, trajs):
    """trajs: [(cond, lr)] 모두 학습·검증 완료 상태. V400 완성 후 report.json (결정적 내용)."""
    ids400 = [i["id"] for i in ctx.v400_items]
    p400_b0, d400_b0, d200_b0 = b0_details(ctx)
    rep = {"stage": ctx.stage, "protocol_digest": ctx.pdig, "b0": {"v400": d400_b0, "v200": d200_b0}, "trajectories": {}}
    preds = {"B0": p400_b0}
    dets = {"B0": d400_b0}
    for cond, lr in trajs:
        d = run_dir(ctx, cond, lr)
        name = f"{cond}@{lrs(lr)}"
        sel, det200, spe = select_traj(ctx, d, d200_b0)
        E = ctx.cfg["epochs"]
        entry = {"lr": lr, "cond": cond, "steps_per_epoch": spe, "selection_v200": sel, "v200_detail_by_epoch": {str(e): det200[e] for e in det200}}
        for tag, e in (("final", E), ("selected", sel["selected_epoch"])):
            if e is None:
                entry[tag] = None
                continue
            recs = gen_v400(ctx, [int(g) for g in ctx.ex["gen_gpus"]], d, e)
            p = AE.preds_of(recs, ids400)
            entry[tag] = {"epoch": e, "update": e * spe, "v400": AE.detail(p, ctx.gt, ids400, ctx.aed, ctx.bed),
                          "guardrail_v400": AE.guardrail(AE.detail(p, ctx.gt, ids400, ctx.aed, ctx.bed), d400_b0)}
            preds[f"{name}/{tag}"] = p
            dets[f"{name}/{tag}"] = entry[tag]["v400"]
        rep["trajectories"][name] = entry
    rep["pairwise_v400_paired_bootstrap"] = {}
    names = [n for n in preds if n != "B0"]
    for tag in ("selected", "final"):
        pb = {"B0": preds["B0"], **{n.split("/")[0]: p for n, p in preds.items() if n.endswith("/" + tag)}}
        cs = sorted(k for k in pb if k != "B0")
        pairs = [(a, "B0") for a in cs] + [(a, b) for a in cs for b in cs if a != b and a.split("@")[0] in ("D", "H") and b.split("@")[0] in ("C", "H") and not (a[0] == b[0])]
        rep["pairwise_v400_paired_bootstrap"][tag] = compare(pb, ctx.gt, ids400, pairs)
    del names
    return rep, preds


def write_or_verify(path, obj):
    return SEL.write_or_verify(path, obj)


def lane(ctx, gpu, items):
    for fn in items:
        fn()


def run_lanes(lanes):
    """lanes: {gpu: [callable...]}. 각 lane은 순차, lane 간 병렬. 예외는 모두 수집해 다시 던진다."""
    errs = []

    def w(fns):
        try:
            for f in fns:
                f()
        except BaseException as e:  # noqa
            errs.append(e)
            ABORT.set()

    ths = [threading.Thread(target=w, args=(fns,)) for fns in lanes.values()]
    [t.start() for t in ths]
    [t.join() for t in ths]
    if errs:
        raise errs[0]


_B0 = {}
_LOCK = threading.Lock()
ABORT = threading.Event()


def b0_cached(ctx):
    with _LOCK:
        if "v" not in _B0:
            _B0["v"] = b0_details(ctx)
        return _B0["v"]


def prefetch(ctx, gpu, pending, trajs_dirs):
    """이 lane이 학습을 마친 뒤, 학습이 끝난 trajectory부터 하나씩 claim해 final/selected checkpoint의 V400 나머지 200요청을 자기 GPU에서 생성한다.
    (다른 lane이 아직 학습 중이면 그 trajectory가 끝날 때까지 기다린다.) 결과는 report()가 재검증하므로 여기서는 생성만 한다."""
    while True:
        with _LOCK:
            ready = [t for t in pending if os.path.exists(os.path.join(trajs_dirs[t], "done.json"))]
            if not pending:
                return
            claim = ready[0] if ready else None
            if claim:
                pending.remove(claim)
        if claim is None:
            if ABORT.is_set():
                return
            time.sleep(60)
            continue
        d = trajs_dirs[claim]
        _, _, d200_b0 = b0_cached(ctx)
        sel, _, _ = select_traj(ctx, d, d200_b0)
        for e in sorted({ctx.cfg["epochs"], sel["selected_epoch"]} - {None}):
            gen_v400(ctx, [gpu], d, e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--trajs", required=True, help="예: C:2e-5,D:2e-5,H:2e-5 (lane 배정: 순서대로 gpu0, gpu1 번갈아)")
    ap.add_argument("--report-name", default="report")
    a = ap.parse_args()
    ctx = Ctx(a.stage)
    lk, own, _ = queue_lock.try_lock(os.path.join(os.path.realpath(ctx.dir), "pipeline.lock"), queue_lock.my_info(role="adapt_pipeline"))
    if lk is None:
        sys.exit(f"another pipeline owns {ctx.dir}: {own}")
    try:
        trajs = [(c, float(l)) for c, l in (x.split(":") for x in a.trajs.split(","))]
        gpus = [int(g) for g in ctx.ex["train_gpus"]]
        lanes = {g: [] for g in gpus}
        dirs = {(c, l): run_dir(ctx, c, l) for c, l in trajs}
        pending = list(dirs)
        for k, (c, l) in enumerate(trajs):
            g = gpus[k % len(gpus)]
            lanes[g].append(lambda g=g, c=c, l=l: train_traj(ctx, g, c, l))
        for g in gpus:
            lanes[g].append(lambda g=g: prefetch(ctx, g, pending, dirs))
        t0 = time.time()
        run_lanes(lanes)
        ctx.log(f"all trainings verified; wall={time.time() - t0:.0f}s")
        rep, preds = report(ctx, trajs)
        ctx.log(f"report {write_or_verify(f'{ctx.dir}/{a.report_name}.json', json.loads(json.dumps(rep)))}")
        ctx.log("STAGE COMPLETE")
    finally:
        lk.release()


if __name__ == "__main__":
    main()
