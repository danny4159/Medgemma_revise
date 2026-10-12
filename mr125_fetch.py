"""iter_125: 선택 study ZIP 다운로드(mr123_fetch.py 수정본; 출처 e39ba0666faf). 공식 revision 고정, LFS sha256으로 기존/신규 ZIP 모두 검증, 누적 예산 선계산, 원자적 ledger. 토큰 내용 미출력.
usage: python mr125_fetch.py ROLE[,ROLE] [--dry]"""
import hashlib, json, os, sys, warnings
warnings.filterwarnings('ignore')
os.environ['HF_TOKEN_PATH'] = '/home/test/.cache/huggingface/token'
from huggingface_hub import HfApi, hf_hub_download

ROOT = '/home/test/.local/share/medgemma/mr_rate/'
RES = 'results/iter_125/data/'
OLD_LEDGERS = ['results/iter_123/data/fetch_ledger.json']
REV = 'f6e39794e7820c96c18465231a30da424e6d1c69'
BUDGET = 10 * 1024 ** 3  # 누적 ZIP 예산(기존 iter_123 54개 포함)


def sha(p):
    d = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            d.update(b)
    return d.hexdigest()


def atomic_json(obj, p):
    with open(p + '.tmp', 'w') as f:
        json.dump(obj, f, indent=1)
    os.replace(p + '.tmp', p)


def main(roles, dry):
    L = json.load(open(RES + 'selection_lock.json'))
    assert L['manifest']
    items = [r for r in L['manifest'] if r['role'] in roles]
    old = {}
    for p in OLD_LEDGERS:
        old.update(json.load(open(p)))
    api = HfApi()
    led_p = RES + 'fetch_ledger.json'
    led = json.load(open(led_p)) if os.path.exists(led_p) else {}
    # 기존 ZIP: 크기·공식 sha256 검증
    zp = lambda r: f'mri/{r["batch_id"]}/{r["study_uid"]}.zip'
    paths = [zp(r) for r in items] + [v['path'].split('raw/')[-1] for v in old.values()]
    info = {i.path: i for i in api.get_paths_info('Forithmus/MR-RATE', paths, repo_type='dataset', revision=REV)}
    old_total = 0
    for k, v in old.items():
        rel = v['path'].split('raw/')[-1]
        i = info[rel]
        assert os.path.getsize(v['path']) == i.size == v['size'], ('old size', k)
        assert v['sha256'] == i.lfs.sha256, ('old sha', k)
        old_total += i.size
    new_need = sum(info[zp(r)].size for r in items if r['study_uid'] not in led)
    used_new = sum(v['size'] for v in led.values())
    free = os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize
    print(f'roles={roles} 기존 {old_total/1e9:.2f}GB(54) + 이번 이전 {used_new/1e9:.2f}GB + 새로 {new_need/1e9:.2f}GB = {(old_total+used_new+new_need)/1e9:.2f}GB / 예산 {BUDGET/1e9:.2f}GB, 디스크 여유 {free/1e9:.0f}GB')
    if old_total + used_new + new_need > BUDGET or new_need * 3 > free:
        print('BUDGET_EXCEEDED: 다운로드 중단')
        sys.exit(3)
    if dry:
        return
    for r in items:
        if r['study_uid'] in led:
            continue
        i = info[zp(r)]
        p = hf_hub_download('Forithmus/MR-RATE', zp(r), repo_type='dataset', revision=REV, local_dir=ROOT + 'raw', cache_dir=ROOT + 'cache')
        assert os.path.getsize(p) == i.size
        h = sha(p)
        assert h == i.lfs.sha256, ('sha mismatch', r['study_uid'])
        led[r['study_uid']] = dict(path=p, size=i.size, sha256=h, revision=REV, role=r['role'], official_lfs_sha256=i.lfs.sha256)
        atomic_json(led, led_p)
        print('ok', r['study_uid'], i.size)


if __name__ == '__main__':
    main(sys.argv[1].split(','), '--dry' in sys.argv)
