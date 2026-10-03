"""iter_059: D6 paired 전체 pipeline 비용 측정 (HD-GLIO+OR vs U8). 경계: 원본 NIfTI -> 6구간 답변 파일 저장.
python hdglio59_timing.py lock      # 입력·코드·checkpoint digest 잠금 (exclusive)
python hdglio59_timing.py tech      # 첫 block(BRATS_053/199) 기술 검사: HD·U8 각 1회 + 정합성 대조
python hdglio59_timing.py blocks    # 고정 3 block x 2 order. 완료 pair는 재사용, 미완료 pair는 새 attempt로 전체 재측정(실패 attempt 보존)
출력: results/iter_059/{protocol.json, tech/, timing/}
"""
import glob
import json
import os
import subprocess
import sys
import time

import hdglio59_common as C

ROOT = C.ROOT
PYV = f"{ROOT}/results/environments/hdglio58/bin/python"
PARAMS = f"{ROOT}/results/iter_058/external/weights/params"
OUT = f"{ROOT}/results/iter_059"
BLOCKS = [["BRATS_053", "BRATS_199"], ["BRATS_368", "BRATS_380"], ["BRATS_037", "BRATS_455"]]
PEAK = {"HD": 3072, "U8": 9728}  # MiB: iter_058 관측 reserved 1660/9312에서 여유. tech 단계에서 갱신 기록.
OLD_PRED = f"{ROOT}/results/iter_058/hd/run_D_2g1w"
PLAN_058 = "../agent/runs/iter_058/plan.md"


def lock_digests():
    src = json.load(open(f"{ROOT}/results/iter_058/external/sources.json"))
    ck = {}
    for rel, h in src["weights"]["files"].items():
        p = f"{PARAMS}/{rel}"
        got = C.sha_file(p)
        if got != h:
            raise C.TechError(f"checkpoint file changed: {rel}")
        ck[rel] = got
    cases = {c["case"]: c for c in json.load(open(f"{ROOT}/results/iter_056/data/cases.json"))["chosen"]}
    imgs = {}
    for cs in BLOCKS:
        for c in cs:
            p = f"{ROOT}/results/iter_056/data/raw/{c}_img.nii.gz"
            got = C.sha_file(p)
            if got != cases[c]["img_sha256"]:
                raise C.TechError(f"raw image changed {c}")
            imgs[c] = got
    old = {}
    for f in ["results/iter_058/eval_E/report.json", "results/iter_058/eval_E/per_slab_hd.json", "results/iter_058/hd/run_E_main/pred_manifest.json",
              "results/iter_058/input_manifest.json", "results/iter_058/external/sources.json", "results/iter_056/data/gt_slabs.json",
              "results/iter_056/data/cases.json"]:
        old[f] = C.sha_file(f)
    for f in sorted(glob.glob("results/iter_058/hd/run_E_main/*/pred/BRATS_*.nii.gz")):
        old[f] = C.sha_file(f)
    return {"code": C.current_digests(), "checkpoint": ck, "raw_images": imgs, "iter058_fixed": old, "plan_058_sha256": C.sha_file(PLAN_058),
            "model_revision": "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"}


def cmd_lock():
    os.makedirs(OUT, exist_ok=True)
    d = lock_digests()
    d["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    C.atomic_json(f"{OUT}/protocol.json", d, exclusive=True)
    print("locked", len(d["code"]), "code files")


def load_lock():
    lk = json.load(open(f"{OUT}/protocol.json"))
    C.check_locked(lk["code"], C.current_digests())
    for k in ("iter058_fixed",):
        C.check_locked(lk[k], {f: C.sha_file(f) for f in lk[k]})
    return lk


def run_one(kind, cases, logical_gpu, run_dir, allowed, extra_env=None):
    gpu = C.pick_gpu(logical_gpu, allowed)
    tbl = C.gpu_table()
    adm = C.admit(tbl, gpu, PEAK[kind])
    C.new_run_dir(run_dir)  # 존재하면 거부(부모 생성). 실제 디렉터리는 자식이 만든다.
    cj = run_dir + ".cases.json"
    json.dump(cases, open(cj, "w"))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu))
    if kind == "HD":
        env.update(HD_GLIO_PARAMS=PARAMS, HDG_PROCS="2")
        cmd = [PYV, f"{ROOT}/hdglio59_hd.py", cj, run_dir]
    else:
        cmd = [sys.executable, f"{ROOT}/hdglio59_u8.py", cj, run_dir]
    env.update(extra_env or {})
    t_ep = time.time()
    t = time.perf_counter()
    r = subprocess.run(cmd, env=env, stdout=open(run_dir + ".log", "w"), stderr=subprocess.STDOUT)
    wall = time.perf_counter() - t
    rec = {"kind": kind, "cases": cases, "logical_gpu": logical_gpu, "physical_gpu": gpu, "admission": adm, "rc": r.returncode,
           "wall_s": wall, "parent_start_epoch": t_ep, "parent_end_epoch": t_ep + wall, "dir": run_dir}
    return rec


def finalize_run(rec):
    if rec["rc"] != 0:
        rec["complete"] = False
        rec["error"] = f"rc={rec['rc']}"
        return rec
    try:
        s, flags = C.verify_run(rec["kind"], rec["dir"], rec["cases"])
        rec.update(complete=True, flags=flags, peak_reserved_MiB=s["peak_reserved_MiB"], peak_alloc_MiB=s["peak_alloc_MiB"])
    except C.TechError as e:
        rec.update(complete=False, error=str(e))
    return rec


def pair(b, o, attempt, base, lk, allowed):
    cs = BLOCKS[b]
    order = (("U8", "HD"), ("HD", "U8"))[o]
    logical = (b + o) % 2
    C.check_locked(lk["code"], C.current_digests())
    rec = {"block": b, "order": "->".join(order), "cases": cs, "attempt": attempt, "logical_gpu": logical,
           "smi_before": C.gpu_table(), "loadavg": os.getloadavg(), "runs": {}}
    ok = True
    for name in order:
        d = f"{base}/b{b}_o{o}_a{attempt}_{name}"
        rec["runs"][name] = finalize_run(run_one(name, cs, logical, d, allowed))
        if not rec["runs"][name]["complete"]:
            ok = False
            break  # pair 중단: 부분 시간을 이어 붙이지 않는다
    rec["complete"] = ok
    return rec


def cmd_blocks():
    lk = load_lock()
    allowed = C.allowed_physical(os.environ.get("CUDA_VISIBLE_DEVICES"))
    base = f"{OUT}/timing"
    os.makedirs(base, exist_ok=True)
    for b in range(len(BLOCKS)):
        for o in range(2):
            done = f"{base}/pair_b{b}_o{o}.json"
            if os.path.exists(done):
                p = json.load(open(done))
                for name, r in p["runs"].items():  # 완료 pair 재사용 전 digest(출력 존재·case 집합) 재검증
                    C.verify_run(name, r["dir"], r["cases"])
                print("reuse", b, o, flush=True)
                continue
            att = len(glob.glob(f"{base}/attempt_b{b}_o{o}_a*.json"))
            rec = pair(b, o, att, base, lk, allowed)
            C.atomic_json(f"{base}/attempt_b{b}_o{o}_a{att}.json", rec, exclusive=True)
            print(b, rec["order"], rec["complete"], {k: round(v["wall_s"], 2) for k, v in rec["runs"].items()}, flush=True)
            if rec["complete"]:
                C.atomic_json(done, rec, exclusive=True)
            else:
                print("INCOMPLETE pair; rerun to retry with new attempt", flush=True)
                sys.exit(1)


def cmd_tech():
    import numpy as np
    import nibabel as nib
    lk = load_lock()
    allowed = C.allowed_physical(os.environ.get("CUDA_VISIBLE_DEVICES"))
    base = f"{OUT}/tech"
    os.makedirs(base, exist_ok=True)
    att = len(glob.glob(f"{base}/tech_a*.json"))
    cs = BLOCKS[0]
    out = {"cases": cs, "attempt": att, "checks": {}}
    hd = finalize_run(run_one("HD", cs, 0, f"{base}/a{att}_HD", allowed))
    u8 = finalize_run(run_one("U8", cs, 1, f"{base}/a{att}_U8", allowed))
    out["runs"] = {"HD": hd, "U8": u8}
    chk = out["checks"]
    if hd["complete"]:
        # 1) 원본 채널 대응: 새 입력 channel voxel/affine == 원본 4D의 지정 channel
        hd_ch = {"0000": 1, "0001": 2, "0002": 3, "0003": 0}
        ch_ok = {}
        for c in cs:
            img = nib.load(f"{ROOT}/results/iter_056/data/raw/{c}_img.nii.gz")
            data = np.asarray(img.dataobj)
            for suf, ch in hd_ch.items():
                x = nib.load(f"{hd['dir']}/in/{c}_{suf}.nii.gz")
                ch_ok[f"{c}_{suf}"] = bool(np.array_equal(np.asarray(x.dataobj), data[..., ch].astype(np.float32)) and np.allclose(x.affine, img.affine, atol=1e-4)
                                           and x.shape == img.shape[:3] and np.isfinite(np.asarray(x.dataobj)).all())
        chk["channel_voxel_affine_equal"] = ch_ok
        # 2) 공간 대응 + 기존 iter_058 D pred와 비교(알려진 미세 voxel 변동은 기록)
        cmp = {}
        for c in cs:
            new = np.asarray(nib.load(f"{hd['dir']}/pred/{c}.nii.gz").dataobj) > 0
            old_p = glob.glob(f"{OLD_PRED}/*/pred/{c}.nii.gz")
            old = np.asarray(nib.load(old_p[0]).dataobj) > 0
            a_new = json.load(open(f"{hd['dir']}/hd_{c}.json"))
            cmp[c] = {"same_shape": new.shape == old.shape, "fg_new": int(new.sum()), "fg_old": int(old.sum()), "fg_xor": int((new ^ old).sum()),
                      "answers_new": [x["answer"] for x in a_new["answers"]],
                      "answers_from_old_pred": None}
            oldv = [int(old[:, :, x["z0"]:x["z1"] + 1].sum()) for x in a_new["answers"]]
            cmp[c]["answers_from_old_pred"] = ["PRESENT" if v > 0 else "ABSENT" for v in oldv]
            cmp[c]["answers_equal"] = cmp[c]["answers_new"] == cmp[c]["answers_from_old_pred"]
        chk["hd_vs_iter058_pred"] = cmp
    if u8["complete"]:
        # 3) U8 답변 vs iter_058 u8check(동일 입력·greedy) 및 EOS
        cmp = {}
        for c in cs:
            new = json.load(open(f"{u8['dir']}/u8_{c}.json"))["answers"]
            old = json.load(open(f"{ROOT}/results/iter_058/timing/u8check/u8_{c}.json"))["answers"]
            cmp[c] = {"answers_equal": [x["answer"] for x in new] == [x["answer"] for x in old],
                      "raw_equal": [x["raw"] for x in new] == [x["raw"] for x in old], "all_eos": all(x["ended_eos"] for x in new)}
        chk["u8_vs_iter058_u8check"] = cmp
    # 4) 계측 연결: 외부 wall이 내부 event 구간을 포함하는지
    link = {}
    for name, r in (("HD", hd), ("U8", u8)):
        if r["complete"]:
            s = json.load(open(f"{r['dir']}/summary.json"))
            e = {x["event"]: x["t"] for x in s["events"] if "case" not in x}
            ps = [x for x in s["events"] if x["event"] == "proc_start"][0]["t"]
            link[name] = {"wall_s": r["wall_s"], "startup_s": ps - r["parent_start_epoch"], "pipeline_s": e["pipeline_end"] - e["pipeline_start"],
                          "load_s": e["load_model_end"] - e["load_model_start"], "tail_after_pipeline_s": r["parent_end_epoch"] - e["pipeline_end"],
                          "events_inside_wall": r["parent_start_epoch"] <= ps and e["pipeline_end"] <= r["parent_end_epoch"]}
    chk["event_wall_link"] = link
    out["complete"] = bool(hd["complete"] and u8["complete"])
    C.atomic_json(f"{base}/tech_a{att}.json", out, exclusive=True)
    print(json.dumps(chk, indent=1, default=str)[:4000])


if __name__ == "__main__":
    {"lock": cmd_lock, "tech": cmd_tech, "blocks": cmd_blocks}[sys.argv[1]]()
