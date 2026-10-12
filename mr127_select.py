"""iter127 전용 원문 검토/선정. 의미 판정은 저장한 사례별 판단만 사용한다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import pandas as pd
import mr125_select as candidate

OUT = Path('results/iter_127/data')
META = Path(candidate.M)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def save(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def prepare():
    old = read('results/iter_125/data/selection_lock.json')
    sources = {str(META / p): sha(META / p) for p in old['source_sha256']}
    assert all(sources[str(META / p)] == h for p, h in old['source_sha256'].items())
    baseline = read('../agent/runs/iter_127/code_baseline.json')
    for p, v in baseline['files'].items():
        if p.startswith(('mr123_', 'mr125_', 'mr126_')):
            assert sha(p) == v['hash'], p
    plans = {'125': '477a1c817abfe198e25c14f64a487fbd6f53d5ab0c4a7e5fab91e36f2b705a47',
             '126': '632a6090c0246dde0e0d8d80c18fee007d3f0625bae6d4320ffe1d67972e4070'}
    for i, h in plans.items():
        p = f'../agent/runs/iter_{i}/plan.md'
        assert sha(p) == h
        sources[p] = h
    for p in ['../agent/runs/iter_127/plan.md', '../agent/runs/iter_127/plan.json',
              '../agent/runs/iter_125/reuse_manifest.json', 'results/iter_125/data/candidates_raw.json',
              'results/iter_125/data/ordered_candidates.json', 'results/iter_125/data/selection_lock.json']:
        sources[p] = sha(p)
    splits = pd.read_csv(META / 'splits.csv')
    old_pids = candidate.old_patients()
    joined, reports = [], {}
    for b in ['batch04', 'batch23']:
        meta = pd.read_csv(META / f'metadata/{b}_metadata.csv', low_memory=False)
        t = meta[(meta.classified_modality == 'T2w') & (meta.acquisition_plane == 'AXIAL') &
                 (meta.is_derived.astype(str) == 'False') & (meta.is_localizer.astype(str) == 'False')].copy()
        spacing = t.array_spacing_mm.map(json.loads)
        t['dz'] = spacing.map(lambda x: x[2])
        t['area'] = spacing.map(lambda x: x[0] * x[1])
        t = t.sort_values(['study_uid', 'dz', 'area', 'series_id']).groupby('study_uid').head(1)
        t = t.merge(splits[splits.batch_id == b][['study_uid', 'split']], on='study_uid', validate='one_to_one')
        r = pd.read_csv(META / f'reports/{b}_reports.csv').fillna('')
        assert not r.study_uid.duplicated().any()
        reports[b] = {x['study_uid']: dict(csv_row_index=i, **x) for i, x in enumerate(r.to_dict('records'))}
        t = t[t.split == 'train'].merge(r, on='study_uid', validate='one_to_one')
        t['batch_id'] = b
        joined.append(t)
    d = pd.concat(joined)
    d = d[~d.patient_uid.isin(old_pids)].sort_values(['patient_uid', 'study_uid']).groupby('patient_uid').head(1)
    rebuilt = []
    for _, x in d.iterrows():
        hits = [(k, s) for k in ['findings', 'impression'] for s in candidate.sents(x[k]) if candidate.LV.search(s)]
        if not hits:
            continue
        pos = [h for h in hits if candidate.ENL.search(h[1]) and not candidate.NEGENL.search(h[1])]
        neg = [h for h in hits if h not in pos and (candidate.NORM.search(h[1]) or candidate.NEGENL.search(h[1]))]
        rebuilt.append(dict(batch_id=x.batch_id, patient_uid=int(x.patient_uid), study_uid=x.study_uid,
                            series_id=x.series_id, array_shape=x.array_shape, array_spacing_mm=x.array_spacing_mm,
                            hits=hits, pos=pos, neg=neg))
    # JSON 직렬화로 tuple/list 표현을 정규화한다. 후보 검색 규칙 변경을 허용하지 않는다.
    assert json.loads(json.dumps(rebuilt)) == read('results/iter_125/data/candidates_raw.json')
    ordered = {}
    for c in rebuilt:
        lab = 'positive' if c['pos'] and not c['neg'] else 'negative' if c['neg'] and not c['pos'] else None
        if lab:
            c.update(cand_label=lab, h=hashlib.sha256(f"125|{c['patient_uid']}".encode()).hexdigest())
            ordered.setdefault(c['batch_id'] + '|' + lab, []).append(c)
    for v in ordered.values():
        v.sort(key=lambda c: c['h'])
    assert json.loads(json.dumps(ordered)) == read('results/iter_125/data/ordered_candidates.json')
    inherited = {str(p): sha(p) for i in [125, 126] for p in Path(f'results/iter_{i}').rglob('*') if p.is_file()}
    save(OUT / 'provenance.json', dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         inputs=sources, inherited_outputs=inherited, baseline_sha=baseline['sha'],
         baseline_sources={p: v['hash'] for p,v in baseline['files'].items() if p.startswith(('mr123_', 'mr125_', 'mr126_'))},
         candidate_reconstruction_equal=True, original_order_equal=True,
         excluded_previous_patients=sorted(old_pids), sizes={k: len(v) for k,v in ordered.items()}))
    save(OUT / 'ordered_candidates.json', ordered)
    save(OUT / 'full_reports.json', reports)
    print({k: len(v) for k,v in ordered.items()})


def show(cell, start, end):
    rows = read(OUT / 'ordered_candidates.json')[cell]
    reports = read(OUT / 'full_reports.json')
    for rank, c in enumerate(rows[start:end], start):
        r = reports[c['batch_id']][c['study_uid']]
        print(f"\n[{rank}] patient={c['patient_uid']} study={c['study_uid']} cell={cell} CSVrow={r['csv_row_index']}")
        print('REPORT:', r['report'])
        # 원 report에 이미 표시된 문장은 비교 결과와 함께 중복 표시만 생략한다.
        norm = lambda s: re.sub(r'\s+', ' ', s).strip()
        for section in ['findings', 'impression']:
            lines = [re.sub(r'^[—•*·]\s*','',line).strip() for line in r[section].splitlines() if line.strip()]
            new = [line for line in lines if norm(line) not in norm(r['report'])]
            print(section.upper(), '원 report와 중복인 행', len(lines)-len(new), '/',len(lines))
            for line in new:
                print('추가 구조화 문구:',line)


def lock():
    provenance = read(OUT / 'provenance.json')
    assert all(sha(p) == h for p,h in provenance['inputs'].items())
    ordered = read(OUT / 'ordered_candidates.json')
    reports = read(OUT / 'full_reports.json')
    judgments = read(OUT / 'judgments.json')
    old = read('results/iter_125/data/selection_lock.json')
    manifest, traces = [], {}
    required = {m['patient_uid'] for m in old['manifest']}
    for cell, rows in ordered.items():
        old_ids = {m['patient_uid'] for m in old['manifest'] if m['batch_id']+'|'+m['label'] == cell}
        last = max(i for i,c in enumerate(rows) if c['patient_uid'] in old_ids)
        required.update(c['patient_uid'] for c in rows[:last+1])
        selected = []
        for rank,c in enumerate(rows):
            pid = str(c['patient_uid'])
            if pid not in judgments:
                raise ValueError(f'의미 검토 누락: {cell} rank={rank} patient={pid}')
            j = judgments[pid]
            r = reports[c['batch_id']][c['study_uid']]
            assert j['full_fields_reviewed'] == ['report','findings','impression']
            assert j['decision'] in ['include','exclude','unknown'] and j['reason_ko']
            assert j['target'] and j['polarity'] and isinstance(j['conflict'], bool)
            anchors = []
            for a in j['quotes']:
                text = r[a['section']]
                start = text.find(a['quote'])
                assert start >= 0, (pid,a)
                anchors.append(dict(**a,start=start,end=start+len(a['quote'])))
            assert anchors
            if j['decision'] == 'include':
                assert j['polarity'] == c['cand_label'] and not j['conflict']
                selected.append(dict(**c, rank_zero_based=rank, review=j,
                                     anchors=anchors, source_csv=str(META/f"reports/{c['batch_id']}_reports.csv"),
                                     source_sha256=sha(META/f"reports/{c['batch_id']}_reports.csv"),
                                     csv_row_index=r['csv_row_index'],
                                     source_row_sha256=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()))
            if len(selected) == 15:
                break
        traces[cell] = dict(last_reviewed_rank=rank, selected_patients=[m['patient_uid'] for m in selected])
        assert len(selected) == 15, ('층별 적격 표본 부족',cell)
        for i,m in enumerate(selected):
            m['label'] = m.pop('cand_label')
            m['role'] = 'tech' if i < 2 else 'calib' if i < 5 else 'explore'
            manifest.append(m)
    assert required <= {int(p) for p in judgments}, ('기존/선행 후보 검토 누락',required-{int(p) for p in judgments})
    assert len(manifest) == len({m['patient_uid'] for m in manifest}) == len({m['study_uid'] for m in manifest}) == 60
    assert not {m['patient_uid'] for m in manifest} & set(provenance['excluded_previous_patients'])
    oldby = {m['patient_uid']: m for m in old['manifest']}
    newby = {m['patient_uid']: m for m in manifest}
    diff = [dict(patient_uid=pid, old_role=oldby.get(pid,{}).get('role'), new_role=newby.get(pid,{}).get('role'),
                 reason_ko=judgments[str(pid)]['reason_ko'] if pid not in newby else '원 hash 순서 첫15 적격자 재선정과 역할 재배정')
            for pid in sorted(oldby.keys()|newby.keys()) if oldby.get(pid,{}).get('role') != newby.get(pid,{}).get('role')]
    assert all(sha(p)==h for p,h in provenance['inherited_outputs'].items())
    save(OUT / 'selection_diff.json',diff)
    save(OUT / 'selection_lock.json',dict(seed=125, manifest=manifest, traces=traces,
          created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
          judgments_sha256=sha(OUT/'judgments.json'), provenance_sha256=sha(OUT/'provenance.json'),
          source_code_sha256=sha(__file__), reviewed_patients=len(judgments),
          semantic_review_scope='기록된 개별 후보만; 후순위 미검토 후보는 미인증', inherited_results_unchanged=True))
    print('locked',len(manifest),Counter(m['role'] for m in manifest),'diff',len(diff))


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('action',choices=['prepare','show','lock'])
    ap.add_argument('--cell')
    ap.add_argument('--start',type=int,default=0)
    ap.add_argument('--end',type=int,default=5)
    a=ap.parse_args()
    if a.action=='prepare': prepare()
    elif a.action=='show': show(a.cell,a.start,a.end)
    else: lock()
