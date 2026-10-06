"""iter_086 E 표본 구축(CPU, 모델 출력 미사용).
python report86_build_E.py extract   # 후보 영상(각 층 앞 N명) 추출·hash·중복 검사·contact sheet
python report86_build_E.py lock      # visual_audit_E.json(눈으로 확인한 제외 ID) 반영 후 E96/E192x 입력·정답·잠금 파일 작성
영상 규약은 iter_039/042와 동일: uint16 -> uint8 right shift 8, 값 보존 RGB 복제는 generate.load_image가 수행.
"""
import glob
import hashlib
import io
import json
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

import pg39_data as D
import report86_facts as F
from report86_common import ROOT, R86, sha, sha_obj, save

E = R86 / 'E'
N_PER_STRATUM_POOL = 120  # 시각 점검용 후보 풀(층별 앞 120명). 실제 선택은 층별 앞 96명이며 점검 제외 시 다음 순서로 대체.


def extract_one(z, zi, iid):
    raw = z.read(zi)
    a = np.asarray(Image.open(io.BytesIO(raw)))
    if a.dtype != np.uint16 or a.ndim != 2:
        raise D.InputError(f'{iid}: unexpected dtype/shape {a.dtype} {a.shape}')
    b = (a >> 8).astype(np.uint8)
    (E / 'images').mkdir(parents=True, exist_ok=True)
    (E / 'raw').mkdir(parents=True, exist_ok=True)
    pu8, praw = E / 'images' / iid, E / 'raw' / iid
    if not praw.exists():
        praw.write_bytes(raw)
    if not pu8.exists():
        tmp = str(pu8) + f'.{os.getpid()}.tmp.png'
        Image.fromarray(b).save(tmp)
        os.replace(tmp, pu8)
    h, w = a.shape
    return {'image': str(pu8), 'raw_path': str(praw), 'zip_member': zi.filename, 'zip_crc': zi.CRC,
            'raw_png_sha256': hashlib.sha256(raw).hexdigest(), 'u16_pixel_sha256': hashlib.sha256(a.tobytes()).hexdigest(),
            'u8_pixel_sha256': hashlib.sha256(b.tobytes()).hexdigest(), 'file_sha256': sha(pu8), 'h': int(h), 'w': int(w),
            'u16_min': int(a.min()), 'u16_max': int(a.max())}


def ordered_pools():
    enum = json.loads((E / 'enumeration.json').read_text())
    cands = enum['ordered_candidates']
    ab = [c for c in cands if c['has_abnormal_flag'] and F.eligible_abnormal(F.facts_for(c))]
    no = [c for c in cands if not c['has_abnormal_flag']]
    return enum, ab, no


def prior_hashes():
    s_pix, s_pat, s_study, s_img = set(), set(), set(), set()
    for p in glob.glob(str(ROOT / 'results/iter_0*/data/manifest*.jsonl')):
        for ln in open(p):
            d = json.loads(ln)
            im = d.get('image_meta') or {}
            if im.get('u16_pixel_sha256'):
                s_pix.add(im['u16_pixel_sha256'])
            s_pat.add(d.get('PatientID'))
            s_study.add(d.get('StudyID'))
            s_img.add(d.get('ImageID'))
    return s_pix, s_pat, s_study, s_img


def do_extract():
    enum, ab, no = ordered_pools()
    z = D.open_image_zip()
    idx = D.zip_index(z)
    meta = {}
    for stratum, pool in (('abnormal', ab[:N_PER_STRATUM_POOL]), ('no_abnormal', no[:N_PER_STRATUM_POOL])):
        for rank, c in enumerate(pool):
            m = extract_one(z, idx[c['ImageID']], c['ImageID'])
            meta[c['ImageID']] = {**m, 'stratum': stratum, 'rank': rank, 'PatientID': c['PatientID'], 'StudyID': c['StudyID']}
    pix, pat, study, img = prior_hashes()
    ov = {'pixel_hash_overlap_with_prior_manifests': sum(m['u16_pixel_sha256'] in pix for m in meta.values()),
          'patient_overlap_with_prior_manifests': sum(m['PatientID'] in pat for m in meta.values()),
          'study_overlap': sum(m['StudyID'] in study for m in meta.values()),
          'image_id_overlap': sum(k in img for k in meta),
          'within_set_duplicate_pixel_hashes': len(meta) - len({m['u16_pixel_sha256'] for m in meta.values()}),
          'within_set_duplicate_patients': len(meta) - len({m['PatientID'] for m in meta.values()}),
          'n_eligible_abnormal_total': len(ab), 'n_no_abnormal_total': len(no)}
    save(E / 'extract_meta.json', {'meta': meta, 'overlaps': ov, 'convention': 'uint16>>8 -> uint8 (iter_039/042과 동일)'})
    # contact sheets (16 per sheet, 4x4, 320px thumbnails)
    order = [(m['stratum'], m['rank'], k) for k, m in meta.items()]
    order.sort()
    sheets = []
    for s in range(0, len(order), 16):
        part = order[s:s + 16]
        sheet = Image.new('L', (4 * 320, 4 * 340), 0)
        from PIL import ImageDraw
        dr = ImageDraw.Draw(sheet)
        for i, (st, rank, k) in enumerate(part):
            im = Image.open(E / 'images' / k).convert('L')
            im.thumbnail((320, 320))
            x, y = (i % 4) * 320, (i // 4) * 340
            sheet.paste(im, (x, y + 20))
            dr.text((x + 4, y + 4), f'{st[:3]}{rank}', fill=255)
        p = E / 'contact' / f'sheet_{s // 16:02d}.png'
        p.parent.mkdir(exist_ok=True)
        sheet.save(p)
        sheets.append({'file': str(p), 'items': [f'{st[:3]}{rank}:{k[:8]}' for st, rank, k in part]})
    save(E / 'contact_sheets.json', sheets)
    print(json.dumps(ov, indent=1), len(sheets), 'sheets')


def do_lock():
    enum, ab, no = ordered_pools()
    meta = json.loads((E / 'extract_meta.json').read_text())['meta']
    audit = json.loads((E / 'visual_audit_E.json').read_text())
    excluded = {x['ImageID'] for x in audit['excluded']}
    for stratum, pool in (('abnormal', ab), ('no_abnormal', no)):
        pass
    sel = {}
    for stratum, pool in (('abnormal', ab), ('no_abnormal', no)):
        keep = [c for c in pool[:N_PER_STRATUM_POOL] if c['ImageID'] not in excluded]
        sel[stratum] = keep
    n_have = {k: len(v) for k, v in sel.items()}
    assert all(n >= 96 for n in n_have.values()), n_have
    rows = {'E96': [], 'E192x': []}
    refs = {}
    for stratum, keep in sel.items():
        for i, c in enumerate(keep[:96]):
            stage = 'E96' if i < 48 else 'E192x'
            m = meta[c['ImageID']]
            row = {'PatientID': c['PatientID'], 'StudyID': c['StudyID'], 'ImageID': c['ImageID'], 'image': m['image'], 'file_sha256': m['file_sha256'],
                   'mode': 'L', 'size': [m['w'], m['h']], 'source': 'iter_086 E (PadChest-GR validation)', 'split': 'validation',
                   'stratum': stratum, 'stratum_rank': i, 'order_hash': c['hash'], 'u16_pixel_sha256': m['u16_pixel_sha256']}
            rows[stage].append(row)
            refs[c['ImageID']] = {'ImageID': c['ImageID'], 'PatientID': c['PatientID'], 'StudyID': c['StudyID'], 'stratum': stratum, 'stage': stage,
                                  'PreviousImageID': c['PreviousImageID'], 'facts': F.facts_for(c), 'findings_raw': c['findings']}
    for stage in rows:
        rows[stage].sort(key=lambda r: r['order_hash'])  # 두 층을 섞어 처리 순서를 고정
        save(E / f'inputs_{stage}.json', rows[stage])
        save(E / f'raw_manifest_{stage}.json', [{'ImageID': r['ImageID'], 'raw_path': meta[r['ImageID']]['raw_path'],
                                                   'sha256': meta[r['ImageID']]['raw_png_sha256']} for r in rows[stage]])
    save(E / 'reference_facts_E_private.json', refs)
    lock = {'enumeration_sha256': sha(E / 'enumeration.json'), 'extract_meta_sha256': sha(E / 'extract_meta.json'),
            'visual_audit_sha256': sha(E / 'visual_audit_E.json'), 'facts_rules_sha256': F.rules_sha(),
            'inputs_E96_sha256': sha(E / 'inputs_E96.json'), 'inputs_E192x_sha256': sha(E / 'inputs_E192x.json'),
            'reference_facts_sha256': sha(E / 'reference_facts_E_private.json'),
            'counts': {st: Counter(r['stratum'] for r in rows[st]) for st in rows},
            'fact_class_counts': {st: dict(Counter(x['fact_class'] for r in rows[st] for x in refs[r['ImageID']]['facts'])) for st in rows},
            'n_excluded_visual': len(excluded), 'rule': 'sha256(84017|PatientID|ImageID) order; abnormal stratum requires >=1 pos_def fact; first 48 per stratum E96, next 48 E192x'}
    save(E / 'selection_lock.json', lock)
    print(json.dumps(lock, indent=1, default=dict))


if __name__ == '__main__':
    {'extract': do_extract, 'lock': do_lock}[sys.argv[1]]()
