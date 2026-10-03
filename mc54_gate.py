"""iter_054 기술 gate: 입력·scoring·재개·변조·worker 정합성·tech 완료가 모두 통과해야 main 단계 protocol을 만들 수 있다.
내용상 오답(정확도)은 gate 조건이 아니다. gate 파일은 증거 파일 경로+sha256을 보존하고, make_protocol/verify_protocol이 재검증한다."""
import json
import os
import sys

import mc54_run as RUN


def build_gate(out, tech_out_dir, tech_protocol, requests, evidence_paths):
    ev = {}
    for name, p in evidence_paths.items():
        d = json.load(open(p))
        if d.get("all_pass") is not True:
            raise SystemExit(f"evidence {name} not all_pass")
        ev[name] = {"path": p, "sha256": RUN.file_sha(p), "require_all_pass": True}
    recs = RUN.verify_completion(tech_out_dir, requests, tech_protocol)  # raw–protocol–요청 연결 재검증
    comp_path = os.path.join(tech_out_dir, "completion.json")
    g = {"run": True, "evidence": ev, "tech_out_dir": tech_out_dir, "tech_protocol": tech_protocol,
         "tech_protocol_sha256": RUN.file_sha(tech_protocol), "tech_completion": comp_path,
         "tech_completion_sha256": RUN.file_sha(comp_path), "n_tech_records_verified": len(recs),
         "scope": "technical validity only (inputs, scoring alignment, resume, tamper, worker consistency); not a performance gate"}
    if os.path.exists(out):
        raise SystemExit(f"gate exists {out}")
    with open(out, "x") as f:
        json.dump(g, f, indent=1)
    return g


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    build_gate(spec["out"], spec["tech_out_dir"], spec["tech_protocol"], spec["requests"], spec["evidence"])
