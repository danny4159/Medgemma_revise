"""iter_014 GPU fixture (실제 MedGemma). 사용: python -m rsna_diag.on_gpu --gpu N -- python test_rsna_iter014_gpu.py
결과: results/iter_014/tests/fixtures_iter014_gpu.json
사전 고정 허용 오차(bf16): A 후보 span logits |suffix 유무 차이| <= 0.05 (softcap 후 logit), NLL 차이 <= 0.02;
B C 환원: CE 합 상대 1e-6, LoRA gradient 최대 상대 1e-5 (같은 연산이므로 사실상 비트 동일 기대); C branch chunk 합 상대 <= 1e-2(bf16 padding·batch 효과)."""
import json
import os
import sys

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"  # run2: 결정적 kernel (run1은 비결정 kernel이라 B의 gradient 대조가 잡음에 묻혔다; run1 결과는 별도 파일에 보존)

import numpy as np

OUT = "results/iter_014/tests/fixtures_iter014_gpu.json"
res = []


def ok(name, cond, detail=""):
    res.append({"name": name, "pass": bool(cond), "detail": str(detail)[:400]})
    print(("PASS " if cond else "FAIL ") + name, str(detail)[:200], flush=True)


def main():
    import torch
    from rsna_diag import adapt as A, adapt_geo as AG, coord_loss as CL, geo_loss as GL, inputs, lora, prompts as P, sft_data
    from rsna_diag import train as T
    items, gt = inputs.load_items(T.MANIFEST, T.GT, "results/iter_013/subsets/sanity16_ids.json", "train", exact=False)
    cands = json.load(open("results/iter_014/candidates/train_candidates.json"))
    T.set_deterministic(torch)
    _, proc, model, names = T.setup_model(17)
    tok = proc.tokenizer
    dig = CL.digit_ids(tok)
    pb = torch.load("results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt", map_location="cpu", weights_only=True)
    lora.load_lora_state(model, pb["state"])
    model.eval()  # dropout 끔 (수치 등가 검사 전용; 본학습 설정은 바꾸지 않음)
    params = list(lora.lora_params(model).values())
    pos = [k for k, it in enumerate(items) if gt[it["id"]]["category"] == "opacity"]
    multi = [k for k in pos if len(gt[items[k]["id"]]["boxes"]) >= 2]
    sel = [pos[0], multi[0]]
    order = np.arange(len(items))
    dsG = AG.GeoDataset(tok, proc, items, gt, P.CONCISE, order, dig, "G", cands)
    dsC = AG.GeoDataset(tok, proc, items, gt, P.CONCISE, order, dig, "C", cands)
    exG = [dsG[k] for k in sel]
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    cuda = lambda d: {k: v.cuda() for k, v in d.items()}

    # A. suffix가 span logits에 영향이 없다 (causal)
    e = exG[1]
    br = e["branches"][1]
    tgt = sft_data.target_text([b["yxyx_norm"] for b in gt[items[sel[1]]["id"]]["boxes"]])
    ctext = GL.replace_box_text(tgt, br["box"], br["cand"])
    img, _, _ = inputs.load_verified(items[sel[1]])
    full = sft_data.build_example(proc, img, P.CONCISE, ctext)
    n_br = len(br["input_ids"])
    a0, a1 = br["span"]
    npf = full["n_prefix"]

    def span_logits(input_ids, tt):
        b = {"input_ids": input_ids[None].cuda(), "attention_mask": torch.ones(1, len(input_ids), dtype=torch.long).cuda(), "pixel_values": full["pixel_values"].to(torch.bfloat16).cuda()}
        if tt is not None:
            b["token_type_ids"] = tt[None].cuda()
        with torch.no_grad():
            h = model.model(**b, use_cache=False).last_hidden_state[0]
            lg = model.lm_head(h[npf + a0 - 1:npf + a1]).float()
            if softcap:
                lg = torch.tanh(lg / softcap) * softcap
        return lg

    l_trunc = span_logits(br["input_ids"], br.get("token_type_ids"))
    l_full = span_logits(full["input_ids"], full.get("token_type_ids"))
    lab = br["input_ids"][npf + a0:npf + a1 + 1].cuda()
    nll = lambda lg: (torch.logsumexp(lg, -1) - lg.gather(1, lab[:, None]).squeeze(1))
    d_lg, d_nll = float((l_trunc - l_full).abs().max()), float((nll(l_trunc) - nll(l_full)).abs().max())
    ok("A(preset tol): truncated-branch span logits vs full-candidate-sequence span logits (|dlogit|<=0.05, |dNLL|<=0.02; run1 FAILED this bf16 tolerance: length-dependent kernel noise)", d_lg <= 0.05 and d_nll <= 0.02, (d_lg, d_nll))
    # A1(run2 추가, 결과를 본 뒤 정의): 같은 길이에서 suffix token만 무작위 교체 -> span logits는 정확히 같아야 한다 (causal). A2: 길이가 다른 경우의 잡음 하한
    # (같은 sequence에 마지막 token 하나를 더 붙인 것 vs 원본)과 truncated-vs-full 차이를 비교한다.
    ids_full = full["input_ids"].clone()
    tt_full = full.get("token_type_ids")
    ids_mod = ids_full.clone()
    g_ = torch.Generator().manual_seed(1)
    ids_mod[npf + a1 + 1:] = torch.randint(1000, 5000, (len(ids_full) - (npf + a1 + 1),), generator=g_)
    l_mod = span_logits(ids_mod, tt_full)
    d_same = float((l_full - l_mod).abs().max())
    ok("A1: same length, random suffix tokens -> span logits identical (abs<=1e-5)", d_same <= 1e-5 and len(ids_full) > npf + a1 + 1, (d_same, len(ids_full) - (npf + a1 + 1)))
    # A2: 배치 padding(오른쪽, attention_mask=0)으로 길이만 45 token 늘린 경우의 span logits 변화 = 길이 변화에 따른 kernel 수치 잡음 하한.
    # truncated-vs-full 차이가 이 잡음과 같은 규모면 (같은 길이 suffix 교체가 정확히 0인 A1과 함께) 차이는 수치 잡음이지 정보 누출이 아니다.
    npad = len(ids_full) - n_br
    ids_pad = torch.cat([ids_full, torch.full((npad,), tok.pad_token_id)])
    tt_pad = torch.cat([tt_full, torch.zeros(npad, dtype=torch.long)]) if tt_full is not None else None
    bpad = {"input_ids": ids_pad[None].cuda(), "attention_mask": torch.cat([torch.ones(len(ids_full)), torch.zeros(npad)]).long()[None].cuda(),
            "pixel_values": full["pixel_values"].to(torch.bfloat16).cuda()}
    if tt_pad is not None:
        bpad["token_type_ids"] = tt_pad[None].cuda()
    with torch.no_grad():
        hp = model.model(**bpad, use_cache=False).last_hidden_state[0]
        lp = model.lm_head(hp[npf + a0 - 1:npf + a1]).float()
        if softcap:
            lp = torch.tanh(lp / softcap) * softcap
    d_floor = float((l_full - lp).abs().max())
    d_nll_floor = float((nll(l_full) - nll(lp)).abs().max())
    ok("A2: truncated-vs-full difference <= 2x length-change noise floor (full vs full right-padded by same token count)", d_lg <= max(2 * d_floor, 1e-3) and d_nll <= max(2 * d_nll_floor, 1e-3),
       {"trunc_vs_full": (d_lg, d_nll), "pad_floor": (d_floor, d_nll_floor)})

    # B. C 환원: 새 geo_forward(C, tokw=1) == iter_013 adapt_loss C (CE 합·gradient)
    exC = [dsC[k] for k in sel]
    bC_new = cuda({k: v for k, v in AG.collate(exC, tok.pad_token_id).items() if k not in ("branches", "sample_pos")})
    bC_old = cuda({k: v for k, v in A.collate([dict(dsC_old) for dsC_old in [A.AdaptDataset(tok, proc, items, gt, P.CONCISE, order, dig)[k] for k in sel]], tok.pad_token_id).items() if k != "sample_pos"})
    for p in params:
        p.grad = None
    w_new, ce_new, n_new = AG.geo_forward(torch, model, bC_new, softcap)
    w_new.backward()
    g_new = [p.grad.detach().clone() for p in params]
    for p in params:
        p.grad = None
    r_old = A.adapt_loss(torch, model, bC_old, softcap, "C", dig, 0.1, 1.0)
    r_old["ce_sum"].backward()
    g_old = [p.grad.detach().clone() for p in params]
    rel_ce = abs(float(w_new) - float(r_old["ce_sum"])) / abs(float(r_old["ce_sum"]))
    gerr = max(float((a - b).abs().max() / (b.abs().max() + 1e-12)) for a, b in zip(g_new, g_old) if b.abs().max() > 0)
    ok("B: C path (q0=1, no branch) == iter_013 adapt_loss C: CE sum and LoRA gradient", rel_ce <= 1e-6 and gerr <= 1e-5 and n_new == r_old["n_tok"], (rel_ce, gerr, n_new, r_old["n_tok"]))
    for p in params:
        p.grad = None

    # C. branch chunk 분할 (1개씩 vs 4개씩) 합 일치 (bf16 허용)
    flat = [(ei, b) for ei, ee in enumerate(exG) for b in ee["branches"]][:8]
    pv = torch.cat([ee["pixel_values"] for ee in exG], 0)

    def total(chunk):
        s = 0.0
        for c0 in range(0, len(flat), chunk):
            bb = cuda(AG.branch_batch(torch, None, pv, tok.pad_token_id, flat[c0:c0 + chunk]))
            with torch.no_grad():
                w, _, _ = AG.geo_forward(torch, model, bb, softcap)
            s += float(w)
        return s

    t1, t4, t8 = total(1), total(2), total(4)
    ok("C: branch microbatch 1/2/4 weighted sums agree (bf16 tol rel 1e-2)", abs(t1 - t4) / t1 <= 1e-2 and abs(t1 - t8) / t1 <= 1e-2, (t1, t4, t8))

    # D. 실제 branch로 gradient가 LoRA에 흐르고 GT prefix hidden을 detach하지 않는다 (branch 하나의 loss가 LoRA grad를 만든다)
    model.train()
    bb = cuda(AG.branch_batch(torch, None, pv, tok.pad_token_id, flat[:2]))
    for p in params:
        p.grad = None
    w, _, _ = AG.geo_forward(torch, model, bb, softcap)
    w.backward()
    gn = float(torch.sqrt(sum((p.grad.float() ** 2).sum() for p in params if p.grad is not None)))
    ok("D: branch-only loss produces finite non-zero LoRA gradient", np.isfinite(gn) and gn > 0, gn)
    model.eval()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"n": len(res), "n_pass": sum(r["pass"] for r in res), "results": res}, open(OUT, "w"), indent=1)
    print(f"{sum(r['pass'] for r in res)}/{len(res)} PASS")
    return 0 if all(r["pass"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
