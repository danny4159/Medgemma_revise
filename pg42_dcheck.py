"""iter_042 D 동작 검사: 2w/4w 정합성, 변조·불일치 거부. 결과는 results/iter_042/tests/ 새 파일.
python pg42_dcheck.py compare | tamper
"""
import glob
import json
import os
import shutil
import sys

import pg41_run as R

OUT = "results/iter_042"


def recs(d):
    out = {}
    for f in sorted(glob.glob(f"{OUT}/gen/{d}/gen_worker*.jsonl")):
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                out[r["request_id"]] = r
    return out


def peak(d):
    mx = {}
    for l in open(f"{OUT}/gen/{d}/resource_log.jsonl"):
        for g in json.loads(l)["gpu"]:
            i, u, _ = [int(x) for x in g.split(",")]
            mx[i] = max(mx.get(i, 0), u)
    return mx


def compare():
    res = {}
    for m in ("M0", "C"):
        a, b = recs(f"D_{m}_2w"), recs(f"D_{m}_4w")
        same = set(a) == set(b)
        mism = [k for k in a if k in b and a[k]["suffix_ids"] != b[k]["suffix_ids"]]
        ca = json.load(open(f"{OUT}/gen/D_{m}_2w/completion.json"))
        cb = json.load(open(f"{OUT}/gen/D_{m}_4w/completion.json"))
        res[m] = {"same_request_set": same, "n": len(a), "token_mismatch": len(mism),
                  "2w": {"wall_s": ca["wall_s"], "gen_union_s": ca["cost"]["device_seconds_generate_union"], "peak_mib": peak(f"D_{m}_2w"),
                          "max_out_tokens": max(r["n_output_tokens"] for r in a.values()), "max_req_wall": max(r["wall_s"] for r in a.values())},
                  "4w": {"wall_s": cb["wall_s"], "gen_union_s": cb["cost"]["device_seconds_generate_union"], "peak_mib": peak(f"D_{m}_4w"),
                          "max_out_tokens": max(r["n_output_tokens"] for r in b.values()), "max_req_wall": max(r["wall_s"] for r in b.values())},
                  "oom": any("oom" in open(f).read() for f in glob.glob(f"{OUT}/gen/D_{m}_4w/*.log"))}
    tot2 = sum(res[m]["2w"]["wall_s"] for m in res)
    tot4 = sum(res[m]["4w"]["wall_s"] for m in res)
    ok = all(v["same_request_set"] and v["token_mismatch"] == 0 and not v["oom"] for v in res.values())
    peak4 = max(max(res[m]["4w"]["peak_mib"].values()) for m in res)
    res["decision"] = {"workers_total": 4 if ok and tot4 < tot2 and peak4 < 24576 - 2048 else 2, "total_wall_2w_s": tot2,
                       "total_wall_4w_s": tot4, "peak4_mib": peak4, "note": "D 36요청/구성, 모델 로딩 포함 wall. E 정확도는 사용하지 않음."}
    os.makedirs(f"{OUT}/decisions", exist_ok=True)
    json.dump(res, open(f"{OUT}/decisions/d_worker_config.json", "x"), indent=1)
    print(json.dumps(res["decision"]), {m: (res[m]["token_mismatch"], res[m]["oom"]) for m in ("M0", "C")})


def tamper():
    tdir = f"{OUT}/tests/tamper"
    os.makedirs(tdir, exist_ok=True)
    req, proto = f"{OUT}/requests/requests_D_C.jsonl", f"{OUT}/protocol/protocol_D_C_2w.json"
    results = {}

    def fresh(name):
        d = f"{tdir}/{name}"
        shutil.copytree(f"{OUT}/gen/D_C_2w", d)
        return d

    def expect_reject(name, d, rq=req, pr=proto):
        try:
            R.verify_completion(d, rq, pr)
            results[name] = "NOT_REJECTED"
        except Exception as e:
            results[name] = f"rejected: {type(e).__name__}: {str(e)[:80]}"
    R.verify_completion(f"{OUT}/gen/D_C_2w", req, proto)
    results["baseline_ok"] = "verified"
    # 1) 내용 변조 (record digest)
    d = fresh("t_content")
    f = sorted(glob.glob(f"{d}/gen_worker*.jsonl"))[0]
    lines = open(f).read().split("\n")
    r = json.loads(lines[0])
    r["suffix_text_raw"] = "[]<end_of_turn>"
    lines[0] = json.dumps(r)
    open(f, "w").write("\n".join(lines))
    expect_reject("tamper_record_content", d)
    # 2) 누락 record
    d = fresh("t_missing")
    f = sorted(glob.glob(f"{d}/gen_worker*.jsonl"))[0]
    lines = open(f).read().split("\n")
    open(f, "w").write("\n".join(lines[1:]))
    expect_reject("missing_record", d)
    # 3) 다른 모델 protocol (M0 protocol로 C 결과 검증)
    d = fresh("t_model")
    expect_reject("wrong_model_protocol", d, rq=f"{OUT}/requests/requests_D_M0.jsonl", pr=f"{OUT}/protocol/protocol_D_M0_2w.json")
    # 4) 중복 record
    d = fresh("t_dup")
    f = sorted(glob.glob(f"{d}/gen_worker*.jsonl"))[0]
    s = open(f).read()
    open(f, "a").write(s.split("\n")[0] + "\n")
    expect_reject("duplicate_record", d)
    json.dump(results, open(f"{OUT}/tests/tamper_result.json", "x"), indent=1)
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    {"compare": compare, "tamper": tamper}[sys.argv[1]]()
