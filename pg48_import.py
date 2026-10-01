"""iter_048 기존 출력 import 검증 (pg43_eval.verify_import를 쓰지 않는 별도 구현). 기존 C(iter_040/041)와 A(iter_046) 출력을 원 request·protocol·adapter·영상 연결로 검증한다.

load_c_v96(): C의 V96 I(iter_040 gen/C) / J_AB / J_BA(iter_041) record를 반환한다 (모두 request/record/completion/protocol/adapter/현재 영상 hash 검증).
load_c_d24(): C의 D24 96요청(iter_041 D24_C_2w; 4w와 token 일치 확인).
load_a_v96(): iter_046 A_U_e5 raw(모든 threshold 저장) 192문장.
"""
import glob
import hashlib
import json
import os

import pg43_run as R

MAN = "results/iter_043/data/manifest_private.json"
C_DIGEST = "419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8"
C_ADAPTER_FILE = "results/iter_040/train2/C_s17/epoch_03/adapter.pt"
A_CKPT = "results/iter_046/train/U/weights_e5.pth"
A_SHA = "b9c2bccd04dde8b7445aa5f60e082a0c93f1f2412af8a583a4ca5ee207c8718a"


class ImportError_(RuntimeError):
    pass


def _need(c, msg):
    if not c:
        raise ImportError_(msg)


def _read_requests(path):
    rows = {}
    for l in open(path):
        if l.strip():
            r = json.loads(l)
            rows[r["request_id"]] = r
    return rows


def verify_old_gen(gen_dir, req_path, proto_path, expect_n):
    """returns (records by request_id, old request rows by request_id, protocol digest)."""
    comp = json.load(open(os.path.join(gen_dir, "completion.json")))
    _need(all(c == 0 for c in comp["exit_codes"]), f"{gen_dir}: nonzero exit")
    proto = json.load(open(proto_path))
    _need(R.file_sha(req_path) == proto["requests_sha256"], f"{gen_dir}: requests file != protocol lock")
    ad = proto["adapter"]
    _need(ad["digest"] == C_DIGEST and R.file_sha(os.path.join(ad["path"], "adapter.pt")) == ad["file_sha256"], f"{gen_dir}: adapter != C")
    _need(R.file_sha(C_ADAPTER_FILE) == ad["file_sha256"], f"{gen_dir}: current C adapter file changed")
    rows = _read_requests(req_path)
    _need(len(rows) == expect_n == comp["n_requests"], f"{gen_dir}: n requests {len(rows)} {comp['n_requests']}")
    files = sorted(glob.glob(os.path.join(gen_dir, "gen_worker*.jsonl")))
    _need(sorted(os.path.basename(f) for f in files) == sorted(comp["worker_file_sha256"]), f"{gen_dir}: worker file set")
    recs = {}
    for f in files:
        _need(R.file_sha(f) == comp["worker_file_sha256"][os.path.basename(f)], f"{gen_dir}: worker file changed {f}")
        for r in R.read_records(f):
            _need(r["request_id"] not in recs, f"{gen_dir}: duplicate {r['request_id']}")
            recs[r["request_id"]] = r
    _need(set(recs) == set(rows), f"{gen_dir}: request set mismatch")
    for rid, r in recs.items():
        _need(r["record_digest"] == R.record_digest(r), f"{gen_dir}: record digest {rid}")
        _need(r["row_digest"] == R.row_digest(rows[rid]), f"{gen_dir}: row digest {rid}")
        _need(r["adapter_digest"] == C_DIGEST and r["protocol_digest"] == comp["protocol_digest"], f"{gen_dir}: record adapter/protocol {rid}")
        _need(r["prompt_sha256"] == rows[rid]["prompt_sha256"] == hashlib.sha256(rows[rid]["prompt"].encode()).hexdigest(), f"{gen_dir}: prompt hash {rid}")
    return recs, rows, comp["protocol_digest"]


def _check_against_new(recs, old_rows, new_rows_by_key, man_entries, what):
    """old 요청 행이 내 요청 행렬과 같은 (patient, cond, targets, prompt, 영상 hash)인지, record 영상 hash가 manifest와 같은지 확인하고 key별 record를 반환."""
    out = {}
    for rid, r in recs.items():
        o = old_rows[rid]
        key = (o["patient"], o["cond"], tuple(o["targets"]))
        n = new_rows_by_key.get(key)
        _need(n is not None, f"{what}: no matching new request for {key}")
        _need(n["prompt_sha256"] == o["prompt_sha256"] and n["caps"] == o["caps"] and n["image_file_sha256"] == o["image_file_sha256"] and
              n["input_pixel_sha256"] == o["input_pixel_sha256"] and n["image"] == o["image"], f"{what}: request differs from new matrix {key}")
        e = man_entries[o["patient"]]
        _need(r["input_pixel_sha256"] == e["input_pixel_sha256"] and o["input_pixel_sha256"] == e["input_pixel_sha256"], f"{what}: pixel hash != manifest")
        _need(r["ended_eos"] is True or r["finish_reason"] in ("eos", "length"), f"{what}: bad finish")
        out[key] = r
    return out


def new_rows_by_key(path):
    return {(r["patient"], r["cond"], tuple(r["targets"])): r for r in (json.loads(l) for l in open(path) if l.strip())}


def man_entries(man, name):
    return {e["PatientID"]: e for e in man[name]}


def load_c_v96(req_new="results/iter_048/requests/requests_V96.jsonl"):
    man = json.load(open(MAN))
    ents = man_entries(man, "V96")
    nk = new_rows_by_key(req_new)
    out = {}
    for tag, gen, req, proto, n in (("I", "results/iter_040/gen/C", "results/iter_040/requests/requests_V96.jsonl", "results/iter_040/protocol/protocol_C.json", 192),
                                    ("AB", "results/iter_041/gen/V96_C_JAB", "results/iter_041/requests/requests_V96_JAB.jsonl", "results/iter_041/protocol/protocol_V96_C_JAB.json", 96),
                                    ("BA", "results/iter_041/gen/V96_C_JBA", "results/iter_041/requests/requests_V96_JBA.jsonl", "results/iter_041/protocol/protocol_V96_C_JBA.json", 96)):
        recs, rows, pdig = verify_old_gen(gen, req, proto, n)
        out[tag] = {"records": _check_against_new(recs, rows, nk, ents, f"C_{tag}"), "protocol_digest": pdig, "gen_dir": gen,
                    "completion_sha256": R.file_sha(os.path.join(gen, "completion.json"))}
    return out


def load_c_d24(req_new="results/iter_048/requests/requests_D24.jsonl"):
    man = json.load(open(MAN))
    ents = man_entries(man, "D24")
    nk = new_rows_by_key(req_new)
    recs, rows, pdig = verify_old_gen("results/iter_041/gen/D24_C_2w", "results/iter_041/requests/requests_D24_C.jsonl", "results/iter_041/protocol/protocol_D24_C.json", 96)
    recs4, _, _ = verify_old_gen("results/iter_041/gen/D24_C_4w", "results/iter_041/requests/requests_D24_C.jsonl", "results/iter_041/protocol/protocol_D24_C.json", 96)
    mism = sum(recs[k]["suffix_ids"] != recs4[k]["suffix_ids"] for k in recs)
    return {"records": _check_against_new(recs, rows, nk, ents, "C_D24"), "protocol_digest": pdig, "tokens_2w_vs_4w_mismatch": mism,
            "gen_dir": "results/iter_041/gen/D24_C_2w"}


def load_a_v96(gen_dir="results/iter_046/mg/V96_A_w2b4"):
    man = json.load(open(MAN))
    ents = man_entries(man, "V96")
    comp = json.load(open(os.path.join(gen_dir, "completion.json")))
    _need(all(c == 0 for c in comp["exit_codes"]) and comp["complete"] and comp["n_unique"] == 192, "A: completion")
    _need(R.file_sha(A_CKPT) == A_SHA, "A: checkpoint file changed")
    recs = {}
    for fn, sha in comp["raw_file_sha256"].items():
        p = os.path.join(gen_dir, fn)
        _need(R.file_sha(p) == sha, f"A: raw file changed {fn}")
        for ln in open(p, "rb").read().split(b"\n")[:-1]:
            if ln.strip():
                r = json.loads(ln)
                _need(r["request_id"] not in recs, "A: duplicate")
                recs[r["request_id"]] = r
    _need(len(recs) == 192, "A: 192 records")
    by = {}
    for r in recs.values():
        e = ents[r["patient"]]
        _need(r["ckpt_sha256"] == A_SHA and r["u8_pixel_sha256"] == e["u8_pixel_sha256"] and r["image"] == e["image"], "A: provenance != manifest")
        _need(r["sentence_sha256"] == hashlib.sha256(e["sentences"][r["target"]].encode()).hexdigest(), "A: sentence mismatch")
        _need("0.8" in r["detections"], "A: threshold 0.8 missing")
        by[(r["patient"], r["target"])] = r
    _need(len(by) == 192 and {p for p, _ in by} == set(ents), "A: patient/sentence coverage")
    return {"records": by, "completion_sha256": R.file_sha(os.path.join(gen_dir, "completion.json")), "gen_dir": gen_dir}
