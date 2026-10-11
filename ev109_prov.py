"""iter_109 1단계: 사용 출력의 출처 연결 검증 + GT 없는 추출 ledger 생성·잠금.

사용: python ev109_prov.py   (결과: results/iter_109/provenance/{manifest,responses_extracted.jsonl,ledger_lock}.json, 기존 파일은 덮어쓰지 않는다)
- iter_108 D/T/C/L: ev108_run.verify_completion (요청 집합·record digest·영상/tensor·completion worker file hash) 재검증. TECH는 w2만 사용.
- F: iter_016 gen/{e180_plain,e600x_plain}__M0 의 requests_sha256·record 연결·행 수·현재 영상 hash. 역사적 protocol digest 재계산 모듈은 이 브랜치에 없어 재계산하지 않는다(한계로 기록).
- 추출 함수는 응답 텍스트·target만 받는다. cats/GT는 이 스크립트에서 읽지 않는다 (infer manifest의 image hash만 사용).
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import ev108_data as D
import ev108_run as RUN
import ev109_extract as X

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results/iter_109/provenance"
R108 = ROOT / "results/iter_108"
DIRS = {"TECH": R108 / "gen/TECH/w2", "P180R": R108 / "gen/P180R/main", "E600R": R108 / "gen/E600R/main"}


def sha(p):
    return D.file_sha(p)


def save_new(path, obj):
    if Path(path).exists():
        sys.exit(f"exists: {path}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def verify_F(first_pix):
    """returns (records dict[(id,target)]->rec, report). 오류는 problems에 모은다 (F 관련 비교만 비활성화하는 근거)."""
    problems, report, recs_out = [], {}, {}
    sets = json.load(open(D.R16 / "manifests/sets.json"))  # 환자 집합만 읽는다 (labels.json/GT 미접근)
    e600 = {i for c in sets["E600"] for i in sets["E600"][c]}
    for st in D.F_STAGES:
        d = D.R16 / "gen" / st
        comp = json.load(open(d / "completion.json"))
        stem = st.replace("__M0", "")
        req_path = D.R16 / "requests" / f"{st}.jsonl"
        rows = D.read_jsonl(req_path)
        rows_by = {r["request_id"]: r for r in rows}
        rep = {"requests_sha256_file": sha(req_path), "requests_sha256_completion": comp["requests_sha256"],
               "protocol_digest": comp["protocol_digest"], "returncodes": comp["returncodes"], "n_expected": comp["n_expected"]}
        if rep["requests_sha256_file"] != comp["requests_sha256"]:
            problems.append(f"{st}: requests_sha256 mismatch")
        if any(c != 0 for c in comp["returncodes"]) or comp.get("verify_error"):
            problems.append(f"{st}: completion nonzero/verify_error")
        recs, per_file_actual = [], {}
        for fn in sorted(d.glob("gen_worker*.jsonl")):
            rr = D.read_jsonl(fn)
            per_file_actual[fn.name] = len(rr)
            recs += rr
        rep["per_file_rows_actual"], rep["per_file_rows_completion"] = per_file_actual, comp["per_file"]
        if per_file_actual != comp["per_file"]:
            problems.append(f"{st}: worker row counts differ from completion")
        ids = [r["request_id"] for r in recs]
        if len(ids) != len(set(ids)):
            problems.append(f"{st}: duplicate request ids")
        if set(ids) != set(rows_by):
            problems.append(f"{st}: request set mismatch missing={len(set(rows_by) - set(ids))} extra={len(set(ids) - set(rows_by))}")
        bad = 0
        for r in recs:
            q = rows_by.get(r["request_id"])
            if q is None:
                continue
            if (r["id"], r["target"], r["image"], r["image_file_sha256"], r["prompt_sha256"], r["checkpoint"], r["fmt"], r["condition"]) != \
               (q["id"], q["target"], q["image"], q["file_sha256"], q["prompt_sha256"], q["checkpoint"], q["fmt"], q["condition"]):
                bad += 1
            if r["protocol_digest"] != comp["protocol_digest"] or r["config_digest"] != comp["config_digest"] or r.get("adapter_digest") is not None:
                bad += 1
            if r["id"] not in e600:
                bad += 1
            if r["id"] in first_pix and r["input_pixel_sha256"] != first_pix[r["id"]]:
                bad += 1
            key = (r["id"], r["target"])
            if key in recs_out:
                problems.append(f"dup F {key}")
            recs_out[key] = r
        rep["n_records"], rep["n_row_link_problems"] = len(recs), bad
        rep["n_final_not_eos"] = sum(not r["ended_eos"] for r in recs)
        if bad:
            problems.append(f"{st}: {bad} record/request link problems")
        # 현재 영상 file hash
        badimg = sum(1 for r in recs if sha(ROOT / r["image"]) != r["image_file_sha256"]) if False else 0
        imgs = {}
        for r in recs:
            imgs[r["image"]] = r["image_file_sha256"]
        badimg = sum(1 for p, h in imgs.items() if sha(ROOT / p) != h)
        rep["n_images"], rep["n_current_image_file_hash_mismatch"] = len(imgs), badimg
        if badimg:
            problems.append(f"{st}: current image hash mismatch {badimg}")
        report[st] = rep
    patients = {k[0] for k in recs_out}
    report["n_patients"], report["n_records_total"] = len(patients), len(recs_out)
    if patients != e600 or len(recs_out) != 1200:
        problems.append(f"F coverage: patients {len(patients)} / records {len(recs_out)} != E600 600 / 1200")
    report["problems"] = problems
    report["note"] = ("F completion의 per_file은 행 수이며 worker file hash가 아님. 역사적 protocol_digest 재계산 모듈(qa_protocol)은 현재 브랜치에 없어 "
                      "재계산하지 않았다. 아래 현재 hash는 이번 분석의 불변성 증거이지 과거 무결성의 소급 증명이 아니다.")
    return recs_out, report


def main_F():
    """첫 실행에서 first_pix 기준 버그(L 행 포함)로 F 검증이 실패해 iter_108 ledger만 잠겨 있다. 같은 규칙 lock 아래 F 전용 ledger를 추가한다."""
    if not (OUT / "ledger_lock.json").exists() or (OUT / "ledger_lock_F.json").exists():
        sys.exit("need existing main ledger lock and no F lock")
    lock = json.load(open(ROOT / "results/iter_109/extract_lock.json"))
    for f, h in lock["files_sha256"].items():
        if sha(ROOT / f) != h:
            sys.exit(f"extract rule file changed after lock: {f}")
    first_pix = {}
    for stage, d in DIRS.items():
        recs = RUN.verify_completion(str(d), str(R108 / f"data/requests_{stage}.jsonl"), str(R108 / f"protocol/protocol_{stage}.json"))
        for r in recs:
            if r["cond"] in ("D", "T", "C"):
                first_pix.setdefault(r["patient"], r["input_pixel_sha256"][0])
    F, frep = verify_F(first_pix)
    rows = []
    if not frep["problems"]:
        for (p, t), r in sorted(F.items()):
            row = dict(patient=p, cond="F", target=t, source="iter016", request_id=r["request_id"], ended_eos=r["ended_eos"], raw=r["suffix_text_raw"])
            row["ext"] = X.resolve(t, row["raw"], row["ended_eos"])
            rows.append(row)
    lp = OUT / "responses_extracted_F.jsonl"
    if rows:
        lp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    save_new(OUT / "manifest_F.json", dict(F=frep, F_usable=bool(rows), n_first_pix_patients=len(first_pix), ledger_F=dict(path=str(lp.relative_to(ROOT)), sha256=sha(lp) if rows else None, n_rows=len(rows)),
                                           note="첫 manifest.json의 F 실패는 first_pix 기준 버그(L 행 포함)였고 이 파일이 대체 검증이다. 첫 파일은 보존한다."))
    save_new(OUT / "ledger_lock_F.json", dict(locked_at_unix=time.time(), locked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"), ledger_sha256=sha(lp) if rows else None,
                                              rules_sha256=sha(ROOT / "ev109_extract.py"), gt_loaded_before_lock=False))
    print("F usable", bool(rows), frep["problems"])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "F":
        return main_F()
    if (OUT / "ledger_lock.json").exists():
        sys.exit("ledger_lock exists; not overwriting")
    t0 = time.time()
    lock = json.load(open(ROOT / "results/iter_109/extract_lock.json"))
    for f, h in lock["files_sha256"].items():
        if sha(ROOT / f) != h:
            sys.exit(f"extract rule file changed after lock: {f}")
    manifest = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "extract_lock": lock, "iter108": {}}
    ans, first_pix = {}, {}
    for stage, d in DIRS.items():
        st = {"TECH": "TECH", "P180R": "P180R", "E600R": "E600R"}[stage]
        recs = RUN.verify_completion(str(d), str(R108 / f"data/requests_{st}.jsonl"), str(R108 / f"protocol/protocol_{st}.json"))
        comp = json.load(open(d / "completion.json"))
        manifest["iter108"][stage] = {"dir": str(d.relative_to(ROOT)), "n_records": len(recs), "worker_file_sha256": comp["worker_file_sha256"],
                                      "protocol_digest": comp["protocol_digest"], "exit_codes": comp["exit_codes"], "verify_completion": "pass"}
        for r in recs:
            k = (r["patient"], r["cond"], r["target"])
            if k in ans:
                sys.exit(f"duplicate answer {k}")
            ans[k] = r
            if r["cond"] in ("D", "T", "C"):  # L은 crop 단독이라 원본 영상이 아님
                first_pix.setdefault(r["patient"], r["input_pixel_sha256"][0])
    manifest["iter108_total_unique"] = len(ans)
    F, frep = verify_F(first_pix)
    manifest["F"] = frep
    f_ok = not frep["problems"]
    manifest["F_usable"] = f_ok
    rows = []
    for (p, c, t), r in sorted(ans.items()):
        rows.append(dict(patient=p, cond=c, target=t, source="iter108", request_id=r["request_id"], ended_eos=r["ended_eos"], raw=r["suffix_text_raw"]))
    if f_ok:
        for (p, t), r in sorted(F.items()):
            rows.append(dict(patient=p, cond="F", target=t, source="iter016", request_id=r["request_id"], ended_eos=r["ended_eos"], raw=r["suffix_text_raw"]))
    for row in rows:
        row["ext"] = X.resolve(row["target"], row["raw"], row["ended_eos"])
    OUT.mkdir(parents=True, exist_ok=True)
    lp = OUT / "responses_extracted.jsonl"
    if lp.exists():
        sys.exit("ledger exists")
    lp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    manifest["ledger"] = {"path": str(lp.relative_to(ROOT)), "sha256": sha(lp), "n_rows": len(rows)}
    manifest["extract_rules_sha256"] = sha(ROOT / "ev109_extract.py")
    manifest["elapsed_s"] = time.time() - t0
    save_new(OUT / "manifest.json", manifest)
    save_new(OUT / "ledger_lock.json", {"locked_at_unix": time.time(), "locked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ledger_sha256": manifest["ledger"]["sha256"],
                                         "rules_sha256": manifest["extract_rules_sha256"], "gt_loaded_before_lock": False})
    from collections import Counter
    c = Counter((r["cond"], r["target"], r["ext"]["source"]) for r in rows)
    print(json.dumps({f"{k[0]}_{k[1]}_{k[2]}": v for k, v in sorted(c.items())}, indent=0))
    print("F usable:", f_ok, frep["problems"][:5], "elapsed", manifest["elapsed_s"])


if __name__ == "__main__":
    main()
