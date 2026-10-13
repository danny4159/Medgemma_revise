"""iter_134: 후보 순서 봉인(seed134) 및 필요한 FLAIR(t2f)·seg 파일만 미러에서 확보. 전체 snapshot 금지.
순서는 다운로드 전에 order.json으로 봉인한다. 기존 파일은 덮어쓰지 않고 크기·LFS sha256으로 검증한다."""
import sys, hashlib, json, os
from pathlib import Path
from i134_common import *

TOK = Path('/home/test/.cache/huggingface/token')


def candidates():
    s = read(OLD / 'radgenome/train_val_test_split.json'); mf = read(OLD / 'radgenome/BraTS_GLI/modal_wise_finding.json')
    lst = dict(read(OLD / 'medotter_listing.json')['files']); assert read(OLD / 'medotter_listing.json')['sha'] == REVISION
    tr = sorted(set(k[:-4] for k in s['train'] if k.endswith('-t2f')))
    out = [p for p in tr if p + '-t2f' in mf and BASE + p + '/' + p + '-t2f.nii.gz' in lst and BASE + p + '/' + p + '-seg.nii.gz' in lst]
    return out, lst, mf


def seal_order():
    c, lst, mf = candidates(); assert len(c) == 161
    order = sorted(c, key=lambda p: hashlib.sha256(('%d|%s' % (SEED, p)).encode()).hexdigest())
    sizes = {p: [lst[BASE + p + '/' + p + '-t2f.nii.gz'], lst[BASE + p + '/' + p + '-seg.nii.gz']] for p in c}
    save(DATA / 'order.json', dict(created_at=now(), rule='sorted by sha256("134|"+pid); first 4 technical, then eligible cases in order for main32',
                                    split='RadGenome train', n_candidates=len(c), order=order, listing_sizes=sizes,
                                    listing_sha256=sha(OLD / 'medotter_listing.json'), split_sha256=sha(OLD / 'radgenome/train_val_test_split.json'),
                                    modal_finding_sha256=sha(OLD / 'radgenome/BraTS_GLI/modal_wise_finding.json')))
    print('sealed', len(order), order[:6])


def fetch(pids):
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi(token=TOK.read_text().strip() if TOK.exists() else None)
    for p in pids:
        for suf in ('-t2f.nii.gz', '-seg.nii.gz'):
            rel = BASE + p + '/' + p + suf; dst = BRATS / BASE / p / (p + suf)
            info = api.get_paths_info(REPO, [rel], repo_type='dataset', revision=REVISION)[0]
            want = info.lfs.sha256 if info.lfs else None
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                got = hf_hub_download(REPO, rel, repo_type='dataset', revision=REVISION, local_dir=str(DATA / '_dl'), token=api.token)
                os.replace(got, str(dst) + '.part'); os.replace(str(dst) + '.part', dst)
            assert want is None or sha(dst) == want, 'sha mismatch ' + rel
            print(p, suf, dst.stat().st_size, 'ok', flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'seal': seal_order()
    else: fetch(read(DATA / 'order.json')['order'][:int(sys.argv[2])])
