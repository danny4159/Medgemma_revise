"""iter_037 overlay: det37 GT 감사 행에서 범주별 최대 6명(hash 순서, 성능 무관)을 골라 분류 근거를 그린다.
초록=GT, 빨강=detector 선택 후보, 파랑=SFT17, 노랑=GT의 IoU>=0.3 최고 score 후보(index·score 표기, threshold 아래 포함),
주황=최대 IoU 후보(index). 사용: python rsna_diag/det37_overlay.py --report_dir <det37 결과 dir> --det 17|29 --out_dir <새 dir>"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det37 as T  # noqa: E402
from rsna_diag import geometry as G  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report_dir", required=True)
    ap.add_argument("--det", type=int, required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--split", default="confirm800")
    a = ap.parse_args()
    if os.path.exists(a.out_dir):
        raise FileExistsError(a.out_dir)
    ctx = T.Ctx(a.split, sft_seeds=[17])
    rows = [json.loads(l) for l in open(f"{a.report_dir}/audit/det{a.det}__selected__gt_audit.jsonl")]
    thr = ctx.operating_points(a.det)["selected"]
    key = "sft17_only_category@0.3"
    os.makedirs(a.out_dir)
    manifest = {}
    for cat in T.CATS:
        pats = sorted({r["patient"] for r in rows if r[key] == cat}, key=T.DA.sha_str)[:6]
        manifest[cat] = pats
        for pid in pats:
            im = Image.open(f"{T.BASE}/{ctx.infer[pid]['image']}").convert("RGB")
            top, left, side = G.pad_offsets(im.size[1], im.size[0])
            canvas = Image.new("RGB", (side, side))
            canvas.paste(im, (left, top))
            dr = ImageDraw.Draw(canvas)
            px = lambda b: (b[1] / 1000 * side, b[0] / 1000 * side, b[3] / 1000 * side, b[2] / 1000 * side)
            cands = {c["idx"]: c for c in ctx.cands[a.det][pid]}
            for b in ctx.gt[pid]["boxes"]:
                dr.rectangle(px(b["yxyx_norm"]), outline=(0, 255, 0), width=4)
            for c in cands.values():
                if c["score"] >= thr:
                    dr.rectangle(px(c["box"]), outline=(255, 0, 0), width=3)
            for b in ctx.sft[17][pid]["boxes"]:
                dr.rectangle(px(b), outline=(0, 128, 255), width=3)
            for r in [r for r in rows if r["patient"] == pid and r[key] == cat]:
                ts = r["top_score_cand_iou_ge_0.3"]
                if ts:
                    c = cands[ts[1]]
                    dr.rectangle(px(c["box"]), outline=(255, 255, 0), width=2)
                    dr.text((px(c["box"])[0] + 3, px(c["box"])[1] + 3), f"idx{ts[1]} s={ts[0]:.3f}", fill=(255, 255, 0))
                if r["max_iou_all_idx"] is not None:
                    c = cands[r["max_iou_all_idx"]]
                    dr.rectangle(px(c["box"]), outline=(255, 140, 0), width=2)
                    dr.text((px(c["box"])[0] + 3, px(c["box"])[3] - 12), f"maxIoU idx{r['max_iou_all_idx']} {r['max_iou_all']:.2f} s={c['score']:.3f}", fill=(255, 140, 0))
            canvas.resize((768, 768)).save(os.path.join(a.out_dir, f"{cat}__{pid}.png"))
    with open(os.path.join(a.out_dir, "manifest.json"), "w") as f:
        json.dump({"det": a.det, "threshold": thr, "patients_by_category": manifest}, f, indent=1)
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
