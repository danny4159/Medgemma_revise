"""고정 8명의 원 DWI–global 문장 연결·공간 검사와 동일 관측 요청을 구성한다."""
from collections import Counter
from pathlib import Path
import json
import math
import re
import nibabel as nib
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from i141_common import HERE, RES, read, save, sha, digest, now
from i141_preflight import IDS
from i141_spec import QUESTION, RENDER, SEMANTIC_CONTRACT

LOCATIONS = {
    '0001': ['left frontal-parietal lobes', 'bilateral occipital lobes', 'near the left lateral ventricle', 'thalamus', 'bilateral cerebellum'],
    '0003': ['left frontal-parietal-temporal-occipital lobes'],
    '0004': ['vicinity of the right frontal lobe', 'border of the frontal and parietal lobes', 'insular cortex', 'adjacent to the lateral ventricle'],
    '0006': ['cerebral peduncles'],
    '0007': ['left cerebellum', 'right occipital lobe', 'brainstem'],
    '0008': ['left frontal lobe', 'corpus callosum', 'basal ganglia region'],
    '0009': ['left basal ganglia', 'frontal-parietal-temporal lobes'],
    '0010': ['brainstem', 'right cerebellum', 'bilateral thalami', 'left parieto-occipital lobe'],
}


def span(text, quote):
    assert text.count(quote) == 1, quote
    start = text.index(quote)
    return {'quote': quote, 'start': start, 'end': start + len(quote)}


def build():
    completion = read(RES / 'selected_download_complete.json')
    assert completion['selected_members_crc32_verified'] is True
    for f in completion['files']:
        assert sha(f['path']) == f['sha256']
    official = RES / 'official'
    reports = read(official / 'ISLES22/global_finding.json')
    modal = read(official / 'ISLES22/modal_wise_finding.json')
    split = read(official / 'train_val_test_split.json')['train']
    raw = RES / 'data_selected/ISLES-2022'
    print((raw / 'README').read_text(), flush=True)
    print((raw / 'dataset_description.json').read_text(), flush=True)
    assert not (RES / 'data_manifest.json').exists()
    rows, reference, requests, hashes = [], [], {'technical': [], 'main': []}, []
    for index, pid in enumerate(IDS):
        key = pid + '_ses-0001_dwi'
        global_key = pid + '_ses-0001'
        assert key in split and global_key in reports
        p = raw / pid / 'ses-0001/dwi' / (key + '.nii.gz')
        assert p.is_file(), '선택 원영상 누락'
        img = nib.load(p)
        original = np.asanyarray(img.dataobj)
        assert original.ndim == 3 and np.isfinite(original).all(), '임의 4D channel 선택 금지'
        canonical = nib.as_closest_canonical(img)
        arr = np.asanyarray(canonical.dataobj)
        assert nib.aff2axcodes(canonical.affine) == ('R', 'A', 'S')
        orientation = nib.orientations.ornt_transform(nib.orientations.io_orientation(img.affine),
                                                     nib.orientations.io_orientation(canonical.affine))
        voxel_map = nib.orientations.inv_ornt_aff(orientation, img.shape)
        checks = []
        for q in [(0, 0, 0), tuple(x-1 for x in arr.shape), tuple(x//2 for x in arr.shape)]:
            qh = np.array([*q, 1.])
            native = voxel_map @ qh
            physical_old, physical_new = img.affine @ native, canonical.affine @ qh
            v = original[tuple(np.rint(native[:3]).astype(int))]
            checks.append({'canonical_index': list(q), 'native_index': native[:3].tolist(),
                           'physical_error_mm': float(np.max(np.abs(physical_old-physical_new))),
                           'voxel_equal': bool(v == arr[q])})
        assert all(c['physical_error_mm'] < 1e-5 and c['voxel_equal'] for c in checks)
        lo, hi = float(arr.min()), float(arr.max())
        assert hi > lo
        nonzero = np.where(np.any(arr != 0, axis=(0, 1)))[0]
        assert len(nonzero)
        zs = list(range(int(nonzero[0]), int(nonzero[-1]) + 1))
        mask_path = raw / 'derivatives' / pid / 'ses-0001' / (global_key + '_msk.nii.gz')
        mask = nib.load(mask_path)
        maskarr = np.asanyarray(mask.dataobj)
        labels = [float(x) for x in np.unique(maskarr)]
        geometry_ok = mask.shape == img.shape and np.allclose(mask.affine, img.affine, atol=1e-5)
        # mask 정합은 검사만 하며 입력·선정·정규화에는 사용하지 않는다.
        meta_path = p.with_suffix('').with_suffix('.json')
        sidecar = read(meta_path) if meta_path.is_file() else None
        images = []
        for z in zs:
            pixels = np.round(np.clip((arr[:, :, z]-lo)/(hi-lo), 0, 1)*255).astype(np.uint8)
            displayed = np.flip(pixels.T, axis=(0, 1))
            ph = digest({'shape': list(displayed.shape), 'bytes_hex': displayed.tobytes().hex()})
            im = Image.fromarray(displayed).convert('RGB')
            zoom = canonical.header.get_zooms()
            width = max(1, round(displayed.shape[1]*float(zoom[0])))
            height = max(1, round(displayed.shape[0]*float(zoom[1])))
            im = im.resize((width, height), Image.Resampling.BILINEAR)
            im = ImageOps.pad(im, (RENDER['side'], RENDER['side']), method=Image.Resampling.BILINEAR, color=0)
            dest = RES / 'png' / pid / f'z{z:04d}.png'
            dest.parent.mkdir(parents=True, exist_ok=True)
            assert not dest.exists()
            im.save(dest)
            physical = canonical.affine @ np.array([(arr.shape[0]-1)/2, (arr.shape[1]-1)/2, z, 1])
            images.append({'path': str(dest), 'sha256': sha(dest), 'pixel_sha256': digest({'shape':[256,256,3], 'bytes_hex':np.asarray(im).tobytes().hex()}),
                           'native_display_pixel_digest': ph, 'canonical_z': z, 'physical_center_RAS_mm': physical[:3].tolist()})
        hashes.extend(im['pixel_sha256'] for im in images)
        stage = 'technical' if index < 2 else 'main'
        condition_rows = []
        for condition, size in [('S', 1), ('A', 5)]:
            for pos in range(0, len(images), size):
                chunk = images[pos:pos+size]
                req = {'id': pid + f'__{condition}__{pos:04d}', 'patient_id': pid, 'condition': condition,
                       'kind': 'findings', 'images': chunk, 'slice_indices': [x['canonical_z'] for x in chunk],
                       'roles': ['DWI']*len(chunk), 'prompt': QUESTION}
                req['request_digest'] = digest(req)
                requests[stage].append(req)
                condition_rows.append(req)
        multisets = {c: Counter(im['sha256'] for r in condition_rows if r['condition']==c for im in r['images']) for c in ['S','A']}
        assert multisets['S'] == multisets['A']
        # global 문장 내부의 같은 병변에 대한 DWI 절만 연결. ADC·병인·병기는 제외.
        text = reports[global_key]
        atom_quotes = [('finding', 'abnormal signal' if 'abnormal signal' in text else 'abnormal signals'),
                       ('signal', 'high signal on DWI' if 'high signal on DWI' in text else 'hyperintense on DWI')]
        for quote in ['Scattered', 'scattered']:
            if quote in text:
                atom_quotes.append(('distribution', quote))
                break
        for quote in ['patchy', 'punctate', 'plaque-like']:
            if quote in text:
                atom_quotes.append(('morphology', quote))
                break
        atom_quotes += [('location', q) for q in LOCATIONS[pid[-4:]]]
        atoms = [{'id': f'{pid}__atom{j:02d}', 'type': kind, **span(text, quote)} for j, (kind,quote) in enumerate(atom_quotes)]
        reference.append({'patient_id': pid, 'source_path': str(official/'ISLES22/global_finding.json'),
                          'source_sha256': sha(official/'ISLES22/global_finding.json'), 'source_key': global_key,
                          'original_text': text, 'positive_atoms': atoms,
                          'negative_reference': [span(text, m.group()) for m in re.finditer(r'no (?:midline shift|displacement of midline structures)', text, re.I)],
                          'excluded': ['ADC low signal', 'diffusion restriction', 'etiology', 'timing'],
                          'DWI_modal_key_present': key in modal,
                          'link_basis': '같은 BIDS patient/session global key. 문장 자체가 해당 병변의 DWI 신호를 명시한다.',
                          'supervision_unit': 'whole sequence; regional/slice mapping not provided'})
        rows.append({'patient_id':pid, 'role':stage, 'DWI_key':key, 'global_key':global_key,
                     'source_path':str(p), 'source_sha256':sha(p), 'native_shape':list(img.shape),
                     'canonical_shape':list(arr.shape), 'native_affine':img.affine.tolist(), 'canonical_affine':canonical.affine.tolist(),
                     'native_axcodes':list(nib.aff2axcodes(img.affine)), 'stored_spacing_mm':[float(x) for x in img.header.get_zooms()],
                     'canonical_to_native_voxel':voxel_map.tolist(), 'physical_checks':checks,
                     'sidecar_path':str(meta_path) if sidecar is not None else None, 'sidecar':sidecar,
                     'DWI_b_value_basis':'공식 ISLES2022 record 7960856: b=1000; 3D image, no channel selection',
                     'slice_indices':zs, 'trimmed_exact_zero_exterior_slices':list(range(0,zs[0]))+list(range(zs[-1]+1,arr.shape[2])),
                     'volume_minmax':[lo,hi], 'images':images, 'same_observation_multiset':True,
                     'mask':{'path':str(mask_path),'sha256':sha(mask_path),'shape':list(mask.shape),'affine':mask.affine.tolist(),
                             'numeric_labels':labels, 'geometry_matches_DWI':bool(geometry_ok), 'used_for_input_selection':False},
                     'new_patient_independence':'new development cases; prior global metadata access and model training exposure not excluded'})
    assert len(set(r['source_sha256'] for r in rows)) == len(rows), '환자간 원영상 중복'
    # 작은 pad slice의 pixel 중복은 표시하며 환자를 제거하지 않는다.
    save(RES/'data_manifest.json', {'created_at':now(),'source_release':'ISLES2022 v2.3.1 record 7960856',
         'use_basis':'public CC-BY-4.0 source MRI; RadGenome text MIT card', 'rows':rows, 'render':RENDER,
         'cross_patient_raw_duplicate_count':len(rows)-len(set(r['source_sha256'] for r in rows)),
         'rendered_pixel_unique':len(set(hashes)), 'rendered_slices':len(hashes)})
    save(RES/'reference_locked.json', {'created_at':now(),'rows':reference,'evaluation_contract':SEMANTIC_CONTRACT})
    for stage, rr in requests.items():
        save(RES/'requests'/f'{stage}.json', rr)
    save(RES/'data_gate.json', {'created_at':now(),'passed':True, 'candidates':len(rows),'eligible':len(rows),
         'DWI_modal_report_links':0, 'explicit_global_DWI_links':len(rows),
         'mask_geometry_matches':sum(r['mask']['geometry_matches_DWI'] for r in rows),
         'supervision':'whole DWI sequence from explicit global DWI clauses; no slice-specific target',
         'restriction':'global report linkage is text-grounded; clinical image truth and prior model exposure remain unverified',
         'requests':{s:len(v) for s,v in requests.items()}, 'new_model_requests':0})
    print(json.dumps({'patients':len(rows),'requests':{s:len(v) for s,v in requests.items()},'slices':[len(r['slice_indices']) for r in rows]}))


if __name__ == '__main__':
    build()
