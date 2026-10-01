"""iter_045 비교 평가 (CPU only, 기본 python). 순서: lock -> report.

  python mg45_report.py lock   --out results/iter_045/eval/eval_lock.json      (출력 평가 전에 평가 소스·입력·decision을 digest로 잠금)
  python mg45_report.py report --lock results/iter_045/eval/eval_lock.json --out results/iter_045/eval/report.json

사전 고정 규칙(plan.md Evaluation; 결과를 본 뒤 변경하지 않는다):
  주지표 문장 F1@0.3 (환자 안 평균 -> 환자 평균), 원본 정규화 xyxy에서 최대 cardinality 일대일 matching.
  정확도·FP 차이: 환자 paired bootstrap 10,000회 seed 4401, 97.5% CI.
  비용: 6 paired block, block별 MG/C 비율의 log 평균 +- t(5) 95% CI.
  모듈형 대안 지지: MG-C F1@0.3 CI하한>=-0.03 & F1@0.5 CI하한>=-0.03 & FP차 CI상한<=0.10 & device ratio(MG/C) CI상한<=0.50
                    & throughput ratio(MG/C) CI하한>=2.0 & p95 latency ratio(MG/C) CI상한<=1.20.
  C 잔여 이점 지지: C-MG F1@0.3 점차>=0.05 & CI하한>0 & F1@0.5 CI하한>=-0.03 & FP차(C-MG) CI상한<=0.10 &
                    C/MG device ratio CI상한<=2.0 & C/MG p95 latency ratio CI상한<=2.0 (+ 두 checkpoint 정상 실행).
  그 외 과학적 불확정 -> track 보류. 실행/provenance 결함이 있으면 execution_failed.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

import mg45_eval as E
import pg39_spec as S39
import pg43_eval as PE
import pg43_run as R
from rsna_diag import geometry, parse

NBOOT = 10000
SEED = 4401
MAN = E.MAN
SEL = "results/iter_045/decisions/D24_select.json"
V96_DIRS = {"P": "results/iter_045/mg/V96_P_w2b4", "MS": "results/iter_045/mg/V96_MS_w2b4"}
C_GEN = "results/iter_040/gen/C"
C_REQ = "results/iter_040/requests/requests_V96.jsonl"
C_PROTO = "results/iter_040/protocol/protocol_C.json"
C_ADAPTER_DIGEST = "419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8"
C_COMMIT = "18fdae2eec4f4ab3605845fdaeafd1959d9d725f"  # iter_040 코드 보관 commit
C_STORED = {"f1_03": 0.5779513888888889, "f1_05": 0.2911458333333333}
TIMING = "results/iter_045/timing/main"
BLOCK_ATTEMPT = {1: 2, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}  # block1 attempt1은 C 중복 claim 결함으로 보존만 한다
LOCK_FILES = ["mg45_report.py", "mg45_eval.py", "mg45_verify.py", "mg45_ccheck.py", "mg45_mg.py", "mg45_worker.py", "mg45_launch.py", "mg45_ctime.py",
              "mg45_timing.py", "pg39_spec.py", "pg43_eval.py", "pg43_run.py", "pg43_retrieval.py", "rsna_diag/metrics.py", "rsna_diag/parse.py",
              "rsna_diag/geometry.py", "rsna_diag/__init__.py", "rsna_diag/generate.py", "rsna_diag/prompts.py", "rsna_diag/lora.py", "rsna_diag/queue_lock.py",
              MAN, SEL, C_REQ, C_PROTO, "results/iter_045/decisions/D24_P_cfg_compare.json", "results/iter_045/d8/d8_check.json",
              "results/iter_045/external/code_manifest.json", "results/iter_045/external/weights/weights_manifest.json",
              "results/iter_045/external/text_encoder_manifest.json"]


def fsha(p):
    return E.file_sha(p)


# ---------------- lock ----------------
def cmd_lock(a):
    if os.path.exists(a.out):
        sys.exit("lock exists")
    lock = {"files": {f: fsha(f) for f in LOCK_FILES},
            "mg_v96_completions": {k: fsha(d + "/completion.json") for k, d in V96_DIRS.items()},
            "c_completion": fsha(C_GEN + "/completion.json"),
            "timing_completions": {f"{s}{k}": fsha(f"{TIMING}/block{k}_a{BLOCK_ATTEMPT[k]}_{s}/completion.json") for k in range(1, 7) for s in ("C", "MG")},
            "locked_at": time.time(), "bootstrap": {"B": NBOOT, "seed": SEED},
            "note": "V96 출력 채점 전에 작성. 이후 평가 소스/입력이 달라지면 report가 중단한다."}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(lock, open(a.out, "x"), indent=1)
    print("locked", len(lock["files"]), "files")


def check_lock(path):
    lock = json.load(open(path))
    bad = [f for f, h in lock["files"].items() if fsha(f) != h]
    if bad:
        raise E.EvalError(f"locked eval source/input changed: {bad}")
    for k, d in V96_DIRS.items():
        if fsha(d + "/completion.json") != lock["mg_v96_completions"][k]:
            raise E.EvalError("mg completion changed")
    if fsha(C_GEN + "/completion.json") != lock["c_completion"]:
        raise E.EvalError("C completion changed")
    for k in range(1, 7):
        for s in ("C", "MG"):
            if fsha(f"{TIMING}/block{k}_a{BLOCK_ATTEMPT[k]}_{s}/completion.json") != lock["timing_completions"][f"{s}{k}"]:
                raise E.EvalError("timing completion changed")
    return lock


# ---------------- C import 검증 (pg43_eval.verify_import 보완판: protocol -> completion -> record config -> adapter -> 현재 영상/요청/GT manifest) ----------------
def git_show_sha(commit, path):
    p = subprocess.run(["git", "show", f"{commit}:{path}"], capture_output=True)
    return hashlib.sha256(p.stdout).hexdigest() if p.returncode == 0 else None


def verify_c_import(man_v96):
    d = C_GEN
    comp = json.load(open(d + "/completion.json"))
    if any(c != 0 for c in comp["exit_codes"]):
        raise R.RunError("C: nonzero exit codes")
    proto = json.load(open(C_PROTO))
    pdig = R.sha_bytes(R.canon(proto).encode())
    if comp["protocol_digest"] != pdig:
        raise R.RunError("C: completion protocol_digest != digest(원본 protocol 파일)")
    if R.file_sha(C_REQ) != proto["requests_sha256"]:
        raise R.RunError("C: requests != protocol lock")
    ad = proto["adapter"]
    if ad["digest"] != C_ADAPTER_DIGEST or R.file_sha(os.path.join(ad["path"], "adapter.pt")) != ad["file_sha256"]:
        raise R.RunError("C: adapter digest/file mismatch")
    # 원본 protocol의 코드 hash는 보관 commit의 실제 파일과 대조 (이전 protocol의 source 검사)
    code_vs_git = {f: (git_show_sha(C_COMMIT, f) == h) for f, h in proto["code"].items()}
    rows = {}
    for l in open(C_REQ):
        if l.strip():
            r = json.loads(l)
            rows[r["request_id"]] = r
    files = sorted(glob.glob(d + "/gen_worker*.jsonl"))
    if sorted(os.path.basename(f) for f in files) != sorted(comp["worker_file_sha256"]):
        raise R.RunError("C: worker file set != completion")
    recs = []
    for f in files:
        if R.file_sha(f) != comp["worker_file_sha256"][os.path.basename(f)]:
            raise R.RunError("C: worker file changed after completion")
        recs += R.read_records(f)
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(rows) or len(ids) != comp["n_requests"]:
        raise R.RunError("C: request set mismatch")
    out = {}
    for r in recs:
        row = rows[r["request_id"]]
        if r["record_digest"] != R.record_digest(r) or r["row_digest"] != R.row_digest(row):
            raise R.RunError("C: record/row digest mismatch")
        if r["protocol_digest"] != pdig or r["config_digest"] != proto["generation_config_digest"] or r["adapter_digest"] != C_ADAPTER_DIGEST:
            raise R.RunError("C: record protocol/config/adapter digest mismatch")
        e = man_v96[r["patient"]]
        t = r["targets"][0]
        if row["prompt_sha256"] != R.sha_bytes(S39.prompt_I_short(e["sentences"][t], t).encode()) or r["prompt_sha256"] != row["prompt_sha256"] \
                or R.sha_bytes(row["prompt"].encode()) != row["prompt_sha256"]:
            raise R.RunError("C: prompt != manifest sentence")
        if r["input_pixel_sha256"] != e["input_pixel_sha256"] or row["image"] != e["image"] or R.file_sha(e["image"]) != e["image_file_sha256"]:
            raise R.RunError("C: input image != manifest/current file")
        if R.G.load_image(e["image"])[2] != e["input_pixel_sha256"]:
            raise R.RunError("C: current pixel hash mismatch")
        if tuple(r["pad_affine_top_left_side"]) != tuple(geometry.pad_offsets(e["h"], e["w"])):
            raise R.RunError("C: pad affine mismatch")
        out[(r["patient"], t)] = r
    if len(out) != 192:
        raise R.RunError(f"C: expected 192, got {len(out)}")
    return out, {"protocol_digest": pdig, "code_hash_equals_git_blob_at_iter040_commit": code_vs_git, "adapter_digest": ad["digest"]}


def c_scores(recs, ents):
    """C: canvas -> 원본 정규화 xyxy 변환 후 채점. canvas F1과의 불변성도 검사한다."""
    out, st, inv = {}, {}, {"checked": 0, "mismatch": 0}
    for (p, t), r in recs.items():
        e = ents[p]
        pr = S39.parse_ids(r["suffix_text_raw"], r["ended_eos"], {t})
        valid = pr["status"] in parse.VALID
        boxes = [PE.canvas_to_norm_xyxy(b, r["pad_affine_top_left_side"], e["h"], e["w"]) for b in pr["groups"][t]] if valid else []
        sc = E.score(boxes, e["gt_boxes_xyxy_norm"][t])
        cc = S39.score_request(pr["status"], {t: pr["groups"][t]}, [t], {t: e["gt_canvas_yxyx"][t]})[t]
        inv["checked"] += 1
        inv["mismatch"] += int(abs(cc["f1_03"] - sc["f1_03"]) > 1e-9 or abs(cc["f1_05"] - sc["f1_05"]) > 1e-9)
        sc["valid"] = valid
        out[(p, t)] = sc
        st[(p, t)] = pr["status"]
    return out, st, inv


# ---------------- 통계 ----------------
def boot_idx(n, seed=SEED, B=NBOOT):
    return np.random.default_rng(seed).integers(0, n, size=(B, n), dtype=np.int32)


def pat_arr(sc, pids, key):
    return np.array([np.mean([sc[(p, t)][key] for t in ("qA", "qB")]) for p in pids])


def ci(v, level, idx):
    v = np.asarray(v, float)
    m = v[idx].mean(axis=1)
    al = (1 - level) / 2 * 100
    return {"mean": float(v.mean()), "lo": float(np.percentile(m, al)), "hi": float(np.percentile(m, 100 - al)), "level": level}


T5_975 = 2.5705818366147395  # scipy.stats.t.ppf(0.975, 5)


def ratio_ci(x, y):
    """block별 비율 x/y의 log 평균 +- t(5) 95% CI (원시 비율도 반환). x,y: 길이 6."""
    r = np.asarray(x, float) / np.asarray(y, float)
    lr = np.log(r)
    n = len(lr)
    se = lr.std(ddof=1) / math.sqrt(n)
    m = lr.mean()
    t = T5_975 if n == 6 else None
    if t is None:
        raise ValueError("t critical value fixed for n=6")
    return {"raw_ratios": r.tolist(), "geo_mean": float(math.exp(m)), "ci95_lo": float(math.exp(m - t * se)), "ci95_hi": float(math.exp(m + t * se)),
            "raw_min": float(r.min()), "raw_max": float(r.max()), "n_blocks": n}


# ---------------- timing 분석 ----------------
def timing_block(k):
    att = BLOCK_ATTEMPT[k]
    c_dir, m_dir = f"{TIMING}/block{k}_a{att}_C", f"{TIMING}/block{k}_a{att}_MG"
    cc = json.load(open(c_dir + "/completion.json"))
    mc = json.load(open(m_dir + "/completion.json"))
    # C: 환자 단위 record
    crecs = []
    for f in sorted(glob.glob(c_dir + "/ctime_worker*.jsonl")):
        if cc["worker_file_sha256"][os.path.basename(f)] != fsha(f):
            raise E.EvalError("C timing worker file changed")
        crecs += [json.loads(l) for l in open(f, "rb").read().split(b"\n")[:-1] if l.strip()]
    cmap = {int(w): g for w, g in cc["mapping"].items()}
    c_by_p = {}
    for r in crecs:
        c_by_p.setdefault(r["patient"], []).append(r)
    c_lat = {p: v[0]["t_patient_done"] - v[0]["t_patient_dispatch"] for p, v in c_by_p.items()}
    c_iv = {}
    for p, v in c_by_p.items():
        c_iv.setdefault(cmap[v[0]["worker"]], []).append((v[0]["t_patient_dispatch"], v[0]["t_patient_done"]))
    # MG: 환자 latency = 두 문장 중 최대 t_done - 최소 t_dispatch
    man = json.load(open(MAN))
    mrecs, mcomp, _ = E.verify_mg_dir(m_dir, "V96", json.load(open(SEL))["selected"]["ckpt"], man)
    mmap = {int(w): g for w, g in mc["mapping"].items()}
    m_by_p = {}
    for (p, t), r in mrecs.items():
        m_by_p.setdefault(p, []).append(r)
    m_lat = {p: max(x["t_done"] for x in v) - min(x["t_dispatch"] for x in v) for p, v in m_by_p.items()}
    m_iv = {}
    for p, v in m_by_p.items():
        m_iv.setdefault(mmap[v[0]["worker"]], []).append((min(x["t_dispatch"] for x in v), max(x["t_done"] for x in v)))

    def span(iv):
        return sum(max(e for _, e in v) - min(s for s, _ in v) for v in iv.values())

    def union(iv):
        return sum(PE_union(v) for v in iv.values())

    def lat_stats(d):
        v = np.array(list(d.values()))
        return {"mean": float(v.mean()), "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95)), "n": int(len(v))}
    out = {}
    for name, comp, iv, lat in (("C", cc, c_iv, c_lat), ("MG", mc, m_iv, m_lat)):
        out[name] = {"workload_wall_s": comp["workload_wall_s"], "patients_per_min": 96 / comp["workload_wall_s"] * 60,
                     "device_seconds_span": span(iv), "device_seconds_union": union(iv), "latency_s": lat_stats(lat),
                     "peak_alloc_gb_max": comp["peak_alloc_gb_max"], "workers": comp["workers"],
                     "launcher_wall_s_incl_loading": comp["launcher_wall_s_incl_loading"], "mapping": comp["mapping"]}
    out["C"]["cold_load_s_max"] = max(cc["cold_load_s"].values())
    out["MG_n_records"] = len(mrecs)
    return out, c_dir, m_dir


def PE_union(iv):
    tot, cs, ce = 0.0, None, None
    for s_, e_ in sorted(iv):
        if ce is None or s_ > ce:
            if ce is not None:
                tot += ce - cs
            cs, ce = s_, e_
        else:
            ce = max(ce, e_)
    return tot + ((ce - cs) if ce is not None else 0.0)


def mg_meta_cold(dirpath):
    ms = [json.load(open(p)) for p in glob.glob(dirpath + "/worker*.meta.*.json")]
    return max(m["load_s"] for m in ms), max(m["peak_reserved_gb"] for m in ms)


def cmd_report(a):
    if os.path.exists(a.out):
        sys.exit("output exists")
    t_start = time.time()
    lock = check_lock(a.lock)
    man = json.load(open(MAN))
    sel = json.load(open(SEL))
    ents = {e["PatientID"]: e for e in man["V96"]}
    pids = sorted(ents)
    # ---- C ----
    crecs, cprov = verify_c_import(ents)
    c_sc, c_status, c_inv = c_scores(crecs, ents)
    # ---- MG ----
    mg = {}
    for ck, d in V96_DIRS.items():
        recs, comp, proto = E.verify_mg_dir(d, "V96", ck, man)
        mg[ck] = {"recs": recs, "comp": comp}
    P_thr, MS_thr = sel["ckpts"]["P"]["selected_threshold"], sel["ckpts"]["MS"]["selected_threshold"]
    sysdefs = {"C": c_sc,
               "MG-P@sel": E.mg_scores(mg["P"]["recs"], ents, P_thr), "MG-MS@sel": E.mg_scores(mg["MS"]["recs"], ents, MS_thr),
               "MG-P@0.8": E.mg_scores(mg["P"]["recs"], ents, 0.8), "MG-MS@0.8": E.mg_scores(mg["MS"]["recs"], ents, 0.8)}
    selname = f"MG-{sel['selected']['ckpt']}@sel"
    idx = boot_idx(len(pids))
    prim = {}
    for s, sc in sysdefs.items():
        base = E.summarize(sc, pids)
        base["f1_03_ci95"] = ci(pat_arr(sc, pids, "f1_03"), 0.95, idx)
        base["f1_05_ci95"] = ci(pat_arr(sc, pids, "f1_05"), 0.95, idx)
        base["n_sentences"] = len(sc)
        prim[s] = base
    prim["C"]["valid_rate"] = float(np.mean([v in parse.VALID for v in c_status.values()]))
    prim["C"]["eos_rate"] = float(np.mean([r["ended_eos"] for r in crecs.values()]))
    prim["C"]["status_counts"] = {k: sum(v == k for v in c_status.values()) for k in sorted(set(c_status.values()))}
    # C 재현
    repro = {"C_f1_03": prim["C"]["f1_03"], "C_f1_05": prim["C"]["f1_05"], "stored": C_STORED,
             "abs_diff_03": abs(prim["C"]["f1_03"] - C_STORED["f1_03"]), "abs_diff_05": abs(prim["C"]["f1_05"] - C_STORED["f1_05"]),
             "canvas_vs_original_invariance": c_inv}
    # ---- 차이 (paired) ----
    def diff(x, y, key, level):
        return ci(pat_arr(sysdefs[x], pids, key) - pat_arr(sysdefs[y], pids, key), level, idx)
    cmp = {}
    for x, y in ((selname, "C"), ("C", selname), ("MG-P@sel", "C"), ("MG-MS@sel", "C"), ("MG-P@0.8", "C"), ("MG-MS@0.8", "C"), ("MG-P@sel", "MG-MS@sel")):
        k = f"{x}_minus_{y}"
        if k in cmp:
            continue
        cmp[k] = {"f1_03": diff(x, y, "f1_03", 0.975), "f1_05": diff(x, y, "f1_05", 0.975), "fp_03": diff(x, y, "fp_03", 0.975), "recall_03": diff(x, y, "recall_03", 0.975)}
    # ---- 층별 ----
    def area_frac(b):
        return max(0, (b[2] - b[0])) * max(0, (b[3] - b[1])) / 1e6
    max_area = {(p, t): max(area_frac(b) for b in ents[p]["gt_canvas_yxyx"][t]) for p in pids for t in ("qA", "qB")}
    med = float(np.median(list(max_area.values())))
    strat = {"multi_box": lambda p, t: len(ents[p]["gt_canvas_yxyx"][t]) > 1, "single_box": lambda p, t: len(ents[p]["gt_canvas_yxyx"][t]) == 1,
             "small_box(max GT area<median)": lambda p, t: max_area[(p, t)] < med, "large_box": lambda p, t: max_area[(p, t)] >= med,
             "share_group_patient": lambda p, t: ents[p]["stratum"].startswith("share1"), "non_share_patient": lambda p, t: ents[p]["stratum"].startswith("share0")}
    strata = {}
    for nm, fn in strat.items():
        ks = [(p, t) for p in pids for t in ("qA", "qB") if fn(p, t)]
        strata[nm] = {"n_sentences": len(ks), "systems": {s: {"f1_03": float(np.mean([sc[k]["f1_03"] for k in ks])), "recall_03": float(np.mean([sc[k]["recall_03"] for k in ks])),
                                                          "fp_per_sentence": float(np.mean([sc[k]["fp_03"] for k in ks])), "empty_rate": float(np.mean([bool(sc[k]["empty"]) for k in ks])),
                                                          "missed_gt_per_sentence": float(np.mean([sc[k]["n_gt"] * (1 - sc[k]["recall_03"]) for k in ks]))}
                                                      for s, sc in sysdefs.items()}}
    # ---- timing ----
    blocks = {}
    for k in range(1, 7):
        blocks[k], c_dir, m_dir = timing_block(k)
    bl = [blocks[k] for k in range(1, 7)]
    cost = {"blocks": {str(k): blocks[k] for k in blocks}, "lead_order": {str(k): ("C" if k % 2 == 1 else "MG") for k in range(1, 7)},
            "attempts": BLOCK_ATTEMPT, "excluded_attempts": {"block1_a1": "C 환자 claim 중복(flock 해제 경쟁)으로 기술 실패; 원본 보존, paired block 전체 재측정"}}
    for nm in ("device_seconds_span", "device_seconds_union"):
        cost[f"MG_over_C_{nm}"] = ratio_ci([b["MG"][nm] for b in bl], [b["C"][nm] for b in bl])
    cost["MG_over_C_throughput"] = ratio_ci([b["MG"]["patients_per_min"] for b in bl], [b["C"]["patients_per_min"] for b in bl])
    cost["MG_over_C_p95_latency"] = ratio_ci([b["MG"]["latency_s"]["p95"] for b in bl], [b["C"]["latency_s"]["p95"] for b in bl])
    cost["MG_over_C_mean_latency"] = ratio_ci([b["MG"]["latency_s"]["mean"] for b in bl], [b["C"]["latency_s"]["mean"] for b in bl])
    cost["MG_over_C_workload_wall"] = ratio_ci([b["MG"]["workload_wall_s"] for b in bl], [b["C"]["workload_wall_s"] for b in bl])
    inv_c_over_mg = lambda r: {"geo_mean": 1 / r["geo_mean"], "ci95_lo": 1 / r["ci95_hi"], "ci95_hi": 1 / r["ci95_lo"]}
    cost["C_over_MG_device_seconds_span"] = inv_c_over_mg(cost["MG_over_C_device_seconds_span"])
    cost["C_over_MG_p95_latency"] = inv_c_over_mg(cost["MG_over_C_p95_latency"])
    cold = {}
    for k in range(1, 7):
        mdir = f"{TIMING}/block{k}_a{BLOCK_ATTEMPT[k]}_MG"
        cold[str(k)] = {"MG_cold_load_s_max": mg_meta_cold(mdir)[0], "MG_peak_reserved_gb": mg_meta_cold(mdir)[1], "C_cold_load_s_max": blocks[k]["C"]["cold_load_s_max"]}
    cost["cold_loading"] = cold
    # timing 출력 정합성: C token == iter_040 / MG timing 최종 box == V96 raw(selected thr) box
    import mg45_ccheck as CC
    old = CC.old_records()
    cchk = [CC.check(f"{TIMING}/block{k}_a{BLOCK_ATTEMPT[k]}_C", old) for k in range(1, 7)]
    mg_raw = mg[sel["selected"]["ckpt"]]["recs"]
    mchk = []
    for k in range(1, 7):
        recs, _, _ = E.verify_mg_dir(f"{TIMING}/block{k}_a{BLOCK_ATTEMPT[k]}_MG", "V96", sel["selected"]["ckpt"], man)
        ts = E.mg_scores(recs, ents, sel["selected"]["threshold"])
        ref = E.mg_scores(mg_raw, ents, sel["selected"]["threshold"])
        mchk.append({"block": k, "n": len(recs), "n_f1_differ": sum(abs(ts[x]["f1_03"] - ref[x]["f1_03"]) > 1e-12 or abs(ts[x]["f1_05"] - ref[x]["f1_05"]) > 1e-12 or ts[x]["n_pred"] != ref[x]["n_pred"] for x in ts),
                     "max_abs_logit_diff_vs_raw": float(max(np.abs(np.array(recs[x]["logits"]) - np.array(mg_raw[x]["logits"])).max() for x in recs))})
    integrity = {"C_timing_token_mismatch_total": int(sum(c["token_mismatch"] for c in cchk)), "C_timing_all_eos": all(c["all_eos"] for c in cchk),
                 "C_timing_n": [c["n"] for c in cchk], "MG_timing_f1_or_count_differ_total": int(sum(m["n_f1_differ"] for m in mchk)),
                 "MG_timing": mchk, "C_peak_gpu_used_mib_sampled": [c["gpu_used_mib_max_sampled"] for c in cchk]}
    # ---- 결정 ----
    s = f"{selname}_minus_C"
    cm = f"C_minus_{selname}"
    mod = {"MG-C_f1_03_ci_lo>=-0.03": cmp[s]["f1_03"]["lo"] >= -0.03, "MG-C_f1_05_ci_lo>=-0.03": cmp[s]["f1_05"]["lo"] >= -0.03,
           "MG-C_fp_ci_hi<=0.10": cmp[s]["fp_03"]["hi"] <= 0.10, "device_ratio_ci_hi<=0.50": cost["MG_over_C_device_seconds_span"]["ci95_hi"] <= 0.50,
           "throughput_ratio_ci_lo>=2.0": cost["MG_over_C_throughput"]["ci95_lo"] >= 2.0, "p95_latency_ratio_ci_hi<=1.20": cost["MG_over_C_p95_latency"]["ci95_hi"] <= 1.20}
    both_ok = all(prim[x]["n_patients"] == 96 for x in ("MG-P@sel", "MG-MS@sel"))
    res_adv = {"C-MG_f1_03_point>=0.05": cmp[cm]["f1_03"]["mean"] >= 0.05, "C-MG_f1_03_ci_lo>0": cmp[cm]["f1_03"]["lo"] > 0,
               "C-MG_f1_05_ci_lo>=-0.03": cmp[cm]["f1_05"]["lo"] >= -0.03, "C-MG_fp_ci_hi<=0.10": cmp[cm]["fp_03"]["hi"] <= 0.10,
               "C/MG_device_ratio_ci_hi<=2.0": cost["C_over_MG_device_seconds_span"]["ci95_hi"] <= 2.0,
               "C/MG_p95_latency_ratio_ci_hi<=2.0": cost["C_over_MG_p95_latency"]["ci95_hi"] <= 2.0, "both_checkpoints_ran": both_ok}
    prov_ok = (repro["abs_diff_03"] < 1e-9 and repro["abs_diff_05"] < 1e-9 and c_inv["mismatch"] == 0 and integrity["C_timing_token_mismatch_total"] == 0
               and integrity["MG_timing_f1_or_count_differ_total"] == 0 and all(n == 192 for n in integrity["C_timing_n"]))
    if not prov_ok:
        outcome = "execution_failed_provenance_or_integrity"
    elif all(mod.values()):
        outcome = "modular_alternative_supported"
    elif all(res_adv.values()):
        outcome = "C_residual_advantage_supported"
    else:
        outcome = "scientifically_inconclusive_hold_track"
    decision = {"outcome": outcome, "modular_alternative_conditions": mod, "C_residual_advantage_conditions": res_adv, "provenance_integrity_ok": prov_ok,
                "note": "개발 자료 V96 고정 비교. 비적응(MG) 대 T305 적응(C) 차이는 적응 예산 설명을 제거하지 않는다. 임상적 충분성·신규 contribution·외부 일반화 주장이 아니다."}
    rep = {"n_patients": len(pids), "selected": sel["selected"], "primary_V96": prim, "compare_paired_ci975": cmp, "strata": strata, "strata_small_threshold": med,
           "C_reproduction": repro, "C_import_provenance": cprov, "cost": cost, "integrity": integrity, "decision": decision,
           "mg_runs": {k: {"dir": V96_DIRS[k], "workload_wall_s": mg[k]["comp"].get("workload_wall_s"), "exit_codes": mg[k]["comp"]["exit_codes"]} for k in mg},
           "provenance": {"lock_sha256": fsha(a.lock), "eval_source_sha256": fsha("mg45_report.py"), "bootstrap": {"B": NBOOT, "seed": SEED}, "eval_wall_s": time.time() - t_start}}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + f".{os.getpid()}.tmp"
    json.dump(rep, open(tmp, "w"), indent=1)
    tmp2 = a.out.replace(".json", "_per_item.json") + f".{os.getpid()}.tmp"
    json.dump({s_: {f"{k[0]}|{k[1]}": v for k, v in sc.items()} for s_, sc in sysdefs.items()}, open(tmp2, "w"))
    os.replace(tmp2, a.out.replace(".json", "_per_item.json"))
    os.replace(tmp, a.out)
    print(json.dumps({"outcome": outcome, "F1_03": {s_: round(prim[s_]["f1_03"], 4) for s_ in prim}, "F1_05": {s_: round(prim[s_]["f1_05"], 4) for s_ in prim},
                      "mod": mod, "res_adv": res_adv, "prov_ok": prov_ok}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lock")
    l.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--lock", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    {"lock": cmd_lock, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
