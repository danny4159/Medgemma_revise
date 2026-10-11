"""기술 표본 시각 감사용 overlay: 원본(예측 box·enclosing·중앙 rect 표시) | T crop | C crop. results/iter_108/tech/overlays 에 새로 저장."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import ev108_build as B

geo = json.load(open(B.DATA / "geometry.json"))
st = json.load(open(B.DATA / "stage_patients.json"))
out = B.R108 / "tech/overlays"
out.mkdir(parents=True, exist_ok=True)
for pid in st["stages"]["TECH"]:
    g = geo[pid]
    canvas, _, _ = B.load_canvas(g["orig_image"])
    side = g["side"]
    im = Image.fromarray(canvas).copy()
    d = ImageDraw.Draw(im)
    for b in g["boxes_yxyx"]:
        d.rectangle([b[1] * side / 1000, b[0] * side / 1000, b[3] * side / 1000, b[2] * side / 1000], outline=(255, 0, 0), width=3)
    x0, y0, x1, y1 = g["rect_T"]
    d.rectangle([x0, y0, x1, y1], outline=(0, 255, 0), width=3)
    x0, y0, x1, y1 = g["rect_C"]
    d.rectangle([x0, y0, x1, y1], outline=(0, 128, 255), width=3)
    t = Image.open(B.ROOT / g["images"]["T"]["path"]).resize((side // 2, side // 2))
    c = Image.open(B.ROOT / g["images"]["C"]["path"]).resize((side // 2, side // 2))
    im = im.resize((side // 2, side // 2))
    W = Image.new("RGB", (3 * side // 2, side // 2))
    W.paste(im, (0, 0))
    W.paste(t, (side // 2, 0))
    W.paste(c, (side, 0))
    p = out / f"{pid}.png"
    if p.exists():
        sys.exit(f"exists {p}")
    W.save(p)
    print(pid, g["rect_T"], g["rect_C"], round(g["area_ratio"], 3), g["n_boxes"], g["T_equals_C"])
