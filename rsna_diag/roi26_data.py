"""iter_026 데이터 연결: roi23_data의 D24(val)/E60·E200(confirm) pool과 iter_012 원시 bbox 출력을 재사용한다.

- D24(val_*)의 B0 reader-proposal bbox: iter_012 train/lr2e-4_s17/epoch_05/val_gen (concise, split=validation).
- E60/E200(con_*)의 M0 rule(official_long/concise) 및 B0 rule/reader-proposal(concise) bbox: iter_012 confirm_base/confirm_sft_seed17
  (roi23_data.source_bbox_records/BBOX_DIR를 그대로 쓴다).
- B29/B43(con_*)의 rule bbox: confirm_sft_seed29/43.
"""
import glob
import json
import os

from . import geometry, roi23_data as D26D, roi26_spec as R26
from . import roi23_spec as R23

VAL_B0_DIR = "results/iter_012/train/lr2e-4_s17/epoch_05/val_gen"


class DataError(RuntimeError):
    pass


def load_val_b0_records(pinned=None):
    """D24(val_*)의 B0(seed17 epoch5) concise 원시 record, {id: record}. pinned: {path: sha256}로 변조 거부."""
    files = sorted(glob.glob(os.path.join(VAL_B0_DIR, "gen_worker*.jsonl")))
    if not files:
        raise DataError(f"no gen_worker*.jsonl in {VAL_B0_DIR}")
    if pinned:
        for f in files:
            got = D26D.sha(open(f, "rb").read())
            if f not in pinned or got != pinned[f]:
                raise DataError(f"val B0 source {f} not pinned or changed")
    out = {}
    for f in files:
        for ln in open(f):
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("prompt_name") != "concise" or r.get("split") != "validation":
                continue
            if r["id"] in out:
                raise DataError(f"duplicate val B0 record for {r['id']}")
            out[r["id"]] = r
    return out


def completion_ok(gen_dir, expected_n):
    cp = os.path.join(gen_dir, "completion.json")
    if not os.path.exists(cp):
        raise DataError(f"no completion.json in {gen_dir}")
    c = json.load(open(cp))
    if (c.get("n_expected") != expected_n or c.get("n_actual_unique") != expected_n or c.get("n_missing") != 0
            or c.get("n_duplicate") != 0 or c.get("n_extra", 0) != 0 or not c.get("returncodes")
            or any(x != 0 for x in c["returncodes"])):
        raise DataError(f"completion.json content invalid in {gen_dir}: {c}")
    return c


def proposal_for(ckpt, rec):
    """record -> (boxes_norm float list or None, status). None이면 unavailable(파싱 실패/truncated)."""
    return D26D.predicted_boxes(rec)


def partition_gt(boxes_norm):
    """GT box(yxyx_norm float) 목록 -> {target: [box,...]} 사분면 분할."""
    out = {t: [] for t in R26.TARGETS}
    for b in boxes_norm:
        cy, cx = R23.center_yx(b)
        out[R23.quadrant_of(cy, cx)].append(list(b))
    return out


def multi_quadrant_subset(gts, ids):
    """여러 사분면에 GT가 있는(진부분집합) 환자 id 목록, 정렬됨."""
    out = []
    for i in ids:
        boxes = [b["yxyx_norm"] for b in gts[i]["boxes"]]
        quads = {R23.quadrant_of(*R23.center_yx(b)) for b in boxes}
        if len(quads) >= 2:
            out.append(i)
    return sorted(out)


load_val_pool = D26D.load_val_pool
load_confirm_pool = D26D.load_confirm_pool
check_disjoint = D26D.check_disjoint
source_bbox_records = D26D.source_bbox_records
predicted_boxes = D26D.predicted_boxes
BBOX_DIR = D26D.BBOX_DIR
