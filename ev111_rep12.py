"""대표 12명(범주별 sha256(id) 오름차순 4명) 연결 점검: 영상·GT·detector·SFT 박스 overlay와 존재 응답 원문. 지표 계산 없음."""
import hashlib
import json
import os
import sys

from PIL import Image, ImageDraw

import ev109_extract as X
import ev111_core as C

OUT = "results/iter_111/rep12"


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(f"{OUT}/rep12.json"):
        sys.exit("exists")
    rows = json.load(open("results/iter_111/provenance/ledger.json"))["rows"]
    P = {p["id"]: p for p in C.prep(rows)}
    sel = []
    for c in C.CATS:
        ids = sorted((r["id"] for r in rows if r["category"] == c), key=lambda i: hashlib.sha256(i.encode()).hexdigest())[:4]
        sel += ids
    R = {r["id"]: r for r in rows}
    tiles, info = [], []
    for i in sel:
        r, p = R[i], P[i]
        im = Image.open(r["image"]).convert("RGB")
        w, h = im.size
        top, left, side = r["pad"]
        d = ImageDraw.Draw(im)

        def px(b):  # yxyx norm -> pixel(원본, padding 0일 때 동일)
            return [b[1] * side / 1000 - left, b[0] * side / 1000 - top, b[3] * side / 1000 - left, b[2] * side / 1000 - top]
        for b in p["gt"]:
            d.rectangle(px(b), outline=(0, 255, 0), width=4)
        for b in p["det"]:
            d.rectangle(px(b), outline=(255, 0, 0), width=3)
        for b in p["sft"]:
            d.rectangle(px(b), outline=(0, 128, 255), width=3)
        tiles.append(im.resize((384, 384)))
        info.append(dict(id=i, category=p["cat"], size=[h, w], n_gt=len(p["gt"]), n_det=len(p["det"]), det_scores=p["det_scores"],
                         sft_status=p["sft_status"], n_sft=len(p["sft"]), O_raw=r["O"]["raw"][:120], ans=p["ans"], ans_source=p["ans_source"],
                         O_prompt=r["O"]["prompt"], request_id=r["O"]["request_id"]))
    W = Image.new("RGB", (384 * 4, 384 * 3))
    for n, t in enumerate(tiles):
        W.paste(t, ((n % 4) * 384, (n // 4) * 384))
    W.save(f"{OUT}/overlay12.png")
    json.dump(info, open(f"{OUT}/rep12.json", "w"), indent=1, ensure_ascii=False)
    for x in info:
        print(x["id"], x["category"], "gt", x["n_gt"], "det", x["n_det"], "sft", x["sft_status"], x["n_sft"], "ans", x["ans"], x["ans_source"], repr(x["O_raw"][:50]))
    print(info[0]["O_prompt"])


if __name__ == "__main__":
    main()
