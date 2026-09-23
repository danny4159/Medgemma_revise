"""MedGemma 1.5 Yes/No margin scorer. torch/transformers는 load() 안에서만 import한다 (import-time GPU 부작용 없음)."""
import os

from .data import MODEL_ID, MODEL_REVISION, SCORER_VERSION

HF_HOME = "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache"


class Scorer:
    def __init__(self):
        self.model = None

    def load(self):
        os.environ.setdefault("HF_HOME", HF_HOME)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import torch
        import transformers

        self.torch = torch
        torch.manual_seed(0)
        self.proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
        self.model = transformers.AutoModelForImageTextToText.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, dtype=torch.bfloat16, device_map="cuda")
        self.model.eval()
        tok = self.proc.tokenizer
        self.tok = tok
        self.cand_ids = {k: tok.encode(k, add_special_tokens=False) for k in ("Yes", "No")}
        if any(len(v) != 1 for v in self.cand_ids.values()):
            raise RuntimeError(f"Yes/No not single tokens: {self.cand_ids}")
        self.yes_id = self.cand_ids["Yes"][0]
        self.no_id = self.cand_ids["No"][0]
        # proc.image_token_id는 <start_of_image>(boi)를 가리키므로 soft token id를 직접 쓴다.
        self.image_token_id = tok.convert_tokens_to_ids("<image_soft_token>")
        self.eot_id = tok.convert_tokens_to_ids("<end_of_turn>")
        self.eos_ids = {self.eot_id, tok.eos_token_id}
        cfg = self.model.config
        text_cfg = getattr(cfg, "text_config", cfg)
        self.softcap = getattr(text_cfg, "final_logit_softcapping", None)
        return self.env_info()

    def env_info(self):
        import transformers
        ip = self.proc.image_processor
        return {
            "model_id": MODEL_ID,
            "model_revision_requested": MODEL_REVISION,
            "model_commit_hash": getattr(self.model.config, "_commit_hash", None),
            "name_or_path": self.model.config._name_or_path,
            "transformers": transformers.__version__,
            "torch": self.torch.__version__,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "gpu_name": self.torch.cuda.get_device_name(0),
            "dtype": str(self.model.dtype),
            "processor_class": type(self.proc).__name__,
            "image_processor_class": type(ip).__name__,
            "image_processor_size": str(getattr(ip, "size", None)),
            "image_seq_length": getattr(self.proc, "image_seq_length", None),
            "do_pan_and_scan": str(getattr(ip, "do_pan_and_scan", None)),
            "candidate_token_ids": self.cand_ids,
            "image_token_id": self.image_token_id,
            "eot_id": self.eot_id,
            "final_logit_softcapping": self.softcap,
            "scorer_version": SCORER_VERSION,
        }

    def _inputs(self, img, prompt):
        msgs = [{"role": "user", "content": [{"type": "image", "image": img},
                                             {"type": "text", "text": prompt}]}]
        inp = self.proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                            return_dict=True, return_tensors="pt")
        torch = self.torch
        return {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values" else v.to("cuda"))
                for k, v in inp.items()}

    def _fp32_head(self, h):
        torch = self.torch
        W = self.model.get_output_embeddings().weight
        lg = h.float() @ W.float().T
        if self.softcap:
            lg = torch.tanh(lg / self.softcap) * self.softcap
        return torch.log_softmax(lg, -1)

    def score(self, img, prompt):
        torch = self.torch
        inp = self._inputs(img, prompt)
        with torch.no_grad():
            out = self.model(**inp, output_hidden_states=True)
            lp = torch.log_softmax(out.logits[0, -1].float(), -1)
            lp32 = self._fp32_head(out.hidden_states[-1][0, -1])
        ids = inp["input_ids"][0]
        text = self.tok.decode(ids, skip_special_tokens=False)
        top = int(torch.argmax(lp))
        return {
            "lp_yes": float(lp[self.yes_id]),
            "lp_no": float(lp[self.no_id]),
            "m": float(lp[self.yes_id] - lp[self.no_id]),
            "m_fp32head": float(lp32[self.yes_id] - lp32[self.no_id]),
            "p_yes_plus_no": float(lp[self.yes_id].exp() + lp[self.no_id].exp()),
            "top1_token": self.tok.decode([top]),
            "n_tokens": int(ids.shape[0]),
            "n_image_tokens": int((ids == self.image_token_id).sum()),
            "pixel_values_shape": list(inp["pixel_values"].shape),
            "prompt_intact": prompt in text,
        }

    def teacher_forced(self, img, prompt):
        """후보 token을 붙여 teacher-forced로 log P(cand)를 구한다 (후보마다 forward 1회)."""
        torch = self.torch
        inp = self._inputs(img, prompt)
        res = {}
        for name, cid in (("Yes", self.yes_id), ("No", self.no_id)):
            x = dict(inp)
            add = torch.tensor([[cid]], device="cuda", dtype=inp["input_ids"].dtype)
            x["input_ids"] = torch.cat([inp["input_ids"], add], 1)
            x["attention_mask"] = torch.cat([inp["attention_mask"], torch.ones_like(add)], 1)
            if "token_type_ids" in inp:
                x["token_type_ids"] = torch.cat([inp["token_type_ids"], torch.zeros_like(add)], 1)
            with torch.no_grad():
                lg = self.model(**x).logits[0, -2].float()
            res[name] = float(torch.log_softmax(lg, -1)[cid])
        return {"tf_lp_yes": res["Yes"], "tf_lp_no": res["No"], "m_tf": res["Yes"] - res["No"]}

    def generate(self, img, prompt, max_new_tokens=8):
        torch = self.torch
        inp = self._inputs(img, prompt)
        n0 = inp["input_ids"].shape[1]
        with torch.no_grad():
            out = self.model.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False)
        new = out[0, n0:].tolist()
        text = self.tok.decode(new, skip_special_tokens=True).strip()
        first = text.split()[0].strip(".,!:;").lower() if text else ""
        parsed = "Yes" if first == "yes" else ("No" if first == "no" else None)
        return {"gen_text": text, "gen_token_ids": new, "gen_n_forward": len(new),
                "gen_truncated": not any(t in self.eos_ids for t in new), "gen_parsed": parsed}
