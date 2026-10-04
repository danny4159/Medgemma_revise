"""iter_066 CPU 변조·재개 검사 (GPU 불필요). 모든 임시 파일은 results/iter_066/tests/tamper/ 안에만 쓴다.
각 검사는 '의도한 분기'에서 실패해야 통과: 예외 메시지에 expect 문자열 포함."""
import copy
import json
import os
import shutil
import sys

import m66_run as R

T = "results/iter_066/tests/tamper"
REQ = "results/iter_066/data/requests_D.jsonl"
PROTO = "results/iter_066/protocol/D_main.json"
OUT = "results/iter_066/tests/tamper_result.json"


def expect(name, fn, needle, res):
    try:
        fn()
        res.append({"name": name, "pass": False, "why": "no error"})
    except Exception as e:  # noqa: BLE001
        res.append({"name": name, "pass": needle in str(e), "error": str(e)[:200], "expected_branch": needle})


def main():
    os.makedirs(T, exist_ok=True)
    rows = R.jl(REQ)
    res = []
    # 1 요청 파일 변조: 영상 순서 교환
    r1 = copy.deepcopy(rows)
    r1[0]["images"][0], r1[0]["images"][1] = r1[0]["images"][1], r1[0]["images"][0]
    p1 = f"{T}/req_swap_images.jsonl"
    open(p1, "w").write("\n".join(json.dumps(r) for r in r1) + "\n")
    expect("requests_differ_from_protocol(image swap)", lambda: R.verify_protocol(PROTO, p1), "requests differ", res)
    # 2 정답 필드 포함 요청 거부
    r2 = copy.deepcopy(rows)
    r2[0]["answer"] = "PRESENT"
    p2 = f"{T}/req_with_answer.jsonl"
    open(p2, "w").write("\n".join(json.dumps(r) for r in r2) + "\n")
    expect("inference_row_with_label_field", lambda: R.read_requests(p2), "evaluation field", res)
    # 3 prompt 해시 불일치
    r3 = copy.deepcopy(rows)
    r3[0]["prompt"] += " x"
    p3 = f"{T}/req_prompt.jsonl"
    open(p3, "w").write("\n".join(json.dumps(r) for r in r3) + "\n")
    expect("prompt_hash_mismatch", lambda: R.read_requests(p3), "prompt hash", res)
    # 4 중복 request_id
    p4 = f"{T}/req_dup.jsonl"
    open(p4, "w").write("\n".join(json.dumps(r) for r in rows + rows[:1]) + "\n")
    expect("duplicate_request_id", lambda: R.read_requests(p4), "duplicate", res)
    # 5 protocol 변조: 잠긴 labels hash 변경 / config(cand_batch) 변경
    pr = json.load(open(PROTO))
    a = copy.deepcopy(pr)
    k = next(iter(a["locked_files"]))
    a["locked_files"][k] = "0" * 64
    pa = f"{T}/proto_labels.json"
    json.dump(a, open(pa, "w"))
    expect("locked_file_hash_changed", lambda: R.verify_protocol(pa, REQ), "locked_files changed", res)
    b = copy.deepcopy(pr)
    b["config"]["cand_batch"] = 2
    pb = f"{T}/proto_cfg.json"
    json.dump(b, open(pb, "w"))
    expect("config_changed", lambda: R.verify_protocol(pb, REQ), "config digest tampered", res)
    c = copy.deepcopy(pr)
    c["code"]["m66_run.py"] = "1" * 64
    pc = f"{T}/proto_code.json"
    json.dump(c, open(pc, "w"))
    expect("code_hash_changed", lambda: R.verify_protocol(pc, REQ), "code changed", res)
    # 6 E 단계 gate 없이 protocol 생성 거부
    expect("E_protocol_without_gate", lambda: R.make_protocol("E12", "results/iter_066/data/requests_E12.jsonl", f"{T}/e12_nogate.json", 1, None),
           "require --gate", res)
    # 7 gate가 run=false이면 거부
    g = f"{T}/gate_false.json"
    json.dump({"for_stage": "E12", "run": False, "evidence": {}}, open(g, "w"))
    expect("gate_run_false", lambda: R.make_protocol("E12", "results/iter_066/data/requests_E12.jsonl", f"{T}/e12_gatefalse.json", 1, g),
           "does not permit", res)
    # 8 기존 protocol 덮어쓰기 거부
    expect("overwrite_protocol", lambda: R.make_protocol("D", REQ, PROTO, 1, None), "refuse to overwrite", res)
    # 9 completion 사본의 worker 파일 변조/누락 (resume_D는 부분 완료라 D main 완료 후 별도 실행: 존재 시에만)
    d = "results/iter_066/gen/D_main"
    if os.path.exists(f"{d}/completion.json"):
        cp = f"{T}/D_main_copy"
        if os.path.exists(cp):
            shutil.rmtree(cp)
        shutil.copytree(d, cp, ignore=shutil.ignore_patterns("claims"))
        wf = sorted(f for f in os.listdir(cp) if f.startswith("worker") and f.endswith(".jsonl"))[0]
        raw = open(f"{cp}/{wf}", "rb").read()
        open(f"{cp}/{wf}", "wb").write(raw.replace(b'"mean_ll": ', b'"mean_ll": 0.0, "x": ', 1))
        expect("completed_worker_file_changed", lambda: R.verify_completion(cp, REQ, PROTO), "changed after completion", res)
        os.remove(f"{cp}/{wf}")
        expect("completed_worker_file_missing", lambda: R.verify_completion(cp, REQ, PROTO), "worker file set", res)
        open(f"{cp}/worker9.jsonl", "w").close()
    n_pass = sum(r["pass"] for r in res)
    json.dump({"n": len(res), "n_pass": n_pass, "all_pass": n_pass == len(res), "checks": res}, open(OUT, "w"), indent=1)
    print(n_pass, "/", len(res))
    for r in res:
        print(r["name"], r["pass"], r.get("error", "")[:80])
    sys.exit(0 if n_pass == len(res) else 1)


if __name__ == "__main__":
    main()
