"""Label-free selection. 모든 질문의 선택을 annotation 접근 없이 먼저 저장·고정한다.

실행: python research/select_qes.py --out research/results/iter_004
iter_005: 공통 preflight(현재 입력 재해시)를 거치고, selection에 현재 유효 prediction 전체 결과 필드의
digest·config hash·requests digest를 연결한다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qes.data import DATA_DIR, SCORER_VERSION  # noqa: E402
from qes.preflight import PreflightError, check_manifest, predictions_digest, requests_digest  # noqa: E402
from qes.selection import select_all  # noqa: E402
from qes.store import read_jsonl, validate_predictions, write_json_atomic  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default=DATA_DIR)
    ap.add_argument("--status-out", default=None, help="completion.json 대신 쓸 경로 (재감사용)")
    args = ap.parse_args(argv)
    try:
        cfg, chash, reqs, info, subsets = check_manifest(args.out, data_dir=args.data_dir)
    except PreflightError as e:
        raise SystemExit(f"preflight failed -> selection not computed: {e}")
    pred_path = os.path.join(args.out, "predictions.jsonl")
    v = validate_predictions(reqs, read_jsonl(pred_path), chash, SCORER_VERSION)
    status = {"scope": "prediction_collection (평가 완료 여부는 evaluation_status.json)",
              "status": v["status"], "n_requests": len(reqs), "n_valid": len(v["valid"]),
              "n_missing": len(v["missing"]), "n_conflicts": len(v["conflicts"]),
              "n_rejected": len(v["rejected"]), "rejected_reasons": {}}
    for x in v["rejected"]:
        status["rejected_reasons"][x["reason"]] = status["rejected_reasons"].get(x["reason"], 0) + 1
    write_json_atomic(args.status_out or os.path.join(args.out, "completion.json"), status)
    print(json.dumps(status), flush=True)
    if v["status"] != "complete":
        raise SystemExit("incomplete: selection not computed (결측 조합을 제외하고 계산하지 않는다)")
    main_sel = select_all(reqs, v["valid"], field="m")
    fp32_sel = select_all(reqs, v["valid"], field="m_fp32head")
    pred_digest = predictions_digest(v["valid"], chash)
    out = {"predictions_digest": pred_digest, "predictions_digest_version": "iter005-all-result-fields",
           "config_sha256": chash, "requests_digest": requests_digest(reqs), "label_free": True,
           "main": main_sel, "sensitivity_fp32head": fp32_sel}
    path = os.path.join(args.out, "selections.json")
    if os.path.exists(path):
        old = json.load(open(path))
        if old.get("predictions_digest") != pred_digest:
            raise SystemExit("selections.json exists for different predictions (or old digest format); "
                             "refusing to overwrite")
    write_json_atomic(path, out)
    print(f"selections saved: {path}; ties(main)={len(main_sel['ties'])} ties(fp32)={len(fp32_sel['ties'])}")


if __name__ == "__main__":
    main()
