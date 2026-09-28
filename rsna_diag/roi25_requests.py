"""iter_025 D768 요청 행렬: 2 checkpoint(M0,B0) x 4 target(TL/TR/BL/BR) x 4 condition(OB_I,OB_T,OC_I,OC_T) x 24 patient.

request_id는 modality를 포함한 전체 provenance의 hash다 (image/text 조건은 서로 다른 id를 가진다).
"""
import json
import os

from . import generate, prompts as P, roi23_spec as R, roi25_spec as R25

OUT = os.environ.get("ROI25_RUN_ROOT", "results/iter_025")
CKPT_SPEC = {"M0": None, "B0": "results/iter_012/train/lr2e-4_s17/epoch_05"}
ID_FIELDS = ("model_revision", "adapter_digest", "id", "split", "modality", "file_sha256", "pixel_sha256", "target",
             "fmt", "condition", "prompt_sha256", "config_digest", "preprocess")


class RequestError(RuntimeError):
    pass


def compute_id(row):
    return R.request_key({k: row.get(k) for k in ID_FIELDS})


def make_row(item_id, split, ckpt, adapter_digest, target, condition, prompt, cfg_digest, stage, modality,
             image_fields=None, extra=None):
    row = {"id": item_id, "split": split, "checkpoint": ckpt, "adapter_digest": adapter_digest, "target": target,
           "fmt": R25.FMT, "condition": condition, "prompt": prompt, "prompt_sha256": P.digest(prompt),
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
    if row["modality"] == "text" and (row.get("image") is not None or row.get("file_sha256") is not None
                                       or row.get("pixel_sha256") is not None):
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
    if os.path.exists(out):
        old = json.load(open(out))
        if old != tab:
            raise RequestError("checkpoint table exists and differs")
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(tab, open(out, "w"), indent=1)
    return tab


def build_d(items, gts, tab, cfg, stage="D"):
    """returns {ckpt: [rows]}. items: {id: manifest row with image/file_sha256/pixel_sha256/split}."""
    out = {}
    for ckpt in ("M0", "B0"):
        ad = tab[ckpt]["digest"]
        rows = []
        for i in sorted(items):
            boxes_f = [b["yxyx_norm"] for b in gts[i]["boxes"]]
            boxes_i = R25.check_rounding_preserves_answer(boxes_f)
            for target in R25.TARGETS:
                for cond in R25.CONDITIONS:
                    modality = R25.MODALITY_OF[cond]
                    txt = R25.prompt(cond, target, boxes_i)
                    img_fields = None
                    extra = {"boxes_int": boxes_i, "representation": R25.REPRESENTATION_OF[cond]}
                    if modality == "image":
                        img_fields = {"image": items[i]["image"], "file_sha256": items[i]["file_sha256"],
                                      "pixel_sha256": items[i]["pixel_sha256"]}
                    rows.append(make_row(i, items[i]["split"], ckpt, ad, target, cond, txt, cfg, stage, modality,
                                         img_fields, extra))
        out[ckpt] = rows
    return out


def build_ar(items, gts, tab, cfg, ckpts, stage="AR"):
    """OB/OC 모두 실패했을 때의 답 읽기 sanity: text-only, 정답 사분면 이름을 GT로 직접 제공한다.
    ckpts: OB gate가 실패한 checkpoint 목록 (최대 ['M0','B0'])."""
    out = {}
    for ckpt in ckpts:
        ad = tab[ckpt]["digest"]
        rows = []
        for i in sorted(items):
            boxes_f = [b["yxyx_norm"] for b in gts[i]["boxes"]]
            boxes_i = R25.check_rounding_preserves_answer(boxes_f)
            names = R25.quadrant_names_from_boxes(boxes_i)
            for target in R25.TARGETS:
                txt = R25.ar_prompt(target, names)
                rows.append(make_row(i, items[i]["split"], ckpt, ad, target, "AR", txt, cfg, stage, "text",
                                     extra={"quadrant_names": names}))
        out[ckpt] = rows
    return out


def write_rows(stage, ckpt, rows, out_dir=None):
    out_dir = out_dir or f"{OUT}/requests"
    os.makedirs(out_dir, exist_ok=True)
    p = f"{out_dir}/{stage}__{ckpt}.jsonl"
    if os.path.exists(p):
        raise RequestError(f"{p} exists (not overwriting)")
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p
