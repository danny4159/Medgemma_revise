"""iter_140의 한정 자료 검사. 자료 gate가 닫힌 경우 생성·학습을 시작하지 않는다.

기존 실패 기록은 입력 증거로만 읽는다. 현재 공개 metadata, 자격 설정의 존재,
고정 후보의 로컬 연결과 자산 digest를 별도 저장한다. 비밀 값은 기록하지 않는다.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
SOURCE_COMMIT = '3fb452dc0e53ebbbf26c0f9437afca348c18ea39'
FILES = ['i136_run.py', 'i136_common.py', 'i136_spec.py', 'i134_spec.py']
RAD_REV = '0348ba42fad134da57b50e736ba858a8e73eb086'
AUTO_REV = '9670703c88e8f599c0c7edc472a5ffce4dd72b0e'
RAD = HERE / 'results/iter_135/data_evidence/official/JiayuLei__RadGenome-Brain_MRI'


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def now():
    return datetime.now(timezone.utc).isoformat()


def save(p, value):
    with Path(p).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def verify(out):
    """현재 소스·원입력·산출물 모두 completion 당시 hash와 대조한다."""
    d = read(out / 'completion.json')
    checks = []
    for group in ['outputs', 'inputs', 'code']:
        for name, value in d[group].items():
            p = out / name if group == 'outputs' else Path(name)
            checks.append({'group': group, 'path': name, 'pass': p.is_file() and sha(p) == value})
    gate = read(out / 'gate.json')
    checks.append({'group': 'gate', 'path': 'unperformed_experiment_not_valid',
                   'pass': gate['run_generation'] is False and gate['valid_experiment'] is False})
    return {'checked_at': now(), 'all_pass': all(c['pass'] for c in checks), 'checks': checks}


def main(out, metadata_from=None):
    import requests
    import nibabel as nib
    import numpy as np
    from huggingface_hub import HfApi

    # 존재하는 결과 경로는 네트워크·출력 쓰기 전에 거부한다.
    if out.is_symlink() or out.exists():
        raise FileExistsError('기존 결과 경로는 변경하지 않는다: ' + str(out))
    if not out.resolve().is_relative_to((HERE / 'results/iter_140').resolve()):
        raise ValueError('iter_140 결과 범위 밖')
    out.mkdir(parents=True)
    t0 = time.monotonic()
    inputs = [PARENT / 'agent/runs/iter_140/plan.json', PARENT / 'agent/runs/iter_140/plan.md',
              PARENT / 'agent/runs/iter_140/reuse_manifest.json',
              HERE / 'results/iter_083/preflight_a1/train_review8.json',
              HERE / 'results/iter_083/preflight_a1/access_attempts.json',
              HERE / 'results/iter_083/preflight_a1/release_evidence.json',
              HERE / 'results/iter_135/data_evidence.json',
              HERE / 'results/iter_134/data/data_manifest_v2.json',
              RAD / 'BraTS_GLI/modal_wise_finding.json', RAD / 'train_val_test_split.json',
              RAD / 'README.md', HERE / 'results/iter_070/models/weights_manifest.json']
    input_hashes = {str(p): sha(p) for p in inputs}
    code_hashes = {str(HERE / p): sha(HERE / p) for p in FILES + [Path(__file__).name]}
    if metadata_from:
        old_baseline = read(metadata_from / 'baseline.json')
        for p, h in old_baseline['inputs'].items():
            assert sha(p) == h, '부분 감사 입력 변경: ' + p
        for p, h in old_baseline['code'].items():
            if Path(p) != Path(__file__).resolve():
                assert sha(p) == h, '반입 파일 변경: ' + p
        save(out / 'recovery.json', {'created_at': now(), 'previous_attempt': str(metadata_from),
             'previous_source_sha256': old_baseline['code'][str(Path(__file__).resolve())],
             'current_source_sha256': sha(__file__),
             'reason': '보존 raw snapshot에는 test.py가 없다. 존재하지 않는 raw 파일을 hash하던 코드 오류를 수정했다. 공식 archive source는 존재하며 별도로 기록한다.',
             'scientific_contract_changed': False, 'network_requests_reused': True})
    save(out / 'baseline.json', {'created_at': now(), 'inputs': input_hashes, 'code': code_hashes})
    manifest = read(PARENT / 'agent/runs/iter_140/reuse_manifest.json')
    reuse = []
    for name in FILES:
        current = subprocess.check_output(['git', 'hash-object', '--', name], cwd=HERE, text=True).strip()
        source = subprocess.check_output(['git', 'rev-parse', SOURCE_COMMIT + ':' + name], cwd=HERE, text=True).strip()
        assert current == source == manifest['files'][name]['blob'], name
        reuse.append({'path': name, 'source_commit': SOURCE_COMMIT, 'source_blob': source,
                      'current_blob': current, 'blob_match': True,
                      'required_checks': [
                          {'check': c, 'status': 'passed_blob_check_only' if i == 0 else 'not_run_data_gate_closed'}
                          for i, c in enumerate(manifest['files'][name]['required_checks'])]})
    save(out / 'reuse_checks.json', {'state': 'pending_runtime_validation', 'files': reuse})

    credential_files = [Path.home() / '.synapseConfig', Path('/home/test/.synapseConfig')]
    for name in ['SYNAPSE_CONFIG_FILE', 'SYNAPSE_CONFIG_PATH']:
        if os.environ.get(name):
            credential_files.append(Path(os.environ[name]))
    credentials = {
        'synapse_env_present': {name: bool(os.environ.get(name)) for name in
                                ['SYNAPSE_AUTH_TOKEN', 'SYNAPSE_ACCESS_TOKEN', 'SYNAPSE_SESSION_TOKEN']},
        'synapse_config_present': {str(p): p.is_file() for p in set(credential_files)},
        'hf_token_file_present': Path('/home/test/.cache/huggingface/token').is_file(),
        'scope': '검사한 환경 변수와 기본/지정 설정 경로만 해당. 사용자 계정의 원격 승인 상태는 미조회.'}
    save(out / 'credential_presence.json', credentials)

    # 새로 필요한 metadata만 조회. 과거 익명 mapping/file 403 요청을 반복하지 않는다.
    session = requests.Session()
    session.trust_env = False
    sources = [
        ('synapse_requirement', 'https://repo-prod.prod.sagebase.org/repo/v1/accessRequirement/9606684'),
        ('synapse_postchallenge_wiki', 'https://repo-prod.prod.sagebase.org/repo/v1/entity/syn64952532/wiki'),
        ('autorg_readme', f'https://raw.githubusercontent.com/ljy19970415/AutoRG-Brain/{AUTO_REV}/README.md'),
        ('synapse_access_api', 'https://rest-docs.synapse.org/rest/org/sagebionetworks/repo/model/AccessRequirement.html'),
        ('isles_zenodo_metadata', 'https://zenodo.org/api/records/7960856'),
    ]
    responses = {}
    for name, url in sources:
        if metadata_from:
            p = metadata_from / (name + '.json')
            record = read(p)
            assert record['url'] == url
            input_hashes[str(p)] = sha(p)
            save(out / (name + '.json'), record)
            responses[name] = record
            continue
        started = now()
        try:
            r = session.get(url, timeout=40)
            record = {'requested_at': started, 'url': url, 'final_url': r.url, 'status_code': r.status_code,
                      'body': r.text, 'body_sha256': hashlib.sha256(r.content).hexdigest()}
        except requests.RequestException as e:
            record = {'requested_at': started, 'url': url, 'status_code': None, 'error_type': type(e).__name__}
        save(out / (name + '.json'), record)
        responses[name] = record
    if metadata_from:
        p = metadata_from / 'radgenome_current_metadata.json'
        hf = read(p)
        input_hashes[str(p)] = sha(p)
    else:
        token_path = Path('/home/test/.cache/huggingface/token')
        api = HfApi(token=token_path.read_text().strip() if token_path.is_file() else False)
        try:
            info = api.dataset_info('JiayuLei/RadGenome-Brain_MRI', files_metadata=True)
            hf = {'requested_at': now(), 'revision': info.sha, 'matches_pinned': info.sha == RAD_REV,
                  'files': [{'path': f.rfilename, 'bytes': f.size} for f in info.siblings],
                  'status': 'metadata_received', 'auth': 'stored_HF_token' if token_path.is_file() else 'anonymous'}
        except Exception as e:
            hf = {'requested_at': now(), 'status': 'failed', 'error_type': type(e).__name__}
    save(out / 'radgenome_current_metadata.json', hf)

    previous = read(HERE / 'results/iter_083/preflight_a1/train_review8.json')
    ids = list(previous['rows'])
    assert len(ids) == 8 and len({p.rsplit('-', 1)[0] for p in ids}) == 8
    reports = read(RAD / 'BraTS_GLI/modal_wise_finding.json')
    splits = read(RAD / 'train_val_test_split.json')
    # train만 접근하며 공식 test/val 항목과 원문을 출력하지 않는다.
    train = splits['train']
    old_data = read(HERE / 'results/iter_134/data/data_manifest_v2.json')
    roots = [HERE / 'results/iter_070/data/brats', HERE / 'results/iter_134/data/brats']
    candidates = []
    for pid in ids:
        key = pid + '-t2f'
        assert key in train and reports[key] == previous['rows'][pid]['flair']
        local = {}
        for suffix in ['t2f', 'seg']:
            found = [p for root in roots for p in root.rglob(pid + '-' + suffix + '.nii.gz')]
            assert len(found) <= 1, '로컬 후보 충돌: ' + pid
            if found:
                p = found[0]
                h = sha(p)
                input_hashes[str(p)] = h
                img = nib.load(p)
                arr = np.asanyarray(img.dataobj)
                local[suffix] = {'path': str(p), 'sha256': h, 'bytes': p.stat().st_size,
                                 'shape': list(img.shape), 'axcodes': list(nib.aff2axcodes(img.affine)),
                                 'affine': img.affine.tolist(), 'stored_spacing_mm': [float(x) for x in img.header.get_zooms()],
                                 'finite': bool(np.isfinite(arr).all())}
                old = old_data['cases'].get(pid)
                if old:
                    assert old[suffix + '_sha256'] == h
                if suffix == 'seg':
                    local[suffix]['observed_numeric_labels'] = [int(x) for x in np.unique(arr)]
        pair_ok = bool(local.get('t2f') and local.get('seg'))
        if pair_ok:
            pair_ok = (local['t2f']['shape'] == local['seg']['shape'] and
                       bool(np.allclose(local['t2f']['affine'], local['seg']['affine'])) and
                       local['t2f']['finite'] and local['seg']['finite'])
        candidates.append({'scan_id': pid, 'patient_prefix': pid.rsplit('-', 1)[0],
                           'official_split': 'train', 'report_key': key, 'report': reports[key],
                           'report_matches_fixed_review': True, 'local_files': local,
                           'local_pair_geometry_valid': pair_ok,
                           'source_use_basis': 'unconfirmed', 'official_release_equivalence': 'unconfirmed',
                           'prior_exposure': 'iter_083 train text review; local 3 cases also iter_134/135 development',
                           'eligible_for_generation': False})
    save(out / 'candidate_linkage.json', {'candidate_order': ids, 'rows': candidates,
          'n_report_links': len(candidates), 'n_local_pairs': sum(c['local_pair_geometry_valid'] for c in candidates),
          'scope': '파일명·report key·로컬 기하 검사이며 공식 release 대응/이용 인증은 아니다.'})

    weights_manifest = read(HERE / 'results/iter_070/models/weights_manifest.json')
    weights = []
    for name in ['AutoRG_Brain_SEG.model', 'AutoRG_Brain_SEG.model.pkl',
                 'RG_v2/AutoRG_Brain_RGv2.model', 'RG_v2/AutoRG_Brain_RGv2.model.pkl']:
        p = HERE / 'results/iter_070/models/autorg' / name
        h = sha(p)
        input_hashes[str(p)] = h
        assert h == weights_manifest[name]
        weights.append({'path': str(p), 'sha256': h, 'bytes': p.stat().st_size, 'matches_manifest': True})
    source_checks = []
    for name in ['README.md', 'AutoRG_Brain/test.py', 'AutoRG_Brain/inference/inferenceSdk.py']:
        p = HERE / 'results/iter_070/external/src' / ('AutoRG-Brain-' + AUTO_REV) / name
        raw = HERE / 'results/iter_070/external/raw' / name
        input_hashes[str(p)] = sha(p)
        if raw.is_file():
            input_hashes[str(raw)] = sha(raw)
        source_checks.append({'path': str(p), 'sha256': sha(p), 'preserved_raw_exists': raw.is_file(),
                             'matches_preserved_raw': sha(p) == sha(raw) if raw.is_file() else None})
    env = HERE / 'results/environments/autorg70/bin/python'
    save(out / 'autorg_assets.json', {'source_revision': AUTO_REV, 'weights_revision': weights_manifest['AutoRG_Brain_rev'],
         'weights': weights, 'source_checks': source_checks, 'environment_python': str(env), 'python_exists': env.is_file(),
         'runtime_import_and_gpu_validation': 'not_run; no_environment_changed',
         'supported_input': 'T2FLAIR NIfTI volume; mask fields omitted for predicted-mask route',
         'practical_route': 'region_segtool; report field omitted', 'oracle_route': 'given_mask; GT anomaly mask',
         'training_exposure': 'RGv2 pretrained on RadGenome; current train cases cannot be independent generalization',
         'local_supervision': 'modal_wise_finding is sequence/anomaly-scope text, not slice-specific target',
         'slice_sft': 'not_supported_by_current_verified_labels', 'volume_sft': 'conditional_on_source_linkage_and_new_method_plan',
         'performance_comparison': 'not_run'})

    req_record = responses['synapse_requirement']
    req = json.loads(req_record['body']) if req_record['status_code'] == 200 else {}
    disk = shutil.disk_usage(HERE)
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.used,memory.free',
                          '--format=csv,noheader,nounits'], capture_output=True, text=True)
    save(out / 'resources.json', {'created_at': now(), 'python': sys.executable,
         'CUDA_VISIBLE_DEVICES': os.environ.get('CUDA_VISIBLE_DEVICES'), 'disk_free_bytes': disk.free,
         'nvidia_smi_exit': gpu.returncode, 'nvidia_smi': gpu.stdout,
         'gpu_execution': 'none_data_gate_closed', 'new_image_or_weight_download_bytes': 0,
         'new_environment_install': False})
    blockers = ['고정 후보 원천 MRI의 이용 승인 근거가 없고 공식 release 대응이 확인되지 않았다.']
    if not any(credentials['synapse_env_present'].values()) and not any(credentials['synapse_config_present'].values()):
        blockers.append('검사한 Synapse 인증 설정은 없다. HF 인증은 Synapse 승인을 입증하지 않는다.')
    if req:
        blockers.append('현재 Synapse DOWNLOAD 접근 요건 ' + str(req.get('id')) + ' v' + str(req.get('versionNumber')) +
                        ' (' + req.get('concreteType', '').rsplit('.', 1)[-1] + ')가 존재한다. 사용자별 승인 상태는 미확인이다.')
    gate = {'created_at': now(), 'approach_status': 'execution_failed', 'valid_experiment': False,
            'run_generation': False, 'run_training': False, 'data_gate': 'unresolved', 'blockers': blockers,
            'n_candidate_scans': len(ids), 'n_connected_report_keys': len(ids),
            'n_local_image_mask_pairs': sum(c['local_pair_geometry_valid'] for c in candidates),
            'n_verified_source_use_and_release_pairs': 0,
            'new_model_requests': 0, 'training_updates': 0, 'new_3d_outputs': 0,
            'prior_403_reused_as_historical_evidence': True, 'new_mapping_download_attempts': 0,
            'evaluation_prelock': 'not_created_no_generation', 'visual_audit': 'not_performed',
            'scope': '현재 BraTS_GLI 자료 경로에만 해당하며 MRI 가설의 음성 판정이 아니다.',
            'required_next_evidence': '사용자 본인의 Synapse 로그인·접근 승인 또는 이미 승인된 원천 영상과 release 대응 증거. 토큰을 보고서/대화로 전달하지 않는다.',
            'alternative': 'RadGenome ISLES22 + 공식 ISLES2022 Zenodo source. 이번 후보 대체/다운로드/모델 실행은 하지 않음. 환자·sequence·mask·report 대응은 후속 한정 검사 필요.',
            'elapsed_seconds': time.monotonic() - t0}
    save(out / 'gate.json', gate)
    unchanged = {p: sha(p) == h for p, h in {**input_hashes, **code_hashes}.items()}
    assert all(unchanged.values()), '기존 자산 변경'
    save(out / 'invariance.json', {'all_pass': True, 'checks': unchanged})
    outputs = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
    save(out / 'completion.json', {'created_at': now(), 'status': 'preflight_complete_experiment_not_run',
         'outputs': outputs, 'inputs': input_hashes, 'code': code_hashes})
    checks = verify(out)
    save(out / 'verification.json', checks)
    assert checks['all_pass']
    print(json.dumps({'status': gate['approach_status'], 'valid_experiment': False,
          'candidates': len(ids), 'local_pairs': gate['n_local_image_mask_pairs'],
          'verification_checks': len(checks['checks']), 'elapsed_seconds': gate['elapsed_seconds'],
          'output': str(out)}, ensure_ascii=False))
    return 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE / 'results/iter_140/preflight_a1')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--metadata-from', type=Path, help='동일 반복 부분 감사의 응답을 보존·재사용한다. 입력 hash 불일치는 거부한다.')
    args = parser.parse_args()
    if args.verify:
        result = verify(args.output)
        print(json.dumps({'all_pass': result['all_pass'], 'checks': len(result['checks'])}))
        sys.exit(0 if result['all_pass'] else 1)
    sys.exit(main(args.output, args.metadata_from))
