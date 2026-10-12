"""iter_125: 선택 T2 안전 추출(study/series/revision별 경로, member·파일 sha 기록) + SynthSeg 실행.
usage: python mr125_seg.py ROLE GPU_INDEX   (SynthSeg 공식 commit 2a2aa3b, 번들 synthseg_1.0.h5; 2.0 가중치는 접근 불가)"""
import hashlib, json, os, subprocess, sys, time, zipfile

ROOT = '/home/test/.local/share/medgemma/mr_rate/e125/'
RES = 'results/iter_125/'
REV = 'f6e39794e7820c96c18465231a30da424e6d1c69'
ENVPY = os.path.abspath('results/environments/synthseg125/bin/python')
SS = os.path.abspath('results/external/synthseg_src/SynthSeg-2a2aa3bbfccb83f8253a51ca8b329b9938a2646d')


def sha_file(p):
    d = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            d.update(b)
    return d.hexdigest()


def extract(m, zip_path):
    out = os.path.join(ROOT, REV[:8], m['study_uid'], m['series_id'])
    os.makedirs(out, exist_ok=True)
    want = {f'{m["study_uid"]}/img/{m["study_uid"]}_{m["series_id"]}.nii.gz': 'img.nii.gz',
            f'{m["study_uid"]}/seg/{m["study_uid"]}_{m["series_id"]}_brain-mask.nii.gz': 'brain.nii.gz'}
    z = zipfile.ZipFile(zip_path)
    res = {}
    for info in z.infolist():
        if info.filename in want:
            assert '..' not in info.filename and not info.filename.startswith('/')
            assert (info.external_attr >> 16) & 0o170000 != 0o120000
            dst = os.path.join(out, want[info.filename])
            if not os.path.exists(dst):
                with z.open(info) as s, open(dst + '.part', 'wb') as d:
                    for b in iter(lambda: s.read(1 << 22), b''):
                        d.write(b)
                os.replace(dst + '.part', dst)
            h = sha_file(dst)
            assert os.path.getsize(dst) == info.file_size
            res[want[info.filename]] = dict(path=dst, sha256=h, size=info.file_size, zip_member=info.filename, zip_crc=info.CRC)
    assert set(res) == set(want.values()), 'missing member'
    return out, res


def main(role, gpu):
    L = json.load(open(RES + 'data/selection_lock.json'))
    led = json.load(open(RES + 'data/fetch_ledger.json'))
    prov_p = RES + f'seg/prov_{role}.json'
    os.makedirs(RES + 'seg', exist_ok=True)
    prov = json.load(open(prov_p)) if os.path.exists(prov_p) else {}
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), TF_FORCE_GPU_ALLOW_GROWTH='true', TF_CPP_MIN_LOG_LEVEL='2')
    for m in L['manifest']:
        if m['role'] != role or m['study_uid'] in prov:
            continue
        zp = led[m['study_uid']]['path']
        assert sha_file(zp) == led[m['study_uid']]['sha256']
        out, files = extract(m, zp)
        so = os.path.join(out, 'synthseg1.nii.gz')
        volcsv = os.path.join(out, 'synthseg1_vol.csv')
        t0 = time.time()
        if not os.path.exists(so):
            r = subprocess.run([ENVPY, SS + '/scripts/commands/SynthSeg_predict.py', '--i', files['img.nii.gz']['path'], '--o', so + '.tmp.nii.gz', '--v1', '--threads', '4'],
                               env=env, capture_output=True, text=True, cwd=SS)
            open(os.path.join(out, 'synthseg1.log'), 'w').write(r.stdout[-4000:] + '\n---\n' + r.stderr[-4000:])
            assert r.returncode == 0, (m['study_uid'], r.stderr[-1500:])
            os.replace(so + '.tmp.nii.gz', so)
        prov[m['study_uid']] = dict(files=files, seg=so, seg_sha256=sha_file(so), vol_csv=volcsv, seconds=time.time() - t0, gpu=gpu)
        json.dump(prov, open(prov_p + '.tmp', 'w'), indent=1)
        os.replace(prov_p + '.tmp', prov_p)
        print('ok', m['study_uid'], round(time.time() - t0, 1), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
