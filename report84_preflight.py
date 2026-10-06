"""iter_084의 출처·보호 split·모델 접근 확인. 추론 gate나 성능 평가기가 아니다.

재실행은 새로운 --out 경로를 요구한다. 인증 값은 저장하지 않는다.
"""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
UP = ROOT.parent
CURE_REV = "9365333856c0534af0cb05cb4291ce48dd95bb1d"
BASE_REV = "290cda5eeccbee130f987c4ad74a59ae6f196408"
ADAPTER_REV = "4bb5dc5a5025a854d1f25e475769949915b08b44"


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def rows(p):
    return [json.loads(s) for s in p.read_text().splitlines() if s]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    ap.add_argument('--iteration', type=int, choices=[84,85], default=84)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.relative_to(ROOT / 'results' / f'iter_{args.iteration:03d}')
    out.mkdir(parents=True, exist_ok=False)
    # HF 보조 Xet/PyTorch/pip 캐시도 이번 결과 경로에 한정한다.
    for key, name in {'HF_HOME': 'hf', 'HF_HUB_CACHE': 'hf/hub', 'HF_XET_CACHE': 'hf/xet', 'XDG_CACHE_HOME': 'xdg', 'TORCH_HOME': 'torch', 'PIP_CACHE_DIR': 'pip', 'TMPDIR': 'tmp'}.items():
        cache = out / 'runtime_cache' / name
        cache.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(cache)
    start = time.time()
    save(out / 'execution.json', {'argv': sys.argv, 'python': sys.executable,
         'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
         'start_unix': start, 'source_sha256': sha(__file__),
         'plan_sha256': sha(UP / f'agent/runs/iter_{args.iteration:03d}/plan.json')})
    blockers = []
    try:
        import requests
        from huggingface_hub import get_token, hf_hub_download
        token = get_token()
        session = requests.Session()
        assets = []
        sources = ['README.md', 'requirements.txt', 'vlm_research_kit/utils/model_utils.py',
                   'scripts/eval_report_generation.py',
                   'vlm_research_kit/data/datasets/chest_imagenome_dataset.py',
                   'notebooks/inference/Load and run CURE from Hugging Face.ipynb']
        for i, name in enumerate(sources):
            url = f'https://raw.githubusercontent.com/PabloMessina/CURE/{CURE_REV}/{requests.utils.quote(name)}'
            r = session.get(url, timeout=60)
            r.raise_for_status()
            dest = out / 'official' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f:
                f.write(r.content)
            assets.append({'url': url, 'final_url': r.url, 'status': r.status_code,
                           'path': str(dest.relative_to(ROOT)), 'sha256': sha(dest)})
        access = []
        for repo, rev in [('google/medgemma-4b-it', BASE_REV),
                          ('pamessina/medgemma-4b-it-cure', ADAPTER_REV)]:
            name = 'adapter_config.json' if 'cure' in repo else 'config.json'
            url = f'https://huggingface.co/{repo}/resolve/{rev}/{name}'
            r = session.get(url, headers={'Authorization': 'Bearer ' + token} if token else {}, timeout=60)
            row = {'repo': repo, 'revision': rev, 'filename': name, 'url': url,
                   'status': r.status_code, 'token_available': bool(token)}
            if r.status_code == 200:
                config = r.json()
                dest = out / 'official' / repo / name
                save(dest, config)
                row.update(config_sha256=sha(dest), config_path=str(dest.relative_to(ROOT)))
                if 'cure' in repo:
                    assert config['base_model_name_or_path'] == 'google/medgemma-4b-it'
                    row['base_model_name_or_path'] = config['base_model_name_or_path']
                    row['modules_to_save'] = config.get('modules_to_save')
            else:
                row['response'] = r.text[:1500]
                blockers.append(f'{repo}/{name}: HTTP {r.status_code}')
            access.append(row)
        # 공식 SDK 경로에서도 동일 접근 상태를 확인한다. 새 캐시만 사용한다.
        sdk = {}
        try:
            path = hf_hub_download('google/medgemma-4b-it', 'config.json', revision=BASE_REV,
                                   cache_dir=str(out / 'hf_cache'), token=token or False)
            sdk = {'ok': True, 'sha256': sha(path)}
        except Exception as e:
            sdk = {'ok': False, 'exception_type': type(e).__name__,
                   'status': getattr(getattr(e, 'response', None), 'status_code', None)}
            blockers.append('공식 HF SDK base config 접근 실패: ' + type(e).__name__)
        save(out / 'official_sources.json', assets)
        save(out / 'model_access.json', {'http': access, 'sdk': sdk,
             'credentials_recorded': False, 'base_cache_exists':
             (UP / 'hf_cache/hub/models--google--medgemma-4b-it').exists()})

        manifest = json.loads((UP / 'agent/runs/iter_084/reuse_manifest.json').read_text())
        checked = []
        for path, spec in manifest['files'].items():
            actual = subprocess.check_output(['git', 'hash-object', '--', path], cwd=ROOT, text=True).strip()
            assert actual == spec['blob'], path
            importlib.import_module(path[:-3].replace('/', '.') if not path.endswith('__init__.py')
                                    else path.rsplit('/', 1)[0].replace('/', '.'))
            checked.append({'path': path, 'blob': actual, 'source_commit': spec['source_commit'],
                            'sha256': sha(ROOT / path), 'import_ok': True})
        save(out / 'reuse_checks.json', {'files': checked,
             'scope': 'blob·import만 확인. GPU·runner·평가 required_checks는 미실행',
             'all_required_checks_complete': False})

        from pg39_data import load_inputs
        # report 내용 의미 검토 전에 master와 보호 manifest만으로 제외 ID를 확정한다.
        import pandas as pd
        import zipfile
        raw = ROOT / 'results/datasets/padchest_gr/raw'
        with zipfile.ZipFile(raw / 'master_table.csv.zip') as z:
            master = pd.read_csv(z.open('master_table.csv'), dtype=str)
        p39 = ROOT / 'results/iter_039/data/manifest_private.jsonl'
        p40 = ROOT / 'results/iter_040/data/manifest_eval_private.jsonl'
        old39, old40 = rows(p39), rows(p40)
        protected = [x for x in old39 if x['subset'] == 'F'] + [x for x in old40 if x['eval_set'] == 'H192']
        assert len(protected) == 312
        banned_patients = {x['PatientID'] for x in protected}
        banned_studies = {x['StudyID'] for x in protected}
        banned_images = {x['ImageID'] for x in protected}
        uniq = master.drop_duplicates('ImageID')
        candidates = uniq[(uniq.split == 'validation') & ~uniq.PatientID.isin(banned_patients)
                          & ~uniq.StudyID.isin(banned_studies) & ~uniq.ImageID.isin(banned_images)]
        save(out / 'protected_exclusion.json', {
            'protected_counts': {'H192': 192, 'F120': 120},
            'candidate_images': len(candidates), 'candidate_patients': candidates.PatientID.nunique(),
            'test_candidates': int((candidates.split == 'test').sum()),
            'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in (p39, p40)},
            'scope': 'metadata 후보; frontal·현재 사실·CURE 학습 노출·pixel 중복 확인 전. E 표본 확정 아님'})
        reports, _, links = load_inputs(str(raw))
        save(out / 'metadata_checks.json', {'pinned_hash_and_links_pass': True,
             'report_count': len(reports), 'input_sha256': links['inputs_sha256'],
             'report_semantic_inspection': False, 'test_report_content_used': False})

        manual = ROOT / 'results/manual_rsna_report_transfer_20261006'
        protocol = json.loads((manual / 'protocol.json').read_text())
        manual_hashes = {p.name: sha(p) for p in [manual / n for n in
                         ['RESULTS.txt', 'protocol.json', 'summary.json', 'paired_assessments.json', 'base.jsonl', 'sft.jsonl']]}
        outputs = {}
        for model in ['base', 'sft']:
            rr = rows(manual / f'{model}.jsonl')
            completion = json.loads((manual / f'{model}_completed.json').read_text())
            assert len(rr) == len({r['id'] for r in rr}) == 60
            assert completion['output_sha256'] == sha(manual / f'{model}.jsonl')
            assert all(r['protocol_digest'] == sha(manual / 'protocol.json') for r in rr)
            outputs[model] = {'n': len(rr), 'non_eos': sum(not r['ended_eos'] for r in rr)}
        import torch
        from rsna_diag.lora import state_digest
        adapter = ROOT / 'results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt'
        blob = torch.load(adapter, map_location='cpu', weights_only=True)
        digest = state_digest(blob['state'])
        assert digest == protocol['adapter_expected_digest'] == 'e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11'
        save(out / 'manual_and_adapter_checks.json', {'manual_sha256': manual_hashes, 'outputs': outputs,
             'adapter_file_sha256': sha(adapter), 'adapter_state_digest': digest,
             'adapter_tensor_count': len(blob['state']),
             'strict_model_key_shape_check': '미실행', 'semantic_reannotation': '미실행',
             'manual_validated_promotion': False})
        versions = {}
        for package in ['torch', 'transformers', 'numpy', 'pandas', 'Pillow', 'peft', 'bitsandbytes', 'opencv-python-headless']:
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        gpu = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        (out / 'nvidia-smi.txt').write_text(gpu.stdout + gpu.stderr)
        save(out / 'environment.json', {'python': sys.executable, 'versions': versions,
             'torch_cuda_available': torch.cuda.is_available(), 'torch_cuda_count': torch.cuda.device_count(),
             'disk_free_bytes': shutil.disk_usage(ROOT).free, 'nvidia_smi_rc': gpu.returncode,
             'installation_performed': False,
             'installation_deferred_reason': ('접근 실패; 오류 기록 참조' if blockers else '접근 확인; 설치 및 실제 로딩은 별도 단계')})
    except Exception as e:
        import traceback
        (out / 'error.txt').write_text(traceback.format_exc())
        blockers.append(type(e).__name__ + ': ' + str(e))
    files = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    save(out / 'completion.json', {'stage': 'preflight_only', 'blockers': blockers,
         'asset_access_ready': not blockers, 'experiment_complete': False,
         'gpu_generation_count': 0, 'wall_s': time.time() - start, 'files_sha256': files,
         'next': ('접근 오류 해결 필요; 성능 판정 없음.' if blockers else '접근 확인; 공식 로딩·D8와 전체 비교는 미완료.')})
    print(json.dumps({'stage': 'preflight_only', 'blockers': blockers, 'out': str(out)}, ensure_ascii=False))
    return 2 if blockers else 0


if __name__ == '__main__':
    raise SystemExit(main())
