"""iter_031 평가 실행기: C201 또는 E402의 O/F 결과를 읽어 report.json을 만든다.

run_iter030_eval.py를 이어받아 다음을 보강한다:
- 실행 전 protocol을 재검증하고 이번 경로가 요구하는 필수 파일이 실제로 잠겨 있는지 확인한다.
- split=E는 --decide-c(잠긴 C201 decision, enter_E=true)를 필수로 받고 그 안의 bstar를 그대로 쓴다.
  임의 --bstar 문자열로 C의 선택을 바꿀 수 없다.
- report.json에 protocol_digest·source_manifest_sha256·decide_c 연결 정보를 남긴다 (decide 단계의 digest 연결용).
- h1_report에 split을 넘겨 C는 95%, E는 97.5% primary CI를 쓰게 한다.
- ceil(0.2N) Capture, 단일 class 배제 bootstrap, 한 박스 층 diff, population cost report를 포함한다 (risk30_eval.py 수정분).
"""
import argparse
import hashlib
import json
import os

from rsna_diag import risk30, risk30_eval as REV
from rsna_diag import lock_protocol as LP


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def check_inputs(source_manifest, split, out_dir):
    items = list(source_manifest["patients"][split].values())
    comp = risk30.check_completion(out_dir, items, tasks=("O", "F"))
    if not comp["ok"]:
        raise RuntimeError(f"{split}: completion check failed: {comp['problems']}")
    return comp


def load_tokenizer():
    import os as _os
    _os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
    _os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import transformers
    return transformers.AutoTokenizer.from_pretrained(
        "google/medgemma-1.5-4b-it", revision="91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-manifest", default="results/iter_030/source_manifest.json")
    ap.add_argument("--source-audit", default="results/iter_030/source_audit.json")
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--split", required=True, choices=["C", "E"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report-out", required=True)
    ap.add_argument("--decide-c", default=None, help="split=E일 때 필수: C201 decision 경로 (enter_E=true, bstar 포함)")
    a = ap.parse_args()
    if a.split == "E" and not a.decide_c:
        raise RuntimeError("E 평가는 --decide-c(잠긴 C201 decision)가 필요하다 (재선택 금지)")
    if os.path.exists(a.report_out):
        raise RuntimeError(f"refusing to overwrite existing {a.report_out}")

    protocol_digest = risk30.require_full_protocol(a.protocol, a.source_manifest)

    sm = json.load(open(a.source_manifest))
    audit = json.load(open(a.source_audit))
    check_inputs(sm, a.split, a.out_dir)
    o_records = risk30.load_all(a.out_dir)
    f_records = o_records  # same file set; keyed by (id, task)

    rows = REV.build_rows(sm, audit, o_records, a.split)
    n_bad = sum(1 for r in rows if not r["reproduced_expected_suffix"])
    if n_bad:
        raise RuntimeError(f"{n_bad} patients failed to reproduce expected O suffix; execution invalid")

    decide_c_link = None
    if a.split == "C":
        bstar_name, aurocs = REV.pick_bstar(rows)
    else:
        decision, decide_c_sha = risk30.verify_c_gate(a.decide_c)
        bstar_name = decision["bstar"]
        if bstar_name is None:
            raise RuntimeError("C201 decision has no locked bstar")
        aurocs = REV.compute_baseline_aurocs(rows)
        decide_c_link = {"path": a.decide_c, "sha256": decide_c_sha, "bstar": bstar_name, "enter_E": decision["enter_E"]}

    h1 = REV.h1_report(rows, bstar_name, a.split)
    tok = load_tokenizer()
    h2 = REV.h2_and_cost_report(sm, audit, f_records, a.split, tok)

    report = {
        "split": a.split, "n": len(rows), "bstar": bstar_name, "raw_baseline_aurocs": aurocs,
        "h1": h1, "h2": h2,
        "n_reproduced_ok": len(rows) - n_bad,
        "protocol_path": a.protocol, "protocol_digest": protocol_digest,
        "source_manifest_path": a.source_manifest, "source_manifest_sha256": sha256_file(a.source_manifest),
        "source_audit_path": a.source_audit, "source_audit_sha256": sha256_file(a.source_audit),
        "decide_c_link": decide_c_link,
    }
    os.makedirs(os.path.dirname(a.report_out), exist_ok=True)
    json.dump(report, open(a.report_out, "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k not in ("h2",)}, indent=1))
    h2_summary = {k: v for k, v in h2.items() if k not in ("events_detail", "recovered_ids", "cost_rows")}
    print("h2 summary:", json.dumps(h2_summary, indent=1))


if __name__ == "__main__":
    main()
