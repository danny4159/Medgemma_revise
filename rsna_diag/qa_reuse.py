"""iter_015 (extract) / iter_016 (import_manifests, verify_old_stage, build_manifest): 과거 iter_012 confirm concise bbox 출력(M0, B0=seed17 epoch05)을 provenance 검증 후 E600 환자 subset으로 추출한다.

검증(record별): request_id 재계산(모델 revision·adapter digest·split·id·prompt sha), prompt sha == 현재 CONCISE, config_digest == 과거 env 기록 ==
현재 static config(concise 단독)의 재계산, adapter digest == checkpoint table, protocol digest == 과거 protocol 파일 digest, 현재 영상의 file/pixel hash.
과거 protocol은 새 코드로 통과했다고 소급 표시하지 않는다: 원본 protocol digest와 출처 경로를 그대로 기록한다.
사용: python -m rsna_diag.qa_reuse
"""
import glob
import json
import os

import hashlib
import shutil

from . import eval_gate, generate, inputs, lock_protocol, prompts as P, qa_data, qa_gen, qa_requests as Q

SRC_DIRS = {"M0": "results/iter_012/confirm_base", "B0": "results/iter_012/confirm_sft_seed17"}
OLD_PROTOCOL = "results/iter_012/protocols/main_protocol.json"


# iter_015 extract()는 과거 산출물을 만든 기록용이다. iter_016은 재추출하지 않고 아래 함수로 검증만 한다.
def extract():
    if Q.OUT != Q.SRC:
        raise SystemExit("extract() is the iter_015 step; iter_016 must not re-extract")
    sets = json.load(open(f"{Q.OUT}/manifests/sets.json"))
    ids = {i for c in sets["E600"] for i in sets["E600"][c]}
    man = {}
    for ln in open(f"{Q.OUT}/manifests/infer_manifest.jsonl"):
        r = json.loads(ln)
        man[r["id"]] = r
    tab = json.load(open(f"{Q.OUT}/manifests/checkpoints.json"))
    pdig_old = lock_protocol.digest_of(OLD_PROTOCOL)
    psha = P.digest(P.CONCISE)
    os.makedirs(f"{Q.OUT}/reuse", exist_ok=True)
    report = {}
    for ck, d in SRC_DIRS.items():
        adg = tab[ck]["digest"]
        comp = json.load(open(f"{d}/completion.json"))
        assert comp["n_expected"] == comp["n_actual_unique"] and comp["n_missing"] == 0 and comp["n_duplicate"] == 0 and "concise" in comp["prompts"] and comp["adapter_digest"] == adg
        assert comp["protocol_digest"] == pdig_old
        allp = P.all_prompts()
        cdig_now, _ = generate.config_digest(generate.static_env(), {k: allp[k] for k in comp["prompts"]})
        envs = [json.load(open(f)) for f in sorted(glob.glob(f"{d}/gen_worker*.jsonl.env.json"))]
        assert all(e["config_digest"] == cdig_now and e["adapter_digest"] == adg for e in envs), "env config/adapter differ from current"
        recs = {}
        for f in sorted(glob.glob(f"{d}/gen_worker*.jsonl")):
            for r in generate.read_records(f):
                if r["prompt_name"] != "concise":
                    continue
                assert r["id"] not in recs, f"duplicate {r['id']}"
                recs[r["id"]] = r
        assert len(recs) == 800, len(recs)
        out = []
        for i in sorted(ids):
            r = recs[i]
            rid = generate.request_id(generate.MODEL_REVISION, adg, "confirm", i, psha)
            checks = {"request_id": r["request_id"] == rid, "prompt": r["prompt_sha256"] == psha, "config": r["config_digest"] == cdig_now,
                      "adapter": r["adapter_digest"] == adg, "protocol": r["protocol_digest"] == pdig_old,
                      "file": r["image_file_sha256"] == man[i]["file_sha256"],
                      "pixel": r["input_pixel_sha256"] == generate.load_image(man[i]["image"])[2]}
            if not all(checks.values()):
                raise qa_gen.QAError(f"{ck} {i}: provenance check failed {checks}")
            out.append({"id": i, "checkpoint": ck, "condition": "bbox", "request_id": r["request_id"], "suffix_text_raw": r["suffix_text_raw"],
                        "ended_eos": r["ended_eos"], "finish_reason": r["finish_reason"], "n_output_tokens": r["n_output_tokens"],
                        "source_dir": d, "source_worker": r["worker"], "old_protocol_digest": pdig_old, "adapter_digest": adg})
        p = f"{Q.OUT}/reuse/bbox_{ck}_concise.jsonl"
        if os.path.exists(p):
            raise SystemExit(f"{p} exists (not overwriting)")
        with open(p, "w") as f:
            for r in out:
                f.write(json.dumps(r) + "\n")
        report[ck] = {"n_extracted": len(out), "source_total": len(recs), "source_dir": d, "old_protocol_digest": pdig_old,
                      "old_protocol_path": OLD_PROTOCOL, "adapter_digest": adg, "config_digest_recomputed": cdig_now, "run_prompts": comp["prompts"],
                      "note": "과거 protocol을 새 코드로 재검증한 것이 아니다. 출력 provenance만 현재 입력·prompt·adapter와 대조했다."}
    json.dump(report, open(f"{Q.OUT}/reuse/reuse_report.json", "w"), indent=1)
    print(json.dumps(report, indent=1))


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


MANIFEST_FILES = ["sets.json", "labels.json", "infer_manifest.jsonl", "audit.json"]


def import_manifests():
    """iter_015의 확정된 표본·label·manifest를 run-root로 복사한다(재추출 없음). 목적지가 있으면 내용이 같아야 한다. 검증: 전체 checks + 영상 hash."""
    os.makedirs(f"{Q.OUT}/manifests", exist_ok=True)
    rep = {}
    for f in MANIFEST_FILES:
        src, dst = f"{Q.SRC}/manifests/{f}", f"{Q.OUT}/manifests/{f}"
        if os.path.exists(dst):
            if fsha(src) != fsha(dst):
                raise qa_gen.QAError(f"{dst} exists and differs from source")
        else:
            shutil.copyfile(src, dst)
        rep[f] = {"source": src, "sha256": fsha(dst), "source_sha256": fsha(src)}
    sets = json.load(open(f"{Q.OUT}/manifests/sets.json"))
    gt = json.load(open(qa_data.GT))
    man = [json.loads(ln) for ln in open(f"{Q.OUT}/manifests/infer_manifest.jsonl") if ln.strip()]
    sizes = qa_data.checks(sets, gt, man)
    rows = [dict(m, image=m["image"]) for m in man]
    qa_gen.check_inputs(rows)  # 현재 file/raw pixel hash 재확인 (636장)
    lab = json.load(open(f"{Q.OUT}/manifests/labels.json"))
    for i, l in lab.items():
        if gt[i]["category"] != l["category"] or len(gt[i]["boxes"]) != len(l["boxes"]):
            raise qa_gen.QAError(f"labels differ from gt_manifest for {i}")
    rep["_checks"] = {"set_sizes": sizes, "n_images_hash_verified": len(man), "n_labels": len(lab)}
    return rep


def old_protocol_digest(path):
    return lock_protocol.digest_of(path)


def verify_old_stage(stage_dir, requests, ckpt, old_protocol, tab):
    """iter_015 stage 결과를 원래 protocol과 별도로, 현재 입력·adapter·요청 행과 대조하는 호환성 검증 (원본을 재잠금하지 않는다).
    returns dict(기록) — 요청 완전성·중복·잉여·adapter·config·입력 hash 중 하나라도 어긋나면 예외."""
    from . import qa_protocol
    cfg, _ = qa_protocol.static_cfg()
    rows = Q.load_rows(requests, cfg)
    pdig = old_protocol_digest(old_protocol)
    comp = json.load(open(f"{stage_dir}/completion.json"))
    if comp.get("protocol_digest") != pdig:
        raise qa_gen.QAError(f"{stage_dir}: completion protocol digest != old protocol file digest")
    adg = tab[ckpt]["digest"]
    if rows[0]["adapter_digest"] != adg:
        raise qa_gen.QAError(f"{requests}: adapter digest != current checkpoint table")
    qa_gen.check_inputs(rows)
    files = {f: qa_gen.read_strict(f) for f in sorted(glob.glob(f"{stage_dir}/gen_worker*.jsonl"))}
    cache = {}
    done = qa_gen.validate_records(files, rows, cfg, adg, pdig, lambda p: cache.setdefault(p, generate.load_image(p)[2]))
    missing = [r["request_id"] for r in rows if r["request_id"] not in done]
    if missing:
        raise qa_gen.QAError(f"{stage_dir}: {len(missing)} requests missing")
    return {"stage_dir": stage_dir, "requests": requests, "requests_sha256": fsha(requests), "n_requests": len(rows), "n_records": len(done),
            "old_protocol": old_protocol, "old_protocol_digest": pdig, "adapter_digest": adg,
            "worker_files": {os.path.basename(f): fsha(f) for f in files},
            "note": "원래 protocol을 새 코드로 재잠금하지 않았다. 현재 입력·adapter·요청 행과의 호환성만 검증했다."}


def verify_old_bbox_reuse(ck, tab):
    """iter_015 reuse jsonl(M0/B0 E600)을 원본 iter_012 worker 파일과 record 단위로 대조한다."""
    p = f"{Q.SRC}/reuse/bbox_{ck}_concise.jsonl"
    recs = [json.loads(ln) for ln in open(p) if ln.strip()]
    src = SRC_DIRS[ck]
    orig = {}
    for f in sorted(glob.glob(f"{src}/gen_worker*.jsonl")):
        for r in generate.read_records(f):
            if r["prompt_name"] == "concise":
                orig[r["id"]] = r
    ids = [r["id"] for r in recs]
    if len(set(ids)) != len(ids) or len(ids) != 600:
        raise qa_gen.QAError(f"{p}: duplicate or wrong count {len(ids)}")
    man = {json.loads(ln)["id"]: json.loads(ln) for ln in open(f"{Q.OUT}/manifests/infer_manifest.jsonl")}
    pdig_old = old_protocol_digest(OLD_PROTOCOL)
    psha = P.digest(P.CONCISE)
    for r in recs:
        o = orig[r["id"]]
        ok = (r["suffix_text_raw"] == o["suffix_text_raw"] and r["request_id"] == o["request_id"] and r["ended_eos"] == o["ended_eos"]
              and r["adapter_digest"] == tab[ck]["digest"] == o["adapter_digest"] and r["checkpoint"] == ck and r["condition"] == "bbox"
              and o["prompt_sha256"] == psha and o["protocol_digest"] == pdig_old and o["image_file_sha256"] == man[r["id"]]["file_sha256"]
              and o["input_pixel_sha256"] == generate.load_image(man[r["id"]]["image"])[2])
        if not ok:
            raise qa_gen.QAError(f"{ck} {r['id']}: reuse record differs from original record/current inputs")
    return {"path": p, "sha256": fsha(p), "n": len(recs), "source_dir": src, "source_worker_files": {os.path.basename(f): fsha(f) for f in sorted(glob.glob(f"{src}/gen_worker*.jsonl"))},
            "old_protocol": OLD_PROTOCOL, "old_protocol_digest": pdig_old, "adapter_digest": tab[ck]["digest"]}


def build_manifest(out):
    """reuse manifest: manifests 복사 + 재사용하는 D36/D12/E180 결과의 호환성 검증 + M0/B0 bbox record 대조."""
    tab = json.load(open(f"{Q.OUT}/manifests/checkpoints.json"))
    m = {"manifests": import_manifests(), "stages": {}, "bbox_reuse": {}}
    for fmt in ("plain", "json"):
        for ck in ("M0", "B0", "C"):
            st = f"d36_{fmt}"
            m["stages"][f"{st}__{ck}"] = verify_old_stage(f"{Q.SRC}/gen/{st}__{ck}", f"{Q.SRC}/requests/{st}__{ck}.jsonl", ck,
                                                          _protocol_of(f"{Q.SRC}/gen/{st}__{ck}"), tab)
    for st, ck in (("d12_bbox", "B0"), ("d12_bbox", "C"), ("e180_bbox", "C")):
        m["stages"][f"{st}__{ck}"] = verify_old_stage(f"{Q.SRC}/gen/{st}__{ck}", f"{Q.SRC}/requests/{st}__{ck}.jsonl", ck,
                                                      _protocol_of(f"{Q.SRC}/gen/{st}__{ck}"), tab)
    for ck in ("M0", "B0"):
        m["bbox_reuse"][ck] = verify_old_bbox_reuse(ck, tab)
    if os.path.exists(out):
        raise SystemExit(f"{out} exists (not overwriting)")
    json.dump(m, open(out, "w"), indent=1)
    return m


def _protocol_of(stage_dir):
    """completion의 protocol digest와 같은 digest를 갖는 iter_015 protocol 파일을 찾는다(모호하면 오류)."""
    want = json.load(open(f"{stage_dir}/completion.json"))["protocol_digest"]
    hits = [f for f in sorted(glob.glob(f"{Q.SRC}/protocols/*.json")) if old_protocol_digest(f) == want]
    if len(hits) != 1:
        raise qa_gen.QAError(f"{stage_dir}: {len(hits)} old protocol files match digest {want[:12]}")
    return hits[0]


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["manifest"]:
        r = build_manifest(sys.argv[2])
        print(json.dumps({k: (v if k != "manifests" else v["_checks"]) for k, v in r.items() if k != "stages"}, indent=1)[:1500], len(r["stages"]), "stages verified")
    else:
        extract()
