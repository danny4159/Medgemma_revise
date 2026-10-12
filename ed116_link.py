"""iter_116 E600 provenance 연결 (ev111_link.py 보완판; 원 ev111_link.py는 수정하지 않는다).

ev111_link 대비 보완 (iter_111 리뷰의 reuse_issues):
 (1) 원 protocol 파일의 *내용*에서 sha256(canon(locked))을 재계산해 completion.protocol_digest와 대조한다 (digest 문자열 복사 금지).
     locked 안의 비-코드 파일(요청·manifest·labels·sets·reuse manifest 등)의 현재 hash가 달라지면 거부한다. 코드 파일(.py)은
     이후 반복에서 진화했으므로 불일치를 정보로만 기록한다.
 (2) completion.per_file(worker별 record 수)과 실제 worker 파일, completion의 requests_sha256과 요청 파일을 대조한다.
 (3) 영상 file hash뿐 아니라 decoded pixel hash가 원 manifest와 다르면 거부한다.
 (4) 출력은 results/iter_116/provenance 에만 쓴다. GT가 없는 입력 ledger(ledger_nogt.json)와 평가 전용 gt.json을 분리한다.
 (5) iter_111 ledger와 내용(O 원문·SFT 원문·detector·GT)이 같은지 회귀 대조한다 (참고용; 불일치는 problems).
문제가 하나라도 있으면 ledger를 쓰지 않고 problems만 쓴 뒤 종료코드 1. 기존 파일은 덮어쓰지 않는다.
"""
import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

from rsna_diag import geometry as G

R = "results"
OUT = f"{R}/iter_116/provenance"
SETS = f"{R}/iter_016/manifests/sets.json"
LABELS = f"{R}/iter_016/manifests/labels.json"
INFER = f"{R}/iter_016/manifests/infer_manifest.jsonl"
O_STAGES = {"e180_plain": f"{R}/iter_016/gen/e180_plain__M0", "e600x_plain": f"{R}/iter_016/gen/e600x_plain__M0"}
O_REQ = {"e180_plain": f"{R}/iter_016/requests/e180_plain__M0.jsonl", "e600x_plain": f"{R}/iter_016/requests/e600x_plain__M0.jsonl"}
O_PROTO = {"e180_plain": f"{R}/iter_016/protocols/protocol_e180.json", "e600x_plain": f"{R}/iter_016/protocols/protocol_e600.json"}
SFT_DIR = f"{R}/iter_012/confirm_sft_seed17"
SFT_PROTO = f"{R}/iter_012/protocols/main_protocol.json"
SFT_REUSE = f"{R}/iter_015/reuse/bbox_B0_concise.jsonl"
DET_DIR = f"{R}/iter_035/confirm800/det17"
DET_LOCK = f"{R}/iter_035/select/LOCK.json"
DET_SEL = f"{R}/iter_035/select/seed17/v400_selection.json"
OLD_LEDGER = f"{R}/iter_111/provenance/ledger.json"
THR, EPOCH = 0.70, 18


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def canon_digest(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def jl(p):
    with open(p) as f:
        return [json.loads(x) for x in f if x.strip()]


def read_workers(d):
    rows, files, counts = [], {}, {}
    for p in sorted(glob.glob(f"{d}/gen_worker*.jsonl")):
        files[os.path.basename(p)] = fsha(p)
        r = jl(p)
        counts[os.path.basename(p)] = len(r)
        rows += r
    return rows, files, counts


def check_protocol(path, comp, P, tag):
    """원 protocol 내용 재계산 + locked 데이터 파일 현재 hash 대조. returns provenance dict."""
    proto = json.load(open(path))
    locked = proto["locked"]
    dig = canon_digest(locked)
    if dig != comp["protocol_digest"]:
        P.append(f"{tag}: protocol 내용 재계산 digest {dig} != completion {comp['protocol_digest']}")
    data_bad, code_changed, missing_code = [], [], []
    for f, h in locked.get("files", {}).items():
        if not os.path.exists(f):
            if f.endswith(".py"):
                missing_code.append(f)
            else:
                data_bad.append(f"{f}: 파일 없음")
            continue
        if fsha(f) != h:
            (code_changed if f.endswith(".py") else data_bad).append(f)
    if data_bad:
        P.append(f"{tag}: protocol 잠금 비-코드 파일 불일치 {data_bad}")
    return dict(path=path, protocol_sha256=fsha(path), recomputed_locked_digest=dig,
                n_locked=len(locked.get("files", {})), code_changed_since_lock=code_changed, code_missing_now=missing_code)


def main():
    os.makedirs(OUT, exist_ok=True)
    for fn in ("ledger_nogt.json", "gt.json", "provenance.json", "problems.json"):
        if os.path.exists(f"{OUT}/{fn}"):
            sys.exit(f"exists: {fn} 덮어쓰기 금지")
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

    # --- 존재 응답 Q_O (원 MedGemma 1.5, 어댑터 없음)
    O, o_prov = {}, {}
    for st, d in O_STAGES.items():
        reqs = jl(O_REQ[st])
        comp = json.load(open(f"{d}/completion.json"))
        rs = fsha(O_REQ[st])
        if comp["requests_sha256"] != rs or comp["n_missing"] or comp["n_duplicate"] or comp["n_extra"] or comp["returncodes"] != [0] * len(comp["returncodes"]):
            P.append(f"{st}: completion 불일치")
        if comp["adapter_digest"] is not None:
            P.append(f"{st}: adapter가 있다")
        recs, files, counts = read_workers(d)
        if counts != comp["per_file"]:
            P.append(f"{st}: worker 파일 record 수 {counts} != completion.per_file {comp['per_file']}")
        pv = check_protocol(O_PROTO[st], comp, P, st)
        rb = {}
        for r in recs:
            if r["request_id"] in rb:
                P.append(f"{st}: 중복 record {r['request_id']}")
            rb[r["request_id"]] = r
        if len(rb) != comp["n_expected"] or len(reqs) != comp["n_expected"]:
            P.append(f"{st}: record 수 {len(rb)} vs {comp['n_expected']}")
        o_prov[st] = dict(requests_sha256=rs, completion_protocol_digest=comp["protocol_digest"], config_digest=comp["config_digest"],
                          worker_files=files, adapter_digest=comp["adapter_digest"], protocol=pv)
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
                if a != b:
                    P.append(f"{st}:{q['id']} 필드 {k} 불일치 {a!r} {b!r}")
            if r["image_file_sha256"] != q["file_sha256"] or r["protocol_digest"] != comp["protocol_digest"]:
                P.append(f"{st}:{q['id']} 이미지/protocol hash 불일치")
            if q["id"] in O:
                P.append(f"중복 O {q['id']}")
            O[q["id"]] = dict(stage=st, request_id=q["request_id"], raw=r["suffix_text_raw"], ended_eos=r["ended_eos"],
                              finish_reason=r["finish_reason"], image_file_sha256=r["image_file_sha256"],
                              input_ids_sha256=r["input_ids_sha256"], prompt=q["prompt"])

    # --- SFT bbox (iter_012 seed17 concise): 원 worker 파일에서 재추출하여 reuse 파일과 대조
    reuse = {r["id"]: r for r in jl(SFT_REUSE)}
    comp = json.load(open(f"{SFT_DIR}/completion.json"))
    src_rows, sft_files, sft_counts = read_workers(SFT_DIR)
    if sft_counts != comp["per_file"]:
        P.append(f"SFT: worker 파일 record 수 {sft_counts} != completion.per_file {comp['per_file']}")
    if comp["n_missing"] or comp["n_duplicate"] or comp["n_extra"] or comp["returncodes"] != [0] * len(comp["returncodes"]):
        P.append("SFT completion 이상")
    sft_pv = check_protocol(SFT_PROTO, comp, P, "SFT")
    sb = {}
    for r in src_rows:
        if r.get("prompt_name") == "concise":
            if r["id"] in sb:
                P.append(f"SFT 중복 {r['id']}")
            sb[r["id"]] = r
    sft_prov = dict(dir=SFT_DIR, worker_files=sft_files, protocol_digest=comp.get("protocol_digest"),
                    adapter_digest=sorted({r["adapter_digest"] for r in src_rows}), n_concise=len(sb), protocol=sft_pv)
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

    # --- detector17 epoch18
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
    rows, gt = [], {}
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
        if not pixel_ok:
            P.append(f"원 영상 decoded pixel hash 불일치 {i}")
        for b in lab["boxes"]:
            c = G.canvas_to_norm(b["xyxy_px"], top, left, side)
            if max(abs(x - y) for x, y in zip(c, b["yxyx_norm"])) > 1e-3:
                P.append(f"GT px/norm 불일치 {i}")
        if (lab["category"] == "opacity") != bool(lab["boxes"]):
            P.append(f"category-box 불일치 {i}")
        rows.append(dict(id=i, patient=lab["patient"], image=p, size_hw=[h, w], pad=[top, left, side],
                         file_sha256=inf["file_sha256"], pixel_sha256=inf["pixel_sha256"], O=O[i], SFT=SFT[i],
                         det=dict(boxes_xyxy_px=d["boxes_xyxy_px"], scores=d["scores"], labels=d["labels"], img_hw=d["img_hw"])))
        gt[i] = dict(category=lab["category"], gt_yxyx_norm=[b["yxyx_norm"] for b in lab["boxes"]],
                     gt_ann_ids=[b["ann_id"] for b in lab["boxes"]])

    # --- iter_111 ledger 회귀 대조 (내용 동일성)
    if os.path.exists(OLD_LEDGER):
        old = {r["id"]: r for r in json.load(open(OLD_LEDGER))["rows"]}
        nd = 0
        for r in rows:
            o = old.get(r["id"])
            if o is None or o["O"]["raw"] != r["O"]["raw"] or o["SFT"]["raw"] != r["SFT"]["raw"] or o["det"] != r["det"] \
                    or o["category"] != gt[r["id"]]["category"] or o["gt_yxyx_norm"] != gt[r["id"]]["gt_yxyx_norm"] \
                    or o["file_sha256"] != r["file_sha256"]:
                nd += 1
        if nd or len(old) != len(rows):
            P.append(f"iter_111 ledger와 내용 불일치 {nd}행 (old {len(old)} / new {len(rows)})")
    prov = dict(inputs=inputs, O=o_prov, SFT=sft_prov, det=det_prov, n_rows=len(rows), n_pixel_hash_reproduced=len(rows) - sum(
        1 for x in P if "pixel hash" in x), old_ledger_sha256=fsha(OLD_LEDGER) if os.path.exists(OLD_LEDGER) else None)
    if P:
        json.dump(P, open(f"{OUT}/problems.json", "w"), indent=1, ensure_ascii=False)
        print("PROBLEMS", len(P), P[:10])
        sys.exit(1)
    s1 = json.dumps(dict(rows=rows), sort_keys=True)
    s2 = json.dumps(gt, sort_keys=True)
    prov["ledger_nogt_sha256"] = hashlib.sha256(s1.encode()).hexdigest()
    prov["gt_sha256"] = hashlib.sha256(s2.encode()).hexdigest()
    open(f"{OUT}/ledger_nogt.json", "x").write(s1)
    open(f"{OUT}/gt.json", "x").write(s2)
    json.dump(prov, open(f"{OUT}/provenance.json", "x"), indent=1, sort_keys=True)
    print("OK", len(rows), "ledger_nogt_sha256", prov["ledger_nogt_sha256"], "gt_sha256", prov["gt_sha256"])


if __name__ == "__main__":
    main()
