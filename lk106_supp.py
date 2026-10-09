"""iter_106 사후 기술 분석(주판정과 분리, 탐색용): 형식(좌표 유무)과 위치 내용을 분리한다.
- 요청별 좌표 출력률(valid_nonempty 비율), 좌표가 나온 요청의 조건부 회복, J/R의 box 개수, 대표 원문.
주판정 규칙·임계는 바꾸지 않는다. 입력: report_E32_per_patient.json + 원시 출력. 결과: eval/supplement_E32.json (새 파일).
"""
import json
import sys
from collections import Counter

import numpy as np

import lk106_run as R
import lk106_spec as S
import lk106_eval as E
from report86_common import save


def main():
    rows, _ = R.stage_rows("E32")
    new, _ = E.load_gen("results/iter_106/gen/E32", "E32", 2)
    ind, _ = E.load_ind_from_iter105("results/iter_105/gen/E32", 2)
    gen = lambda iid, c: (ind if c in ("I1", "I2") else new)[f"{iid}|CURE|{c}"]
    out = {"box_rate": {}, "n_boxes": {}, "conditional": {}}
    for c in ("I1", "I2", "J12", "J21", "R11", "R22"):
        st = [E.box_set(gen(r["ImageID"], c)) for r in rows]
        out["box_rate"][c] = sum(s == "valid_nonempty" for s, _ in st) / len(st)
        out["n_boxes"][c] = dict(Counter(len(b) for _, b in st))
    # 요청 수준 조건부: 좌표가 나온 J 요청에서 2 GT 중 맞힌 수
    for c in ("J12", "J21"):
        vals, only1 = [], 0
        for r in rows:
            s, b = E.box_set(gen(r["ImageID"], c))
            if s == "valid_nonempty":
                sc = S.score_boxes([r["box1"], r["box2"]], b)
                vals.append(sc["n_matched"])
                only1 += len(b) == 1
        out["conditional"][c] = {"n_with_boxes": len(vals), "mean_matched_of_2": float(np.mean(vals)) if vals else None,
                                 "dist_matched": dict(Counter(vals)), "n_single_box_outputs": only1}
    # 동일 환자 I 대비: J12 또는 J21 중 하나라도 좌표가 나온 환자의 recall(J 순서 평균)과 I
    both, any_ = [], []
    for r in rows:
        iid = r["ImageID"]
        sts = {c: E.box_set(gen(iid, c)) for c in ("J12", "J21")}
        sc = {c: S.score_boxes([r["box1"], r["box2"]], sts[c][1])["recall"] for c in sts}
        Ib = E.box_set(gen(iid, "I1"))[1] + E.box_set(gen(iid, "I2"))[1]
        rI = S.score_boxes([r["box1"], r["box2"]], Ib)["recall"]
        row = {"I": rI, "J12": sc["J12"], "J21": sc["J21"], "have": [c for c in sts if sts[c][0] == "valid_nonempty"]}
        if len(row["have"]) == 2:
            both.append(row)
        if row["have"]:
            any_.append(row)
    out["patients_both_orders_with_boxes"] = {"n": len(both), "mean_I": float(np.mean([x["I"] for x in both])) if both else None,
                                              "mean_J12": float(np.mean([x["J12"] for x in both])) if both else None,
                                              "mean_J21": float(np.mean([x["J21"] for x in both])) if both else None}
    out["patients_any_order_with_boxes"] = {"n": len(any_)}
    # 대표 원문 (조건별 처음 3개 + 좌표 있는 J 2개)
    ex = []
    for c in ("J12", "J21", "R11", "R22"):
        for r in rows[:3]:
            ex.append({"id": f"{r['ImageID'][:12]}|{c}", "text": gen(r["ImageID"], c)["text"][:240], "n_new": gen(r["ImageID"], c)["attempts"][-1]["n_new"]})
    out["examples"] = ex
    # J가 좌표를 내는 경우 두 문장이 모두 출력에 반복되는지(문장 앞부분 문자열 포함; 의미 판정 아님)
    contain = []
    for r in rows:
        t = gen(r["ImageID"], "J12")["text"]
        contain.append({"S1_prefix_in_text": r["S1"][:20] in t, "S2_prefix_in_text": r["S2"][:20] in t})
    out["J12_echoes_both_phrases_rate(string_containment_not_semantic)"] = float(np.mean([c["S1_prefix_in_text"] and c["S2_prefix_in_text"] for c in contain]))
    out["label"] = "post-hoc 기술 분석. 주판정·임계·표본 변경 없음. 문자열 포함은 사실성/binding 판정이 아니다."
    save(R.R106 / "eval/supplement_E32.json", out)
    print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
