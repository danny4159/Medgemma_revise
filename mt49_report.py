"""iter_049: 적격 manifest 기반 후속 비용 산식·정밀도 표·영상 중복/입력 규모 (CPU-only).
모델 출력은 사용하지 않는다. 결과: results/iter_049/report/feasibility.json
"""
import collections
import json
import math
import os
import sys

from mt49_fetch import OUT, sha256_file

AUD = os.path.join(OUT, "audit_v2")
REP = os.path.join(OUT, "report")
MODEL_SNAP = "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache/models--google--medgemma-1.5-4b-it/snapshots/91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"
TOK_PER_IMAGE = 256  # Gemma3 SigLIP 896x896 -> 256 soft tokens (모델 config로 확인, 아래 mm_tokens_per_image)


def mde(N, q, z_a=1.96, z_b=0.8416):
    """paired accuracy 차이의 최소 검출 효과(독립 case 근사): delta s.t. delta = (z_a+z_b)*sqrt((q-delta^2)/N)."""
    d = 0.0
    for _ in range(200):
        d = (z_a + z_b) * math.sqrt(max(q - d * d, 0) / N)
    return d


def main():
    os.makedirs(REP, exist_ok=True)
    cases = [json.loads(l) for l in open(os.path.join(AUD, "eligible_cases.jsonl"))]
    man = json.load(open(os.path.join(OUT, "image_manifest.json")))
    recs = man["records"]
    # 영상 연결: 모든 case 의 모든 영상이 manifest 에 있고 decode 성공
    by_path = {r["path"]: r for r in recs}
    miss = [i["path"] for c in cases for i in c["images"] if i["path"] not in by_path]
    undec = [r["path"] for r in recs if not r.get("decode_ok")]
    # pixel hash 중복 (case 간)
    owner = collections.defaultdict(set)
    for r in recs:
        owner[r["pixel_sha256"]].add(r["case_key"])
    dup_pix = {h: sorted(v) for h, v in owner.items() if len(v) > 1}
    same_case_dup = collections.Counter(r["pixel_sha256"] for r in recs)
    within_dup = sum(1 for h, n in same_case_dup.items() if n > 1 and len(owner[h]) == 1)
    wh = collections.Counter(tuple(r["wh"]) for r in recs)
    mx = [max(r["wh"]) for r in recs]
    mn = [min(r["wh"]) for r in recs]
    modes = collections.Counter(r["mode"] for r in recs)
    N = len(cases)
    S = sum(c["_audit"]["image_count"] for c in cases)
    # 토큰 수 (텍스트: CLINICAL_HISTORY + options; prompt 템플릿은 후속 계획에서 고정)
    tok_info = {}
    try:
        from transformers import AutoTokenizer
        tk = AutoTokenizer.from_pretrained(MODEL_SNAP, local_files_only=True)
        cfg = json.load(open(os.path.join(MODEL_SNAP, "config.json")))
        tok_info["mm_tokens_per_image_config"] = cfg.get("mm_tokens_per_image")
        tl = []
        for c in cases:
            txt = c["CLINICAL_HISTORY"] + "\n" + "\n".join("%s. %s" % (k, v) for k, v in c["options"].items())
            tl.append(len(tk(txt)["input_ids"]))
        tl.sort()
        tok_info.update({"text_tokens_mean": sum(tl) / N, "text_tokens_max": tl[-1], "text_tokens_p95": tl[int(.95 * N) - 1]})
        per_img = tok_info["mm_tokens_per_image_config"] or TOK_PER_IMAGE
        mx_img = max(c["_audit"]["image_count"] for c in cases)
        tok_info["max_images_in_case"] = mx_img
        tok_info["max_input_tokens_est"] = max(len(tk(c["CLINICAL_HISTORY"])["input_ids"]) +
                                               per_img * c["_audit"]["image_count"] for c in cases)
        tok_info["note"] = "텍스트(이력+선택지)와 영상 soft token 합. chat template·지시문 토큰은 미포함(후속 prompt 고정 시 추가)."
    except Exception as e:  # noqa
        tok_info["error"] = repr(e)
    # 후속 후보 요청량 산식 (실행 허가량 아님)
    req = {
        "N_cases": N, "S_images": S,
        "direct_full_images": N, "per_image_findings": S, "integrate": N, "stepwise_final": N,
        "findings_plus_original_images_final": N, "extra_budget_direct_control": N, "text_only": N,
        "stepwise_total_calls": S + N + N, "stepwise_vs_direct_call_ratio": (S + 2 * N) / N,
        "note": "shared findings 를 조건 2/3 이 공유하면 per_image_findings+integrate 는 한 번만 센다. 비용은 device-seconds 로 실측해야 한다.",
    }
    # 정밀도 표
    prec = []
    for n_eff, label in [(N, "N=%d (cluster 없음 가정)" % N), (round(N * 0.8), "유효 N 80%"), (round(N * 0.5), "유효 N 50%"),
                         (100, "N=100 부분표본")]:
        for q in (0.10, 0.20, 0.30, 0.40):
            for delta in (0.0, 0.05, 0.10):
                se = math.sqrt(max(q - delta ** 2, 0) / n_eff)
                prec.append({"n_eff": n_eff, "label": label, "q_discordant": q, "delta": delta,
                             "SE": round(se, 4), "ci95_half": round(1.96 * se, 4), "ci975_half": round(2.241 * se, 4)})
    mdes = [{"n_eff": n, "q": q, "mde_80power_a05": round(mde(n, q), 4), "mde_80power_a025": round(mde(n, q, 2.241), 4)}
            for n in (N, round(N * 0.8), round(N * 0.5), 100) for q in (0.10, 0.20, 0.30, 0.40)]
    # 하위 군(분석 단위) 크기
    sub = collections.Counter("|".join(c["_audit"]["sub_modalities"]) for c in cases)
    out = {
        "eligible_N": N, "S": S, "unit": "case(title); 환자 동일성 미보장",
        "links": {"cases_without_all_images": miss, "undecodable": undec, "n_bad_in_manifest": man["n_bad"]},
        "image_pixel_dup_across_cases": len(dup_pix), "image_pixel_dup_clusters": dup_pix,
        "within_case_pixel_dup_hashes": within_dup,
        "image_wh_top": [(list(k), v) for k, v in wh.most_common(8)],
        "longest_side_min_max_mean": [min(mx), max(mx), sum(mx) / len(mx)], "shortest_side_min": min(mn),
        "image_modes": dict(modes), "tokens": tok_info, "requests": req,
        "precision_table": prec, "mde_table": mdes, "sub_modality_set_counts": sub.most_common(),
        "acquisition_cost": {"image_download_seconds": man["seconds"], "image_bytes": man["bytes"],
                             "n_images": man["n_images"], "train_jsonl_bytes": os.path.getsize(os.path.join(OUT, "raw", "train.jsonl"))},
        "manifest_digests": {"eligible_cases": sha256_file(os.path.join(AUD, "eligible_cases.jsonl")),
                             "image_manifest": sha256_file(os.path.join(OUT, "image_manifest.json")),
                             "train_jsonl": sha256_file(os.path.join(OUT, "raw", "train.jsonl"))},
    }
    with open(os.path.join(REP, "feasibility.json"), "x") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("precision_table", "image_pixel_dup_clusters")},
                     indent=1, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    sys.exit(main())
