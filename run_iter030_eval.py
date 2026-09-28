"""iter_030 평가 실행기: C201 또는 E402의 O/F 결과를 읽어 report.json을 만든다.

--split C: B*를 새로 선택해 report와 decision(E 진입 gate)을 만든다.
--split E: C에서 잠근 B*를 그대로 적용해 report만 만든다 (재선택하지 않는다).
"""
import argparse
import json
import os

from rsna_diag import risk30, risk30_eval as REV


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
    ap.add_argument("--split", required=True, choices=["C", "E"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report-out", required=True)
    ap.add_argument("--bstar", default=None, help="E에서 C가 잠근 B* 이름을 그대로 넘긴다 (필수)")
    a = ap.parse_args()
    if a.split == "E" and not a.bstar:
        raise RuntimeError("E 평가는 C에서 잠근 --bstar가 필요하다 (재선택 금지)")
    if os.path.exists(a.report_out):
        raise RuntimeError(f"refusing to overwrite existing {a.report_out}")

    sm = json.load(open(a.source_manifest))
    audit = json.load(open(a.source_audit))
    check_inputs(sm, a.split, a.out_dir)
    o_records = risk30.load_all(a.out_dir)
    f_records = o_records  # same file set; keyed by (id, task)

    rows = REV.build_rows(sm, audit, o_records, a.split)
    n_bad = sum(1 for r in rows if not r["reproduced_expected_suffix"])
    if n_bad:
        raise RuntimeError(f"{n_bad} patients failed to reproduce expected O suffix; execution invalid")

    if a.split == "C":
        bstar_name, aurocs = REV.pick_bstar(rows)
    else:
        bstar_name, aurocs = a.bstar, REV.compute_baseline_aurocs(rows)

    h1 = REV.h1_report(rows, bstar_name)
    tok = load_tokenizer()
    h2 = REV.h2_and_cost_report(sm, audit, f_records, a.split, tok)

    report = {
        "split": a.split, "n": len(rows), "bstar": bstar_name, "raw_baseline_aurocs": aurocs,
        "h1": h1, "h2": h2,
        "n_reproduced_ok": len(rows) - n_bad,
    }
    os.makedirs(os.path.dirname(a.report_out), exist_ok=True)
    json.dump(report, open(a.report_out, "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k not in ("h2",)}, indent=1))
    print("h2 summary:", {k: v for k, v in h2.items() if k not in ("events_detail", "recovered_ids", "cost_rows")})


if __name__ == "__main__":
    main()
