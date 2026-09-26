"""iter_014 실행 경로 fixture (CPU/파일): geo_pipeline의 완료 판정·재사용·GPU 허용 집합·메모리 대기 검사. 사용: python test_rsna_iter014_pipeline.py PROTOCOL
PROTOCOL은 sanity/explore stage 파일을 잠근 protocol (본실험 전 검사는 pilot3, 본실험 protocol이 만들어진 뒤에는 main).
결과: results/iter_014/tests/fixtures_iter014_pipeline.json"""
import copy
import json
import os
import sys

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from rsna_diag import geo_pipeline as GP

OUT = "results/iter_014/tests/fixtures_iter014_pipeline.json"
res = []


def ok(name, cond, detail=""):
    res.append({"name": name, "pass": bool(cond), "detail": str(detail)[:400]})
    print(("PASS " if cond else "FAIL ") + name, str(detail)[:200], flush=True)


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return True, repr(e)[:150]
    return False, "no exception"


def main():
    GP.PROT = sys.argv[1]
    ctx = GP.Ctx("sanity")
    # --- 완료 판정: 실제 재개 검사 run의 train_config를 기반으로, 요청과 일치하는 경우만 통과
    tc = json.load(open("results/iter_014/tests/resume2/uninterrupted/train_config.json"))
    tc["config"]["deterministic"] = False  # 검사 run은 결정적 kernel이었다 (양성 대조용으로만 되돌림)
    ctx_lr = 2e-5
    base = copy.deepcopy(tc)
    base["config"]["microbatch"], base["config"]["branch_microbatch"] = ctx.ex["train_microbatch"], ctx.ex["branch_microbatch"]
    base["config"]["protocol_digest"] = ctx.pdig
    good = raises(lambda: GP.expected_cfg_check(ctx, base, "G", ctx_lr))
    ok("positive control: matching train_config accepted", not good[0], good[1])
    muts = {"loss_mode": lambda c: c.__setitem__("loss_mode", "U"), "lr": lambda c: c.__setitem__("lr", 5e-5), "seed": lambda c: c.__setitem__("seed", 29),
            "stage_config_sha256": lambda c: c.__setitem__("stage_config_sha256", "0" * 64), "protocol_digest": lambda c: c.__setitem__("protocol_digest", "0" * 64),
            "train_inputs_digest": lambda c: c.__setitem__("train_inputs_digest", "0" * 64), "val_inputs_digest": lambda c: c.__setitem__("val_inputs_digest", "0" * 64),
            "total_updates": lambda c: c.__setitem__("total_updates", 999), "geo.cand_manifest_sha256": lambda c: c["geo"].__setitem__("cand_manifest_sha256", "0" * 64),
            "stage.parent_adapter_digest": lambda c: c["stage"].__setitem__("parent_adapter_digest", "0" * 64), "stage.epochs": lambda c: c["stage"].__setitem__("epochs", 9),
            "stage.train_ids": lambda c: c["stage"].__setitem__("train_ids", "x.json"), "microbatch": lambda c: c.__setitem__("microbatch", 4)}
    for k, f in muts.items():
        t = copy.deepcopy(base)
        f(t["config"])
        r = raises(lambda: GP.expected_cfg_check(ctx, t, "G", ctx_lr), RuntimeError)
        ok(f"negative: {k} mismatch is refused (not accepted as completion)", r[0], r[1])
    # --- done.json 검증 (임시 run dir)
    d = "results/iter_014/tests/pipeline_tmp/run"
    os.makedirs(d, exist_ok=True)
    json.dump(base, open(os.path.join(d, "train_config.json"), "w"))
    ok("no done.json -> trained_ok False (not complete)", GP.trained_ok(ctx, d, "G", ctx_lr) is False)
    json.dump({"status": "complete", "steps": 3, "loss_mode": "G", "train_digest": base["train_digest"]}, open(os.path.join(d, "done.json"), "w"))
    r = raises(lambda: GP.trained_ok(ctx, d, "G", ctx_lr), RuntimeError)
    ok("negative: done.json with wrong step count refused", r[0], r[1])
    json.dump({"status": "complete", "steps": ctx.spe * ctx.cfg["epochs"], "loss_mode": "U", "train_digest": base["train_digest"]}, open(os.path.join(d, "done.json"), "w"))
    r = raises(lambda: GP.trained_ok(ctx, d, "G", ctx_lr), RuntimeError)
    ok("negative: done.json for a different loss refused", r[0], r[1])
    # --- 부족한 응답: 검증 epoch의 val_metrics 없음 -> False (complete로 인정 안 함)
    json.dump({"status": "complete", "steps": ctx.spe * ctx.cfg["epochs"], "loss_mode": "G", "train_digest": base["train_digest"]}, open(os.path.join(d, "done.json"), "w"))
    ok("missing milestone val_metrics -> not complete", GP.trained_ok(ctx, d, "G", ctx_lr) is False)
    # --- GPU 허용 집합
    saved = os.environ["CUDA_VISIBLE_DEVICES"]
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    r = raises(lambda: GP.Ctx("sanity"), SystemExit)
    os.environ["CUDA_VISIBLE_DEVICES"] = saved
    ok("exec_config GPU outside inherited allowed set -> refused", r[0], r[1])
    # --- 메모리 대기: lock 존재와 무관하게 실제 여유를 본다
    calls = []
    orig_snap, orig_sleep = GP.gpu_snapshot, GP.time.sleep
    GP.gpu_snapshot = lambda s: ([{"index": 0, "mem_total_mib": 24576, "mem_used_mib": 20000, "util": 0}], [])

    class Stop(Exception):
        pass

    def sl(_):
        calls.append(1)
        raise Stop()
    GP.time.sleep = sl
    r = raises(lambda: GP.wait_gpu_free(ctx, 0, 13000), Stop)
    GP.gpu_snapshot = lambda s: ([{"index": 0, "mem_total_mib": 24576, "mem_used_mib": 5000, "util": 0}], [])
    ok_free = raises(lambda: GP.wait_gpu_free(ctx, 0, 13000), Stop)
    GP.gpu_snapshot, GP.time.sleep = orig_snap, orig_sleep
    ok("wait_gpu_free waits when free (4.5GB) < need 13GB+2GiB, returns when free 19.5GB", r[0] and not ok_free[0], (r, ok_free))
    # --- iter_013 C 재사용 호환성 (실제 파일)
    cx = GP.Ctx("explore")
    okc, why = GP.c_compat(cx, "results/iter_013/explore/C_lr2e-05", 2e-5)
    ok("iter_013 C trajectory compatible with iter_014 explore C (inputs/config/parent/order)", okc, why)
    okc2, why2 = GP.c_compat(cx, "results/iter_013/explore/C_lr2e-05", 5e-5)
    ok("negative: C reuse refused when LR differs", not okc2, why2)
    okd, whyd = GP.c_compat(cx, "results/iter_013/explore/D_lr2e-05", 2e-5)
    ok("negative: iter_013 D trajectory refused as C reuse", not okd, str(whyd)[:200])
    # --- 재사용 원시 응답 검증과 집계 정정 (V200, epoch 1..3)
    d13 = "results/iter_013/explore/C_lr2e-05"
    rep13 = json.load(open("results/iter_013/explore/report.json"))
    old = rep13["trajectories"]["C@2e-05"]["v200_detail_by_epoch"]
    _, _, d200_b0 = GP.b0_details(cx)
    sel, det, spe = GP.select_traj(cx, d13, d200_b0, reused=True)
    same_main = all(abs(det[e]["S_loc"] - old[str(e)]["S_loc"]) < 1e-12 and abs(det[e]["f1@0.3"] - old[str(e)]["f1@0.3"]) < 1e-12 for e in (1, 2, 3))
    ok("reused C V200 raw responses re-verified; S_loc/F1@0.3 unchanged vs iter_013 report (main metric invariant)", same_main, {e: det[e]["S_loc"] for e in det})
    ok("multi fix visible: iter_013 V200 multi n vs corrected", det[3]["by_n_gt_S_loc"]["multi"]["n"] >= old["3"]["by_n_gt_S_loc"]["multi"]["n"] and det[3]["by_n_gt_S_loc"]["ge3"]["n"] > 0,
       {"old_multi_n": old["3"]["by_n_gt_S_loc"]["multi"]["n"], "new_multi_n": det[3]["by_n_gt_S_loc"]["multi"]["n"], "new_ge3_n": det[3]["by_n_gt_S_loc"]["ge3"]["n"]})
    ok("C selection from reused V200 equals iter_013 selected epoch (1) and selection_eligible", sel["selected_epoch"] == 1 and sel["selection_eligible"], (sel["selected_epoch"], sel["selection_eligible"]))
    recs = GP.gen_v400(cx, [0], d13, 1, reused=True)
    ok("reused V400 epoch1 (V200 parent + 200 new) verified: 400 requests", len(recs) == 400, len(recs))
    recs3 = GP.gen_v400(cx, [0], d13, 3, reused=True)
    ok("reused V400 epoch3 verified: 400 requests", len(recs3) == 400, len(recs3))
    # 결정: 저장된 iter_013 C 응답의 V400 selected S_loc가 iter_013 report와 같다
    p = GP.AE.preds_of(recs, [i["id"] for i in cx.v400_items])
    dt = GP.detail14(cx, p, [i["id"] for i in cx.v400_items])
    old400 = rep13["trajectories"]["C@2e-05"]["selected"]["v400"]
    ok("reused C selected V400 S_loc equals iter_013 report", abs(dt["S_loc"] - old400["S_loc"]) < 1e-12, (dt["S_loc"], old400["S_loc"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"protocol": sys.argv[1], "n": len(res), "n_pass": sum(x["pass"] for x in res), "results": res}, open(OUT, "w"), indent=1)
    print(f"{sum(x['pass'] for x in res)}/{len(res)} PASS")
    return 0 if all(x["pass"] for x in res) else 1


if __name__ == "__main__":
    sys.exit(main())
