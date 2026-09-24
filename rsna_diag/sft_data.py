"""직접 병변 SFT 학습 입력 (iter_010): target 문자열, 생성용/학습용 prefix 대조, assistant-only labels, collator.

- 학습 prompt는 생성 평가와 같은 concise prompt, 같은 영상 전처리(generate.load_image), 같은 chat template이다.
- target = 모든 GT box의 JSON 목록(중심 x, 중심 y, 좌표 순 결정적 정렬) 또는 "[]".
- labels: assistant 본문 + <end_of_turn> 만 학습 (system/user/image/padding/후행 개행은 -100).
"""
import json

from . import generate

TARGET_LABEL = "pulmonary opacity"


def round_half_up(v):
    return int(v + 0.5)


def target_boxes(boxes_yxyx):
    """GT 정규화 box -> 정수 좌표, 결정적 순서. 반올림 뒤 유효하지 않으면 예외 (조용히 고치지 않는다)."""
    out = []
    for b in boxes_yxyx:
        y0, x0, y1, x1 = [round_half_up(v) for v in b]
        if not (0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
            raise ValueError(f"box invalid after integer rounding: {b} -> {[y0, x0, y1, x1]}")
        out.append([y0, x0, y1, x1])
    return sorted(out, key=lambda b: ((b[1] + b[3]) / 2, (b[0] + b[2]) / 2, b[0], b[1], b[2], b[3]))


def target_text(boxes_yxyx):
    bs = target_boxes(boxes_yxyx)
    return json.dumps([{"box_2d": b, "label": TARGET_LABEL} for b in bs])


def build_example(proc, image, prompt, target):
    """returns dict(input_ids, attention_mask, token_type_ids?, pixel_values, labels) 1-D/텐서 (batch 차원 없음, pixel_values는 (n,3,H,W))."""
    import torch
    gen = generate.build_inputs(proc, image, prompt)
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]},
            {"role": "assistant", "content": [{"type": "text", "text": target}]}]
    full = proc.apply_chat_template(msgs, add_generation_prompt=False, tokenize=True, return_dict=True, return_tensors="pt")
    gi, fi = gen["input_ids"][0], full["input_ids"][0]
    n = gi.shape[0]
    if fi.shape[0] <= n or not torch.equal(fi[:n], gi):
        raise ValueError("generation prefix != training prefix (token mismatch)")
    tail = proc.tokenizer.decode(fi[n:].tolist(), skip_special_tokens=False)
    if tail != target + "<end_of_turn>\n":
        raise ValueError(f"unexpected assistant tail {tail!r}")
    if not torch.equal(gen["pixel_values"], full["pixel_values"]):
        raise ValueError("pixel_values differ between generation and training inputs")
    labels = fi.clone()
    labels[:n] = -100
    labels[-1] = -100  # 후행 "\n"
    if int((labels != -100).sum()) < 2:
        raise ValueError("no assistant tokens to learn")
    ex = {"input_ids": fi, "attention_mask": full["attention_mask"][0], "pixel_values": full["pixel_values"], "labels": labels,
          "n_prefix": n}
    if "token_type_ids" in full:
        ex["token_type_ids"] = full["token_type_ids"][0]
    return ex


def collate(examples, pad_id):
    import torch
    L = max(e["input_ids"].shape[0] for e in examples)
    B = len(examples)
    ids = torch.full((B, L), pad_id, dtype=torch.long)
    att = torch.zeros((B, L), dtype=torch.long)
    lab = torch.full((B, L), -100, dtype=torch.long)
    has_tt = "token_type_ids" in examples[0]
    tt = torch.zeros((B, L), dtype=torch.long) if has_tt else None
    for i, e in enumerate(examples):
        n = e["input_ids"].shape[0]  # right padding
        ids[i, :n], att[i, :n], lab[i, :n] = e["input_ids"], e["attention_mask"], e["labels"]
        if has_tt:
            tt[i, :n] = e["token_type_ids"]
    out = {"input_ids": ids, "attention_mask": att, "labels": lab, "pixel_values": torch.cat([e["pixel_values"] for e in examples], 0)}
    if has_tt:
        out["token_type_ids"] = tt
    return out
