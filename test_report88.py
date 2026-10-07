"""실제 평가 진입 경로의 필요한 거부·보존 검사. 변조는 메모리에서만 한다."""
import copy
import json
import re
import sys
from pathlib import Path
import report87_eval as E
from report86_common import ROOT, sha
from report88_eval import load_final
from report88_check import provenance_checks
from report88_handoff import OUT, write_new


def main():
    rows,reads,amend,v1,initial,jud=load_final()
    text=(OUT/'adjudication/judgments_final.txt').read_text(); tests=[]
    def reject(name,fn,needle):
        try:fn()
        except (E.JudgmentError,ValueError,FileExistsError,AssertionError) as ex:
            ok=needle in str(ex);tests.append({'name':name,'pass':ok,'error':str(ex)[:250],'expected_branch':needle});return
        tests.append({'name':name,'pass':False,'error':'예상 오류 없음'})
    def parse(t):return E.parse_v3(t,rows,amend,reads,v1)
    reject('중복 환자',lambda:parse(text+'\nP000\nO1\n'),'duplicate patient')
    reject('누락 환자',lambda:parse(text[:text.index('\nP095')]),'patients judged')
    reject('누락 조건',lambda:parse(re.sub(r'\nO8\n.*?(?=\nP[0-9]{3})','',text,count=1,flags=re.S)),'outputs')
    reject('잘못된 주장 anchor',lambda:parse(text.replace('c U -','c U -',1).replace('"The lungs are clear"','"없는 원문 anchor 880001"',1)),'anchor')
    # co-evidence 연결 검사는 실제 parser 분기에서 거부되어야 한다.
    b=text.splitlines();p=o=None;target=None
    for n,l in enumerate(b):
        if l.startswith('P') and len(l)==4:p=l
        if l.startswith('O') and len(l)==2:o=l
        if l.startswith('f ') and ' + N ' in l and target is None:target=(p,o,l.split()[1])
    pp,oo,fid=target;p=o=None;bad=[]
    for l in b:
        if l.startswith('P') and len(l)==4:p=l
        if l.startswith('O') and len(l)==2:o=l
        if (p,o)==(pp,oo) and l.startswith('c C.pos '+fid+' '):l=l.replace('c C.pos '+fid+' ','c U - ',1)
        bad.append(l)
    reject('co N의 C.pos 누락',lambda:parse('\n'.join(bad)),'co-evidence N needs')
    j=copy.deepcopy(jud)
    first=next(x for cs in j.values() for out in cs.values() for x in out['facts'].values() if x['co'])
    first['co']['span']='없는 co anchor 880002'
    errors,_=provenance_checks(j,reads)
    tests.append({'name':'co anchor 출처 검사','pass':any('co anchor' in str(e) for e in errors)})
    j=copy.deepcopy(jud);out=next(out for cs in j.values() for out in cs.values() if out['claims'])
    out['claims'].append(copy.deepcopy(out['claims'][0]));errors,_=provenance_checks(j,reads)
    tests.append({'name':'주장 중복 거부','pass':any('중복 주장' in str(e) for e in errors)})
    old=ROOT/'results/iter_087/protocol_lock.json';before=sha(old)
    reject('원본 경로 쓰기 거부',lambda:write_new(old,{}),'밖 쓰기 거부')
    tests.append({'name':'원본 보존','pass':sha(old)==before})
    current=OUT/'eval/report.json';before=sha(current)
    reject('완료 결과 덮어쓰기 거부',lambda:write_new(current,{}),'File exists')
    tests.append({'name':'완료 결과 보존','pass':sha(current)==before})
    fixed=json.loads((ROOT/'results/iter_086/E96/recheck_sample.json').read_text())
    actual=json.loads((OUT/'adjudication/recheck24.json').read_text())['indices']
    expected=[p['index'] for p in fixed['patients']]
    tests.append({'name':'원 고정24 표본','pass':actual==expected,'expected':expected,'actual':actual})
    tests.append({'name':'정정 분모72/73','pass':sum(f['v1_class']=='pos_def' for p in amend.values() for f in p['facts'])==72 and sum(f['v2_class']=='pos_def' for p in amend.values() for f in p['facts'])==73})
    tests.append({'name':'주장 연결 완전성','pass':len(jud)==96 and sum(map(len,jud.values()))==768})
    result={'passed':all(t['pass'] for t in tests),'tests':tests,'n_pass':sum(t['pass'] for t in tests),'n':len(tests),'source_sha256':sha(__file__)}
    write_new(OUT/'tests'/sys.argv[1],result)
    print(json.dumps(result,ensure_ascii=False,indent=1))
    assert result['passed']


if __name__=='__main__':main()
