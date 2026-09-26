"""iter_014 G 재개 검사 (실제 GPU, 결정적 kernel, sanity stage): 중간 optimizer-step checkpoint에서 저장·강제 종료·재개한 실행이 끊김 없는 실행과 같은지 대조한다.
사용: python test_rsna_iter014_resume.py PROTOCOL  -> results/iter_014/tests/fixtures_iter014_resume.json
비교: step별 batch ID·batch_token_sha·branch_sha(후보 ID/token/mask)·rng_before·opt_step_before·LR·loss·grad_norm, 저장 시점 digest(adapter/optimizer/RNG), 최종 epoch adapter digest.
허용 오차는 사전 고정: 이산 항목(ID/digest/sha/opt_step)은 정확 일치, 수치(loss, grad_norm, lr)는 상대 1e-6 (결정적 kernel)."""
import json
import os
import subprocess
import sys
import threading

R = "results/iter_014/tests/resume2"
STAGE = "results/iter_014/stage/sanity.json"


def cmd(d, prot, extra=()):
    return [sys.executable, "-m", "rsna_diag.on_gpu", "--gpu", "%s", "--", sys.executable, "-m", "rsna_diag.adapt_geo", "--run-dir", d, "--stage-config", STAGE, "--loss", "G", "--lr", "2e-5",
            "--protocol", prot, "--microbatch", "1", "--branch-microbatch", "2", "--workers", "0", "--ckpt-every", "2", "--deterministic", *extra]


def run(gpu, d, prot, extra=()):
    c = [x if x != "%s" else str(gpu) for x in cmd(d, prot, extra)]
    return subprocess.run(c, stdout=open(d + ".log", "a"), stderr=subprocess.STDOUT).returncode


def steps(d):
    rows = [json.loads(l) for l in open(os.path.join(d, "train_log.jsonl"))]
    return {r["step"]: r for r in rows if "step" in r and "event" not in r}, [r for r in rows if r.get("event")]


def main():
    prot = sys.argv[1]
    os.makedirs(R, exist_ok=True)
    A, B = os.path.join(R, "uninterrupted"), os.path.join(R, "interrupted")
    rc = {}

    def a():
        rc["A"] = run(0, A, prot)

    def b():
        rc["B1"] = run(1, B, prot, ("--stop-after-step", "2"))
        rc["B2"] = run(1, B, prot)

    ts = [threading.Thread(target=a), threading.Thread(target=b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    out = {"returncodes": rc, "checks": []}

    def ck(name, cond, detail=""):
        out["checks"].append({"name": name, "pass": bool(cond), "detail": str(detail)[:400]})
        print(("PASS " if cond else "FAIL ") + name, str(detail)[:200], flush=True)

    ck("A completed rc=0; B interrupted rc=5 then resumed rc=0", rc.get("A") == 0 and rc.get("B1") == 5 and rc.get("B2") == 0, rc)
    sa, ea = steps(A)
    sb, eb = steps(B)
    ck("same step set (1..8)", sorted(sa) == sorted(sb) == list(range(1, 9)), (sorted(sa), sorted(sb)))
    disc = ("batch_ids", "batch_token_sha", "branch_sha", "rng_before", "opt_step_before", "n_branches", "n_label_tokens", "n_branch_label_tokens", "epoch", "pos")
    bad = {s: [k for k in disc if sa[s][k] != sb[s][k]] for s in sa if s in sb and any(sa[s][k] != sb[s][k] for k in disc)}
    ck("discrete provenance identical every step (batch/candidate/token-mask sha, RNG digest, optimizer step count)", not bad, bad)
    rel = lambda x, y: abs(x - y) / max(abs(y), 1e-12)
    badn = {s: {k: (sa[s][k], sb[s][k]) for k in ("loss", "grad_norm", "lr", "gt_weighted_ce", "branch_weighted_ce") if rel(sa[s][k], sb[s][k]) > 1e-6} for s in sa if s in sb}
    badn = {s: v for s, v in badn.items() if v}
    ck("loss/grad_norm/LR equal within 1e-6 (deterministic kernels)", not badn, badn)
    ck_a = {(e["step"]): e["digests"] for e in ea if e.get("event") == "checkpoint"}
    ck_b = {(e["step"]): e["digests"] for e in eb if e.get("event") == "checkpoint"}
    common = sorted(set(ck_a) & set(ck_b))
    ck("checkpoint digests (adapter/optimizer/RNG) identical at every common step incl. mid-epoch step 2 and post-resume", bool(common) and all(ck_a[s] == ck_b[s] for s in common), common)
    rs = [e for e in eb if e.get("event") == "resume"]
    ck("resume event: restored state == saved checkpoint state, from step 2", len(rs) == 1 and rs[0]["restored_equals_saved"] and rs[0]["step"] == 2, rs[:1])
    ma = json.load(open(os.path.join(A, "epoch_02", "val_metrics.json")))
    mb = json.load(open(os.path.join(B, "epoch_02", "val_metrics.json")))
    ck("final adapter digest identical (epoch 2)", ma["adapter_digest"] == mb["adapter_digest"], (ma["adapter_digest"][:12], mb["adapter_digest"][:12]))
    out["n_pass"] = sum(c["pass"] for c in out["checks"])
    out["n"] = len(out["checks"])
    json.dump(out, open("results/iter_014/tests/fixtures_iter014_resume.json", "w"), indent=1)
    print(f"{out['n_pass']}/{out['n']} PASS")
    return 0 if out["n_pass"] == out["n"] else 1


if __name__ == "__main__":
    sys.exit(main())
