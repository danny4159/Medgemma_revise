"""iter_028: C400/E800의 기존 원시 출력·GT·adapter를 감사하고 read-only source manifest를 만든다.

GT는 평가 경로에만 연결한다 (score 계산 입력에는 쓰지 않는다). 새 영상 file/raw/padded pixel hash는
worker 실행 시점에 재계산해 이 manifest의 expected_pixel_sha256과 대조한다 (여기서는 기존 레코드의
저장값만 감사한다).
"""
import glob
import hashlib
import json
import os

from . import parse

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


def build(out_path):
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
    seed17_digest = {recs[("C", 17)][i]["adapter_digest"] for i in val_ids} | \
                    {recs[("E", 17)][i]["adapter_digest"] for i in confirm_ids}
    if seed17_digest != {ADAPTER_TENSOR_DIGEST_KNOWN}:
        raise RuntimeError(f"seed17 adapter_digest in stored records != known: {seed17_digest}")

    def build_split(split, ids_expected):
        c17 = recs[(split, 17)]
        c29 = recs[(split, 29)]
        c43 = recs[(split, 43)]
        m0 = recs[(split, "M0")]
        patients = {}
        for pid in ids_expected:
            p17 = parse.parse_response(c17[pid]["suffix_text_raw"], c17[pid]["ended_eos"])
            p29 = parse.parse_response(c29[pid]["suffix_text_raw"], c29[pid]["ended_eos"])
            p43 = parse.parse_response(c43[pid]["suffix_text_raw"], c43[pid]["ended_eos"])
            g = gt[pid]
            patients[pid] = {
                "id": pid, "split": split, "image": c17[pid]["image"],
                "file_sha256": c17[pid]["image_file_sha256"],
                "expected_pixel_sha256": c17[pid]["input_pixel_sha256"],
                "m0_expected_pixel_sha256": m0[pid]["input_pixel_sha256"],
                "category": g["category"], "gt_boxes": g["boxes"], "y_miss": bool(len(g["boxes"]) > 0),
                "seed17_status": p17["status"], "seed17_suffix_ids": c17[pid]["suffix_ids"],
                "seed17_empty": p17["status"] == "valid_empty",
                "seed29_status": p29["status"], "seed29_empty": p29["status"] == "valid_empty",
                "seed43_status": p43["status"], "seed43_empty": p43["status"] == "valid_empty",
                "seed17_n_output_tokens": c17[pid]["n_output_tokens"],
            }
        return patients

    C = build_split("C", val_ids)
    E = build_split("E", confirm_ids)
    empty_C = [p for p in C.values() if p["seed17_empty"]]
    empty_E = [p for p in E.values() if p["seed17_empty"]]
    for p in empty_C + empty_E:
        if p["seed17_suffix_ids"] not in ([3805, 106],):
            raise RuntimeError(f"unexpected empty suffix ids for {p['id']}: {p['seed17_suffix_ids']}")

    from . import generate as G
    from . import risk28
    os.environ.setdefault("HF_HOME", G.HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION)
    special_token_ids = risk28.resolve_special_ids(proc)

    manifest = {
        "model_revision": "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b",
        "special_token_ids": special_token_ids,
        "adapter_sha256": adapter_sha, "adapter_tensor_digest_seed17": ADAPTER_TENSOR_DIGEST_KNOWN,
        "adapter_digest_seed17": ADAPTER_TENSOR_DIGEST_KNOWN,
        "n_val": len(val_ids), "n_confirm": len(confirm_ids),
        "n_empty_C": len(empty_C), "n_empty_E": len(empty_E),
        "n_opacity_empty_C": sum(p["y_miss"] for p in empty_C),
        "n_opacity_empty_E": sum(p["y_miss"] for p in empty_E),
        "patients": {"C": C, "E": E},
        "empty_ids": {"C": sorted(p["id"] for p in empty_C), "E": sorted(p["id"] for p in empty_E)},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(manifest, open(out_path, "w"), indent=1)
    return manifest


def _h(pid):
    return hashlib.sha256(pid.encode()).hexdigest()


def select_d24(manifest):
    """C400에서 hash 순서로 24명 고정: 빈 출력 12명(카테고리별 4명) + nonempty 12명(두 길이·전 카테고리 포함, hash 순서)."""
    C = manifest["patients"]["C"]
    empty = sorted((p for p in C.values() if p["seed17_empty"]), key=lambda p: _h(p["id"]))
    by_cat = {}
    for p in empty:
        by_cat.setdefault(p["category"], []).append(p)
    empty_pick = []
    for cat in ("opacity", "normal", "not_normal_no_opacity"):
        empty_pick += by_cat.get(cat, [])[:4]
    if len(empty_pick) != 12:
        raise RuntimeError(f"could not pick 12 empty D24 patients: got {len(empty_pick)}")

    nonempty = sorted((p for p in C.values() if not p["seed17_empty"]), key=lambda p: _h(p["id"]))
    need_len = {37, 71} & {p["seed17_n_output_tokens"] for p in nonempty}
    need_cat = {p["category"] for p in nonempty}
    picked, picked_ids = [], set()
    covered_len, covered_cat = set(), set()

    def take(p):
        picked.append(p)
        picked_ids.add(p["id"])
        covered_len.add(p["seed17_n_output_tokens"])
        covered_cat.add(p["category"])

    for p in nonempty:
        if covered_len >= need_len and covered_cat >= need_cat:
            break
        if p["seed17_n_output_tokens"] not in covered_len or p["category"] not in covered_cat:
            take(p)
    for p in nonempty:
        if len(picked) >= 12:
            break
        if p["id"] not in picked_ids:
            take(p)
    if len(picked) != 12:
        raise RuntimeError(f"could not pick 12 nonempty D24 patients: got {len(picked)}")
    if not (covered_len >= need_len and covered_cat >= need_cat):
        raise RuntimeError(f"D24 nonempty pick did not cover need_len={need_len} need_cat={need_cat}: "
                            f"got len={covered_len} cat={covered_cat}")
    return {"empty": empty_pick, "nonempty": picked}


if __name__ == "__main__":
    import sys
    m = build(sys.argv[1] if len(sys.argv) > 1 else "results/iter_028/source_manifest.json")
    print("n_empty_C", m["n_empty_C"], "opacity", m["n_opacity_empty_C"])
    print("n_empty_E", m["n_empty_E"], "opacity", m["n_opacity_empty_E"])
