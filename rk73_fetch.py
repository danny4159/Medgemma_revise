"""iter_073/074: 3DReasonKnee 공개 annotation 파일의 고정 provenance 검증 (다운로드 없음).

- iter_073 source_manifest.json(고정 SHA256)에 기록된 revision/bytes/sha256과 대조한다. 현재 파일의 hash로 기대값을 만들지 않는다.
- generate_data/test* 와 통합 원 label(data/labels/*; test 환자 행 포함)은 읽기 대상에서 거부한다. 파일명에 test가 없다는 이유로 허용하지 않는다.
- mismatch·누락은 중단한다(자동 재다운로드 없음). hash는 byte 동일성의 근거이며 split 안전성의 증명이 아니다.
"""
import hashlib, json, os

REPO = 'rajpurkarlab/3DReasonKnee'
REV = '7a611f92fd3ad3954e8b62feef49ee12bfef725a'
ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DEFAULT = os.path.join(ROOT, 'results/iter_073/raw')
PINNED_MANIFEST = os.path.join(ROOT, 'results/iter_073/source_manifest.json')
PINNED_MANIFEST_SHA256 = '0f39716f8ac932a0dc1f540a75f3439ac8cfc749f1de36cd692ee3fbd90eb64f'  # iter_073 산출물(2026-10-05 기록 시점)의 hash
FORBIDDEN = ('generate_data/test', 'data/labels/')
# 이 경계 아래에서 읽기를 허용하는 파일(통합 label과 test 답변 제외)
ALLOWED = (
    'README.md',
    'data/question_files/questions.json', 'data/question_files/cot_question_mapping.json',
    'data/question_files/grade_dict.json', 'data/question_files/labels.json',
    'data/question_files/question_subregion_mapping.json',
    'data/split_files/all_studies.csv', 'data/split_files/train_split.csv',
    'data/split_files/val_split.csv', 'data/split_files/test_split.csv',  # ID 메타데이터만
    'data/generate_data/val.json', 'data/generate_data/train.json',
)


class ProvenanceError(RuntimeError):
    pass


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def is_forbidden(rel):
    return any(x in rel.replace('\\', '/') for x in FORBIDDEN)


def load_pinned_manifest(path=PINNED_MANIFEST, expect_sha=PINNED_MANIFEST_SHA256):
    if not os.path.exists(path):
        raise ProvenanceError('manifest 누락: %s' % path)
    if sha(path) != expect_sha:
        raise ProvenanceError('manifest hash 불일치: %s' % path)
    m = json.load(open(path))
    if m.get('revision') != REV or m.get('repo') != REPO:
        raise ProvenanceError('revision/repo 불일치: %s' % m.get('revision'))
    return m


def verify_allowed(raw_root=RAW_DEFAULT, names=ALLOWED, manifest_path=PINNED_MANIFEST, expect_sha=PINNED_MANIFEST_SHA256):
    """names의 각 파일이 허용 목록에 있고, 고정 manifest의 bytes/sha256과 일치할 때만 {name: sha256} 반환. 아니면 예외."""
    for n in names:
        if is_forbidden(n):
            raise ProvenanceError('접근 금지 파일(test 답변/통합 원 label): %s' % n)
        if n not in ALLOWED:
            raise ProvenanceError('허용 목록에 없는 파일: %s' % n)
    man = load_pinned_manifest(manifest_path, expect_sha)
    out = {}
    for n in names:
        ent = man['files'].get(n)
        if ent is None:
            raise ProvenanceError('manifest에 없는 파일: %s' % n)
        p = os.path.join(raw_root, n)
        if not os.path.exists(p) or os.path.islink(p):
            raise ProvenanceError('파일 누락 또는 symlink: %s' % n)
        if os.path.getsize(p) != ent['bytes']:
            raise ProvenanceError('크기 불일치: %s' % n)
        h = sha(p)
        if h != ent['sha256']:
            raise ProvenanceError('sha256 불일치: %s' % n)
        out[n] = h
    return out


def main(argv=None):
    import argparse, time
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default=RAW_DEFAULT)
    ap.add_argument('--out', required=True, help='검증 결과 JSON 경로 (results/iter_074/ 아래)')
    a = ap.parse_args(argv)
    if '/results/iter_074/' not in os.path.abspath(a.out) or os.path.exists(a.out):
        raise ProvenanceError('출력은 새 iter_074 경로여야 한다: %s' % a.out)
    t0 = time.time()
    res = verify_allowed(a.raw)
    json.dump({'revision': REV, 'manifest_sha256': PINNED_MANIFEST_SHA256, 'verified_sha256': res,
               'not_read': ['data/labels/* (통합 원 label, test 환자 행 포함)', 'generate_data/test*'],
               'wall_s': round(time.time() - t0, 2)}, open(a.out, 'w'), indent=1)
    print('verified', len(res))


if __name__ == '__main__':
    main()
