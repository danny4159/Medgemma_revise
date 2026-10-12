"""iter_112: 기술 집단의 모델 입력 box(MedRegA 0-999 좌표를 영상으로 되돌림, 적색)와 GT(녹색), 원 detector box(황색 점선 대신 얇은 선)를 겹친 확인용 montage."""
import json

from PIL import Image, ImageDraw

man = json.load(open("results/iter_112/data/manifest.json"))
gt = json.load(open("results/iter_112/data/gt.json"))
rows = {r["id"]: r for r in man["rows"]}
reg = [q for q in man["requests"] if q["group"] == "tech" and q["kind"] == "region"][:12]
tiles = []
for q in reg:
    r = rows[q["id"]]
    im = Image.open(r["image"]).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    for g in gt[q["id"]]["boxes_xyxy_px"]:
        d.rectangle(g, outline=(0, 255, 0), width=4)
    b = next(x for x in r["boxes"] if x["det_index"] == q["det_index"])
    d.rectangle(b["xyxy_px"], outline=(255, 255, 0), width=1)
    x1, y1, x2, y2 = q["box"]
    d.rectangle((x1 / 1000 * w, y1 / 1000 * h, x2 / 1000 * w, y2 / 1000 * h), outline=(255, 0, 0), width=3)
    tiles.append(im.resize((340, 340)))
W = Image.new("RGB", (340 * 4, 340 * 3))
for i, t in enumerate(tiles):
    W.paste(t, ((i % 4) * 340, (i // 4) * 340))
W.save("results/iter_112/data/overlay_tech12.png")
print("ok", len(tiles))
