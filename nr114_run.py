"""iter_114 실행기(CPU 분석). 단계: link -> (pre-run) lock -> stage_lock -> analyze -> expand? -> judge -> seal.

link   : 저장 모델 출력(MG A / MSPC / CURE) 과 items/GT 를 연결해 항목별 ledger 작성(순위·GT 오류 미계산). 중복·누락·digest 불일치는 LinkError.
lock   : (모델 본출력 전) 코드·규칙·표본·checkpoint·요청 hash 를 실제 시각과 함께 results/iter_114/analysis/protocol.json 에 기록. fixtures PASS 필요.
stage_lock <init|final> : ledger 와 모델 출력 hash 를 단계별로 잠근다(순위/GT 오류 계산 전).
analyze <init|final>    : lock 검증 후 고정 분석 1회. 결과 디렉터리는 임시 경로에 모두 쓴 뒤 한 번에 rename (부분 산출물이 최종 이름으로 남지 않음). 같은 입력의 기존 결과는 재검증 후 재사용.
judge  : 확대 규칙·최종 판정 입력(비용 포함) 기록. seal: 독립 verifier PASS 가 현재 파일 hash 와 일치할 때만 completion.
기존 산출물은 덮어쓰지 않는다.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import nr113_core as B
import nr114_core as C
import nr114_mg as N
import nr114_cure as CU
import nr107_spec as S
from report86_common import ROOT, sha, sha_obj

R114 = ROOT / "results/iter_114"
AN = R114 / "analysis_r1"  # r0 (results/iter_114/analysis)는 대상 MG box 범위 검사 누락으로 대체된 기록으로 보존
DATA = R114 / "data"
CODE = ["nr114_core.py", "nr114_run.py", "nr114_verify.py", "nr114_tests.py", "nr114_mg.py", "nr114_cure.py", "nr113_core.py", "nr107_geom.py", "nr107_spec.py",
        "mg45_mg.py", "pg43_run.py", "pg39_data.py", "pg39_spec.py", "report86_common.py", "rsna_diag/generate.py", "rsna_diag/geometry.py", "rsna_diag/parse.py",
        "nr114_data.py", "nr114_devcheck.py", "nr114_weights.py", "nr114_cost.py"]


def wjson(p, obj):
    p = Path(p)
    if p.exists():
        raise SystemExit(f"refuse to overwrite {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.link(tmp, p)
    tmp.unlink()


# ---------------------------------------------------------------- link
def mg_by_item(run, stage, model):
    d = ROOT / run
    mp = json.loads((d / "mapping.json").read_text())
    assert mp["stage"] == stage and mp["model"] == model
    comp = json.loads((d / "completion.json").read_text())
    for name, h in comp["files"].items():
        assert sha(d / name) == h, f"top completion hash differs {name}"
    recs, digest = N.verify_all(d, stage, model, mp["workers"])
    assert comp["scientific_digest"] == digest
    by = {}
    for r in recs:
        assert r["item_key"] not in by, "duplicate item in MG output"
        by[r["item_key"]] = r
    return by, comp


def cure_by_id(run, stage):
    d = ROOT / run
    mp = json.loads((d / "mapping.json").read_text())
    assert mp["stage"] == stage
    nw = mp["workers"]
    sd = sha_obj(CU.scientific_protocol(stage, nw))
    top = json.loads((d / "completion.json").read_text())
    assert top["scientific_digest"] == sd
    rows = []
    for k in range(nw):
        sdir = CU.shard_dir(d, k)
        assert sha(sdir / "completion.json") == top["files"][f"cure/shard{k}/completion.json"]
        c, recs = CU.verify_completion(sdir, stage, k, nw, sd)
        rows += recs
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate CURE ids"
    return {r["id"]: r for r in rows}, top


def link(stage, a_run, p_run, c_run):
    items = CU.stage_items(stage)
    raw = CU.raw_map(stage)
    A, a_comp = mg_by_item(a_run, stage, "A")
    P, p_comp = mg_by_item(p_run, stage, "MSPC")
    CR, c_comp = cure_by_id(c_run, stage)
    if {it["item_key"] for it in items} != set(A) or set(A) != set(P):
        raise C.LinkError("MG item sets differ from stage items")
    if set(CR) != {S.request_id(it["ImageID"], it["finding_index"]) for it in items}:
        raise C.LinkError("CURE request set differs from stage items")
    ledger = []
    for it in items:
        bad = []
        a, p = A[it["item_key"]], P[it["item_key"]]
        c = CR[S.request_id(it["ImageID"], it["finding_index"])]
        if sha(raw[it["ImageID"]]["raw_path"]) != raw[it["ImageID"]]["sha256"] or raw[it["ImageID"]]["sha256"] != it["image_meta"]["raw_png_sha256"]:
            bad.append("raw_image_sha")
        if c["image_sha256"] != it["image_meta"]["raw_png_sha256"] or c["prompt"] != S.pg_prompt(it["sentence"]) or c["item_key"] != it["item_key"]:
            bad.append("cure_request_fields")
        for nm, r in (("mg_A", a), ("mg_mspc", p)):
            if r["sentence_sha256"] != it["sentence_sha256"] or r["u8_pixel_sha256"] != it["image_meta"]["u8_pixel_sha256"] or r["ImageID"] != it["ImageID"]:
                bad.append(nm + "_identity")
        det_a, det_p = a["detection"], p["detection"]
        bad += C.mg_target_defects(det_a)
        bad += C.mspc_defects(det_p)
        try:
            B.check_boxes("gt", it["gt"])
            if it["extra"]:
                B.check_boxes("extra", it["extra"])
        except B.LinkError as e:
            bad.append(str(e))
        att = c["attempts"][-1]
        eos = bool(att["ended_eos"]) and att["finish_reason"] == "eos"
        pr = S.parse_pg(c["text"], eos)
        led = {"item_key": it["item_key"], "PatientID": it["PatientID"], "ImageID": it["ImageID"], "finding_index": it["finding_index"],
               "sentence_sha256": it["sentence_sha256"], "stage": stage, "cure_request_id": c["id"], "mg_A_request_id": a["request_id"],
               "mspc_request_id": p["request_id"], "cure_status": pr["status"], "cure_ended_eos": eos, "n_gt": len(it["gt"]), "n_alt": len(it["extra"]),
               "M": det_a["boxes_orig_xyxy"], "M_scores": det_a["scores"], "C": pr["boxes"], "P": det_p["boxes_orig_xyxy"], "P_scores": det_p["scores"],
               "GT": it["gt"], "ALT": it["extra"], "core": it["core"], "cure_text": c["text"], "cure_attempts": len(c["attempts"])}
        if bad:
            led["excluded_from_ranking"] = "technical:" + ",".join(bad)
        elif pr["status"] not in ("valid_nonempty", "no_box"):
            led["excluded_from_ranking"] = f"cure_{pr['status']}"
        ledger.append(led)
    return ledger, {"mg_A_completion": a_comp, "mg_mspc_completion": p_comp, "cure_completion": c_comp}


def run_args(stage):
    """각 단계의 모델 출력 디렉터리(런칭 시 고정된 이름)."""
    return json.loads((AN / f"runs_{stage}.json").read_text())


def cmd_register(stage, a_run, p_run, c_run):
    wjson(AN / f"runs_{stage}.json", {"stage": stage, "A": a_run, "MSPC": p_run, "CURE": c_run})


def input_hashes(stage_names):
    h = {}
    for st in stage_names:
        r = run_args("init" if st == "INIT" else "expand")
        for k in ("A", "MSPC", "CURE"):
            d = ROOT / r[k]
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.suffix in (".json", ".jsonl") and "partial" not in p.name and "launch" not in p.name and "resource" not in p.name:
                    h[f"{st}/{k}/{p.relative_to(d)}"] = sha(p)
    return h


def cmd_lock():
    """본출력 전 잠금. r1: INIT 출력 이후(대체된 r0 분석의 구현 오류 수정)에 만든 재잠금이므로 amendment 로 사실대로 기록하고 EXPAND 출력이 아직 없어야 한다."""
    tests = R114 / "tests/fixtures_core_r1.json"
    if not tests.exists() or not json.loads(tests.read_text()).get("all_pass"):
        raise SystemExit("fixtures must pass before lock")
    if any((R114 / "mg").glob("EXPAND_*")) or any((R114 / "cure").glob("EXPAND*")):
        raise SystemExit("EXPAND outputs already exist: cannot claim a pre-EXPAND lock")
    sel = json.loads((DATA / "selection_lock.json").read_text())
    dev = json.loads((R114 / "dev/devcheck.json").read_text())
    v0 = R114 / "analysis"
    proto = {"locked_at_unix": time.time(), "locked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "revision": "r1", "tag": C.TAG, "seed": C.SEED,
             "boot_n": C.BOOT_N, "ci_percentiles": list(C.CI_Q), "min_effect": C.MIN_EFFECT, "review_frac": "ceil(N/4)", "thr_key": B.THR_KEY, "err_iou": B.ERR_IOU,
             "rules": C.__doc__, "code_sha256": {f: sha(ROOT / f) for f in CODE}, "selection_lock_sha256": sha(DATA / "selection_lock.json"), "items_sha256": sel["items_sha256"],
             "cohort_summary_sha256": sha(DATA / "cohort_summary.json"), "exposure_ledger_sha256": sha(DATA / "exposure_ledger.json"),
             "devcheck_sha256": sha(R114 / "dev/devcheck.json"), "mspc_floor_met": dev["MSPC_meets_floor"],
             "weights_lock_sha256": sha(R114 / "protocol/weights_lock.json"), "mg_ckpt_sha256": {k: v["sha256"] for k, v in N.CKPT.items()},
             "request_sha256": {f"{st}_{m}": sha_obj(N.requests_for(st, m)) for st in ("INIT", "EXPAND") for m in ("A", "MSPC")},
             "cure_requests_sha256": {st: sha_obj(CU.requests(st)) for st in ("INIT", "EXPAND")}, "fixtures_sha256": sha(tests),
             "amendment": {"supersedes": "results/iter_114/analysis (r0)", "r0_protocol_sha256": sha(v0 / "protocol.json"), "r0_protocol_locked_before_INIT_outputs": True,
                           "r0_files_present": sorted(str(p.relative_to(v0)) for p in v0.rglob("*") if p.is_file() and "partial" not in p.name),
                           "reason": "r0 link 가 대상 MG(A) 출력의 box 범위/퇴화 검사(iter_113 check_boxes('mg'))를 빠뜨렸다. 독립 verifier 가 INIT 에서 y 범위를 벗어난 A box 1개(item 5cc1e30b95c41696)를 발견했다. 원 규칙 구현 오류 수정이며 새로운 과학적 기준이 아니다. r0 INIT 결과(N=47)는 보존하되 판정·확대 결정에 쓰지 않는다.",
                           "seen_before_r1_lock": "r0 INIT 분석 결과(점추정 포함)를 본 뒤에 r1 을 잠갔다. EXPAND 모델 출력은 r1 잠금 이후에 생성한다."},
             "note": "r1 lock: INIT outputs existed (generated under r0 lock); EXPAND outputs absent at lock time"}
    wjson(AN / "protocol.json", proto)
    print("locked", proto["locked_at_utc"])


def verify_protocol():
    p = json.loads((AN / "protocol.json").read_text())
    for f, h in p["code_sha256"].items():
        if sha(ROOT / f) != h:
            raise SystemExit(f"code changed after lock: {f}")
    return p


def cmd_stage_lock(stage):
    p = verify_protocol()
    names = ["INIT"] if stage == "init" else ["INIT", "EXPAND"]
    led = []
    glob = {}
    for st in names:
        r = run_args("init" if st == "INIT" else "expand")
        l, g = link(st, r["A"], r["MSPC"], r["CURE"])
        led += l
        glob[st] = g
    wjson(AN / f"ledger_{stage}.json", {"ledger": led, "summary": {"n": len(led)}, "completions": glob})
    wjson(AN / f"stage_lock_{stage}.json", {"locked_at_unix": time.time(), "locked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stage": stage,
                                            "protocol_sha256": sha(AN / "protocol.json"), "ledger_sha256": sha(AN / f"ledger_{stage}.json"),
                                            "input_sha256": input_hashes(names),
                                            "note": "ranking and GT-error not computed before this lock"})
    print("stage lock", stage, len(led))


def verify_stage_lock(stage):
    verify_protocol()
    names = ["INIT"] if stage == "init" else ["INIT", "EXPAND"]
    sl = json.loads((AN / f"stage_lock_{stage}.json").read_text())
    if sl["protocol_sha256"] != sha(AN / "protocol.json") or sl["ledger_sha256"] != sha(AN / f"ledger_{stage}.json") or sl["input_sha256"] != input_hashes(names):
        raise SystemExit("inputs changed after stage lock")
    return sl


def cmd_analyze(stage):
    sl = verify_stage_lock(stage)
    final = AN / f"result_{stage}"
    digest = sl["ledger_sha256"] + sl["protocol_sha256"]
    if final.exists():
        st = json.loads((final / "state.json").read_text())
        if st["input_digest"] != digest:
            raise SystemExit("existing result directory belongs to different inputs; refuse")
        for f, h in st["files"].items():
            if sha(final / f) != h:
                raise SystemExit(f"existing result file changed: {f}")
        print("reuse verified existing", final)
        return
    led = json.loads((AN / f"ledger_{stage}.json").read_text())["ledger"]
    t0 = time.time()
    res, ent, boot = C.analyze(led)
    res["analysis_wall_s"] = time.time() - t0
    res["protocol_locked_at_utc"] = json.loads((AN / "protocol.json").read_text())["locked_at_utc"]
    res["stage"] = stage
    res["gpu_used"] = 0
    tmp = AN / f"result_{stage}.partial.{os.getpid()}"
    tmp.mkdir()
    (tmp / "report.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    sel_all = {k: set(v) for k, v in res["selected"].items()}
    (tmp / "per_item.json").write_text(json.dumps([{k: v for k, v in e.items() if k != "tk"} | {"tie_hash": e["tk"][0], "sel_cure": e["item_key"] in sel_all["cure"],
                                                    "sel_mspc": e["item_key"] in sel_all["mspc"], "sel_conf": e["item_key"] in sel_all["confidence"]} for e in ent], indent=1))
    (tmp / "bootstrap.json").write_text(json.dumps(boot))
    files = {f: sha(tmp / f) for f in ("report.json", "per_item.json", "bootstrap.json")}
    (tmp / "state.json").write_text(json.dumps({"input_digest": digest, "files": files}, indent=1))
    os.rename(tmp, final)
    print(json.dumps({k: res[k] for k in ("N", "K", "n_patients", "capture", "dA", "dB", "n_errors_official")}), "wall", res["analysis_wall_s"])
    print(json.dumps(res["bootstrap"]))


def n_remaining():
    cs = json.loads((DATA / "cohort_summary.json").read_text())
    return sum(1 for x in cs["patient_order"] if x["stage"] == "expand")


def cmd_expansion():
    rep = json.loads((AN / "result_init/report.json").read_text())
    dec = C.expansion_decision(rep, n_remaining())
    dec["decided_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    dec["init_report_sha256"] = sha(AN / "result_init/report.json")
    wjson(AN / "expansion_decision.json", dec)
    print(json.dumps(dec, indent=1))


def cmd_judge(cost_path):
    stage = "final" if (AN / "result_final").exists() else "init"
    rep = json.loads((AN / f"result_{stage}/report.json").read_text())
    cost = json.loads(Path(cost_path).read_text())
    j = C.judge(rep, cost["mspc_cost_le_cure"])
    j.update({"based_on_stage": stage, "report_sha256": sha(AN / f"result_{stage}/report.json"), "cost_sha256": sha(cost_path)})
    wjson(AN / "judge.json", j)
    print(json.dumps(j, indent=1))


def cmd_seal():
    stages = [st for st in ("init", "final") if (AN / f"result_{st}").exists()]
    verifies = {}
    for st in stages:
        vp = AN / f"verify_{st}.json"
        if not vp.exists():
            raise SystemExit(f"missing verification for {st}")
        v = json.loads(vp.read_text())
        if not v.get("all_pass"):
            raise SystemExit(f"verification not PASS: {st}")
        cur = {f: sha(AN / f) for f in v["verified_files"]}
        if cur != v["verified_files"]:
            raise SystemExit(f"stale PASS: verified files changed after verification ({st})")
        verifies[st] = sha(vp)
    verify_protocol()
    files = {str(p.relative_to(AN)): sha(p) for p in sorted(AN.rglob("*")) if p.is_file() and "partial" not in p.name and p.name != "completion.json"}
    wjson(AN / "completion.json", {"status": "complete", "verify_all_pass": True, "verify_sha256": verifies, "files": files,
                                   "sealed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "register":
        cmd_register(*sys.argv[2:6])
    elif cmd == "lock":
        cmd_lock()
    elif cmd == "stage_lock":
        cmd_stage_lock(sys.argv[2])
    elif cmd == "analyze":
        cmd_analyze(sys.argv[2])
    elif cmd == "expansion":
        cmd_expansion()
    elif cmd == "judge":
        cmd_judge(sys.argv[2])
    elif cmd == "seal":
        cmd_seal()
    else:
        raise SystemExit("unknown command")
