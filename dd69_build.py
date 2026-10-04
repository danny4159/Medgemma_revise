"""iter_069 자료 봉인: 적격 20 case 표, 추론 요청(정답·caption 미포함), 별도 labels, 제외 기록, hash manifest.
새 경로(results/iter_069/data)에만 쓰고 기존 파일이 있으면 실패한다 (x 모드)."""
import hashlib
import json
import os
import re
import sys

import dd69_cases as C
import dd69_fetch as F
import dd69_spec as S

DATA = "data"


def sha_file(p):
    return F.sha256_file(p)


def build():
    rows = C.load_rows()
    s180 = C.search180(rows)
    assert len(s180) == 180
    cand_man = json.load(open(F.safe_dest("cand/image_manifest_cand.json")))
    imrec = {(r["case"], r["kind"]): r for r in cand_man["records"]}
    cand_by = {x[0]: x for x in C.CAND}
    cases, labels, reqs, reqs_r = [], {}, [], []
    seen_file, seen_pix = {}, {}
    for n, di, ai, lab, tgt in sorted(S.ELIGIBLE):
        c = cand_by[n]
        assert (c[1], c[2], c[3]) == (di, ai, lab), n
        r = rows[n]
        d, a = imrec[(n, "DWI")], imrec[(n, "ADC")]
        assert d["image_index"] == di and a["image_index"] == ai and d["modality"] == "MRI" and a["modality"] == "MRI"
        for rec in (d, a):
            for key, tab in (("file_sha256", seen_file), ("pixel_sha256", seen_pix)):
                if rec[key] in tab:
                    raise RuntimeError(f"duplicate {key} between {tab[rec[key]]} and case {n}")
                tab[rec[key]] = n
        fnd = [s for s in re.split(r"(?<=[.;])\s+", r["IMAGING_FINDINGS"]) if re.search(r"ADC|DWI|diffusion", s, re.I)]
        cases.append({"case": n, "title": r["title"], "label": lab, "target": tgt,
                      "dwi": {"index": di, "remote_path": d["remote_path"], "file_sha256": d["file_sha256"], "pixel_sha256": d["pixel_sha256"],
                              "caption": r["image_%02d_caption" % di]},
                      "adc": {"index": ai, "remote_path": a["remote_path"], "file_sha256": a["file_sha256"], "pixel_sha256": a["pixel_sha256"],
                              "caption": r["image_%02d_caption" % ai]},
                      "findings_sentences": fnd[:6], "source_evidence": c[4]})
        labels[str(n)] = {"label": lab, "gt": {k: S.gt(k, lab) for k in S.CONDS + [S.R_COND]}}
        path = {"DWI": os.path.join(F.ROOT, d["remote_path"]), "ADC": os.path.join(F.ROOT, a["remote_path"])}
        for cond in S.CONDS:
            reqs.append({"rid": f"c{n}_{cond}", "case": n, "cond": cond, "images": [os.path.relpath(path[k]) for k in S.COND_IMAGES[cond]],
                         "prompt": S.prompt(cond, tgt, lab if cond == "O" else None)})
        reqs_r.append({"rid": f"c{n}_R", "case": n, "cond": "R", "images": [os.path.relpath(path["ADC"])] * 2, "prompt": S.prompt("R", tgt)})
    out = {"cases": cases}
    man = {"spec_version": S.SPEC_VERSION, "train_sha256": C.TRAIN_SHA256, "hf_revision": F.HF_REV, "n_search_rows": len(s180),
           "n_text_candidates_checked": len(C.CAND), "n_visual_excluded": len(S.VISUAL_EXCLUDED), "n_eligible": len(cases),
           "n_low": sum(1 for c in cases if c["label"] == "LOW"), "n_not_low": sum(1 for c in cases if c["label"] == "NOT_LOW"),
           "visual_excluded": S.VISUAL_EXCLUDED, "text_excluded_in_74_separate": C.EXCLUDED_TEXT, "PIL": __import__("PIL").__version__}
    files = {"cases_private.json": out, "labels.json": labels, "build_manifest.json": man}
    for name, obj in files.items():
        with open(F.safe_dest(f"{DATA}/{name}"), "x") as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
    for name, rr in (("requests_main.jsonl", reqs), ("requests_R.jsonl", reqs_r)):
        with open(F.safe_dest(f"{DATA}/{name}"), "x") as f:
            for q in rr:
                f.write(json.dumps(q) + "\n")
    print(json.dumps({k: man[k] for k in ("n_eligible", "n_low", "n_not_low")}), len(reqs), len(reqs_r))


if __name__ == "__main__":
    os.makedirs(F.safe_dest(DATA), exist_ok=True)
    sys.exit(build())


def make_tech():
    """기술 사례: case ID 순 첫 LOW(7006), 첫 NOT_LOW(14955)의 main 요청 14건을 requests_tech.jsonl 로 분리 (이미 생성된 파일을 재현하는 함수; x 모드)."""
    cases = json.load(open(F.safe_dest(f"{DATA}/cases_private.json")))["cases"]
    first = [min(c["case"] for c in cases if c["label"] == lab) for lab in ("LOW", "NOT_LOW")]
    rows = [json.loads(l) for l in open(F.safe_dest(f"{DATA}/requests_main.jsonl"))]
    with open(F.safe_dest(f"{DATA}/requests_tech.jsonl"), "x") as f:
        for r in rows:
            if r["case"] in first:
                f.write(json.dumps(r) + "\n")
    return first
