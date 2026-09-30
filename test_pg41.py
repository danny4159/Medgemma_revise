"""iter_041 CPU 합성 fixture: pg41_run의 completion 검증·잠금·부분 행·claim 및 ID 반전 처리를 검사한다.

python test_pg41.py --out results/iter_041/tests/fixtures_pg41.json --work results/iter_041/tests/cpu
"""
import argparse
import copy
import glob
import json
import os
import shutil
import subprocess
import sys

import pg39_spec as S
import pg41_run as R

RES = []


def check(name, ok, detail=None):
    RES.append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:300], flush=True)


def raises(fn, exc=R.RunError):
    try:
        fn()
    except exc as e:
        return str(e)[:120]
    return None


def make_rec(row, pdig, cdig, adig, worker=0, t=1000.0):
    rec = {"request_id": row["request_id"], "row_digest": R.row_digest(row), "cond": row["cond"], "patient": row["patient"],
           "targets": row["targets"], "kind": row["kind"], "prompt_sha256": row["prompt_sha256"], "image": row["image"],
           "input_pixel_sha256": row["input_pixel_sha256"], "pad_affine_top_left_side": [0, 0, 1], "n_input_tokens": 1,
           "input_ids_sha256": "x", "suffix_ids": [1], "suffix_text_raw": "[]<end_of_turn>", "n_output_tokens": 1,
           "finish_reason": "eos", "ended_eos": True, "final_cap": row["caps"][0], "attempts": [{"n_new": 1}],
           "runtime_s_total": 1.0, "wall_s": 1.0, "t_start": t, "peak_mem_alloc_gb_max": 1.0, "peak_mem_reserved_gb_max": 1.0,
           "protocol_digest": pdig, "config_digest": cdig, "adapter_digest": adig, "worker": worker, "ts": t + 1, "gpu_uuid": "u"}
    rec["record_digest"] = R.record_digest(rec)
    return rec


def build(work, rows, name, lock=None, mutate_rows=None):
    d = os.path.join(work, name)
    os.makedirs(d, exist_ok=True)
    req = os.path.join(d, "requests.jsonl")
    with open(req, "w") as f:
        for r in (mutate_rows(copy.deepcopy(rows)) if mutate_rows else rows):
            f.write(json.dumps(r) + "\n")
    proto = os.path.join(d, "protocol.json")
    p = R.make_protocol(req, proto, lock=lock)
    pdig, _ = R.verify_protocol(proto, req)
    rr = R.read_requests(req)
    out = os.path.join(d, "gen")
    os.makedirs(out)
    recs = [make_rec(r, pdig, p["generation_config_digest"], None) for r in rr]
    with open(os.path.join(out, "gen_worker0.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    comp = {"exit_codes": [0], "n_requests": len(recs), "protocol_digest": pdig,
            "worker_file_sha256": {"gen_worker0.jsonl": R.file_sha(os.path.join(out, "gen_worker0.jsonl"))}}
    json.dump(comp, open(os.path.join(out, "completion.json"), "w"))
    return d, req, proto, out, recs, comp


def rewrite(out, recs, redigest=True):
    with open(os.path.join(out, "gen_worker0.jsonl"), "w") as f:
        for r in recs:
            if redigest:
                r["record_digest"] = R.record_digest(r)
            f.write(json.dumps(r) + "\n")
    comp = json.load(open(os.path.join(out, "completion.json")))
    comp["worker_file_sha256"] = {"gen_worker0.jsonl": R.file_sha(os.path.join(out, "gen_worker0.jsonl"))}
    json.dump(comp, open(os.path.join(out, "completion.json"), "w"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out) or (os.path.exists(a.work) and os.listdir(a.work)):
        sys.exit("output or work dir exists")
    os.makedirs(a.work, exist_ok=True)
    rows = [json.loads(l) for l in open("results/iter_041/requests/requests_V96_JAB.jsonl")][:4]
    lock_f = os.path.join(a.work, "lockme.txt")
    open(lock_f, "w").write("gt manifest stand-in")
    d, req, proto, out, recs, comp = build(a.work, rows, "base", lock=[lock_f])
    check("valid_synthetic_completion_passes", len(R.verify_completion(out, req, proto)) == 4)

    # 1 record 내용 변조 (digest 유지)
    bad = copy.deepcopy(recs)
    bad[0]["suffix_text_raw"] = "[x]"
    rewrite(out, bad, redigest=False)
    check("tampered_record_content_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    rewrite(out, copy.deepcopy(recs))
    # 2 duplicate / missing / extra
    rewrite(out, recs + [recs[0]])
    check("duplicate_record_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    rewrite(out, recs[:3])
    check("missing_record_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    ex = copy.deepcopy(recs[0])
    ex["request_id"] = "unexpected"
    rewrite(out, recs + [ex])
    check("extra_record_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    rewrite(out, copy.deepcopy(recs))
    check("restored_completion_passes_again", len(R.verify_completion(out, req, proto)) == 4)
    # 3 record 필드가 요청 행과 다름 (조건·target·pixel·adapter·config)
    for k, v in (("cond", "J-short-rev"), ("targets", ["qA"]), ("input_pixel_sha256", "0" * 64), ("adapter_digest", "abc"),
                 ("config_digest", "0" * 64), ("prompt_sha256", "0" * 64)):
        b2 = copy.deepcopy(recs)
        b2[1][k] = v
        rewrite(out, b2)
        check(f"record_field_mismatch_rejected:{k}", raises(lambda: R.verify_completion(out, req, proto)))
    rewrite(out, copy.deepcopy(recs))
    # 4 completion 변조: exit code, worker file set
    c0 = json.load(open(os.path.join(out, "completion.json")))
    c1 = dict(c0, exit_codes=[1])
    json.dump(c1, open(os.path.join(out, "completion.json"), "w"))
    check("nonzero_exit_code_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    json.dump(c0, open(os.path.join(out, "completion.json"), "w"))
    shutil.copy(os.path.join(out, "gen_worker0.jsonl"), os.path.join(out, "gen_worker9.jsonl"))
    check("unlisted_worker_file_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    os.remove(os.path.join(out, "gen_worker9.jsonl"))
    # 5 잠금 파일(GT manifest 대용)·요청 파일·코드 hash 변경
    open(lock_f, "a").write("x")
    check("locked_file_change_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    open(lock_f, "w").write("gt manifest stand-in")
    check("locked_file_restored_passes", len(R.verify_completion(out, req, proto)) == 4)
    p = json.load(open(proto))
    p2 = dict(p, code=dict(p["code"], **{"pg39_spec.py": "0" * 64}))
    proto2 = os.path.join(d, "protocol_badcode.json")
    json.dump(p2, open(proto2, "w"))
    check("code_hash_change_rejected", raises(lambda: R.verify_protocol(proto2, req)))
    with open(req, "a") as f:
        f.write("\n")
    check("requests_file_change_rejected", raises(lambda: R.verify_completion(out, req, proto)))
    # 6 현재 영상 file/pixel hash가 요청 행과 다름 (요청 자체의 hash가 틀린 경우)
    for k in ("image_file_sha256", "input_pixel_sha256"):
        def mut(rs, k=k):
            rs[0][k] = "0" * 64
            return rs
        d2, req2, proto2_, out2, _, _ = build(a.work, rows, f"badimg_{k}", mutate_rows=mut)
        check(f"current_image_hash_mismatch_rejected:{k}", raises(lambda: R.verify_completion(out2, req2, proto2_)))
    # 7 부분 행 원본 바이트 보존
    pf = os.path.join(a.work, "partial.jsonl")
    with open(pf, "wb") as f:
        f.write(b'{"a": 1}\n{"request_id": "torn", "x": ')
    n = R.repair_tail(pf)
    kept = glob.glob(pf + ".partial.*.bin")
    check("partial_row_truncated_and_bytes_preserved", n > 0 and len(kept) == 1 and open(kept[0], "rb").read() == b'{"request_id": "torn", "x": '
          and open(pf, "rb").read() == b'{"a": 1}\n' and os.path.exists(pf + ".repair.log"))
    with open(pf, "ab") as f:
        f.write(b'{"partial')
    check("read_records_ignores_in_progress_tail", R.read_records(pf) == [{"a": 1}])
    # 8 단일 소유권 / claim
    lk = os.path.join(a.work, "x.lock")
    fd = R.try_flock(lk)
    check("second_claim_on_same_file_refused_while_held", fd is not None and R.try_flock(lk) is None)
    os.close(fd)
    check("claim_reacquirable_after_owner_release", R.try_flock(lk) is not None)
    # 9 완료된 out-dir 재실행 거부 (worker는 모델 로딩 전에 거부해야 한다)
    r = subprocess.run([sys.executable, "pg41_run.py", "worker", "--requests", req2, "--protocol", proto2_, "--out-dir", out2,
                        "--worker", "0"], capture_output=True, text=True, timeout=120)
    check("worker_rerun_into_completed_dir_refused_before_model_load", r.returncode != 0 and "completion.json exists" in r.stderr, r.stderr[-150:])
    # 10 ID 반전: J-short-rev는 문장 순서만 바뀌고 ID·targets 유지, 채점은 라벨 기준
    rr = [json.loads(l) for l in open("results/iter_041/requests/requests_V96_JBA.jsonl")][:5]
    ok_ids = all(r["targets"] == ["qA", "qB"] and r["prompt"].index('qB: "') < r["prompt"].index('qA: "') and r["cond"] == "J-short-rev" for r in rr)
    check("reversed_prompt_lists_qB_first_keeps_ids_and_targets", ok_ids)
    raw1 = '[{"box_2d": [10, 10, 100, 100], "label": "qA"}, {"box_2d": [500, 500, 600, 600], "label": "qB"}]<end_of_turn>'
    raw2 = '[{"box_2d": [500, 500, 600, 600], "label": "qB"}, {"box_2d": [10, 10, 100, 100], "label": "qA"}]<end_of_turn>'
    g1 = S.parse_ids(raw1, True, {"qA", "qB"})["groups"]
    g2 = S.parse_ids(raw2, True, {"qA", "qB"})["groups"]
    check("group_assignment_by_label_independent_of_listing_order", g1 == g2 and g1["qA"] == [[10, 10, 100, 100]] and g1["qB"] == [[500, 500, 600, 600]])
    # 11 요청 파일: 중복 request_id 거부
    dup = os.path.join(a.work, "dup.jsonl")
    with open(dup, "w") as f:
        f.write(json.dumps(rows[0]) + "\n" + json.dumps(rows[0]) + "\n")
    check("duplicate_request_id_in_requests_file_rejected", raises(lambda: R.read_requests(dup)))
    # 12 occupancy: 겹치는 worker 구간은 중복 합산하지 않는다
    recs_o = [{"worker": 0, "t_start": 0, "ts": 10}, {"worker": 1, "t_start": 5, "ts": 15}, {"worker": 2, "t_start": 100, "ts": 110}]
    o = R.occupancy(recs_o, os.path.join(a.work, "none"), {0: 0, 1: 0, 2: 1}, 200.0)
    check("device_seconds_union_no_double_count", abs(o["device_seconds_generate_union"] - (15 + 10)) < 1e-9, o)
    json.dump({"results": RES, "n_pass": sum(x["pass"] for x in RES), "n": len(RES)}, open(a.out, "x"), indent=1, default=str)
    print(f"{sum(x['pass'] for x in RES)}/{len(RES)} PASS")
    sys.exit(0 if all(x["pass"] for x in RES) else 1)


if __name__ == "__main__":
    main()
