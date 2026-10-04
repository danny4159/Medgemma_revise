"""iter_067 IVD 중심 sagittal stack PNG 렌더 + manifest. 사용: python sp67_render.py <split> [n_patients]
출력: results/iter_067/png/<pid>/<seq>/ivd<k>/s<ii>.png, results/iter_067/data/render_<split>[_n].json (crop·clip·window·PNG sha)."""
import json, os, sys
import sp67_data as S

PNG = 'results/iter_067/png'


def render_patient(pair):
    pid = pair['patient']
    out = {'patient': pid, 'seq': {}}
    for seq in ('t1', 't2'):
        v = S.load_pair(pid, seq)
        info = S.ivd_info(v['L'], v['spacing'])
        ent = {'src_sha': v['src_sha'], 'spacing_canon': v['spacing'], 'shape_canon': list(v['V'].shape), 'ivd': {}}
        for it in pair['ivd']:
            k = it['k']
            cb = S.crop_box(info[k], v['V'].shape, v['spacing'])
            slices, meta = S.render_stack(v['V'], v['spacing'], cb)
            paths, shas = [], []
            for i, a in enumerate(slices):
                p = f'{PNG}/{pid}/{seq}/ivd{k}/s{i:02d}.png'
                shas.append(S.save_png(p, a)); paths.append(p)
            ent['ivd'][str(k)] = {'crop': cb, 'render': meta, 'paths': paths, 'png_sha256': shas, 'n_slices': len(paths),
                                  'ivd_bbox_canon': {'lo': info[k]['lo'], 'hi': info[k]['hi']}}
        out['seq'][seq] = ent
    return out


def main():
    split = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else None
    pairs = json.load(open(f'results/iter_067/data/pairs_{split}.json'))
    if n:
        pairs = pairs[:n]
    tag = f'{split}' if not n else f'{split}_{n}'
    res = []
    for p in pairs:
        res.append(render_patient(p)); print('rendered', p['patient'], flush=True)
    json.dump(res, open(f'results/iter_067/data/render_{tag}.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
