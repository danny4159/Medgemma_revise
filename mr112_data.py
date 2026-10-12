"""iter_112: confirm800 중 E600 밖 200명을 detector17 저장 출력·GT·영상과 연결하고 요청 manifest를 만든다.
GT는 gt.json에 분리하고 요청에는 넣지 않는다. 문제가 있으면 manifest 없이 problems.json만 쓰고 종료코드 1. 덮어쓰기 금지."""
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

import mr112_spec as S

R = "results"
OUT = f"{R}/iter_112/data"
CONFIRM = f"{R}/iter_010/manifests/confirm_ids.json"
TRAIN = f"{R}/iter_010/manifests/train_ids.json"
VAL = f"{R}/iter_010/manifests/validation_ids.json"
GT = f"{R}/iter_010/manifests/gt_manifest.json"
INFER = f"{R}/iter_010/manifests/infer_manifest.jsonl"
SETS = f"{R}/iter_016/manifests/sets.json"
DET_DIR = f"{R}/iter_035/confirm800/det17"
DET_LOCK = f"{R}/iter_035/select/LOCK.json"
DET_SEL = f"{R}/iter_035/select/seed17/v400_selection.json"


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(f"{OUT}/manifest.json") or os.path.exists(f"{OUT}/problems.json"):
        sys.exit("exists")
    P = []
    confirm = json.load(open(CONFIRM))
    gt = json.load(open(GT))
    infer = {}
    for l in open(INFER):
        r = json.loads(l)
        infer[r["id"]] = r
    e600 = {i for v in json.load(open(SETS))["E600"].values() for i in v}
    train = set(json.load(open(TRAIN)))
    val = set(json.load(open(VAL)))
    ids = sorted(set(confirm) - e600)
    if len(confirm) != 800 or len(e600) != 600 or not e600 <= set(confirm) or len(ids) != 200:
        P.append(f"confirm/E600 구성 {len(confirm)} {len(e600)} {len(ids)}")
    # detector 출처 검증 (ev111_link 규약과 동일한 내용 hash 대조)
    comp = json.load(open(f"{DET_DIR}/completion.json"))
    sel = json.load(open(DET_SEL))
    lock = json.load(open(DET_LOCK))
    if fsha(f"{DET_DIR}/raw_preds.json") != comp["raw_preds_sha256"]:
        P.append("det raw_preds hash")
    for fn, h in comp["shard_sha256"].items():
        if fsha(f"{DET_DIR}/{fn}") != h:
            P.append(f"det shard {fn}")
    if lock["files"]["seed17"]["sha256"] != fsha(DET_SEL):
        P.append("LOCK-selection hash")
    if sel["selected"]["epoch"] != S.EPOCH or sel["selected"]["threshold"] != S.THR:
        P.append("epoch/threshold")
    if comp["checkpoint_sha256"] != sel["selected_checkpoint_sha256"] or fsha(comp["checkpoint"]) != comp["checkpoint_sha256"]:
        P.append("checkpoint hash")
    if comp["manifest_path"].split("research/")[-1] != CONFIRM:
        P.append("completion manifest path")
    det = json.load(open(f"{DET_DIR}/raw_preds.json"))
    # 환자 분리: 이 200명과 train/validation/E600의 id·patient·pixel hash 교집합
    pat = {i: gt[i]["patient"] for i in gt}
    bad_pat = {pat[i] for i in ids} & {pat[i] for i in (train | val | e600) if i in pat}
    pix_other = {infer[i]["pixel_sha256"] for i in (train | val | e600) if i in infer}
    bad_pix = [i for i in ids if infer[i]["pixel_sha256"] in pix_other]
    if bad_pat or bad_pix or set(ids) & (train | val | e600):
        P.append(f"환자/영상 중복 pat={sorted(bad_pat)[:5]} pix={bad_pix[:5]}")
    if len({pat[i] for i in ids}) != 200:
        P.append("id-patient 1:1 아님")
    rows, gts, boxes_all = [], {}, []
    for i in ids:
        g, inf, d = gt[i], infer[i], det[i]
        p = inf["image"]
        if fsha(p) != inf["file_sha256"]:
            P.append(f"file hash {i}")
        im = Image.open(p)
        w, h = im.size
        if hashlib.sha256(np.asarray(im).tobytes()).hexdigest() != inf["pixel_sha256"]:
            P.append(f"pixel hash {i}")
        if g["pixel_sha256"] != inf["pixel_sha256"] or list(d["img_hw"]) != [h, w]:
            P.append(f"gt/det 연결 {i}")
        if (g["category"] == "opacity") != bool(g["boxes"]):
            P.append(f"category-box {i}")
        keep = [(k, b, s) for k, (b, s, l) in enumerate(zip(d["boxes_xyxy_px"], d["scores"], d["labels"])) if l == 1 and s >= S.THR]
        gts[i] = dict(category=g["category"], boxes_xyxy_px=[b["xyxy_px"] for b in g["boxes"]], ann_ids=[b["ann_id"] for b in g["boxes"]])
        rows.append(dict(id=i, patient=pat[i], image=p, size_wh=[w, h], file_sha256=inf["file_sha256"], pixel_sha256=inf["pixel_sha256"],
                         tech_key=S.tech_key(pat[i]), boxes=[dict(det_index=k, xyxy_px=b, score=s, medrega=list(S.box_to_medrega(b, w, h)))
                                                            for k, b, s in keep]))
    elig = sorted([r for r in rows if r["boxes"]], key=lambda r: r["tech_key"])
    tech = [r["id"] for r in elig[:S.TECH_N]]
    main_ids = sorted(r["id"] for r in elig[S.TECH_N:])
    by = {r["id"]: r for r in rows}
    req = []
    for i in tech:  # 최고 confidence box 하나(동률은 낮은 det_index)
        b = sorted(by[i]["boxes"], key=lambda x: (-x["score"], x["det_index"]))[0]
        req.append(dict(group="tech", id=i, det_index=b["det_index"], kind="region", box=b["medrega"]))
        req.append(dict(group="tech", id=i, det_index=b["det_index"], kind="full", box=list(S.FULL_BOX)))
    for i in main_ids:
        for b in by[i]["boxes"]:
            req.append(dict(group="main", id=i, det_index=b["det_index"], kind="region", box=b["medrega"]))
        req.append(dict(group="main", id=i, det_index=-1, kind="full", box=list(S.FULL_BOX)))
    for q in req:
        q["prompt"] = S.prompt(q["box"])
        q["target"] = S.TARGET
        q["request_id"] = hashlib.sha256(json.dumps([q["group"], q["id"], q["det_index"], q["kind"], q["box"]]).encode()).hexdigest()[:16]
    if len({q["request_id"] for q in req}) != len(req):
        P.append("request_id 중복")
    if P:
        json.dump(P, open(f"{OUT}/problems.json", "w"), indent=1)
        print("PROBLEMS", P[:10])
        sys.exit(1)
    json.dump(gts, open(f"{OUT}/gt.json", "w"), indent=1, sort_keys=True)
    main_boxes = sum(len(by[i]["boxes"]) for i in main_ids)
    man = dict(spec=dict(prompt_head=S.HEAD, prompt_tail=S.TAIL, target=S.TARGET, thr=S.THR, epoch=S.EPOCH, k_frac=S.K_FRAC),
               inputs={k: fsha(v) for k, v in dict(confirm=CONFIRM, gt=GT, infer=INFER, sets=SETS, det_lock=DET_LOCK, det_sel=DET_SEL,
                                                    det_raw=f"{DET_DIR}/raw_preds.json", det_completion=f"{DET_DIR}/completion.json",
                                                    spec="mr112_spec.py", train=TRAIN, val=VAL).items()},
               counts=dict(non_e600=len(ids), nonempty=len(elig), tech_patients=len(tech), main_patients=len(main_ids), main_boxes=main_boxes,
                           main_region_requests=main_boxes, main_full_requests=len(main_ids), tech_requests=2 * len(tech),
                           n_requests=len(req), all_boxes=sum(len(r["boxes"]) for r in rows)),
               tech_ids=tech, main_ids=main_ids, rows=rows, requests=req)
    open(f"{OUT}/manifest.json", "w").write(json.dumps(man, sort_keys=True, indent=1))
    print("OK", man["counts"])


if __name__ == "__main__":
    main()
