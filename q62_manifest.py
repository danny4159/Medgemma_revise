"""iter_062: E21(적격성 정정) / D3 manifest 고정. 모델 출력 없이 iter_061 자료에서만 구성한다.

- E21 = iter_061 E24에서 QA 2322(intervention/전후 변화), 1419(수술 후 재발 longitudinal), 2033(비뇌 부비동)을 제외한 21 cluster
- 요청은 mri61_spec.build_rows로 재구성하고 기존 E24 요청과 행 단위로 동일함을 검증(MedGemma 기존 출력 재사용 근거)
- 소견 미서술 6개(QA 1552,1513,1475,1451,1596,1416)는 Qwen 출력 전에 고정하는 보조 분류
사용: python q62_manifest.py
"""
import hashlib, json, os, sys
import mri61_spec as S

OUT = 'results/iter_062/data'
P61 = 'results/iter_061'
EXCL = {2322: 'intervention/전후 변화 질문', 1419: '수술 후 재발의 longitudinal 관측', 2033: '비뇌(부비동) 진단'}
UNSTATED = [1552, 1513, 1475, 1451, 1596, 1416]
D_QA = [694, 1518, 1253]


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def main():
    os.makedirs(OUT, exist_ok=True)
    assert not os.path.exists(f'{OUT}/selection_manifest.json'), 'already locked'
    lock = json.load(open(f'{S.DATA}/selection_lock.json'))
    qa = {x['id']: x for x in json.load(open(f'{S.DATA}/eligible_qa.json'))}
    imgm = json.load(open(f'{S.DATA}/image_manifest.json'))
    e24 = {r['rid']: r for r in jl(f'{P61}/E24_requests.jsonl')}
    e24_labels = json.load(open(f'{P61}/E24_requests_labels.json'))
    d_all = {r['rid']: r for r in jl(f'{P61}/D_requests.jsonl')}
    d_labels = json.load(open(f'{P61}/D_requests_labels.json'))
    ex = lock['visual_exclusions']

    E = [r for r in lock['E_ordered_multi'] if r['cluster_id'] not in ex][:24]
    assert [r['cluster_id'] for r in E] == list(e24_labels), 'E24 order mismatch'
    excl_rows = {}
    for c in E:
        if c['qa_id'] in EXCL:
            excl_rows[c['cluster_id']] = {'qa_id': c['qa_id'], 'reason': EXCL[c['qa_id']],
                                          'question_head': qa[c['qa_id']]['question'][:300]}
    assert {v['qa_id'] for v in excl_rows.values()} == set(EXCL)
    E21 = [c for c in E if c['qa_id'] not in EXCL]
    assert len(E21) == 21

    def build(cl, ref):
        rows = S.build_rows(cl, qa, f'{S.DATA}/images')
        for r in rows:
            assert r['rid'] in ref and ref[r['rid']] == r, 'row differs from iter_061 request ' + r['rid']
        assert len({r['rid'] for r in rows}) == len(rows)
        return rows

    rowsE = build(E21, e24)
    labelsE = {c['cluster_id']: {**e24_labels[c['cluster_id']], 'unstated_findings': c['qa_id'] in UNSTATED} for c in E21}
    assert sum(v['unstated_findings'] for v in labelsE.values()) == 6

    Dc = [c for c in lock['D'] if c['qa_id'] in D_QA]
    assert sorted(c['qa_id'] for c in Dc) == sorted(D_QA)
    rowsD = build(Dc, d_all)
    labelsD = {c['cluster_id']: d_labels[c['cluster_id']] for c in Dc}

    # 영상 file hash 대조 + 개수
    imgs = sorted({p for r in rowsE + rowsD for p in r['images']})
    for p in imgs:
        rel = os.path.relpath(p, f'{S.DATA}/images')
        assert sha_file(p) == imgm[rel]['file_sha256'], 'image hash ' + p
    n_img_E = sum(len(S_.get('images', [])) for S_ in E21)
    cnt = {'E21_requests': len(rowsE), 'E21_T_J': sum(r['cond'] in ('T', 'J') for r in rowsE),
           'E21_S': sum(r['cond'].startswith('S') for r in rowsE), 'E21_image_sum': n_img_E,
           'D3_requests': len(rowsD)}
    assert cnt['E21_requests'] == 232 and cnt['E21_T_J'] == 84 and cnt['E21_S'] == 148 and n_img_E == 74 and len(rowsD) == 34, cnt

    for name, rows, labels in (('E21', rowsE, labelsE), ('D3', rowsD, labelsD)):
        with open(f'{OUT}/{name}_requests.jsonl', 'w') as f:
            for r in rows:
                f.write(json.dumps(r) + '\n')
        json.dump(labels, open(f'{OUT}/{name}_labels.json', 'w'), indent=1)
    man = {'base_plan_sha256': 'e310aa2f05e57d0ea53062b2dffda860b7444223e774259ee3436a9e3ab9afcc',
           'source_selection_lock_sha256': sha_file(f'{S.DATA}/selection_lock.json'),
           'source_eligible_qa_sha256': sha_file(f'{S.DATA}/eligible_qa.json'),
           'source_image_manifest_sha256': sha_file(f'{S.DATA}/image_manifest.json'),
           'source_E24_requests_sha256': sha_file(f'{P61}/E24_requests.jsonl'),
           'source_E24_labels_sha256': sha_file(f'{P61}/E24_requests_labels.json'),
           'excluded': excl_rows, 'E21_clusters': [c['cluster_id'] for c in E21],
           'unstated_findings_qa': UNSTATED, 'D3_qa': D_QA, 'counts': cnt,
           'E21_requests_sha256': sha_file(f'{OUT}/E21_requests.jsonl'),
           'D3_requests_sha256': sha_file(f'{OUT}/D3_requests.jsonl'),
           'note': 'MedGemma 결과를 본 뒤의 정정 집합: 독립 검증이 아니다. 개발 자료. 대체 사례 없음.'}
    json.dump(man, open(f'{OUT}/selection_manifest.json', 'w'), indent=1)
    print(cnt)


if __name__ == '__main__':
    main()
