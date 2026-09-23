"""iter_004 QES 결과의 무결성 재감사 (CPU, GPU 재실행 없음). iter_004 디렉터리에는 아무것도 쓰지 않는다.

실행: python research/audit_qes_iter004.py --src research/results/iter_004 --out research/results/iter_005/qes_reaudit_iter004.json

- 수정된 evaluate_qes.gate()를 그대로 적용한다 (manifest 재해시, prediction, verification, selection 연결).
- 저장된 selection에 새 digest 정보가 없으면 꾸며 넣지 않고 incomplete로 보고한다.
- 별도로, 현재 유효 prediction에서 selection을 메모리에서 다시 계산해 저장된 선택 내용과 같은지만 비교한다
  (이는 gate 통과로 간주하지 않는다).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate_qes  # noqa: E402
from qes.data import DATA_DIR  # noqa: E402
from qes.preflight import predictions_digest  # noqa: E402
from qes.selection import select_all  # noqa: E402
from qes.store import write_json_atomic  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-dir", default=DATA_DIR)
    args = ap.parse_args()
    ok, report, objs = evaluate_qes.gate(args.src, data_dir=args.data_dir)
    res = {"src": os.path.abspath(args.src), "gate_pass": ok, "gate": report,
           "note": "gate 실패 시 iter_004의 complete/투자 판정은 수정된 기준에서 재확인되지 않은 것으로 본다."}
    if objs is not None:
        reqs, v, ver, sel_all = objs
        if v["status"] == "complete" and sel_all is not None:
            chash = sel_all.get("config_sha256")
            recomputed = {"main": select_all(reqs, v["valid"], field="m"),
                          "sensitivity_fp32head": select_all(reqs, v["valid"], field="m_fp32head")}
            res["recomputed_selection_matches_stored"] = {
                k: recomputed[k]["selection"] == sel_all[k]["selection"] for k in recomputed}
            res["stored_selection_keys"] = sorted(sel_all)
            res["stored_predictions_digest_format"] = sel_all.get("predictions_digest_version", "iter004-m-only")
            res["current_predictions_digest_all_fields"] = predictions_digest(v["valid"], chash) if chash else None
    write_json_atomic(args.out, res)
    print(json.dumps({k: res[k] for k in res if k != "gate"}, indent=1))
    print(json.dumps({s: report["stages"][s]["pass"] for s in report["stages"]}))


if __name__ == "__main__":
    main()
