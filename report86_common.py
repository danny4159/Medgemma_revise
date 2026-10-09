"""iter_086 공통: 경로·hash·원자적 저장·고정 prompt/과학적 protocol·격리 캐시 환경.

원본(iter_084/085, 수동 결과)은 읽기만 한다. 새 산출물은 results/iter_086 아래에만 쓴다.
"""
import ast
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UP = ROOT.parent
R85 = ROOT / 'results/iter_085'
R86 = ROOT / 'results/iter_086'
BASE_REV = "290cda5eeccbee130f987c4ad74a59ae6f196408"
ADAPTER_REV = "4bb5dc5a5025a854d1f25e475769949915b08b44"
MODEL15_REV = "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"
B0_DIGEST = 'e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11'
SEED = 17
CAPS = [1024, 2048, 4096]
SYSTEMS = ['M15', 'B0', 'M1', 'M1G', 'C']
CURE_PY = ROOT / 'results/environments/cure085/bin/python'
SYSTEMATIC_SUFFIX = (' Systematically review the lungs, pleura, cardiomediastinal silhouette, bones, and visible devices. '
                     'Mention an abnormality only when supported by this image, and distinguish definite from uncertain findings.')
CONDITION_OF = {  # 8 판독 조건 -> (system, prompt name)
    'M15-R': ('M15', 'R'), 'M15-S': ('M15', 'S'), 'B0-R': ('B0', 'R'), 'B0-S': ('B0', 'S'),
    'M1-R': ('M1', 'R'), 'M1-G': ('M1G', 'G'), 'C-G': ('C', 'G'),
}


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save(p, value):
    """새 파일만 원자적으로 만든다. 이미 있으면 덮어쓰지 않고 FileExistsError."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f'.{os.getpid()}.tmp')
    with tmp.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, p)  # 이미 있으면 FileExistsError
    finally:
        os.unlink(tmp)


def read_jsonl_complete(path):
    """개행으로 끝난 완결 행만 읽는다(다른 worker가 쓰는 부분 행은 무시). 중간 행이 깨지면 예외."""
    out = []
    p = Path(path)
    if p.exists():
        data = p.read_bytes()
        for ln in data.split(b'\n')[:-1]:
            if ln.strip():
                out.append(json.loads(ln))
    return out


def record_digest(rec):
    return hashlib.sha256(json.dumps({k: v for k, v in rec.items() if k != 'record_digest'}, sort_keys=True).encode()).hexdigest()


def cure_locations():
    src = ROOT / 'results/iter_084/preflight_01/official/vlm_research_kit/data/datasets/chest_imagenome_dataset.py'
    locs = next(ast.literal_eval(n.value) for n in ast.parse(src.read_text()).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'SUPPORTED_LOCATE_AND_DESCRIBE_LOCATIONS' for t in n.targets))
    assert len(locs) == 29
    return sorted(locs)


def manual_prompt():
    return json.loads((ROOT / 'results/manual_rsna_report_transfer_20261006/protocol.json').read_text())['prompt']


def prompts_for(system):
    mp = manual_prompt()
    if system in ('M15', 'B0'):
        return [('R', mp), ('S', mp + SYSTEMATIC_SUFFIX)]
    if system == 'M1':
        return [('R', 'Describe this X-ray')]
    if system == 'M1G':
        return [('G', 'Generate a grounded report.')]
    if system == 'C':
        return [('G', 'Generate a grounded report.')] + [(loc, f'Locate and describe the {loc}.') for loc in cure_locations()]
    raise ValueError(system)


def base_path(system):
    if system in ('M15', 'B0'):
        return str(UP / 'hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots' / MODEL15_REV)
    return str(R85 / 'models/models--google--medgemma-4b-it/snapshots' / BASE_REV)


def adapter_path_C():
    return R85 / 'models/models--pamessina--medgemma-4b-it-cure/snapshots' / ADAPTER_REV


STAGES = {
    'D8': {'inputs': R85 / 'D8/inputs.json', 'raw': R85 / 'D8/raw_manifest.json'},
    'E96': {'inputs': R86 / 'E/inputs_E96.json', 'raw': R86 / 'E/raw_manifest_E96.json'},
    'E192x': {'inputs': R86 / 'E/inputs_E192x.json', 'raw': R86 / 'E/raw_manifest_E192x.json'},
}


def scientific_protocol(system, stage, adapter_digest=None):
    """모델 로딩 없이 계산 가능한 과학적 설정. GPU·python·source는 execution 기록으로 분리한다."""
    st = STAGES[stage]
    if adapter_digest is None:
        adapter_digest = {'B0': B0_DIGEST, 'C': None}.get(system)
        if system == 'C':
            adapter_digest = sha(adapter_path_C() / 'adapter_model.safetensors')
    return {'system': system, 'base': base_path(system), 'adapter_digest': adapter_digest, 'seed': SEED, 'caps': CAPS,
            'prompts': [list(x) for x in prompts_for(system)], 'input_sha256': sha(st['inputs']), 'raw_sha256': sha(st['raw'])}


def expected_ids(rows, system):
    return {r['ImageID'] + '|' + system + '|' + n for r in rows for n, _ in prompts_for(system)}


def isolated_env(base_env=None):
    env = dict(base_env or os.environ)
    cache = R86 / 'runtime_cache'
    for key, name in {'HF_HOME': 'hf', 'HF_HUB_CACHE': 'hf/hub', 'HF_XET_CACHE': 'hf/xet', 'XDG_CACHE_HOME': 'xdg',
                      'TORCH_HOME': 'torch', 'TORCHINDUCTOR_CACHE_DIR': 'inductor', 'TRITON_CACHE_DIR': 'triton',
                      'CUDA_CACHE_PATH': 'cuda', 'MPLCONFIGDIR': 'matplotlib', 'PIP_CACHE_DIR': 'pip', 'TMPDIR': 'tmp'}.items():
        p = cache / name
        p.mkdir(parents=True, exist_ok=True)
        env[key] = str(p)
    env['HF_HUB_OFFLINE'] = '1'
    env['TOKENIZERS_PARALLELISM'] = 'false'
    env['NO_ALBUMENTATIONS_UPDATE'] = '1'
    return env
