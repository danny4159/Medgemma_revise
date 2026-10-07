"""iter_090 target amendment. 기존 ID와 원문을 보존하고 E 원문은 출력하지 않는다."""
import re
import copy
from collections import Counter
import report89_data as B
from report86_common import save, sha

OUT=B.ROOT/'results/iter_090'
TEMPORAL=re.compile(B.D.TEMPORAL_RE.pattern.replace('|chang\\w*',''),re.I)
CHANGE=re.compile(r'\b(changed|changing|change(?:s)?\s+(?:since|from|compared|over))\b',re.I)
DEPENDENT=re.compile(r'\b(?:no other|otherwise|remaining|rest of)\b',re.I)

def current_findings(r):
    keep,excluded=[],[]
    for i,f in enumerate(r['findings']):
        s=f.get('sentence_en','')
        reason=None
        if not isinstance(s,str) or not s.strip(): reason='empty'
        elif f.get('progression') is not None or TEMPORAL.search(s) or CHANGE.search(s): reason='temporal'
        elif DEPENDENT.search(s) and (i==0 or excluded): reason='context_dependency_after_exclusion'
        if reason: excluded.append([i,reason])
        else:
            assert all(B.D.valid_box(b) for b in f.get('boxes',[]))
            keep.append(dict(f,source_index=i))
    return keep,excluded

def main():
    old=B.read(B.OUT/'data/selection.json')
    save(OUT/'amendment_v2.json',dict(parent_plan_sha256=sha(B.ROOT.parent/'agent/runs/iter_089/plan.md'),
        plan_sha256=sha(B.ROOT.parent/'agent/runs/iter_090/plan.md'),parent_selection_sha256=sha(B.OUT/'data/selection.json'),
        prior_failure_sha256=sha(B.OUT/'tech/a1/result.json'),source_sha256=sha(__file__),
        rule='현재 changes 명사 보존; progression/명시 시간 비교 제외; 선행 제외 뒤 문맥 의존 문장 제외',
        id_rule='기존 적격 ID 보존. 빈 target은 같은 split/기존 층의 seed89017 hash 순 미사용 환자로 보충; E 원문 비출력',training_authorized=False))
    cases=[('Degenerative changes of dorsal spondylosis.',True),('Chronic pulmonary changes in the middle lobe and lingula.',True),
           ('COPD changes with air trapping.',True),('Mechanical changes in intersomatic spaces.',True),
           ('Increased effusion compared with prior imaging.',False),('Stable cardiomegaly.',False),('Changed since last examination.',False)]
    checks=[]
    for text,want in cases:
        got=bool(current_findings({'findings':[dict(sentence_en=text,progression=None)]})[0]);checks.append(dict(text=text,passed=got==want))
    for first,want in [('Stable spondylosis.',False),('Degenerative changes of the spine.',True)]:
        fs,_=current_findings({'findings':[dict(sentence_en=first),dict(sentence_en='No other abnormalities.')]})
        checks.append(dict(text=first+' No other abnormalities.',passed=any(f['source_index']==1 for f in fs)==want))
    assert all(x['passed'] for x in checks)
    save(OUT/'tests/target_fixtures_v2.json',dict(passed=True,checks=checks))
    reports,_,links=B.D.load_inputs();by={r['ImageID']:r for r in reports}
    selected=copy.deepcopy(old);changes=[];invalid=[]
    for subset,rows in selected.items():
        for row in rows:
            source=by[row['ImageID']];fs,ex=current_findings(source)
            if not fs:invalid.append([subset,row['ImageID'],'empty'])
            orig=any(f.get('abnormal') is True for f in source['findings'])
            row.update(stratum=B.stratum(fs,orig),retained_abnormal=any(f.get('abnormal') is True for f in fs),excluded_sentences=ex)
            if subset in ('T512','V64'):
                before,_=B.current_findings(source)
                if before!=fs:changes.append(dict(subset=subset,ImageID=row['ImageID'],before=before,after=fs,excluded=ex))
    lock=B.read(B.OUT/'data/selection_lock.json')
    used={r['PatientID'] for s in ('T512','V64','E128') for r in selected[s]}
    replacements={}
    for subset,iid,reason in invalid:
        if subset not in ('T512','V64','E128'):continue
        previous=next(r for r in old[subset] if r['ImageID']==iid)
        candidates=[]
        for source in reports:
            image=source['ImageID'];pid=links['img2patient'][image]
            if links['img2split'][image]!=previous['split'] or pid in used or pid in lock['protected_patients']:continue
            if previous['split']=='test' and pid in lock['exposed_patients']:continue
            fs,ex=current_findings(source)
            if not fs:continue
            orig=any(f.get('abnormal') is True for f in source['findings'])
            st=B.stratum(fs,orig)
            if st!=previous['stratum']:continue
            candidates.append(dict(ImageID=image,PatientID=pid,StudyID=source['StudyID'],split=previous['split'],stratum=st,
                original_abnormal=orig,retained_abnormal=any(f.get('abnormal') is True for f in fs),excluded_sentences=ex))
        replacement=min(candidates,key=B.key);used.add(replacement['PatientID']);replacements[iid]=replacement
    for subset,rows in selected.items():
        selected[subset]=[copy.deepcopy(replacements.get(r['ImageID'],r)) for r in rows]
    save(OUT/'data/replacements.json',dict(invalid=invalid,replacements=replacements))
    assert sum(r['retained_abnormal'] for r in selected['E128'])==96
    assert sum(not r['original_abnormal'] for r in selected['E128'])==32
    for s in selected:
        assert all(a['ImageID']==b['ImageID'] or b['ImageID'] in replacements for a,b in zip(selected[s],old[s]))
    for a,b in [('T512','V64'),('T512','E128'),('V64','E128')]:
        for field in ('PatientID','StudyID','ImageID'):assert not {r[field] for r in selected[a]}&{r[field] for r in selected[b]}
    save(OUT/'data/selection.json',selected)
    save(OUT/'data/selection_lock.json',dict(selection_sha256=sha(OUT/'data/selection.json'),source_sha256=sha(__file__),
        metadata=links['inputs_sha256'],parent_lock_sha256=sha(B.OUT/'data/selection_lock.json'),id_replacements=len(replacements),
        strata={s:dict(Counter(r['stratum'] for r in rows)) for s,rows in selected.items()},E_reference_opened=False))
    save(OUT/'data/target_changes_TV.json',changes)
    B.OUT=OUT;B.current_findings=current_findings;B.extract('D8')
    print('target fixtures',len(checks),'changed T/V patients',len(changes),'ID replacements',len(replacements))

if __name__=='__main__':main()
