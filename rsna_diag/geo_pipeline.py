"""iter_014 실행 파이프라인 (재개 가능, 단계별 근거 재검증). 사용:
python -m rsna_diag.geo_pipeline --stage explore|full|compute --trajs G:2e-5,U:2e-5,C:2e-5 [--reuse-c results/iter_013/explore/C_lr2e-05]

한 stage = 여러 trajectory(조건 x LR)의 추가 적응 학습 + milestone V200 검증 + V400 완성(V200 응답을 부모로 재사용해 나머지 200만 생성) + 보고.
iter_013 adapt_pipeline.py에서 고친 것 (reuse_issues):
- GPU 허용 집합: 상속된 CUDA_VISIBLE_DEVICES(정수 목록)의 원소만 쓰고, 자식에게는 그 원소를 물리 장치로 전달한다 (덮어써서 허용 밖으로 확장하지 않는다).
- 메모리 확인은 train.lock 존재와 무관하게 항상 수행한다. 필요 여유 = exec_config의 측정 peak + 2GiB.
- 완료 판정(trained_ok)은 done.json·milestone 검증뿐 아니라 요청한 stage 파일 hash, loss, LR, 부모 adapter digest, 후보 manifest digest, train/validation
  입력 digest, 예정 update 수, 현재 protocol과 train_config를 대조한다 (불일치는 예외, 조용한 재사용 없음).
- selected=null 은 null로 두고 final과 분리해 기록한다 (selection_eligible=false). 대체는 geo_decide의 사전 규칙(C/U 한정)만.
- iter_013 C의 재사용은 호환성 manifest(compat_C.json)로 입력·설정·adapter·원시 응답을 검증한 경우에만 읽기 전용으로 쓴다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np

from . import adapt_eval as AE, eval_gate, inputs, lock_protocol, metrics as M, migrate, parse as PA, queue_lock, select as SEL, sft_eval
from .run_shards import gpu_snapshot

R = "results/iter_014"
PROT = f"{R}/protocols/main_protocol.json"
EXEC = f"{R}/decisions/exec_config.json"
MAN = AE.MANIFEST
OLD_PROT = "results/iter_013/protocols/main_protocol.json"
OLD_STAGE = "results/iter_013/stage/explore.json"
MARGIN_MIB = 2048


def lrs(x):
    return f"{x:g}"


def allowed_gpus():
    raw = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not raw:
        raise SystemExit("CUDA_VISIBLE_DEVICES not set")
    return [int(x) for x in raw.split(",")]


class Ctx:
    def __init__(self, stage):
        self.stage = stage
        self.stage_path = f"{R}/stage/{stage}.json"
        self.cfg = json.load(open(self.stage_path))
        self.dir = f"{R}/{stage}"
        os.makedirs(self.dir, exist_ok=True)
        self.logp = f"{self.dir}/pipeline.log"
        self.ex = json.load(open(EXEC))
        self.allowed = allowed_gpus()
        for g in self.ex["train_gpus"] + self.ex["gen_gpus"]:
            if g not in self.allowed:
                raise SystemExit(f"exec_config gpu {g} not within inherited allowed set {self.allowed}")
        self.pdig = lock_protocol.verify(PROT)
        self.val_items, self.gt = inputs.load_items(MAN, AE.GT, self.cfg["val_ids"], "validation", exact=False)
        self.v_in = inputs.inputs_digest(self.val_items, self.gt)
        self.train_items = inputs.load_items(MAN, AE.GT, self.cfg["train_ids"], "train", exact=False)[0]
        self.t_in = inputs.inputs_digest(self.train_items, self.gt)
        self.v400_items, _ = inputs.load_items(MAN, AE.GT, AE.V400_IDS, "validation", exact=True)
        self.tr_ids = [i for i in self.gt if self.gt[i]["split"] == "train"]
        self.aed = sft_eval.area_edges(self.gt, self.tr_ids)
        self.bed = AE.box_edges_train(self.gt, self.tr_ids)
        self.milestones = sorted(self.cfg.get("milestone_epochs") or range(1, self.cfg["epochs"] + 1))
        self.spe = -(-len(self.train_items) // self.cfg["eff_batch"])

    def log(self, msg):
        line = f"[{time.strftime('%F %T')}] {msg}"
        print(line, flush=True)
        with open(self.logp, "a") as f:
            f.write(line + "\n")


def wait_gpu_free(ctx, gpu, need_mib):
    """실제 여유가 need_mib + 2GiB 이상일 때까지 기다린다 (lock 존재 여부와 무관)."""
    while True:
        rows, apps = gpu_snapshot({gpu})
        if rows and rows[0]["mem_total_mib"] - rows[0]["mem_used_mib"] >= need_mib + MARGIN_MIB:
            ctx.log(f"gpu {gpu} ok (need {need_mib}+{MARGIN_MIB} MiB): {rows[0]}")
            return
        ctx.log(f"waiting for gpu {gpu} (need {need_mib}+{MARGIN_MIB} MiB free): {rows} apps={apps}")
        time.sleep(120)


def run_dir(ctx, cond, lr):
    return f"{ctx.dir}/{cond}_lr{lrs(lr)}"


def expected_cfg_check(ctx, tc, cond, lr):
    """train_config가 이번 요청(stage 파일·loss·LR·부모·후보·입력·예정 update)과 일치하는지 검사한다. 불일치는 예외."""
    c = tc["config"]
    want = {"loss_mode": cond, "lr": lr, "seed": ctx.cfg["seed"], "n_train": len(ctx.train_items), "n_val": len(ctx.val_items), "eff_batch": ctx.cfg["eff_batch"],
            "total_updates": ctx.spe * ctx.cfg["epochs"], "steps_per_epoch": ctx.spe, "train_inputs_digest": ctx.t_in, "val_inputs_digest": ctx.v_in,
            "stage_config_sha256": migrate.file_sha(ctx.stage_path), "protocol_digest": ctx.pdig, "model_revision": AE_MODEL_REVISION(), "deterministic": False,
            "microbatch": ctx.ex["train_microbatch"], "branch_microbatch": ctx.ex["branch_microbatch"]}
    bad = {k: (c.get(k), v) for k, v in want.items() if c.get(k) != v}
    st = c.get("stage", {})
    for k in ("parent_adapter_digest", "parent_adapter_sha256", "cand_manifest_sha256", "train_ids", "val_ids", "epochs", "warmup_frac"):
        if st.get(k) != ctx.cfg.get(k):
            bad[f"stage.{k}"] = (st.get(k), ctx.cfg.get(k))
    if c.get("geo", {}).get("cand_manifest_sha256") != ctx.cfg["cand_manifest_sha256"]:
        bad["geo.cand_manifest_sha256"] = (c.get("geo", {}).get("cand_manifest_sha256"), ctx.cfg["cand_manifest_sha256"])
    if bad:
        raise RuntimeError(f"train_config differs from requested run: {bad}")


def AE_MODEL_REVISION():
    from . import generate
    return generate.MODEL_REVISION


def trained_ok(ctx, d, cond, lr):
    """done.json + milestone epoch 전체 검증(원시 응답 재계산) + 요청 일치. 파일이 없으면 False, 근거 불일치는 예외."""
    if not os.path.exists(os.path.join(d, "train_config.json")):
        return False
    tc = json.load(open(os.path.join(d, "train_config.json")))
    expected_cfg_check(ctx, tc, cond, lr)
    if not os.path.exists(os.path.join(d, "done.json")):
        return False
    dn = json.load(open(os.path.join(d, "done.json")))
    if dn.get("status") != "complete" or dn.get("steps") != ctx.spe * ctx.cfg["epochs"] or dn.get("loss_mode") != cond or dn.get("train_digest") != tc["train_digest"]:
        raise RuntimeError(f"{d}: done.json inconsistent with request: {dn}")
    for e in ctx.milestones:
        if not os.path.exists(os.path.join(d, f"epoch_{e:02d}", "val_metrics.json")):
            return False
        SEL.verify_epoch(d, e, tc, ctx.v_in, PROT, ctx.val_items, ctx.gt)
    return True


def train_cmd(ctx, cond, lr, d, gpu):
    return [sys.executable, "-m", "rsna_diag.adapt_geo", "--run-dir", d, "--stage-config", ctx.stage_path, "--loss", cond, "--lr", str(lr), "--protocol", PROT,
            "--microbatch", str(ctx.ex["train_microbatch"]), "--branch-microbatch", str(ctx.ex["branch_microbatch"]), "--workers", "3"]


def train_traj(ctx, gpu, cond, lr):
    d = run_dir(ctx, cond, lr)
    if trained_ok(ctx, d, cond, lr):
        ctx.log(f"{d}: verified complete")
        return
    wait_gpu_free(ctx, gpu, ctx.ex["train_peak_mib"][cond])
    ctx.log(f"train {cond} lr={lr} on gpu {gpu} -> {d}")
    t0 = time.time()
    rc = subprocess.run(train_cmd(ctx, cond, lr, d, gpu), env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)), stdout=open(f"{d}.log", "a"), stderr=subprocess.STDOUT).returncode
    ctx.log(f"train {cond} lr={lr} rc={rc} wall={time.time() - t0:.0f}s")
    if rc != 0 or not trained_ok(ctx, d, cond, lr):
        raise RuntimeError(f"{d}: training failed or not verified (rc={rc})")


# ---------- iter_013 C 재사용 (읽기 전용, 호환성 manifest) ----------
def c_compat(ctx, d, lr):
    """iter_013 C trajectory가 이 stage의 새 C와 같은 조건인지 검증하고 근거를 반환한다. 다르면 (False, 사유). 원본은 수정하지 않는다."""
    if ctx.stage != "explore":
        return False, "reuse only defined for the explore stage"
    tc = json.load(open(os.path.join(d, "train_config.json")))
    c, old = tc["config"], json.load(open(OLD_STAGE))
    st_now = ctx.cfg
    chk = {"loss_mode": (c["loss_mode"], "C"), "lr": (c["lr"], lr), "seed": (c["seed"], st_now["seed"]), "n_train": (c["n_train"], len(ctx.train_items)), "n_val": (c["n_val"], len(ctx.val_items)),
           "eff_batch": (c["eff_batch"], st_now["eff_batch"]), "microbatch": (c["microbatch"], ctx.ex["train_microbatch"]), "total_updates": (c["total_updates"], ctx.spe * st_now["epochs"]),
           "train_inputs_digest": (c["train_inputs_digest"], ctx.t_in), "val_inputs_digest": (c["val_inputs_digest"], ctx.v_in), "model_revision": (c["model_revision"], AE_MODEL_REVISION()),
           "lora_r/dropout/wd/clip/warmup": ((c["r"], c["dropout"], c["weight_decay"], c["grad_clip"], c["warmup_frac"]), (16, 0.05, 0.01, 1.0, 0.05)),
           "optimizer_init": (c["optimizer_init"], "fresh AdamW (parent optimizer not resumed)"), "dataloader_rng": (c["dataloader_rng"], "torch.Generator seeded seed*1000+epoch"),
           "parent_adapter_digest": (c["stage"]["parent_adapter_digest"], st_now["parent_adapter_digest"]), "parent_adapter_sha256": (c["stage"]["parent_adapter_sha256"], st_now["parent_adapter_sha256"]),
           "train_ids/val_ids/epochs": ((c["stage"]["train_ids"], c["stage"]["val_ids"], c["stage"]["epochs"]), (st_now["train_ids"], st_now["val_ids"], st_now["epochs"])),
           "old_stage_file_sha": (c["stage_config_sha256"], migrate.file_sha(OLD_STAGE)), "deterministic": (c["deterministic"], False)}
    bad = {k: v for k, v in chk.items() if v[0] != v[1]}
    if old["parent_adapter_digest"] != st_now["parent_adapter_digest"]:
        bad["old_stage_parent"] = "differs"
    return (not bad), (bad or {"checked": sorted(chk)})


def verify_gen_reused(ctx, gen_dir, items, adapter_dir, parent_dir):
    """iter_013 원시 응답(구 protocol digest)을 읽기 전용으로 검증한다: verify_gen의 부모 경로 + 구 completion 대조."""
    recs = eval_gate.verify_gen(gen_dir if os.path.isdir(gen_dir) else parent_dir, items, ["concise"], adapter_dir, PROT, parent_dir, OLD_PROT, require_completion=False)
    adg = eval_gate.adapter_digest(adapter_dir)
    old_dig = lock_protocol.digest_of(OLD_PROT)
    for dd in {parent_dir, gen_dir}:
        cp = os.path.join(dd, "completion.json")
        if os.path.isdir(dd) and os.path.exists(cp):
            c = json.load(open(cp))
            if c.get("adapter_digest") != adg or c.get("protocol_digest") != old_dig or c.get("n_missing") != 0 or c.get("n_duplicate") != 0:
                raise eval_gate.GateError(f"reused completion inconsistent: {cp}")
        elif dd == gen_dir and os.path.isdir(dd):
            raise eval_gate.GateError(f"reused completion missing: {cp}")
    return recs


def verify_epoch_reused(ctx, d, e, tc):
    ed = os.path.join(d, f"epoch_{e:02d}")
    m = json.load(open(os.path.join(ed, "val_metrics.json")))
    if m.get("epoch") != e or m.get("train_digest") != tc["train_digest"] or m.get("val_inputs_digest") != ctx.v_in:
        raise eval_gate.GateError(f"{d} epoch {e}: metrics not linked to run/inputs")
    if m.get("protocol_digest") != lock_protocol.digest_of(OLD_PROT) or m.get("adapter_digest") != eval_gate.adapter_digest(ed):
        raise eval_gate.GateError(f"{d} epoch {e}: protocol/adapter digest mismatch")
    recs = verify_gen_reused(ctx, os.path.join(ed, "val_gen"), ctx.val_items, ed, os.path.join(ed, "val_gen"))
    ids = [i["id"] for i in ctx.val_items]
    edges = sft_eval.area_edges(ctx.gt, ctx.tr_ids)
    rec = json.loads(json.dumps(sft_eval.summarize(sft_eval.parse_records(recs, ids, "concise", strict=True), ctx.gt, ids, edges)))
    bad = [k for k in rec if m.get(k) != rec[k]]
    if bad:
        raise eval_gate.GateError(f"{d} epoch {e}: recorded scores differ from recomputation: {bad[:5]}")
    return recs


# ---------- 평가 ----------
def v200_detail(ctx, d, e, reused=False):
    tc = json.load(open(os.path.join(d, "train_config.json")))
    if reused:
        recs = verify_epoch_reused(ctx, d, e, tc)
    else:
        SEL.verify_epoch(d, e, tc, ctx.v_in, PROT, ctx.val_items, ctx.gt)
        ed = os.path.join(d, f"epoch_{e:02d}")
        recs = eval_gate.verify_gen(os.path.join(ed, "val_gen"), ctx.val_items, ["concise"], ed, PROT)
    ids = [i["id"] for i in ctx.val_items]
    return detail14(ctx, AE.preds_of(recs, ids), ids), tc["config"]["steps_per_epoch"]


def iou_bins(preds, gt, ids):
    """개별 GT box의 best IoU(모든 예측 box 대상) 구간 분포 - one-to-one matching recall과는 다른 분석. 그리고 예측 개수 부족/일치/초과."""
    edges = [0.0, 0.1, 0.3, 0.5, 1.0000001]
    cnt = [0, 0, 0, 0]
    under = over = same = 0
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    for i in pos:
        pr = preds[i]
        pb = pr["boxes"] if pr["status"] in PA.VALID else []
        g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
        for b in g:
            best = max([M.iou(p, b) for p in pb], default=0.0)
            cnt[int(np.digitize(best, edges[1:-1]))] += 1
        under += len(pb) < len(g)
        over += len(pb) > len(g)
        same += len(pb) == len(g)
    n = sum(cnt)
    return {"gt_boxes": n, "best_iou<0.1": cnt[0], "0.1<=best<0.3": cnt[1], "0.3<=best<0.5": cnt[2], "best>=0.5": cnt[3],
            "pred_count_vs_gt": {"under": under, "same": same, "over": over}, "note": "best-IoU 구간(모든 예측 대상)과 one-to-one recall@thr는 다른 분석"}


def detail14(ctx, preds, ids):
    d = AE.detail(preds, ctx.gt, ids, ctx.aed, ctx.bed)
    d["best_iou_bins"] = iou_bins(preds, ctx.gt, ids)
    return d


def b0_details(ctx):
    recs = AE.b0_records(PROT, ctx.v400_items)
    ids400 = [i["id"] for i in ctx.v400_items]
    p400 = AE.preds_of(recs, ids400)
    v200 = [i["id"] for i in ctx.val_items]
    return p400, detail14(ctx, p400, ids400), detail14(ctx, {i: p400[i] for i in v200}, v200)


def gen_v400(ctx, gpu_list, d, e, reused=False):
    """epoch e adapter의 V400 완성. V200 val_gen을 부모로 재사용하고 나머지만 새로 생성한다. returns records."""
    ed = os.path.join(d, f"epoch_{e:02d}")
    out = os.path.join(d, f"v400_epoch{e:02d}")
    par = os.path.join(ed, "val_gen")
    if reused:
        return verify_gen_reused(ctx, out, ctx.v400_items, ed, par)
    try:
        return eval_gate.verify_gen(out, ctx.v400_items, ["concise"], ed, PROT, par, PROT)
    except (eval_gate.GateError, FileNotFoundError) as ex:
        ctx.log(f"{out}: not complete/verified ({str(ex)[:120]}) -> run_shards")
    for g in gpu_list:
        wait_gpu_free(ctx, g, ctx.ex["gen_peak_mib_per_worker"] * ctx.ex["gen_workers_per_gpu"])
    nw = ctx.ex["gen_workers_per_gpu"] * len(gpu_list)
    cmd = [sys.executable, "-m", "rsna_diag.run_shards", "--manifest", MAN, "--ids", AE.V400_IDS, "--out-dir", out, "--protocol", PROT, "--prompts", "concise",
           "--workers", str(nw), "--gpus", ",".join(map(str, gpu_list)), "--adapter", ed, "--parent-dir", par, "--parent-protocol", PROT]
    rc = subprocess.run(cmd, env=dict(os.environ, CUDA_VISIBLE_DEVICES=",".join(map(str, gpu_list))), stdout=open(f"{out}.log", "a"), stderr=subprocess.STDOUT).returncode
    ctx.log(f"gen {out} rc={rc}")
    if rc != 0:
        raise RuntimeError(f"{out}: run_shards failed rc={rc}")
    return eval_gate.verify_gen(out, ctx.v400_items, ["concise"], ed, PROT, par, PROT)


def select_traj(ctx, d, b0_v200, reused=False):
    """milestone별 V200 detail. guardrail 통과 최대 S_loc 선택(동률 이른 update). 통과 후보가 없으면 selected=null (final로 대체하지 않는다).
    v200_best_fallback = guardrail 무시 최고 S_loc milestone (geo_decide가 C/U 비교 기준으로만 쓰는 사전 규칙)."""
    cands, det = {}, {}
    spe = None
    for e in ctx.milestones:
        dt, spe = v200_detail(ctx, d, e, reused)
        cands[e * spe], det[e] = dt, dt
    sel_upd, table = AE.select_checkpoint(cands, b0_v200)
    best = max(cands, key=lambda k: (round(cands[k]["S_loc"], 12), -k))
    return {"update_to_epoch": {u: u // spe for u in cands}, "selected_update": sel_upd, "selected_epoch": (sel_upd // spe if sel_upd else None),
            "selection_eligible": sel_upd is not None, "fallback_best_update_ignoring_guardrail": best, "fallback_best_epoch": best // spe,
            "table": {str(u): t for u, t in table.items()}}, det, spe


def compare(preds_by, gt, ids, pairs):
    return {f"{a}-{b}": AE.paired_ci(preds_by[a], preds_by[b], gt, ids) for a, b in pairs if a in preds_by and b in preds_by}


def report(ctx, trajs, reuse_map):
    """trajs: [(cond, lr)] 모두 학습·검증 완료 상태. V400 완성 후 report.json (결정적 내용). reuse_map: {(cond, lr): iter_013 dir}."""
    ids400 = [i["id"] for i in ctx.v400_items]
    p400_b0, d400_b0, d200_b0 = b0_details(ctx)
    rep = {"stage": ctx.stage, "protocol_digest": ctx.pdig, "b0": {"v400": d400_b0, "v200": d200_b0}, "trajectories": {}, "reused": {f"{c}@{lrs(l)}": v for (c, l), v in reuse_map.items()}}
    preds = {"B0": p400_b0}
    for cond, lr in trajs:
        reused = (cond, lr) in reuse_map
        d = reuse_map.get((cond, lr)) or run_dir(ctx, cond, lr)
        name = f"{cond}@{lrs(lr)}"
        sel, det200, spe = select_traj(ctx, d, d200_b0, reused)
        E = ctx.cfg["epochs"]
        entry = {"lr": lr, "cond": cond, "steps_per_epoch": spe, "reused_from": d if reused else None, "selection_v200": sel,
                 "v200_detail_by_epoch": {str(e): det200[e] for e in det200}}
        want = {"final": E, "selected": sel["selected_epoch"], "v200_best_fallback": sel["fallback_best_epoch"]}
        for tag, e in want.items():
            if e is None:
                entry[tag] = None
                continue
            if tag == "v200_best_fallback" and cond == "G":
                continue  # G에는 대체를 허용하지 않는다
            if tag == "v200_best_fallback" and sel["selected_epoch"] is not None:
                continue  # 선택이 있으면 필요 없음
            recs = gen_v400(ctx, [int(g) for g in ctx.ex["gen_gpus"]], d, e, reused)
            p = AE.preds_of(recs, ids400)
            dt = detail14(ctx, p, ids400)
            entry[tag] = {"epoch": e, "update": e * spe, "v400": dt, "guardrail_v400": AE.guardrail(dt, d400_b0)}
            preds[f"{name}/{tag}"] = p
        entry["final_v400_reported_separately_from_selection"] = True
        rep["trajectories"][name] = entry
    rep["pairwise_v400_paired_bootstrap"] = {}
    for tag in ("selected", "final"):
        pb = {"B0": preds["B0"]}
        for n, p in preds.items():
            if n.endswith("/" + tag):
                pb[n.split("/")[0]] = p
        for n, p in preds.items():  # 선택 checkpoint가 없는 C/U는 사전 규칙의 V200 최고 checkpoint(대체)를 selected 비교에 쓴다
            if tag == "selected" and n.endswith("/v200_best_fallback"):
                pb.setdefault(n.split("/")[0], p)
        cs = sorted(k for k in pb if k != "B0")
        pairs = [(a, "B0") for a in cs] + [(a, b) for a in cs for b in cs if a != b and a.split("@")[0] in ("G", "U") and b.split("@")[0] in ("C", "U") and not (a[0] == b[0])]
        rep["pairwise_v400_paired_bootstrap"][tag] = compare(pb, ctx.gt, ids400, pairs)
    return rep, preds


def write_or_verify(path, obj):
    return SEL.write_or_verify(path, obj)


ABORT = threading.Event()
_B0 = {}
_LOCK = threading.Lock()


def run_lanes(lanes):
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


def b0_cached(ctx):
    with _LOCK:
        if "v" not in _B0:
            _B0["v"] = b0_details(ctx)
        return _B0["v"]


def prefetch(ctx, gpu, pending, dirs, reuse_map):
    """학습이 끝난 trajectory부터 claim해 final/selected(/C·U 대체) checkpoint의 V400 나머지 200요청을 자기 GPU에서 생성한다 (결과는 report()가 재검증)."""
    while True:
        with _LOCK:
            ready = [t for t in pending if os.path.exists(os.path.join(dirs[t], "done.json"))]
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
        d = dirs[claim]
        _, _, d200_b0 = b0_cached(ctx)
        sel, _, _ = select_traj(ctx, d, d200_b0)
        es = {ctx.cfg["epochs"], sel["selected_epoch"]}
        if sel["selected_epoch"] is None and claim[0] != "G":
            es.add(sel["fallback_best_epoch"])
        for e in sorted(x for x in es if x is not None):
            gen_v400(ctx, [gpu], d, e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--trajs", required=True, help="예: G:2e-5,U:2e-5,C:2e-5 (lane 배정: 순서대로 train_gpus에 번갈아)")
    ap.add_argument("--reuse-c", default=None, help="iter_013 C trajectory 디렉터리 (호환성 검증 통과 시 읽기 전용 재사용, 아니면 새로 학습)")
    ap.add_argument("--report-name", default="report")
    a = ap.parse_args()
    ctx = Ctx(a.stage)
    lk, own, _ = queue_lock.try_lock(os.path.join(os.path.realpath(ctx.dir), "pipeline.lock"), queue_lock.my_info(role="geo_pipeline"))
    if lk is None:
        sys.exit(f"another pipeline owns {ctx.dir}: {own}")
    try:
        trajs = [(c, float(l)) for c, l in (x.split(":") for x in a.trajs.split(","))]
        reuse_map = {}
        if a.reuse_c:
            lr_c = [l for c, l in trajs if c == "C"][0]
            okc, why = c_compat(ctx, a.reuse_c, lr_c)
            comp = {"source": a.reuse_c, "compatible": okc, "detail": why, "source_protocol": OLD_PROT, "source_protocol_digest": lock_protocol.digest_of(OLD_PROT),
                    "new_protocol_digest": ctx.pdig, "note": "읽기 전용 재사용. 원시 응답은 report에서 구 protocol digest(parent 경로)로 재검증·재계산한다."}
            SEL.write_or_verify(f"{ctx.dir}/compat_C.json", json.loads(json.dumps(comp, default=str)))
            ctx.log(f"C reuse compat={okc}: {str(why)[:300]}")
            if okc:
                reuse_map[("C", lr_c)] = a.reuse_c
        gpus = [int(g) for g in ctx.ex["train_gpus"]]
        todo = [(c, l) for c, l in trajs if (c, l) not in reuse_map]
        lanes = {g: [] for g in gpus}
        dirs = {(c, l): (reuse_map.get((c, l)) or run_dir(ctx, c, l)) for c, l in trajs}
        pending = [t for t in dirs if t not in reuse_map]
        # 재사용 trajectory의 V400 검증은 report에서 수행. 학습 lane 배정은 순서대로
        for k, (c, l) in enumerate(todo):
            g = gpus[k % len(gpus)]
            lanes[g].append(lambda g=g, c=c, l=l: train_traj(ctx, g, c, l))
        for g in gpus:
            lanes[g].append(lambda g=g: prefetch(ctx, g, pending, dirs, reuse_map))
        t0 = time.time()
        run_lanes(lanes)
        ctx.log(f"all trainings verified; wall={time.time() - t0:.0f}s")
        rep, preds = report(ctx, trajs, reuse_map)
        ctx.log(f"report {write_or_verify(f'{ctx.dir}/{a.report_name}.json', json.loads(json.dumps(rep)))}")
        ctx.log("STAGE COMPLETE")
    finally:
        lk.release()


if __name__ == "__main__":
    main()
