"""iter_113: CURE-MedGrounder 위치 출력 불일치의 오류 검토 정보 (저장 출력의 CPU 분석, 모델·GPU 미사용).

고정 규칙(결과 확인 전에 protocol.json 에 코드·입력 hash 와 함께 잠근다):
- 모집단: iter_107 items.json 의 영상-소견 47개 전부. 연결·좌표 결함 항목만 제외 사유와 함께 제외.
- M = MedGrounder A_U_e5 의 기존 선택 운영점 0.8 출력(boxes, scores). C = CURE 엄격 parser(최종 EOS 필요).
- 위험 D = 1-IoU(∪M, ∪C) (둘 다 빈 출력이면 0, 하나만 비면 1). 위험 B = 1-min(M scores) (M 이 비면 confidence=0 -> B=1).
- CURE truncated/malformed/coord_invalid 는 두 순위에서 공통 제외, no_box 는 빈 집합.
- 순위: 위험 내림차순, 동률은 (sha256("iter113|item_key"), 복제 순번) 오름차순. K=ceil(N/4).
- 오류 E_G=1[IoU(∪M, ∪G)<0.3] (빈 M 은 오류). 대체 주석 H 로 같은 E_H. 두 주석이 일치하면 확정, 아니면 미확정.
"""
import hashlib
import json
import math
import random

import numpy as np

import nr107_geom as G
import nr107_spec as S

TAG = "iter113"
THR_KEY = "0.8"
ERR_IOU = 0.3
SEED = 113
BOOT_N = 10000


class LinkError(Exception):
    pass


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def sha256_text(t):
    return hashlib.sha256(t.encode()).hexdigest()


def k_of(n):
    return -(-n // 4)


def tie_key(item_key, rep=0):
    return (sha256_text(f"{TAG}|{item_key}"), rep)


def box_ok(b):
    """호출 경계 검사: 길이 4, 유한, 0<=x0<x1<=1, 0<=y0<y1<=1 (nr107_geom.valid_box 만으로 승인하지 않는다)."""
    if not isinstance(b, (list, tuple)) or len(b) != 4:
        return False
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in b):
        return False
    return 0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1


def check_boxes(name, boxes):
    for b in boxes:
        if not box_ok(b):
            raise LinkError(f"{name}: invalid box {b}")


# ---------------------------------------------------------------- 위험·오류
def risk_d(m, c):
    if not m and not c:
        return 0.0
    if not m or not c:
        return 1.0
    return 1.0 - G.union_iou(m, c)


def risk_b(scores):
    if not scores:
        return 1.0
    return 1.0 - min(scores)


def is_error(m, gts):
    """E=1[union IoU(M,gts)<0.3]; 빈 M 은 오류."""
    if not m:
        return 1
    return int(G.union_iou(m, gts) < ERR_IOU)


def annot_status(eg, eh):
    if eh is None:
        return "undetermined_no_alt"
    return "confirmed_error" if (eg == 1 and eh == 1) else "confirmed_ok" if (eg == 0 and eh == 0) else "undetermined_disagree"


# ---------------------------------------------------------------- 선택·포착
# entry: dict(patient, tk(tuple), D, B, e)
def select(entries, field):
    K = k_of(len(entries))
    order = sorted(range(len(entries)), key=lambda i: (-entries[i][field], entries[i]["tk"]))
    return set(order[:K]), K


def capture_diff(entries):
    sd, K = select(entries, "D")
    sb, _ = select(entries, "B")
    cd = sum(entries[i]["e"] for i in sd)
    cb = sum(entries[i]["e"] for i in sb)
    return cd - cb, cd, cb, K, sd, sb


def tie_options(entries, field):
    """각 항목의 선택 가능 여부: 1 강제 / 0 불가 / 2 경계 동률(가변). 필요한 동률 선택 수 r 반환."""
    K = k_of(len(entries))
    vals = sorted((e[field] for e in entries), reverse=True)
    rk = vals[K - 1]
    above = sum(1 for v in vals if v > rk)
    opts = [1 if e[field] > rk else 2 if e[field] == rk else 0 for e in entries]
    return opts, K - above


def fixed_options(entries, sel):
    return [1 if i in sel else 0 for i in range(len(entries))]


def extreme(entries, optD, rD, optB, rB, free, maximize):
    """sum_i e_i*(sD_i - sB_i) 의 정확한 최소/최대. optX: 1 강제, 0 불가, 2 가변(가변은 정확히 rX 개 선택).
    free[i]=True 이면 e_i 는 {0,1} 중 값을 최적으로 택한다(공유 선택 항목은 한 e 로 두 조건에 동일 적용)."""
    sign = 1 if maximize else -1
    NEG = float("-inf")
    dp = {(0, 0): 0}
    for i, en in enumerate(entries):
        nd = {}
        dopts = (1,) if optD[i] == 1 else (0,) if optD[i] == 0 else (0, 1)
        bopts = (1,) if optB[i] == 1 else (0,) if optB[i] == 0 else (0, 1)
        for (cd, cb), v in dp.items():
            for sd in dopts:
                for sb in bopts:
                    ncd = cd + (sd if optD[i] == 2 else 0)
                    ncb = cb + (sb if optB[i] == 2 else 0)
                    if ncd > rD or ncb > rB:
                        continue
                    if free[i]:
                        gain = max(sign * (e * (sd - sb)) for e in (0, 1))
                    else:
                        gain = sign * en["e"] * (sd - sb)
                    key = (ncd, ncb)
                    nv = v + gain
                    if nd.get(key, NEG) < nv:
                        nd[key] = nv
        dp = nd
    best = dp.get((rD, rB))
    if best is None:
        raise LinkError("infeasible selection constraints")
    return sign * best


def side_extreme(entries, field, maximize):
    """한 순위만의 포착 오류 수 최소/최대(경계 동률에서 가능한 선택)."""
    opt, r = tie_options(entries, field)
    # 한 순위: sum e_i * s_i. 반대 쪽을 모두 불가로 두고 값을 부호 맞춰 계산.
    n = len(entries)
    zero = [0] * n
    free = [False] * n
    if field == "D":
        return extreme(entries, opt, r, zero, 0, free, maximize)
    return -extreme(entries, zero, 0, opt, r, free, not maximize)


def bounds(entries, undetermined):
    """returns dict: 동률 한정 / 주석 한정 / 동률+주석 결합 차이 범위(D포착-B포착)."""
    sd, K = select(entries, "D")
    sb, _ = select(entries, "B")
    optD, rD = tie_options(entries, "D")
    optB, rB = tie_options(entries, "B")
    fD, fB = fixed_options(entries, sd), fixed_options(entries, sb)
    free_none = [False] * len(entries)
    free_u = [u for u in undetermined]
    out = {}
    out["tie_only"] = (extreme(entries, optD, rD, optB, rB, free_none, False), extreme(entries, optD, rD, optB, rB, free_none, True))
    out["annot_only"] = (extreme(entries, fD, 0, fB, 0, free_u, False), extreme(entries, fD, 0, fB, 0, free_u, True))
    out["tie_and_annot"] = (extreme(entries, optD, rD, optB, rB, free_u, False), extreme(entries, optD, rD, optB, rB, free_u, True))
    out["D_capture_tie_range"] = (side_extreme(entries, "D", False), side_extreme(entries, "D", True))
    out["B_capture_tie_range"] = (side_extreme(entries, "B", False), side_extreme(entries, "B", True))
    return out


# ---------------------------------------------------------------- bootstrap / LOO
def bootstrap(entries, n_boot=BOOT_N, seed=SEED):
    """환자 cluster bootstrap. 환자는 PatientID 정렬 순서; 복제 항목 tie-break 는 (원 hash, 추출 순번)."""
    pats = sorted({e["patient"] for e in entries})
    by_p = {p: [e for e in entries if e["patient"] == p] for p in pats}
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        draws = [rng.randrange(len(pats)) for _ in pats]
        rep = []
        for j, di in enumerate(draws):
            for e in by_p[pats[di]]:
                ne = dict(e)
                ne["tk"] = (e["tk"][0], j)
                rep.append(ne)
        diffs.append(capture_diff(rep)[0])
    return diffs


def summarize_boot(diffs):
    a = np.array(diffs, dtype=float)
    return {"n": len(diffs), "mean": float(a.mean()), "ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
            "p_gt0": float((a > 0).mean()), "p_eq0": float((a == 0).mean()), "p_lt0": float((a < 0).mean())}


def leave_one_patient_out(entries):
    out = {}
    for p in sorted({e["patient"] for e in entries}):
        sub = [e for e in entries if e["patient"] != p]
        d, cd, cb, K, _, _ = capture_diff(sub)
        out[p] = {"N": len(sub), "K": K, "diff": d, "capture_D": cd, "capture_B": cb}
    return out


# ---------------------------------------------------------------- 연결
def mg_defects(det):
    """MedGrounder 한 운영점 출력의 기술 결함(score 누락·길이 불일치·비유한·임계 미만). score 누락을 0 으로 대체하지 않는다."""
    bad = []
    if len(det["boxes_orig_xyxy"]) != len(det["scores"]):
        bad.append("mg_scores_length")
    elif any((not isinstance(s, (int, float)) or not math.isfinite(s)) for s in det["scores"]):
        bad.append("mg_score_nonfinite")
    elif any(s < float(THR_KEY) for s in det["scores"]):
        bad.append("mg_score_below_thr")
    return bad


def read_jsonl(p):
    rows = []
    with open(p) as f:
        for ln in f:
            if ln.strip():
                rows.append(json.loads(ln))
    return rows


def link(paths):
    """저장 자산을 연결해 항목별 ledger 를 만든다. 전역 결함은 LinkError, 항목 결함은 excluded 로 기록(결과 기반 제외 없음)."""
    items = json.load(open(paths["items"]))
    cohort = json.load(open(paths["cohort"]))
    rawman = json.load(open(paths["raw_manifest"]))
    glob = {}
    # 전역 hash 검사
    if sha256_file(paths["items"]) != cohort["items_sha256"]:
        raise LinkError("items.json sha mismatch vs cohort_summary")
    if sha256_file(paths["raw_manifest"]) != cohort["raw_manifest_sha256"]:
        raise LinkError("raw_manifest sha mismatch")
    # CURE completions
    comp_top = json.load(open(paths["cure_completion"]))
    cure_rows = []
    for sh in (0, 1):
        d = paths["cure_dir"] / f"shard{sh}"
        comp = json.load(open(d / "completion.json"))
        for fn, h in comp["files"].items():
            if sha256_file(d / fn) != h:
                raise LinkError(f"cure shard{sh} {fn} hash mismatch")
        if comp.get("final_not_eos", 0) != 0:
            raise LinkError("cure completion reports non-EOS")
        rel = f"cure/shard{sh}/completion.json"
        if sha256_file(d / "completion.json") != comp_top["files"][rel]:
            raise LinkError(f"cure top completion hash mismatch {rel}")
        cure_rows += read_jsonl(d / "outputs.jsonl")
    digest = comp_top["scientific_digest"]
    ids = [r["id"] for r in cure_rows]
    if len(ids) != len(set(ids)):
        raise LinkError("duplicate CURE ids")
    cure_by = {r["id"]: r for r in cure_rows}
    # MG raw
    mg_comp = json.load(open(paths["mg_completion"]))
    mg_rows = []
    for fn, h in mg_comp["raw_file_sha256"].items():
        if sha256_file(paths["mg_dir"] / fn) != h:
            raise LinkError(f"mg {fn} hash mismatch")
        mg_rows += read_jsonl(paths["mg_dir"] / fn)
    if len(mg_rows) != mg_comp["n_expected"] or not mg_comp["complete"]:
        raise LinkError("mg raw incomplete")
    if len({r["request_id"] for r in mg_rows}) != len(mg_rows):
        raise LinkError("duplicate MG request ids")
    mg_by = {r["request_id"]: r for r in mg_rows}
    sel = json.load(open(paths["selection"]))
    if sel["label"] != "A_U_e5" or sel["selected_threshold"] != 0.8 or sel["ckpt_sha256"] != cohort["mg_selection"]["ckpt_sha256"]:
        raise LinkError("MG selection mismatch")
    # 원 manifest (GT)
    man = {}
    for r in read_jsonl(paths["manifest_private"]):
        for tgt in r["sentences"]:
            k = (r["ImageID"], r["PatientID"], tgt)
            if k in man:
                raise LinkError(f"duplicate manifest key {k}")
            man[k] = (r, tgt)
    raw_sha = {r["ImageID"]: r["sha256"] for r in rawman}
    glob["n_items_in"] = len(items)
    if len({it["item_key"] for it in items}) != len(items):
        raise LinkError("duplicate item_key")
    if set(ids) - {S.request_id(it["ImageID"], it["finding_index"]) for it in items}:
        raise LinkError("extra CURE records beyond the 47 items")

    ledger, excluded = [], []
    for it in items:
        why = []
        rid = S.request_id(it["ImageID"], it["finding_index"])
        cr = cure_by.get(rid)
        mr = mg_by.get(it["mg_request_id"])
        mrow = man.get((it["ImageID"], it["PatientID"], it["target"]))
        if cr is None:
            why.append("cure_record_missing")
        if mr is None:
            why.append("mg_record_missing")
        if mrow is None:
            why.append("manifest_row_missing")
        if why:
            excluded.append({"item_key": it["item_key"], "reason": why})
            continue
        row, tgt = mrow
        bad = []
        if sha256_text(it["sentence"]) != it["sentence_sha256"]:
            bad.append("sentence_sha_vs_text")
        if row["sentences"][tgt] != it["sentence"] or row["finding_index"][tgt] != it["finding_index"]:
            bad.append("manifest_sentence_or_index")
        if cr["item_key"] != it["item_key"] or cr["prompt"] != S.pg_prompt(it["sentence"]) or cr["protocol_digest"] != digest:
            bad.append("cure_request_fields")
        if cr["image_sha256"] != raw_sha.get(it["ImageID"]) or cr["image_sha256"] != it["image_meta"]["raw_png_sha256"] or row["image_meta"]["raw_png_sha256"] != cr["image_sha256"]:
            bad.append("cure_image_sha")
        if mr["patient"] != it["PatientID"] or mr["target"] != it["target"] or mr["sentence_sha256"] != it["sentence_sha256"]:
            bad.append("mg_record_identity")
        if mr["u8_pixel_sha256"] != it["image_meta"]["u8_pixel_sha256"] or mr["ckpt_sha256"] != sel["ckpt_sha256"]:
            bad.append("mg_pixel_or_ckpt")
        if not mr["image"].endswith(it["ImageID"]):
            bad.append("mg_image_path")
        if row["gt_boxes_xyxy_norm"][tgt] != it["gt"] or row["extra_boxes_xyxy_norm"][tgt] != it["extra"]:
            bad.append("annotation_vs_manifest")
        det = mr["detections"][THR_KEY]
        if det["boxes_orig_xyxy"] != it["mg"][THR_KEY]["boxes"] or det["scores"] != it["mg"][THR_KEY]["scores"]:
            bad.append("mg_items_vs_raw")
        bad += mg_defects(det)
        att = cr["attempts"][-1]
        eos = bool(att["ended_eos"]) and att["finish_reason"] == "eos"
        pr = S.parse_pg(cr["text"], eos)
        try:
            check_boxes("mg", det["boxes_orig_xyxy"])
            check_boxes("cure", pr["boxes"])
            check_boxes("gt", it["gt"])
            if it["extra"]:
                check_boxes("extra", it["extra"])
            if not it["gt"]:
                bad.append("gt_empty")
        except LinkError as e:
            bad.append(str(e))
        if bad:
            excluded.append({"item_key": it["item_key"], "reason": bad})
            continue
        m, sc, c, g, h = det["boxes_orig_xyxy"], det["scores"], pr["boxes"], it["gt"], it["extra"]
        cure_ok = pr["status"] in ("valid_nonempty", "no_box")
        led = {"item_key": it["item_key"], "PatientID": it["PatientID"], "ImageID": it["ImageID"], "finding_index": it["finding_index"],
               "sentence_sha256": it["sentence_sha256"], "cure_request_id": rid, "mg_request_id": it["mg_request_id"],
               "cure_status": pr["status"], "cure_ended_eos": eos, "n_mg": len(m), "n_cure": len(c), "n_gt": len(g), "n_alt": len(h),
               "M": m, "M_scores": sc, "C": c, "GT": g, "ALT": h, "core_iter107": it["core"], "cure_text": cr["text"]}
        if not cure_ok:
            led["excluded_from_ranking"] = f"cure_{pr['status']}"
        ledger.append(led)
    glob.update(n_ledger=len(ledger), n_excluded_link=len(excluded))
    return ledger, excluded, glob


def build_entries(ledger):
    """순위 대상 항목과 오류/모호성 표. CURE 비정상 출력은 두 순위에서 공통 제외."""
    ent, excl = [], []
    for l in ledger:
        if "excluded_from_ranking" in l:
            excl.append({"item_key": l["item_key"], "reason": l["excluded_from_ranking"]})
            continue
        eg = is_error(l["M"], l["GT"])
        eh = is_error(l["M"], l["ALT"]) if l["ALT"] else None
        st = annot_status(eg, eh)
        ent.append({"item_key": l["item_key"], "patient": l["PatientID"], "tk": tie_key(l["item_key"]),
                    "D": risk_d(l["M"], l["C"]), "B": risk_b(l["M_scores"]), "e": eg, "eh": eh, "annot": st,
                    "iou_M_GT": G.union_iou(l["M"], l["GT"]) if l["M"] else 0.0,
                    "iou_M_C": G.union_iou(l["M"], l["C"]) if l["M"] and l["C"] else 0.0})
    return ent, excl


def analyze(ledger, n_boot=BOOT_N, seed=SEED):
    ent, excl = build_entries(ledger)
    N = len(ent)
    d, cd, cb, K, sd, sb = capture_diff(ent)
    und = [e["annot"].startswith("undetermined") for e in ent]
    # 확정 오류(두 주석 일치 오류)가 아닌 미확정만 자유 상태. 확정 항목은 e 고정(=E_G).
    bnd = bounds(ent, und)
    n_err = sum(e["e"] for e in ent)
    sd_l, sb_l = sorted(sd), sorted(sb)
    d_only = [i for i in sd_l if i not in sb]
    b_only = [i for i in sb_l if i not in sd]
    both = [i for i in sd_l if i in sb]
    miss = [i for i in range(N) if i not in sd and i not in sb]
    pat = lambda idx, errs_only=True: sorted({ent[i]["patient"] for i in idx if (ent[i]["e"] or not errs_only)})
    comp = {
        "D_only_errors": [ent[i]["item_key"] for i in d_only if ent[i]["e"]],
        "B_only_errors": [ent[i]["item_key"] for i in b_only if ent[i]["e"]],
        "both_errors": [ent[i]["item_key"] for i in both if ent[i]["e"]],
        "neither_errors": [ent[i]["item_key"] for i in miss if ent[i]["e"]],
        "D_only_error_patients": len(pat(d_only)), "B_only_error_patients": len(pat(b_only)),
        "both_error_patients": len(pat(both)), "neither_error_patients": len(pat(miss)),
    }
    t0 = __import__("time").time()
    boot = bootstrap(ent, n_boot, seed)
    boot_s = __import__("time").time() - t0
    loo = leave_one_patient_out(ent)
    loo_diffs = [v["diff"] for v in loo.values()]
    ann_counts = {k: sum(1 for e in ent if e["annot"] == k) for k in ("confirmed_error", "confirmed_ok", "undetermined_disagree", "undetermined_no_alt")}
    res = {
        "N": N, "K": K, "n_patients": len({e["patient"] for e in ent}), "n_errors_official": n_err, "excluded_from_ranking": excl,
        "capture_D": cd, "capture_B": cb, "diff": d, "diff_over_N": d / N, "precision_D": cd / K, "precision_B": cb / K,
        "selected_D": [ent[i]["item_key"] for i in sd_l], "selected_B": [ent[i]["item_key"] for i in sb_l],
        "complementarity": comp, "annotation_status_counts": ann_counts, "bounds": bnd,
        "bootstrap": summarize_boot(boot), "bootstrap_seconds": boot_s,
        "leave_one_patient_out": {"min": min(loo_diffs), "max": max(loo_diffs), "n_negative": sum(1 for x in loo_diffs if x < 0), "per_patient": loo},
        "min_gain_required": -(-5 * N // 100),
    }
    res["decision_inputs"] = decide(res)
    return res, ent, boot


def decide(res):
    need = res["min_gain_required"]
    cond = {
        "diff_ge_min_gain": res["diff"] >= need,
        "d_only_error_patients_ge_2": res["complementarity"]["D_only_error_patients"] >= 2,
        "conservative_tie_and_annot_min_gt0": res["bounds"]["tie_and_annot"][0] > 0,
        "loo_no_negative": res["leave_one_patient_out"]["n_negative"] == 0,
    }
    if all(cond.values()):
        verdict = "positive_exploratory"
    elif res["diff"] <= 0:
        verdict = "negative"
    else:
        verdict = "inconclusive"
    return {"conditions": cond, "verdict": verdict}
