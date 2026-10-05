"""iter_078 참고 사례 조건(Q/L/I/D)의 prompt·chat message 구성.

Q: 기존 PROMPT_R + 대상 세 crop (iter_077 R 입력과 동일).
L: 참고 grade 목록 텍스트 + 대상 세 crop (참고 영상 없음).
I/D: 참고 사례 3개(세 crop + grade) + 대상 세 crop. I와 D는 텍스트가 동일하고 참고 영상(및 그 grade 순서는 유지)만 다르다.
참고 환자 ID·ordinal·cosine은 prompt에 넣지 않는다. 대상은 항상 마지막 세 영상이다.
"""
import hashlib

import sp75_vlm as V

HEADER = ('The following may show reference cases from OTHER patients first, then the target case. Each case consists of three adjacent '
          'sagittal T2-weighted MRI crops of one lumbar intervertebral disc, shown in left-to-right order. A reference case is labeled with its '
          'Pfirrmann grade. Grade only the TARGET disc, not the reference discs.')
QUESTION = ('What is the Pfirrmann grade (1 = bright homogeneous disc with clear nucleus/annulus distinction, '
            '5 = dark collapsed disc without distinction) of the target intervertebral disc? Answer with a single digit from 1 to 5.')
MAX_NEW = V.MAX_NEW
MAX_NEW_TOKENS = MAX_NEW
ADVICE = ('An automated image classifier estimated Pfirrmann grade {c} for this target disc. '
          'This estimate may be correct or incorrect. Use the MRI to determine the final grade.')


def audit_prompt(cond, grade):
    if cond not in ('A', 'T', 'X') or grade not in range(1, 6):
        raise ValueError('invalid audit condition/automated grade')
    tail = V.PROMPT_R
    if cond == 'T':
        tail = 'No MRI images are available in this condition. What is' + V.PROMPT_R.split('What is', 1)[1]
    return ADVICE.format(c=grade) + '\n\n' + tail


def ref_line(j, g, shown):
    return f'Reference case {j} (Pfirrmann grade {g}' + ('):' if shown else '; images not shown):')


def prompt_digest():
    return hashlib.sha256('|'.join([HEADER, QUESTION, V.PROMPT_R, ref_line(1, 0, True), ref_line(1, 0, False), 'Target case:']).encode()).hexdigest()


def blocks(cond, ref_imgs, ref_grades, tgt_imgs):
    """chat content block 목록과 영상 역할 목록 [(role, j)] 반환. ref_imgs: [[3 PIL] x3] 또는 None."""
    if cond in ('A', 'T', 'X'):
        ims = [] if cond == 'T' else tgt_imgs
        return ([{'type': 'image', 'image': im} for im in ims] +
                [{'type': 'text', 'text': audit_prompt(cond, ref_grades)}]), [('target', k) for k in range(len(ims))]
    if cond == 'Q':
        return [{'type': 'image', 'image': im} for im in tgt_imgs] + [{'type': 'text', 'text': V.PROMPT_R}], [('target', k) for k in range(3)]
    c = [{'type': 'text', 'text': HEADER + '\n\n'}]
    roles = []
    for j in range(3):
        c.append({'type': 'text', 'text': ref_line(j + 1, ref_grades[j], cond != 'L') + '\n'})
        if cond != 'L':
            for k, im in enumerate(ref_imgs[j]):
                c.append({'type': 'image', 'image': im})
                roles.append((f'ref{j + 1}', k))
    c.append({'type': 'text', 'text': 'Target case:\n'})
    for k, im in enumerate(tgt_imgs):
        c.append({'type': 'image', 'image': im})
        roles.append(('target', k))
    c.append({'type': 'text', 'text': '\n' + QUESTION})
    return c, roles


def build_inputs(proc, cond, ref_imgs, ref_grades, tgt_imgs):
    content, roles = blocks(cond, ref_imgs, ref_grades, tgt_imgs)
    inp = proc.apply_chat_template([{'role': 'user', 'content': content}], add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')
    n_img = sum(1 for b in content if b['type'] == 'image')
    actual = int(inp['pixel_values'].shape[0]) if 'pixel_values' in inp else 0
    if actual != n_img:
        raise RuntimeError(f"pixel_values images {inp['pixel_values'].shape[0]} != {n_img}")
    return inp, roles


def request_fields(req, cond):
    """request에서 영상 관련 provenance를 평탄화. cond별 사용 영상만."""
    q = req['query_images']
    out = {'query_pixel': [e['pixel_sha256_padded'] for e in q]}
    if cond in ('I', 'D'):
        out['ref_ids'] = [r['ref_id'] for r in req[cond]]
        out['ref_pixel'] = [[e['pixel_sha256_padded'] for e in r['images']] for r in req[cond]]
        out['ref_grades'] = [r['grade'] for r in req[cond]]
    elif cond == 'L':
        out['ref_ids'] = [r['ref_id'] for r in req['I']]
        out['ref_pixel'] = None
        out['ref_grades'] = [r['grade'] for r in req['I']]
    return out
