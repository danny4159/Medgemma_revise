"""iter_048 재개 검사 비교: 결정적 기준 실행(ref)과 중단-재개 실행(int: epoch 중간 step 4, bnd: epoch 끝 checkpoint 직후·adapter 저장 전 step 3)의
adapter·optimizer·RNG digest, 스텝별 loss/grad/batch/RNG가 같은지 확인한다. 기준: 결정적 모드이므로 digest 정확 일치, loss/grad 차이 == 0.
python pg48_resume_check.py --out results/iter_048/tests/resume/resume_compare.json
"""
import argparse
import json
import os
import sys

import torch

ROOT = "results/iter_048/tests/resume"


def steps(d):
    out, ev = {}, []
    for l in open(os.path.join(d, "train_log.jsonl")):
        r = json.loads(l)
        if r["event"] == "step":
            if r["step"] in out:
                out.setdefault("_dup", []).append(r["step"])
            out[r["step"]] = r
        else:
            ev.append(r)
    return out, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    res, allok = {}, True
    for mode in ("J", "E"):
        ref_s, ref_ev = steps(f"{ROOT}/{mode}_ref")
        for var in ("int", "bnd"):
            d = f"{ROOT}/{mode}_{var}"
            s, ev = steps(d)
            entry = {"n_steps": len([k for k in s if k != "_dup"]), "duplicate_step_records": s.get("_dup", [])}
            keys = sorted(k for k in ref_s if k != "_dup")
            entry["loss_max_abs_diff"] = max(abs(s[k]["loss"] - ref_s[k]["loss"]) for k in keys)
            entry["grad_norm_max_abs_diff"] = max(abs(s[k]["grad_norm"] - ref_s[k]["grad_norm"]) for k in keys)
            entry["batch_rows_equal"] = all(s[k]["batch_rows"] == ref_s[k]["batch_rows"] for k in keys)
            entry["rng_before_equal"] = all(s[k]["rng_before"] == ref_s[k]["rng_before"] for k in keys)
            entry["opt_step_before_equal"] = all(s[k]["opt_step_before"] == ref_s[k]["opt_step_before"] for k in keys)
            entry["joint_orders_equal"] = all(s[k]["joint_orders"] == ref_s[k]["joint_orders"] for k in keys)
            resumes = [e for e in ev if e["event"] == "resume"]
            entry["resume_events"] = [{"step": e["step"], "epoch": e["epoch"], "pos": e["pos"], "restored_equals_saved": e["restored_equals_saved"]} for e in resumes]
            entry["base_frozen_verified"] = any(e["event"] == "base_frozen_verified" for e in ev)
            fa = {}
            for ep in (1, 2):
                ra = torch.load(f"{ROOT}/{mode}_ref/epoch_{ep:02d}/adapter.pt", map_location="cpu", weights_only=True)["digest"]
                ia = torch.load(f"{d}/epoch_{ep:02d}/adapter.pt", map_location="cpu", weights_only=True)["digest"]
                fa[f"epoch{ep}_adapter_digest_equal"] = ra == ia
                rc = torch.load(f"{ROOT}/{mode}_ref/epoch_{ep:02d}/ckpt.pt", map_location="cpu", weights_only=False)["digests"]
                ic = torch.load(f"{d}/epoch_{ep:02d}/ckpt.pt", map_location="cpu", weights_only=False)["digests"]
                fa[f"epoch{ep}_ckpt_digests_equal(adapter,optimizer,rng)"] = rc == ic
            entry.update(fa)
            entry["ok"] = (entry["loss_max_abs_diff"] == 0 and entry["grad_norm_max_abs_diff"] == 0 and entry["batch_rows_equal"] and entry["rng_before_equal"]
                           and entry["opt_step_before_equal"] and entry["joint_orders_equal"] and not entry["duplicate_step_records"]
                           and len(resumes) == 1 and all(r["restored_equals_saved"] for r in resumes) and entry["base_frozen_verified"] and all(fa.values()))
            allok &= entry["ok"]
            res[f"{mode}_{var}"] = entry
    out = {"results": res, "all_ok": allok, "criterion": "deterministic mode: exact digest equality, loss/grad diff == 0, one resume event restored_equals_saved"}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
