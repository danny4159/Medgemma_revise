"""iter_111 fixture: 합성 사례 + 변조 거부 + 재개/덮어쓰기 거부. 실제 결과 비교는 하지 않는다. results/iter_111/tests/fixtures.json 새 파일."""
import itertools
import json
import os
import shutil
import sys
import tempfile

import numpy as np

import ev111_core as C
import ev111_link as L
from rsna_diag import metrics as M

OUT = sys.argv[1] if len(sys.argv) > 1 else "results/iter_111/tests/fixtures.json"
res = []


def chk(name, ok, **kw):
    res.append(dict(name=name, ok=bool(ok), **kw))


def P(i, gt, det=(), scores=(), ans="no", cat=None, sft=(), sft_status="empty"):
    return dict(id=i, cat=cat or ("opacity" if gt else "normal"), gt=[list(b) for b in gt], det=[list(b) for b in det],
                det_scores=list(scores), sft=[list(b) for b in sft], sft_status=sft_status, ans=ans, ans_source="x")


A = [100, 100, 300, 300]
B = [500, 500, 700, 700]
FAR = [800, 800, 950, 950]


def brute_match(pred, gt, thr):
    best = 0
    for r in range(min(len(pred), len(gt)) + 1):
        for gi in itertools.combinations(range(len(gt)), r):
            for pi in itertools.permutations(range(len(pred)), r):
                if all(M.iou(pred[p], gt[g]) >= thr for g, p in zip(gi, pi)):
                    best = max(best, r)
    return best


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        sys.exit("exists")
    # --- box_outcome / joint
    chk("empty_empty_neg", C.box_outcome([], [], .3)["exact"])
    chk("neg_with_box_fails", not C.box_outcome([A], [], .3)["exact"])
    chk("pos_empty_fails", not C.box_outcome([], [A], .3)["exact"])
    chk("pos_exact", C.box_outcome([A], [A], .3)["exact"])
    o = C.box_outcome([A, FAR], [A], .3)
    chk("pos_extra_fp_fails", (not o["exact"]) and o["fp"] == 1 and o["fn"] == 0)
    o = C.box_outcome([A], [A, B], .3)
    chk("pos_missing_gt_fails", (not o["exact"]) and o["fn"] == 1)
    chk("multi_box_exact", C.box_outcome([B, A], [A, B], .3)["exact"])
    chk("duplicate_pred_one_gt", C.box_outcome([A, A], [A], .3)["tp"] == 1 and not C.box_outcome([A, A], [A], .3)["exact"])
    edge = [100, 100, 300, 300]
    shifted = [100, 100, 300, 300 + 0]  # IoU=1
    chk("iou_boundary_inclusive", C.box_outcome([[100, 100, 200, 200]], [[100, 100, 200, 300]], .5)["exact"])  # IoU=0.5 정확히
    # brute-force matching 대조
    rng = np.random.default_rng(3)
    bad = 0
    for _ in range(300):
        def rb():
            y, x = rng.integers(0, 700, 2)
            h, w = rng.integers(60, 250, 2)
            return [int(y), int(x), int(y + h), int(x + w)]
        pr = [rb() for _ in range(rng.integers(0, 4))]
        gt = [rb() for _ in range(rng.integers(0, 3))]
        for thr in (.3, .5):
            if len(M.match(pr, gt, thr)) != brute_match(pr, gt, thr):
                bad += 1
    chk("match_vs_bruteforce_300x2", bad == 0, bad=bad)
    # joint modes
    pos = P("p", [A], [A], [.9], ans="yes")
    neg = P("n", [], [A], [.9], ans="no", cat="normal")
    chk("loc_pos_ok", C.joint(pos, "det", "loc", .3) is True)
    chk("loc_neg_with_box_false", C.joint(neg, "det", "loc", .3) is False)
    chk("indep_neg_No_but_box_false", C.joint(neg, "det", "indep", .3) is False)
    chk("gate_neg_No_empties_box", C.joint(neg, "det", "gate", .3) is True)
    chk("gate_pos_No_fails", C.joint(P("p2", [A], [A], [.9], ans="no"), "det", "gate", .3) is False)
    chk("unresolved_none", C.joint(P("u", [A], [A], [.9], ans=None), "det", "gate", .3) is None)
    sft_bad = P("s", [A], ans="yes", sft_status="invalid")
    chk("sft_invalid_is_not_empty_success", C.joint(sft_bad, "sft", "loc", .3) is False and C.joint(P("s2", [], ans="no", sft_status="invalid", cat="normal"), "sft", "loc", .3) is False)
    chk("gate_No_ignores_invalid_boxes", C.joint(P("s3", [], ans="no", sft_status="invalid", cat="normal"), "sft", "gate", .3) is True)
    # --- expected_found 동률
    chk("tie_expected", abs(C.expected_found([.1, .5, .5, .5], [0, 1, 0, 0], 2) - (0 + 1 / 3)) < 1e-12)
    chk("k0", C.expected_found([.1, .2], [1, 1], 0) == 0.0)
    chk("k_all", C.expected_found([.1, .2], [1, 0], 2) == 1.0)
    chk("empty_set", C.expected_found([], [], 3) == 0.0)
    # --- endpoint: 모든 reader가 No면 k=전체 -> 퇴화, ep=0
    Ps = [P(f"a{i}", [A] if i % 2 else [], [A], [.7 + .01 * i], ans="no", cat="opacity" if i % 2 else "normal") for i in range(8)]
    e = C.endpoint_arrays(Ps)
    chk("k_all_degenerate", e["degenerate"] and abs(e["ep"]) < 1e-12 and e["k"] == e["n_resolved"], e=e["ep"])
    Ps0 = [dict(p, ans="yes") for p in Ps]
    e0 = C.endpoint_arrays(Ps0)
    chk("k0_degenerate", e0["degenerate"] and e0["k"] == 0 and e0["found_vlm"] == 0)
    # reader가 정확히 오류를 가리키는 oracle-like 합성: S 6명, 오류 3명(neg 3), reader No=오류
    Pm = []
    for i in range(6):
        neg_ = i < 3
        Pm.append(P(f"m{i}", [] if neg_ else [A], [A], [.9 - 0.01 * i], ans="no" if neg_ else "yes", cat="normal" if neg_ else "opacity"))
    em = C.endpoint_arrays(Pm)
    # conf은 점수 낮은 3명(i=3..5, 모두 정답)을 고르므로 0 포착, vlm=3
    chk("endpoint_known", em["found_vlm"] == 3 and em["found_conf"] == 0 and abs(em["ep"] - 0.5) < 1e-12 and em["vlm_neg_claim"] == 3 and em["vlm_pos_location"] == 0, em=em["ep"])
    # S 밖 환자(detector 빈 출력)는 분모에 들어가지 않음
    em2 = C.endpoint_arrays(Pm + [P("z", [A], [], [], ans="no")])
    chk("S_excludes_det_empty", em2["n_S"] == 6)
    # 미해결: 양쪽 상쇄(비교에서 제외)하되 n_S 분모엔 포함
    Pu = Pm + [P("u1", [], [A], [.75], ans=None, cat="normal")]
    eu = C.endpoint_arrays(Pu)
    chk("unresolved_in_denominator_not_in_selection", eu["n_S"] == 7 and eu["n_unres"] == 1 and eu["n_resolved"] == 6 and eu["k"] == 3)
    # 같은 응답을 공유하는 서로 다른 시스템: ans는 환자당 하나
    chk("shared_answer_single_source", all("ans" in p and not isinstance(p["ans"], (list, dict)) for p in Pm))
    # 퇴화 bootstrap이 실패 없이 동작
    b = C.boot(Pm, B=200)
    chk("boot_runs", len(b["ep"]) == 200)
    # 부트스트랩 index 재표집 == 재표집 환자 리스트로 직접 계산
    rng2 = np.random.default_rng(5)
    ix = rng2.integers(0, len(Pu), size=len(Pu))
    ea = C.endpoint(C.vec(Pu), ix)
    eb = C.endpoint(C.vec([Pu[j] for j in ix]))
    chk("boot_index_equals_direct", all(abs(ea[k] - eb[k]) < 1e-12 for k in ("ep", "ep_aux", "found_vlm", "found_conf", "found_confmin")) and ea["k"] == eb["k"])
    # assign_unresolved
    q = C.assign_unresolved(Pu, "yes")
    chk("assign_yes", all(p["ans"] is not None for p in q) and q[-1]["ans"] == "yes")
    q2 = C.assign_unresolved(Pu, "adverse")
    q3 = C.assign_unresolved(Pu, "favorable")
    # u1은 오류(Y)인 neg_claim: adverse는 오류를 놓치게('yes'), favorable은 잡게('no') 배정
    chk("assign_adverse_favorable", q2[-1]["ans"] == "yes" and q3[-1]["ans"] == "no")
    # --- 답 추출 변경 없음
    import ev109_extract as X
    chk("extract_rules_digest", X.rules_digest() == "260bbb1d8b270f577549c62ac4b02affbacb9ee7461c21536f5b5a71e7321bd5")
    import inspect
    chk("resolve_signature_no_gt", list(inspect.signature(X.resolve).parameters) == ["target", "raw", "ended_eos"])
    # --- 변조 거부: link를 임시 사본으로 돌려 problems 발생 확인
    tmp = tempfile.mkdtemp()
    orig = {k: getattr(L, k) for k in ("OUT", "LABELS", "DET_DIR", "SFT_REUSE", "O_STAGES")}

    def run_link(**over):
        for k, v in orig.items():
            setattr(L, k, v)
        L.OUT = os.path.join(tmp, "o_" + str(len(os.listdir(tmp))))
        for k, v in over.items():
            setattr(L, k, v)
        try:
            L.main()
        except SystemExit as ex:
            return ex.code, json.load(open(os.path.join(L.OUT, "problems.json"))) if os.path.exists(os.path.join(L.OUT, "problems.json")) else None
        return 0, None

    lab = json.load(open(orig["LABELS"]))
    k0 = sorted(lab)[0]
    lab_bad = {**lab, k0: {**lab[k0], "category": "normal" if lab[k0]["category"] == "opacity" else "opacity"}}
    p1 = os.path.join(tmp, "labels_bad.json")
    json.dump(lab_bad, open(p1, "w"))
    code, pr = run_link(LABELS=p1)
    chk("tamper_label_category_rejected", code == 1 and pr and any("category" in x or "연결 누락" in x for x in pr), n=len(pr or []))
    d2 = os.path.join(tmp, "det")
    shutil.copytree(orig["DET_DIR"], d2)
    raw = json.load(open(f"{d2}/raw_preds.json"))
    kk = sorted(raw)[0]
    raw[kk]["scores"] = [0.0] + list(raw[kk]["scores"][1:]) if raw[kk]["scores"] else [0.5]
    json.dump(raw, open(f"{d2}/raw_preds.json", "w"))
    code, pr = run_link(DET_DIR=d2)
    chk("tamper_det_raw_rejected", code == 1 and pr and any("raw_preds hash" in x for x in pr))
    rows = open(orig["SFT_REUSE"]).read().splitlines()
    r0 = json.loads(rows[0])
    r0["suffix_text_raw"] = "[]<end_of_turn>" if r0["suffix_text_raw"] != "[]<end_of_turn>" else '[{"box_2d": [1, 1, 5, 5], "label": "x"}]<end_of_turn>'
    p3 = os.path.join(tmp, "sft_bad.jsonl")
    open(p3, "w").write("\n".join([json.dumps(r0)] + rows[1:]) + "\n")
    code, pr = run_link(SFT_REUSE=p3)
    chk("tamper_sft_text_rejected", code == 1 and pr and any("SFT 원본-reuse" in x for x in pr))
    # 응답 hash: O 출력 worker 파일 한 줄 제거 -> record 수 불일치/누락
    d4 = os.path.join(tmp, "gen")
    shutil.copytree(orig["O_STAGES"]["e600x_plain"], d4)
    w = f"{d4}/gen_worker0.jsonl"
    ln = open(w).read().splitlines()
    open(w, "w").write("\n".join(ln[1:]) + "\n")
    code, pr = run_link(O_STAGES={**orig["O_STAGES"], "e600x_plain": d4})
    chk("tamper_O_missing_record_rejected", code == 1 and pr and any("record" in x for x in pr))
    # 기존 ledger 덮어쓰기 거부
    for k, v in orig.items():
        setattr(L, k, v)
    try:
        L.main()
        ow = False
    except SystemExit as ex:
        ow = isinstance(ex.code, str) and "exists" in ex.code
    chk("overwrite_rejected", ow)
    shutil.rmtree(tmp)
    ok = all(r["ok"] for r in res)
    json.dump(dict(n=len(res), n_pass=sum(r["ok"] for r in res), results=res), open(OUT, "w"), indent=1)
    print(sum(r["ok"] for r in res), "/", len(res), [r["name"] for r in res if not r["ok"]])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
