"""iter_049 회귀 검사: 합성 결함 행 거부 + 실제 산출물 독립 재계산. 결과 -> results/iter_049/tests/fixtures_mt49.json"""
import copy
import json
import os
import re
import shutil
import sys
import tempfile

import mt49_audit as A
from mt49_fetch import OUT
from mt49_images import safe_rel

CHECKS = []


def chk(name, cond, detail=""):
    CHECKS.append({"name": name, "pass": bool(cond), "detail": str(detail)})


def base(n=3, mod="X-ray"):
    r = {"title": "Case number 77", "CLINICAL_HISTORY": "A patient with pain.",
         "IMAGING_FINDINGS": "secret findings", "discussion": "d",
         "options": {k: "Dx " + k for k in "ABCDE"}, "correct_answer": "B", "correct_answer_text": "Dx B",
         "ICD Chapter": "c", "ICD Block": "b", "ICD Category": "k",
         "is_longitudinal": False, "timepoint_count": 1, "interval_text": "", "image_count": n}
    for i in range(1, 50):
        k = "image_%02d_" % i
        if i <= n:
            r.update({k + "id": "id%d" % i, k + "path": "images/case00077/id%d.jpg" % i, k + "caption": "cap",
                      k + "modality": mod, k + "sub_modality": "Plain radiograph"})
        else:
            r.update({k + s: "" for s in ("id", "path", "caption", "modality", "sub_modality")})
    return r


def main():
    ok, fr, _ = A.classify(base())
    chk("baseline_eligible (title/path zero-padding 허용)", ok and fr == "eligible")
    r = base(); r["image_count"] = 4
    chk("slot_count_mismatch 거부", A.classify(r)[1] == "R1_schema" and "slot_count_mismatch" in A.classify(r)[2])
    r = base(); r["image_02_path"] = ""
    chk("partial_slot 거부", "partial_slot:2" in A.classify(r)[2])
    r = base(); r["image_03_id"] = r["image_02_id"]; r["image_03_path"] = r["image_02_path"]
    chk("중복 영상 id/path 거부", {"dup_image_id_in_case", "dup_image_path_in_case"} <= set(A.classify(r)[2]) or
        "path_id_mismatch" in A.classify(r)[2])
    r = base(); r["image_02_path"] = "images/case00078/id2.jpg"
    chk("다른 case 경로 거부", "path_case_mismatch" in A.classify(r)[2])
    r = base(); r["options"]["D"] = r["options"]["A"]
    chk("중복 선택지 거부", A.classify(r)[1] == "R2_answer")
    r = base(); r["correct_answer_text"] = "Dx C"
    chk("정답 text/letter 불일치 거부", A.classify(r)[2] == ["answer_text_mismatch"])
    r = base(); r["correct_answer"] = "F"
    chk("정답 letter 범위 밖 거부", A.classify(r)[1] == "R2_answer")
    r = base(); r["options"].pop("E")
    chk("options 5개 아님 거부", A.classify(r)[2] == ["options_not_A_E"])
    r = base(); r["image_02_modality"] = "CT"
    chk("혼합 modality 거부 (삭제로 구제하지 않음)", A.classify(r)[1] == "R3_not_all_xray")
    r = base(); r["is_longitudinal"] = True; r["timepoint_count"] = 2
    chk("longitudinal 거부", A.classify(r)[1] == "R4_longitudinal")
    r = base(); r["is_longitudinal"] = False; r["timepoint_count"] = 2
    chk("longitudinal 상충(false & tc=2) 거부, 보정 안 함", A.classify(r)[1] == "R4_longitudinal")
    r = base(); r["is_longitudinal"] = None
    chk("is_longitudinal 누락(None) 거부", A.classify(r)[1] in ("R1_schema", "R4_longitudinal") and not A.classify(r)[0])
    r = base(1)
    chk("단일 영상 거부", A.classify(r)[1] == "R5_single_image")
    r = base(); del r["correct_answer"]
    chk("필수 필드 누락 거부", "missing_field:correct_answer" in A.classify(r)[2])
    # 누출 필드 혼입 거부
    v = A.infer_view(base())
    chk("정상 추론 view 통과", A.assert_no_leak(v))
    for f in ("correct_answer", "IMAGING_FINDINGS", "discussion", "ICD Chapter", "image_01_caption"):
        w = copy.deepcopy(v); w[f] = "x"
        try:
            A.assert_no_leak(w); res = False
        except ValueError:
            res = True
        chk("추론 view 에 %s 혼입 거부" % f, res)
    w = copy.deepcopy(v); w["images"][0]["caption"] = "x"
    try:
        A.assert_no_leak(w); res = False
    except ValueError:
        res = True
    chk("영상 항목에 caption 혼입 거부", res)
    chk("추론 view 에 정답/발견 문자열 없음", "secret" not in json.dumps(v) and "Dx B" not in json.dumps(v["CLINICAL_HISTORY"]))
    # 이력 누출 표시
    r = base(); r["CLINICAL_HISTORY"] = "Findings of dx b were described."
    chk("이력 내 정답 텍스트 표시", "answer_text_in_history" in A.history_leak_flags(r))
    # path traversal
    for bad in ("../x.jpg", "/etc/passwd", "images/case1/../../x", "other/case1/a.jpg"):
        try:
            safe_rel(bad); res = False
        except ValueError:
            res = True
        chk("경로 이탈 거부 %s" % bad, res)
    # malformed jsonl 줄 및 원본 hash 변경 시 감사 재사용 금지
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps(base()) + "\n{broken\n")
    rows = A.read_rows(p)
    chk("malformed JSON 줄 탐지", "__malformed__" in rows[1])
    out = os.path.join(d, "audit")
    s = A.audit(p, out, None, expect_rows=2)
    chk("합성 audit: malformed 기록·적격 1", s["malformed_lines"] == [2] and s["eligible_N"] == 1)
    with open(p, "a") as f:
        f.write(json.dumps(dict(base(), title="Case number 78")) + "\n")
    try:
        A.audit(p, out, None); res = False
    except RuntimeError:
        res = True
    chk("원본 hash 변경 시 기존 감사 완료 재사용 거부", res)
    try:
        A.audit(p, os.path.join(d, "a2"), "0" * 64); res = False
    except RuntimeError:
        res = True
    chk("기대 sha256 불일치 거부", res)
    shutil.rmtree(d, ignore_errors=True)

    # ---- 실제 산출물 독립 재계산 (audit 코드 미사용, 최소 로직) ----
    raw = [json.loads(l) for l in open(os.path.join(OUT, "raw", "train.jsonl"))]
    n_x = 0; n_el = 0; S = 0
    ids = {}
    for r in raw:
        ms = [r["image_%02d_modality" % i] for i in range(1, 50) if r["image_%02d_id" % i]]
        if ms and set(ms) == {"X-ray"}:
            n_x += 1
            n_img = len(ms)
            opts = [r["options"][k].strip().lower() for k in "ABCDE"]
            if (n_img >= 2 and r["is_longitudinal"] is False and r["timepoint_count"] == 1 and
                    len(set(opts)) == 5 and r["options"][r["correct_answer"]] == r["correct_answer_text"] and
                    n_img == r["image_count"]):
                n_el += 1; S += n_img
                ids[r["title"]] = [r["image_%02d_path" % i] for i in range(1, n_img + 1)]
    summ = json.load(open(os.path.join(OUT, "audit_v2", "audit_summary.json")))
    chk("독립 재계산: X-ray-only 433 (논문 M.6과 일치)", n_x == 433 == summ["xray_only_modality_set_cases"], n_x)
    chk("독립 재계산: 적격 N/S 일치", (n_el, S) == (summ["eligible_N"], summ["eligible_S_images"]), (n_el, S))
    chk("실패 사유 합 = 7347", sum(summ["first_failure_counts"].values()) == 7347)
    el = [json.loads(l) for l in open(os.path.join(OUT, "audit_v2", "eligible_cases.jsonl"))]
    chk("적격 manifest 의 영상 경로가 독립 재계산과 일치",
        {c["case_key"]: [i["path"] for i in c["images"]] for c in el} == ids)
    chk("적격 manifest 추론 필드에 누출 필드 없음", all(A.assert_no_leak({k: c[k] for k in A.INFER_FIELDS}) for c in el))
    chk("적격 manifest 추론 필드가 INFER_FIELDS 와 정확히 일치",
        all(set(c) - {"_eval", "_audit"} == set(A.INFER_FIELDS) for c in el))
    im = json.load(open(os.path.join(OUT, "image_manifest.json")))
    chk("영상 manifest: 896개 전부 decode 성공, 실패 0", im["n_images"] == 896 and im["n_bad"] == 0)
    chk("영상 파일 경로가 images/ 아래에만 존재", all(os.path.realpath(os.path.join(OUT, r["path"])).startswith(
        os.path.realpath(os.path.join(OUT, "images")) + os.sep) for r in im["records"]))
    chk("train 이외 split 영상 미포함 (case 번호가 train title 집합)", all(
        any(k == "Case number %d" % int(re.search(r"case(\d+)/", r["path"]).group(1)) for k in [r["case_key"]])
        for r in im["records"]))
    chk("test.jsonl 미다운로드", not os.path.exists(os.path.join(OUT, "raw", "test.jsonl")))
    os.makedirs(os.path.join(OUT, "tests"), exist_ok=True)
    npass = sum(c["pass"] for c in CHECKS)
    with open(os.path.join(OUT, "tests", "fixtures_mt49.json"), "x") as f:
        json.dump({"n": len(CHECKS), "n_pass": npass, "checks": CHECKS}, f, indent=1, ensure_ascii=False)
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["name"], c["detail"])
    print("%d/%d PASS" % (npass, len(CHECKS)))
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
