"""iter_095 reference 잠금 + 초기 32/나머지 64 선택. 새 Describe 출력 생성 전에 실행한다.

규칙(출력·모델 조건과 무관하게 reference 문장만 사용; 이미 본 E96 개발 자료이며 사후 탐색 설계임을 기록):
- 주 대상: 폐 opacity/infiltrate/consolidation 및 atelectasis. 임상적으로 동일 진단으로 합치지 않고 원 소견 종류 유지.
- 현재 확정 양성: amendment v2_class가 pos_def/pos_temporal(현재 존재 포함)인 사실 중 label이 {infiltrates, consolidation,
  atelectasis, laminar atelectasis}이거나 문장이 'pulmonary opacit'을 포함. temporal은 현재 존재만 평가(변화 정확도 아님).
- 명시적 부재: v2_class가 neg_specific/neg_scoped이고 문장이 infiltrat|consolidat|opacit|condensat 중 하나를 부정.
  generic_normal·normal_scoped(예: 'Pulmonary parenchyma within normal limits')는 명시적 부재로 쓰지 않는다.
- 층: pos(최대12) / neg(최대10) / rest(10). 부족한 층은 전원, 남은 자리는 rest의 hash 순 미선택자로 채운다.
- 환자 hash 순서: sha256(['report95', seed95017, ImageID]).
"""
import json
import re

from report95_common import R86, LOCK, ROOT, sha, sha_obj, save, hash_order

SEED_LOCK = 95017
TARGET_LABELS = {'infiltrates', 'consolidation', 'atelectasis', 'laminar atelectasis'}
NEG_RE = re.compile(r'infiltrat|consolidat|opacit|condensat', re.I)


def build():
    facts = json.loads((R86 / 'E/reference_facts_E_private.json').read_text())
    amend = json.loads((ROOT / 'results/iter_087/reference_amend_E96.json').read_text())['patients']
    rows = json.loads((R86 / 'E/inputs_E96.json').read_text())
    ids = [r['ImageID'] for r in rows]
    layer, detail = {}, {}
    for idx, img in enumerate(ids):
        by = {f['fact_id']: f for f in facts[img]['facts']}
        pos, neg = [], []
        for af in amend[img]['facts']:
            f = by[af['fact_id']]
            cls, text = af['v2_class'], af['sentence_en']
            if cls in ('pos_def', 'pos_temporal') and (set(f['labels']) & TARGET_LABELS or re.search(r'pulmonary opacit', text, re.I)):
                pos.append({'fact_id': af['fact_id'], 'class': cls, 'sentence': text, 'labels': f['labels'], 'loc_req': af['loc_req'],
                            'attr_req': af['attr_req']})
            if cls in ('neg_specific', 'neg_scoped') and NEG_RE.search(text):
                neg.append({'fact_id': af['fact_id'], 'class': cls, 'sentence': text})
        layer[img] = 'pos' if pos else ('neg' if neg else 'rest')
        detail[img] = {'patient_index': idx, 'layer': layer[img], 'pos_facts': pos, 'neg_facts': neg}
    pos_ids = hash_order([i for i in ids if layer[i] == 'pos'], ['report95', SEED_LOCK])
    neg_ids = hash_order([i for i in ids if layer[i] == 'neg'], ['report95', SEED_LOCK])
    rest_ids = hash_order([i for i in ids if layer[i] == 'rest'], ['report95', SEED_LOCK])
    p, n = pos_ids[:12], neg_ids[:10]
    r = rest_ids[:10]
    short = 32 - len(p) - len(n) - len(r)
    r = rest_ids[:10 + max(short, 0)]
    # 양성/음성 층이 12/10을 넘어 남는 환자는 나머지 64로 이동(여기서는 해당 없음)
    e32 = p + n + r
    assert len(e32) == 32 and len(set(e32)) == 32
    e64 = [i for i in ids if i not in set(e32)]
    sel = {'seed': SEED_LOCK, 'E32': e32, 'E64': e64,
           'strata_counts_E96': {k: sum(v == k for v in layer.values()) for k in ('pos', 'neg', 'rest')},
           'E32_strata': {'pos': len(p), 'neg': len(n), 'rest': len(r)},
           'E64_remaining_strata': {k: sum(layer[i] == k for i in e64) for k in ('pos', 'neg', 'rest')},
           'opportunity_note': '남은 64명에는 reference 지지 양성/명시적 부재 평가 기회가 각각 이 수만큼만 있다.',
           'inputs_E96_sha256': sha(R86 / 'E/inputs_E96.json'),
           'reference_amend_sha256': sha(ROOT / 'results/iter_087/reference_amend_E96.json'),
           'reference_facts_sha256': sha(R86 / 'E/reference_facts_E_private.json'),
           'code_sha256': sha(__file__), 'status': '출력 생성 전 잠금. 이미 본 E96 개발 자료의 사후 탐색 설계(독립 확인 아님).'}
    return sel, detail


if __name__ == '__main__':
    sel, detail = build()
    save(LOCK / 'reference_target.json', detail)
    sel['reference_target_sha256'] = sha(LOCK / 'reference_target.json')
    save(LOCK / 'selection.json', sel)
    print(json.dumps({k: sel[k] for k in ('strata_counts_E96', 'E32_strata', 'E64_remaining_strata')}))
