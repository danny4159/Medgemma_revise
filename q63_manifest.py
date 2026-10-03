"""iter_063: 소견 삭제(R) 조건 요청 구성. 모델 출력 없이 iter_061/062 자료에서만 만든다.

규칙(사전 고정): 질문 = [MRI 소개 문장 ")."까지] + ' ' + [소견 문단] + ' ' + 'What is the most likely diagnosis for this participant?'
R 조건은 소견 문단만 삭제하고 앞뒤 두 문장을 원문 그대로 둔다. 새 정보·paraphrase 없음. 경계가 다르면 중단한다.
E10 = E21 중 위 틀을 갖는 BraTS/ISLES 10개(QA 587,658,721,740,759,782,831,1120,1224,1297), D2 = D3 중 QA 694,1253.
원문(O) 요청 중 T/J는 E21/D3 요청 파일의 행과 동일해야 한다(동일 함수로 재구성해 행 단위 대조).
사용: python q63_manifest.py
"""
import hashlib, json, os
import mri61_spec as S

OUT = 'results/iter_063/data'
P62 = 'results/iter_062/data'
E_QA = [587, 658, 721, 740, 759, 782, 831, 1120, 1224, 1297]
D_QA = [694, 1253]
FINAL_Q = 'What is the most likely diagnosis for this participant?'
INTRO_END = ').'


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def split_question(q):
    """(intro, core, final, start, end). 경계 가정이 깨지면 AssertionError."""
    assert q.count(FINAL_Q) == 1 and q.endswith(FINAL_Q), 'final question boundary'
    i = q.index(INTRO_END)
    assert q.startswith('The participant underwent Magnetic Resonance Imaging (MRI) scans (') and i < 200, 'intro boundary'
    intro = q[:i + 2]
    start, end = i + 3, len(q) - len(FINAL_Q) - 1
    assert q[i + 2] == ' ' and q[end] == ' ', 'separator'
    core = q[start:end]
    assert core.strip() == core and len(core) > 20, 'core'
    assert q == intro + ' ' + core + ' ' + FINAL_Q
    return intro, core, FINAL_Q, start, end


def redact(q):
    intro, core, final, start, end = split_question(q)
    return intro + ' ' + final, {'intro': intro, 'removed': core, 'final': final, 'removed_start': start, 'removed_end': end}


def build_rows_T_J(clusters, qa_by_id, img_dir, redacted):
    rows = []
    for c in clusters:
        x = dict(qa_by_id[c['qa_id']])
        if redacted:
            x['question'] = redact(x['question'])[0]
        paths = [f'{img_dir}/{p}' for p in c['images']]
        for order, perm in S.perms(x['id']).items():
            prompt = S.make_prompt(x['question'], x['options'], perm)
            for cond, imgs in (('T', []), ('J', paths)):
                ish = S.sha(json.dumps(imgs))
                tag = 'R' if redacted else 'O'
                rid = S.sha(f"{c['cluster_id']}|{x['id']}|{cond}|{order}|{ish}|{S.sha(prompt)}|{S.SEED}|{tag}")[:24]
                rows.append({'rid': rid, 'cluster_id': c['cluster_id'], 'qa_id': x['id'], 'source': c['source'], 'K': len(paths),
                             'cond': cond, 'order': order, 'perm': perm, 'images': imgs, 'prompt': prompt, 'images_sha': ish,
                             'text_cond': tag})
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    assert not os.path.exists(f'{OUT}/selection_manifest.json'), 'already locked'
    lock = json.load(open(f'{S.DATA}/selection_lock.json'))
    qa = {x['id']: x for x in json.load(open(f'{S.DATA}/eligible_qa.json'))}
    imgm = json.load(open(f'{S.DATA}/image_manifest.json'))
    m62 = json.load(open(f'{P62}/selection_manifest.json'))
    e_rows_orig = {r['rid']: r for r in jl(f'{P62}/E21_requests.jsonl')}
    d_rows_orig = {r['rid']: r for r in jl(f'{P62}/D3_requests.jsonl')}
    e_labels = json.load(open(f'{P62}/E21_labels.json'))
    d_labels = json.load(open(f'{P62}/D3_labels.json'))

    Ec = [c for c in lock['E_ordered_multi'] if c['cluster_id'] in set(m62['E21_clusters']) and c['qa_id'] in E_QA]
    Ec.sort(key=lambda c: m62['E21_clusters'].index(c['cluster_id']))
    Dc = [c for c in lock['D'] if c['qa_id'] in D_QA]
    assert sorted(c['qa_id'] for c in Ec) == sorted(E_QA) and sorted(c['qa_id'] for c in Dc) == sorted(D_QA)

    out, info = {}, {}
    for name, cl, orig, labels in (('E10', Ec, e_rows_orig, e_labels), ('D2', Dc, d_rows_orig, d_labels)):
        # O 재구성(재사용 근거): 원문 T/J 행은 기존 요청과 달라지면 안 된다. rid에 'O' tag를 쓰지 않으므로 필드 비교만.
        rowsO = build_rows_T_J(cl, qa, f'{S.DATA}/images', False)
        for r in rowsO:
            ref = None
            for o in orig.values():
                if o['cluster_id'] == r['cluster_id'] and o['cond'] == r['cond'] and o['order'] == r['order']:
                    ref = o
            assert ref is not None
            for k in ('qa_id', 'source', 'K', 'perm', 'images', 'prompt', 'images_sha'):
                assert ref[k] == r[k], f'O mismatch {k} {r["cluster_id"]}'
        rowsR = build_rows_T_J(cl, qa, f'{S.DATA}/images', True)
        assert len({r['rid'] for r in rowsR}) == len(rowsR) == len(cl) * 4
        for r in rowsR:  # 삭제 외 변경 없음 + 정답 단서 문자열 부재
            o = next(x for x in rowsO if x['cluster_id'] == r['cluster_id'] and x['cond'] == r['cond'] and x['order'] == r['order'])
            assert r['perm'] == o['perm'] and r['images'] == o['images']
            intro, core, final, _, _ = split_question(qa[r['qa_id']]['question'])
            assert o['prompt'].replace(' ' + core, '', 1) == r['prompt'], 'prompt diff beyond removal'
        out[name] = rowsR
        with open(f'{OUT}/{name}_requests.jsonl', 'w') as f:
            for r in rowsR:
                f.write(json.dumps(r) + '\n')
        json.dump({c['cluster_id']: labels[str(c['cluster_id'])] if str(c['cluster_id']) in labels else labels[c['cluster_id']] for c in cl},
                  open(f'{OUT}/{name}_labels.json', 'w'), indent=1)
        info[name] = {'clusters': [c['cluster_id'] for c in cl], 'n_requests': len(rowsR), 'n_original_TJ_rows_checked': len(rowsO)}

    # 삭제 manifest: offset·삭제 문자열·전후 질문·원 annotation hash
    red = {}
    for c in Ec + Dc:
        x = qa[c['qa_id']]
        rq, d = redact(x['question'])
        red[str(c['qa_id'])] = {'cluster_id': c['cluster_id'], 'source': c['source'], 'split': 'E10' if c in Ec else 'D2',
                                'original_question_sha256': S.sha(x['question']), 'redacted_question': rq,
                                'redacted_question_sha256': S.sha(rq), 'answer_letter': x['answer'], 'label': x['label'],
                                'n_images': len(c['images']), 'sequences': x.get('modality_type'),
                                'annotation_sha256': S.sha(json.dumps(x, sort_keys=True)), **d}
    imgs = sorted({p for rs in out.values() for r in rs for p in r['images']})
    for p in imgs:
        assert sha_file(p) == imgm[os.path.relpath(p, f'{S.DATA}/images')]['file_sha256'], 'image hash ' + p
    man = {'plan': 'iter_063', 'iter_062_plan_sha256': '277b988b39f2292e02df668eaa1d6be0536bda4f524d754fbfdc20e6f411a98d',
           'E10_qa': E_QA, 'D2_qa': D_QA, 'redaction': red, 'info': info, 'n_images_checked': len(imgs),
           'source_selection_lock_sha256': sha_file(f'{S.DATA}/selection_lock.json'),
           'source_eligible_qa_sha256': sha_file(f'{S.DATA}/eligible_qa.json'),
           'source_image_manifest_sha256': sha_file(f'{S.DATA}/image_manifest.json'),
           'iter062_selection_manifest_sha256': sha_file(f'{P62}/selection_manifest.json'),
           'iter062_E21_requests_sha256': sha_file(f'{P62}/E21_requests.jsonl'),
           'iter062_D3_requests_sha256': sha_file(f'{P62}/D3_requests.jsonl'),
           'E10_requests_sha256': sha_file(f'{OUT}/E10_requests.jsonl'), 'D2_requests_sha256': sha_file(f'{OUT}/D2_requests.jsonl'),
           'note': 'MedGemma/Qwen 결과를 본 뒤 정한 집합이 아니라 질문 틀(구조) 기준. 개발 자료, 독립 확인 아님.'}
    json.dump(man, open(f'{OUT}/selection_manifest.json', 'w'), indent=1)
    print(info, 'images', len(imgs))


if __name__ == '__main__':
    main()
