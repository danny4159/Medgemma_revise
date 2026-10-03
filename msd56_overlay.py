"""iter_056 D6 시각 검사용 overlay: 각 case의 최대 annotation slice를 모델 입력 PNG(왼쪽)와 mask 합집합 overlay(오른쪽)로 나란히 저장.
렌더 경로는 msd56_data.render/mask_slice 와 동일 변환을 쓴다(영상·mask 정합 확인용).
"""
import json
import sys

import numpy as np
from PIL import Image

import msd56_data as D

cs = json.load(open(f"{D.DATA}/cases.json"))["chosen"]
tiles = []
for c in [x for x in cs if x["split"] == "D"]:
    flair, mask, _ = D.load_case(c["case"])
    areas = (mask > 0).sum(axis=(0, 1))
    k = int(np.argmax(areas))
    png = np.asarray(Image.open(f"{D.DATA}/png/{c['case']}_z{k:03d}.png")) if False else D.render(flair, k, c["vmin"], c["vmax"])
    m = D.mask_slice(mask, k)
    ov = png.copy()
    edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
    ov[edge] = [255, 0, 0]
    tiles.append(np.concatenate([png, ov], axis=1))
    print(c["case"], "slice", k, "area", int(areas[k]))
rows = [np.concatenate(tiles[i:i + 2], axis=1) for i in range(0, len(tiles), 2)]
Image.fromarray(np.concatenate(rows, axis=0)).save(sys.argv[1])
