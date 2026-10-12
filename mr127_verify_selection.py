"""선정의 독립 산술·원문 anchor 검산. 의미 판단 자체의 독립 전문가 검증은 아니다."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import time


def digest(p):
    d=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):d.update(b)
    return d.hexdigest()


def main():
    root=Path('results/iter_127/data')
    load=lambda p:json.loads(Path(p).read_text())
    lock=load(root/'selection_lock.json'); ordered=load(root/'ordered_candidates.json')
    judgments=load(root/'judgments.json'); provenance=load(root/'provenance.json')
    checks=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
    check('judgment_hash',digest(root/'judgments.json')==lock['judgments_sha256'])
    check('provenance_hash',digest(root/'provenance.json')==lock['provenance_sha256'])
    for p,h in provenance['inputs'].items():check('input:'+p,digest(p)==h)
    for p,h in provenance['inherited_outputs'].items():check('old_output:'+p,digest(p)==h)
    old=load('results/iter_125/data/selection_lock.json')
    required={m['patient_uid'] for m in old['manifest']}
    for cell,rows in ordered.items():
        hashes=[hashlib.sha256(('125|'+str(c['patient_uid'])).encode()).hexdigest() for c in rows]
        check('ordered:'+cell,hashes==sorted(hashes) and all(c['h']==h for c,h in zip(rows,hashes)))
        old_ids={m['patient_uid'] for m in old['manifest'] if m['batch_id']+'|'+m['label']==cell}
        last=max(i for i,c in enumerate(rows) if c['patient_uid'] in old_ids)
        required.update(c['patient_uid'] for c in rows[:last+1])
        wanted=[]
        for c in rows:
            if len(wanted)==15:break
            j=judgments.get(str(c['patient_uid']))
            check('reviewed_prefix:'+str(c['patient_uid']),j is not None)
            if j and j['decision']=='include':wanted.append(c['patient_uid'])
        selected=[m for m in lock['manifest'] if m['batch_id']+'|'+m['label']==cell]
        check('first15:'+cell,[m['patient_uid'] for m in selected]==wanted and len(wanted)==15)
        check('roles:'+cell,[m['role'] for m in selected]==['tech']*2+['calib']*3+['explore']*10)
    check('old60_and_skipped20_reviewed',required<={int(p) for p in judgments})
    check('unique60',len(lock['manifest'])==len({m['patient_uid'] for m in lock['manifest']})==len({m['study_uid'] for m in lock['manifest']})==60)
    reports={}
    for batch in ['batch04','batch23']:
        p=Path('/home/test/.local/share/medgemma/mr_rate/meta/reports')/f'{batch}_reports.csv'
        with p.open(newline='') as f:rows=list(csv.DictReader(f))
        reports[batch]={r['study_uid']:(i,r) for i,r in enumerate(rows)}
    for m in lock['manifest']:
        i,r=reports[m['batch_id']][m['study_uid']]
        check('csv_row:'+m['study_uid'],i==m['csv_row_index'])
        check('polarity:'+m['study_uid'],m['review']['polarity']==m['label'] and not m['review']['conflict'])
        for a in m['anchors']:
            check('anchor:'+m['study_uid']+':'+str(a['start']),r[a['section']][a['start']:a['end']]==a['quote'])
    status=all(c['passed'] for c in checks)
    output=dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),all_pass=status,
        check_count=len(checks),checks=checks,reviewed_cases=len(judgments),required_cases=len(required),
        selected_cells=dict(Counter(m['batch_id']+'|'+m['label'] for m in lock['manifest'])),
        judgment_counts=dict(Counter(j['decision'] for j in judgments.values())),
        scope_ko='원 CSV·입력 hash·순서·역할·인용·과거 결과 불변을 검산. 임상 정답이나 새로운 독립 의미 판정을 만들지 않음.',
        source_sha256=digest(__file__),selection_sha256=digest(root/'selection_lock.json'))
    with (root/'independent_verify.json').open('x') as f:json.dump(output,f,ensure_ascii=False,indent=2)
    print('selection verify',sum(c['passed'] for c in checks),'/',len(checks))
    return 0 if status else 2


if __name__=='__main__':raise SystemExit(main())
