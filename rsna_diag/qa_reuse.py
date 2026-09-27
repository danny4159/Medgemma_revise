"""iter_015: 과거 iter_012 confirm concise bbox 출력(M0, B0=seed17 epoch05)을 provenance 검증 후 E600 환자 subset으로 추출한다.

검증(record별): request_id 재계산(모델 revision·adapter digest·split·id·prompt sha), prompt sha == 현재 CONCISE, config_digest == 과거 env 기록 ==
현재 static config(concise 단독)의 재계산, adapter digest == checkpoint table, protocol digest == 과거 protocol 파일 digest, 현재 영상의 file/pixel hash.
과거 protocol은 새 코드로 통과했다고 소급 표시하지 않는다: 원본 protocol digest와 출처 경로를 그대로 기록한다.
사용: python -m rsna_diag.qa_reuse
"""
import glob
import json
import os

from . import generate, lock_protocol, prompts as P, qa_data, qa_gen, qa_requests as Q

SRC = {"M0": "results/iter_012/confirm_base", "B0": "results/iter_012/confirm_sft_seed17"}
OLD_PROTOCOL = "results/iter_012/protocols/main_protocol.json"


def extract():
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
    for ck, d in SRC.items():
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


if __name__ == "__main__":
    extract()
