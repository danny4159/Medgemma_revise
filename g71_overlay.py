"""GT bbox overlay 몽타주 (시각 확인용). 사용: python g71_overlay.py out.png pid1 pid2 ...  (padding canvas 좌표로 vertebra=초록, disc=빨강)"""
import json, sys

import numpy as np
from PIL import Image, ImageDraw

import g71_data as D
from rsna_diag import generate as GEN

man = json.load(open(f'{D.DATA}/manifest.json'))
out, pids = sys.argv[1], sys.argv[2:]
tiles = []
for pid in pids:
    for off in ('m1', 'c', 'p1'):
        rows = [r for r in man['rows'] if r['patient'] == pid and D.OFF_NAME[r['offset']] == off]
        img, aff, _ = GEN.load_image(rows[0]['image'])
        im = img.resize((384, 384))
        dr = ImageDraw.Draw(im)
        for r in rows:
            col = (0, 255, 0) if r['category'] == 'vertebra' else (255, 0, 0)
            for g in r['gt']:
                y0, x0, y1, x1 = [v * 384 / 1000 for v in g['yxyx_norm']]
                dr.rectangle([x0, y0, x1, y1], outline=col, width=1)
        dr.text((4, 4), f'{pid} {off}', fill=(255, 255, 0))
        tiles.append(np.asarray(im))
rows_ = [np.concatenate(tiles[i:i + 3], axis=1) for i in range(0, len(tiles), 3)]
Image.fromarray(np.concatenate(rows_, axis=0)).save(out)
