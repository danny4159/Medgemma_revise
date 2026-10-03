"""iter_061: OmniBrainBench closed-ended MRI 진단 QA 적격성·cluster·D/E 잠금 (모델 출력을 보지 않는다).

공식 loader의 누락 영상 fallback을 쓰지 않는다. 영상은 ZIP basename으로 정확히 한 번 대응해야 한다.
"""
import hashlib, io, json, os, re, sys, zipfile, collections
import numpy as np
from PIL import Image

SEED = 61
ROOT = 'results/iter_061/data'
RAW = f'{ROOT}/raw'
IMG = f'{ROOT}/images'
MRI = {'mri', 't1w', 't2w', 'flair', 't1ce', 'adc', 'dwi', 'magnetic resonance angiography'}
REV = '899f22f932c46eeb1e034d1693742e2cb6bbddc4'
ZIP_SHA = '471d4e7f3b2e2a2c3f83720580c5b6105fc2fe753692bade024f294a1ee788ac'
JSON_SHA = None  # 실행 시 기록


def sha(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def paths(x):
    return list(x['image_path']) if isinstance(x['image_path'], list) else [x['image_path']]


def answer_text(x):
    return x['options']['ABCDE'.index(x['answer'])]


def cluster_key(x):
    p = paths(x)[0]
    for pat in (r'(BraTS2021_\d+)', r'(BraTS-MEN-\d+)', r'(BraTS-MET-\d+)', r'(strokecase\d+)',
                r'(case\d{4})', r'(pmc_\d+)'):
        m = re.search(pat, p)
        if m:
            return x['source_file'].split('_')[0] + ':' + m.group(1)
    return x['source_file'].split('_')[0] + ':' + os.path.splitext(p)[0]


def eligibility(x, zbase):
    """모델 출력과 무관한 규칙. (ok, reason)"""
    if x['task_label'] != 'Disease Diagnosis Reasoning':
        return False, 'task_not_diagnosis'
    mt = x['modality_type']
    if not all(m.lower() in MRI for m in mt):
        return False, 'non_mri_modality'
    if 'diagnos' not in x['question'].lower():
        return False, 'not_diagnosis_question'
    if len(x['options']) != 5 or len(set(o.strip().lower() for o in x['options'])) != 5:
        return False, 'options_not_unique5'
    if x['answer'] not in list('ABCDE'):
        return False, 'bad_answer'
    a = answer_text(x)
    if a.strip().lower() in x['question'].lower():
        return False, 'answer_in_question'
    ps = paths(x)
    if len(set(ps)) != len(ps):
        return False, 'dup_image_in_qa'
    if any(p not in zbase for p in ps):
        return False, 'image_missing'
    return True, ''


def main():
    os.makedirs(IMG, exist_ok=True)
    assert file_sha(f'{RAW}/closed-ended-qa_6823.zip') == ZIP_SHA
    d = json.load(open(f'{RAW}/closed-ended-qa_6823.json'))
    z = zipfile.ZipFile(f'{RAW}/closed-ended-qa_6823.zip')
    zbase = {}
    for n in z.namelist():
        if n.endswith('/'):
            continue
        b = os.path.basename(n)
        assert b not in zbase and '..' not in n and not n.startswith('/')
        zbase[b] = n
    elig, excl = [], collections.Counter()
    for x in d:
        ok, why = eligibility(x, zbase)
        if ok:
            elig.append(x)
        else:
            excl[why] += 1
    print('eligible QA', len(elig), dict(excl))
    # 영상 추출·hash (적격 QA의 영상만)
    info = {}
    for x in elig:
        for p in paths(x):
            if p in info:
                continue
            raw = z.read(zbase[p])
            im = Image.open(io.BytesIO(raw))
            im.load()
            rgb = im.convert('RGB')
            out = f'{IMG}/{p}'
            if os.path.exists(out):
                assert sha(open(out, 'rb').read()) == sha(raw), p
            else:
                with open(out, 'wb') as f:
                    f.write(raw)
            info[p] = {'file_sha256': sha(raw), 'pixel_sha256': sha(np.asarray(rgb).tobytes()),
                       'size': list(rgb.size), 'mode': im.mode}
    # connected component: cluster_key + 동일 pixel hash 공유
    par = {}

    def find(a):
        par.setdefault(a, a)
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def union(a, b):
        par[find(a)] = find(b)

    for x in elig:
        k = 'C:' + cluster_key(x)
        find(k)
        for p in paths(x):
            union(k, 'H:' + info[p]['pixel_sha256'])
    comp = collections.defaultdict(list)
    for x in elig:
        comp[find('C:' + cluster_key(x))].append(x)
    pool = []
    for r, xs in comp.items():
        cid = min(cluster_key(x) for x in xs)
        xs = sorted(xs, key=lambda x: sha(f'{SEED}|qa|{cid}|{x["id"]}'.encode()))
        x = xs[0]
        ps = paths(x)
        pool.append({'cluster_id': cid, 'qa_id': x['id'], 'source': x['source_file'].split('_')[0], 'K': len(ps),
                     'n_qa_in_component': len(xs), 'n_clusters_keys': len(set(cluster_key(y) for y in xs)),
                     'images': ps, 'answer_text': answer_text(x)})
    vx = f'{ROOT}/visual_exclusions.json'
    VEX = json.load(open(vx)) if os.path.exists(vx) else {}
    n0 = len(pool)
    pool = [r for r in pool if r['cluster_id'] not in VEX]
    print('components', n0, 'after visual exclusions', len(pool), 'multi', sum(1 for r in pool if r['K'] >= 2))

    def binK(k):
        return '1' if k == 1 else '2' if k == 2 else '3-4' if k <= 4 else '5+'

    byhash = lambda tag, r: sha(f'{SEED}|{tag}|{r["cluster_id"]}'.encode())
    # D: 최대 K 사례 + (source,Kbin)이 다른 사례를 우선, 부족하면 hash 순
    order = sorted(pool, key=lambda r: byhash('D', r))
    D = [max(order, key=lambda r: (r['K'], byhash('Dmax', r)))]
    used = {(D[0]['source'], binK(D[0]['K']))}
    for r in order:
        if len(D) >= 6:
            break
        if r in D:
            continue
        if (r['source'], binK(r['K'])) not in used:
            D.append(r)
            used.add((r['source'], binK(r['K'])))
    for r in order:
        if len(D) >= 6:
            break
        if r not in D:
            D.append(r)
    Dids = {r['cluster_id'] for r in D}
    rest = [r for r in pool if r['cluster_id'] not in Dids]
    multi = [r for r in rest if r['K'] >= 2]
    main_pool = multi if multi else rest
    strata = collections.defaultdict(list)
    for r in main_pool:
        strata[(r['source'], binK(r['K']))].append(r)
    for k in strata:
        strata[k].sort(key=lambda r: byhash('E', r))
    keys = sorted(strata, key=lambda k: sha(f'{SEED}|stratum|{k}'.encode()))
    E = []
    i = 0
    while any(i < len(strata[k]) for k in keys):
        for k in keys:
            if i < len(strata[k]):
                E.append(strata[k][i])
        i += 1
    single = sorted([r for r in rest if r['K'] == 1], key=lambda r: byhash('S', r))
    lock = {
        'dataset_revision': REV, 'zip_sha256': ZIP_SHA, 'json_sha256': file_sha(f'{RAW}/closed-ended-qa_6823.json'),
        'seed': SEED, 'n_eligible_qa': len(elig), 'exclusion_counts': dict(excl), 'n_pool': len(pool),
        'visual_exclusions': VEX, 'D': D, 'E_ordered_multi': E, 'E_single_ordered': single[:200],
        'strata_sizes': {f'{k[0]}|{k[1]}': len(v) for k, v in strata.items()},
        'rules': 'see plan.md; selection uses only metadata + hashes (no model output)',
    }
    json.dump(lock, open(f'{ROOT}/selection_lock.json', 'w'), indent=1, ensure_ascii=False)
    json.dump(info, open(f'{ROOT}/image_manifest.json', 'w'), indent=1)
    json.dump([x for x in elig], open(f'{ROOT}/eligible_qa.json', 'w'), ensure_ascii=False)
    print('strata', lock['strata_sizes'])
    print('D', [(r['cluster_id'], r['K']) for r in D])
    print('E first 24', [(r['cluster_id'], r['K']) for r in E[:24]])
    print('E len', len(E), 'single', len(single))


if __name__ == '__main__':
    main()
