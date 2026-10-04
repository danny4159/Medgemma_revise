"""iter_073: 3DReasonKnee 공개 annotation 파일 고정 revision 다운로드 + manifest. test 답변(generate_data/test*.json)은 받지 않는다."""
import hashlib, json, os, time
from huggingface_hub import HfApi, hf_hub_download

REPO = 'rajpurkarlab/3DReasonKnee'
REV = '7a611f92fd3ad3954e8b62feef49ee12bfef725a'
OUT = 'results/iter_073/raw'
FILES = [
    'README.md',
    'data/question_files/questions.json', 'data/question_files/cot_question_mapping.json',
    'data/question_files/grade_dict.json', 'data/question_files/labels.json',
    'data/question_files/question_subregion_mapping.json',
    'data/split_files/all_studies.csv', 'data/split_files/train_split.csv',
    'data/split_files/val_split.csv', 'data/split_files/test_split.csv',
    'data/labels/manual_annotated_kMRI_18M.csv',
    'data/labels/taxonomymatch_kMRI_FNIH_SQ_MOAKS_BICL00.csv',
    'data/labels/taxonomymatch_kMRI_FNIH_SQ_MOAKS_BICL01.csv',
    'data/labels/taxonomymatch_kMRI_FNIH_SQ_MOAKS_BICL03.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL01.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL03.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL06.csv',
    'data/generate_data/val.json', 'data/generate_data/train.json',
]
FORBIDDEN = ('generate_data/test',)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def main():
    assert not any(any(x in f for x in FORBIDDEN) for f in FILES)
    api = HfApi()
    sizes = {}
    for p in sorted({os.path.dirname(f) for f in FILES if os.path.dirname(f)}):
        for t in api.list_repo_tree(REPO, path_in_repo=p, repo_type='dataset', revision=REV):
            if hasattr(t, 'size'):
                sizes[t.path] = t.size
    sizes['README.md'] = 5727
    man = {'repo': REPO, 'revision': REV, 'files': {}}
    t0 = time.time()
    for f in FILES:
        dst = os.path.join(OUT, f)
        if not (os.path.exists(dst) and os.path.getsize(dst) == sizes[f]):
            hf_hub_download(REPO, f, repo_type='dataset', revision=REV, local_dir=OUT)
        assert os.path.getsize(dst) == sizes[f], f
        man['files'][f] = {'bytes': sizes[f], 'sha256': sha(dst),
                           'url': 'https://huggingface.co/datasets/%s/resolve/%s/%s' % (REPO, REV, f)}
        print(f, sizes[f], flush=True)
    man['wall_s'] = round(time.time() - t0, 1)
    man['total_bytes'] = sum(v['bytes'] for v in man['files'].values())
    man['not_downloaded'] = ['data/generate_data/test.json', 'data/generate_data/test_balanced.json',
                             'masks archives', 'OAI images']
    json.dump(man, open('results/iter_073/source_manifest.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
