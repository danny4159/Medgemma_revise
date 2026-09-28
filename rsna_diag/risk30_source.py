"""iter_030: 비어 있지 않은 B0(seed17) 출력 C201/E402의 read-only source manifest와 부분 누락 사건 계산.

GT는 이 manifest의 audit 전용 필드에만 있고, GPU 추론에 넘기는 item(risk30.py가 읽는 부분)에는 넣지 않는다.
"""
import glob
import hashlib
import json
import os

from . import geometry, metrics, parse

GT_MANIFEST = "results/iter_010/manifests/gt_manifest.json"
VALIDATION_IDS = "results/iter_010/manifests/validation_ids.json"
CONFIRM_IDS = "results/iter_010/manifests/confirm_ids.json"

PATTERNS = {
    ("C", 17): "results/iter_012/train/lr2e-4_s17/epoch_05/val_gen/gen_worker*.jsonl",
    ("C", 29): "results/iter_012/train/lr2e-4_s29/epoch_05/val_gen/gen_worker*.jsonl",
    ("C", 43): "results/iter_012/train/lr2e-4_s43/epoch_05/val_gen/gen_worker*.jsonl",
    ("C", "M0"): "results/iter_012/base_val_full/gen_worker*.jsonl",
    ("E", 17): "results/iter_012/confirm_sft_seed17/gen_worker*.jsonl",
    ("E", 29): "results/iter_012/confirm_sft_seed29/gen_worker*.jsonl",
    ("E", 43): "results/iter_012/confirm_sft_seed43/gen_worker*.jsonl",
    ("E", "M0"): "results/iter_012/confirm_base/gen_worker*.jsonl",
}
ADAPTER_PATH = "results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt"
ADAPTER_SHA256_KNOWN = "5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29"
ADAPTER_TENSOR_DIGEST_KNOWN = "e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11"

IOU_THR = 0.3
LAST_OPACITY_TOKEN = 23131  # '_opacity'
CLOSE_TOKEN = 236775        # '"'  (list-closing branch)
CONTINUE_TOKEN = 23179      # '"},'  (list-continuation branch)
LIST_CLOSE_TOKEN = 15947    # '}]'
EOT_TOKEN = 106             # <end_of_turn>
EMPTY_SUFFIX = [3805, 106]


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_concise(pattern):
    by_id = {}
    for f in sorted(glob.glob(pattern)):
        for ln in open(f):
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r.get("prompt_name") != "concise":
                continue
            if r["id"] in by_id:
                raise RuntimeError(f"duplicate id {r['id']} in {pattern}")
            by_id[r["id"]] = r
    return by_id


def gt_norm_boxes(gt_entries, aff, pixel_sha=None):
    """gt_manifest의 각 항목은 이미 yxyx_norm(패딩 canvas 기준, 0-1000)을 담고 있다.
    xyxy_px에서 canvas_to_norm으로 독립 재계산해 저장값과 대조한다(허용 오차 1e-6)."""
    top, left, side = aff
    out = []
    for e in gt_entries:
        recomputed = geometry.canvas_to_norm(e["xyxy_px"], top, left, side)
        stored = e["yxyx_norm"]
        if max(abs(a - b) for a, b in zip(recomputed, stored)) > 1e-6:
            raise RuntimeError(f"gt yxyx_norm mismatch: stored={stored} recomputed={recomputed} pixel_sha={pixel_sha}")
        out.append(stored)
    return out


def branch_index(suffix_ids):
    """suffix_ids 내 마지막 LAST_OPACITY_TOKEN(23131)의 index+1 (다음 결정 지점). 없으면 None."""
    idx = None
    for i, t in enumerate(suffix_ids):
        if t == LAST_OPACITY_TOKEN:
            idx = i
    if idx is None:
        return None
    return idx + 1


def event_from_boxes(pred_boxes, gt_boxes, thr=IOU_THR):
    """returns dict: tp, fn_034, any_gt_zero_overlap, y_partial(strict), n_pred, n_gt."""
    pairs = metrics.match(pred_boxes, gt_boxes, thr)
    tp = len(pairs)
    matched_gt = {gi for gi, _ in pairs}
    any_zero = any(all(metrics.inter(g, p) <= 0.0 for p in pred_boxes) for gi, g in enumerate(gt_boxes) if gi not in matched_gt) \
        if len(gt_boxes) > len(matched_gt) else False
    zero_overlap_gt = [gi for gi, g in enumerate(gt_boxes) if gi not in matched_gt and all(metrics.inter(g, p) <= 0.0 for p in pred_boxes)]
    fn = len(gt_boxes) - tp
    y_partial = (tp >= 1) and (len(zero_overlap_gt) >= 1)
    return {"tp": tp, "n_pred": len(pred_boxes), "n_gt": len(gt_boxes), "fn": fn,
            "zero_overlap_gt_idx": zero_overlap_gt, "any_gt_zero_overlap": len(zero_overlap_gt) >= 1,
            "y_partial": bool(y_partial)}


def build(out_path, audit_out_path):
    gt = json.load(open(GT_MANIFEST))
    val_ids = json.load(open(VALIDATION_IDS))
    confirm_ids = json.load(open(CONFIRM_IDS))
    assert len(val_ids) == 400 and len(set(val_ids)) == 400
    assert len(confirm_ids) == 800 and len(set(confirm_ids)) == 800

    recs = {key: load_concise(pat) for key, pat in PATTERNS.items()}
    for split, ids_expected in (("C", val_ids), ("E", confirm_ids)):
        for who in (17, 29, 43, "M0"):
            got = recs[(split, who)]
            missing = set(ids_expected) - set(got)
            extra = set(got) - set(ids_expected)
            if missing or extra:
                raise RuntimeError(f"{split}/{who}: missing={len(missing)} extra={len(extra)}")

    adapter_sha = sha256_file(ADAPTER_PATH)
    if adapter_sha != ADAPTER_SHA256_KNOWN:
        raise RuntimeError(f"adapter sha256 mismatch: {adapter_sha} != {ADAPTER_SHA256_KNOWN}")

    def build_split(split, ids_expected):
        c17, c29, c43, m0 = (recs[(split, w)] for w in (17, 29, 43, "M0"))
        patients_infer = {}   # GT-free: fed to GPU code
        patients_audit = {}   # includes GT; read-only, never passed to generation
        for pid in ids_expected:
            p17 = parse.parse_response(c17[pid]["suffix_text_raw"], c17[pid]["ended_eos"])
            if p17["status"] != "valid_nonempty":
                continue
            if c17[pid]["adapter_digest"] != ADAPTER_TENSOR_DIGEST_KNOWN:
                raise RuntimeError(f"{pid}: seed17 adapter_digest != known")
            p29 = parse.parse_response(c29[pid]["suffix_text_raw"], c29[pid]["ended_eos"])
            p43 = parse.parse_response(c43[pid]["suffix_text_raw"], c43[pid]["ended_eos"])
            pm0 = parse.parse_response(m0[pid]["suffix_text_raw"], m0[pid]["ended_eos"])
            g = gt[pid]
            aff = tuple(c17[pid]["pad_affine_top_left_side"])
            gt_boxes_norm = gt_norm_boxes(g["boxes"], aff, pixel_sha=c17[pid]["input_pixel_sha256"])
            ev = event_from_boxes(p17["boxes"], gt_boxes_norm, IOU_THR)
            bidx = branch_index(c17[pid]["suffix_ids"])
            if bidx is None or bidx >= len(c17[pid]["suffix_ids"]):
                raise RuntimeError(f"{pid}: could not locate branch index in suffix {c17[pid]['suffix_ids']}")
            expect_last4 = c17[pid]["suffix_ids"][-4:]
            if expect_last4 != [LAST_OPACITY_TOKEN, CLOSE_TOKEN, LIST_CLOSE_TOKEN, EOT_TOKEN]:
                raise RuntimeError(f"{pid}: unexpected tail token structure {expect_last4}")
            branch_chosen = c17[pid]["suffix_ids"][bidx]
            if branch_chosen != CLOSE_TOKEN:
                raise RuntimeError(f"{pid}: branch token at index {bidx} is {branch_chosen}, expected {CLOSE_TOKEN}")

            patients_infer[pid] = {
                "id": pid, "split": split, "image": c17[pid]["image"],
                "file_sha256": c17[pid]["image_file_sha256"],
                "expected_pixel_sha256": c17[pid]["input_pixel_sha256"],
                "m0_expected_pixel_sha256": m0[pid]["input_pixel_sha256"],
                "seed17_suffix_ids": c17[pid]["suffix_ids"],
                "seed17_n_output_tokens": c17[pid]["n_output_tokens"],
                "branch_index": bidx,
                "n_pred_boxes": len(p17["boxes"]),
            }
            patients_audit[pid] = {
                "category": g["category"], "gt_boxes_pixel_xyxy": [e["xyxy_px"] for e in g["boxes"]],
                "gt_boxes_norm": gt_boxes_norm,
                "pad_affine": list(aff),
                "pred_boxes_seed17": p17["boxes"], "pred_labels_seed17": p17["labels"],
                "pred_boxes_seed29": p29["boxes"] if p29["status"] in parse.VALID else None,
                "pred_boxes_seed43": p43["boxes"] if p43["status"] in parse.VALID else None,
                "seed29_status": p29["status"], "seed43_status": p43["status"],
                "pred_boxes_m0": pm0["boxes"] if pm0["status"] in parse.VALID else None,
                "m0_status": pm0["status"],
                "event": ev,
            }
        return patients_infer, patients_audit

    C_infer, C_audit = build_split("C", val_ids)
    E_infer, E_audit = build_split("E", confirm_ids)

    from . import generate as G
    from . import risk28
    os.environ.setdefault("HF_HOME", G.HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION)
    special_token_ids = risk28.resolve_special_ids(proc)
    branch_ids = {"opacity": LAST_OPACITY_TOKEN, "close": CLOSE_TOKEN, "continue": CONTINUE_TOKEN,
                  "list_close": LIST_CLOSE_TOKEN, "eot": EOT_TOKEN}
    decoded = {k: proc.tokenizer.decode([v]) for k, v in branch_ids.items()}

    manifest = {
        "model_revision": G.MODEL_REVISION,
        "special_token_ids": special_token_ids,
        "branch_token_ids": branch_ids, "branch_token_decoded": decoded,
        "adapter_sha256": adapter_sha, "adapter_digest_seed17": ADAPTER_TENSOR_DIGEST_KNOWN,
        "n_C": len(C_infer), "n_E": len(E_infer),
        "patients": {"C": C_infer, "E": E_infer},
    }
    audit = {"patients": {"C": C_audit, "E": E_audit},
             "n_events_C": sum(1 for p in C_audit.values() if p["event"]["y_partial"]),
             "n_events_E": sum(1 for p in E_audit.values() if p["event"]["y_partial"])}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    os.makedirs(os.path.dirname(audit_out_path), exist_ok=True)
    json.dump(manifest, open(out_path, "w"), indent=1)
    json.dump(audit, open(audit_out_path, "w"), indent=1)
    return manifest, audit


def token_ids_len(proc, text):
    return len(proc.tokenizer(text, add_special_tokens=False)["input_ids"])


def _h(pid):
    return hashlib.sha256(pid.encode()).hexdigest()


def select_d24(manifest):
    """C에서 hash 순서로 1박스 12명 + 2박스 12명 (계획 2절)."""
    C = manifest["patients"]["C"]
    one = sorted((p for p in C.values() if p["n_pred_boxes"] == 1), key=lambda p: _h(p["id"]))[:12]
    two = sorted((p for p in C.values() if p["n_pred_boxes"] == 2), key=lambda p: _h(p["id"]))[:12]
    if len(one) != 12 or len(two) != 12:
        raise RuntimeError(f"could not select D24: one={len(one)} two={len(two)}")
    return {"one_box": one, "two_box": two}


if __name__ == "__main__":
    import sys
    m, a = build(sys.argv[1] if len(sys.argv) > 1 else "results/iter_030/source_manifest.json",
                 sys.argv[2] if len(sys.argv) > 2 else "results/iter_030/source_audit.json")
    print("n_C", m["n_C"], "events_C", a["n_events_C"])
    print("n_E", m["n_E"], "events_E", a["n_events_E"])
