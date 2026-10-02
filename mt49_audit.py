"""iter_049: MedThinkVQA train metadata 전수 감사 (CPU-only).

검사 함수는 순수 함수(row -> 문제 목록)로 두고 test_mt49.py 에서 회귀 검사한다.
적격 규칙(고정 순서): R1 schema/slot 정합, R2 정답-선택지 정합, R3 모든 영상 modality=X-ray,
R4 is_longitudinal=false & timepoint_count=1, R5 고유 영상(id/path) >= 2.
누락·상충 값은 보정하지 않고 reason 으로 집계한다. 모델 출력/정오답은 사용하지 않는다.
"""
import collections
import hashlib
import json
import os
import re
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "iter_049")
MAXSLOT = 49
LETTERS = "ABCDE"
# 추론 입력 허용 필드 / 평가·감사 전용 필드
INFER_FIELDS = ("case_key", "CLINICAL_HISTORY", "options", "images")
EVAL_ONLY = ("IMAGING_FINDINGS", "discussion", "correct_answer", "correct_answer_text",
             "ICD Chapter", "ICD Block", "ICD Category", "caption")
FORBIDDEN_IN_INFER = set(EVAL_ONLY) | {"image_%02d_caption" % i for i in range(1, MAXSLOT + 1)}


def slots(row):
    out = []
    for i in range(1, MAXSLOT + 1):
        k = "image_%02d_" % i
        vals = {s: row.get(k + s) for s in ("id", "path", "caption", "modality", "sub_modality")}
        out.append((i, vals))
    return out


def schema_problems(row):
    """R1: 필수 필드, image_count 와 nonempty slot, slot 내부 일관성, 중복 영상."""
    p = []
    for k in ("title", "CLINICAL_HISTORY", "options", "correct_answer", "correct_answer_text",
              "is_longitudinal", "timepoint_count", "image_count"):
        if k not in row or row[k] is None:
            p.append("missing_field:" + k)
    if p:
        return p
    ne = []
    for i, v in slots(row):
        filled = [bool(v[s]) for s in ("id", "path", "modality")]
        if any(filled) and not all(filled):
            p.append("partial_slot:%d" % i)
        if all(filled):
            ne.append((i, v))
    if not isinstance(row["image_count"], int) or row["image_count"] != len(ne):
        p.append("slot_count_mismatch")
    # nonempty slot 이 앞에서부터 연속인지
    if ne and [i for i, _ in ne] != list(range(1, len(ne) + 1)):
        p.append("slot_gap")
    ids = [v["id"] for _, v in ne]
    paths = [v["path"] for _, v in ne]
    if len(set(ids)) != len(ids):
        p.append("dup_image_id_in_case")
    if len(set(paths)) != len(paths):
        p.append("dup_image_path_in_case")
    m = re.fullmatch(r"Case number (\d+)", row["title"] or "")
    for _, v in ne:
        pm = re.fullmatch(r"images/case(\d+)/([^/\\]+)\.jpg", v["path"])
        if not pm:
            p.append("bad_path_form")
            break
        if m and int(pm.group(1)) != int(m.group(1)):  # title 과 경로는 zero-padding 만 다를 수 있다
            p.append("path_case_mismatch")
            break
        if pm.group(2) != v["id"]:
            p.append("path_id_mismatch")
            break
    return p


def answer_problems(row):
    """R2: options A-E 와 정답 letter/text 대응."""
    p = []
    o = row.get("options")
    if not isinstance(o, dict) or sorted(o.keys()) != list(LETTERS):
        return ["options_not_A_E"]
    if any(not isinstance(o[k], str) or not o[k].strip() for k in LETTERS):
        p.append("empty_option")
    if len({o[k].strip().lower() for k in LETTERS}) != 5:
        p.append("duplicate_option_text")
    ca = row.get("correct_answer")
    if ca not in LETTERS:
        p.append("bad_answer_letter")
    elif o[ca] != row.get("correct_answer_text"):
        p.append("answer_text_mismatch")
    return p


def modalities(row):
    return [v["modality"] for _, v in slots(row) if v["id"] and v["path"]]


def classify(row):
    """고정 순서 적용 -> (eligible, first_reason, all_reasons)."""
    reasons = []
    sp = schema_problems(row)
    if sp:
        return False, "R1_schema", sp
    ap = answer_problems(row)
    if ap:
        return False, "R2_answer", ap
    mods = modalities(row)
    if any(m != "X-ray" for m in mods):
        return False, "R3_not_all_xray", sorted(set(mods))
    lg = row["is_longitudinal"]
    tc = row["timepoint_count"]
    if lg is not False or tc != 1:
        return False, "R4_longitudinal", ["is_longitudinal=%r timepoint_count=%r" % (lg, tc)]
    if row["image_count"] < 2:
        return False, "R5_single_image", []
    return True, "eligible", []


def case_key(row):
    return row["title"]


def infer_view(row):
    """추론 입력: 임상 이력, options, 영상(id/path)만. caption/정답/발견은 포함하지 않는다."""
    imgs = [{"id": v["id"], "path": v["path"]} for _, v in slots(row) if v["id"] and v["path"]]
    return {"case_key": case_key(row), "CLINICAL_HISTORY": row["CLINICAL_HISTORY"],
            "options": dict(row["options"]), "images": imgs}


def assert_no_leak(view):
    bad = [k for k in view if k in FORBIDDEN_IN_INFER]
    for im in view.get("images", []):
        bad += [k for k in im if k in FORBIDDEN_IN_INFER]
    if bad:
        raise ValueError("leak fields in inference view: %s" % bad)
    if set(view) != set(INFER_FIELDS):
        raise ValueError("unexpected fields: %s" % sorted(set(view) ^ set(INFER_FIELDS)))
    return True


def norm_text(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def history_leak_flags(row):
    """임상 이력에 정답 선택지 텍스트(정규화) 또는 그 핵심 토큰이 포함되는지 표시(확정 아님)."""
    h = norm_text(row["CLINICAL_HISTORY"])
    ans = norm_text(row["correct_answer_text"])
    flags = []
    if ans and ans in h:
        flags.append("answer_text_in_history")
    # 오답 선택지 포함은 대조(정답만 있는 것이 아니라 어느 선택지든 언급되는지)
    others = [norm_text(row["options"][k]) for k in LETTERS if k != row["correct_answer"]]
    if any(o and o in h for o in others):
        flags.append("distractor_text_in_history")
    toks = [t for t in ans.split() if len(t) >= 5]
    if toks and all(t in h.split() for t in toks) and "answer_text_in_history" not in flags:
        flags.append("answer_tokens_in_history")
    return flags


def read_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln, l in enumerate(f, 1):
            try:
                rows.append(json.loads(l))
            except json.JSONDecodeError:
                rows.append({"__malformed__": ln})
    return rows


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def audit(train_path, out_dir, expect_sha=None, expect_rows=7347):
    sha = file_sha(train_path)
    if expect_sha and sha != expect_sha:
        raise RuntimeError("train.jsonl sha256 mismatch")
    done = os.path.join(out_dir, "audit_done.json")
    if os.path.exists(done):
        d = json.load(open(done))
        if d.get("train_sha256") == sha:
            return d  # 같은 원본이면 재사용
        raise RuntimeError("raw hash changed; 기존 감사 결과를 재사용하지 않는다. 새 out_dir 사용")
    rows = read_rows(train_path)
    n = len(rows)
    malformed = [r["__malformed__"] for r in rows if "__malformed__" in r]
    good = [r for r in rows if "__malformed__" not in r]
    keys = collections.Counter(case_key(r) for r in good if "title" in r)
    dup_keys = {k: c for k, c in keys.items() if c > 1}
    first = collections.Counter()
    all_reason = collections.Counter()
    elig = []
    excl = []
    cascade = collections.Counter()
    for r in good:
        ok, fr, rs = classify(r)
        first[fr] += 1
        for x in rs:
            all_reason[fr + ":" + x] += 1
        (elig if ok else excl).append((r, fr, rs))
    # modality 집합 단독 X-ray (다중 영상 여부 무관) 집계 = 논문 M.6 대응 후보
    xray_only_any = 0
    xray_only_ge2 = 0
    xray_only_nonlong = 0
    mod_sets = collections.Counter()
    for r in good:
        if schema_problems(r):
            continue
        ms = frozenset(modalities(r))
        mod_sets["+".join(sorted(ms))] += 1
        if ms == {"X-ray"}:
            xray_only_any += 1
            if r["image_count"] >= 2:
                xray_only_ge2 += 1
            if r["is_longitudinal"] is False and r["timepoint_count"] == 1:
                xray_only_nonlong += 1
    # 적격 사례 요약
    cnt_dist = collections.Counter(r["image_count"] for r, _, _ in elig)
    subs = collections.Counter()
    case_subs = collections.Counter()
    icd = collections.Counter()
    for r, _, _ in elig:
        ss = sorted({v["sub_modality"] for _, v in slots(r) if v["id"]})
        case_subs["|".join(ss)] += 1
        for _, v in slots(r):
            if v["id"]:
                subs[v["sub_modality"]] += 1
        icd[r["ICD Chapter"]] += 1
    S = sum(r["image_count"] for r, _, _ in elig)
    # 적격 사례 간 중복(영상 id, 문맥+선택지)
    id_owner = collections.defaultdict(set)
    for r, _, _ in elig:
        for _, v in slots(r):
            if v["id"]:
                id_owner[v["id"]].add(case_key(r))
    shared_ids = {k: sorted(v) for k, v in id_owner.items() if len(v) > 1}
    ctx_owner = collections.defaultdict(list)
    for r, _, _ in elig:
        sig = hashlib.sha256((norm_text(r["CLINICAL_HISTORY"]) + "|" +
                              "|".join(sorted(norm_text(r["options"][k]) for k in LETTERS))).encode()).hexdigest()
        ctx_owner[sig].append(case_key(r))
    dup_ctx = [v for v in ctx_owner.values() if len(v) > 1]
    opt_owner = collections.defaultdict(list)
    for r, _, _ in elig:
        sig = "|".join(sorted(norm_text(r["options"][k]) for k in LETTERS))
        opt_owner[sig].append(case_key(r))
    dup_opts = [v for v in opt_owner.values() if len(v) > 1]
    # 전체 train 에서 영상 id 가 다른 case 와 공유되는지 (적격 사례가 비적격과 공유하는 경우 포함)
    all_owner = collections.defaultdict(set)
    for r in good:
        if schema_problems(r):
            continue
        for _, v in slots(r):
            if v["id"]:
                all_owner[v["id"]].add(case_key(r))
    elig_keys = {case_key(r) for r, _, _ in elig}
    shared_with_noneligible = sorted({k for k, v in all_owner.items() if len(v) > 1 and (v & elig_keys)})
    # 누출 표시
    lk = collections.Counter()
    leak_cases = collections.defaultdict(list)
    for r, _, _ in elig:
        fl = history_leak_flags(r)
        for f in fl:
            lk[f] += 1
            leak_cases[f].append(case_key(r))
        assert_no_leak(infer_view(r))
    ans_dist = collections.Counter(r["correct_answer"] for r, _, _ in elig)
    summary = {
        "train_sha256": sha, "rows_read": n, "rows_expected": expect_rows,
        "malformed_lines": malformed, "unique_case_keys": len(keys), "dup_case_keys": dup_keys,
        "first_failure_counts": dict(first), "all_reason_counts": dict(all_reason),
        "xray_only_modality_set_cases": xray_only_any,
        "xray_only_ge2_images": xray_only_ge2, "xray_only_nonlongitudinal": xray_only_nonlong,
        "modality_set_top": mod_sets.most_common(25),
        "eligible_N": len(elig), "eligible_S_images": S,
        "image_count_dist": dict(sorted(cnt_dist.items())),
        "sub_modality_image_counts": dict(subs.most_common()),
        "case_sub_modality_sets_top": case_subs.most_common(25),
        "icd_chapter_dist": dict(icd.most_common()),
        "answer_letter_dist": dict(ans_dist),
        "shared_image_ids_among_eligible": len(shared_ids),
        "shared_image_ids_with_any_other_case": len(shared_with_noneligible),
        "duplicate_context_options_clusters": dup_ctx,
        "duplicate_options_set_clusters_n": len(dup_opts),
        "history_leak_flags": dict(lk),
        "case_unit_note": "case(title)를 분석 단위로 쓴다. case=환자 동일성은 보장되지 않는다.",
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "eligible_cases.jsonl"), "x") as f:
        for r, _, _ in elig:
            v = infer_view(r)
            v["_eval"] = {"correct_answer": r["correct_answer"], "correct_answer_text": r["correct_answer_text"]}
            v["_audit"] = {"history_leak_flags": history_leak_flags(r),
                           "sub_modalities": sorted({s["sub_modality"] for _, s in slots(r) if s["id"]}),
                           "icd_chapter": r["ICD Chapter"], "image_count": r["image_count"]}
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "excluded_cases.jsonl"), "x") as f:
        for r, fr, rs in excl:
            f.write(json.dumps({"case_key": case_key(r), "first_reason": fr, "detail": rs}, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "leak_flag_cases.json"), "x") as f:
        json.dump(leak_cases, f, indent=1)
    with open(os.path.join(out_dir, "audit_summary.json"), "x") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)
    with open(done, "x") as f:
        json.dump({"train_sha256": sha, "eligible_N": len(elig), "S": S}, f)
    return summary


if __name__ == "__main__":
    tp = os.path.join(OUT, "raw", "train.jsonl")
    # audit/ (v0)는 path_case_mismatch 문자열 비교 오류(zero-padding)로 무효. 오류 기록으로 보존하고 audit_v2 사용
    s = audit(tp, os.path.join(OUT, "audit_v2"),
              "7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a")
    print(json.dumps({k: v for k, v in s.items() if k not in ("modality_set_top", "case_sub_modality_sets_top",
                                                              "duplicate_context_options_clusters")},
                     indent=1, ensure_ascii=False)[:6000])
