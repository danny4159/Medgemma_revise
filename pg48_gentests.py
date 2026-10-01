"""iter_048 생성 경로 CPU 검사: D8의 C adapter 실행(2w/4w/중단-재개)에 대해
 (1) 완료 검증 통과, (2) 2w/4w/재개 token 일치, (3) 저장된 iter_041 C D24 출력과 token 일치 (같은 (환자, cond, targets)),
 (4) 변조·중복·누락·wrong config 거부 (복사본에서 변조하고 completion을 다시 만들어 깊은 검사 분기가 실제로 실패하는지 확인).
python pg48_gentests.py --out results/iter_048/tests/gen_tests.json
"""
import argparse
import glob
import json
import os
import shutil
import sys

import pg43_run as R
import pg48_import as IM

ROOT = "results/iter_048"
REQ = f"{ROOT}/requests/requests_D8.jsonl"
DIRS = {"2w": f"{ROOT}/gen/D8_C_2w", "4w": f"{ROOT}/gen/D8_C_4w_b", "resume": f"{ROOT}/gen/D8_C_resume"}
PROTO = f"{ROOT}/protocol/proto_D8_C.json"
TAMPER = f"{ROOT}/tests/tamper"


def recs_by_key(d):
    out = {}
    for fn in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
        for r in R.read_records(fn):
            out[(r["patient"], r["cond"], tuple(r["targets"]))] = r
    return out


def rewrite(src, dst, mutate):
    """src dir 복사 후 mutate(files:{name:[records]}) 로 변조하고 completion의 worker_file_sha256/n_requests를 일치시킨다 (깊은 검사 분기를 시험하기 위함)."""
    if os.path.exists(dst):
        shutil.rmtree(dst) if False else sys.exit(f"exists {dst}")
    shutil.copytree(src, dst)
    comp = json.load(open(os.path.join(dst, "completion.json")))
    files = {os.path.basename(f): R.read_records(f) for f in sorted(glob.glob(os.path.join(dst, "gen_worker*.jsonl")))}
    mutate(files)
    for fn, recs in files.items():
        with open(os.path.join(dst, fn), "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
    comp["worker_file_sha256"] = {fn: R.file_sha(os.path.join(dst, fn)) for fn in files}
    json.dump(comp, open(os.path.join(dst, "completion.json"), "w"), indent=1)


def expect_fail(name, dst, proto, req, res, needle):
    try:
        R.verify_completion(dst, req, proto)
        res[name] = {"rejected": False, "message": None}
    except Exception as e:  # noqa
        res[name] = {"rejected": True, "message": str(e)[:200], "expected_branch_match": needle in str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    res = {"verify_completion_pass": {}, "token_equality": {}, "tamper": {}}
    for k, d in DIRS.items():
        recs = R.verify_completion(d, REQ, PROTO)
        res["verify_completion_pass"][k] = len(recs)
    base = {k: recs_by_key(d) for k, d in DIRS.items()}
    for k in ("4w", "resume"):
        res["token_equality"][f"2w_vs_{k}"] = {"n": len(base["2w"]), "suffix_ids_mismatch": sum(base["2w"][x]["suffix_ids"] != base[k][x]["suffix_ids"] for x in base["2w"]),
                                               "text_mismatch": sum(base["2w"][x]["suffix_text_raw"] != base[k][x]["suffix_text_raw"] for x in base["2w"])}
    old = IM.load_c_d24()["records"]
    for k in DIRS:
        res["token_equality"][f"{k}_vs_stored_iter041_C_D24"] = {"n": len(base[k]), "suffix_ids_mismatch": sum(base[k][x]["suffix_ids"] != old[x]["suffix_ids"] for x in base[k])}
    res["resume_info"] = {"repair_logs": sorted(glob.glob(f"{DIRS['resume']}/*.repair.log")), "partial_files": sorted(glob.glob(f"{DIRS['resume']}/*.partial.*")),
                          "n_worker_timing_files": len(glob.glob(f"{DIRS['resume']}/worker*.timing.*.json")), "partial_json": sorted(glob.glob(f"{DIRS['resume']}/partial_*.json"))}
    os.makedirs(TAMPER, exist_ok=True)
    src = DIRS["2w"]

    def dup(files):
        fn = sorted(files)[0]
        files[fn].append(dict(files[fn][0]))

    def drop(files):
        fn = max(files, key=lambda k: len(files[k]))
        files[fn].pop()

    def flip_text(files):
        fn = sorted(files)[0]
        files[fn][0]["suffix_text_raw"] = files[fn][0]["suffix_text_raw"] + " "  # record_digest stale

    def wrong_adapter(files):
        fn = sorted(files)[0]
        r = files[fn][0]
        r["adapter_digest"] = "0" * 64
        r["record_digest"] = R.record_digest(r)  # digest 재계산: adapter 검사 분기

    def wrong_prompt(files):
        fn = sorted(files)[0]
        r = files[fn][0]
        r["prompt_sha256"] = "1" * 64
        r["record_digest"] = R.record_digest(r)

    def wrong_image(files):
        fn = sorted(files)[0]
        r = files[fn][0]
        r["input_pixel_sha256"] = "2" * 64
        r["record_digest"] = R.record_digest(r)

    for name, mut, needle in (("duplicate_record", dup, "request set mismatch"), ("missing_record", drop, "request set mismatch"), ("altered_text_stale_digest", flip_text, "record digest"),
                              ("wrong_adapter_digest", wrong_adapter, "adapter/protocol digest"), ("wrong_prompt_hash", wrong_prompt, "row digest"),
                              ("wrong_image_pixel_hash", wrong_image, "pixel hash")):
        dst = f"{TAMPER}/{name}"
        rewrite(src, dst, mut)
        expect_fail(name, dst, PROTO, REQ, res["tamper"], needle)
    # 원본 completion 파일 변조 (worker file sha 분기)
    dst = f"{TAMPER}/raw_file_changed"
    shutil.copytree(src, dst)
    fn = sorted(glob.glob(os.path.join(dst, "gen_worker*.jsonl")))[0]
    open(fn, "a").write("\n")
    expect_fail("worker_file_changed_after_completion", dst, PROTO, REQ, res["tamper"], "worker file changed")
    # wrong config: 다른 protocol(adapter가 다른 protocol)로 같은 출력을 검증
    wp = f"{ROOT}/protocol/proto_D8_wrongcfg.json"
    if os.path.exists(wp):
        expect_fail("wrong_protocol_adapter", src, wp, REQ, res["tamper"], "protocol")
    res["all_rejected"] = all(v["rejected"] for v in res["tamper"].values())
    res["all_branch_match"] = all(v.get("expected_branch_match", True) for v in res["tamper"].values())
    res["tokens_all_equal"] = all(v["suffix_ids_mismatch"] == 0 for v in res["token_equality"].values())
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("all_rejected", "all_branch_match", "tokens_all_equal")}))
    print(json.dumps(res["tamper"], indent=1))
    print(json.dumps(res["token_equality"], indent=1))


if __name__ == "__main__":
    main()
