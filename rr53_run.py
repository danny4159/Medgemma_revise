"""iter_053 실행 wrapper: pg43_run의 worker/launcher/verify_completion 재사용 + 이번 실험의 호출자 요구 대조.

python rr53_run.py protocol --stage D|E|F --out P [--gate G]   # 코드·요청·자료·평가 소스 hash 잠금
python rr53_run.py verify --out-dir D --stage D|E|F --protocol P
생성: python pg43_run.py launch --requests results/iter_053/requests/requests_<S>.jsonl --protocol P --out-dir D --workers N --peak-gb G
- E protocol은 D gate decision(run=true, stage=D), F protocol은 E decision(run=true, stage=E)을 요구하며, decision이 참조하는 모든 입력 파일의
  현재 sha256을 다시 계산해 일치해야 한다 (run=true만 있는 JSON은 통과하지 못한다).
- verify는 manifest에서 기대 요청 집합을 다시 구성해 요청 파일과 byte 단위로 비교하고(관측 출력 ID를 기대 집합으로 쓰지 않는다) completion을 재검증한다.
"""
import argparse
import json
import os

import pg43_run as R
import rr53_build as B
import rr53_spec as S
from rr53_data import OUT, file_sha
from rsna_diag import generate as G

LOCK = ["rr53_spec.py", "rr53_data.py", "rr53_build.py", "rr53_run.py", "rr53_eval.py", "rr53_verify.py", "rr53_gate.py", "rr53_decide.py",
        "rr47_spec.py", "rr47_eval.py", "rsna_diag/cx18_data.py", "rsna_diag/cx18_spec.py", "rsna_diag/qa_spec.py",
        f"{OUT}/data/data_check.json", "results/iter_018/manifests/labels.json", "results/iter_018/manifests/sets.json",
        "results/iter_018/manifests/infer_manifest.jsonl"]
EXPECT = {"P": dict(n=48, modality=dict(image=30, text=18)), "D": dict(n=448, modality=dict(image=272, text=176)), "E": dict(n=768, modality=dict(image=528, text=240)),
          "F": dict(n=1680, modality=dict(image=1155, text=525))}
GATE_STAGE = {"E": "D", "F": "E"}


def check_gate_inputs(gate_path, want_stage):
    g = json.load(open(gate_path))
    if g.get("run") is not True or g.get("stage") != want_stage:
        raise R.RunError(f"gate {gate_path}: run!=true or stage!={want_stage}")
    if g.get("data_check_sha256") != file_sha(f"{OUT}/data/data_check.json"):
        raise R.RunError("gate data_check digest != current data_check")
    ins = g.get("inputs") or {}
    if not ins:
        raise R.RunError("gate has no input digests")
    for name, d in ins.items():
        if file_sha(d["path"]) != d["sha256"]:
            raise R.RunError(f"gate input {name} changed since decision: {d['path']}")
    return g


def stage_files(stage):
    return [f"{OUT}/data/manifest_{'D' if stage == 'P' else stage}.json"]


def pilot_subset(reqs):
    """D에서 사전 규칙으로 고른 처리량·정합성·재개 pilot (출력과 무관): 조건군(R1,R2,T,BJ,BT,BI,O,OT)마다 CheXpert D 요청 중 order_key가 앞선 6개."""
    out = []
    for base in ("R1", "R2", "T", "BJ", "BT", "BI", "O", "OT"):
        cand = sorted((r for r in reqs if r["set"] == "D" and r["cond"].split("_")[0] == base), key=lambda r: r["order_key"])
        out += cand[:6]
    return out


def make(stage, out, gate):
    if stage in GATE_STAGE:
        if not gate:
            raise R.RunError(f"stage {stage} protocol requires the {GATE_STAGE[stage]} decision (--gate)")
        check_gate_inputs(gate, GATE_STAGE[stage])
    req = f"{OUT}/requests/requests_{stage}.jsonl"
    check_requests(stage, req)
    return R.make_protocol(req, out, adapter=None, gate=gate, lock=LOCK + stage_files(stage), extra={"stage": stage, "version": S.VERSION})


def expected_requests(stage):
    man = json.load(open(f"{OUT}/data/manifest_{'D' if stage == 'P' else stage}.json"))
    cache = {}
    if stage in ("D", "P"):
        reqs = B.make_requests(man["rows"], "D", "with", cache)
        reqs += B.make_requests(man["pc_oracle_rows"], "pc_D8", "only", cache)
        if stage == "P":
            reqs = pilot_subset(reqs)
    else:
        reqs = B.make_requests(man["rows"], stage, "none", cache)
    return reqs


def check_requests(stage, req_path):
    got = R.read_requests(req_path)
    exp = expected_requests(stage)
    if len(got) != EXPECT[stage]["n"] or len(exp) != len(got):
        raise R.RunError(f"{stage}: request count {len(got)} != plan {EXPECT[stage]['n']}")
    key = lambda r: r["request_id"]
    if {key(r): r for r in got} != {key(r): r for r in exp}:
        raise R.RunError(f"{stage}: request file differs from manifest reconstruction")
    mod = {m: sum(r["modality"] == m for r in got) for m in ("image", "text")}
    if mod != EXPECT[stage]["modality"]:
        raise R.RunError(f"{stage}: modality counts {mod}")
    return got


def verify(out_dir, stage, protocol):
    req = f"{OUT}/requests/requests_{stage}.jsonl"
    pdig, proto = R.verify_protocol(protocol, req)
    if proto["requests_path"] != req:
        raise R.RunError("protocol requests_path != requested stage requests")
    if proto.get("adapter") is not None:
        raise R.RunError("adapter must not be used in iter_053 (M0 only)")
    if proto["generation_config"]["model_revision"] != G.MODEL_REVISION:
        raise R.RunError("protocol model revision mismatch")
    if proto["extra"].get("stage") != stage or proto["extra"].get("version") != S.VERSION:
        raise R.RunError("protocol stage/version mismatch")
    miss = [f for f in LOCK + stage_files(stage) if f not in proto["locked_files"]]
    if miss:
        raise R.RunError(f"protocol lacks required locked files: {miss}")
    if stage in GATE_STAGE:
        if not proto.get("gate"):
            raise R.RunError("protocol lacks gate")
        check_gate_inputs(proto["gate"]["decision_path"], GATE_STAGE[stage])
    check_requests(stage, req)
    recs = R.verify_completion(out_dir, req, protocol)
    for r in recs:
        if r["adapter_digest"] is not None:
            raise R.RunError("record used an adapter")
    return recs


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("protocol")
    p.add_argument("--stage", required=True, choices=["P", "D", "E", "F"])
    p.add_argument("--out", required=True)
    p.add_argument("--gate", default=None)
    w = sub.add_parser("write-pilot-requests")
    v = sub.add_parser("verify")
    v.add_argument("--stage", required=True, choices=["P", "D", "E", "F"])
    v.add_argument("--out-dir", required=True)
    v.add_argument("--protocol", required=True)
    a = ap.parse_args()
    if a.cmd == "write-pilot-requests":
        from rr53_data import write_new
        reqs = expected_requests("P")
        write_new(f"{OUT}/requests/requests_P.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in reqs))
        print("pilot requests", len(reqs))
    elif a.cmd == "protocol":
        make(a.stage, a.out, a.gate)
        print("protocol written", a.out)
    else:
        print("verified", len(verify(a.out_dir, a.stage, a.protocol)), "records")


if __name__ == "__main__":
    main()
