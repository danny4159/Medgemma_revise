"""iter_028 D24: 동작 확인 (GPU). 24명(빈 12 + nonempty 12)에서

1. B0 adapter 로드 후 원래 bbox 출력 재현(generate_scored, 빈/nonempty 모두)
2. 독립 CPU FP64(numpy) log_softmax와 torch FP32 log_softmax 대조
3. Presence/P(True) M0/B0 score 산출과 tokenizer 단일 token 확인
4. 24요청(=1 task, D24 자체는 patient 단위 sanity이며 별도로 controlled interrupt/resume은 run_iter028_resume.py에서 수행)

실행: python run_iter028_d24.py [--out results/iter_028/d24]
"""
import argparse
import json
import os
import time

import numpy as np

from rsna_diag import generate as G, risk28, risk28_source as RS, prompts as PR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/iter_028/d24")
    ap.add_argument("--manifest", default="results/iter_028/source_manifest.json")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    manifest = json.load(open(a.manifest))
    d24 = RS.select_d24(manifest)
    patients = d24["empty"] + d24["nonempty"]
    print(f"D24: {len(d24['empty'])} empty + {len(d24['nonempty'])} nonempty = {len(patients)}")

    torch, proc, model = G.load_model()
    ids_map = risk28.resolve_special_ids(proc)
    print("special token ids:", ids_map)
    env = G.env_info(torch, proc, model)
    print("model revision:", env["model_revision"], "transformers", env["transformers"], "torch", env["torch"])
    assert env["model_revision"] == risk28.MODEL_REVISION

    adapter_digest = G.load_adapter(torch, model, "results/iter_012/train/lr2e-4_s17/epoch_05")
    print("adapter digest:", adapter_digest)
    assert adapter_digest == manifest["adapter_digest_seed17"], "adapter digest mismatch"

    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])

    results = []
    numeric_checks = []
    for p in patients:
        image, aff, px_hash = G.load_image(p["image"])
        assert px_hash == p["expected_pixel_sha256"], f"pixel hash mismatch for {p['id']}"
        expect_suffix = p["seed17_suffix_ids"]
        max_new = max(8, len(expect_suffix) + 4)
        rec = risk28.score_token_original(torch, proc, model, ids_map, image, eos_ids,
                                           expect_suffix=expect_suffix, max_new=max_new)
        ok_reproduce = rec["suffix_ids"] == expect_suffix
        results.append({"id": p["id"], "category": p["category"], "expect_len": len(expect_suffix),
                         "got_len": len(rec["suffix_ids"]), "reproduced": ok_reproduce,
                         "ended_eos": rec["ended_eos"], "argmax_matches_greedy": rec["argmax_matches_greedy"],
                         "nll_bracket": rec.get("nll_bracket"), "entropy_bracket": rec.get("entropy_bracket")})
        if not ok_reproduce:
            print("MISMATCH", p["id"], "expect", expect_suffix, "got", rec["suffix_ids"])

    # 독립 CPU FP64 log_softmax 대조: D24의 각 빈 출력 patient에서 step0 raw logits 재추출해 비교
    for p in d24["empty"][:6]:
        image, aff, px_hash = G.load_image(p["image"])
        inp = risk28.build_image_inputs(proc, image, PR.CONCISE)
        gs = risk28.generate_scored(torch, model, inp, 8, eos_ids)
        row = gs["scores"][0]
        nll_t, ent_t, _ = risk28.fp32_logsoftmax_stats(row, ids_map["bracket"])
        nll_c, ent_c = risk28.cpu_independent_logsoftmax_stats(row.numpy(), ids_map["bracket"])
        d_nll, d_ent = abs(nll_t - nll_c), abs(ent_t - ent_c)
        numeric_checks.append({"id": p["id"], "nll_torch_fp32": nll_t, "nll_cpu_fp64": nll_c,
                                "d_nll": d_nll, "entropy_torch_fp32": ent_t, "entropy_cpu_fp64": ent_c,
                                "d_entropy": d_ent, "d_nll_le_1e-3": d_nll <= 1e-3, "d_entropy_le_1e-3": d_ent <= 1e-3})

    # Presence/P(True) sanity: M0/B0 각 3명 (empty D24 앞 3명)에서 실행
    presence_ptrue = []
    for p in d24["empty"][:3]:
        image, aff, px_hash = G.load_image(p["image"])
        b0_pres = risk28.score_yes_no(torch, proc, model, ids_map, image, risk28.presence_prompt(), eos_ids, "presence")
        b0_ptrue = risk28.score_yes_no(torch, proc, model, ids_map, image, risk28.ptrue_prompt(), eos_ids, "ptrue")
        presence_ptrue.append({"id": p["id"], "variant": "sft", "presence": b0_pres, "ptrue": b0_ptrue})

    del model
    torch.cuda.empty_cache()
    torch2, proc2, model2 = G.load_model()
    for p in d24["empty"][:3]:
        image, aff, px_hash = G.load_image(p["image"])
        m0_pres = risk28.score_yes_no(torch2, proc2, model2, ids_map, image, risk28.presence_prompt(), eos_ids, "presence")
        m0_ptrue = risk28.score_yes_no(torch2, proc2, model2, ids_map, image, risk28.ptrue_prompt(), eos_ids, "ptrue")
        presence_ptrue.append({"id": p["id"], "variant": "base", "presence": m0_pres, "ptrue": m0_ptrue})
    del torch2, proc2, model2

    n_repro = sum(r["reproduced"] for r in results)
    n_eos = sum(r["ended_eos"] for r in results)
    n_argmax = sum(r["argmax_matches_greedy"] for r in results)
    gate = {
        "n_patients": len(patients), "n_reproduced": n_repro, "n_ended_eos": n_eos,
        "n_argmax_matches_greedy": n_argmax,
        "gate_reproduce_all": n_repro == len(patients),
        "gate_eos_all": n_eos == len(patients),
        "gate_argmax_all": n_argmax == len(patients),
        "gate_numeric_all": all(c["d_nll_le_1e-3"] and c["d_entropy_le_1e-3"] for c in numeric_checks),
        "special_token_ids": ids_map, "adapter_digest": adapter_digest,
        "model_revision": env["model_revision"], "transformers": env["transformers"], "torch": env["torch"],
    }
    gate["PASS"] = gate["gate_reproduce_all"] and gate["gate_eos_all"] and gate["gate_argmax_all"] and gate["gate_numeric_all"]
    out = {"gate": gate, "per_patient": results, "numeric_checks": numeric_checks, "presence_ptrue": presence_ptrue}
    json.dump(out, open(os.path.join(a.out, "d24_sanity.json"), "w"), indent=1)
    print(json.dumps(gate, indent=1))


if __name__ == "__main__":
    main()
