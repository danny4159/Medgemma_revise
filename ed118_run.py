"""iter_118 감독기: TECH 기술 검사(2/4 worker·재개) → MAIN 생성 → 평가·독립 검산 → 봉인.

모든 결과는 results/iter_118 아래 새 경로. 평가 잠금(private/eval_lock.json)은 부모가 검증한다 (worker는 private를 열 수 없다).
 stage 명령:
   gen    --name TECH_w2 --requests TECH --workers 2 [--max-requests N]   생성 launcher 호출 (protocol은 stage별 요청 파일 기준)
   techreport                                                              TECH 기술 검사 요약 (정답률 gate 아님)
   eval                                                                    MAIN 평가 + 독립 verifier
   seal                                                                    검증 대상 digest 봉인
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import ed118_eval as EV
import ed118_gen as RUN
import ed118_spec as S
import ed118_verify as V

OUT = Path("results/iter_118")
PRIV = OUT / "private"
LOCK = PRIV / "eval_lock.json"
REQ = lambda n: str(OUT / f"requests/{n}.jsonl")
PROTO = lambda n: str(OUT / f"protocol/protocol_{n}.json")


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, sort_keys=True)


def event(ev, **kw):
    OUT.mkdir(exist_ok=True)
    with (OUT / "events.jsonl").open("a") as f:
        f.write(json.dumps(dict(event=ev, epoch=time.time(), **kw)) + "\n")


def verify_lock():
    lock = read(LOCK)
    bad = [p for p, h in lock["files"].items() if RUN.file_sha(p) != h]
    if bad:
        raise RuntimeError(f"평가 잠금 불일치: {bad}")
    return lock


def gen(a):
    verify_lock()
    out_dir = str(OUT / "gen" / a.name)
    t0 = time.monotonic()
    cmd = [sys.executable, "-u", "ed118_gen.py", "launch", "--requests", REQ(a.requests), "--protocol", PROTO(a.requests), "--out-dir", out_dir,
           "--workers", str(a.workers), "--peak-gb", str(a.peak_gb)]
    if a.max_requests is not None:
        cmd += ["--max-requests", str(a.max_requests)]
    event("gen_start", name=a.name, argv=cmd, free_mib=RUN.gpu_free_mib())
    os.makedirs(OUT / "launch", exist_ok=True)
    n = len(glob.glob(str(OUT / "launch" / f"{a.name}.attempt*.stdout")))
    with open(OUT / "launch" / f"{a.name}.attempt{n}.stdout", "x") as so, open(OUT / "launch" / f"{a.name}.attempt{n}.stderr", "x") as se:
        rc = subprocess.run(cmd, stdout=so, stderr=se).returncode
    event("gen_exit", name=a.name, exit_code=rc, wall_s=time.monotonic() - t0)
    print(a.name, "rc", rc, "wall_s", round(time.monotonic() - t0, 1))
    sys.exit(0 if (rc == 0 or a.max_requests is not None) else rc)


def classify_summary(recs, cmap):
    """TECH: 정답 없이 분류 분포만 (조건별 방향·flag 수). 정답률은 보고하지 않는다."""
    out = {}
    for r in recs:
        c = cmap[r["patient"]][r["cond"]]
        k = S.classify(r["suffix_text_raw"], r["ended_eos"])
        d = out.setdefault(c, dict(n=0, yes=0, no=0, unknown=0, hedged=0, conditional=0, contradictory=0, refusal=0, parse_failure=0, non_eos=0,
                                   confirmed=0))
        d["n"] += 1
        d[k["direction"]] += 1
        for f in ("hedged", "conditional", "contradictory", "refusal", "parse_failure", "non_eos", "confirmed"):
            d[f] += int(k[f])
    return out


def techreport(a):
    verify_lock()
    cmap = read(PRIV / "cond_map.json")
    res = dict(created=time.time(), checks={})
    stages = {}
    for name, reqn in (("TECH_w2", "TECH"), ("TECH_w4", "TECH"), ("RESUME6", "RESUME6")):
        recs = RUN.verify_completion(str(OUT / "gen" / name), REQ(reqn), PROTO(reqn))
        stages[name] = recs
        comp = read(OUT / "gen" / name / "completion.json")
        res[name] = dict(n=len(recs), wall_s=comp["wall_s"], workers=comp["workers"], cost=comp["cost"], exit_codes=comp["exit_codes"],
                         mapping=comp["mapping"])
    tok = lambda recs: {r["request_id"]: r["suffix_ids"] for r in recs}
    t2, t4, tr = tok(stages["TECH_w2"]), tok(stages["TECH_w4"]), tok(stages["RESUME6"])
    res["checks"]["w2_w4_tokens_equal"] = t2 == t4 and len(t2) == 18
    res["checks"]["resume_tokens_equal"] = all(tr[k] == t2[k] for k in tr) and len(tr) == 6
    res["checks"]["same_pixels_within_patient"] = all(
        len({r["input_pixel_sha256"] for r in stages["TECH_w2"] if r["patient"] == p}) == 1 for p in {r["patient"] for r in stages["TECH_w2"]})
    res["checks"]["all_eos_or_retried"] = [r["request_id"] for r in stages["TECH_w2"] if not r["ended_eos"]]
    # 접근 기록: private 경로가 열렸거나 거부 시도가 있었는지
    access = {}
    for fn in sorted(glob.glob(str(OUT / "gen" / "*" / "file_access.worker*.json"))):
        d = read(fn)
        access[fn] = dict(n_opened=d["n_opened"], denied=d["denied"], private_opened=[p for p in d["opened"] if "iter_118/private" in p or p.endswith("gt_manifest.json")])
    res["file_access"] = access
    res["checks"]["no_private_or_gt_access"] = bool(access) and all(not v["denied"] and not v["private_opened"] for v in access.values())
    res["classification_distribution_no_gt"] = classify_summary(stages["TECH_w2"], cmap)
    # 재사용 코드 불변: iter_117 protocol의 코드 hash와 현재 생성 경로 파일 비교
    p117 = read("results/iter_117/protocol/MAIN.json")["code"]
    res["checks"]["generate_geometry_prompts_unchanged_vs_iter117"] = all(
        RUN.file_sha(f) == p117[f] for f in ("rsna_diag/generate.py", "rsna_diag/geometry.py", "rsna_diag/prompts.py", "rsna_diag/__init__.py"))
    wc = read("results/iter_118/data/weights_check.json")
    res["checks"]["weights_match_iter116_reference"] = not wc["differences_vs_reference"]
    res["all_pass"] = all(v is True or v == [] for v in res["checks"].values())
    write(OUT / "tech/tech_report.json", res)
    print(json.dumps(res["checks"]), "all_pass", res["all_pass"])


def eval_main(a):
    lock = verify_lock()
    ledger = read(OUT / "data/ledger_det.json")["rows"]
    labels = read(PRIV / "labels.json")
    cmap = read(PRIV / "cond_map.json")
    recs = RUN.verify_completion(str(OUT / "gen/MAIN"), REQ("MAIN"), PROTO("MAIN"))
    assert len(recs) == 576
    main_ids = {r["id"] for r in ledger if r["stage"] == "MAIN"}
    ps = EV.build_patients(recs, cmap, labels, [r for r in ledger if r["stage"] == "MAIN"])
    assert {p["id"] for p in ps} == main_ids and len(ps) == 192
    comp = read(OUT / "gen/MAIN/completion.json")
    det = read(OUT / "det/raw_preds.json")
    rep = EV.report(ps, dict(cost=dict(EV.cost(recs), launcher_wall_s=comp["wall_s"], device_seconds=comp["cost"].get("device_seconds_generate_union"),
                                      device_seconds_incl_loading=comp["cost"].get("device_seconds_incl_loading_union"), workers=comp["workers"],
                                      detector_wall_s_198_images_incl_loading=det["wall_s"],
                                      note="S는 E 출력+detector 규칙 비용이며 자연 초안 생성 비용은 측정하지 않았다."),
                             eval_lock_sha256=RUN.file_sha(str(LOCK)), classifier_version=S.CLASSIFIER_VERSION, locked_at_utc=lock["locked_at_utc"]))
    checks = V.verify(ps, rep, recs, cmap, labels) + V.verify_requests(RUN.read_requests(REQ("MAIN")), cmap, labels)
    ver = dict(checks=checks, all_pass=all(c["ok"] for c in checks), n_checks=len(checks))
    obs = [dict(id=p["id"], cat=p["cat"], gt=p["gt"], B=p["B"], E=p["E"]["direction"], C=p["C"]["direction"], W=p["W"]["direction"],
                E_text=p["E"]["text"][:200], W_text=p["W"]["text"][:200]) for p in ps
           if p["E"]["outcome"] == "ok" and p["W"]["outcome"] == "bad"]
    write(OUT / "eval/per_patient.json", ps)
    write(OUT / "eval/report.json", rep)
    write(OUT / "eval/observations_E_ok_W_bad.json", obs)
    ver["verified_files"] = {str(OUT / "eval" / f): RUN.file_sha(str(OUT / "eval" / f))
                             for f in ("per_patient.json", "report.json", "observations_E_ok_W_bad.json")}
    write(OUT / "eval/verify.json", ver)
    event("eval_done", label=rep["decision"]["label"], verify_all_pass=ver["all_pass"])
    print(json.dumps(rep["decision"]), "verify", ver["all_pass"], ver["n_checks"])


def seal(a):
    verify_lock()
    v = read(OUT / "eval/verify.json")
    assert v["all_pass"] is True
    for p, h in v["verified_files"].items():
        assert RUN.file_sha(p) == h, p
    recs = RUN.verify_completion(str(OUT / "gen/MAIN"), REQ("MAIN"), PROTO("MAIN"))
    files = list(v["verified_files"]) + [str(OUT / "eval/verify.json"), str(LOCK), str(OUT / "tech/tech_report.json"), str(OUT / "tests/fixtures.json")]
    write(OUT / "completion.json", dict(complete=True, epoch=time.time(), n_records=len(recs), n_patients=192, files={p: RUN.file_sha(p) for p in files},
                                         label=read(OUT / "eval/report.json")["decision"]["label"], new_training=False))
    event("sealed")
    print("봉인 완료")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--name", required=True)
    g.add_argument("--requests", required=True)
    g.add_argument("--workers", type=int, required=True)
    g.add_argument("--peak-gb", type=float, default=9.0)
    g.add_argument("--max-requests", type=int, default=None)
    for n in ("techreport", "eval", "seal"):
        sub.add_parser(n)
    a = ap.parse_args()
    {"gen": gen, "techreport": techreport, "eval": eval_main, "seal": seal}[a.cmd](a)


if __name__ == "__main__":
    main()
