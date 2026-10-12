"""iter_124: 기존 iter_123 탐색 48명에서 batch x label 층별 SHA256('124|patient_uid|study_uid') 오름차순 첫 6명(24명)을 고정한다.
출력(모델 응답)을 사용하지 않는다. 원 iter_123 파일은 읽기만 한다.
usage: python mr124_select.py candidates   # results/iter_124/data/candidates.json 생성(없을 때만)
       python mr124_select.py print        # 선정 24명 보고서 findings/impression 출력
"""
import hashlib, json, os, sys
import pandas as pd

SRC = 'results/iter_123/data/selection_lock.json'
OUT = 'results/iter_124/data/'
META = '/home/test/.local/share/medgemma/mr_rate/meta/'


def h(p, s):
    return hashlib.sha256(f'124|{p}|{s}'.encode()).hexdigest()


def candidates():
    L = json.load(open(SRC))
    ex = [m for m in L['manifest'] if m['role'] == 'explore']
    out = {}
    for m in ex:
        out.setdefault(f"{m['batch_id']}|{m['label']}", []).append(m)
    sel = []
    for k in sorted(out):
        rows = sorted(out[k], key=lambda m: h(m['patient_uid'], m['study_uid']))
        for i, m in enumerate(rows):
            m = dict(m, rank_in_stratum=i, hash124=h(m['patient_uid'], m['study_uid']), stratum=k, selected=i < 6)
            sel.append(m)
    return sel


def reports(batch):
    return pd.read_csv(META + f'reports/{batch}_reports.csv', dtype=str).set_index('study_uid')


if __name__ == '__main__':
    if sys.argv[1] == 'candidates':
        p = OUT + 'candidates.json'
        assert not os.path.exists(p)
        c = candidates()
        json.dump(c, open(p, 'w'), indent=1)
        print(len(c), sum(x['selected'] for x in c))
    elif sys.argv[1] == 'print':
        c = [x for x in json.load(open(OUT + 'candidates.json')) if x['selected']]
        R = {b: reports(b) for b in ('batch04', 'batch23')}
        for x in c:
            r = R[x['batch_id']].loc[x['study_uid']]
            print('=' * 100)
            print(x['stratum'], x['rank_in_stratum'], x['study_uid'], x['patient_uid'])
            print('SPANS pos:', x['pos_spans'], '\nSPANS neg:', x['neg_spans'])
            print('FINDINGS:', r['findings'])
            print('IMPRESSION:', r['impression'])
