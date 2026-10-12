"""iter_112 동작 확인(기술 집단 앞 3명): scoring의 shift/mask를 공식 forward(labels) 경로와 독립 대조, 생성 첫 token과 logits argmax 대조,
결정성, ViT feature 캐시 동치, 영상 대체 민감도, 이미지/프롬프트 token이 평균에서 제외되는지. GT 미사용."""
import hashlib
import json
import time

import torch

import mr112_model as MM
import mr112_spec as S


@torch.no_grad()
def run_checks(model, tok, man, out_path):
    rows = {r["id"]: r for r in man["rows"]}
    reg = [q for q in man["requests"] if q["group"] == "tech" and q["kind"] == "region"][:3]
    full = {q["id"]: q for q in man["requests"] if q["group"] == "tech" and q["kind"] == "full"}
    res = []

    def chk(name, ok, info=""):
        res.append(dict(name=name, ok=bool(ok), info=str(info)))
        print("PASS" if ok else "FAIL", name, info, flush=True)

    pvs = {q["id"]: MM.load_image(rows[q["id"]]["image"]) for q in reg}
    for q in reg:
        pid = q["id"]
        pv = pvs[pid]
        vit = MM.vit_features(model, pv)
        chk(f"{pid} image token 수", vit.shape[1] == model.num_image_token == 256, tuple(vit.shape))
        s1 = MM.score(model, tok, q["prompt"], vit)
        s2 = MM.score(model, tok, q["prompt"], MM.vit_features(model, pv))  # 캐시 없이 재계산
        chk(f"{pid} 결정성/ViT 재계산 동치", s1["token_logprobs"] == s2["token_logprobs"], (s1["mean_logprob"], s2["mean_logprob"]))
        # 공식 forward(labels) 경로: prompt 위치를 -100으로 마스크 -> loss = -mean(target token logprob)
        query = MM.build_query(model, tok, q["prompt"])
        full_ids, n, ok = MM.target_split(tok, query, S.TARGET)
        chk(f"{pid} tokenization prefix 경계", ok, tok.convert_ids_to_tokens(full_ids[0, n:]))
        labels = full_ids.clone()
        labels[:, :n] = -100
        dev = model.language_model.get_input_embeddings().weight.device
        out = model(pixel_values=pv.to(next(model.vision_model.parameters()).device, torch.bfloat16), input_ids=full_ids.to(dev),
                    attention_mask=torch.ones_like(full_ids).to(dev), image_flags=torch.ones(1, 1, dtype=torch.long),
                    labels=labels.to(dev), use_cache=False, return_dict=True)
        off = -float(out.loss)
        chk(f"{pid} 공식 forward CE vs 평균 logprob", abs(off - s1["mean_logprob"]) < 5e-3, (off, s1["mean_logprob"]))
        # 첫 target token: 수동 shift 계산과 대조 (logits[n-1] -> target[0])
        lg = MM.forward_logits(model, full_ids, vit)
        manual = float(torch.log_softmax(lg[0, n - 1].float(), -1)[full_ids[0, n]])
        chk(f"{pid} 수동 첫 token logprob", abs(manual - s1["token_logprobs"][0]) < 1e-6, (manual, s1["token_logprobs"][0]))
        chk(f"{pid} 평균에 prompt/image token 미포함", s1["n_target_tokens"] == full_ids.shape[1] - n and s1["target_ids"] == [int(x) for x in full_ids[0, n:]],
            (s1["n_target_tokens"], int(full_ids.shape[1]), int(n)))
        # 생성 첫 token == prompt-only logits argmax
        pre = tok(query, return_tensors="pt")["input_ids"]
        lg0 = MM.forward_logits(model, pre, vit)
        am = int(lg0[0, -1].argmax())
        t0 = time.time()
        gen = MM.generate(model, tok, q["prompt"], pv, max_new_tokens=1)
        chk(f"{pid} 생성 첫 token == argmax", tok.decode([am], skip_special_tokens=True).strip() == gen.strip(), (tok.convert_ids_to_tokens([am]), gen))
        # 영상 대체 민감도 (다른 환자 영상으로 같은 prompt)
        other = [x for x in pvs if x != pid][0]
        s3 = MM.score(model, tok, q["prompt"], MM.vit_features(model, pvs[other]))
        chk(f"{pid} 다른 환자 영상으로 바꾸면 score 변화", abs(s3["mean_logprob"] - s1["mean_logprob"]) > 1e-4, (s1["mean_logprob"], s3["mean_logprob"]))
        # region vs full box
        sf = MM.score(model, tok, full[pid]["prompt"], vit)
        chk(f"{pid} region/full 입력 prompt 다름", q["prompt"] != full[pid]["prompt"] and sf["mean_logprob"] != s1["mean_logprob"],
            (s1["mean_logprob"], sf["mean_logprob"]))
    json.dump(res, open(out_path, "w"), indent=1)
    return all(r["ok"] for r in res)
