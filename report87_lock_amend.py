"""규약 amendment hash 기록. python report87_lock_amend.py <out_name.json> <file relative to research/> ...
기존 protocol_lock.json은 변경하지 않고 새 파일에 이후 변경 이력을 남긴다."""
import sys

from report86_common import ROOT, save, sha

if __name__ == '__main__':
    out, files = sys.argv[1], sys.argv[2:]
    save(ROOT / 'results/iter_087' / out, {'files': {f: sha(ROOT / f) for f in files}})
    print('saved', out, len(files))
