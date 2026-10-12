"""iter_118 detector17 epoch18 추론 (GT 없는 loader). natten_py310 환경에서 `conda run -p ... python ed118_det.py ...` 로 실행한다.

- 체크포인트 SHA256을 확인한다 (576b8d78...). threshold/NMS/cap은 변경하지 않는다 (box_score_thresh 0.001 원시 출력 저장, 0.70 적용은 평가 명세에서).
- 입력은 ledger의 PNG만 읽는다. ed118_guard로 private 경로 접근이 거부·기록된다.
- 명령: infer --ledger L --out raw_preds.json   /  regress --out R.json  (기존 확인 영상 2개의 threshold 후 box/score 회귀 대조)
"""
import argparse
import hashlib
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import ed118_guard  # noqa: E402

CKPT = f"{BASE}/results/iter_035/train/seed17/epoch_18/model.pt"
CKPT_SHA = "576b8d789ef5f9e1924d7ad6e56954d51589dc437eaa12215874ce77cd3cc76c"
THR = 0.70
OLD_RAW = f"{BASE}/results/iter_035/confirm800/det17/raw_preds.json"
OLD_INFER = f"{BASE}/results/iter_010/manifests/infer_manifest.jsonl"


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def load_model(device):
    import torch
    from rsna_diag import det_lib
    if fsha(CKPT) != CKPT_SHA:
        raise RuntimeError("checkpoint sha256 불일치")
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    model = det_lib.build_model()
    model.load_state_dict(ck["model"])
    model.to(device).eval()
    return torch, model


def run(paths):
    import numpy as np
    from PIL import Image
    from rsna_diag import geometry as G
    device = "cuda"
    torch, model = load_model(device)
    out = {}
    with torch.no_grad():
        for key, path in paths:
            arr = np.array(Image.open(path))
            rgb = G.to_uint8_rgb_preserving(arr)
            h, w = rgb.shape[:2]
            img = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
            pr = model([img.to(device)])[0]
            out[key] = {"boxes_xyxy_px": pr["boxes"].cpu().numpy().tolist(), "scores": pr["scores"].cpu().numpy().tolist(),
                        "labels": pr["labels"].cpu().numpy().tolist(), "img_hw": [h, w]}
    return out, torch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["infer", "regress"])
    ap.add_argument("--ledger")
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    for p in (a.out, a.log):
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    ed118_guard.install([f"{BASE}/results/iter_118/private", f"{BASE}/results/iter_010/manifests/gt_manifest.json",
                         f"{BASE}/results/iter_009/manifests/gt_manifest.json"], a.log)
    if os.path.exists(a.out):
        sys.exit("출력 존재: 덮어쓰지 않는다")
    t0 = time.time()
    if a.cmd == "infer":
        rows = json.load(open(a.ledger))["rows"]
        pred, torch = run([(r["id"], os.path.join(BASE, r["image"])) for r in rows])
        res = dict(checkpoint_sha256=CKPT_SHA, ledger_sha256=fsha(a.ledger), threshold_applied_later=THR, n=len(pred), preds=pred,
                   torch=torch.__version__, device=torch.cuda.get_device_name(0), wall_s=time.time() - t0,
                   cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"))
    else:
        old = json.load(open(OLD_RAW))
        inf = {}
        for ln in open(OLD_INFER):
            r = json.loads(ln)
            inf[r["id"]] = r["image"]
        ids = []
        for k in sorted(old):  # 임계값 이상 box가 있는 영상 1개 + 없는 영상 1개 (결정적 선택: 정렬 순 첫 항목)
            has = any(s >= THR for s in old[k]["scores"])
            if has and sum(1 for i in ids if i[1]) == 0:
                ids.append((k, True))
            elif not has and sum(1 for i in ids if not i[1]) == 0:
                ids.append((k, False))
            if len(ids) == 2:
                break
        pred, torch = run([(k, os.path.join(BASE, inf[k])) for k, _ in ids])
        cmp = []
        for k, has in ids:
            o, n = old[k], pred[k]
            oo = [(s, b) for s, b in zip(o["scores"], o["boxes_xyxy_px"]) if s >= THR]
            nn = [(s, b) for s, b in zip(n["scores"], n["boxes_xyxy_px"]) if s >= THR]
            md = max((abs(x - y) for (s1, b1), (s2, b2) in zip(oo, nn) for x, y in list(zip(b1, b2)) + [(s1, s2)]), default=0.0)
            cmp.append(dict(id=k, old_has_box=has, n_old=len(oo), n_new=len(nn), max_abs_diff=md,
                            n_all_old=len(o["scores"]), n_all_new=len(n["scores"])))
        res = dict(cmp=cmp, ok=all(c["n_old"] == c["n_new"] and c["max_abs_diff"] < 0.05 for c in cmp), tolerance="box px/score abs <0.05")
    with open(a.out, "x") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("preds",)}, default=str)[:1500])


if __name__ == "__main__":
    main()
