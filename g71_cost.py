"""iter_071 같은 workload(V8 8명 x 3 slice x 2 category) 비용 측정: 원본 T2 읽기 -> canonical -> render(PNG 저장) -> 추론 -> 답변 JSON 저장까지.
annotation mask는 읽지 않는다. 한 프로세스가 한 system(vlm|det)의 한 block을 수행하고 단조 시계로 단계별 시간을 기록한다.
- t_total_incl_load: 프로세스 시작 직후(import 이후) ~ 마지막 답변 저장까지(모델 적재 포함).
- t_resident: 모델 적재 이후 ~ 마지막 답변 저장까지(read/render 포함, 상주 모델 가정).
사용: python g71_cost.py vlm OUT_DIR --adapter DIR | python g71_cost.py det OUT_DIR --ckpt PATH --thr 0.85
"""
import argparse, hashlib, io, json, os, sys, time

import numpy as np
from PIL import Image

import g71_data as D
import sp67_data as S

t_proc = time.perf_counter()


def read_render_patient(pid, outdir):
    """mask 없이: 영상만 읽고 선택 slice를 렌더해 PNG로 저장. returns {offset: path}, ms 단위 세부."""
    img, ibytes, arr = S.read_sitk(S.IMG_ZIP, f'images/{pid}_{D.SEQ}.mha')
    ca = S.canon_axes(img.GetDirection())
    V, spc = S.to_canonical(arr, img.GetSpacing(), ca)
    paths = {}
    for off, idx in zip(D.OFFSETS, D.select_slices(V.shape[0])):
        a, meta = D.render_slice(V, spc, idx)
        buf = io.BytesIO()
        Image.fromarray(a, mode='L').save(buf, format='PNG')
        p = f'{outdir}/{pid}_{D.OFF_NAME[off]}.png'
        with open(p, 'wb') as f:
            f.write(buf.getvalue())
        paths[off] = (p, hashlib.sha256(buf.getvalue()).hexdigest())
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('system', choices=['vlm', 'det'])
    ap.add_argument('out_dir')
    ap.add_argument('--adapter', default=None)
    ap.add_argument('--ckpt', default=None)
    ap.add_argument('--thr', type=float, default=0.85)
    ap.add_argument('--key', default='V8')
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    sp = D.load_split()
    man = json.load(open(f'{D.DATA}/manifest.json'))
    pids = sp[a.key]
    img_dir = os.path.join(a.out_dir, 'png')
    os.makedirs(img_dir, exist_ok=True)
    ev = {'system': a.system, 'key': a.key, 'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES')}
    answers = {}
    if a.system == 'vlm':
        from rsna_diag import generate as GEN
        t0 = time.perf_counter()
        torch, proc, model = GEN.load_model()
        adig = GEN.load_adapter(torch, model, a.adapter)
        env = GEN.env_info(torch, proc, model)
        eos = env['eos_token_id']
        eos_ids = set(eos if isinstance(eos, list) else [eos])
        import torch as _t
        _t.cuda.synchronize()
        ev['t_load_model'] = time.perf_counter() - t0
        t_res0 = time.perf_counter()
        t_rr = t_inf = 0.0
        for pid in pids:
            t = time.perf_counter()
            paths = read_render_patient(pid, img_dir)
            t_rr += time.perf_counter() - t
            for off, (p, h) in paths.items():
                if h != man['patients'][pid]['images'][D.OFF_NAME[off]]['file_sha256']:
                    raise RuntimeError(f'rendered PNG differs from manifest for {pid} {off}')
                for cat in D.CATS:
                    t = time.perf_counter()
                    rec = GEN.run_request(torch, proc, model, eos_ids, {'id': D.item_id(pid, off, cat), 'image': p}, cat, D.PROMPTS[cat])
                    t_inf += time.perf_counter() - t
                    answers[rec['id']] = {'suffix_ids': rec['suffix_ids'], 'ended_eos': rec['ended_eos'], 'n_out': rec['n_output_tokens'], 'text': rec['suffix_text_raw']}
        with open(os.path.join(a.out_dir, 'answers.json'), 'w') as f:
            json.dump(answers, f)
        torch.cuda.synchronize()
        t_end = time.perf_counter()
        ev.update({'adapter_digest': adig, 'peak_gb': torch.cuda.max_memory_allocated() / 2 ** 30})
    else:
        sys.path.insert(0, 'results/environments/tv071')
        os.environ.setdefault('TORCH_HOME', os.path.abspath('results/environments/torch_home071'))
        import torch
        import g71_det as X
        from rsna_diag import geometry as G
        t0 = time.perf_counter()
        model = X.build_model().to('cuda')
        b = torch.load(a.ckpt, map_location='cpu', weights_only=False)
        model.load_state_dict(b['model'])
        model.eval()
        torch.cuda.synchronize()
        ev['t_load_model'] = time.perf_counter() - t0
        t_res0 = time.perf_counter()
        t_rr = t_inf = 0.0
        for pid in pids:
            t = time.perf_counter()
            paths = read_render_patient(pid, img_dir)
            t_rr += time.perf_counter() - t
            for off, (p, h) in paths.items():
                if h != man['patients'][pid]['images'][D.OFF_NAME[off]]['file_sha256']:
                    raise RuntimeError(f'rendered PNG differs from manifest for {pid} {off}')
                t = time.perf_counter()
                arr = np.asarray(Image.open(p))
                rgb = G.to_uint8_rgb_preserving(arr)
                x = torch.from_numpy(rgb).permute(2, 0, 1).float().div(255.0).cuda()
                with torch.no_grad():
                    pr = model([x])[0]
                h_, w_ = rgb.shape[:2]
                top, left, side = G.pad_offsets(h_, w_)
                for cat, lab in (('vertebra', 1), ('disc', 2)):
                    bx = [G.canvas_to_norm(bb, top, left, side) for bb, s, l in zip(pr['boxes'].cpu().tolist(), pr['scores'].cpu().tolist(), pr['labels'].cpu().tolist())
                          if l == lab and s >= a.thr]
                    answers[D.item_id(pid, off, cat)] = {'boxes': bx}
                t_inf += time.perf_counter() - t
        with open(os.path.join(a.out_dir, 'answers.json'), 'w') as f:
            json.dump(answers, f)
        torch.cuda.synchronize()
        t_end = time.perf_counter()
        ev['peak_gb'] = torch.cuda.max_memory_allocated() / 2 ** 30
    ev.update({'t_total_incl_load': t_end - t_proc, 't_resident': t_end - t_res0, 't_read_render': t_rr, 't_infer': t_inf, 'n_answers': len(answers), 'n_expected': len(pids) * 6})
    assert len(answers) == len(pids) * 6
    json.dump(ev, open(os.path.join(a.out_dir, 'timing.json'), 'w'), indent=1)
    print(json.dumps(ev))


if __name__ == '__main__':
    main()
