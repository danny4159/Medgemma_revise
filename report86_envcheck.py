"""실제 자식 Python 두 개(기본 medgemma, CURE 격리 환경)의 캐시 경로·버전·GPU 가시성을 격리 환경 변수로 확인한다.
설치·변경은 하지 않는다. 인증 값은 읽지 않는다(토큰 경로 상속 여부만 bool). 결과: results/iter_086/environment_state.json
"""
import json
import subprocess
import sys

from report86_common import R86, ROOT, CURE_PY, isolated_env, save, sha

CODE = r"""
import json, os, sys
from pathlib import Path
import huggingface_hub.constants as c
import torch, transformers
root = Path(os.environ['HF_HOME']).resolve().parents[1] if False else None
cache_root = Path(os.environ['XDG_CACHE_HOME']).resolve().parent
paths = {'HF_HOME': c.HF_HOME, 'HF_HUB_CACHE': c.HF_HUB_CACHE, 'HF_XET_CACHE': c.HF_XET_CACHE,
         'TORCH_HOME': os.environ['TORCH_HOME'], 'TMPDIR': os.environ['TMPDIR'], 'TRITON_CACHE_DIR': os.environ['TRITON_CACHE_DIR'],
         'XDG_CACHE_HOME': os.environ['XDG_CACHE_HOME'], 'CUDA_CACHE_PATH': os.environ['CUDA_CACHE_PATH']}
res = {'python': sys.executable, 'torch': torch.__version__, 'transformers': transformers.__version__,
       'cuda_available': torch.cuda.is_available(), 'visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
       'n_cuda_devices': torch.cuda.device_count(), 'paths': paths, 'cache_root': str(cache_root),
       'all_under_cache_root': all(Path(v).resolve().is_relative_to(cache_root) for v in paths.values()),
       'token_path_inherited': bool(os.environ.get('HF_TOKEN_PATH')), 'hf_hub_offline': os.environ.get('HF_HUB_OFFLINE')}
for m in ['peft', 'bitsandbytes', 'accelerate', 'albumentations', 'timm']:
    try:
        res[m] = __import__(m).__version__
    except Exception as e:
        res[m] = 'absent:' + type(e).__name__
print(json.dumps(res))
"""


def main():
    env = isolated_env()
    out = {}
    for name, py in (('medgemma_default', sys.executable), ('cure085', str(CURE_PY))):
        p = subprocess.run([py, '-c', CODE], cwd=ROOT, env=env, capture_output=True, text=True)
        out[name] = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {'error': p.stderr[-500:]}
    old = json.loads((ROOT / 'results/iter_085/environment_final.json').read_text())
    out['iter_085_environment_final_json_torch_record'] = json.dumps(old)[:300]
    out['reconciliation'] = ('environment_final.json의 오래된 torch 2.5.1 기록과 달리 실제 cure085 Python은 위 값을 보고한다. '
                             '최종 D8 CURE/M1G 출력 protocol에는 2.7.1+cu126이 기록돼 있다. 재설치는 하지 않았다.')
    out['d8_protocol_torch'] = {s: json.loads((ROOT / f'results/iter_085/D8/{d}/protocol.json').read_text()).get('torch')
                                for s, d in {'M15': 'M15', 'B0': 'B0', 'M1': 'M1', 'M1G_official': 'M1G_official', 'C': 'C', 'M1G_failed': 'M1G'}.items()}
    save(R86 / 'environment_state.json', out)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
