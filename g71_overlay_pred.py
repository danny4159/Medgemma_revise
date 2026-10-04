"""예측 vs GT overlay (E24 영상, 시각 확인용). 사용: python g71_overlay_pred.py OUT.png PATIENT... ; 열: GT(초록) / D8(노랑) / R8(주황) / detector(청록), category 별 2행(vertebra, disc) 중 vertebra만 표시."""
import json, sys

import numpy as np
from PIL import Image, ImageDraw

import g71_analyze as A
import g71_data as D
import g71_det_stage as DS
from rsna_diag import generate as GEN

out, pids = sys.argv[1], sys.argv[2:]
cat = 'vertebra'
raw = {k: A.score_dir(f'results/iter_071/gen/E24/{k}', 'E24')['raw'] for k in ('D8', 'R8')}
man = {r['id']: r for r in json.load(open(f'{D.DATA}/manifest.json'))['rows']}
lock = json.load(open('results/iter_071/decide/e24_lock.json'))
_, rawm, _, _ = DS.score_det(json.load(open(f"{lock['detector']['run']}/infer_E24_e{lock['detector']['epoch']}.json")), 'E24', lock['detector']['threshold'])
rawm = {i: v for i, v in rawm.items()}
tiles = []
for pid in pids:
    iid = D.item_id(pid, 0, cat)
    img, _, _ = GEN.load_image(man[iid]['image'])
    for name, src, col in (('GT', None, (0, 255, 0)), ('D8', raw['D8'], (255, 255, 0)), ('R8', raw['R8'], (255, 140, 0)), ('M8', rawm, (0, 255, 255))):
        im = img.resize((320, 320))
        dr = ImageDraw.Draw(im)
        boxes = [g['yxyx_norm'] for g in man[iid]['gt']] if src is None else src[iid]['boxes']
        for y0, x0, y1, x1 in boxes:
            dr.rectangle([x0 * 0.32, y0 * 0.32, x1 * 0.32, y1 * 0.32], outline=col, width=1)
        dr.text((4, 4), f'{pid} {name}', fill=col)
        tiles.append(np.asarray(im))
rows = [np.concatenate(tiles[i:i + 4], axis=1) for i in range(0, len(tiles), 4)]
Image.fromarray(np.concatenate(rows, axis=0)).save(out)
