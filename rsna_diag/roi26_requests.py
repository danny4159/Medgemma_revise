"""iter_026 요청 행렬 빌더: V(direct)/O(oracle, D전용)/RD(reader, M0전용)/text-only(D전용).

request_id는 stage를 포함하지 않는다 (roi25_requests와 동일한 설계): 같은 (checkpoint, target, condition, id, prompt)
조합이면 E60/E200처럼 서로 다른 stage에서도 같은 request_id를 가져 생성 출력을 그대로 재사용할 수 있다.
"""
import json
import os

from . import generate, prompts as P, roi23_spec as R, roi26_spec as R26

OUT = os.environ.get("ROI26_RUN_ROOT", "results/iter_026")
CKPT_SPEC = {"M0": None, "B0": "results/iter_012/train/lr2e-4_s17/epoch_05",
             "B29": "results/iter_012/train/lr2e-4_s29/epoch_05", "B43": "results/iter_012/train/lr2e-4_s43/epoch_05"}
ID_FIELDS = ("model_revision", "adapter_digest", "id", "split", "modality", "file_sha256", "pixel_sha256", "target",
             "condition", "prompt_sha256", "config_digest", "preprocess")


class RequestError(RuntimeError):
    pass


def compute_id(row):
    return R.request_key({k: row.get(k) for k in ID_FIELDS})


def make_row(item_id, split, ckpt, adapter_digest, target, condition, prompt, cfg_digest, stage, modality,
             image_fields=None, extra=None):
    row = {"id": item_id, "split": split, "checkpoint": ckpt, "adapter_digest": adapter_digest, "target": target,
           "condition": condition, "prompt": prompt, "prompt_sha256": P.digest(prompt),
           "model_revision": generate.MODEL_REVISION, "config_digest": cfg_digest,
           "preprocess": generate.PREPROC_VERSION, "stage": stage, "modality": modality}
    if modality == "image":
        row.update({"image": image_fields["image"], "file_sha256": image_fields["file_sha256"],
                    "pixel_sha256": image_fields["pixel_sha256"]})
    else:
        row.update({"image": None, "file_sha256": None, "pixel_sha256": None})
    if extra:
        row["extra"] = extra
    row["request_id"] = compute_id(row)
    return row


def verify_row(row, cfg_digest):
    if row.get("prompt_sha256") != P.digest(row["prompt"]):
        raise RequestError(f"prompt_sha256 mismatch for {row.get('request_id')}")
    if row.get("config_digest") != cfg_digest:
        raise RequestError(f"config_digest mismatch for {row.get('request_id')}")
    if row.get("model_revision") != generate.MODEL_REVISION:
        raise RequestError("model revision differs")
    if row.get("request_id") != compute_id(row):
        raise RequestError(f"request_id != recomputed for {row.get('request_id')}")
    if row["modality"] == "text" and (row.get("image") is not None or row.get("file_sha256") is not None):
        raise RequestError(f"text-only row {row.get('request_id')} carries image fields")
    if row["modality"] == "image" and row.get("image") is None:
        raise RequestError(f"image row {row.get('request_id')} missing image field")
    return True


def load_rows(path, cfg_digest=None):
    rows = [json.loads(ln) for ln in open(path) if ln.strip()]
    ids = [r["request_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise RequestError(f"duplicate request_id in {path}")
    if cfg_digest:
        for r in rows:
            verify_row(r, cfg_digest)
    return rows


def checkpoints(ckpts, out=None):
    import torch
    from . import eval_gate
    out = out or f"{OUT}/manifests/checkpoints.json"
    tab = json.load(open(out)) if os.path.exists(out) else {}
    changed = False
    for k in ckpts:
        if k in tab:
            continue
        d = CKPT_SPEC[k]
        if d is None:
            tab[k] = {"dir": None, "digest": None}
        else:
            b = torch.load(os.path.join(d, "adapter.pt"), map_location="cpu", weights_only=True)
            tab[k] = {"dir": d, "digest": eval_gate.adapter_digest(d), "epoch": b.get("epoch"), "step": b.get("step"),
                      "train_digest": b.get("train_digest"), "lora": b["config"]}
        changed = True
    if changed:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + ".tmp"
        json.dump(tab, open(tmp, "w"), indent=1)
        os.replace(tmp, out)
    return tab


def _img_fields(item):
    return {"image": item["image"], "file_sha256": item["file_sha256"], "pixel_sha256": item["pixel_sha256"]}


def build_v(items, tab, cfg, ckpts, stage):
    out = {}
    for ckpt in ckpts:
        ad = tab[ckpt]["digest"]
        rows = []
        for i in sorted(items):
            for t in R26.TARGETS:
                txt = R26.v_prompt(t)
                rows.append(make_row(i, items[i]["split"], ckpt, ad, t, "V", txt, cfg, stage, "image",
                                     _img_fields(items[i])))
        out[ckpt] = rows
    return out


def build_o(items, gts, tab, cfg, ckpts, stage="D"):
    out = {}
    for ckpt in ckpts:
        ad = tab[ckpt]["digest"]
        rows = []
        for i in sorted(items):
            boxes_f = sorted([b["yxyx_norm"] for b in gts[i]["boxes"]], key=lambda b: json.dumps(b))
            boxes_i = R26.boxes_int(boxes_f)
            for t in R26.TARGETS:
                txt = R26.o_prompt(t, boxes_i)
                rows.append(make_row(i, items[i]["split"], ckpt, ad, t, "O", txt, cfg, stage, "image",
                                     _img_fields(items[i]), extra={"gt_boxes_int": boxes_i}))
        out[ckpt] = rows
    return out


def build_rd(items, proposals, tab, cfg, stage, ckpt="M0"):
    """proposals: {id: (boxes_norm_float or None, status)}. status != valid면 그 환자는 건너뛰고 unavailable로 기록."""
    ad = tab[ckpt]["digest"]
    rows, unavailable = [], []
    for i in sorted(items):
        boxes_f, status = proposals.get(i, (None, "missing"))
        if boxes_f is None:
            unavailable.append({"id": i, "status": status})
            continue
        boxes_i = R26.boxes_int(boxes_f)
        for t in R26.TARGETS:
            txt = R26.rd_prompt(t, boxes_i)
            rows.append(make_row(i, items[i]["split"], ckpt, ad, t, "RD", txt, cfg, stage, "image",
                                 _img_fields(items[i]), extra={"proposal_boxes_int": boxes_i,
                                                                "proposal_status": status}))
    return rows, unavailable


def build_text(tab, cfg, ckpts, stage="D"):
    out = {}
    for ckpt in ckpts:
        ad = tab[ckpt]["digest"]
        rows = []
        for t in R26.TARGETS:
            txt = R26.v_prompt(t)
            rows.append(make_row("control_text", "control", ckpt, ad, t, "V_TEXT", txt, cfg, stage, "text"))
        out[ckpt] = rows
    return out


def write_rows(name, rows, out_dir=None):
    out_dir = out_dir or f"{OUT}/requests"
    os.makedirs(out_dir, exist_ok=True)
    p = f"{out_dir}/{name}.jsonl"
    if os.path.exists(p):
        raise RequestError(f"{p} exists (not overwriting)")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p
