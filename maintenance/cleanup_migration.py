"""명시적 파일 목록만 정리한다. plan 후 양쪽에서 check, 이후 apply한다."""
import argparse
import collections
import json
from pathlib import Path

TEST_ROOTS = [f'research/results/iter_{i}/{d}' for i,d in [
    ('035','sanity'), ('040','tests'), ('046','tests'), ('048','tests'), ('090','tests')]]
CACHES = ['research/results/environments/qwen25vl_cache',
          'research/results/environments/qwen3vl_cache', 'research/results/iter_085/models']

def plan(root):
    files = {}
    sources = []
    def add(p, reason):
        if p.is_file() and not p.is_symlink():
            files[str(p.relative_to(root))] = {'bytes':p.stat().st_size, 'reason':reason}
    for rel in TEST_ROOTS:
        for p in (root/rel).rglob('*'):
            if p.suffix in {'.pt','.pth','.safetensors'}:
                add(p, '재개·오류 주입 테스트 가중치: 해당 iter 코드/plan으로 재생성. 실제 학습 결과는 보존')
    for rel in CACHES:
        for repo in (root/rel).glob('models--*'):
            revisions = [p.name for p in (repo/'snapshots').glob('*') if p.is_dir()]
            if not revisions:
                raise RuntimeError(f'고정 revision 없음: {repo}')
            sources.append({'repo':repo.name[len('models--'):].replace('--','/'),
                            'revisions':revisions,'cache_dir':rel})
            for p in (repo/'blobs').glob('*'):
                if p.stat().st_size > 100_000_000:
                    add(p,'공개 HF 모델: sources의 repo/revision으로 snapshot_download(cache_dir=...)')
    rel='research/results/environments/medrega112_weights'
    sources.append({'repo':'Luxuriant16/medrega','revision':'ec1d98335322b2200f93b35562b681e05fc3a194', 'local_dir':rel})
    for p in (root/rel).glob('*.safetensors'):
        add(p,'공개 MedRegA: sources의 고정 revision으로 snapshot_download(local_dir=...)')
    for p in (root/'research/results/iter_085/pip_cache').rglob('*'):
        add(p,'pip 다운로드 캐시: 패키지 재설치로 복원')
    return {'files':files,'sources':sources,'preserved':['hf_cache 전체','직접 학습한 정식 train/pilot 가중치','iter_143 전체','데이터·코드·평가 결과·실행 기록'], 'bytes':sum(v['bytes'] for v in files.values())}

def check(root, data):
    for rel,meta in data['files'].items():
        p=root/rel
        if Path(rel).is_absolute() or '..' in Path(rel).parts or not p.resolve().is_relative_to(root):
            raise RuntimeError(f'범위 이탈: {rel}')
        if p.is_symlink() or not p.is_file() or p.stat().st_size != meta['bytes']:
            raise RuntimeError(f'파일 상태 불일치: {rel}')

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=['plan','check','apply','verify'])
    ap.add_argument('--root',required=True)
    ap.add_argument('--manifest',required=True)
    a=ap.parse_args(); root=Path(a.root).resolve(); manifest=Path(a.manifest)
    if root.name!='08_medgemma' or not (root/'orchestrator.py').is_file():
        raise RuntimeError('프로젝트 루트 검증 실패')
    if a.mode=='plan':
        data=plan(root); manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    else:
        data=json.loads(manifest.read_text())
        if a.mode=='verify':
            assert all(not (root/p).exists() for p in data['files'])
        else:
            check(root,data)
            if a.mode=='apply':
                for rel in data['files']: (root/rel).unlink()
    print(json.dumps({'mode':a.mode,'files':len(data['files']),'GiB':round(data['bytes']/2**30,2)}))
