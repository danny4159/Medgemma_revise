"""iter_125 인계 감사: 원 산출물을 변경하지 않고 예산 중단과 미완료 범위를 보존한다."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import nibabel as nib
import numpy as np
from PIL import Image
from scipy.ndimage import affine_transform


ROOT = Path('results/iter_125')
REV = 'f6e39794e7820c96c18465231a30da424e6d1c69'
SS = Path('results/external/synthseg_src/SynthSeg-2a2aa3bbfccb83f8253a51ca8b329b9938a2646d')


def sha(path):
    d = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            d.update(b)
    return d.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(out)
    started = time.time()
    before = {str(p): sha(p) for p in ROOT.rglob('*') if p.is_file()}
    lock = json.loads((ROOT / 'data/selection_lock.json').read_text())
    old = json.loads(Path('results/iter_123/data/fetch_ledger.json').read_text())
    current = json.loads((ROOT / 'data/fetch_ledger.json').read_text())
    prov = json.loads((ROOT / 'seg/prov_tech.json').read_text())
    build = json.loads((ROOT / 'seg/build_tech.json').read_text())
    checks = []

    def check(name, ok, detail=None):
        checks.append({'name': name, 'pass': bool(ok), 'detail': detail})

    check('selection_60_unique_patients', len(lock['manifest']) == 60 and
          len({m['patient_uid'] for m in lock['manifest']}) == 60)
    roles = Counter(m['role'] for m in lock['manifest'])
    cells = Counter(f"{m['role']}|{m['batch_id']}|{m['label']}" for m in lock['manifest'])
    check('fixed_role_cell_sizes', roles == {'tech': 8, 'calib': 12, 'explore': 40} and
          all(n == {'tech': 2, 'calib': 3, 'explore': 10}[k.split('|')[0]] for k, n in cells.items()))
    for rel, h in lock['source_sha256'].items():
        check('metadata:' + rel, sha(Path('/home/test/.local/share/medgemma/mr_rate/meta') / rel) == h)
    for rel, h in lock['code_sha256'].items():
        check('selection_code:' + rel, sha(rel) == h)
    reuse = json.loads(Path('../agent/runs/iter_125/reuse_manifest.json').read_text())
    for rel, item in reuse['files'].items():
        blob = subprocess.check_output(['git', 'hash-object', '--', rel], text=True).strip()
        check('reuse_blob:' + rel, blob == item['blob'], {'actual': blob, 'expected': item['blob']})

    os.environ['HF_TOKEN_PATH'] = '/home/test/.cache/huggingface/token'
    from huggingface_hub import HfApi
    paths = {f"mri/{m['batch_id']}/{m['study_uid']}.zip" for m in lock['manifest']}
    paths.update(v['path'].split('/raw/')[-1] for v in old.values())
    infos = {i.path: i for i in HfApi().get_paths_info('Forithmus/MR-RATE', sorted(paths),
                                                   repo_type='dataset', revision=REV)}
    check('official_path_set_complete', set(infos) == paths)
    for origin, led in [('old', old), ('current', current)]:
        for study, v in led.items():
            rel = v['path'].split('/raw/')[-1]
            i = infos[rel]
            h = sha(v['path'])
            check(f'{origin}_zip:{study}', h == v['sha256'] == i.lfs.sha256 and
                  Path(v['path']).stat().st_size == v['size'] == i.size and v['revision'] == REV)
    old_paths = {v['path'].split('/raw/')[-1] for v in old.values()}
    current_paths = {v['path'].split('/raw/')[-1] for v in current.values()}
    selected_paths = {f"mri/{m['batch_id']}/{m['study_uid']}.zip" for m in lock['manifest']}
    needed_paths = selected_paths - old_paths - current_paths
    total_bytes = sum(infos[p].size for p in old_paths | current_paths | selected_paths)
    budget = dict(revision=REV, limit_bytes=10 * 1024 ** 3,
                  old_zip_count=len(old_paths), current_zip_count=len(current_paths),
                  old_bytes=sum(infos[p].size for p in old_paths),
                  current_bytes=sum(infos[p].size for p in current_paths - old_paths),
                  remaining_zip_count=len(needed_paths), remaining_bytes=sum(infos[p].size for p in needed_paths),
                  planned_cumulative_bytes=total_bytes, exceeded=total_bytes > 10 * 1024 ** 3,
                  official_objects={p: dict(size=infos[p].size, sha256=infos[p].lfs.sha256) for p in sorted(paths)})
    budget['excess_bytes'] = max(0, total_bytes - budget['limit_bytes'])
    # 예산 실패는 원 계획의 실행 중단 조건이다. 실패를 모델의 음성 결과로 바꾸지 않는다.
    check('planned_cumulative_zip_budget', not budget['exceeded'], budget)

    import mr123_data as render
    from mr125_build import resample_nn
    technical = []
    for m in lock['manifest']:
        study = m['study_uid']
        if m['role'] != 'tech':
            continue
        p = prov[study]
        b = build[study]
        with zipfile.ZipFile(current[study]['path']) as z:
            for kind, f in p['files'].items():
                matches = [i for i in z.infolist() if i.filename == f['zip_member']]
                check(f'unique_member:{study}:{kind}', len(matches) == 1)
                with z.open(matches[0]) as member:
                    d = hashlib.sha256()
                    for chunk in iter(lambda: member.read(4 << 20), b''):
                        d.update(chunk)
                check(f'extracted_sha:{study}:{kind}', d.hexdigest() == sha(f['path']) == f['sha256'])
        check('seg_sha:' + study, sha(p['seg']) == p['seg_sha256'])
        im = nib.load(p['files']['img.nii.gz']['path'])
        brain = nib.load(p['files']['brain.nii.gz']['path'])
        seg = nib.load(p['seg'])
        sd = np.rint(np.asarray(seg.dataobj)).astype(np.int16)
        check('input_grid:' + study, len(im.shape) == 3 and im.shape == brain.shape and
              np.allclose(im.affine, brain.affine, atol=1e-3) and np.isfinite(im.get_fdata()).all())
        check('seg_1mm:' + study, np.allclose(seg.header.get_zooms()[:3], 1))
        mapping = np.linalg.inv(seg.affine) @ im.affine
        independent = affine_transform(sd, mapping[:3, :3], offset=mapping[:3, 3], output_shape=im.shape,
                                       order=0, mode='grid-constant', cval=0, prefilter=False)
        actual = resample_nn(sd, seg.affine, im.shape, im.affine)
        check('nearest_resampling_vs_scipy:' + study, np.array_equal(actual, independent),
              {'differing_voxels': int(np.count_nonzero(actual != independent))})
        a = np.asarray(nib.as_closest_canonical(im).dataobj).astype(np.float32)
        bm = np.asarray(nib.as_closest_canonical(brain).dataobj) > 0
        window = render.intensity_window(a, bm)
        check('window:' + study, np.allclose(window, b['window_p1_p99']))
        check('ras:' + study, ''.join(nib.aff2axcodes(nib.as_closest_canonical(im).affine)) == 'RAS')
        for idx, entry in b['pngs'].items():
            img = render.render_slice(a, int(idx), *window, b['canon_zooms'])
            check(f'png:{study}:{idx}', sha(entry['path']) == entry['sha256'] and
                  np.array_equal(np.asarray(img), np.asarray(Image.open(entry['path']))) and img.size == (896, 896))
        has_foreground = bool(np.any(sd))
        technical.append(dict(study_uid=study, label=m['label'], seconds=p['seconds'],
                              foreground_voxels=int(np.count_nonzero(sd)),
                              lateral_ventricle_voxels=int(np.isin(sd, [4, 43]).sum()),
                              segmentation_nonempty=has_foreground, A_fallback=b['A_fallback'],
                              U_idx=b['U_idx'], A_idx=b['A_idx'],
                              vol_csv_exists=Path(p['vol_csv']).exists(),
                              provisional_S=b['S']))
    code = (SS / 'SynthSeg/predict_synthseg.py').read_text()
    check('official_v1_no_total_icv_branch_identified', "if not v1:" in code and
          "np.array(['total intracranial'])" in code)
    invalid_baseline = {
        'implementation': 'SynthSeg --v1; hard-label nonbackground voxel count used as ICV',
        'official': 'predict_synthseg.py adds total intracranial output only when not v1; volumes sum posterior probabilities',
        'status': '미검증',
        'reason_ko': '현재 hard mask 비배경 부피는 계획의 공식 ICV와 동등성이 검증되지 않았음',
        'missing_v2_weights': not (SS / 'models/synthseg_2.0.h5').exists(),
        'missing_qc_weights': not (SS / 'models/synthseg_qc_2.0.h5').exists(),
        'zero_segmentations': [v['study_uid'] for v in technical if not v['segmentation_nonempty']],
    }
    envpy = Path('results/environments/synthseg125/bin/python').resolve()
    freeze = subprocess.run([str(envpy), '-m', 'pip', 'freeze'], capture_output=True, text=True)
    check('isolated_environment_freeze', freeze.returncode == 0)
    check('inherited_outputs_unchanged', all(sha(p) == h for p, h in before.items()))
    report = dict(iteration=125, created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  elapsed_s=time.time() - started, checkpoint='adb8d637bace1f0ad30f48df78a58befee78f836',
                  sys_executable=sys.executable, CUDA_VISIBLE_DEVICES=os.environ.get('CUDA_VISIBLE_DEVICES'),
                  source_sha256=sha(__file__), checks=checks, roles=dict(roles), cells=dict(cells), budget=budget,
                  technical=technical, baseline_blocker=invalid_baseline,
                  inherited_files_before_sha256=before,
                  official_source_sha256={str(p): sha(p) for p in [SS / 'README.md', SS / 'LICENSE.txt',
                      SS / 'data/labels table.txt', SS / 'SynthSeg/predict_synthseg.py',
                      SS / 'scripts/commands/SynthSeg_predict.py', SS / 'models/synthseg_1.0.h5']},
                  synthseg_environment_python=str(envpy), synthseg_pip_freeze=freeze.stdout,
                  medgemma_packages={k: importlib.metadata.version(k) for k in ['torch','transformers','numpy','nibabel','Pillow','huggingface_hub']},
                  valid_experiment=False, decision='execution_blocked_before_VLM',
                  pending=['budget_replanning', 'official_ICV_QC_baseline', 'full_report_eligibility_validation',
                           'technical_MedGemma_outputs', 'throughput_comparison', 'strict_runtime_tests',
                           'pregeneration_eval_lock', 'calibration12', 'explore40', 'independent_evaluation'],
                  summary_ko='누적 ZIP 예산 초과로 사전 중단. 기존 기술8명 자산은 보존했으나 공식 ICV 전문 대조와 VLM 비교는 미완료.')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(dict(output=str(out), checks=len(checks), failed=[c['name'] for c in checks if not c['pass']],
                          budget={k:v for k,v in budget.items() if k != 'official_objects'},
                          baseline_blocker=invalid_baseline), ensure_ascii=False))
    return 2 if budget['exceeded'] or invalid_baseline['status'] == '미검증' or any(not c['pass'] for c in checks) else 0


if __name__ == '__main__':
    raise SystemExit(main())
