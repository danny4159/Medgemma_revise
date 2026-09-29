"""iter_037: RSNA detector17/29 대 MedGemma grounding SFT의 고정 FP budget별 비용·성능 표, GT·후보 감사 행,
같은 대응쌍의 IoU0.5 통과율과 독립 재매칭의 구분, 통합 FP 범주, criterion_a/b (medgemma env, CPU만 사용).

iter_036의 det_error_audit.py는 결과 재현성을 위해 수정하지 않고 그 순수 함수(classify 규칙 참고, fp_decompose,
stratified_d24, ratio_ci_cluster, pair_row)만 재사용한다. 이 모듈은 실제 사용하는 저장 출력 loader(fail-closed)와
분석 출력 소유권(flock, 덮어쓰기 거부, 단위별 재개)을 새로 제공한다. det_match.bounded_match의 GT identity는 쓰지 않고
metrics.match(승인된 최대 cardinality matching)만 쓴다.

FP 범주 amendment: `competes_for_matched_gt`는 중복 후보와 GT 대응 경쟁을 합친 통합 범주이며 둘의 원인을 분리하지 않는다.
"""
import argparse
import fcntl
import glob
import hashlib
import json
import math
import multiprocessing as mp
import os
import sys
import time

import numpy as np
from PIL import Image

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det_compare as DC  # noqa: E402
from rsna_diag import det_error_audit as DA  # noqa: E402
from rsna_diag import det_eval as E  # noqa: E402
from rsna_diag import det_lib as D  # noqa: E402
from rsna_diag import geometry as G  # noqa: E402
from rsna_diag import metrics as M  # noqa: E402
from rsna_diag import parse as PA  # noqa: E402
from rsna_diag import sft_eval as SE  # noqa: E402

IT010 = DC.IT010
IT012 = DC.IT012
ADAPTERS = DC.ADAPTERS
LOCK_PATH = f"{BASE}/results/iter_035/select/LOCK.json"
SEL = {17: f"{BASE}/results/iter_035/select/seed17/v400_selection.json",
       29: f"{BASE}/results/iter_035/select/seed29/v400_selection.json"}
DET_DIRS = {"confirm800": {17: f"{BASE}/results/iter_035/confirm800/det17", 29: f"{BASE}/results/iter_035/confirm800/det29"},
            "V400": {17: f"{BASE}/results/iter_035/eval/seed17/V400_e18", 29: f"{BASE}/results/iter_035/eval/seed29/V400_e26"}}
MANIFEST_NAME = {"confirm800": "confirm800", "V400": "V400"}
SFT_DIRS = {"confirm800": {s: f"{IT012}/confirm_sft_seed{s}" for s in (17, 29, 43)},
            "V400": {17: f"{IT012}/train/lr2e-4_s17/epoch_05/val_gen"}}
IDS_PATH = {"confirm800": f"{IT010}/confirm_ids.json", "V400": f"{IT010}/validation_ids.json"}
CAP = 100
NEW_BOOT_SEED = DA.NEW_BOOT_SEED  # 20260929 (R·threshold 제외 비율, 97.5% 환자 cluster bootstrap)
OLD_BOOT_SEED = DC.BOOT_SEED      # 20260924 (기존 F1/FP/상보성 비교의 원본 설정)
B = 10000
IOUS = (0.3, 0.5)
CATS = DA.CATS
CATEGORIES = ("opacity", "normal", "not_normal_no_opacity")
PRIMARY_SFT = 17


# ------------------------------------------------------------------ 공용 유틸
def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def jd(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def write_json_new(path, obj):
    """원자적·덮어쓰기 거부: 임시 파일에 쓴 뒤 os.link로 생성(이미 있으면 FileExistsError)."""
    if os.path.exists(path):
        raise FileExistsError(path)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    try:
        os.link(tmp, path)
    finally:
        os.unlink(tmp)


class OutputOwner:
    """분석 출력 디렉터리의 단일 소유권: 비차단 flock. 두 번째 프로세스는 즉시 거부된다."""

    def __init__(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        self.fd = open(os.path.join(out_dir, ".owner.lock"), "a+")
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"{out_dir} is owned by another running process")
        self.fd.seek(0)
        self.fd.truncate()
        self.fd.write(json.dumps({"pid": os.getpid(), "t": time.time()}))
        self.fd.flush()

    def release(self):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        self.fd.close()


# ------------------------------------------------------------------ provenance / loader
def verify_lock(lock_path=LOCK_PATH, base=BASE):
    """LOCK의 5개 파일 hash·seed 집합을 현재 파일과 대조한다."""
    lock = json.load(open(lock_path))
    if lock.get("seed_set") != [17, 29] or not lock.get("locked_before_confirm800"):
        raise ValueError(f"unexpected LOCK seed_set/flag: {lock.get('seed_set')}")
    for name, ent in lock["files"].items():
        p = os.path.join(base, ent["path"])
        if sha_file(p) != ent["sha256"]:
            raise ValueError(f"LOCK file {name} changed: {p}")
    if len(lock["files"]) != 5:
        raise ValueError("LOCK must list 5 files")
    return lock


def verify_selection(selp, lock, base=BASE):
    """선택 파일이 LOCK 목록의 파일이며 내용이 잠긴 hash와 같은지, 필수 key가 있는지 확인한다."""
    rel = os.path.relpath(os.path.abspath(selp), base)
    ent = [e for e in lock["files"].values() if e["path"] == rel]
    if len(ent) != 1 or sha_file(selp) != ent[0]["sha256"]:
        raise ValueError(f"selection {selp} not locked / changed")
    sel = json.load(open(selp))
    for k in ("selected", "selected_checkpoint", "selected_checkpoint_sha256", "fp_budgets", "cap_ok"):
        if k not in sel:
            raise ValueError(f"selection missing {k}")
    if not sel["cap_ok"]:
        raise ValueError("selection reports cap problem")
    return sel


def validate_raw_record(pid, rec, img_hw=None):
    """boxes/scores/labels 길이, 유한성, 좌표 유효성, label, score 범위. 조용한 보정·절단 없음."""
    bx, sc, lb = rec["boxes_xyxy_px"], rec["scores"], rec["labels"]
    if not (len(bx) == len(sc) == len(lb)):
        raise ValueError(f"{pid}: boxes/scores/labels length mismatch {len(bx)}/{len(sc)}/{len(lb)}")
    if len(bx) > CAP:
        raise ValueError(f"{pid}: more than cap candidates")
    h, w = rec["img_hw"]
    if img_hw is not None and (h, w) != tuple(img_hw):
        raise ValueError(f"{pid}: img_hw {h, w} != image {img_hw}")
    for k, (b, s, l) in enumerate(zip(bx, sc, lb)):
        if len(b) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in b):
            raise ValueError(f"{pid}[{k}]: non-finite/invalid box {b}")
        if not (isinstance(s, (int, float)) and math.isfinite(s) and 0.0 <= s <= 1.0):
            raise ValueError(f"{pid}[{k}]: invalid score {s}")
        if l != 1:
            raise ValueError(f"{pid}[{k}]: unexpected label {l}")
        x0, y0, x1, y1 = b
        if not (x1 > x0 and y1 > y0 and x0 >= -1e-3 and y0 >= -1e-3 and x1 <= w + 1e-3 and y1 <= h + 1e-3):
            raise ValueError(f"{pid}[{k}]: box outside image or non-positive size {b} for {w}x{h}")


def check_shards(out_dir, comp, ids, raw, infer):
    """completion에 기록된 shard의 모든 record가 request 집합·provenance·raw_preds와 일치하는지 확인."""
    seen = {}
    for fn in sorted(comp["shard_sha256"]):
        for ln in open(os.path.join(out_dir, fn)):
            r = json.loads(ln)
            if r["id"] in seen:
                raise ValueError(f"duplicate id {r['id']} in shards of {out_dir}")
            for k in ("checkpoint_sha256", "source_digest", "manifest_digest", "batch_size"):
                if r.get(k) != comp[k]:
                    raise ValueError(f"shard record {r['id']} provenance {k} mismatch")
            if r.get("file_sha256") != infer[r["id"]]["file_sha256"]:
                raise ValueError(f"shard record {r['id']} file_sha256 != infer manifest")
            for k in ("boxes_xyxy_px", "scores", "labels", "img_hw"):
                if r[k] != raw[r["id"]][k]:
                    raise ValueError(f"shard record {r['id']} differs from raw_preds ({k})")
            seen[r["id"]] = True
    if set(seen) != set(ids) or len(seen) != len(ids):
        raise ValueError(f"shard request set != expected ({len(seen)} vs {len(ids)})")


def image_hw(infer_rec):
    with Image.open(f"{BASE}/{infer_rec['image']}") as im:
        return im.size[1], im.size[0]


def verify_images(ids, infer):
    """현재 영상 file hash(infer manifest)와 실제 크기를 확인하고 (h,w)를 반환한다."""
    hw = {}
    for i in ids:
        p = f"{BASE}/{infer[i]['image']}"
        if sha_file(p) != infer[i]["file_sha256"]:
            raise ValueError(f"image file hash mismatch: {i}")
        hw[i] = image_hw(infer[i])
    return hw


def load_detector(split, dseed, ids, infer, hw, lock):
    """LOCK·선택·completion·shard·영상·경계 검사를 통과한 raw 후보만 반환한다."""
    sel = verify_selection(SEL[dseed], lock)
    cdir = DET_DIRS[split][dseed]
    raw, comp, rid = E.load_verified(cdir, MANIFEST_NAME[split], sel["selected_checkpoint"])
    if comp["checkpoint_sha256"] != sel["selected_checkpoint_sha256"]:
        raise ValueError(f"{cdir}: checkpoint sha != locked selection")
    if rid != ids:
        raise ValueError(f"{cdir}: id order != expected ids")
    if comp["batch_size"] != 1:
        raise ValueError(f"{cdir}: batch_size {comp['batch_size']} != 1")
    if comp["source_digest"] != E.source_digest():
        raise ValueError(f"{cdir}: generation source digest differs from preserved sources")
    check_shards(cdir, comp, ids, raw, infer)
    for i in ids:
        validate_raw_record(i, raw[i], hw[i])
    return raw, sel, comp


def load_sft(split, seed, ids, infer, hw):
    """DC.load_stored(중복·집합·adapter·protocol·영상hash·completion) + prompt·EOS·pad affine·현재 영상 연결."""
    run_dir = SFT_DIRS[split][seed]
    recs, prov = DC.load_stored(run_dir, ids, ("concise",), ADAPTERS[seed], infer)
    prompt_hashes = {r["prompt_sha256"] for r in recs.values()}
    ref = json.loads(open(f"{IT012}/confirm_sft_seed17/gen_worker0.jsonl").readline())["prompt_sha256"]
    if prompt_hashes != {ref}:
        raise ValueError(f"{run_dir}: prompt hash set {prompt_hashes} != reference {ref}")
    for (i, _), r in recs.items():
        if r["image"] != infer[i]["image"]:
            raise ValueError(f"{run_dir}: image path differs from infer manifest for {i}")
        top, left, side = G.pad_offsets(*hw[i])
        if list(r["pad_affine_top_left_side"][:2]) != [top, left]:
            raise ValueError(f"{run_dir}: pad affine differs for {i}")
    preds = SE.parse_records(recs, ids, "concise", strict=True)
    n_eos = sum(1 for r in recs.values() if r["ended_eos"])
    prov["n_ended_eos"] = n_eos
    prov["status_counts"] = {s: sum(1 for p in preds.values() if p["status"] == s) for s in sorted({p["status"] for p in preds.values()})}
    return preds, prov


# ------------------------------------------------------------------ 후보·대응
def candidates(rec, hw):
    """label==1 후보 전체를 원래 index와 함께 padded 0-1000 yxyx로 변환한다 (길이 불일치 시 예외)."""
    validate_raw_record("cand", rec, hw)
    h, w = rec["img_hw"]
    top, left, side = G.pad_offsets(h, w)
    return [{"idx": k, "box": G.canvas_to_norm(b, top, left, side), "score": float(s)}
            for k, (b, s) in enumerate(zip(rec["boxes_xyxy_px"], rec["scores"]))]


def op_select(cands, thr):
    return [c for c in cands if c["score"] >= thr]


def pairs_orig(sel_cands, gt_boxes, thr):
    """{gi: (원래 candidate idx, IoU)} — metrics.match(최대 cardinality)의 결과를 원래 index로 환원."""
    if not sel_cands or not gt_boxes:
        return {}
    boxes = [c["box"] for c in sel_cands]
    return {gi: (sel_cands[pi]["idx"], M.iou(boxes[pi], gt_boxes[gi])) for gi, pi in M.match(boxes, gt_boxes, thr)}


def sft_pairs(pred, gt_boxes, thr):
    b = pred["boxes"] if pred["status"] in PA.VALID else []
    if not b or not gt_boxes:
        return {}
    return {gi: (pi, M.iou(b[pi], gt_boxes[gi])) for gi, pi in M.match(b, gt_boxes, thr)}


def best_iou(cands, gb):
    """(max IoU, 그 후보 idx) — 동률은 낮은 idx. 후보 없으면 (0.0, None)."""
    best, bi = 0.0, None
    for c in cands:
        v = M.iou(c["box"], gb)
        if bi is None or v > best:
            best, bi = v, c["idx"]
    return (best, bi) if bi is not None else (0.0, None)


def best_score_over(cands, gb, thr):
    """IoU>=thr 후보 중 score 최고 후보 (score, idx, iou). 부재는 None(0 score로 대체하지 않음)."""
    best = None
    for c in cands:
        v = M.iou(c["box"], gb)
        if v >= thr and (best is None or c["score"] > best[0]):
            best = (c["score"], c["idx"], v)
    return list(best) if best else None


def category(sel_cands, all_cands, gb, thr, adj=DA.ADJ_THR):
    """SFT-only GT의 4범주. 규칙은 det_error_audit.classify_gt와 동일."""
    if max((M.iou(c["box"], gb) for c in sel_cands), default=0.0) >= thr:
        return "matching_competition"
    mx = max((M.iou(c["box"], gb) for c in all_cands), default=0.0)
    if mx >= thr:
        return "threshold_excluded"
    if mx >= adj:
        return "adjacent_localization_error"
    return "no_stored_candidate_coverage"


def gt_audit_rows(pos, gt, cands_by, thr_op, sft_preds):
    """양성 GT별 감사 행. SFT 의존 필드는 seed별로 저장한다."""
    rows = []
    for pid in pos:
        gbs = [b["yxyx_norm"] for b in gt[pid]["boxes"]]
        allc = cands_by[pid]
        selc = op_select(allc, thr_op)
        dp = {t: pairs_orig(selc, gbs, t) for t in IOUS}
        sp = {s: {t: sft_pairs(sft_preds[s][pid], gbs, t) for t in IOUS} for s in sft_preds}
        for gi, gb in enumerate(gbs):
            mi_sel, ii_sel = best_iou(selc, gb)
            mi_all, ii_all = best_iou(allc, gb)
            row = {"patient": pid, "gi": gi, "n_cands_total": len(allc), "n_cands_selected": len(selc),
                   "max_iou_selected": mi_sel if ii_sel is not None else None, "max_iou_selected_idx": ii_sel,
                   "max_iou_all": mi_all if ii_all is not None else None, "max_iou_all_idx": ii_all,
                   "top_score_cand_iou_ge_0.3": best_score_over(allc, gb, 0.3),
                   "top_score_cand_iou_ge_0.5": best_score_over(allc, gb, 0.5)}
            for t in IOUS:
                row[f"det_pair_idx@{t}"] = dp[t][gi][0] if gi in dp[t] else None
                row[f"det_pair_iou@{t}"] = dp[t][gi][1] if gi in dp[t] else None
                for s in sp:
                    row[f"sft{s}_pair_idx@{t}"] = sp[s][t][gi][0] if gi in sp[s][t] else None
                    row[f"sft{s}_pair_iou@{t}"] = sp[s][t][gi][1] if gi in sp[s][t] else None
            for s in sp:
                for t in IOUS:
                    if gi in sp[s][t] and gi not in dp[t]:
                        row[f"sft{s}_only_category@{t}"] = category(selc, allc, gb, t)
                    else:
                        row[f"sft{s}_only_category@{t}"] = None
            rows.append(row)
    return rows


def category_stats(rows, pos, s, t, idx):
    """rows에서 SFT seed s의 IoU t 분해와 R(원 정의)·threshold 제외 비율(97.5% cluster CI)을 계산한다."""
    key = f"sft{s}_only_category@{t}"
    pat_pos = {p: k for k, p in enumerate(pos)}
    n_gt = np.zeros(len(pos)); rn = np.zeros(len(pos)); tn = np.zeros(len(pos)); so = np.zeros(len(pos))
    counts = {c: 0 for c in CATS}
    for r in rows:
        k = pat_pos[r["patient"]]
        n_gt[k] += 1
        c = r[key]
        if c:
            counts[c] += 1
            so[k] += 1
            rn[k] += c in ("adjacent_localization_error", "no_stored_candidate_coverage")
            tn[k] += c == "threshold_excluded"
    out = {"category_counts": counts, "sft_only_total": int(so.sum()), "total_gt": int(n_gt.sum()),
           "r_numerator": int(rn.sum()), "r_point": float(rn.sum() / n_gt.sum()), "r_n_affected_patients": int((rn > 0).sum()),
           "r_ci97.5": DA.ratio_ci_cluster(rn, n_gt, idx)["ci"],
           "threshold_excluded_point": float(tn.sum() / so.sum()) if so.sum() > 0 else None,
           "threshold_excluded_ci97.5": DA.ratio_ci_cluster(tn, so, idx)["ci"],
           "threshold_excluded_n_degenerate_denom0": DA.ratio_ci_cluster(tn, so, idx)["n_degenerate_denom0"]}
    if rn.sum() == 0:
        out["r_degenerate_bootstrap"] = True
        out["r_patient_event_wilson95"] = list(M.wilson(0, len(pos)))
    if tn.sum() == 0:
        out["threshold_excluded_degenerate_bootstrap"] = True
    return out, rn, n_gt


def pair_rows(model, pos, gt, pairs03, hit05_sets):
    """IoU0.3 원래 대응쌍을 고정하고 그 쌍 자체의 IoU>=0.5 여부와 독립 IoU0.5 재매칭의 GT 검출 여부를 기록한다."""
    out = []
    for pid in pos:
        gbs = [b["yxyx_norm"] for b in gt[pid]["boxes"]]
        for gi, (pi, iou_v) in pairs03[pid].items():
            out.append({"model": model, "patient": pid, "gi": gi, "pair_iou": iou_v,
                        "pair_iou_ge_0.5": iou_v >= 0.5, "gt_hit_independent_rematch_0.5": gi in hit05_sets[pid],
                        "pred_idx": pi, "gt_box": gbs[gi]})
    return out


def summarize_pairs(rows_):
    out = {}
    for model in sorted({r["model"] for r in rows_}):
        mr = [r for r in rows_ if r["model"] == model]
        pass05 = np.array([r["pair_iou_ge_0.5"] for r in mr])
        rem = np.array([r["gt_hit_independent_rematch_0.5"] for r in mr])
        out[model] = {"n_pairs_iou0.3": len(mr), "pair_pass_iou0.5_rate": float(pass05.mean()),
                      "gt_hit_by_independent_rematch_0.5_rate": float(rem.mean()),
                      "pair_fail_but_rematch_hit": int((~pass05 & rem).sum()),
                      "pair_pass_but_rematch_miss": int((pass05 & ~rem).sum())}
    return out


# ------------------------------------------------------------------ FP 비용·성능 표
def preds_from_cands(cands_by, thr):
    out = {}
    for pid, cs in cands_by.items():
        bx = [c["box"] for c in op_select(cs, thr)]
        out[pid] = {"status": "valid_nonempty" if bx else "valid_empty", "boxes": bx}
    return out


def fp_block(preds, gt, ids_by_cat, ids_all):
    """FP 총수/환자당/분모/invalid + 두 IoU의 통합 범주 (범주 합 == 전체 FP 검사)."""
    out = {"n_invalid": sum(1 for i in ids_all if preds[i]["status"] not in PA.VALID)}
    for name, ids_ in (("all800" if len(ids_all) == 800 else "all", ids_all), *ids_by_cat.items()):
        blk = {"n_patients": len(ids_), "n_invalid": sum(1 for i in ids_ if preds[i]["status"] not in PA.VALID)}
        for t in IOUS:
            d = DA.fp_decompose(ids_, gt, preds, thr=t)
            tot = d["n_fp_total"]
            if sum(v for k, v in d.items() if k != "n_fp_total") != tot:
                raise AssertionError("FP category sum != total")
            blk[f"iou{t}"] = {**d, "fp_per_patient": tot / len(ids_)}
        out[name] = blk
    return out


def model_table(preds, gt, ids, pos, ids_by_cat, edges, idx_pos):
    sm = SE.summarize(preds, gt, ids, edges=edges)
    tab = {"f1@0.3": sm["f1@0.3"], "f1@0.5": sm["f1@0.5"], "utility": sm["utility"], "status_all": sm["status_all"],
           "lesion@0.3": DC.lesion_stats(preds, gt, pos, 0.3), "lesion@0.5": DC.lesion_stats(preds, gt, pos, 0.5),
           "fp": fp_block(preds, gt, ids_by_cat, ids)}
    # 기존 구현(det_compare.fp_stats)과 FP 총수 대조
    fs, _ = DC.fp_stats(preds, gt, ids)
    if int(fs.sum()) != tab["fp"]["all800" if len(ids) == 800 else "all"]["iou0.3"]["n_fp_total"]:
        raise AssertionError("FP total != det_compare.fp_stats")
    return tab


def compare_block(det_preds, sft_preds, gt, pos, idx_pos):
    """양성 환자 paired 차이(det−SFT) F1@0.3/0.5, 97.5% CI(기존 설정) + 상보성."""
    _, pd_ = SE.per_patient(det_preds, gt, pos + [])  # pos만 전달돼도 pos 순서
    _, ps_ = SE.per_patient(sft_preds, gt, pos)
    out = {}
    for k in ("f1@0.3", "f1@0.5"):
        d = pd_[k] - ps_[k]
        out[f"diff_{k}"] = {"diff": float(d.mean()), "ci97.5": DC.boot_ci(d, idx_pos, 1.25, 98.75)}
    out["complementarity"] = {}
    for t in IOUS:
        c, _ = DC.complementarity(det_preds, sft_preds, gt, pos, t, idx_pos)
        out["complementarity"][f"iou{t}"] = c
    return out


# ------------------------------------------------------------------ criterion a/b
def criterion_ab(r_num, n_gt, cap_pat, idx, min_patients=20, thr=0.05):
    """criterion_a: 관측 R의 영향 환자>=20이고 97.5% CI 상한>=5%.
    criterion_b: cap(100)에 도달한 환자의 저장 후보 미대응 GT(R 분자)를 (관측=회복 불가 / 0=모두 회복 가능)의 양극단으로
    두었을 때 criterion_a 판정이 달라지는지. cap 환자가 없으면 비해당(False). escalate = a 또는 b.
    (이 구성에서 lo<=hi이므로 b는 a가 참인 경우에만 참일 수 있다 — cap 민감성을 명시하는 역할.)"""
    r_num, n_gt = np.asarray(r_num, float), np.asarray(n_gt, float)
    cap_pat = np.asarray(cap_pat, bool)

    def crit(num):
        ci = DA.ratio_ci_cluster(num, n_gt, idx)["ci"]
        aff = int((num > 0).sum())
        return {"r_point": float(num.sum() / n_gt.sum()), "n_affected_patients": aff, "ci97.5_upper": ci[1],
                "met": bool(aff >= min_patients and ci[1] is not None and ci[1] >= thr)}
    hi = crit(r_num)
    lo = crit(np.where(cap_pat, 0.0, r_num))
    cap_present = bool(cap_pat.any())
    b = bool(cap_present and hi["met"] != lo["met"])
    return {"criterion_a_met": hi["met"], "criterion_b_applicable": cap_present, "criterion_b_met": b,
            "extreme_not_recoverable": hi, "extreme_all_recoverable": lo, "n_cap_patients": int(cap_pat.sum()),
            "escalate_to_gpu_trace": bool(hi["met"] or b)}


# ------------------------------------------------------------------ 단위 실행
class Ctx:
    """분할별 검증된 입력. fork된 worker가 공유한다."""

    def __init__(self, split, ids=None, sft_seeds=None):
        self.split = split
        self.gt, self.infer = D.load_gt_infer()
        self.all_ids = json.load(open(IDS_PATH[split]))
        self.ids = self.all_ids if ids is None else ids
        self.full = ids is None
        self.lock = verify_lock()
        self.hw = verify_images(self.all_ids, self.infer)
        self.raw, self.sel, self.comp, self.cands = {}, {}, {}, {}
        for d in (17, 29):
            r, s, c = load_detector(split, d, self.all_ids, self.infer, self.hw, self.lock)
            self.raw[d], self.sel[d], self.comp[d] = r, s, c
        self.sft, self.sft_prov = {}, {}
        for s in (sft_seeds or SFT_DIRS[split]):
            self.sft[s], self.sft_prov[s] = load_sft(split, s, self.all_ids, self.infer, self.hw)
        self.pos = [i for i in self.ids if self.gt[i]["category"] == "opacity"]
        self.by_cat = {c: [i for i in self.ids if self.gt[i]["category"] == c] for c in CATEGORIES}
        self.edges = json.load(open(f"{BASE}/results/iter_033/data/area_edges.json"))["train_positive_area_tertile_edges"]
        for d in (17, 29):
            self.cands[d] = {i: candidates(self.raw[d][i], self.hw[i]) for i in self.ids}
        self.idx_pos = M.bootstrap_indices(len(self.pos), B=B, seed=OLD_BOOT_SEED)
        self.idx_new = M.bootstrap_indices(len(self.pos), B=B, seed=NEW_BOOT_SEED)

    def operating_points(self, d):
        ops = {"selected": self.sel[d]["selected"]["threshold"]}
        for b, r in self.sel[d]["fp_budgets"].items():
            if r is not None:
                ops[f"fp_budget_{b}"] = r["threshold"]
        return ops

    def unit_names(self):
        u = [f"sft{s}" for s in sorted(self.sft)]
        for d in (17, 29):
            u += [f"det{d}__{op}" for op in self.operating_points(d)]
        return u

    def inputs_digest(self):
        return jd({"lock": {k: v["sha256"] for k, v in self.lock["files"].items()},
                   "det": {d: {"raw": self.comp[d]["raw_preds_sha256"], "ckpt": self.comp[d]["checkpoint_sha256"]} for d in self.comp},
                   "sft": {s: p["files"] for s, p in self.sft_prov.items()}, "ids": jd(self.ids),
                   "sft_seeds": sorted(self.sft), "split": self.split})


def code_digest():
    files = [f"{BASE}/rsna_diag/{n}.py" for n in ("det37", "det_error_audit", "det_compare", "det_eval", "det_lib", "geometry", "metrics", "parse", "sft_eval")]
    return {os.path.relpath(p, BASE): sha_file(p) for p in files}


CONFIG = {"B": B, "boot_seed_old": OLD_BOOT_SEED, "boot_seed_new": NEW_BOOT_SEED, "ious": list(IOUS), "cap": CAP,
          "adj_thr": DA.ADJ_THR, "ci_percentiles_primary": [1.25, 98.75], "primary_sft": PRIMARY_SFT,
          "fp_definition": "unmatched predictions (n_pred - tp at the IoU); invalid SFT output counts 0 FP (lower bound)",
          "fp_category_amendment": "competes_for_matched_gt merges duplicate candidates and GT-matching competition",
          "matching": "metrics.match (max cardinality, then total IoU, then lexicographic)"}


def run_unit(ctx, name):
    t0 = time.time()
    if name.startswith("sft"):
        s = int(name[3:])
        pr = ctx.sft[s]
        out = {"kind": "sft", "seed": s, "table": model_table(pr, ctx.gt, ctx.ids, ctx.pos, ctx.by_cat, ctx.edges, ctx.idx_pos)}
    else:
        dpart, opname = name.split("__")
        d = int(dpart[3:])
        thr = ctx.operating_points(d)[opname]
        pr = preds_from_cands(ctx.cands[d], thr)
        # 기존 경로(preds_to_norm_yxyx)와 선택 결과 동일성
        old = D.preds_to_norm_yxyx({i: ctx.raw[d][i] for i in ctx.ids}, ctx.gt, thr)
        if any(old[i]["boxes"] != pr[i]["boxes"] for i in ctx.ids):
            raise AssertionError("candidate selection differs from D.preds_to_norm_yxyx")
        out = {"kind": "detector", "seed": d, "op": opname, "threshold": thr,
               "table": model_table(pr, ctx.gt, ctx.ids, ctx.pos, ctx.by_cat, ctx.edges, ctx.idx_pos)}
        out["vs_sft"] = {}
        cap_pat = np.array([len(ctx.cands[d][i]) >= CAP for i in ctx.pos])
        rows = gt_audit_rows(ctx.pos, ctx.gt, ctx.cands[d], thr, ctx.sft)
        out["gt_audit_rows"] = rows
        for s in sorted(ctx.sft):
            blk = compare_block(pr, ctx.sft[s], ctx.gt, ctx.pos, ctx.idx_pos)
            blk["decomposition"] = {}
            for t in IOUS:
                cs, rn, ngt = category_stats(rows, ctx.pos, s, t, ctx.idx_new)
                if cs["sft_only_total"] != blk["complementarity"][f"iou{t}"]["sft_only"]:
                    raise AssertionError("category sum != complementarity sft_only")
                blk["decomposition"][f"iou{t}"] = cs
                if t == 0.3:
                    blk["criterion"] = criterion_ab(rn, ngt, cap_pat, ctx.idx_new)
            out["vs_sft"][f"sft{s}"] = blk
        # 위치: IoU0.3 대응쌍 고정, 그 쌍의 IoU>=0.5 통과 vs 독립 재매칭
        pairs03, hit05 = {}, {}
        for pid in ctx.pos:
            gbs = [b["yxyx_norm"] for b in ctx.gt[pid]["boxes"]]
            sc = op_select(ctx.cands[d][pid], thr)
            pairs03[pid] = pairs_orig(sc, gbs, 0.3)
            hit05[pid] = set(pairs_orig(sc, gbs, 0.5))
        prow = pair_rows("detector", ctx.pos, ctx.gt, pairs03, hit05)
        for s in sorted(ctx.sft):
            p3, h5 = {}, {}
            for pid in ctx.pos:
                gbs = [b["yxyx_norm"] for b in ctx.gt[pid]["boxes"]]
                p3[pid] = sft_pairs(ctx.sft[s][pid], gbs, 0.3)
                h5[pid] = set(sft_pairs(ctx.sft[s][pid], gbs, 0.5))
            prow += pair_rows(f"sft{s}", ctx.pos, ctx.gt, p3, h5)
        out["pair_summary"] = summarize_pairs(prow)
        out["pair_rows"] = prow
        out["n_at_cap"] = int(sum(1 for i in ctx.ids if len(ctx.cands[d][i]) >= CAP))
        out["max_candidates"] = max(len(ctx.cands[d][i]) for i in ctx.ids)
    out["elapsed_s"] = time.time() - t0
    return out


def unit_path(out_dir, name):
    return os.path.join(out_dir, "units", f"{name}.json")


def header(ctx):
    return {"config": CONFIG, "config_digest": jd(CONFIG), "inputs_digest": ctx.inputs_digest(), "code": code_digest(), "split": ctx.split}


def _worker(args):
    ctx, out_dir, name, hdr = args
    p = unit_path(out_dir, name)
    if os.path.exists(p):
        cur = json.load(open(p))
        if cur["header"]["inputs_digest"] != hdr["inputs_digest"] or cur["header"]["config_digest"] != hdr["config_digest"]:
            raise ValueError(f"existing unit {name} has different config/inputs")
        return name, "reused"
    res = run_unit(ctx, name)
    write_json_new(p, {"header": hdr, "unit": name, "result": res})
    return name, "computed"


def run_all(ctx, out_dir, workers=1, stop_after=None):
    owner = OutputOwner(out_dir)
    try:
        os.makedirs(os.path.join(out_dir, "units"), exist_ok=True)
        hdr = header(ctx)
        mpath = os.path.join(out_dir, "manifest.json")
        if os.path.exists(mpath):
            cur = json.load(open(mpath))
            for k in ("config_digest", "inputs_digest", "code", "split"):
                if cur[k] != hdr[k]:
                    raise ValueError(f"manifest {k} differs from current run; use a new attempt dir")
        else:
            write_json_new(mpath, hdr)
        todo = ctx.unit_names()
        if stop_after is not None:  # 재개 검사용: 지정 개수만 계산하고 비정상 종료
            done = 0
            for n in todo:
                if not os.path.exists(unit_path(out_dir, n)):
                    if done >= stop_after:
                        os._exit(7)
                    _worker((ctx, out_dir, n, hdr))
                    done += 1
            return todo
        jobs = [(ctx, out_dir, n, hdr) for n in todo]
        if workers > 1:
            with mp.get_context("fork").Pool(workers) as pool:
                for n, st in pool.imap_unordered(_worker, jobs):
                    print(n, st, flush=True)
        else:
            for j in jobs:
                print(*_worker(j), flush=True)
        return todo
    finally:
        owner.release()


def load_units(out_dir, ctx):
    hdr = header(ctx)
    units = {}
    for n in ctx.unit_names():
        p = unit_path(out_dir, n)
        if not os.path.exists(p):
            raise FileNotFoundError(f"missing unit {n}")
        u = json.load(open(p))
        if u["header"]["inputs_digest"] != hdr["inputs_digest"] or u["header"]["config_digest"] != hdr["config_digest"]:
            raise ValueError(f"unit {n} stale")
        units[n] = u["result"]
    return units


def finalize(ctx, out_dir):
    """모든 unit을 검증해 report.json(GT 감사 행·pair 행은 별도 jsonl)을 만든다."""
    units = load_units(out_dir, ctx)
    audit_dir = os.path.join(out_dir, "audit")
    os.makedirs(audit_dir, exist_ok=True)
    report = {"header": header(ctx), "n_ids": len(ctx.ids), "n_positive": len(ctx.pos),
              "n_gt": int(sum(len(ctx.gt[i]["boxes"]) for i in ctx.pos)),
              "sft_provenance": ctx.sft_prov, "tables": {}, "detector": {}}
    for n, u in units.items():
        if u["kind"] == "sft":
            report["tables"][n] = u["table"]
            continue
        slim = {k: v for k, v in u.items() if k not in ("gt_audit_rows", "pair_rows")}
        report["detector"][n] = slim
        for key, fname in (("gt_audit_rows", "gt_audit"), ("pair_rows", "pairs")):
            p = os.path.join(audit_dir, f"{n}__{fname}.jsonl")
            if not os.path.exists(p):
                with open(p + f".tmp{os.getpid()}", "w") as f:
                    for r in u[key]:
                        f.write(json.dumps(r) + "\n")
                os.link(p + f".tmp{os.getpid()}", p)
                os.unlink(p + f".tmp{os.getpid()}")
    # R 불변성: 같은 후보 pool·SFT에서 R 분자는 detector operating threshold에 의존하지 않는다.
    inv = {}
    for d in (17, 29):
        for s in sorted(ctx.sft):
            for t in IOUS:
                vals = {n: report["detector"][n]["vs_sft"][f"sft{s}"]["decomposition"][f"iou{t}"]["r_numerator"]
                        for n in report["detector"] if n.startswith(f"det{d}__")}
                inv[f"det{d}_vs_sft{s}_iou{t}"] = {"r_numerator_by_op": vals, "invariant": len(set(vals.values())) == 1}
    report["r_invariance"] = inv
    report["cap_check"] = {f"det{d}": {"n_at_cap100": max(report["detector"][n]["n_at_cap"] for n in report["detector"] if n.startswith(f"det{d}__")),
                                       "max_candidates": max(report["detector"][n]["max_candidates"] for n in report["detector"] if n.startswith(f"det{d}__"))}
                           for d in (17, 29)}
    write_json_new(os.path.join(out_dir, "report.json"), report)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["confirm800", "V400"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--d24", action="store_true", help="V400/confirm800의 D24 hash 순서 층화 subset만 분석(동작 확인)")
    ap.add_argument("--stop_after", type=int, default=None, help="재개 검사 전용")
    a = ap.parse_args()
    ctx = Ctx(a.split)
    if a.d24:
        d24 = DA.stratified_d24(ctx.all_ids, ctx.gt)
        ctx.ids = d24
        ctx.pos = [i for i in d24 if ctx.gt[i]["category"] == "opacity"]
        ctx.by_cat = {c: [i for i in d24 if ctx.gt[i]["category"] == c] for c in CATEGORIES}
        for d in (17, 29):
            ctx.cands[d] = {i: ctx.cands[d][i] for i in d24}
        ctx.idx_pos = M.bootstrap_indices(len(ctx.pos), B=B, seed=OLD_BOOT_SEED)
        ctx.idx_new = M.bootstrap_indices(len(ctx.pos), B=B, seed=NEW_BOOT_SEED)
    run_all(ctx, a.out, a.workers, a.stop_after)
    if a.stop_after is None:
        rep = finalize(ctx, a.out)
        print(json.dumps({"finalized": True, "n_units": len(ctx.unit_names())}))


if __name__ == "__main__":
    main()
