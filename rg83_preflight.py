"""iter_083의 제한된 train 자료·출처 검사. 영상 접근 gate를 우회하지 않는다."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import requests

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parent / 'agent'
DATA = ROOT / 'results/iter_070/data/radgenome'
EXPECTED = {
    'BraTS_GLI/global_finding.json': 'b5deb0ce13fa6a987abe7dbaa01d3be90eb322c184e6d3c42cf695aa01b03865',
    'BraTS_GLI/modal_wise_finding.json': '978952a16c1f99ed11b62c8b47c5e2266f0d21819873da86aa70a778edfd51ee',
    'train_val_test_split.json': 'a6c32048292cdd869280d643da31e381a2fa47c1241efb79080cefd7ed1901e5',
}
REVIEW = {
    '00017-000': ('HIGH', 'ABSENT', 'hyperintense', 'no midline shift is observed', ''),
    '00021-000': ('MIXED', 'PRESENT', 'mixed high and low signal intensities', 'a leftward shift of midline structures', ''),
    '00024-000': (None, 'ABSENT', 'some mixed signals within the lesion', 'no midline shift is present', '고신호와 mixed가 공존하지만 고·저 혼합이 명시되지 않음'),
    '00045-001': ('MIXED', 'ABSENT', 'mixed high and low signal', 'no midline shift is observed', 'modal의 미언급은 음성 근거가 아니며 global의 명시적 부재를 사용'),
    '00046-000': (None, 'ABSENT', 'mixed signal intensity', 'no midline shift is observed', 'mixed만으로 고·저 혼합을 확정할 수 없음'),
    '00053-000': ('MIXED', 'PRESENT', 'mixed high and low signal intensity', 'a rightward deviation of midline structures', '복수 병변과 union의 실제 대응은 미검증'),
    '00061-000': (None, 'ABSENT', 'neither clearly hyperintense nor hypointense', 'no shift of midline structures', 'global의 고·저 혼합과 modal의 neither 표현의 대응이 모호함'),
    '00064-000': ('MIXED', 'PRESENT', 'mixed high and low signal intensity', 'a rightward deviation of midline structures', ''),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def train_ids(split):
    scans = sorted({x.rsplit('-', 1)[0] for x in split['train'] if x.startswith('BraTS-GLI-')})
    patients = {}
    for scan in scans:
        patients.setdefault(scan.rsplit('-', 1)[0], scan)
    return scans, list(patients.values())


def guarded_reports(ids, allowed, global_reports, modal_reports):
    if not set(ids) <= set(allowed):
        raise ValueError('train 밖의 보고서 요청 거부')
    return {k: {'global': global_reports[k], 'flair': modal_reports[k + '-t2f']} for k in ids}


def span(text, needle):
    start = text.index(needle)
    return {'text': needle, 'start': start, 'end': start + len(needle)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    if not out.is_relative_to(ROOT / 'results/iter_083'):
        raise ValueError('iter_083 결과 경로만 허용')
    out.mkdir(parents=True, exist_ok=False)
    input_hashes = {name: sha(DATA / name) for name in EXPECTED}
    assert input_hashes == EXPECTED, '기존 자료 digest 불일치'
    reuse_path = AGENT / 'runs/iter_083/reuse_manifest.json'
    reuse = json.loads(reuse_path.read_text())
    blobs = {}
    for name, info in reuse['files'].items():
        p = ROOT / name
        assert not p.is_symlink()
        actual = subprocess.check_output(['git', 'hash-object', '--', name], cwd=ROOT, text=True).strip()
        assert actual == info['blob'], name
        blobs[name] = {'blob': actual, 'source_commit': info['source_commit'], 'sha256': sha(p)}
    write(out / 'source_audit.json', {'input_sha256': input_hashes, 'reuse_manifest_sha256': sha(reuse_path), 'blobs': blobs,
          'runtime_reuse': '없음: 학습·추론 모듈을 import하거나 실행하지 않음',
          'required_checks': {'blob_check': 'PASS', 'new_task_gpu_checks': 'NOT_RUN_DATA_ACCESS_GATE'}})
    split = json.loads((DATA / 'train_val_test_split.json').read_text())
    scans, patients = train_ids(split)
    chosen = patients[:8]
    assert chosen == ['BraTS-GLI-' + k for k in REVIEW]
    rows = guarded_reports(chosen, patients,
                           json.loads((DATA / 'BraTS_GLI/global_finding.json').read_text()),
                           json.loads((DATA / 'BraTS_GLI/modal_wise_finding.json').read_text()))
    for k, r in rows.items():
        signal, displacement, signal_span, displacement_span, note = REVIEW[k.removeprefix('BraTS-GLI-')]
        r.update(signal=signal, displacement=displacement,
                 signal_span=span(r['flair'], signal_span), displacement_span=span(r['global'], displacement_span),
                 note=note, status='원문 후보만 검토; 영상·mask 연결 미검증')
    write(out / 'train_review8.json', {'train_scans': len(scans), 'patient_prefixes': len(patients),
          'selection_rule': 'label 적격 판정 전 patient prefix별 사전순 첫 scan, 그 후 첫 8명',
          'rows': rows, 'final_eligibility': False, 'split_created': False})
    fixtures = {}
    try:
        guarded_reports(['outside'], patients, {}, {})
    except ValueError:
        fixtures['non_train_report_rejected'] = True
    fixtures['earliest_scan'] = train_ids({'train': ['BraTS-GLI-00001-001-t2f', 'BraTS-GLI-00001-000-t2f']})[1] == ['BraTS-GLI-00001-000']
    fixtures['ambiguous_mixed_not_positive'] = rows['BraTS-GLI-00024-000']['signal'] is None
    fixtures['crossing_not_displacement_evidence'] = 'cross' not in rows['BraTS-GLI-00053-000']['displacement_span']['text']
    fixtures['mention_absence_not_negative_evidence'] = 'mention' not in rows['BraTS-GLI-00045-001']['displacement_span']['text']
    fixtures['all_spans_roundtrip'] = all(r['flair'][r['signal_span']['start']:r['signal_span']['end']] == r['signal_span']['text'] and r['global'][r['displacement_span']['start']:r['displacement_span']['end']] == r['displacement_span']['text'] for r in rows.values())
    assert all(fixtures.values())
    write(out / 'fixtures.json', fixtures)
    urls = {
        'mapping_entity': 'https://repo-prod.prod.sagebase.org/repo/v1/entity/syn51615438',
        'mapping_access': 'https://repo-prod.prod.sagebase.org/repo/v1/entity/syn51615438/accessRequirement',
        'mapping_download': 'https://repo-prod.prod.sagebase.org/repo/v1/entity/syn51615438/file',
        'mirror_card': 'https://huggingface.co/datasets/MedOtter/brats2023-gli-dataset/raw/b032d353a3e80911a5f850bc54e6fb575298a354/README.md',
    }
    attempts = {}
    for name, url in urls.items():
        t = time.time()
        try:
            r = requests.get(url, timeout=30, allow_redirects=False)
            # 인증·signed URL은 저장하지 않는다. 공개 metadata와 오류 본문만 보존한다.
            record = {'url': url, 'status_code': r.status_code, 'timestamp': t,
                      'body': r.text if r.status_code in (200, 403) else '', 'redirect': r.is_redirect}
        except requests.RequestException as e:
            record = {'url': url, 'timestamp': t, 'error_type': type(e).__name__}
        attempts[name] = record
    write(out / 'access_attempts.json', attempts)
    write(out / 'release_evidence.json', {
        'official_release_url': 'https://www.synapse.org/Synapse:syn51156910/discussion/threadId=10714',
        'corroborating_url': 'https://www.synapse.org/Synapse:syn27046444/discussion/threadId=10197',
        'finding': '공식 공개 설명은 2021/2023 GLI 영상 동일성과 ET label 4→3 변경을 뒷받침한다.',
        'scope': '이는 release 설명이며 현재 mirror 파일의 voxel 동일성 또는 접근 요건 충족의 인증은 아니다.',
        'mapping_download_status': attempts['mapping_download'].get('status_code'),
        'image_files_downloaded': 0, 'visual_audit': 'NOT_PERFORMED'})
    write(out / 'incident.json', {
        'type': '비학습 split 내용의 우발적 터미널 출력',
        'detail': '초기 schema 확인에서 split dict 앞부분(test ID) 및 global dict 앞부분을 출력했다. test 보고서 00006-000과 00032-001 일부, val 보고서 일부가 노출됐다.',
        'response': '이후 모든 보고서 출력은 train membership 검사 후 수행. 공식 val/test 영상·모델 평가·학습은 실행하지 않음.',
        'limitation': '공식 val/test 원문을 전혀 열지 않았다는 주장은 불가. 새 학습·표본 선택에는 사용하지 않음.'})
    write(out / 'gate.json', {
        'run_training': False, 'stage': 'bounded_data_check_incomplete',
        'reason': '공식 mapping 다운로드의 접근 요건 미충족. mirror의 공개 license 표기만으로 공식 접근 요건 해결을 확정하지 않음. 실제 train 영상·mask 연결 미검증.',
        'not_a_model_result': True,
        'next_required_evidence': '사용자의 공식 BraTS 접근 요건 충족 또는 사용 권한·출처가 검증된 원본 영상 경로. 이후 최대 8명 실제 영상·mask 연결 검사를 계속한다.',
        'source_checks_passed': True, 'gpu_requests': 0, 'training_updates': 0,
        'environment': {'python': sys.executable, 'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES')},
        'new_task_required_checks': '자료 gate 전이므로 tensor/loss/LoRA/동결/재개/처리량/비용 검사 미실행'})
    write(out / 'completion.json', {'scope': '출처 검사와 접근 실패 기록만 완료; 실험 완료 아님',
          'self_check': 'FAIL', 'source_sha256': sha(__file__),
          'files': {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}})
    print(json.dumps({'out': str(out), 'fixtures': len(fixtures), 'reuse_blobs': len(blobs),
                      'train_scans': len(scans), 'patients': len(patients),
                      'mapping_status': attempts['mapping_download'].get('status_code'), 'run_training': False}))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
