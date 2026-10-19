"""삭제한 공개 모델을 고정 revision으로 복원. HF_TOKEN은 환경변수로 제공."""
import argparse
import json
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
ap.add_argument('--repo',required=True,help='cleanup_20261019.json sources의 repo 중 하나')
a=ap.parse_args()
root=Path(a.root)
data=json.loads((Path(__file__).parent/'cleanup_20261019.json').read_text())
matches=[s for s in data['sources'] if s['repo']==a.repo]
if not matches:
    raise SystemExit('기록에 없는 모델입니다.')
from huggingface_hub import snapshot_download
for source in matches:
    if 'local_dir' in source:
        snapshot_download(source['repo'],revision=source['revision'],local_dir=root/source['local_dir'])
    else:
        for rev in source['revisions']:
            snapshot_download(source['repo'],revision=rev,cache_dir=root/source['cache_dir'])
