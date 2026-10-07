"""iter_089 고정 표본과 D8 자료 확인. 과거 산출물에는 쓰지 않는다."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw
import pg39_data as D
from report86_common import sha, save
from rsna_diag.geometry import pad_offsets, canvas_to_norm

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results/iter_089'
SEED = 89017
EXPOSED = [
    'results/iter_039/data/manifest_private.jsonl',
    'results/iter_040/data/manifest_train_private.jsonl',
    'results/iter_040/data/manifest_eval_private.jsonl',
    'results/iter_042/data/manifest_private.jsonl',
    'results/iter_043/data/manifest_private.json',
    'results/iter_047/data/manifest_D8.json',
    'results/iter_053/data/manifest_D.json',
    'results/iter_053/data/manifest_E.json',
    'results/iter_053/data/manifest_F.json',
    'results/iter_085/D8/inputs.json',
    'results/iter_086/E/inputs_E96.json',
    'results/iter_086/E/inputs_E192x.json',
]


def read(p):
    p = Path(p)
    return [json.loads(s) for s in p.read_text().splitlines()] if p.suffix == '.jsonl' else json.loads(p.read_text())


def walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)


def key(r):
    return D.h(SEED, r['PatientID'], r['ImageID'])


def current_findings(r):
    keep, excluded = [], []
    for i, f in enumerate(r['findings']):
        s = f.get('sentence_en', '')
        if not isinstance(s, str) or not s.strip():
            excluded.append([i, 'empty'])
        elif f.get('progression') is not None or D.TEMPORAL_RE.search(s):
            excluded.append([i, 'temporal'])
        else:
            if any(not D.valid_box(b) for b in f.get('boxes', [])):
                raise ValueError(('invalid box', r['ImageID'], i))
            keep.append(dict(f, source_index=i))
    return keep, excluded


def stratum(fs, original_abnormal):
    if any(f.get('abnormal') is True and f.get('boxes') for f in fs):
        return 'abnormal_box'
    if original_abnormal:
        return 'abnormal_no_box'
    return 'no_abnormal_annotation'


def take(pool, n):
    by = defaultdict(list)
    for r in sorted(pool, key=key):
        by[r['stratum']].append(r)
    sizes = {k: len(v) for k, v in by.items()}
    q = D.apportion(sizes, min(n, len(pool)))
    for k in sorted(q):
        if sizes[k] and q[k] == 0:
            donor = max(q, key=q.get)
            assert q[donor] > 1
            q[donor] -= 1
            q[k] += 1
    return sorted([r for k in by for r in by[k][:q[k]]], key=key), q


def select():
    reports, master, links = D.load_inputs()
    source = {p: sha(ROOT/p) for p in EXPOSED}
    seen = {r['ImageID'] for p in EXPOSED for r in walk(read(ROOT/p)) if r.get('ImageID') in links['img2patient']}
    protected = [r for r in read(ROOT/EXPOSED[0]) if r.get('subset') == 'F']
    protected += [r for r in read(ROOT/EXPOSED[2]) if r.get('eval_set') == 'H192']
    assert len(protected) == 312
    protected_pat = {r['PatientID'] for r in protected}
    exposed_pat = {links['img2patient'][i] for i in seen}
    excluded_test = '251488034557732338959601580328898734705_wigcpj.png'
    exposed_pat.add(links['img2patient'][excluded_test])
    pools = defaultdict(dict)
    counts = Counter()
    for r in reports:
        iid = r['ImageID']; pid = links['img2patient'][iid]; split = links['img2split'][iid]
        if split not in ('train', 'test'):
            continue
        if pid in (protected_pat if split == 'train' else exposed_pat | protected_pat):
            counts[split + '_excluded_patient'] += 1
            continue
        fs, ex = current_findings(r)
        counts[split + '_temporal_or_empty_sentences'] += len(ex)
        if not fs:
            counts[split + '_no_current_sentences'] += 1
            continue
        original_abnormal = any(f.get('abnormal') is True for f in r['findings'])
        row = dict(ImageID=iid, PatientID=pid, StudyID=r['StudyID'], split=split,
                   stratum=stratum(fs, original_abnormal), original_abnormal=original_abnormal,
                   retained_abnormal=any(f.get('abnormal') is True for f in fs),
                   excluded_sentences=ex)
        if pid not in pools[split] or key(row) < key(pools[split][pid]):
            pools[split][pid] = row
    train, tq = take(list(pools['train'].values()), 512)
    tids = {r['PatientID'] for r in train}
    val, vq = take([r for r in pools['train'].values() if r['PatientID'] not in tids], 64)
    assert len(train) == 512 and len(val) == 64
    # E는 ID·층만 잠근다. reference 원문과 영상은 checkpoint 선택 뒤에 연다.
    test = []
    for flag, n in [(True, 96), (False, 32)]:
        group = [r for r in pools['test'].values() if r['retained_abnormal'] == flag
                 and (flag or not r['original_abnormal'])]
        test += sorted(group, key=key)[:n]
    byid = {r['ImageID']: r for r in reports}
    dev = []
    for s in sorted(tq):
        dev.append(next(r for r in train if r['stratum'] == s))
    for measure in [lambda r: sum(len(f['sentence_en']) for f in current_findings(byid[r['ImageID']])[0]),
                    lambda r: max([len(f.get('boxes', [])) for f in current_findings(byid[r['ImageID']])[0]] or [0])]:
        r = max(train, key=lambda r: (measure(r), key(r)))
        if r not in dev:
            dev.append(r)
    dev += [r for r in train if r not in dev][:8-len(dev)]
    v32, _ = take(val, 32)
    v16 = [r for r in val if r['stratum'] == 'abnormal_box'][:16]
    assert len(v16) == 16
    selected = dict(T512=train, V64=val, D8=dev, V32=v32, V16=v16, E128=test)
    save(OUT/'data/selection.json', selected)
    save(OUT/'data/selection_lock.json', dict(seed=SEED, selection_sha256=sha(OUT/'data/selection.json'),
         sources=source, metadata=links['inputs_sha256'], protected_patients=sorted(protected_pat),
         exposed_images=sorted(seen), exposed_patients=sorted(exposed_pat), counts=dict(counts),
         pools={s: dict(Counter(r['stratum'] for r in rs.values())) for s, rs in pools.items()},
         allocation=dict(T512=tq,V64=vq),
         frontal_source='https://doi.org/10.1056/AIdbp2401120',
         frontal_evidence='공식 논문: 4555장 모두 PA/AP/AP-horizontal frontal 선별',
         test_pixel_dedup='설정 선택 뒤 실제 추출 시 필수; 현재 ID 사전 잠금은 pixel 검증 완료가 아님',
         code_sha256=sha(__file__)))
    print(json.dumps({'sizes':{k:len(v) for k,v in selected.items()},'train_quota':tq,'val_quota':vq,'counts':dict(counts)}))


def extract(subset):
    lock = read(OUT/'data/selection_lock.json')
    assert sha(OUT/'data/selection.json') == lock['selection_sha256']
    rows = read(OUT/'data/selection.json')[subset]
    assert subset in ('D8','T512','V64'), 'E 추출은 선택 잠금 후 별도 진입 필요'
    reports, _, _ = D.load_inputs(); byid={r['ImageID']:r for r in reports}
    z = D.open_image_zip(); idx = D.zip_index(z)
    out = OUT/'data'/subset; out.mkdir(parents=True, exist_ok=False)
    manifest=[]
    for row in rows:
        b=z.read(idx[row['ImageID']]); arr=np.asarray(Image.open(io.BytesIO(b)))
        assert arr.ndim==2 and arr.dtype==np.uint16
        raw=out/(row['ImageID']+'.raw.png'); raw.write_bytes(b)
        u8=(arr // 256).astype(np.uint8)
        im=out/row['ImageID']; Image.fromarray(u8).save(im)
        h,w=arr.shape; top,left,side=pad_offsets(h,w)
        fs,ex=current_findings(byid[row['ImageID']])
        fs=[dict(f, canvas_boxes=[canvas_to_norm([x0*w,y0*h,x1*w,y1*h],top,left,side)
              for x0,y0,x1,y1 in f.get('boxes',[])]) for f in fs]
        row=dict(row, findings=fs, report=' '.join(f['sentence_en'].strip() for f in fs),
                 image=str(im),file_sha256=sha(im), raw_path=str(raw),raw_sha256=sha(raw),
                 raw_pixel_sha256=hashlib.sha256(arr.tobytes()).hexdigest(),
                 u8_pixel_sha256=hashlib.sha256(u8.tobytes()).hexdigest(),shape=[h,w],
                 pad=[top,left,side],zip_member=idx[row['ImageID']].filename,zip_crc=idx[row['ImageID']].CRC)
        assert ex==row['excluded_sentences']
        manifest.append(row)
    assert len({r['raw_pixel_sha256'] for r in manifest})==len(manifest)
    save(out/'manifest.json',manifest)
    if subset=='D8':
        for i,row in enumerate(manifest):
            im=Image.open(row['image']).convert('RGB'); im.thumbnail((640,640)); dw=ImageDraw.Draw(im)
            w,h=im.size
            for f in row['findings']:
                for x0,y0,x1,y1 in f.get('boxes',[]):
                    dw.rectangle([x0*w,y0*h,x1*w,y1*h],outline='red',width=2)
                    dw.text((x0*w,y0*h),str(f['source_index']),fill='yellow')
            im.save(out/f'overlay_{i}.png')
    save(out/'completion.json',{'manifest_sha256':sha(out/'manifest.json'),'n':len(manifest),
         'source_code_sha256':sha(__file__),'selection_lock_sha256':sha(OUT/'data/selection_lock.json')})
    print(json.dumps({'subset':subset,'n':len(manifest)}))


def reuse():
    spec=read(ROOT.parent/'agent/runs/iter_089/reuse_manifest.json')
    checks=[]
    for p,x in spec['files'].items():
        got=subprocess.check_output(['git','hash-object','--',p],text=True).strip()
        checks.append({'path':p,'blob':got,'expected':x['blob'],'match':got==x['blob']})
        __import__(p.removesuffix('.py').replace('/','.'))
    assert all(c['match'] for c in checks)
    save(OUT/'reuse_import.json',{'checks':checks,'import':True,'scope':'blob/import만; 학습 검증 미완료'})
    print('reuse blob/import PASS',len(checks))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['select','extract','reuse']);ap.add_argument('--subset',default='D8')
    a=ap.parse_args()
    if a.command=='select':select()
    elif a.command=='extract':extract(a.subset)
    else:reuse()
