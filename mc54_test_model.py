"""iter_054 모델 의존 기술 검사 (in-process, 출력은 새 파일).
 T1 공식 processor 직접 호출 vs apply_chat_template 경로의 input_ids·pixel_values·token_type_ids 동일, text-only에 image token/pixel 없음
 T2 PS: 독립 token-by-token(prefix+ans[:j] 별도 forward) log prob vs 구현(logits_to_keep) 평균/합, 답변 token 경계(joint tokenization), EOS 제외
 T3 GD: logits_to_keep=1 vs 전체 logits 마지막 위치, A/B 단일 token, logit 차이 = log-prob 차이
 T4 교환 순서 부호 복원 (순수) 및 질문에 답변 문자열이 이미 등장하는 fixture에서 PS 위치가 prompt 안의 첫 출현이 아닌 실제 답변 위치
 T5 MC 한 건 생성과 do_mc 비교 + 동일 입력 재실행 결정성
사용: CUDA_VISIBLE_DEVICES=<gpu> python mc54_test_model.py <out.json>"""
import json
import os
import sys

import mc54_run as RUN
import mc54_requests as R
import mc54_spec as S
from rsna_diag import generate as G


def main(outp):
    if os.path.exists(outp):
        sys.exit("exists")
    torch, proc, model = G.load_model()
    tk = proc.tokenizer
    rows = R.read_jsonl("results/iter_054/data/requests.jsonl")
    tech = [r for r in rows if r["stage"] == "tech"]
    ev = json.load(open("results/iter_054/data/eval_manifest.json"))
    res, checks = {}, []

    def chk(name, ok, **info):
        checks.append({"name": name, "pass": bool(ok), **info})
        print(("PASS" if ok else "FAIL"), name, info, flush=True)

    img_tok = getattr(model.config, "image_token_id", None) or getattr(model.config, "image_token_index", None)
    ab = [tk.encode(c, add_special_tokens=False) for c in ("A", "B")]
    chk("AB_single_tokens", all(len(x) == 1 for x in ab), ids=ab)
    ab_ids = [x[0] for x in ab]

    # ---- T1: 공식 processor 직접 호출 대조 ----
    sel_img = [r for r in tech if r["modality"] == "image" and r["kind"] == "gd"][:6]
    sel_txt = [r for r in tech if r["modality"] == "text" and r["kind"] == "gd"][:3]
    # 가장 큰 영상 포함
    big = json.load(open("results/iter_054/data/data_report.json"))["tech_extras"]["big_image_local"]
    big_row = [r for r in rows if r["kind"] == "gd" and r["modality"] == "image" and r["image"].endswith(f"/{big}.jpg")][:1]
    t1_ok, t1_info = True, []
    for r in sel_img + big_row:
        img, pxs = RUN.load_rgb(r["image"])
        inp = RUN.build_prefix(proc, r, img)
        text = RUN.prefix_string(proc, r)
        direct = proc(text=text, images=img, return_tensors="pt", add_special_tokens=False)
        same_ids = torch.equal(inp["input_ids"], direct["input_ids"])
        same_pv = torch.equal(inp["pixel_values"], direct["pixel_values"])
        same_tt = torch.equal(inp["token_type_ids"], direct["token_type_ids"]) if "token_type_ids" in inp and "token_type_ids" in direct else None
        n_img = int((inp["input_ids"][0] == img_tok).sum())
        # 영상 pixel이 processor 후 실제로 원본 RGB에서 유래: 직접 image_processor 호출과 일치
        ip = proc.image_processor(images=img, return_tensors="pt")
        same_ip = torch.equal(ip["pixel_values"], inp["pixel_values"])
        ok = same_ids and same_pv and (same_tt in (True, None)) and n_img == 256 and same_ip
        t1_ok &= ok
        t1_info.append({"image": r["image"], "mode": r["image_mode"], "pv_shape": list(inp["pixel_values"].shape), "n_img_tokens": n_img,
                        "ids": same_ids, "pv": same_pv, "tt": same_tt, "ip": same_ip})
    chk("T1_image_inputs_match_direct_processor", t1_ok, n=len(t1_info))
    res["T1_images"] = t1_info
    t1b_ok, t1b = True, []
    for r in sel_txt:
        inp = RUN.build_prefix(proc, r, None)
        text = RUN.prefix_string(proc, r)
        direct = proc(text=text, return_tensors="pt", add_special_tokens=False)
        n_img = int((inp["input_ids"][0] == img_tok).sum())
        ok = (torch.equal(inp["input_ids"], direct["input_ids"]) and "pixel_values" not in inp and n_img == 0
              and not any("pixel" in k or "image" in k for k in inp) and "<start_of_image>" not in text)
        t1b_ok &= ok
        t1b.append({"keys": sorted(inp.keys()), "n_img_tokens": n_img})
    chk("T1_text_only_no_image_token_or_pixels", t1b_ok, n=len(t1b))
    res["T1_text"] = t1b

    # ---- T2/T3: scoring 독립 대조 ----
    ps_rows = [r for r in tech if r["kind"] == "ps"]
    # 서로 다른 답변 길이를 포함하도록 길이 순 정렬해 앞/뒤에서 선택
    def n_ans(r):
        return len(tk.encode(r["assistant_text"], add_special_tokens=False))
    ps_sorted = sorted(ps_rows, key=n_ans)
    pick = [r for r in ps_sorted if r["modality"] == "image"][:2] + [r for r in ps_sorted if r["modality"] == "image"][-3:] + \
           [r for r in ps_sorted if r["modality"] == "text"][:1] + [r for r in ps_sorted if r["modality"] == "text"][-2:]
    maxdiff_mean, maxdiff_sum, t2 = 0.0, 0.0, []
    for r in pick:
        img = RUN.load_rgb(r["image"])[0] if r["modality"] == "image" else None
        inp = RUN.build_prefix(proc, r, img)
        pay = RUN.do_ps(torch, proc, model, inp, r)
        # 독립 계산: 각 j에 대해 prefix+ans[:j] 전체 forward → 마지막 위치 로그확률 (logits_to_keep 미사용)
        ans = pay["ans_ids"]
        ind, ind_nat = [], []
        for j in range(len(ans)):
            x = RUN.to_dev(torch, RUN.extend_inputs(torch, inp, ans[:j]) if j else inp)
            lg32 = RUN.last_logits(torch, model, x, 1)[0]
            ind.append(torch.log_softmax(lg32, dim=-1)[ans[j]].item())
            with torch.no_grad():
                out = model(**x, use_cache=False)
            ind_nat.append(torch.log_softmax(out.logits[0, -1].float(), dim=-1)[ans[j]].item())
        dm = abs(sum(ind) / len(ind) - pay["mean_ll"])
        ds = abs(sum(ind) - pay["sum_ll"])
        maxdiff_mean, maxdiff_sum = max(maxdiff_mean, dm), max(maxdiff_sum, ds)
        # EOS/turn 종료 token이 답변 token에 없음
        eos_free = not any(t in (tk.convert_tokens_to_ids("<end_of_turn>"), tk.eos_token_id) for t in ans)
        # 공식 chat template(assistant turn 포함)과 prefix+ans+<end_of_turn>\n 대조 (문자열 수준)
        content = ([{"type": "image"}] if r["modality"] == "image" else []) + [{"type": "text", "text": r["prompt"]}]
        full = proc.apply_chat_template([{"role": "user", "content": content},
                                         {"role": "assistant", "content": [{"type": "text", "text": r["assistant_text"]}]}], tokenize=False)
        str_ok = full == RUN.prefix_string(proc, r) + r["assistant_text"] + "<end_of_turn>\n"
        t2.append({"cond": r["cond"], "n_ans": len(ans), "mean_diff": dm, "sum_diff": ds, "eos_free": eos_free, "template_string_ok": str_ok,
                   "boundary_ok": pay["boundary_ok"], "mean_ll": pay["mean_ll"], "mean_ll_independent": sum(ind) / len(ind),
                   "native_bf16_independent_mean": sum(ind_nat) / len(ind_nat), "native_vs_fp32_mean_diff": abs(sum(ind_nat) / len(ind_nat) - pay["mean_ll"])})
    chk("T2_ps_vs_token_by_token", maxdiff_mean < 2e-2 and max(x["native_vs_fp32_mean_diff"] for x in t2) < 0.15 and all(x["eos_free"] and x["template_string_ok"] and x["boundary_ok"] for x in t2),
        n=len(t2), max_mean_diff=maxdiff_mean, max_sum_diff=maxdiff_sum, tol="fp32-head independent mean diff<2e-2 nats; vs native bf16 logits <0.15 nats")
    res["T2"] = t2
    # PS 위치: 질문에 답변 문자열이 등장하는 fixture — 공식 token 검색 방식은 마지막 출현을 쓰지만 우리는 prefix 길이로 위치를 정한다
    fx_row = dict(ps_rows[0])
    fx_row["prompt"] = f"{fx_row['assistant_text']}\n{fx_row['prompt']}\n{fx_row['assistant_text']}"
    fx_row["modality"] = "text"
    fx_row["image"] = None
    inp = RUN.build_prefix(proc, fx_row, None)
    pay = RUN.do_ps(torch, proc, model, inp, fx_row)
    ans = pay["ans_ids"]
    ids_in = inp["input_ids"][0].tolist()
    n_occ = sum(ids_in[i:i + len(ans)] == ans for i in range(len(ids_in) - len(ans) + 1))
    x = RUN.to_dev(torch, RUN.extend_inputs(torch, inp, ans))
    L = inp["input_ids"].shape[1]
    ref = []
    for j in range(len(ans)):  # 실제 답변 위치 L+j 를 예측하는 위치 L-1+j 의 전체 시퀀스 fp32 logits
        lg_full = RUN.head_fp32(model, RUN.hidden_last(model, x, len(ans) + 1 - j)[:1])
        ref.append(torch.log_softmax(lg_full[0], -1)[ans[j]].item())
    chk("T4_answer_text_inside_question_fixture", n_occ >= 2 and max(abs(a - b) for a, b in zip(ref, pay["token_logps"])) < 5e-2,
        occurrences_in_prompt=n_occ, max_diff=max(abs(a - b) for a, b in zip(ref, pay["token_logps"])))
    # GD
    gd_rows = [r for r in tech if r["kind"] == "gd"][:6] + [r for r in tech if r["kind"] == "gd" and r["modality"] == "text"][:2]
    t3, gdmax, gd_q = [], 0.0, 0.0
    for r in gd_rows:
        img = RUN.load_rgb(r["image"])[0] if r["modality"] == "image" else None
        inp = RUN.build_prefix(proc, r, img)
        pay = RUN.do_gd(torch, proc, model, inp, ab_ids)
        x = RUN.to_dev(torch, inp)
        with torch.no_grad():
            fl = model(**x, use_cache=False).logits[0, -1].float()  # 모델 native bf16 전체 forward
        nat_margin = (fl[ab_ids[0]] - fl[ab_ids[1]]).item()
        d1 = abs(nat_margin - pay["native_bf16_shown_margin"])
        d2 = abs(pay["shown_margin"] - pay["native_bf16_shown_margin"])  # fp32 head vs bf16 head: bf16 양자화 범위
        d3 = abs((pay["logp_A"] - pay["logp_B"]) - pay["shown_margin"])
        gdmax = max(gdmax, d1, d3)
        gd_q = max(gd_q, d2)
        t3.append({"cond": r["cond"], "native_margin_vs_full_forward": d1, "fp32_vs_bf16_margin_diff": d2, "logp_margin_consistency": d3,
                   "argmax_token": tk.decode([pay["argmax_id"]]), "top5": [tk.decode([i]) for i in pay["top5_ids"]]})
    chk("T3_gd_last_position_vs_full_logits", gdmax < 5e-2 and gd_q < 0.5, max_diff=gdmax, max_fp32_vs_bf16_margin=gd_q)
    res["T3"] = t3
    # T4b 교환 부호 (순수 함수)
    chk("T4_swap_sign_pure", S.canonical_margin(1.5, "swap") == -1.5 and S.canonical_margin(1.5, "orig") == 1.5 and
        S.to_canonical_letter("A", "swap") == "B" and S.to_canonical_letter("-", "swap") == "-")
    # MC 결정성·재시도 구조
    mc_rows = [r for r in tech if r["kind"] == "mc"][:4]
    t5 = []
    eos = G.env_info(torch, proc, model)["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    for r in mc_rows:
        img = RUN.load_rgb(r["image"])[0] if r["modality"] == "image" else None
        inp = RUN.build_prefix(proc, r, img)
        p1 = RUN.do_mc(torch, proc, model, inp, eos_ids, r["caps"])
        p2 = RUN.do_mc(torch, proc, model, inp, eos_ids, r["caps"])
        t5.append({"cond": r["cond"], "text": p1["suffix_text_raw"], "n_tok": p1["n_output_tokens"], "eos": p1["ended_eos"],
                   "deterministic": p1["suffix_ids"] == p2["suffix_ids"], "strict": S.parse_strict(p1["suffix_text_raw"]),
                   "official": S.parse_official_manual(p1["suffix_text_raw"])})
    chk("T5_mc_deterministic_and_terminates", all(x["deterministic"] and x["eos"] for x in t5), n=len(t5))
    res["T5"] = t5
    # PS 전체 tech 요청의 boundary (tokenizer만)
    bad = 0
    for r in rows:
        if r["kind"] != "ps":
            continue
        pre = RUN.prefix_string(proc, r)
        a_ids = tk.encode(r["assistant_text"], add_special_tokens=False)
        bad += tk.encode(pre + r["assistant_text"], add_special_tokens=False) != tk.encode(pre, add_special_tokens=False) + a_ids
    chk("T2_ps_boundary_all_requests", bad == 0, n_ps_rows=sum(r["kind"] == "ps" for r in rows), n_bad=bad)
    out = {"checks": checks, "all_pass": all(c["pass"] for c in checks), "details": res,
           "env": {"cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")}}
    json.dump(out, open(outp, "x"), indent=1, default=str)
    print("all_pass", out["all_pass"])


if __name__ == "__main__":
    main(sys.argv[1])
