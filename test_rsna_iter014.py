"""iter_014 CPU fixture: geo_loss(후보·q·span·branch·FP64 기준)와 실제 tokenizer/processor 연결. 결과: results/iter_014/tests/fixtures_iter014.json
허용 오차는 실행 전에 고정: FP64 손실/가중치 1e-12, FP32 toy gradient 상대 1e-5 (float64 기준 대비)."""
import json
import math
import os
import sys

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

from rsna_diag import coord_loss as CL, generate, geo_loss as GL, sft_data

OUT = "results/iter_014/tests/fixtures_iter014.json"
res = []


def ok(name, cond, detail=""):
    res.append({"name": name, "pass": bool(cond), "detail": str(detail)[:300]})
    print(("PASS " if cond else "FAIL ") + name, str(detail)[:120], flush=True)


def close(a, b, tol):
    return abs(a - b) <= tol


def main():
    import torch
    from transformers import AutoTokenizer, AutoProcessor
    tok = AutoTokenizer.from_pretrained("google/medgemma-1.5-4b-it", revision=generate.MODEL_REVISION)
    dig = CL.digit_ids(tok)
    # 1. GIoU
    ok("giou identical=1", close(GL.giou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0, 1e-12))
    ok("giou half overlap", close(GL.giou([0, 0, 10, 10], [0, 5, 10, 15]), 1 / 3, 1e-12),
       GL.giou([0, 0, 10, 10], [0, 5, 10, 15]))
    ok("giou disjoint negative & closed-form", close(GL.giou([0, 0, 10, 10], [0, 20, 10, 30]), 0 - (300 - 200) / 300, 1e-12), GL.giou([0, 0, 10, 10], [0, 20, 10, 30]))
    ok("giou symmetric", close(GL.giou([1, 2, 30, 40], [5, 6, 50, 60]), GL.giou([5, 6, 50, 60], [1, 2, 30, 40]), 1e-15))
    # 2. candidates
    gt_box = [100, 200, 400, 500]
    c1, n1 = GL.gen_candidates("p1", 0, gt_box)
    c2, n2 = GL.gen_candidates("p1", 0, gt_box)
    c3, _ = GL.gen_candidates("p1", 1, gt_box)
    ok("candidates deterministic", c1 == c2 and n1 == n2 and c1 != c3)
    ok("candidates valid/unique/GIoU>=0.3/!=GT/int grid", len(c1) == 4 and len({tuple(c) for c in c1}) == 4 and all(GL.giou(c, gt_box) >= 0.3 and c != gt_box and c[0] < c[2] and c[1] < c[3]
                                                                                                                     and all(isinstance(v, int) and 0 <= v <= 1000 for v in c) for c in c1))
    tiny, _ = GL.gen_candidates("p2", 0, [500, 500, 502, 503])
    ok("candidates for tiny box", len(tiny) == 4 and all(GL.giou(c, [500, 500, 502, 503]) >= 0.3 for c in tiny), tiny)
    edge, _ = GL.gen_candidates("p3", 0, [0, 0, 900, 1000])
    ok("candidates at image border clipped", all(0 <= v <= 1000 for c in edge for v in c))
    # 실패 gate: 후보가 부족한 경우 조용히 대체하지 않고 예외
    saved = GL.MAX_PROPOSALS
    GL.MAX_PROPOSALS = 5
    try:
        GL.gen_candidates("p4", 0, [10, 10, 11, 11])
        failed = False
    except GL.GeoError:
        failed = True
    GL.MAX_PROPOSALS = saved
    ok("insufficient candidates -> GeoError (no silent substitution)", failed)
    # yxyx round trip through target text + parser-independent json
    tgt = sft_data.target_text([[10, 200, 300, 999], [0, 9, 100, 1000], [40, 39, 99, 100]])
    rt = GL.replace_box_text(tgt, 1, [1, 2, 3, 4])
    js = json.loads(rt)
    ok("replace_box_text json round trip", js[1]["box_2d"] == [1, 2, 3, 4] and js[0] == json.loads(tgt)[0] and js[2] == json.loads(tgt)[2] and rt.count("box_2d") == 3, rt)
    # 3. q
    g = [0.3, 0.5, 0.8, 0.99]
    r = GL.r_weights(g)
    qg, qu, qc = GL.q_weights("G", g), GL.q_weights("U", g), GL.q_weights("C", g)
    ok("r closed form", all(close(r[i + 1], 1 + 0.5 * math.log(g[i]), 1e-15) for i in range(4)) and r[0] == 1.0 and all(v > 0 for v in r))
    ok("q sums to 1 (G,U,C)", all(close(sum(q), 1.0, 1e-12) for q in (qg, qu, qc)))
    ok("U and G share GT mass and total pseudo mass", close(qg[0], qu[0], 1e-15) and close(sum(qg[1:]), sum(qu[1:]), 1e-12) and close(qg[0], 1 / sum(r), 1e-15))
    ok("U pseudo uniform; G ordered by GIoU", len(set(round(v, 15) for v in qu[1:])) == 1 and qg[1] < qg[2] < qg[3] < qg[4])
    ok("C q0=1", qc == [1.0, 0, 0, 0, 0])
    try:
        GL.r_weights([0.1])
        bad = False
    except GL.GeoError:
        bad = True
    ok("weight <=0 rejected", bad)
    # 4. spans / boundary digits / 3 boxes / empty
    boxes = [[0, 9, 10, 39], [40, 99, 100, 999], [1, 2, 999, 1000]]
    text = sft_data.target_text(boxes)
    ids, sp = GL.box_token_spans(tok, text, dig)
    ok("3 boxes -> 3 spans", len(sp) == 3, sp)
    _, offs = GL.encode(tok, text)
    seg = [text[offs[ts][0]:offs[te][1]] for ts, te in sp]
    exp = ["".join(f" [{', '.join(map(str, b))}]," for b in [sft_data.target_boxes(boxes)[i]]) for i in range(3)]
    ok("span text = ' [a, b, c, d],' (space/comma straddle only)", seg == exp, seg)
    ok("empty response has no span", GL.box_token_spans(tok, "[]", dig)[1] == [])
    bts = [[0, 0, 9, 10], [10, 39, 40, 99], [100, 999, 101, 1000]]
    tb = sft_data.target_text(bts)
    _, sb = GL.box_token_spans(tok, tb, dig)
    ok("boundary values 0/9/10/39/40/99/100/999/1000 single-digit tokens", len(sb) == 3)
    # 5. branches
    cl = []
    for b, gb in enumerate(sft_data.target_boxes(boxes)):
        cs, _ = GL.gen_candidates("pt", b, gb)
        cl.append([GL.cand_record(gb, c) for c in cs])
    for mode in ("G", "U", "C"):
        bd = GL.build_branches(tok, text, dig, cl, mode)
        if mode == "C":
            ok("C: no branches, q0=1", bd["branches"] == [] and bd["q0"] == [1.0, 1.0, 1.0])
            continue
        allow = all(b["ids"][:bd["gt_spans"][b["box"]][0] + 1] == bd["gt_ids"][:bd["gt_spans"][b["box"]][0] + 1] for b in bd["branches"])
        ok(f"{mode}: 12 branches, GT prefix identical incl. opening bracket token", len(bd["branches"]) == 12 and allow)
        ok(f"{mode}: branch ends exactly at closing token (suffix dropped)", all(tok.decode([b["ids"][-1]]) == "]," for b in bd["branches"]))
        mass = {}
        for b in bd["branches"]:
            mass[b["box"]] = mass.get(b["box"], 0) + b["n_bm"] * b["w_per_token"]
        wgt = GL.gt_token_weights(len(bd["gt_ids"]), bd["gt_spans"], bd["q0"])
        tot = []
        for k, (ts, te) in enumerate(bd["gt_spans"]):
            tot.append(sum(wgt[ts:te + 1]) + mass[k])
        nb = [te - ts + 1 for ts, te in bd["gt_spans"]]
        ok(f"{mode}: per-box supervision mass = n_b (GT + candidates)", all(close(a, b_, 1e-12) for a, b_ in zip(tot, nb)), (tot, nb))
        outside = [t for t in range(len(bd["gt_ids"])) if not any(ts <= t <= te for ts, te in bd["gt_spans"])]
        ok(f"{mode}: tokens outside spans (keys/label/EOS) weight 1 exactly once", all(wgt[t] == 1.0 for t in outside) and len(outside) + sum(nb) == len(bd["gt_ids"]) and bd["gt_ids"][-1] == tok.convert_tokens_to_ids("<end_of_turn>"))
    # 6. FP64 reference loss & gradient on toy logits
    torch.manual_seed(0)
    V = 7
    bd = GL.build_branches(tok, text, dig, cl, "G")
    gt_len = len(bd["gt_ids"])
    lg_gt = torch.randn(gt_len, V, dtype=torch.float64, requires_grad=True)
    y_gt = torch.tensor([t % V for t in range(gt_len)])
    lg_br = [torch.randn(len(b["ids"]) - 0, V, dtype=torch.float64, requires_grad=True) for b in bd["branches"]]
    q = {(k, 0): bd["q0"][k] for k in range(3)}
    for b in bd["branches"]:
        q[(b["box"], b["m"])] = b["q"]

    def nll(lg, y):
        return torch.logsumexp(lg, -1) - lg.gather(1, y[:, None]).squeeze(1)

    nll_gt = nll(lg_gt, y_gt)
    nll_c = {}
    for b, lg in zip(bd["branches"], lg_br):
        yb = torch.tensor([t % V for t in range(len(b["ids"]))])
        nll_c[(b["box"], b["m"])] = nll(lg, yb)[b["span"][0]:b["span"][1] + 1]
    ref = GL.reference_loss(list(nll_gt), bd["gt_spans"], {k: list(v) for k, v in nll_c.items()}, q)
    # 구현식: token 가중 합
    wgt = torch.tensor(GL.gt_token_weights(gt_len, bd["gt_spans"], bd["q0"]), dtype=torch.float64)
    impl = (nll_gt * wgt).sum()
    for b in bd["branches"]:
        impl = impl + b["w_per_token"] * nll_c[(b["box"], b["m"])].sum()
    ok("FP64 weighted-token loss == reference formula", close(float(impl), float(ref), 1e-12), (float(impl), float(ref)))
    # 손으로 계산한 작은 사례로도 확인
    hand = 0.0
    inside = set()
    for ts, te in bd["gt_spans"]:
        inside.update(range(ts, te + 1))
    hand += sum(float(nll_gt[t]) for t in range(gt_len) if t not in inside)
    for k, (ts, te) in enumerate(bd["gt_spans"]):
        n_b = te - ts + 1
        hand += n_b * bd["q0"][k] * float(nll_gt[ts:te + 1].mean())
        for b in bd["branches"]:
            if b["box"] == k:
                hand += n_b * b["q"] * float(nll_c[(k, b["m"])].mean())
    ok("independent hand computation matches", close(float(impl), hand, 1e-12))
    # gradient: FP32 toy vs FP64 reference autograd
    impl.backward(retain_graph=True)
    g_impl = [lg_gt.grad.clone()] + [l.grad.clone() for l in lg_br]
    for l in [lg_gt] + lg_br:
        l.grad = None
    ref_t = 0.0
    inside_t = torch.tensor([t in inside for t in range(gt_len)])
    ref_t = nll_gt[~inside_t].sum()
    for k, (ts, te) in enumerate(bd["gt_spans"]):
        ref_t = ref_t + bd["q0"][k] * nll_gt[ts:te + 1].sum()
    for b in bd["branches"]:
        n_b = bd["gt_spans"][b["box"]][1] - bd["gt_spans"][b["box"]][0] + 1
        v = nll_c[(b["box"], b["m"])]
        ref_t = ref_t + n_b * b["q"] * v.mean()
    ref_t.backward()
    g_ref = [lg_gt.grad.clone()] + [l.grad.clone() for l in lg_br]
    err = max(float((a - b).abs().max()) for a, b in zip(g_impl, g_ref))
    ok("toy gradient == reference autograd (FP64 abs<=1e-12)", err <= 1e-12, err)
    # FP32 재계산
    l32 = [lg_gt.detach().float().requires_grad_()] + [l.detach().float().requires_grad_() for l in lg_br]
    n32 = nll(l32[0], y_gt)
    im32 = (n32 * wgt.float()).sum()
    for b, l in zip(bd["branches"], l32[1:]):
        yb = torch.tensor([t % V for t in range(len(b["ids"]))])
        im32 = im32 + b["w_per_token"] * nll(l, yb)[b["span"][0]:b["span"][1] + 1].sum()
    im32.backward()
    rel = max(float((a.grad.double() - b).abs().max() / (b.abs().max() + 1e-12)) for a, b in zip(l32, g_ref))
    ok("FP32 toy gradient rel<=1e-5 vs FP64 reference", rel <= 1e-5, rel)
    # C reduction: q0=1 & no branches -> plain CE
    bc = GL.build_branches(tok, text, dig, cl, "C")
    wc = torch.tensor(GL.gt_token_weights(gt_len, bc["gt_spans"], bc["q0"]), dtype=torch.float64)
    ok("C weights all 1 => equals plain CE sum", bool((wc == 1).all()) and float((nll_gt * wc).sum()) == float(nll_gt.sum()))
    # microbatch: 합의 분할 불변
    parts = [float(b["w_per_token"] * nll_c[(b["box"], b["m"])].sum()) for b in bd["branches"]]
    ok("branch-chunk accumulation == single sum", close(sum(parts[:5]) + sum(parts[5:]), sum(parts), 1e-12))
    # 7. 실제 processor 연결 (CPU): sanity16의 모든 환자
    proc = AutoProcessor.from_pretrained("google/medgemma-1.5-4b-it", revision=generate.MODEL_REVISION)
    from rsna_diag import inputs, prompts as P
    from rsna_diag.adapt_geo import GeoDataset
    items, gtm = inputs.load_items("results/iter_010/manifests/infer_manifest.jsonl", "results/iter_010/manifests/gt_manifest.json", "results/iter_013/subsets/sanity16_ids.json", "train", exact=False)
    cands = json.load(open("results/iter_014/candidates/train_candidates.json"))
    order = np.arange(len(items))
    nbr, okc, okfull, ntot = 0, True, True, 0
    for mode in ("G", "U", "C"):
        ds = GeoDataset(tok, proc, items, gtm, P.CONCISE, order, dig, mode, cands)
        for k in range(len(items)):
            e = ds[k]
            nb = len(gtm[items[k]["id"]]["boxes"])
            if len(e["branches"]) != (4 * nb if mode != "C" else 0):
                okc = False
            if mode == "G":
                ntot += 1
                for br in e["branches"][:2] + e["branches"][-1:]:
                    # 완전한 chat template으로 만든 후보 sequence의 앞부분 == 수동 구성 branch ids
                    boxes_i = sft_data.target_boxes([b["yxyx_norm"] for b in gtm[items[k]["id"]]["boxes"]])
                    ctext = GL.replace_box_text(sft_data.target_text([b["yxyx_norm"] for b in gtm[items[k]["id"]]["boxes"]]), br["box"], br["cand"])
                    img, _, _ = inputs.load_verified(items[k])
                    full = sft_data.build_example(proc, img, P.CONCISE, ctext)
                    if full["input_ids"].tolist()[:len(br["input_ids"])] != br["input_ids"].tolist():
                        okfull = False
                    if "token_type_ids" in full and full["token_type_ids"][:len(br["input_ids"])].tolist() != br["token_type_ids"].tolist():
                        okfull = False
                    del boxes_i
            if mode == "C":
                if not bool((e["tokw"] == 1).all()):
                    okc = False
    ok("sanity16: branch counts (4/box; C none) & C weights all 1", okc)
    ok("sanity16: manual branch ids/token_type_ids == full chat-template sequence prefix", okfull and ntot == 16)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"n": len(res), "n_pass": sum(r["pass"] for r in res), "results": res}, open(OUT, "w"), indent=1)
    print(f"{sum(r['pass'] for r in res)}/{len(res)} PASS")
    return 0 if all(r["pass"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
