"""iter_111 E600 provenance ledger: 존재 응답(Q_O, MedGemma 1.5 원본), 직접 SFT bbox(seed17), detector17 출력, GT를
환자 단위로 연결하고 모든 출처를 내용 hash로 검증한다. 결과 지표는 계산하지 않는다(ev111_core.py).
문제가 하나라도 있으면 ledger를 쓰지 않고 problems만 쓴 뒤 종료코드 1. 기존 파일은 덮어쓰지 않는다."""
import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

from rsna_diag import geometry as G

R = "results"
OUT = f"{R}/iter_111/provenance"
SETS = f"{R}/iter_016/manifests/sets.json"
LABELS = f"{R}/iter_016/manifests/labels.json"
INFER = f"{R}/iter_016/manifests/infer_manifest.jsonl"
O_STAGES = {"e180_plain": f"{R}/iter_016/gen/e180_plain__M0", "e600x_plain": f"{R}/iter_016/gen/e600x_plain__M0"}
O_REQ = {"e180_plain": f"{R}/iter_016/requests/e180_plain__M0.jsonl", "e600x_plain": f"{R}/iter_016/requests/e600x_plain__M0.jsonl"}
SFT_DIR = f"{R}/iter_012/confirm_sft_seed17"
SFT_REUSE = f"{R}/iter_015/reuse/bbox_B0_concise.jsonl"
DET_DIR = f"{R}/iter_035/confirm800/det17"
DET_LOCK = f"{R}/iter_035/select/LOCK.json"
DET_SEL = f"{R}/iter_035/select/seed17/v400_selection.json"
THR, EPOCH = 0.70, 18


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def jl(p):
    with open(p) as f:
        return [json.loads(x) for x in f if x.strip()]


def read_workers(d):
    rows, files = [], {}
    for p in sorted(glob.glob(f"{d}/gen_worker*.jsonl")):
        files[os.path.basename(p)] = fsha(p)
        rows += jl(p)
    return rows, files


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(f"{OUT}/ledger.json") or os.path.exists(f"{OUT}/problems.json"):
        sys.exit("exists: 기존 ledger/problems 덮어쓰기 금지")
    P = []
    sets = json.load(open(SETS))["E600"]
    labels = json.load(open(LABELS))
    ids = sorted(i for c in sets.values() for i in c)
    cat_of = {i: c for c, v in sets.items() for i in v}
    if len(ids) != 600 or len(set(ids)) != 600:
        P.append(f"E600 ids {len(ids)}/{len(set(ids))}")
    infer = {r["id"]: r for r in jl(INFER)}
    inputs = {k: fsha(v) for k, v in dict(sets=SETS, labels=LABELS, infer=INFER, det_lock=DET_LOCK, det_sel=DET_SEL,
                                          sft_reuse=SFT_REUSE, det_raw=f"{DET_DIR}/raw_preds.json",
                                          det_completion=f"{DET_DIR}/completion.json").items()}

    # --- 존재 응답 Q_O
    O = {}
    o_prov = {}
    for st, d in O_STAGES.items():
        reqs = jl(O_REQ[st])
        comp = json.load(open(f"{d}/completion.json"))
        rs = fsha(O_REQ[st])
        if comp["requests_sha256"] != rs or comp["n_missing"] or comp["n_duplicate"] or comp["n_extra"] or comp["returncodes"] != [0] * len(comp["returncodes"]):
            P.append(f"{st}: completion 불일치 {comp.get('requests_sha256') == rs}")
        recs, files = read_workers(d)
        rb = {}
        for r in recs:
            if r["request_id"] in rb:
                P.append(f"{st}: 중복 record {r['request_id']}")
            rb[r["request_id"]] = r
        if len(rb) != comp["n_expected"] or len(reqs) != comp["n_expected"]:
            P.append(f"{st}: record 수 {len(rb)} vs {comp['n_expected']}")
        o_prov[st] = dict(requests_sha256=rs, completion_protocol_digest=comp["protocol_digest"], config_digest=comp["config_digest"],
                          worker_files=files, adapter_digest=comp["adapter_digest"])
        for q in reqs:
            if q["target"] != "O":
                continue
            r = rb.get(q["request_id"])
            if r is None:
                P.append(f"{st}: record 없음 {q['id']}")
                continue
            for k in ("id", "checkpoint", "target", "fmt", "condition", "prompt_sha256", "config_digest", "adapter_digest"):
                a = q.get(k)
                b = r.get(k, r.get("prompt_name") if k == "condition" else None)
                if k == "prompt_sha256":
                    b = r.get("prompt_sha256")
                if a != b:
                    P.append(f"{st}:{q['id']} 필드 {k} 불일치 {a!r} {b!r}")
            if r["image_file_sha256"] != q["file_sha256"] or r["protocol_digest"] != comp["protocol_digest"]:
                P.append(f"{st}:{q['id']} 이미지/protocol hash 불일치")
            if q["id"] in O:
                P.append(f"중복 O {q['id']}")
            O[q["id"]] = dict(stage=st, request_id=q["request_id"], raw=r["suffix_text_raw"], ended_eos=r["ended_eos"],
                              finish_reason=r["finish_reason"], image_file_sha256=r["image_file_sha256"],
                              input_ids_sha256=r["input_ids_sha256"], prompt=q["prompt"])

    # --- SFT bbox: 원 worker 파일에서 재추출하여 reuse 파일과 대조
    reuse = {r["id"]: r for r in jl(SFT_REUSE)}
    comp = json.load(open(f"{SFT_DIR}/completion.json"))
    src_rows, sft_files = read_workers(SFT_DIR)
    sb = {}
    for r in src_rows:
        if r.get("prompt_name") == "concise":
            if r["id"] in sb:
                P.append(f"SFT 중복 {r['id']}")
            sb[r["id"]] = r
    sft_prov = dict(dir=SFT_DIR, worker_files=sft_files, protocol_digest=comp.get("protocol_digest"),
                    adapter_digest=sorted({r["adapter_digest"] for r in src_rows}), n_concise=len(sb))
    SFT = {}
    for i in ids:
        r, u = sb.get(i), reuse.get(i)
        if r is None or u is None:
            P.append(f"SFT 없음 {i}")
            continue
        if (r["suffix_text_raw"], r["ended_eos"], r["request_id"], r["adapter_digest"]) != (u["suffix_text_raw"], u["ended_eos"], u["request_id"], u["adapter_digest"]):
            P.append(f"SFT 원본-reuse 불일치 {i}")
        if r["image_file_sha256"] != infer[i]["file_sha256"]:
            P.append(f"SFT 이미지 hash 불일치 {i}")
        SFT[i] = dict(request_id=r["request_id"], raw=r["suffix_text_raw"], ended_eos=r["ended_eos"], finish_reason=r["finish_reason"])

    # --- detector17
    comp = json.load(open(f"{DET_DIR}/completion.json"))
    sel = json.load(open(DET_SEL))
    lock = json.load(open(DET_LOCK))
    raw_sha = fsha(f"{DET_DIR}/raw_preds.json")
    if raw_sha != comp["raw_preds_sha256"]:
        P.append("det raw_preds hash 불일치")
    for fn, h in comp["shard_sha256"].items():
        if fsha(f"{DET_DIR}/{fn}") != h:
            P.append(f"det shard hash 불일치 {fn}")
    if lock["files"]["seed17"]["sha256"] != fsha(DET_SEL):
        P.append("LOCK-v400_selection hash 불일치")
    if sel["selected"]["epoch"] != EPOCH or sel["selected"]["threshold"] != THR:
        P.append("선택 epoch/threshold 불일치")
    if comp["checkpoint_sha256"] != sel["selected_checkpoint_sha256"] or fsha(comp["checkpoint"]) != comp["checkpoint_sha256"]:
        P.append("checkpoint hash 불일치")
    det = json.load(open(f"{DET_DIR}/raw_preds.json"))
    det_prov = dict(raw_preds_sha256=raw_sha, checkpoint_sha256=comp["checkpoint_sha256"], epoch=EPOCH, threshold=THR,
                    lock_sha256=inputs["det_lock"], selection_sha256=inputs["det_sel"], manifest_digest=comp["manifest_digest"])

    # --- 환자별 연결
    rows = []
    for i in ids:
        lab, inf = labels.get(i), infer.get(i)
        if lab is None or inf is None or i not in O or i not in SFT or i not in det:
            P.append(f"연결 누락 {i}: lab={lab is not None} inf={inf is not None} O={i in O} SFT={i in SFT} det={i in det}")
            continue
        if lab["category"] != cat_of[i]:
            P.append(f"category 불일치 {i}")
        p = inf["image"]
        if not os.path.exists(p):
            P.append(f"영상 없음 {i}")
            continue
        if fsha(p) != inf["file_sha256"] or O[i]["image_file_sha256"] != inf["file_sha256"]:
            P.append(f"영상 file hash 불일치 {i}")
        im = Image.open(p)
        w, h = im.size
        top, left, side = G.pad_offsets(h, w)
        d = det[i]
        if list(d["img_hw"]) != [h, w]:
            P.append(f"det img_hw {d['img_hw']} != 영상 {[h, w]} {i}")
        pixel_ok = hashlib.sha256(np.asarray(im).tobytes()).hexdigest() == inf["pixel_sha256"]
        for b in lab["boxes"]:  # px→norm 환산이 저장 norm과 같은지
            c = G.canvas_to_norm(b["xyxy_px"], top, left, side)
            if max(abs(x - y) for x, y in zip(c, b["yxyx_norm"])) > 1e-3:
                P.append(f"GT px/norm 불일치 {i}")
        if (lab["category"] == "opacity") != bool(lab["boxes"]):
            P.append(f"category-box 불일치 {i}")
        rows.append(dict(id=i, category=lab["category"], patient=lab["patient"], image=p, size_hw=[h, w], pad=[top, left, side],
                         file_sha256=inf["file_sha256"], pixel_hash_reproduced=pixel_ok,
                         gt_yxyx_norm=[b["yxyx_norm"] for b in lab["boxes"]], gt_ann_ids=[b["ann_id"] for b in lab["boxes"]],
                         O=O[i], SFT=SFT[i],
                         det=dict(boxes_xyxy_px=d["boxes_xyxy_px"], scores=d["scores"], labels=d["labels"], img_hw=d["img_hw"])))
    prov = dict(inputs=inputs, O=o_prov, SFT=sft_prov, det=det_prov, n_rows=len(rows),
                n_pixel_hash_reproduced=sum(r["pixel_hash_reproduced"] for r in rows))
    if P:
        json.dump(P, open(f"{OUT}/problems.json", "w"), indent=1, ensure_ascii=False)
        print("PROBLEMS", len(P), P[:10])
        sys.exit(1)
    json.dump(prov, open(f"{OUT}/provenance.json", "w"), indent=1, sort_keys=True)
    s = json.dumps(dict(rows=rows), sort_keys=True)
    open(f"{OUT}/ledger.json", "w").write(s)
    print("OK", len(rows), "pixel_reproduced", prov["n_pixel_hash_reproduced"], "ledger_sha256", hashlib.sha256(s.encode()).hexdigest())


if __name__ == "__main__":
    main()
