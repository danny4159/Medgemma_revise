"""시각 검증용 montage: 환자의 각 IVD에서 mask 좌우 중앙 sagittal slice(T1 위, T2 아래). 사용: python sp67_montage.py <render.json> <pid> <out.png>"""
import json, sys
import numpy as np
from PIL import Image, ImageDraw


def main():
    rj, pid, out = sys.argv[1:4]
    r = {x['patient']: x for x in json.load(open(rj))}[pid]
    rows = []
    for seq in ('t1', 't2'):
        tiles = []
        for k, e in sorted(r['seq'][seq]['ivd'].items(), key=lambda kv: int(kv[0])):
            lo, hi = e['ivd_bbox_canon']['lo'][0], e['ivd_bbox_canon']['hi'][0]
            mid = (lo + hi) // 2
            im = Image.open(e['paths'][mid]).resize((224, 224))
            ImageDraw.Draw(im).text((3, 3), f'{seq} k{k} s{mid}', fill=(255, 255, 0))
            tiles.append(np.asarray(im))
        rows.append(np.concatenate(tiles, 1))
    w = max(x.shape[1] for x in rows)
    rows = [np.pad(x, ((0, 0), (0, w - x.shape[1]), (0, 0))) for x in rows]
    Image.fromarray(np.concatenate(rows, 0)).save(out)


if __name__ == '__main__':
    main()
