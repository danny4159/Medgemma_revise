"""iter_039 D 대표 영상의 GT overlay (원본 좌표계 + padded 모델 좌표계 왕복 확인). 결과: results/iter_039/overlays/ (private)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import pg39_spec as S
from rsna_diag import generate as G
from rsna_diag import geometry

OUT = "results/iter_039/overlays"
os.makedirs(OUT, exist_ok=True)
rows = [json.loads(l) for l in open("results/iter_039/data/manifest_private.jsonl")]
D = [r for r in rows if r["set"] == "D"][:12]
bad = 0
for r in D:
    m = r["image_meta"]
    img, aff, px = G.load_image(m["path"])
    assert px and img.size[0] == img.size[1] == aff[2]
    assert Image.open(m["path"]).size == (m["w"], m["h"])
    d = ImageDraw.Draw(img)
    side = aff[2]
    for k, col in (("qA", (255, 0, 0)), ("qB", (0, 128, 255))):
        cb = S.gt_to_canvas(r["gt_boxes_xyxy_norm"][k], m["h"], m["w"])
        for b, orig in zip(cb, r["gt_boxes_xyxy_norm"][k]):
            back = geometry.norm_to_canvas(b, *aff)
            want = [orig[0] * m["w"], orig[1] * m["h"], orig[2] * m["w"], orig[3] * m["h"]]
            if max(abs(x - y) for x, y in zip(back, want)) > 1e-6:
                bad += 1
            y0, x0, y1, x1 = [v * side / 1000 for v in b]
            d.rectangle([x0, y0, x1, y1], outline=col, width=4)
    img.resize((768, 768)).save(f"{OUT}/D_{r['PatientID'][:8]}_{r['ImageID'][:10]}.png")
print("roundtrip_bad", bad, "n", len(D))
