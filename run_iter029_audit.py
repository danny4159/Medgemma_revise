"""iter_029 단계 1: iter_028 C/E raw 산출물을 read-only로 감사하고 provenance를 새 경로에 기록한다.

과거 파일은 전혀 쓰지 않는다. 여기서 만드는 audit.json이 이번 교정 평가의 입력 완전성 근거다.
"""
import glob
import hashlib
import json
import os

from rsna_diag import risk28

SRC_MANIFEST = "results/iter_028/source_manifest.json"
PROTOCOL = "results/iter_028/protocol.json"
OUT = "results/iter_029/audit"


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def check_protocol_locked_files():
    proto = json.load(open(PROTOCOL))
    problems = []
    cur = {}
    for path, want in proto["locked"]["files"].items():
        if not os.path.exists(path):
            problems.append(f"missing locked file: {path}")
            continue
        got = sha256_file(path)
        cur[path] = got
        if got != want:
            problems.append(f"hash mismatch: {path} got={got} want={want}")
    return {"n_locked": len(proto["locked"]["files"]), "problems": problems, "current_hashes": cur}


def audit_split(sm, split):
    """variant별 completion, 중복/누락/잉여, adapter/protocol/pixel 연결을 검사한다.

    계획서 감사 대상: C는 실제로 전체 400명(빈+비빈)에 생성했고(400*5=2000),
    주분석은 그중 빈 출력 199명(199*5=995)만 사용한다. E는 처음부터 빈 출력
    398명에만 생성했다(398*5=1990, 여기에는 확장분이 없다). 두 split의 실제
    생성 대상 모집단이 다르므로 completion 기대 행렬을 분리해서 검사한다.
    """
    all_items = list(sm["patients"][split].values())
    empty_items = [p for p in all_items if p["seed17_empty"]]
    out_dir = f"results/iter_028/{split}"
    expect_items = all_items if split == "C" else empty_items
    comp = risk28.check_completion(out_dir, expect_items, variants=("base", "sft"))
    items = empty_items  # primary-analysis population used below

    problems = list(comp["problems"])
    # per-record cross-checks: adapter digest, protocol digest, pixel hash, duplicate across files
    base_all = risk28.load_all(out_dir, "base")
    sft_all = risk28.load_all(out_dir, "sft")

    proto = json.load(open(PROTOCOL))
    proto_digest_expect = None  # recorded protocol_digest in records; just check internal consistency
    seen_protocol_digests = set()
    for (pid, task), r in list(base_all.items()) + list(sft_all.items()):
        seen_protocol_digests.add(r.get("protocol_digest"))
        if r.get("adapter_digest") is not None and task in ("presence", "ptrue") and r["variant"] == "base":
            problems.append(f"base record has non-null adapter_digest: {pid}/{task}")
    if len(seen_protocol_digests) != 1:
        problems.append(f"multiple distinct protocol_digest values in {split}: {seen_protocol_digests}")

    adapter_digest_seed17 = sm["adapter_digest_seed17"]
    for (pid, task), r in sft_all.items():
        if r.get("adapter_digest") != adapter_digest_seed17:
            problems.append(f"sft record adapter_digest mismatch: {pid}/{task}")

    # exact expected request matrix from source+protocol (not from observed results); primary analysis
    # population is always the empty-output patients, but C's actual generation covered all 400.
    expect_base = {(p["id"], t) for p in expect_items for t in risk28.expected_tasks("base")}
    expect_sft = {(p["id"], t) for p in expect_items for t in risk28.expected_tasks("sft")}
    got_base = set(base_all)
    got_sft = set(sft_all)
    if got_base != expect_base:
        problems.append(f"base matrix mismatch: missing={len(expect_base-got_base)} extra={len(got_base-expect_base)}")
    if got_sft != expect_sft:
        problems.append(f"sft matrix mismatch: missing={len(expect_sft-got_sft)} extra={len(got_sft-expect_sft)}")
    n_primary_base = {(p["id"], t) for p in items for t in risk28.expected_tasks("base")}
    n_primary_sft = {(p["id"], t) for p in items for t in risk28.expected_tasks("sft")}
    if not (n_primary_base <= got_base and n_primary_sft <= got_sft):
        problems.append("primary-analysis (empty-output) requests are not a subset of generated records")

    return {
        "split": split, "n_empty": len(items), "n_events": sum(1 for p in items if p["y_miss"]),
        "n_base_records": len(base_all), "n_sft_records": len(sft_all),
        "problems": problems, "protocol_digests_seen": sorted(str(d) for d in seen_protocol_digests),
        "completion": comp,
    }


def check_pixel_hashes(sm, split):
    """images의 현재 file/pixel hash를 manifest 저장값과 대조한다 (GPU 로드 없이 파일 hash만)."""
    items = sm["patients"][split]
    problems = []
    n = 0
    for pid, p in items.items():
        path = p["image"]
        if not os.path.exists(path):
            problems.append(f"missing image file: {pid} {path}")
            continue
        file_sha = sha256_file(path)
        if file_sha != p["file_sha256"]:
            problems.append(f"file hash mismatch: {pid} got={file_sha} want={p['file_sha256']}")
        n += 1
    return {"split": split, "n_checked": n, "problems": problems}


def protocol_digest_reconciliation():
    """C와 E는 서로 다른 protocol_digest로 생성됐다(claude_stream.jsonl 라인 668/706/712에서 복원).
    C 생성 완료 후 risk28.py main()의 분기가 'C/E 요청 전체(400/800명)'를 채점하던 버그를
    '빈 출력만 채점'하도록 한 줄 수정했고, 그 직후 protocol을 재잠금해 E를 생성했다.
    이 수정은 빈 출력 199/398명 각자의 score_token_original/score_yes_no 계산 경로를
    바꾸지 않는다(호출 인자·prompt·max_new가 patient 단위로 동일하다). 따라서 두 protocol_digest
    차이는 주분석 대상 population에 영향을 주지 않는 것으로 문서화하되, 과거 protocol.json bytes
    자체(교체 전 버전)는 현재 파일로 복원할 수 없어 완전한 재실행 검증은 아니다."""
    return {
        "explanation": "C empty-199 records were generated before a one-line risk28.py fix "
                       "(main(): item filter 'all patients' -> 'seed17_empty only') that only "
                       "removes surplus nonempty-patient requests from being scored; it does not "
                       "change how any individual patient (empty or not) is scored. E was generated "
                       "after this fix and after re-locking protocol.json.",
        "recovered_from": "agent/runs/iter_028/claude_stream.jsonl lines 668 (C launch), 701 (bug "
                           "note), 706 (Edit diff), 712 (protocol re-lock), 748 (E launch)",
        "edit_old": "items = list(sm[\"patients\"][a.split].values())",
        "edit_new": "items = [p for p in sm[\"patients\"][a.split].values() if p[\"seed17_empty\"]]",
        "affects_primary_empty_population_scoring": False,
        "caveat": "past protocol.json bytes at C-generation-time are not independently recoverable; "
                  "this is a documented code-diff reconciliation, not a byte-level replay.",
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    sm = json.load(open(SRC_MANIFEST))

    proto_check = check_protocol_locked_files()

    sm_hash = sha256_file(SRC_MANIFEST)
    proto = json.load(open(PROTOCOL))
    sm_locked = proto["locked"]["files"].get(SRC_MANIFEST)

    problems_all = list(proto_check["problems"])
    if sm_locked is not None and sm_hash != sm_locked:
        problems_all.append(f"source_manifest hash changed since protocol lock: {sm_hash} != {sm_locked}")

    splits_report = {}
    for split in ("C", "E"):
        r = audit_split(sm, split)
        px = check_pixel_hashes(sm, split)
        r["pixel_audit"] = px
        problems_all += [f"{split}: {p}" for p in r["problems"]]
        problems_all += [f"{split}: {p}" for p in px["problems"]]
        splits_report[split] = r

    # cross-split patient/pixel-hash overlap check
    c_ids = set(sm["patients"]["C"])
    e_ids = set(sm["patients"]["E"])
    overlap = c_ids & e_ids
    if overlap:
        problems_all.append(f"patient id overlap between C and E: {len(overlap)}")
    c_px = {p["file_sha256"] for p in sm["patients"]["C"].values()}
    e_px = {p["file_sha256"] for p in sm["patients"]["E"].values()}
    px_overlap = c_px & e_px
    if px_overlap:
        problems_all.append(f"pixel hash overlap between C and E: {len(px_overlap)}")

    out = {
        "protocol_check": proto_check,
        "protocol_digest_reconciliation": protocol_digest_reconciliation(),
        "source_manifest_hash": sm_hash, "source_manifest_locked_hash": sm_locked,
        "splits": splits_report,
        "patient_id_overlap_C_E": len(overlap),
        "pixel_hash_overlap_C_E": len(px_overlap),
        "n_problems": len(problems_all), "problems": problems_all,
        "ok": len(problems_all) == 0,
    }
    json.dump(out, open(os.path.join(OUT, "audit.json"), "w"), indent=1)
    print(f"ok={out['ok']} n_problems={len(problems_all)}")
    for p in problems_all:
        print(" -", p)


if __name__ == "__main__":
    main()
