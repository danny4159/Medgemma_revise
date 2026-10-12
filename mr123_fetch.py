"""iter_123: 선택 study ZIP 다운로드(공식 revision 고정, 토큰 내용 미기록). usage: python mr123_fetch.py tech|explore|reserve"""
import hashlib, json, os, sys, warnings
warnings.filterwarnings('ignore')
os.environ['HF_TOKEN_PATH'] = '/home/test/.cache/huggingface/token'
from huggingface_hub import HfApi, hf_hub_download

ROOT = '/home/test/.local/share/medgemma/mr_rate/'
RES = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_123/data/'
REV = 'f6e39794e7820c96c18465231a30da424e6d1c69'
BUDGET = 10 * 1024 ** 3


def sha(p):
    d = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            d.update(b)
    return d.hexdigest()


def main(roles):
    L = json.load(open(RES + 'selection_lock.json'))
    items = [r for r in L['manifest'] if r['role'] in roles]
    api = HfApi()
    infos = api.get_paths_info('Forithmus/MR-RATE', [r['zip_path'] for r in items], repo_type='dataset', revision=REV)
    size = {i.path: i.size for i in infos}
    led_p = RES + 'fetch_ledger.json'
    led = json.load(open(led_p)) if os.path.exists(led_p) else {}
    used = sum(v['size'] for v in led.values())
    need = sum(size[r['zip_path']] for r in items if r['study_uid'] not in led)
    free = os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize
    print(f'roles={roles} 새 다운로드 {need/1e6:.1f}MB, 누적 {used/1e6:.1f}MB, 예산 {BUDGET/1e9:.1f}GB, 여유 {free/1e9:.0f}GB')
    assert used + need <= BUDGET and need * 3 < free
    for r in items:
        if r['study_uid'] in led:
            continue
        p = hf_hub_download('Forithmus/MR-RATE', r['zip_path'], repo_type='dataset', revision=REV, local_dir=ROOT + 'raw',
                            cache_dir=ROOT + 'cache')
        assert os.path.getsize(p) == size[r['zip_path']]
        led[r['study_uid']] = dict(path=p, size=size[r['zip_path']], sha256=sha(p), revision=REV, role=r['role'])
        json.dump(led, open(led_p, 'w'), indent=1)
        print('ok', r['study_uid'], size[r['zip_path']])


if __name__ == '__main__':
    main(sys.argv[1:])
