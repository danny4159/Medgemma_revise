"""iter_070 worker: AutoRG-Brain RGv2, FLAIR, P (predicted mask) vs G (annotation mask), same given_mask path.

Run with the isolated env python (results/environments/autorg70). One worker processes its cases sequentially:
  seg (official SegModel, saves *_ab/*_ana) -> P report (label=pred_ab,label2=pred_ana)
                                             -> G report (label=GT whole-lesion mask, label2=pred_ana)
Per (case, cond) atomic JSON in <out>/results/. Resume: existing results with same protocol hash are skipped.
Generation: official greedy (max_length=300); a cap-reached output is re-run once with AR70_MAXLEN=600
(both attempts are kept).
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback

ROOT = os.path.abspath(os.path.dirname(__file__))
PATCHED = os.path.join(ROOT, 'results/iter_070/external/patched/AutoRG_Brain')
MODELS = os.path.join(ROOT, 'results/iter_070/models')
BRATS = os.path.join(ROOT, 'results/iter_070/data/brats/ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def protocol_hash():
    keys = [os.path.join(MODELS, 'weights_manifest.json'), os.path.join(os.path.dirname(PATCHED), 'ar70_patch.diff'), os.path.abspath(__file__)]
    return hashlib.sha256(b''.join(open(k, 'rb').read() for k in keys)).hexdigest()[:16]


def atomic_json(path, obj):
    tmp = path + '.tmp.%d' % os.getpid()
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def make_gt_mask(case, out_dir):
    import nibabel as nib
    import numpy as np
    p = f'{BRATS}/{case}/{case}-seg.nii.gz'
    img = nib.load(p)
    m = (np.asarray(img.dataobj) > 0).astype(np.uint8)
    hdr = img.header.copy()
    hdr.set_data_dtype(np.uint8)
    o = os.path.join(out_dir, f'{case}_gt_whole.nii.gz')
    if not os.path.exists(o):
        nib.save(nib.Nifti1Image(m, img.affine, hdr), o)
    return o, int(m.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--conds', default='P,G')
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    for d in ['results', 'masks', 'gt', 'log']:
        os.makedirs(os.path.join(out, d), exist_ok=True)
    os.environ['AR70_GPT2'] = os.path.join(MODELS, 'gpt2pm')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.chdir(PATCHED)
    sys.path.insert(0, PATCHED)
    import torch
    from inference.inferenceSdk import AutoRG_Brain

    ph = protocol_hash()
    t_load = time.time()
    cfg = {'llm_folder': os.path.join(MODELS, 'autorg/RG_v2'), 'seg_folder': os.path.join(MODELS, 'autorg'),
           'llm_chk': 'AutoRG_Brain_RGv2', 'seg_chk': 'AutoRG_Brain_SEG', 'output_dir': os.path.join(out, 'masks'),
           'eval_mode': 'given_mask'}
    model = AutoRG_Brain(gpu_id=[0], config=cfg)
    load_s = time.time() - t_load
    gen_log = []
    orig_gen = model.trainer.llm_model.generate

    def gen_wrap(*args, **kw):
        o = orig_gen(*args, **kw)
        eos = model.trainer.tokenizer.eos_token_id
        gen_log.append({'max_length': kw.get('max_length'), 'shape': list(o.shape),
                        'has_eos': [bool((row == eos).any().item()) for row in o[:, 1:]] if o.shape[1] > 1 else []})
        return o
    model.trainer.llm_model.generate = gen_wrap
    meta = {'protocol_hash': ph, 'load_s': load_s, 'cuda_visible': os.environ.get('CUDA_VISIBLE_DEVICES'),
            'device': torch.cuda.get_device_name(0), 'pid': os.getpid(), 'torch': torch.__version__}
    atomic_json(os.path.join(out, 'log', f'worker_{os.getpid()}.json'), meta)

    for case in a.cases.split(','):
        img = f'{BRATS}/{case}/{case}-t2f.nii.gz'
        stem = f'{case}-t2f'
        need = [c for c in a.conds.split(',') if not os.path.exists(os.path.join(out, 'results', f'{case}__{c}.json'))]
        if not need:
            continue
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        gt_path, gt_vox = make_gt_mask(case, os.path.join(out, 'gt'))
        ab = os.path.join(out, 'masks', f'{stem}_ab.nii.gz')
        ana = os.path.join(out, 'masks', f'{stem}_ana.nii.gz')
        seg_s = None
        if not (os.path.exists(ab) and os.path.exists(ana)):
            ts = time.time()
            try:
                model.segmodel.seg([[img]], [None], [None], ['T2FLAIR'])
            except Exception:
                atomic_json(os.path.join(out, 'results', f'{case}__SEGFAIL.json'), {'case': case, 'err': traceback.format_exc()})
                continue
            seg_s = time.time() - ts
        seg_peak = torch.cuda.max_memory_reserved() / 2**20
        for cond in need:
            label = ab if cond == 'P' else gt_path
            rec = {'case': case, 'cond': cond, 'protocol_hash': ph, 'image': img, 'image_sha256': sha(img),
                   'label_path': label, 'ana_path': ana, 'gt_whole_voxels': gt_vox, 'seg_s_case': seg_s,
                   'attempts': [], 'status': 'ok'}
            for maxlen in (300, 600):
                os.environ['AR70_MAXLEN'] = str(maxlen)
                del gen_log[:]
                tg = time.time()
                try:
                    res = model.report([{'image': img, 'modal': 'T2FLAIR', 'label': label, 'label2': ana}])
                    err = None
                except Exception:
                    res, err = None, traceback.format_exc()
                att = {'max_length': maxlen, 'wall_s': time.time() - tg, 'gen': list(gen_log), 'error': err,
                       'report': res[0]['pred_report'] if res else None}
                cap = any((not all(g['has_eos'])) and g['shape'][1] >= maxlen - 1 for g in gen_log)
                att['cap_hit'] = bool(cap)
                rec['attempts'].append(att)
                if err or not cap:
                    break
            if rec['attempts'][-1]['error']:
                rec['status'] = 'error'
            rec['peak_reserved_MiB'] = torch.cuda.max_memory_reserved() / 2**20
            rec['seg_peak_reserved_MiB'] = seg_peak
            rec['case_wall_s'] = time.time() - t0
            atomic_json(os.path.join(out, 'results', f'{case}__{cond}.json'), rec)
            print(case, cond, rec['status'], round(rec['case_wall_s'], 1), flush=True)


if __name__ == '__main__':
    main()
