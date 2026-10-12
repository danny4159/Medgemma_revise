"""iter_118 독립 verifier: 원 record(텍스트) → 환자별 표 → 계수 → CI → 판정을 ed118_eval과 별개의 코드로 재계산한다 (생성 전 잠금).

- ed118_eval의 함수를 호출하지 않는다 (spec의 classify 결과만 입력으로 받지 않고, 독립 단순 규칙으로 방향 일관성을 별도 검사한다).
- 결과는 results/iter_118/eval/verify.json 에 새로 쓴다 (덮어쓰기 거부).
"""
import json
import os
import re
import sys

import numpy as np

EOT = "<end_of_turn>"
START = re.compile(r"^\W*(yes|no)\b(?=\s*[.,:;!]|\s*$|\s*\n)", re.I)


def clean(t):
    return (t[:-len(EOT)] if t.endswith(EOT) else t).strip()


def direction_consistent(text, ended_eos, rec):
    """독립 단순 검사: (1) 비EOS면 unknown (2) direction yes/no면 해당 단어가 본문에 있다 (3) 문두 yes/no이고 모순/조건/거부가 없는데 반대 방향이면 오류."""
    t = clean(text).lower()
    d = rec["direction"]
    if not ended_eos:
        return d == "unknown"
    if d in ("yes", "no"):
        if not re.search(r"\b" + d + r"\b", t):
            return False
    m = START.match(clean(text))
    f = rec["flags"]
    if m and not (f["contradictory"] or f["conditional"]):
        if d != m.group(1).lower():
            return False
    return True


def verify(per_patient, report, recs, cond_map, labels, boot_seed=11817, boot_n=10000):
    checks = []

    def add(name, ok, **kw):
        checks.append(dict(name=name, ok=bool(ok), **kw))

    n = len(per_patient)
    byc = {}
    for r in recs:
        byc.setdefault(r["patient"], {})[cond_map[r["patient"]][r["cond"]]] = r
    add("n_patients_matches_records", n == len(byc) == len(recs) // 3 and len(recs) == 3 * n)
    add("each_patient_three_conds", all(set(v) == {"E", "C", "W"} for v in byc.values()))
    # 원문 → 방향 일관성
    bad_dir = []
    gt_of = {p: labels[p]["gt_answer"] for p in labels}
    for p in per_patient:
        for c in "ECW":
            r = byc[p["id"]][c]
            if not direction_consistent(r["suffix_text_raw"], r["ended_eos"], p[c] | dict(direction=p[c]["direction"])):
                bad_dir.append((p["id"], c))
    add("direction_consistent_with_text", not bad_dir, n_bad=len(bad_dir), examples=bad_dir[:5])
    # 정답 / outcome 재계산
    mism = []
    for p in per_patient:
        g = gt_of[p["id"]]
        for c in "ECW":
            d = p[c]["direction"]
            o = "unk" if d == "unknown" else ("ok" if d == g else "bad")
            if o != p[c]["outcome"]:
                mism.append((p["id"], c))
    add("outcome_matches_gt", not mism, n_bad=len(mism))
    # 계수 재계산 (draft 방향 검증은 verify_requests)
    cnt = lambda c, o: sum(p[c]["outcome"] == o for p in per_patient)
    for c in "ECW":
        s = report["conditions"][c]
        add(f"counts_{c}", s["explicit_ok"] == cnt(c, "ok") and s["explicit_bad"] == cnt(c, "bad") and s["unknown"] == cnt(c, "unk"))
    for c in "WC":
        t = report["transitions"][c]
        ok = True
        for a in ("ok", "bad", "unk"):
            for b in ("ok", "bad", "unk"):
                ok &= t[a][b] == sum(p["E"]["outcome"] == a and p[c]["outcome"] == b for p in per_patient)
        add(f"transition_{c}", ok)
        h = (t["ok"]["bad"] - t["bad"]["ok"]) / n
        add(f"H_{c}_point", abs(h - report["H"][c]["point"]) < 1e-12, recomputed=h)
        # unknown 범위: 전수 열거 (환자별)
        lo = hi = 0
        for p in per_patient:
            es = ["ok", "bad"] if p["E"]["outcome"] == "unk" else [p["E"]["outcome"]]
            xs = ["ok", "bad"] if p[c]["outcome"] == "unk" else [p[c]["outcome"]]
            vals = [int(e == "ok" and x == "bad") - int(e == "bad" and x == "ok") for e in es for x in xs]
            lo += min(vals)
            hi += max(vals)
        add(f"H_{c}_unknown_range", [lo / n, hi / n] == report["H_unknown_range"][c])
    # bootstrap 독립 재계산 (H_W): 층별 resample
    rng = np.random.default_rng(boot_seed)
    cats = ["opacity", "normal", "not_normal_no_opacity"]
    contrib = np.array([int(p["E"]["outcome"] == "ok" and p["W"]["outcome"] == "bad") - int(p["E"]["outcome"] == "bad" and p["W"]["outcome"] == "ok")
                        for p in per_patient], dtype=float)
    # 보고서와 같은 난수 소비 순서: 통계 벡터 순서와 무관하게 category별 한 번의 draw
    tot = np.zeros(boot_n)
    for c in cats:
        ids = np.array([i for i, p in enumerate(per_patient) if p["cat"] == c])
        if len(ids):
            draw = ids[rng.integers(0, len(ids), size=(boot_n, len(ids)))]
            tot += contrib[draw].sum(axis=1)
    s = tot / n
    lo, hi = float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))
    add("H_W_bootstrap_CI", abs(lo - report["H"]["W"]["lo"]) < 1e-12 and abs(hi - report["H"]["W"]["hi"]) < 1e-12, recomputed=[lo, hi])
    # 판정 분기 재계산
    hw = report["H"]["W"]
    lab = "content_harm_signal" if (hw["point"] >= 0.10 and lo > 0) else ("no_large_content_harm" if hi < 0.10 else "inconclusive")
    add("decision_label", lab == report["decision"]["label"], recomputed=lab)
    # 정책 S 재계산
    badS = []
    for p in per_patient:
        b = p["B"]
        e = p["E"]["direction"]
        g = gt_of[p["id"]]
        for c, draft in (("S_C", g), ("S_W", "no" if g == "yes" else "yes")):
            want = e if (e in ("yes", "no") and e == b) else draft
            if p["policy"][c] != want:
                badS.append((p["id"], c))
    add("policy_S", not badS)
    detm = [p["id"] for p in per_patient if p["B"] != ("yes" if p["n_det"] > 0 else "no")]
    add("policy_B_matches_box_count", not detm)
    add("total_by_category", sum(report["n_by_category"].values()) == n)
    return checks


def verify_requests(req_rows, cond_map, labels):
    """요청 prompt를 독립 파싱: E에는 draft 줄이 없고, C는 gt 방향, W는 반대 방향. 세 요청의 영상 hash 동일."""
    checks = []
    pat = re.compile(r"first-pass answer to this question was: (Yes|No)\.")
    by = {}
    for r in req_rows:
        by.setdefault(r["patient"], []).append(r)
    bad = []
    for pid, rs in by.items():
        g = labels[pid]["gt_answer"]
        if len({r["input_pixel_sha256"] for r in rs}) != 1:
            bad.append((pid, "pixel"))
        for r in rs:
            c = cond_map[pid][r["cond"]]
            m = pat.search(r["prompt"])
            want = None if c == "E" else (g if c == "C" else ("no" if g == "yes" else "yes"))
            got = m.group(1).lower() if m else None
            if got != want:
                bad.append((pid, c, got, want))
    checks.append(dict(name="request_draft_direction_and_pixels", ok=not bad, n_bad=len(bad), examples=bad[:5]))
    return checks
