"""iter_045 D8 동작 확인 (venv 실행): checkpoint strict load, 공식 dataset 경로와 wrapper 입력 tensor 일치, 좌표 왕복,
confidence·threshold·WBF 순서, batch 1 vs N 정합성, empty/복수 box fixture.  GT는 좌표 역변환 검사에만 쓰고 운영점 선택에 쓰지 않는다.

python mg45_vrun.py mg45_d8.py --out results/iter_045/d8/d8_check.json   (CUDA_VISIBLE_DEVICES로 장치 지정)
"""
import argparse
import ast
import json
import os
import sys
import time

import mg45_mg as M

MAN = "results/iter_043/data/manifest_private.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    import numpy as np
    import pandas as pd
    import torch
    dev = torch.device("cuda:0")
    man = json.load(open(MAN))
    d24 = {e["PatientID"]: e for e in man["D24"]}
    d8 = [d24[p] for p in man["D8"]]
    tf = M.val_transform()
    res = {"manifest_sha256": M.file_sha(MAN), "n_d8": len(d8), "checks": {}}

    # --- 공식 dataset 경로와 wrapper 입력 일치 ---
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    csv = os.path.join(os.path.dirname(a.out), "official_dataset_input.csv")
    rows = []
    for e in d8:
        for t in ("qA", "qB"):
            rows.append({"image_id": e["ImageID"], "split": "test", "sentence_en": e["sentences"][t],
                         "labels": str(["cardiomegaly"]),  # 범주는 공식 dataset의 lookup 통과용 더미 (모델 입력 아님)
                         "boxes": str([list(map(float, b)) for b in e["gt_boxes_xyxy_norm"][t]])})
    pd.DataFrame(rows).to_csv(csv, index=False)
    from dataloaders.dataset import GMPGPadChestDataset
    ds = GMPGPadChestDataset(csv, csv, "results/iter_039/data/images", split="test", transform=tf)
    items, affs, tens, phrases, gts_c = [], [], [], [], []
    tdiff, bdiff, aff_ok = [], [], []
    for i, r in enumerate(rows):
        e = d24[man["D8"][i // 2]]
        t = "qA" if i % 2 == 0 else "qB"
        ten, aff, u8 = M.prepare(e["image"], tf)
        assert u8 == e["u8_pixel_sha256"], "decoded u8 pixel hash != manifest"
        o = ds[i]
        tdiff.append(float((o["image"] - ten).abs().max()))
        # GT를 공식 transform이 변환한 canvas cxcywh vs 우리 affine으로 변환한 값
        W, H = aff["r"] - aff["l"], aff["b"] - aff["t"]
        mine = []
        for x0, y0, x1, y1 in e["gt_boxes_xyxy_norm"][t]:
            cx0, cy0, cx1, cy1 = aff["l"] + x0 * W, aff["t"] + y0 * H, aff["l"] + x1 * W, aff["t"] + y1 * H
            mine.append([(cx0 + cx1) / 2, (cy0 + cy1) / 2, cx1 - cx0, cy1 - cy0])
        off = o["bboxes"].numpy()
        bdiff.append(float(np.abs(np.array(mine) - off).max()) if len(mine) == len(off) and len(off) else (0.0 if len(mine) == len(off) else 9.0))
        aff_ok.append(aff)
        tens.append(ten)
        phrases.append(e["sentences"][t])
        gts_c.append(e["gt_boxes_xyxy_norm"][t])
        items.append((e["PatientID"], t))
    res["checks"]["official_dataset_tensor_max_abs_diff"] = max(tdiff)
    res["checks"]["official_dataset_gt_box_vs_affine_max_abs_diff"] = max(bdiff)
    res["checks"]["n_items"] = len(items)
    res["affines"] = {f"{p}|{t}": {k: aff_ok[i][k] for k in aff_ok[i]} for i, (p, t) in enumerate(items)}
    # affine이 정수 resize/padding과 일치하는지 (shape 기준 독립 계산)
    ind = []
    for i, e_ in enumerate(aff_ok):
        sc = 640.0 / max(e_["h"], e_["w"])
        nh, nw = round(e_["h"] * sc), round(e_["w"] * sc)
        ind.append(abs((e_["r"] - e_["l"]) * 640 - nw) < 1e-3 and abs((e_["b"] - e_["t"]) * 640 - nh) < 1e-3 and
                   abs(e_["l"] * 640 - (640 - nw) // 2) < 1.0 and abs(e_["t"] * 640 - (640 - nh) // 2) < 1.0)
    res["checks"]["affine_matches_integer_resize_pad"] = all(ind)

    res["models"] = {}
    for key in ("P", "MS"):
        t0 = time.time()
        model, cfg, load = M.load_model(key, dev)
        assert not load["missing"] and not load["unexpected"], load
        r = {"load_s": time.time() - t0, "state_keys": load["n_state_keys"], "ckpt_sha256": M.file_sha(M.WEIGHTS[key]),
             "text_encoder_type": cfg.text_encoder_type, "grounding_threshold_cfg": cfg.grounding_threshold,
             "num_queries": cfg.num_queries}
        lg1, bx1 = [], []
        for i in range(len(items)):
            l, b = M.forward(model, [tens[i]], [phrases[i]], dev)
            lg1.append(l[0])
            bx1.append(b[0])
        lg1, bx1 = torch.stack(lg1), torch.stack(bx1)
        r["batch_compare"] = {}
        for bs in (4, 8, 16):
            lgs, bxs = [], []
            for s in range(0, len(items), bs):
                l, b = M.forward(model, tens[s:s + bs], phrases[s:s + bs], dev)
                lgs.append(l)
                bxs.append(b)
            lgb, bxb = torch.cat(lgs), torch.cat(bxs)
            r["batch_compare"][bs] = {"max_abs_logit_diff": float((lgb - lg1).abs().max()), "max_abs_box_diff": float((bxb - bx1).abs().max())}
        # confidence/threshold/WBF 순서 검사
        probs = torch.softmax(lg1, dim=-1)[..., 0]
        order = {}
        for thr in M.THRESHOLDS + [1.0]:
            det = M.postprocess(lg1, bx1, thr)
            exp_n = (probs > thr).sum(1).tolist()
            order[str(thr)] = {"pre_wbf_n_equals_softmax0_gt_thr": [d["pre_wbf_n"] for d in det] == exp_n,
                               "n_after_wbf_mean": float(np.mean([len(d["boxes"]) for d in det])),
                               "n_empty": sum(len(d["boxes"]) == 0 for d in det),
                               "max_after_wbf_leq_pre": all(len(d["boxes"]) <= d["pre_wbf_n"] for d in det)}
        r["threshold_wbf"] = order
        # cxcywh 해석 검사: query box를 cxcywh로 보았을 때 [0,1] 범위 안(sigmoid)이며 w,h>0, 원본 좌표 변환 후 영상 안쪽 비율
        cx = bx1.reshape(-1, 4).numpy()
        r["raw_box_range"] = {"min": float(cx.min()), "max": float(cx.max())}
        # 복수 box fixture: 공식 WBF에 겹치지 않는 두 box + 하나의 empty
        fx = [{"boxes": torch.tensor([[0.3, 0.3, 0.2, 0.2], [0.7, 0.7, 0.2, 0.2]]), "scores": torch.tensor([0.9, 0.8])},
              {"boxes": torch.zeros((0, 4)), "scores": torch.zeros((0,))}]
        from utils.box_utils import run_wbf
        o = run_wbf(fx, iou_threshold=0.1, skip_box_threshold=0.0)
        r["wbf_fixture"] = {"two_disjoint_boxes_kept": len(o[0]["boxes"]) == 2, "empty_ok": len(o[1]["boxes"]) == 0,
                            "roundtrip_cxcywh_maxdiff": float((o[0]["boxes"][np.argsort([-s for s in o[0]["scores"].tolist()])] - fx[0]["boxes"]).abs().max())}
        # GT 대비 좌표 sanity (원본 정규화 변환; 운영점 선택 아님): 5 query 중 최대 IoU의 평균
        from rsna_diag import metrics
        best = []
        for i, (p, t) in enumerate(items):
            ob = M.canvas_cxcywh_to_orig_xyxy(bx1[i].tolist(), aff_ok[i])
            ious = [metrics.iou(q, g) for q in ob for g in gts_c[i]] or [0.0]
            best.append(max(ious))
        r["gt_sanity_mean_best_query_iou_orig_coords"] = float(np.mean(best))
        res["models"][key] = r
        del model
        torch.cuda.empty_cache()
    res["torch"] = torch.__version__
    res["cuda_visible"] = os.environ.get("CUDA_VISIBLE_DEVICES")
    res["peak_mem_alloc_gb"] = torch.cuda.max_memory_allocated() / 2**30
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({"checks": res["checks"], "models": {k: {kk: vv for kk, vv in v.items() if kk in ("batch_compare", "gt_sanity_mean_best_query_iou_orig_coords", "raw_box_range")} for k, v in res["models"].items()}}, indent=1))


if __name__ == "__main__":
    main()
