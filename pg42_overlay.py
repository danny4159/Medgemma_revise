"""iter_042 양성 GT box 완결성 확인용 contact sheet (모델 출력 미사용). results/iter_042/data/overlays/ 에 저장 (private)."""
import json
import os

from PIL import Image, ImageDraw

OUT = "results/iter_042/data/overlays"


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = [json.loads(l) for l in open("results/iter_042/data/manifest_private.jsonl")]
    pos = [r for r in rows if r["set"] == "E" and r["group"] == "pos"]
    per, cols, tile = 10, 5, 420
    for s in range(0, len(pos), per):
        chunk = pos[s:s + per]
        sheet = Image.new("RGB", (cols * tile, ((len(chunk) + cols - 1) // cols) * (tile + 16)), "black")
        for k, r in enumerate(chunk):
            im = Image.open(r["image_meta"]["path"]).convert("RGB")
            w, h = im.size
            sc = tile / max(w, h)
            im = im.resize((int(w * sc), int(h * sc)))
            d = ImageDraw.Draw(im)
            for b in r["gt_boxes_xyxy_norm"]["qA"]:
                d.rectangle([b[0] * im.width, b[1] * im.height, b[2] * im.width, b[3] * im.height], outline=(255, 0, 0), width=3)
            x, y = (k % cols) * tile, (k // cols) * (tile + 16)
            sheet.paste(im, (x, y + 16))
            ImageDraw.Draw(sheet).text((x + 2, y + 2), f"#{s + k} {r['ImageID'][:8]} n={len(r['gt_boxes_xyxy_norm']['qA'])}", fill="white")
        sheet.save(f"{OUT}/pos_sheet_{s // per}.png")
    print(len(pos))


if __name__ == "__main__":
    main()
