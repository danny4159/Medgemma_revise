"""iter_051 인계 자료 검증 및 명시적 영상 감사 기록. 과거 결과는 읽기 전용."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import PIL
from PIL import Image, ImageDraw
import mt50_common as C

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results/iter_051'
OLD = ROOT / 'results/iter_050/audit'

def sha(p):
    return C.file_sha(p)

def safe(p):
    p = Path(p).absolute()
    if '..' in p.parts:
        raise ValueError('path traversal')
    if any(q.is_symlink() for q in [p, *p.parents]):
        raise ValueError('symlink: ' + str(p))
    if not p.is_relative_to(ROOT):
        raise ValueError('path escape')
    return p

def write(p, obj):
    p = safe(p)
    if not p.is_relative_to(OUT):
        raise ValueError('old output path forbidden')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def cases():
    return C.read_jsonl(ROOT / 'results/iter_049/audit_v2/eligible_cases.jsonl')

def prepare():
    assert PIL.__version__ == '12.3.0', PIL.__version__
    plans = {'plan.md': '6e9a5010785840182c20e13456bc0051d73b1a827ee4e19eebba229bc7ffc041',
             'plan.json': '32e82ceac78888799067eae50d6e36a87e0286dcb33a20c58f658e7afd478813'}
    for name, digest in plans.items():
        assert sha(ROOT.parent / 'agent/runs/iter_050' / name) == digest
    assert sha(safe(Path(C.R49) / 'raw/train.jsonl')) == C.TRAIN_SHA
    manifest_path = safe(Path(C.R49) / 'image_manifest.json')
    man = json.loads(manifest_path.read_text())
    by_path = {r['path']: r for r in man['records']}
    assert len(by_path) == len(man['records']) == 896
    rows = []
    for c in cases():
        ims, ir = [], []
        for i, im in enumerate(c['images']):
            p = safe(Path(C.R49) / im['path'])
            assert p.is_relative_to(Path(C.R49) / 'images')
            rec = by_path[im['path']]
            assert p.stat().st_size == rec['size'] and sha(p) == rec['file_sha256']
            rgb, info = C.load_rgb(im['path'])
            assert info['native_pixel_sha256'] == rec['pixel_sha256']
            assert info['alpha_min'] in (None, 255)
            ir.append({'index': i, 'path': im['path'], 'file_sha256': sha(p), **info})
            ims.append(rgb)
        cols = min(4, len(ims))
        sheet = Image.new('RGB', (cols*384, ((len(ims)+cols-1)//cols)*384), (40,40,40))
        d = ImageDraw.Draw(sheet)
        for i, im in enumerate(ims):
            x,y = (i%cols)*384, (i//cols)*384
            sheet.paste(im.resize((384,384), Image.Resampling.LANCZOS), (x,y))
            d.rectangle([x,y,x+22,y+16], fill=(255,255,0))
            d.text((x+4,y+2), str(i), fill=(0,0,0))
        cid = c['case_key'].replace('Case number ', 'c')
        sp = safe(OLD / 'sheets' / (cid+'.png'))
        with Image.open(sp) as saved:
            assert saved.mode == sheet.mode and saved.size == sheet.size
            assert saved.tobytes() == sheet.tobytes(), cid
        rows.append({'case_id': cid, 'case_key': c['case_key'], 'sheet': str(sp.relative_to(ROOT)),
                     'sheet_sha256': sha(sp), 'ordered_images': ir, 'visual_status': 'pending'})
    audit_files = []
    for p in sorted((OLD/'decisions').glob('*')):
        name = p.name
        status = 'unverified'
        if name.startswith('image_part') or (name.startswith('image_redo_') and int(p.stem[-2:])<=25):
            status = 'invalid'
        elif name == 'image_redo_26.json':
            status = 'mixed_invalid_c620_c621_other_valid_candidates'
        elif name.startswith(('image_redo_', 'image_valid_')):
            status = 'valid_candidate_requires_render_evidence'
        audit_files.append({'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'status': status,
                            'inherited_visual_decisions': False})
    reuse = json.loads((ROOT.parent/'agent/runs/iter_050/reuse_manifest.json').read_text())
    blobs = {}
    for name, info in reuse['files'].items():
        blob = subprocess.check_output(['git','hash-object','--',name], text=True).strip()
        assert blob == info['blob']
        blobs[name] = blob
    write(OUT/'audit/source_check.json', {'status':'PASS','cases':rows,'n_cases':len(rows),
          'n_images':sum(len(r['ordered_images']) for r in rows), 'decoder':PIL.__version__,
          'python':sys.executable,'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),
          'source_manifest_sha256':sha(manifest_path),'eligible_sha256':sha(Path(C.R49)/'audit_v2/eligible_cases.jsonl'),
          'code_sha256':{p:sha(ROOT/p) for p in ['mt51_audit.py','mt50_common.py','mt50_prep.py']},
          'base_plans':plans,'helper_blobs':blobs,'previous_audits':audit_files,
          'note':'파일·sheet 연결 검증만 완료. 시각적 검증은 case별 신규 기록 필요.'})
    print('PASS: 254 cases / 896 images, source and sheet pixel identity; visual pending')

def record(batch, entries):
    src = json.loads((OUT/'audit/source_check.json').read_text())
    lookup = {r['case_id']:r for r in src['cases']}
    records = []
    for cid, decision, anatomy, note in entries:
        assert decision in ('keep','exclude','pending')
        r = lookup[cid]
        assert sha(ROOT/r['sheet']) == r['sheet_sha256']
        records.append({**r,'visual_status':decision,'anatomy':anatomy,'observation':note,
                        'evidence':f'iter_051 Codex view_image batch {batch}; 실제 반환 영상 직접 확인',
                        'reviewer':'Codex; 비전문가 주석 감사, 임상 gold 아님'})
    write(OUT/'audit/visual'/f'{batch}.json', records)
    print(batch, len(records))

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('action', choices=['prepare']); a=p.parse_args()
    prepare()
