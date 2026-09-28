"""iter_023 사분면 QA 요청 행렬. qa_requests.make_row/compute_id/verify_row/load_rows(request_id 계산·재검증)를
그대로 재사용하고, 질문·evidence는 roi23_spec을 쓴다. OUT(run-root)은 ROI23_RUN_ROOT 환경변수로 정한다.
"""
import json
import os

from . import qa_requests as Q, roi23_data as D, roi23_spec as R

OUT = os.environ.get("ROI23_RUN_ROOT", "results/iter_023")
CKPT_SPEC = {"M0": None, "B0": "results/iter_012/train/lr2e-4_s17/epoch_05",
             "B29": "results/iter_012/train/lr2e-4_s29/epoch_05", "B43": "results/iter_012/train/lr2e-4_s43/epoch_05"}
RequestError = Q.RequestError
load_rows = Q.load_rows
compute_id = Q.compute_id
verify_row = Q.verify_row


def checkpoints(out=None):
    import torch
    from . import eval_gate
    out = out or f"{OUT}/manifests/checkpoints.json"
    tab = {}
    for k, d in CKPT_SPEC.items():
        if d is None:
            tab[k] = {"dir": None, "digest": None}
            continue
        b = torch.load(os.path.join(d, "adapter.pt"), map_location="cpu", weights_only=True)
        tab[k] = {"dir": d, "digest": eval_gate.adapter_digest(d), "epoch": b.get("epoch"), "step": b.get("step"),
                  "train_digest": b.get("train_digest"), "lora": b["config"]}
    # roi23_run(qa_run 파생)은 "ckpt" 인자로 adapter dir을 찾는다. row_key(L/U/O_M0/O_B0/D_M0/D_B0)가
    # 실제로는 M0 또는 B0 adapter를 쓰므로, 같은 adapter를 가리키는 별칭을 같은 표에 추가한다 (새 adapter가 아니다).
    alias = {"D_M0": "M0", "D_B0": "B0", "L": "M0", "U": "M0", "O_M0": "M0", "O_B0": "B0"}
    for k, base in alias.items():
        tab[k] = tab[base]
    if os.path.exists(out):
        old = json.load(open(out))
        if old != tab:
            raise RequestError("checkpoint table exists and differs")
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(tab, open(out, "w"), indent=1)
    return tab


def _direct_rows(items, ckpt, ad, fmt, cfg, stage):
    rows = []
    for i in sorted(items):
        it = items[i]
        for t in R.TARGETS:
            rows.append(Q.make_row(it, ckpt, ad, t, fmt, "direct", R.qa_prompt(t, fmt), None, cfg, stage))
    return rows


def _reader_rows(items, ckpt, ad, fmt, cfg, stage, condition, evidence_of):
    """evidence_of(id) -> (evidence_text, extra_meta)."""
    rows = []
    for i in sorted(items):
        it = items[i]
        txt, meta = evidence_of(i)
        for t in R.TARGETS:
            rows.append(Q.make_row(it, ckpt, ad, t, fmt, condition, R.qa_prompt(t, fmt, txt), R.sha(txt), cfg, stage,
                                    extra=meta))
    return rows


def build_stage(items, gts, tab, fmt, cfg, stage, bbox_pred_b0):
    """returns {row_key: [rows]} for the six generation conditions: D_M0, D_B0, L, U, O_M0, O_B0.
    bbox_pred_b0: {id: (boxes_or_None, status)} from B0 concise raw output (parsed)."""
    out = {}
    out["D_M0"] = _direct_rows(items, "M0", tab["M0"]["digest"], fmt, cfg, stage)
    out["D_B0"] = _direct_rows(items, "B0", tab["B0"]["digest"], fmt, cfg, stage)

    def pred_evidence(i):
        boxes, status = bbox_pred_b0[i]
        if boxes is None:
            return R.evidence_text("unavailable"), {"source": "B0_concise", "source_status": status}
        return R.evidence_text("predicted", boxes), {"source": "B0_concise", "source_status": status, "boxes": boxes}

    def unavail_evidence(i):
        return R.evidence_text("unavailable"), {"source": None}

    def oracle_evidence(i):
        boxes = [b["yxyx_norm"] for b in gts[i]["boxes"]]
        return R.evidence_text("oracle", boxes), {"source": "gt", "boxes": boxes}

    out["L"] = _reader_rows(items, "M0", tab["M0"]["digest"], fmt, cfg, stage, "ev_predicted", pred_evidence)
    out["U"] = _reader_rows(items, "M0", tab["M0"]["digest"], fmt, cfg, stage, "ev_unavailable", unavail_evidence)
    out["O_M0"] = _reader_rows(items, "M0", tab["M0"]["digest"], fmt, cfg, stage, "ev_oracle", oracle_evidence)
    out["O_B0"] = _reader_rows(items, "B0", tab["B0"]["digest"], fmt, cfg, stage, "ev_oracle", oracle_evidence)
    return out


def build_gray(gray_item, tab, fmt, cfg, stage="gray"):
    items = {gray_item["id"]: gray_item}
    return {"D_M0": _direct_rows(items, "M0", tab["M0"]["digest"], fmt, cfg, stage),
            "D_B0": _direct_rows(items, "B0", tab["B0"]["digest"], fmt, cfg, stage)}


def build_bbox_rows(items, ckpt, tab, cfg, stage):
    """D24 전용: 기존 원시 출력이 없는 patient의 M0 official_long/concise, B0 concise bbox를 새로 생성하는 요청."""
    from . import prompts as P
    ad = tab[ckpt]["digest"]
    rows = []
    prompts_ = {"concise": P.CONCISE}
    if ckpt == "M0":
        prompts_["official_long"] = P.official_long()
    for i in sorted(items):
        it = items[i]
        for pname, prompt in prompts_.items():
            rows.append(Q.make_row(it, ckpt, ad, "bbox", pname, f"bbox_{pname}", prompt, None, cfg, stage))
    return rows


def write_rows(stage, ckpt_or_key, rows):
    os.makedirs(f"{OUT}/requests", exist_ok=True)
    p = f"{OUT}/requests/{stage}__{ckpt_or_key}.jsonl"
    if os.path.exists(p):
        raise RequestError(f"{p} exists (not overwriting)")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p
