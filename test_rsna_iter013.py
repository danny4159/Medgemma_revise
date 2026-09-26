"""iter_013 CPU 검사 (MedGemma 로드 없음, processor/tokenizer만). 실행: python test_rsna_iter013.py -> results/iter_013/tests/fixtures_iter013.json

1 좌표 span/token 연결 (실제 학습 target 3,600개 전부, 경계값, 빈 목록, 복수 box, key의 '2'·label 숫자 미포함)
2 loss 수식: 독립 float64 numpy 기준 대조 (C/H/D), 지정 위치 외 gradient 0, alpha=0 == 기존 CE gradient, microbatch 분할 불변, 빈 E, p==q에서 KL=0
3 다음-token shift·padding: mock 모델 + 실제 chat sequence 기반 label 위치
4 학습 일정·subset·입력 provenance (파일/픽셀 hash, 환자·pixel 교집합 0, parent adapter digest)
5 B0 V400 응답 재사용 검증, S_loc 독립 재계산, guardrail/selection/확대 기준/paired bootstrap
"""
import hashlib
import itertools
import json
import math
import os
import sys

import numpy as np

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch  # noqa: E402

from rsna_diag import adapt, adapt_eval, coord_loss as CL, generate, inputs, lora, metrics as M, sft_data, sft_eval  # noqa: E402

PROT = "results/iter_013/protocols/pilot_protocol.json"
OUT = "results/iter_013/tests"
R = {}


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, "" if cond else json.dumps(detail, default=str)[:500], flush=True)


def ref_losses(logits, y, w, dig, alpha=0.1, tau=1.0):
    """독립 float64 기준 (python 루프)."""
    lg = np.asarray(logits, dtype=np.float64)
    ce = h = d = 0.0
    for t in range(len(y)):
        lse = np.log(np.exp(lg[t] - lg[t].max()).sum()) + lg[t].max()
        c = lse - lg[t, y[t]]
        ce += c
        if w[t] > 0:
            h += w[t] * c
            g = dig.index(int(y[t]))
            q = np.array([math.exp(-((v - g) ** 2) / tau) for v in range(10)])
            q /= q.sum()
            lp = np.array([lg[t, dig[v]] - lse for v in range(10)])
            d += w[t] * float((q * (np.log(q) - lp)).sum())
    return ce, h, d


def brute_f1(pred, gt, thr):
    best = 0
    for k in range(min(len(pred), len(gt)) + 1):
        for gs in itertools.combinations(range(len(gt)), k):
            for ps in itertools.permutations(range(len(pred)), k):
                if all(M.iou(pred[p], gt[g]) >= thr for g, p in zip(gs, ps)):
                    best = max(best, k)
    tp = best
    pr = tp / len(pred) if pred else 0.0
    rc = tp / len(gt) if gt else 0.0
    return 2 * pr * rc / (pr + rc) if pr + rc else 0.0


def main():
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(generate.MODEL_ID, revision=generate.MODEL_REVISION)
    tok = proc.tokenizer
    dig = CL.digit_ids(tok)
    gt = json.load(open("results/iter_010/manifests/gt_manifest.json"))
    man = inputs.load_manifest("results/iter_010/manifests/infer_manifest.jsonl")
    check("1.digit_token_ids_equal_plan", dig == CL.PLAN_DIGIT_IDS, dig)

    # 1. span/token
    n_t = n_c = 0
    bad = None
    for s in ("train", "validation", "confirm"):
        for i in json.load(open(f"results/iter_010/manifests/{s}_ids.json")):
            t = sft_data.target_text([b["yxyx_norm"] for b in gt[i]["boxes"]])
            ids = tok(t + "<end_of_turn>", add_special_tokens=False)["input_ids"]
            try:
                w = CL.coord_weights(tok, t, [1, 2, 3] + ids + [107], 3, dig)
            except Exception as e:  # noqa
                bad = (i, str(e)[:200])
                break
            want = sum(len(str(v)) for b in sft_data.target_boxes([x["yxyx_norm"] for x in gt[i]["boxes"]]) for v in b)
            if sum(1 for x in w if x > 0) != want:
                bad = (i, "coord token count", sum(1 for x in w if x > 0), want)
                break
            n_t += 1
            n_c += want
        if bad:
            break
    check("1.all_targets_single_digit_tokens", bad is None and n_t == 3600, {"targets": n_t, "coord_tokens": n_c, "bad": bad})

    def weights_for(target):
        ids = tok(target + "<end_of_turn>", add_special_tokens=False)["input_ids"]
        w = CL.coord_weights(tok, target, [1] + ids + [107], 1, dig)
        return ids, w[1:1 + len(ids)]

    tgt = json.dumps([{"box_2d": [0, 9, 10, 39], "label": "pulmonary opacity"}, {"box_2d": [40, 99, 100, 999], "label": "pulmonary opacity"},
                      {"box_2d": [1000, 1, 2, 3], "label": "x2 3"}])
    ids, w = weights_for(tgt)
    pos = [(tok.decode([ids[k]]), w[k]) for k in range(len(ids)) if w[k] > 0]
    exp = []
    for v in (0, 9, 10, 39, 40, 99, 100, 999, 1000, 1, 2, 3):
        exp += [(c, float(len(str(v)) - j)) for j, c in enumerate(str(v))]
    check("1.boundary_values_and_place_weights", pos == exp, {"got": pos[:12], "exp": exp[:12]})
    check("1.key2_label_digits_excluded", len(pos) == len(exp), len(pos))
    ids0, w0 = weights_for("[]")
    check("1.empty_list_no_coord", sum(w0) == 0)
    tail = [k for k in range(len(ids)) if w[k] == 0 and tok.decode([ids[k]]).strip() in tuple("0123456789")]
    check("1.non_coordinate_digit_tokens_have_zero_weight", len(tail) >= 1, {"n": len(tail), "tokens": [tok.decode([ids[k]]) for k in tail][:6]})
    # span 값 일치 검사가 실제로 동작하는지 (변조 target)
    try:
        CL.coord_weights(tok, tgt.replace("999", "998"), [1] + tok(tgt + "<end_of_turn>", add_special_tokens=False)["input_ids"] + [107], 1, dig)
        ok = False
    except CL.SpanError:
        ok = True
    check("1.mismatched_sequence_rejected", ok)

    # 실제 chat sequence 기반 (build_example): 3개 영상
    real_ok, det = True, []
    for i in ("tra_00000009",):
        pass
    tr = json.load(open("results/iter_013/subsets/sanity16_ids.json"))
    for i in tr[:4]:
        it = man[i]
        image, _, _ = inputs.load_verified(it)
        t = sft_data.target_text([b["yxyx_norm"] for b in gt[i]["boxes"]])
        ex = sft_data.build_example(proc, image, generate.P.CONCISE if hasattr(generate, "P") else __import__("rsna_diag.prompts", fromlist=["x"]).CONCISE, t)
        w = CL.coord_weights(tok, t, ex["input_ids"].tolist(), ex["n_prefix"], dig)
        wt = torch.tensor(w)
        lab = ex["labels"]
        cpos = (wt > 0).nonzero().flatten().tolist()
        digs = "".join(tok.decode([int(ex["input_ids"][p])]) for p in cpos)
        flat = "".join(str(v) for b in sft_data.target_boxes([x["yxyx_norm"] for x in gt[i]["boxes"]]) for v in b)
        ok = digs == flat and all(int(lab[p]) != -100 for p in cpos) and all(int(lab[p]) in dig for p in cpos)
        ok = ok and float(wt[: ex["n_prefix"]].sum()) == 0 and float(wt[-3:].sum()) == 0
        real_ok &= ok
        det.append((i, digs, flat))
    check("1.real_chat_sequence_positions_match", real_ok, det)

    # 2. loss
    g = torch.Generator().manual_seed(0)
    V, Mn = 40, 12
    dig_s = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]  # 작은 vocabulary용 숫자 id
    logits = torch.randn(Mn, V, generator=g, dtype=torch.float64) * 2
    y = torch.tensor([5, 9, 14, 3, 20, 7, 12, 30, 6, 6, 13, 8])
    w = torch.tensor([1., 2., 3., 0, 0, 4., 1., 0, 2., 0, 1., 3.], dtype=torch.float64)
    is_dig = torch.tensor([t in dig_s for t in y.tolist()])
    check("2.fixture_weights_only_on_digits", bool((is_dig | (w == 0)).all()))
    rc, rh, rd = ref_losses(logits.numpy(), y.numpy(), w.numpy(), dig_s)
    l32 = logits.float()
    for mode, refx in (("C", 0.0), ("H", rh), ("D", rd)):
        ce, ex = CL.loss_sums(torch, l32, y, w.float(), mode, dig_s)
        check(f"2.{mode}_matches_float64_reference", abs(float(ce) - rc) < 1e-4 * max(1, rc) and abs(float(ex) - refx) < 1e-4 * max(1, abs(refx)),
              (float(ce), rc, float(ex), refx))
    # gradient: 추가 항은 좌표 위치 행에만, digit 열/전체 vocabulary 정규화 경유
    for mode in ("H", "D"):
        lg = l32.clone().requires_grad_(True)
        CL.loss_sums(torch, lg, y, w.float(), mode, dig_s)[1].backward()
        nz = (lg.grad.abs().sum(1) > 0).tolist()
        check(f"2.{mode}_extra_gradient_only_on_coordinate_rows", nz == (w > 0).tolist(), nz)
    lg = l32.clone().requires_grad_(True)
    CL.loss_sums(torch, lg, y, w.float(), "C", dig_s)[0].backward()
    g_ref = torch.autograd.grad(torch.nn.functional.cross_entropy(l32.clone().requires_grad_(True), y, reduction="sum"), [])[0] if False else None
    lg2 = l32.clone().requires_grad_(True)
    torch.nn.functional.cross_entropy(lg2, y, reduction="sum").backward()
    check("2.alpha0_gradient_equals_plain_CE", torch.allclose(lg.grad, lg2.grad, atol=1e-6))
    for mode in ("H", "D"):
        lg = l32.clone().requires_grad_(True)
        ce, ex = CL.loss_sums(torch, lg, y, w.float(), mode, dig_s)
        (ce + 0.0 * ex).backward()
        check(f"2.{mode}_alpha0_gradient_equals_plain_CE", torch.allclose(lg.grad, lg2.grad, atol=1e-6))
    ce, ex = CL.loss_sums(torch, l32, y, torch.zeros(Mn), "D", dig_s)
    check("2.empty_E_extra_zero", float(ex) == 0.0)
    # p == q: 숫자 밖 질량 0, 숫자 확률 = q 이면 KL = 0
    gd = 3
    q = np.array([math.exp(-((v - gd) ** 2)) for v in range(10)])
    q /= q.sum()
    lgt = torch.full((1, V), -1e4, dtype=torch.float32)
    for v in range(10):
        lgt[0, dig_s[v]] = float(np.log(q[v]))
    ce, ex = CL.loss_sums(torch, lgt, torch.tensor([dig_s[gd]]), torch.tensor([1.0]), "D", dig_s)
    check("2.D_zero_when_p_equals_q", abs(float(ex)) < 1e-5, float(ex))
    # p 재정규화 금지: 비숫자 질량이 크면 KL이 커야 한다 (숫자 10개로 재정규화하면 0에 가깝다)
    lgt2 = lgt.clone()
    lgt2[0, 0] = float(np.log(4.0))  # 비숫자 token에 큰 질량
    ce2, ex2 = CL.loss_sums(torch, lgt2, torch.tensor([dig_s[gd]]), torch.tensor([1.0]), "D", dig_s)
    check("2.D_not_renormalized_over_digits", float(ex2) > 1.0 and abs(float(ex2) - math.log(5.0)) < 1e-3, float(ex2))
    # 39<->40: 자리별 loss는 올림·내림을 표현하지 않음 (명시): 4,0 vs 3,9 의 십의 자리/일의 자리 q가 서로 0/9 를 멀리 봄
    check("2.carry_limitation_documented", True, "0/9 distance is 9 (digit-wise); 39<->40 relation (adjacent integers) is not represented")

    # microbatch 분할 불변: (합/N) 선형
    N = Mn
    parts = [CL.loss_sums(torch, l32[a:b], y[a:b], w.float()[a:b], "D", dig_s) for a, b in ((0, 5), (5, 12))]
    whole = CL.loss_sums(torch, l32, y, w.float(), "D", dig_s)
    check("2.microbatch_split_sums_equal_whole", abs(sum(float(p[0]) for p in parts) - float(whole[0])) < 1e-4 and abs(sum(float(p[1]) for p in parts) - float(whole[1])) < 1e-4)

    # 3. shift/padding: mock 모델 (hidden[t] = onehot(input_ids[t+1]) -> logits[t]가 다음 token을 예측)
    class Out:
        pass

    class Inner(torch.nn.Module):
        def __init__(self, uniq):
            super().__init__()
            self.uniq = uniq

        def forward(self, input_ids, attention_mask=None, pixel_values=None, token_type_ids=None, use_cache=False):
            o = Out()
            nxt = torch.roll(input_ids, -1, 1)
            o.last_hidden_state = torch.nn.functional.one_hot(torch.searchsorted(self.uniq, nxt), len(self.uniq)).float() * 30
            return o

    class Cfg:
        def get_text_config(self):
            class T_:
                final_logit_softcapping = None
            return T_()

    class Mock:
        config = Cfg()

        def __init__(self, V, ids):
            uniq = torch.unique(ids)
            self.model = Inner(uniq)
            W = torch.zeros(V, len(uniq))
            W[uniq, torch.arange(len(uniq))] = 1.0
            self.lm_head = torch.nn.Linear(len(uniq), V, bias=False)
            self.lm_head.weight.data = W

    Vv = 262208
    exs = []
    for i in json.load(open("results/iter_013/subsets/sanity16_ids.json"))[:3]:
        it = man[i]
        image, _, _ = inputs.load_verified(it)
        t = sft_data.target_text([b["yxyx_norm"] for b in gt[i]["boxes"]])
        e = sft_data.build_example(proc, image, __import__("rsna_diag.prompts", fromlist=["x"]).CONCISE, t)
        e["coord_w"] = CL.coord_weights(tok, t, e["input_ids"].tolist(), e["n_prefix"], dig)
        e["sample_pos"] = 0
        exs.append(e)
    b = adapt.collate(exs, tok.pad_token_id)
    b.pop("sample_pos")
    mock = Mock(Vv, b["input_ids"])
    b_cuda = b  # CPU
    r = adapt.adapt_loss(torch, mock, {k: v for k, v in b_cuda.items()}, None, "D", dig, 0.1, 1.0)
    n_lab = int((b["labels"][:, 1:] != -100).sum())
    n_coord = int((b["coord_w"] > 0).sum())
    check("3.shift_aligned_ce_near_zero", float(r["ce_sum"]) / n_lab < 1e-3 and r["n_tok"] == n_lab, (float(r["ce_sum"]), n_lab))
    check("3.coord_count_and_padding", r["n_coord"] == n_coord and n_coord > 0 and float(b["coord_w"][b["attention_mask"] == 0].sum()) == 0
          and b["input_ids"].shape[0] == 3, (r["n_coord"], n_coord))
    check("3.extra_D_positive_but_finite_on_sharp_p", 0 < float(r["extra_sum"]) < 1e6, float(r["extra_sum"]))
    # 잘못된 shift(위치 한 칸 어긋난 label)이면 CE가 커야 한다 -> 검사가 shift에 민감함을 확인
    bb = dict(b)
    bb["labels"] = torch.roll(b["labels"], 1, 1)
    try:
        r_bad = adapt.adapt_loss(torch, mock, bb, None, "C", dig, 0.1, 1.0)
        sens = float(r_bad["ce_sum"]) / max(1, r_bad["n_tok"]) > 1.0
        det_s = float(r_bad["ce_sum"]) / max(1, r_bad["n_tok"])
    except CL.SpanError as e:  # label 위치와 좌표 weight가 어긋나면 digit guard가 먼저 거부한다
        sens, det_s = True, "rejected by digit guard: " + str(e)
    check("3.shift_sensitivity_of_check", sens, det_s)
    # aux metadata가 모델 forward로 가지 않는지 (Inner.forward는 알 수 없는 인자 coord_w를 받으면 TypeError)
    check("3.aux_metadata_not_passed_to_model", True, "Inner.forward has no **kwargs; adapt_loss ran with coord_w in batch")

    # 4. 일정·subset·provenance
    lrs = [adapt.lr_at(s, 225, 2e-5, 0.05) for s in range(225)]
    check("4.lr_schedule_warmup12_cosine_to_0", abs(lrs[0] - 2e-5 / 12) < 1e-12 and abs(lrs[11] - 2e-5) < 1e-12 and lrs[-1] < 2e-5 * 1e-3
          and all(lrs[k] >= lrs[k + 1] for k in range(11, 224)), [lrs[0], lrs[11], lrs[12], lrs[-1]])
    S = "results/iter_013/subsets/"
    tr_ids = json.load(open("results/iter_010/manifests/train_ids.json"))
    va_ids = json.load(open("results/iter_010/manifests/validation_ids.json"))
    cf_ids = json.load(open("results/iter_010/manifests/confirm_ids.json"))
    t1200, v200 = json.load(open(S + "train1200_ids.json")), json.load(open(S + "v200_ids.json"))
    cat = lambda ids, c: sum(gt[i]["category"] == c for i in ids)
    check("4.subset_sizes_categories_disjoint", len(t1200) == 1200 and len(set(t1200)) == 1200 and set(t1200) <= set(tr_ids) and len(v200) == 200
          and set(v200) <= set(va_ids) and not set(t1200) & set(v200) and (cat(t1200, "opacity"), cat(t1200, "normal"), cat(t1200, "not_normal_no_opacity")) == (600, 300, 300)
          and (cat(v200, "opacity"), cat(v200, "normal"), cat(v200, "not_normal_no_opacity")) == (100, 50, 50))
    pat = lambda ids: {gt[i]["patient"] for i in ids}
    pxl = lambda ids: {gt[i]["pixel_sha256"] for i in ids}
    check("4.patient_pixel_overlap_zero_train_val_confirm", not (pat(tr_ids) & pat(va_ids) | pat(tr_ids) & pat(cf_ids) | pat(va_ids) & pat(cf_ids))
          and not (pxl(tr_ids) & pxl(va_ids) | pxl(tr_ids) & pxl(cf_ids) | pxl(va_ids) & pxl(cf_ids)))
    rep = json.load(open(S + "subsets_report.json"))
    check("4.subset_files_match_report_sha", all(hashlib.sha256(open(S + f"{k}_ids.json", "rb").read()).hexdigest() == v for k, v in rep["sha256"].items()))
    for name in ("explore", "sanity", "full_s17"):
        st = json.load(open(f"results/iter_013/stage/{name}.json"))
        b = torch.load(st["parent_adapter"], map_location="cpu", weights_only=True)
        check(f"4.stage_{name}_parent_adapter_sha_digest", hashlib.sha256(open(st["parent_adapter"], "rb").read()).hexdigest() == st["parent_adapter_sha256"]
              and lora.state_digest(b["state"]) == st["parent_adapter_digest"] == b["digest"])
    tt = inputs.inputs_digest(inputs.load_items(adapt.T.MANIFEST, adapt.T.GT, S + "train1200_ids.json", "train", exact=False)[0], gt)
    tv = inputs.inputs_digest(inputs.load_items(adapt.T.MANIFEST, adapt.T.GT, S + "v200_ids.json", "validation", exact=False)[0], gt)
    check("4.current_file_pixel_hashes_match_manifest_train1200_v200", bool(tt) and bool(tv), {"train1200": tt[:12], "v200": tv[:12]})

    # 5. B0 재사용과 평가
    vi, _ = adapt_eval.load_ids_items(adapt_eval.V400_IDS)
    recs = adapt_eval.b0_records(PROT, vi)
    ids = [i["id"] for i in vi]
    check("5.b0_v400_requests_verified", len(recs) == 400 and all(k[1] == "concise" for k in recs), len(recs))
    preds = adapt_eval.preds_of(recs, ids)
    aed = sft_eval.area_edges(gt, [i for i in gt if gt[i]["split"] == "train"])
    bed = adapt_eval.box_edges_train(gt, [i for i in gt if gt[i]["split"] == "train"])
    d = adapt_eval.detail(preds, gt, ids, aed, bed)
    old = json.load(open("results/iter_012/train/lr2e-4_s17/epoch_05/val_metrics.json"))
    check("5.b0_recomputed_matches_stored_iter012_scores", abs(d["f1@0.3"] - old["f1@0.3"]) < 1e-12 and abs(d["f1@0.5"] - old["f1@0.5"]) < 1e-12, (d["f1@0.3"], old["f1@0.3"], d["f1@0.5"], old["f1@0.5"]))
    ind = []
    for i in ids:
        if gt[i]["category"] != "opacity":
            continue
        pb = preds[i]["boxes"] if preds[i]["status"] in ("valid_empty", "valid_nonempty") else []
        gg = [b["yxyx_norm"] for b in gt[i]["boxes"]]
        ind.append((brute_f1(pb, gg, 0.3) + brute_f1(pb, gg, 0.5)) / 2)
    check("5.S_loc_independent_bruteforce_matching", abs(float(np.mean(ind)) - d["S_loc"]) < 1e-12, (float(np.mean(ind)), d["S_loc"]))
    v200_ids = json.load(open(S + "v200_ids.json"))
    p200 = {i: preds[i] for i in v200_ids}
    d200 = adapt_eval.detail(p200, gt, v200_ids, aed, bed)
    check("5.b0_v200_subset_scored", d200["n_patients"] == 200 and d200["n_positive"] == 100, d200["S_loc"])
    # guardrail / selection
    b0s = d
    ok_c = json.loads(json.dumps(b0s))
    bad_c = json.loads(json.dumps(b0s))
    bad_c["neg_Normal"]["valid_empty"]["rate"] = b0s["neg_Normal"]["valid_empty"]["rate"] - 0.04
    bad_c["S_loc"] = 0.9
    low_v = json.loads(json.dumps(b0s))
    low_v["valid_rate_all"]["rate"] = 0.98
    low_v["S_loc"] = 0.95
    ok_c["S_loc"] = 0.6
    ok_c2 = json.loads(json.dumps(ok_c))
    sel, tab = adapt_eval.select_checkpoint({75: ok_c, 150: ok_c2, 225: bad_c}, b0s)
    check("5.selection_tie_earlier_and_guardrail_excludes", sel == 75 and not tab[225]["guardrail"]["ok"], tab)
    sel2, _ = adapt_eval.select_checkpoint({75: bad_c, 150: low_v}, b0s)
    check("5.no_eligible_returns_none", sel2 is None)
    ci = {"ci95": [0.0, 0.05]}
    check("5.expand_rule_cases", adapt_eval.expand_rule(0.53, 0.50, ci, 0.0, True)[0] and adapt_eval.expand_rule(0.51, 0.50, ci, 0.02, True)[0]
          and not adapt_eval.expand_rule(0.51, 0.50, ci, 0.0, True)[0] and not adapt_eval.expand_rule(0.60, 0.50, ci, 0.05, False)[0]
          and not adapt_eval.expand_rule(0.51, 0.50, {"ci95": [0, 0.02]}, 0.05, True)[0])
    c1 = adapt_eval.paired_ci(preds, preds, gt, ids)
    check("5.paired_bootstrap_identical_is_zero_and_deterministic", c1["diff"] == 0 and c1["ci95"] == [0.0, 0.0] and c1["B"] == 10000
          and adapt_eval.paired_ci(preds, preds, gt, ids) == c1)
    json.dump(R, open(os.path.join(OUT, "fixtures_iter013.json"), "w"), indent=1, default=str)
    n_pass = sum(v["pass"] for v in R.values())
    print(f"{n_pass}/{len(R)} PASS")
    sys.exit(0 if n_pass == len(R) else 1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    main()
