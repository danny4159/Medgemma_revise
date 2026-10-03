"""iter_054 기술 단계 runtime 검사: worker 수 변경 재개, 중복 claim, 부분 행 보존, 요청·입력·raw·protocol·gate 변조 거부, 비용 집계, 입력 누출.
각 변조 검사는 의도한 거부 분기(메시지 부분 문자열)에서 실패해야 통과한다. 결과: tests/runtime_checks.json (all_pass)."""
import copy
import glob
import json
import os
import shutil
import subprocess
import sys

import mc54_run as RUN
import mc54_spec as S

REQ = "results/iter_054/data/requests.jsonl"
PROTO = "results/iter_054/protocol/protocol_tech.json"
REF, CMP, RES = "results/iter_054/raw/tech_ref_w2", "results/iter_054/raw/tech_cmp_w4", "results/iter_054/raw/tech_resume"
OUT = "results/iter_054/tests/runtime_checks_v2.json"
TMP = "results/iter_054/tests/tamper_v2"
checks = []


def chk(name, ok, **info):
    checks.append({"name": name, "pass": bool(ok), **info})
    print("PASS" if ok else "FAIL", name, {k: (v if len(str(v)) < 200 else str(v)[:200]) for k, v in info.items()}, flush=True)


def recs_of(d):
    out = {}
    for fn in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
        for r in RUN.read_records(fn):
            out[r["request_id"]] = r
    return out


def expect_fail(name, fn, needle):
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        chk(name, needle in str(e), expected=needle, got=str(e)[:160])
        return
    chk(name, False, expected=needle, got="no exception")


def rewrite(dir_, mutate, fix_sha=True):
    """dir_의 worker 파일들을 읽어 mutate(list_of_(file, records))를 적용 후 다시 쓰고, record digest·completion sha를 맞춘다."""
    files = sorted(glob.glob(os.path.join(dir_, "gen_worker*.jsonl")))
    data = {fn: RUN.read_records(fn) for fn in files}
    mutate(data)
    for fn, recs in data.items():
        for r in recs:
            r["record_digest"] = RUN.record_digest(r)
        with open(fn, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
    if fix_sha:
        cp = os.path.join(dir_, "completion.json")
        c = json.load(open(cp))
        c["worker_file_sha256"] = {os.path.basename(f): RUN.file_sha(f) for f in files}
        json.dump(c, open(cp, "w"))


def fresh(case):
    d = os.path.join(TMP, case)
    shutil.copytree(REF, d, ignore=shutil.ignore_patterns("claims", "*.stdout", "*.stderr", "*.lock", "resource_log.jsonl"))
    return d


def main():
    if os.path.exists(OUT):
        sys.exit("exists")
    rows = RUN.read_requests(REQ)
    by_id = {r["request_id"]: r for r in rows}
    tech_ids = {r["request_id"] for r in rows if r["stage"] == "tech"}
    # C1: 세 실행 모두 완료 검증 통과
    rs = {}
    for name, d in (("ref_w2", REF), ("cmp_w4", CMP), ("resume", RES)):
        recs = RUN.verify_completion(d, REQ, PROTO)
        rs[name] = {r["request_id"]: r for r in recs}
        chk(f"C1_verify_completion_{name}", len(recs) == 252 and set(rs[name]) == tech_ids, n=len(recs))
    # C2: worker 구성 간 출력 일치 (같은 요청·같은 batch=1)
    mx = {"gd_margin": 0.0, "ps_mean": 0.0, "ps_sum": 0.0}
    mc_diff = 0
    for rid in tech_ids:
        a = rs["ref_w2"][rid]["payload"]
        for other in ("cmp_w4", "resume"):
            b = rs[other][rid]["payload"]
            k = by_id[rid]["kind"]
            if k == "mc":
                mc_diff += a["suffix_ids"] != b["suffix_ids"]
            elif k == "gd":
                mx["gd_margin"] = max(mx["gd_margin"], abs(a["shown_margin"] - b["shown_margin"]))
            else:
                mx["ps_mean"] = max(mx["ps_mean"], abs(a["mean_ll"] - b["mean_ll"]))
                mx["ps_sum"] = max(mx["ps_sum"], abs(a["sum_ll"] - b["sum_ll"]))
                if a["ans_ids"] != b["ans_ids"]:
                    mc_diff += 1
    chk("C2_outputs_consistent_across_worker_configs", mc_diff == 0 and mx["gd_margin"] < 1e-3 and mx["ps_mean"] < 1e-3,
        mc_token_mismatch=mc_diff, **mx, n_requests=len(tech_ids), compared=["ref_w2 vs cmp_w4", "ref_w2 vs resume"])
    # C3: 재개 — 첫 attempt 강제 종료, 이후 worker 3개, 찢어진 행 보존
    evs = RUN.jl(os.path.join(RES, "events.jsonl"))
    starts = [e for e in evs if e["event"] == "launch_start"]
    ends = [e for e in evs if e["event"] == "launch_end"]
    wstart = [e for e in evs if e["event"] == "worker_start"]
    wend = [e for e in evs if e["event"] == "worker_end"]
    rep = RUN.jl(os.path.join(RES, "gen_worker0.jsonl.repair.log")) if os.path.exists(os.path.join(RES, "gen_worker0.jsonl.repair.log")) else []
    parts = glob.glob(os.path.join(RES, "gen_worker0.jsonl.partial.*.bin"))
    chk("C3_resume_changed_worker_count_and_preserved_torn_row",
        len(starts) == 2 and [s["workers"] for s in starts] == [2, 3] and len(ends) == 1 and len(wstart) == 5 and len(wend) == 3
        and len(rep) == 1 and len(parts) == 1 and open(parts[0], "rb").read().startswith(b'{"request_id": "torn_partial_row"')
        and rep[0]["preserved_sha256"] == RUN.sha_bytes(open(parts[0], "rb").read()),
        launches=[s["workers"] for s in starts], mappings=[s["mapping"] for s in starts], worker_starts=len(wstart), worker_ends=len(wend),
        repair=rep)
    # C4: 중복 요청 없음, 각 요청 정확히 1 record (claim 경쟁이 있던 4-worker·3-worker 실행 포함)
    for name, d in (("cmp_w4", CMP), ("resume", RES)):
        allr = [r["request_id"] for fn in glob.glob(os.path.join(d, "gen_worker*.jsonl")) for r in RUN.read_records(fn)]
        chk(f"C4_no_duplicate_records_{name}", len(allr) == len(set(allr)) == 252, n=len(allr),
            workers_that_wrote=sorted({r["worker"] for r in recs_of(d).values()}))
    # C5: 비용 집계 — 같은 범위, 강제 종료 attempt는 하한 표시
    c_res = RUN.cost_report([RES])
    c_ref = RUN.cost_report([REF])
    chk("C5_cost_report_all_attempts",
        c_res["n_procs_without_end_lower_bound"] == 2 and c_res["device_seconds_incl_loading_union"] >= c_res["device_seconds_generate_union"] > 0
        and c_ref["n_procs_without_end_lower_bound"] == 0 and c_ref["device_seconds_incl_loading_union"] >= c_ref["device_seconds_generate_union"],
        resume=dict((k, v) for k, v in c_res.items() if k != "attempts"), ref=dict((k, v) for k, v in c_ref.items() if k != "attempts"))
    # C6: 입력 누출 — 추론 행에 pair/정답/caption/category 없음, prompt에 caption 문장 없음
    ds = json.load(open("results/iter_054/source/data__dataset.json"))
    caps = {c.strip() for d in ds.values() for c in (d["cap_1"], d["cap_2"]) if len(c.strip()) > 30}
    leak = sum(any(c in r["prompt"] or c in (r["assistant_text"] or "") for c in caps) for r in rows)
    keys = {k for r in rows for k in r}
    chk("C6_no_label_caption_leak_in_inference_rows", leak == 0 and not ({"pair", "truth", "correct", "caption", "category"} & keys),
        n_rows=len(rows), caption_hits=leak, row_keys=sorted(keys))
    # C7: 완료된 out-dir 재실행 거부
    r = subprocess.run([sys.executable, "mc54_run.py", "launch", "--stage", "tech", "--requests", REQ, "--protocol", PROTO,
                        "--out-dir", REF, "--workers", "1"], capture_output=True, text=True)
    chk("C7_completed_outdir_rerun_refused", r.returncode != 0 and "completion.json exists" in r.stderr, rc=r.returncode, err=r.stderr[-200:])
    # C8: 변조 거부 — 각 사례가 의도한 분기에서 실패
    os.makedirs(TMP, exist_ok=True)

    def case(name, mut, needle, fix_sha=True, req=REQ, proto=PROTO):
        d = fresh(name)
        if mut is not None:
            rewrite(d, mut, fix_sha)
        expect_fail(f"C8_{name}", lambda: RUN.verify_completion(d, req, proto), needle)

    def first(data, pred):
        for fn, recs in data.items():
            for r in recs:
                if pred(r):
                    return fn, r
        raise RuntimeError("no record")

    def m_payload(data):
        _, r = first(data, lambda r: r["kind"] == "gd")
        r["payload"]["logit_A"] += 1.0
    d1 = fresh("payload_edit_no_digest_fix")
    fn, = [sorted(glob.glob(os.path.join(d1, "gen_worker*.jsonl")))[0]]
    recs = RUN.read_records(fn)
    g = next(r for r in recs if r["kind"] == "gd")
    g["payload"]["logit_A"] += 1.0  # record_digest 갱신 안 함
    with open(fn, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    c = json.load(open(os.path.join(d1, "completion.json")))
    c["worker_file_sha256"] = {os.path.basename(x): RUN.file_sha(x) for x in glob.glob(os.path.join(d1, "gen_worker*.jsonl"))}
    json.dump(c, open(os.path.join(d1, "completion.json"), "w"))
    expect_fail("C8_payload_edit_detected_by_record_digest", lambda: RUN.verify_completion(d1, REQ, PROTO), "record digest mismatch")
    d2 = fresh("file_changed_after_completion")
    fn2 = sorted(glob.glob(os.path.join(d2, "gen_worker*.jsonl")))[0]
    with open(fn2, "ab") as f:
        f.write(b"\n")
    expect_fail("C8_worker_file_changed_after_completion", lambda: RUN.verify_completion(d2, REQ, PROTO), "worker file changed after completion")
    case("deleted_record", lambda data: next(iter(data.values())).pop(), "request set mismatch")
    case("duplicated_record", lambda data: next(iter(data.values())).append(copy.deepcopy(next(iter(data.values()))[0])), "request set mismatch")

    def m_proto(data):
        _, r = first(data, lambda r: True)
        r["protocol_digest"] = "0" * 64
    case("record_wrong_protocol_digest", m_proto, "protocol/config mismatch")

    def m_text(data):
        _, r = first(data, lambda r: r["modality"] == "text")
        r["n_image_tokens"] = 256
    case("text_record_claims_image_tokens", m_text, "text-only record carries image input")

    def m_img(data):
        _, r = first(data, lambda r: r["modality"] == "image")
        r["has_pixel_values"] = False
    case("image_record_without_pixels", m_img, "image record bad image tokens")

    def m_px(data):
        _, r = first(data, lambda r: r["modality"] == "image")
        r["input_pixel_sha256"] = "f" * 64
    case("image_record_wrong_pixel_hash", m_px, "input pixel hash mismatch")

    def m_alien(data):
        _, r = first(data, lambda r: True)
        r["request_id"] = "alien_request_id"
    case("alien_request_id", m_alien, "request set mismatch")  # 완료 검증은 집합 불일치로 먼저 거부
    d4 = fresh("alien_request_id_worker_resume_path")
    rewrite(d4, m_alien)
    wf = {fn: RUN.read_records(fn) for fn in glob.glob(os.path.join(d4, "gen_worker*.jsonl"))}
    expect_fail("C8_alien_request_id_rejected_by_worker_validation", lambda: RUN.validate_records(
        wf, by_id, {json.load(open(os.path.join(d4, "completion.json")))["protocol_digest"]},
        json.load(open(PROTO))["generation_config_digest"], lambda p: RUN.load_rgb(p)[1]), "unexpected record")

    def m_boundary(data):
        _, r = first(data, lambda r: r["kind"] == "ps")
        r["payload"]["boundary_ok"] = False
    case("ps_boundary_flag_false", m_boundary, "ps boundary flag false")

    def m_row(data):
        _, r = first(data, lambda r: True)
        r["row_digest"] = "1" * 64
    case("record_row_digest_mismatch", m_row, "row/prompt mismatch")
    d3 = fresh("completion_exit_code")
    c = json.load(open(os.path.join(d3, "completion.json")))
    c["exit_codes"] = [0, 1]
    json.dump(c, open(os.path.join(d3, "completion.json"), "w"))
    expect_fail("C8_completion_nonzero_exit", lambda: RUN.verify_completion(d3, REQ, PROTO), "completion protocol/stage/exit code invalid")
    # 요청 파일 변조 / protocol 코드 변조
    os.makedirs(os.path.join(TMP, "alt"), exist_ok=True)
    alt = os.path.join(TMP, "alt", "requests_altered.jsonl")
    lines = open(REQ).read().split("\n")
    r0 = json.loads(lines[0])
    r0["prompt"] += " "
    lines[0] = json.dumps(r0, sort_keys=True, ensure_ascii=False)
    open(alt, "w").write("\n".join(lines))
    expect_fail("C8_altered_requests_file", lambda: RUN.verify_completion(REF, alt, PROTO), "requests file changed")
    p = json.load(open(PROTO))
    p["code"]["mc54_spec.py"] = "0" * 64
    altp = os.path.join(TMP, "alt", "protocol_wrong_code.json")
    json.dump(p, open(altp, "w"))
    expect_fail("C8_protocol_code_hash_mismatch", lambda: RUN.verify_completion(REF, REQ, altp), "code changed since protocol lock")
    # requests rebuild 변조: 요청 파일에 맞춰 protocol 재작성하지 않은 채 source 변조는 불가 → 행 내용 변경 + sha 맞춘 protocol 로 rebuild 거부 확인
    p2 = json.load(open(PROTO))
    p2["requests_sha256"] = RUN.file_sha(alt)
    p2["requests_path"] = alt
    altp2 = os.path.join(TMP, "alt", "protocol_altered_requests_matching_sha.json")
    json.dump(p2, open(altp2, "w"))
    expect_fail("C8_rebuild_rejects_requests_not_from_locked_sources", lambda: RUN.verify_completion(REF, alt, altp2), "requests file != rebuilt")
    # C9: main stage gate 강제
    pm = os.path.join(TMP, "alt", "protocol_main_nogate.json")
    expect_fail("C9_main_protocol_requires_gate", lambda: RUN.make_protocol("main", REQ, pm), "requires --gate")
    gbad = os.path.join(TMP, "alt", "gate_not_run.json")
    json.dump({"run": False, "evidence": {}}, open(gbad, "w"))
    expect_fail("C9_gate_run_false_rejected", lambda: RUN.make_protocol("main", REQ, pm + "2", gbad, REF, PROTO), "technical gate run != true")
    ev_bad = os.path.join(TMP, "alt", "evidence_not_pass.json")
    json.dump({"all_pass": False}, open(ev_bad, "w"))
    gb2 = os.path.join(TMP, "alt", "gate_evidence_not_pass.json")
    json.dump({"run": True, "evidence": {"x": {"path": ev_bad, "sha256": RUN.file_sha(ev_bad), "require_all_pass": True}}}, open(gb2, "w"))
    expect_fail("C9_gate_evidence_not_all_pass_rejected", lambda: RUN.make_protocol("main", REQ, pm + "3", gb2, REF, PROTO), "evidence not all_pass")
    ev_ok = os.path.join(TMP, "alt", "evidence_pass.json")
    json.dump({"all_pass": True}, open(ev_ok, "w"))
    gb3 = os.path.join(TMP, "alt", "gate_evidence_hash_stale.json")
    json.dump({"run": True, "evidence": {"x": {"path": ev_ok, "sha256": "0" * 64, "require_all_pass": True}}}, open(gb3, "w"))
    expect_fail("C9_gate_evidence_hash_stale_rejected", lambda: RUN.make_protocol("main", REQ, pm + "4", gb3, REF, PROTO), "gate evidence changed")
    out = {"checks": checks, "all_pass": all(c["pass"] for c in checks), "n_checks": len(checks)}
    json.dump(out, open(OUT, "x"), indent=1)
    print("all_pass", out["all_pass"], len(checks))


if __name__ == "__main__":
    main()
