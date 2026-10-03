"""감사용 contact sheet(모델 입력 아님). 사용: python mri61_sheet.py <out_png> <cluster_id>... """
import json, sys, math
from PIL import Image, ImageDraw

lock = json.load(open('results/iter_061/data/selection_lock.json'))
allc = {r['cluster_id']: r for r in lock['D'] + lock['E_ordered_multi'] + lock['E_single_ordered']}
out, cids = sys.argv[1], sys.argv[2:]
T = 224
rows = []
for c in cids:
    r = allc[c]
    ims = []
    for p in r['images']:
        im = Image.open(f'results/iter_061/data/images/{p}').convert('RGB')
        im.thumbnail((T, T))
        ims.append((p, im))
    rows.append((c, ims))
ncol = max(min(len(i), 6) for _, i in rows)
H = 0
tiles = []
for c, ims in rows:
    nr = math.ceil(len(ims) / 6)
    tiles.append(nr)
W = 6 * T
canvas = Image.new('RGB', (W, sum(t * (T + 14) + 14 for t in tiles)), 'white')
dr = ImageDraw.Draw(canvas)
y = 0
for (c, ims), nr in zip(rows, tiles):
    dr.text((2, y), c, fill='red')
    y += 14
    for i, (p, im) in enumerate(ims):
        x = (i % 6) * T
        yy = y + (i // 6) * (T + 14)
        canvas.paste(im, (x, yy + 12))
        dr.text((x + 2, yy), f'{i + 1}:{p[-22:]}', fill='blue')
    y += nr * (T + 14)
canvas.save(out)
print(out, canvas.size)
