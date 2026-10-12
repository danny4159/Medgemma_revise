"""iter_112: MedRegA(공식 InternVLChatModel, 고정 revision) 적재, 공식 chat() 생성, 고정 문자열 teacher-forced likelihood.
실행은 results/environments/medrega112/bin/python. 공식 코드와 다른 점은 README/보고서에 기록한다:
 - LLM attention backend: 공식 config는 flash_attention_2 (flash_attn 미설치) -> sdpa로 지정(수학적으로 동일, 수치 잡음만).
 - 8-bit 적재는 공식 demo의 --load-in-8bit 경로 + device_map(두 GPU 분산)만 추가.
"""
import json
import os
import sys
import time

import torch
from PIL import Image

import mr112_spec as S

EXT = "results/iter_112/external"
SRC = f"{EXT}/MedRegA/src"
WDIR = "results/environments/medrega112_weights"
sys.path.insert(0, os.path.abspath(SRC))
N_GPU0_LAYERS = 23
IMG_START, IMG_END, IMG_CTX ="<img>", "</img>", "<IMG_CONTEXT>"


def ensure_weight_dir():
    """가중치 dir에 config/tokenizer/index 등 소형 파일을 심볼릭 링크 (원본 보존)."""
    for n in os.listdir(f"{EXT}/hf_small"):
        d = f"{WDIR}/{n}"
        if not os.path.lexists(d):
            os.symlink(os.path.abspath(f"{EXT}/hf_small/{n}"), d)


def load(max_memory=None, load_in_8bit=True):
    from internvl.model.internvl_chat import InternVLChatConfig, InternVLChatModel
    from transformers import AutoTokenizer, BitsAndBytesConfig

    ensure_weight_dir()
    tok = AutoTokenizer.from_pretrained(WDIR, trust_remote_code=True, use_fast=False)
    cfg = InternVLChatConfig.from_pretrained(WDIR)
    cfg.llm_config._attn_implementation_internal = "sdpa"
    kw = dict(config=cfg, low_cpu_mem_usage=True, torch_dtype=torch.bfloat16)
    if load_in_8bit:
        # 자동 device_map은 balanced 예산(GPU0 19.4GiB)에서 CPU offload로 떨어져 거부됨 -> 수동 분할(int8 ~40.2GB, 각 GPU ~19.4GiB).
        lm = "language_model.base_model.model"
        dm = {"vision_model": 0, "mlp1": 0, f"{lm}.model.embed_tokens": 0}
        for i in range(60):
            dm[f"{lm}.model.layers.{i}"] = 0 if i < N_GPU0_LAYERS else 1
        dm[f"{lm}.model.norm"] = 1
        dm[f"{lm}.lm_head"] = 0  # HF greedy_search는 logits과 input_ids(embedding 장치)가 같은 장치여야 한다
        # 공식 checkpoint는 미병합 LoRA(lora_A/B)를 포함한다. 기본 8-bit 변환은 lora_A/B까지 int8로 만들어 peft forward가
        # x를 int8로 cast하며 실패('addmm_cuda' Char). lora_A/B(0.12B)는 bf16 유지.
        # lm_head(0.46B)도 bf16 유지: int8 outlier 분해가 어휘 64007 x 수천 열의 1.5GiB 임시 텐서를 만들어 GPU1 OOM, likelihood 정밀도에도 유리.
        kw.update(quantization_config=BitsAndBytesConfig(load_in_8bit=True, llm_int8_skip_modules=["lora_A", "lora_B", "mlp1.3", "lm_head"]),
                  device_map=dm)
    t0 = time.time()
    model = InternVLChatModel.from_pretrained(WDIR, **kw).eval()
    return model, tok, time.time() - t0


def load_image(path):
    from internvl.train.dataset import build_transform
    im = Image.open(path).convert("RGB")
    t = build_transform(is_train=False, input_size=448)
    return t(im).unsqueeze(0)  # 공식: dynamic 미사용, 448 bicubic resize + ImageNet 정규화


def build_query(model, tok, prompt):
    """공식 chat()과 동일한 query 문자열/ids를 만든다."""
    from internvl.conversation import get_conv_template
    model.img_context_token_id = tok.convert_tokens_to_ids(IMG_CTX)
    tpl = get_conv_template(model.template)
    tokens = IMG_START + IMG_CTX * model.num_image_token + IMG_END
    q = prompt.replace("<image>", tokens)
    tpl.append_message(tpl.roles[0], q)
    tpl.append_message(tpl.roles[1], None)
    return tpl.get_prompt()


@torch.no_grad()
def vit_features(model, pixel_values):
    dev = next(model.vision_model.parameters()).device
    return model.extract_feature(pixel_values.to(dev, torch.bfloat16))


@torch.no_grad()
def forward_logits(model, input_ids, vit_embeds):
    """generate()와 동일한 embedding 치환 후 language_model 전체 logits(1,N,V)."""
    emb_layer = model.language_model.get_input_embeddings()
    ids = input_ids.to(emb_layer.weight.device)
    emb = emb_layer(ids).clone()
    B, N, C = emb.shape
    emb = emb.reshape(B * N, C)
    sel = ids.reshape(B * N) == model.img_context_token_id
    assert int(sel.sum()) == vit_embeds.reshape(-1, C).shape[0], "image token 수 불일치"
    emb[sel] = vit_embeds.reshape(-1, C).to(emb.device, emb.dtype)
    emb = emb.reshape(B, N, C)
    mask = torch.ones_like(ids)
    out = model.language_model(inputs_embeds=emb, attention_mask=mask, use_cache=False, return_dict=True)
    return out.logits


def target_split(tok, query, target):
    """query+target 전체 tokenization이 query tokenization을 prefix로 가지는지 확인하고 (ids, n_prefix) 반환."""
    pre = tok(query, return_tensors="pt")["input_ids"]
    full = tok(query + target, return_tensors="pt")["input_ids"]
    n = pre.shape[1]
    ok = bool(full.shape[1] > n and torch.equal(full[0, :n], pre[0]))
    return full, n, ok


@torch.no_grad()
def score(model, tok, prompt, vit_embeds, target=S.TARGET):
    """EOS 제외, target token들의 평균 log-prob. 이미지/프롬프트 token은 평균에 들어가지 않는다."""
    q = build_query(model, tok, prompt)
    full, n, ok = target_split(tok, q, target)
    if not ok:
        raise RuntimeError("target tokenization이 prefix 경계를 깨뜨림")
    logits = forward_logits(model, full, vit_embeds)
    lp = torch.log_softmax(logits[0, n - 1:-1].float(), dim=-1)
    tgt = full[0, n:].to(lp.device)
    tl = lp.gather(1, tgt[:, None])[:, 0]
    return dict(mean_logprob=float(tl.mean()), sum_logprob=float(tl.sum()), token_logprobs=[float(x) for x in tl],
                n_target_tokens=int(tgt.numel()), target_ids=[int(x) for x in tgt], n_prompt_tokens=int(n))


@torch.no_grad()
def generate(model, tok, prompt, pixel_values, max_new_tokens=S.GEN_MAX_NEW_TOKENS):
    """공식 chat(): greedy(num_beams=1, total_params>20 분기와 동일), min_new_tokens=1."""
    dev = next(model.vision_model.parameters()).device
    gc = dict(num_beams=1, max_new_tokens=max_new_tokens, min_new_tokens=1, do_sample=False, temperature=0.0)
    return model.chat(tokenizer=tok, pixel_values=pixel_values.to(dev, torch.bfloat16), question=prompt, generation_config=gc)
