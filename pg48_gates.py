"""iter_048 동작 확인 gate (결과는 results/iter_048/tests/ 의 새 파일; 기존 파일은 덮어쓰지 않는다).

  python pg48_gates.py data      # CPU: 자료·target·AB/BA·좌표·분리·token 분모 (영상 hash 전수)
  python pg48_gates.py inputs    # CPU(processor만): 공식 processor 대조, assistant mask/prefix/EOS
  python pg48_gates.py gpu       # GPU 1장: init digest, CE 독립 계산, gradient accumulation (허용 오차는 검사 전에 고정)
허용 오차(검사 전 고정): CE 상대차 <= 2e-3, accumulation 상대 L2 grad 차 <= 2e-3 (같은 dropout seed, 합 후 단일 backward vs 환자별 backward).
"""
import hashlib
import json
import os
import sys
import time

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

import pg39_spec as S
import pg48_train as T
from rsna_diag import geometry, generate, sft_data

OUT = "results/iter_048/tests"
MAN43 = "results/iter_043/data/manifest_private.json"
EVAL_MAN40 = "results/iter_040/data/manifest_eval_private.jsonl"
CE_TOL = 2e-3
ACC_TOL = 2e-3
checks = []


def chk(name, ok, detail=None):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, "" if ok else detail, flush=True)


TAG = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("tag=")), "")


def write(name, obj):
    if TAG:
        name = name.replace(".json", f"_{TAG}.json")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    if os.path.exists(p):
        sys.exit(f"exists: {p}")
    tmp = p + f".{os.getpid()}.tmp"
    json.dump(obj, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, p)


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def train_rows():
    return sorted(T.load_rows(T.TRAIN_MANIFEST, {"T305"}), key=lambda r: r["PatientID"])


# ------------------------------------------------------------------ data
def gate_data():
    t0 = time.time()
    rows = train_rows()
    man = json.load(open(MAN43))
    chk("T305 305 patients", len(rows) == 305, len(rows))
    chk("T305 610 sentences", sum(len(r["sentences"]) for r in rows) == 610)
    nbox = sum(len(r["gt_boxes_xyxy_norm"][p]) for r in rows for p in ("qA", "qB"))
    chk("T305 765 boxes", nbox == 765, nbox)
    chk("D24 24 / V96 96 patients, 192 sentences", len(man["D24"]) == 24 and len(man["V96"]) == 96)
    chk("iter_043 T305 patient set == iter_040 train manifest", {e["PatientID"] for e in man["T305"]} == {r["PatientID"] for r in rows})
    gt43 = {e["PatientID"]: e["gt_boxes_xyxy_norm"] for e in man["T305"]}
    chk("T305 GT boxes equal between iter_043 and iter_040 manifests", all(gt43[r["PatientID"]] == r["gt_boxes_xyxy_norm"] for r in rows))
    # canvas GT 재계산
    bad = 0
    for r in rows:
        for p in ("qA", "qB"):
            re = S.gt_to_canvas(r["gt_boxes_xyxy_norm"][p], r["image_meta"]["h"], r["image_meta"]["w"])
            if not np.allclose(np.array(re), np.array(r["gt_canvas_yxyx"][p]), atol=1e-9):
                bad += 1
    chk("canvas GT recomputed == stored (T305)", bad == 0, bad)
    # 영상 hash 전수 (train)
    nbad = 0
    for r in rows:
        try:
            T.check_image(r)
        except T.TrainError:
            nbad += 1
    chk("T305 image u8 pixel hash == manifest (305)", nbad == 0, nbad)
    nb2 = 0
    for e in man["D24"] + man["V96"]:
        if sha_file(e["image"]) != e["image_file_sha256"] or generate.load_image(e["image"])[2] != e["input_pixel_sha256"]:
            nb2 += 1
    chk("D24/V96 current image file+padded pixel hash == manifest (120)", nb2 == 0, nb2)
    # 분리
    sets = {"T": man["T305"], "D": man["D24"], "V": man["V96"]}
    for key in ("PatientID", "StudyID", "ImageID"):
        ids = {k: {e[key] for e in v} for k, v in sets.items()}
        chk(f"{key} disjoint T/D/V", not (ids["T"] & ids["D"]) and not (ids["T"] & ids["V"]) and not (ids["D"] & ids["V"]))
    px = {k: {e["u8_pixel_sha256"] for e in v} for k, v in sets.items()}
    chk("raw u8 pixel hash disjoint T/D/V", not (px["T"] & px["D"]) and not (px["T"] & px["V"]) and not (px["D"] & px["V"]))
    # GT 유효성 (유한·양의 크기·범위) — 전체 T/D/V
    invalid = 0
    allbox = 0
    for v in sets.values():
        for e in v:
            for p in ("qA", "qB"):
                for b in e["gt_boxes_xyxy_norm"][p]:
                    allbox += 1
                    x0, y0, x1, y1 = b
                    if not (all(np.isfinite(b)) and 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                        invalid += 1
    chk("all GT boxes finite, positive size, within [0,1] (T/D/V)", invalid == 0, {"invalid": invalid, "n": allbox})
    # 좌표 왕복: canvas(0-1000, yxyx) -> original normalized xyxy -> canvas
    max_err = 0.0
    for e in man["T305"][:] + man["V96"]:
        top, left, side = geometry.pad_offsets(e["h"], e["w"])
        for p in ("qA", "qB"):
            for b in e["gt_boxes_xyxy_norm"][p]:
                c = S.gt_to_canvas([b], e["h"], e["w"])[0]
                x0, y0, x1, y1 = geometry.norm_to_canvas(c, top, left, side)
                back = [x0 / e["w"], y0 / e["h"], x1 / e["w"], y1 / e["h"]]
                max_err = max(max_err, float(np.max(np.abs(np.array(back) - np.array(b)))))
    chk("coordinate round-trip (canvas<->original normalized) max err < 1e-9", max_err < 1e-9, max_err)
    # target 검사
    tok = None
    try:
        import transformers
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("HF_HOME", generate.HF_HOME)
        tok = transformers.AutoProcessor.from_pretrained(generate.MODEL_ID, revision=generate.MODEL_REVISION).tokenizer
    except Exception as ex:  # noqa
        chk("tokenizer load", False, str(ex))
    n_tgt_bad = 0
    n_j_tokens, n_i_tokens = [], []
    max_boxes = 0
    for r in rows:
        gtc = r["gt_canvas_yxyx"]
        for pid in ("qA", "qB"):
            t = T.target_text(gtc[pid], pid)
            L = json.loads(t)
            want = sft_data.target_boxes(gtc[pid])
            if [x["box_2d"] for x in L] != want or {x["label"] for x in L} != {pid} or len(L) != len(r["gt_boxes_xyxy_norm"][pid]) or len(L) < 1:
                n_tgt_bad += 1
            for x in L:
                y0, x0, y1, x1 = x["box_2d"]
                if not (all(isinstance(v, int) for v in x["box_2d"]) and 0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
                    n_tgt_bad += 1
            max_boxes = max(max_boxes, len(L))
            n_i_tokens.append(T.label_count(tok, t))
        for order in (("qA", "qB"), ("qB", "qA")):
            t = T.joint_target_text(gtc, order)
            L = json.loads(t)
            labs = [x["label"] for x in L]
            first = order[0]
            k1 = len(r["gt_boxes_xyxy_norm"][first])
            exp = [x for pid in order for x in [{"box_2d": b, "label": pid} for b in sft_data.target_boxes(gtc[pid])]]
            if L != exp or labs[:k1] != [first] * k1 or len(L) != len(r["gt_boxes_xyxy_norm"]["qA"]) + len(r["gt_boxes_xyxy_norm"]["qB"]):
                n_tgt_bad += 1
            if tok is not None:
                n_j_tokens.append(T.label_count(tok, t))
    chk("I/J targets: all GT boxes, IDs, order, ints in range, no extra boxes (305 pts x I2 + J2 orders)", n_tgt_bad == 0, n_tgt_bad)
    # fixtures
    ok_fix = True
    detail = {}
    try:
        T.joint_target_text(rows[0]["gt_canvas_yxyx"], ("qA", "qA"))
        ok_fix = False
        detail["dup_id_accepted"] = True
    except ValueError:
        pass
    try:
        sft_data.target_boxes([[0.0, 0.0, 0.0, 10.0]])
        ok_fix = False
        detail["zero_size_accepted"] = True
    except ValueError:
        pass
    try:
        sft_data.target_boxes([[0.0, 0.0, 1000.4, 10.0]])  # round -> 1000 ok
        sft_data.target_boxes([[0.0, 0.0, 1000.6, 10.0]])  # round -> 1001 reject
        ok_fix = False
        detail["out_of_range_accepted"] = True
    except ValueError:
        pass
    empty = json.loads(T.joint_target_text({"qA": [], "qB": [[10, 10, 20, 20]]}, ("qA", "qB")))
    chk("fixture: duplicate ID/zero-size/out-of-range rejected; empty list for one ID keeps only the other", ok_fix and len(empty) == 1 and empty[0]["label"] == "qB", detail)
    # AB/BA 균형
    per_epoch = []
    alt_ok = True
    for ep in range(8):
        n_ab = sum(T.joint_order(r["PatientID"], ep)[0] == "qA" for r in rows)
        per_epoch.append(n_ab)
    for r in rows:
        seq = [T.joint_order(r["PatientID"], ep)[0] for ep in range(8)]
        alt_ok &= all(seq[i] != seq[i + 1] for i in range(7))
    chk("J AB/BA: every patient alternates each epoch; per-epoch AB count within 305/2 +- 25", alt_ok and all(abs(n - 152.5) <= 25 for n in per_epoch), per_epoch)
    # 같은 환자가 5 epoch에서 AB/BA 각각 2~3회
    cnt = [sum(T.joint_order(r["PatientID"], ep)[0] == "qA" for ep in range(5)) for r in rows]
    chk("J AB count per patient over 5 epochs in {2,3}", set(cnt) <= {2, 3}, {c: cnt.count(c) for c in set(cnt)})
    # 마지막 불완전 batch: 305 = 38*8 + 1
    order = np.random.default_rng(17 * 1000 + 0).permutation(305)
    spe = -(-305 // 8)
    last = order[(spe - 1) * 8:]
    ok_last = len(last) == 1
    for mode in ("ce", "joint"):
        tt = T.batch_tot_tok(tok, rows, last, mode, 0)
        expect = sum(T.label_count(tok, t) for _, t in T.patient_texts(rows[last[0]], mode, 0))
        ok_last &= (tt == expect)
    chk("last incomplete batch (1 patient): token denominator == that patient's own label tokens (E and J)", ok_last, {"spe": spe, "last_n": len(last)})
    # token 구조 비교
    summ = {"E_label_tokens_per_patient_mean": float(np.mean(n_i_tokens)) * 2 if n_i_tokens else None,
            "J_label_tokens_per_patient_mean": float(np.mean(n_j_tokens)) if n_j_tokens else None,
            "max_boxes_per_sentence": max_boxes,
            "J_label_tokens_max": int(max(n_j_tokens)) if n_j_tokens else None,
            "E_label_tokens_per_sentence_max": int(max(n_i_tokens)) if n_i_tokens else None,
            "E_to_J_label_token_ratio": (float(np.mean(n_i_tokens)) * 2 / float(np.mean(n_j_tokens))) if n_j_tokens else None,
            "joint_AB_per_epoch": per_epoch}
    res = {"checks": checks, "n_pass": sum(c["ok"] for c in checks), "n": len(checks), "summary": summ, "wall_s": time.time() - t0,
           "source_sha256": {f: sha_file(f) for f in T.CODE_FILES + ["pg48_gates.py"]}}
    write("gate_data.json", res)
    print(json.dumps(summ, indent=1))
    print("DATA GATE", res["n_pass"], "/", res["n"])
    sys.exit(0 if res["n_pass"] == res["n"] else 1)


# ------------------------------------------------------------------ inputs
def pick_patients(rows):
    """고정 규칙: stratum별 앞 1명(PatientID 정렬) 중 최대 6 + 가장 긴 J target + 최대 box 수 환자. 8명."""
    by = {}
    for r in rows:
        by.setdefault(r.get("stratum"), []).append(r)
    picks = [by[k][0]["PatientID"] for k in sorted(by, key=str)][:6]
    sizes = {r["PatientID"]: sum(len(r["gt_boxes_xyxy_norm"][p]) for p in ("qA", "qB")) for r in rows}
    longest = max(rows, key=lambda r: (len(T.joint_target_text(r["gt_canvas_yxyx"], ("qA", "qB"))), r["PatientID"]))["PatientID"]
    maxb = max(rows, key=lambda r: (sizes[r["PatientID"]], r["PatientID"]))["PatientID"]
    out = []
    for p in picks + [longest, maxb]:
        if p not in out:
            out.append(p)
    for r in rows:  # 8명까지 채움
        if len(out) >= 8:
            break
        if r["PatientID"] not in out:
            out.append(r["PatientID"])
    return out[:8]


def gate_inputs():
    import torch
    import transformers
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("HF_HOME", generate.HF_HOME)
    t0 = time.time()
    proc = transformers.AutoProcessor.from_pretrained(generate.MODEL_ID, revision=generate.MODEL_REVISION)
    tok = proc.tokenizer
    cfg = transformers.AutoConfig.from_pretrained(generate.MODEL_ID, revision=generate.MODEL_REVISION)
    IMG_TOK = getattr(cfg, "image_token_id", None) or cfg.image_token_index
    rows = train_rows()
    byp = {r["PatientID"]: r for r in rows}
    pick = pick_patients(rows)
    n_ok = 0
    detail = []
    for pid in pick:
        r = byp[pid]
        image, _, _ = generate.load_image(r["image_meta"]["path"])
        for mode, epoch in (("ce", 0), ("joint", 0), ("joint", 1)):
            for prompt, target in T.patient_texts(r, mode, epoch):
                ex = sft_data.build_example(proc, image, prompt, target)
                ids, lab = ex["input_ids"], ex["labels"]
                n = ex["n_prefix"]
                # (1) 공식 경로 독립 구성: apply_chat_template(tokenize=False) + proc(text, images)
                msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
                text = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
                ind = proc(text=text, images=[image], return_tensors="pt", add_special_tokens=False)
                gen_in = generate.build_inputs(proc, image, prompt)
                same_ids = torch.equal(ind["input_ids"][0], gen_in["input_ids"][0]) and torch.equal(ids[:n], gen_in["input_ids"][0])
                same_px = torch.equal(ind["pixel_values"], ex["pixel_values"]) and torch.equal(gen_in["pixel_values"], ex["pixel_values"])
                # (2) mask
                learned = (lab != -100).nonzero()[:, 0]
                contiguous = bool((learned[1:] - learned[:-1] == 1).all())
                prefix_masked = bool((lab[:n] == -100).all())
                dec = tok.decode(ids[learned].tolist(), skip_special_tokens=False)
                eos_ok = dec == target + "<end_of_turn>" and int(learned[-1]) == ids.shape[0] - 2 and int(lab[-1]) == -100
                cnt_ok = int(learned.numel()) == T.label_count(tok, target)
                # (3) target이 모든 GT box를 가진다
                L = json.loads(target)
                gtc = r["gt_canvas_yxyx"]
                if mode == "ce":
                    pid_t = L[0]["label"]
                    gt_ok = [x["box_2d"] for x in L] == sft_data.target_boxes(gtc[pid_t])
                else:
                    gt_ok = len(L) == sum(len(gtc[p]) for p in ("qA", "qB")) and {x["label"] for x in L} == {"qA", "qB"}
                n_img_tok = int((ids == IMG_TOK).sum())
                ok = same_ids and same_px and contiguous and prefix_masked and eos_ok and cnt_ok and gt_ok and n_img_tok == 256
                detail.append({"patient": pid, "mode": mode, "epoch": epoch, "n_tokens": int(ids.shape[0]), "n_learned": int(learned.numel()), "n_boxes": len(L),
                               "same_ids": same_ids, "same_pixel_values": same_px, "contiguous": contiguous, "prefix_masked": prefix_masked, "eos_ok": eos_ok,
                               "label_count_ok": cnt_ok, "gt_ok": gt_ok, "n_image_tokens": n_img_tok, "ok": ok})
                n_ok += ok
    chk(f"official processor / assistant-only mask / EOS / prefix / GT for {len(pick)} patients x (I2 + J AB + J BA)", n_ok == len(detail), {"ok": n_ok, "n": len(detail)})
    # 긴 J sequence: 가장 긴 학습 sequence 길이
    res = {"checks": checks, "n_pass": sum(c["ok"] for c in checks), "n": len(checks), "picked_patients": pick, "detail": detail,
           "max_tokens": max(d["n_tokens"] for d in detail), "wall_s": time.time() - t0,
           "source_sha256": {f: sha_file(f) for f in T.CODE_FILES + ["pg48_gates.py"]}}
    write("gate_inputs_v2.json", res)
    print("INPUT GATE", res["n_pass"], "/", res["n"])
    sys.exit(0 if res["n_pass"] == res["n"] else 1)


# ------------------------------------------------------------------ gpu
def flat_grad(params):
    import torch
    return torch.cat([p.grad.detach().float().reshape(-1) if p.grad is not None else torch.zeros(p.numel(), device=p.device) for p in params])


def gate_gpu():
    """det 인자: 결정적 kernel 모드. 첫 비결정 실행에서 accumulation 차이(1.18%)가 같은 함수의 반복 노이즈(1.20%)와 같아 검사 설계가 비결정 backward를 구분하지 못했다(저장: gate_gpu_01.json).
    그래서 결정적 모드에서 반복 노이즈 <= 1e-6 (결정성 증명)과 accumulation 차이 <= ACC_TOL을 같이 요구하는 검사를 검사 전에 고정해 별도 결과로 다시 수행한다."""
    det = "det" in sys.argv[2:]
    if det:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    import torch
    from rsna_diag import lora
    from rsna_diag import train as T0
    if det:
        T0.set_deterministic(torch)
    t0 = time.time()
    rows = train_rows()
    T0.seed_all(torch, 17)
    _, proc, model = generate.load_model()
    names = lora.apply_lora(model, T.CFG["r"], T.CFG["alpha"], T.CFG["dropout"], seed=17)
    blob = torch.load("results/iter_040/train2/C_s17/epoch_03/adapter.pt", map_location="cpu", weights_only=True)
    chk("C epoch03 adapter file digest == state digest == constant", lora.state_digest(blob["state"]) == blob["digest"] == T.C_ADAPTER_DIGEST)
    lora.load_lora_state(model, blob["state"])
    chk("loaded model LoRA state digest == C digest", lora.state_digest(lora.lora_state_dict(model)) == T.C_ADAPTER_DIGEST)
    chk("LoRA target modules 238 / trainable 29,802,496", len(names) == 238 and sum(p.numel() for p in lora.lora_params(model).values()) == 29802496,
        {"n": len(names)})
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    tok = proc.tokenizer
    pick = pick_patients(rows)[:3]
    # --- CE 독립 계산: 전체 logits(model forward) vs seq_losses (eval mode, dropout 없음)
    model.eval()
    ce_rel = []
    for mode, epoch in (("ce", 0), ("joint", 0)):
        r = [x for x in rows if x["PatientID"] == pick[0]][0]
        image, _, _ = generate.load_image(r["image_meta"]["path"])
        exs = [sft_data.build_example(proc, image, *pt) for pt in T.patient_texts(r, mode, epoch)]
        for ex in exs:
            b = {k: v.cuda() for k, v in sft_data.collate([ex], tok.pad_token_id).items()}
            with torch.no_grad():
                ce_a, n_a = T.seq_losses(torch, model, b, softcap)
                inp = {k: v for k, v in b.items() if k != "labels"}
                inp["pixel_values"] = inp["pixel_values"].to(torch.bfloat16)
                full = model(**inp, use_cache=False).logits.float()
                if softcap:
                    full = torch.tanh(full / softcap) * softcap
                lab = b["labels"][:, 1:]
                sel = lab != -100
                lg = full[:, :-1][sel].double()
                ce_b = torch.nn.functional.cross_entropy(lg, lab[sel], reduction="sum")
            ce_rel.append(abs(float(ce_a.sum()) - float(ce_b)) / float(ce_b))
    chk(f"CE (assistant-only token sum): seq_losses vs full-logits float64 CE, rel diff <= {CE_TOL}", max(ce_rel) <= CE_TOL, ce_rel)
    # --- gradient accumulation (train mode, gradient checkpointing, 같은 dropout seed)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    model.train()
    params = list(lora.lora_params(model).values())
    acc_rel = {}
    base_h = lora.base_digest(model)
    for mode in ("joint", "ce"):
        grp = [x for x in rows if x["PatientID"] in pick]
        items = []
        for r in grp:
            image, _, _ = generate.load_image(r["image_meta"]["path"])
            items.append({"exs": [sft_data.build_example(proc, image, *pt) for pt in T.patient_texts(r, mode, 0)]})
        tot = sum(T.label_count(tok, t) for r in grp for _, t in T.patient_texts(r, mode, 0))
        for p in params:
            p.grad = None
        for k, it in enumerate(items):
            T.patient_step(torch, model, it, tok.pad_token_id, softcap, tot, 2, T.derive_seed(17, 0, k))
        gA = flat_grad(params).clone()
        for p in params:
            p.grad = None
        loss = 0
        for k, it in enumerate(items):
            torch.manual_seed(T.derive_seed(17, 0, k))
            torch.cuda.manual_seed(T.derive_seed(17, 0, k))
            ce, n, _ = T.group_losses(torch, model, it["exs"], tok.pad_token_id, softcap, 2)
            loss = loss + ce.sum() / tot
        loss.backward()
        gB = flat_grad(params).clone()
        rel = float((gA - gB).norm() / gB.norm())
        # 반복 노이즈 기준: 같은 방식 재실행
        for p in params:
            p.grad = None
        for k, it in enumerate(items):
            T.patient_step(torch, model, it, tok.pad_token_id, softcap, tot, 2, T.derive_seed(17, 0, k))
        gA2 = flat_grad(params).clone()
        acc_rel[mode] = {"rel_l2_accum_vs_single_backward": rel, "rel_l2_repeat_noise": float((gA - gA2).norm() / gA.norm()), "grad_norm": float(gB.norm()),
                         "n_patients": len(items), "tot_tokens": tot}
        for p in params:
            p.grad = None
    chk(f"gradient accumulation == single backward (rel L2 <= {ACC_TOL}) for J and E", all(v["rel_l2_accum_vs_single_backward"] <= ACC_TOL for v in acc_rel.values()), acc_rel)
    if det:
        chk("deterministic mode: repeat-run gradient noise <= 1e-6", all(v["rel_l2_repeat_noise"] <= 1e-6 for v in acc_rel.values()), acc_rel)
    chk("base weights unchanged by forward/backward (base digest)", lora.base_digest(model) == base_h)
    chk("gradients only on LoRA parameters (base params have no grad)", all(p.grad is None for n_, p in model.named_parameters() if not p.requires_grad))
    peak = torch.cuda.max_memory_allocated() / 2 ** 30
    res = {"checks": checks, "n_pass": sum(c["ok"] for c in checks), "n": len(checks), "ce_rel": ce_rel, "acc": acc_rel, "peak_alloc_gb": peak,
           "tolerances_fixed_before": {"ce_rel": CE_TOL, "acc_rel": ACC_TOL}, "wall_s": time.time() - t0, "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "source_sha256": {f: sha_file(f) for f in T.CODE_FILES + ["pg48_gates.py"]}}
    res["deterministic_mode"] = det
    write(f"gate_gpu_{'det_' if det else ''}{os.environ.get('CUDA_VISIBLE_DEVICES', 'x').replace(',', '')}.json", res)
    print("GPU GATE", res["n_pass"], "/", res["n"], "peak", peak)
    sys.exit(0 if res["n_pass"] == res["n"] else 1)


if __name__ == "__main__":
    {"data": gate_data, "inputs": gate_inputs, "gpu": gate_gpu}[sys.argv[1]]()
