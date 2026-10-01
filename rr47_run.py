"""iter_047 실행 wrapper: pg43_run의 worker/launcher/verify_completion을 재사용하고, 호출자가 요구한 입력·모델·설정을 protocol과 대조한다.

python rr47_run.py protocol --stage D8|E --out P [--gate D_gate.json]   # 코드·요청·자료·평가 소스 hash를 잠그는 protocol 생성
python rr47_run.py verify --out-dir D --stage D8|E --protocol P         # completion 내용·요청 집합·hash·adapter 미사용·modality 재검증
생성은 `python pg43_run.py launch --requests R --protocol P --out-dir D --workers N --peak-gb G` (CUDA_VISIBLE_DEVICES는 상속된 허용 집합).
E 단계 protocol은 (1) E 자료 gate(E_data_gate.json이 있으면 run=true여야 함), (2) D8 기술 gate decision(run=true)을 반드시 요구한다.
"""
import argparse
import json
import os
import sys

import pg43_run as R
from rsna_diag import generate as G

OUT = "results/iter_047"
LOCK = ["rr47_spec.py", "rr47_data.py", "rr47_build.py", "rr47_run.py", "rr47_eval.py", "rr47_verify.py", "rr47_gate.py", "rr47_decide.py",
        f"{OUT}/data/feasibility.json", f"{OUT}/data/review_private.json"]
EXPECT = {"D8": dict(n=152, modality=dict(image=120, text=32), kinds=["rr47"]),
          "E": dict(n=1440, modality=dict(image=1056, text=384), kinds=["rr47"])}


def stage_files(stage):
    f = [f"{OUT}/data/manifest_{stage}.json", f"{OUT}/requests/requests_{stage}.jsonl"]
    return f


def make(stage, out, gate):
    if stage == "E":
        eg = f"{OUT}/data/E_data_gate.json"
        if os.path.exists(eg) and json.load(open(eg)).get("run") is not True:
            raise R.RunError("E data gate did not pass: refuse to build protocol")
        if not gate:
            raise R.RunError("E protocol requires the D8 technical gate decision (--gate)")
    req = f"{OUT}/requests/requests_{stage}.jsonl"
    lock = LOCK + [f"{OUT}/data/manifest_{stage}.json"]
    if stage == "E":
        lock.append(f"{OUT}/data/E_data_gate.json") if os.path.exists(f"{OUT}/data/E_data_gate.json") else None
    return R.make_protocol(req, out, adapter=None, gate=gate, lock=lock, extra={"stage": stage, "version": "rr47_v1"})


def verify(out_dir, stage, protocol):
    """pg43_run.verify_completion + 이번 실험의 호출자 요구(요청 파일·모델 revision·adapter 미사용·modality 수) 대조."""
    req = f"{OUT}/requests/requests_{stage}.jsonl"
    pdig, proto = R.verify_protocol(protocol, req)
    if proto["requests_path"] != req:
        raise R.RunError("protocol requests_path != requested stage requests")
    if proto.get("adapter") is not None:
        raise R.RunError("adapter must not be used in iter_047 (M0 only)")
    if proto["generation_config"]["model_revision"] != G.MODEL_REVISION:
        raise R.RunError("protocol model revision mismatch")
    if proto["extra"].get("stage") != stage:
        raise R.RunError("protocol stage mismatch")
    miss = [f for f in LOCK if f not in proto["locked_files"]]
    if miss:
        raise R.RunError(f"protocol lacks required locked files: {miss}")
    exp = EXPECT.get(stage)
    if stage == "D8" and (proto["n_requests"], proto["n_by_modality"]) != (exp["n"], exp["modality"]):
        raise R.RunError(f"D8 request set differs from plan: {proto['n_requests']} {proto['n_by_modality']}")
    recs = R.verify_completion(out_dir, req, protocol)
    for r in recs:
        if r["adapter_digest"] is not None:
            raise R.RunError("record used an adapter")
    return recs


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("protocol")
    p.add_argument("--stage", required=True, choices=["D8", "E"])
    p.add_argument("--out", required=True)
    p.add_argument("--gate", default=None)
    v = sub.add_parser("verify")
    v.add_argument("--stage", required=True, choices=["D8", "E"])
    v.add_argument("--out-dir", required=True)
    v.add_argument("--protocol", required=True)
    a = ap.parse_args()
    if a.cmd == "protocol":
        make(a.stage, a.out, a.gate)
        print("protocol written", a.out)
    else:
        recs = verify(a.out_dir, a.stage, a.protocol)
        print("verified", len(recs), "records")


if __name__ == "__main__":
    main()
