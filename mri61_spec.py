"""iter_061 prompt·permutation·strict parser·요청 구성 (순수 함수, GT 접근 없음)."""
import hashlib, json, re

SEED = 61
LETTERS = 'ABCDE'
INSTR = ("Using only the information provided in this conversation, select the single best answer. "
         "You may reason briefly. Your final line must be exactly 'ANSWER: X' where X is one of A, B, C, D, E.")
DATA = 'results/iter_061/data'


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def perms(qa_id):
    f = sorted(range(5), key=lambda i: sha(f'{SEED}|perm|{qa_id}|{i}'))
    return {'F': f, 'R': list(reversed(f))}  # perm[j] = 원본 선택지 index shown at letter j


def make_prompt(question, options, perm):
    lines = [f'{LETTERS[j]}. {options[perm[j]]}' for j in range(5)]
    return f'{question.strip()}\n\nOptions:\n' + '\n'.join(lines) + '\n\n' + INSTR


ANS_RE = re.compile(r'^ANSWER:\s*([A-E])\s*$')


def parse_answer(text):
    """마지막 비공백 줄이 정확히 'ANSWER: X' 일 때만 유효. 반환 letter 또는 None."""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None
    m = ANS_RE.match(lines[-1].strip())
    return m.group(1) if m else None


def letter_to_orig(letter, perm):
    return perm['ABCDE'.index(letter)] if letter else None


def gt_orig_index(x):
    return 'ABCDE'.index(x['answer'])


def build_rows(clusters, qa_by_id, img_dir):
    rows = []
    for c in clusters:
        x = qa_by_id[c['qa_id']]
        ps = c['images']
        paths = [f'{img_dir}/{p}' for p in ps]
        conds = [('T', []), ('J', paths)] + ([(f'S{i + 1}', [paths[i]]) for i in range(len(paths))] if len(paths) > 1 else [])
        for order, perm in perms(x['id']).items():
            prompt = make_prompt(x['question'], x['options'], perm)
            for cond, imgs in conds:
                ish = sha(json.dumps([p for p in imgs]))
                rid = sha(f"{c['cluster_id']}|{x['id']}|{cond}|{order}|{ish}|{sha(prompt)}|{SEED}")[:24]
                rows.append({'rid': rid, 'cluster_id': c['cluster_id'], 'qa_id': x['id'], 'source': c['source'], 'K': len(ps),
                             'cond': cond, 'order': order, 'perm': perm, 'images': imgs, 'prompt': prompt,
                             'images_sha': ish})
    return rows
