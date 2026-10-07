"""고정 판정의 집계 및 사전에 정한 민감도. 새 생성은 수행하지 않는다."""
import copy
import json
import sys
from pathlib import Path
import numpy as np
import report87_eval as E
from report86_common import R86, sha
from report88_check import load_all, provenance_checks
from report88_handoff import OUT, write_new


def load_final():
    rows, reads, amend, v1, initial = load_all()
    p=OUT/'adjudication/judgments_final.txt'
    j=E.parse_v3(p.read_text(),rows,amend,reads,v1)
    errs,linked=provenance_checks(j,reads)
    assert not errs and all(p['claim_ids'] for v in linked.values() for i in v['internal'] for p in i['parts'])
    return rows,reads,amend,v1,initial,j


def change_to_u(j, img, fid):
    for o in j[img].values():
        if fid in o['facts']:
            o['facts'][fid]={'s':'U','loc':None,'attr':None,'span':None,'co':None,'why':'sensitivity'}
        for c in o['claims']:
            if fid in c['refs']:
                c['refs']=[x for x in c['refs'] if x!=fid]
                if not c['refs']: c['cls']='U'


def compact(r):
    return {k:v for k,v in r.items() if k!='per_output'}


def main():
    rows,reads,amend,v1,initial,j=load_final()
    spec=json.loads((OUT/'adjudication/sensitivity_spec.json').read_text())
    lockfiles=[OUT/'adjudication/judgments_final.txt',OUT/'adjudication/sensitivity_spec.json',Path(__file__).resolve(),Path(E.__file__).resolve()]
    write_new(OUT/'eval_lock.json',{'files':{str(p):sha(p) for p in lockfiles},'n_patients':96,'n_outputs':768,'new_gpu_requests':0})
    r=E.evaluate(j,rows,amend,reads)
    r['notes']={'contra_v2_noweak':'상속 필드: 실제로는 모든 normal_scoped 모순을 제외한다. weak-only 제외와 다르며 주지표로 쓰지 않는다.',
      'contra_v2':'상속 구현은 weak-only normal 모순을 제외한다. include_weak_normal_contradictions와 함께 해석.',
      'precision':'접속 목록 C>S>U 단순화의 참고값. 임상 precision/완전 원자 주장 평가 아님.'}
    write_new(OUT/'eval/report.json',r)
    write_new(OUT/'eval/judgments_structured.json',E.serialize_judgments(j))
    old=E.E1.evaluate('E96',(R86/'E96/judgments_E96_v2.txt').read_text())
    write_new(OUT/'eval/original_v1_recomputed.json',old)
    sens={'initial_annotations':compact(E.evaluate(initial,rows,amend,reads))}
    # 가능한 중복의 OR 병합. 분모는 양쪽 규약에서 하나 줄인다.
    jj=copy.deepcopy(j); aa=copy.deepcopy(amend); img=rows[0]['ImageID']
    aa[img]['facts']=[f for f in aa[img]['facts'] if f['fact_id']!='F3']
    for o in jj[img].values():
        f2,f3=o['facts']['F2'],o['facts'].pop('F3')
        rank={'D':4,'P':3,'N':2,'n':1,'U':0}
        if rank[f3['s']]>rank[f2['s']]: o['facts']['F2']=f3
        for c in o['claims']: c['refs']=list(dict.fromkeys('F2' if f=='F3' else f for f in c['refs']))
    sens['merge_P000_F2_F3']=compact(E.evaluate(jj,rows,aa,reads))
    jj=copy.deepcopy(j)
    for n,fid in spec['ambiguous_fact_pairs']: change_to_u(jj,rows[int(n[1:])]['ImageID'],fid)
    sens['ambiguous_mapping_to_U']=compact(E.evaluate(jj,rows,amend,reads))
    jj=copy.deepcopy(j)
    for img,cs in jj.items():
        facts={f['fact_id']:f for f in amend[img]['facts']}
        for o in cs.values():
            for c in o['claims']:
                if c['cls']=='S' and c['refs'] and all(facts[f]['weak'] for f in c['refs']): c['cls']='U'
    sens['exclude_weak_reference_support']=compact(E.evaluate(jj,rows,amend,reads))
    aa=copy.deepcopy(amend)
    for p in aa.values():
        for f in p['facts']: f['weak']=False
    sens['include_weak_normal_contradictions']=compact(E.evaluate(j,rows,aa,reads))
    # 保守的 stress bound; clinically correct alternate labels と混同しない。
    jj=copy.deepcopy(j)
    for img,cs in jj.items():
        o=cs['C-H']
        for fid,f in list(o['facts'].items()):
            if f['s'] in ('N','n'): o['facts'][fid]={'s':'U','loc':None,'attr':None,'span':None,'co':None,'why':'scope stress'}
            elif f['co']: f['co']=None
        for c in o['claims']:
            if c['cls'] in ('C.pos','C.neg'): c['cls']='U'
        o['internal']=[]
    sens['C-H_explicit_region_only']=compact(E.evaluate(jj,rows,amend,reads))
    # 非EOS 환자는 모든 조건에서 함께 제외한다(조건별 유리한 표본 선택 금지).
    keep=[x for x in j if all(all(reads[x,c]['final_eos']) for c in E.CONDS)]
    sens['exclude_nonEOS']=compact(E.evaluate({x:j[x] for x in keep},rows,amend,reads))
    write_new(OUT/'eval/sensitivity.json',sens)
    deltas=[]
    for img,cs in j.items():
        for c,o in cs.items():
            for f,x in o['facts'].items():
                oldf=v1[img][c]['facts'][f]
                if oldf['s']!=x['s'] or (x['s'] in 'DP' and oldf['loc']!=x['loc']):
                    deltas.append({'ImageID':img,'condition':c,'fact':f,'v1':oldf,'v2':x})
    write_new(OUT/'eval/v1_change_log.json',{'facts':deltas,'note':'위치 코드 체계 변경 자체도 포함. v1/v2 strict 정의는 동일하지 않음.'})
    result={}
    for k,v in r['comparisons']['abnormal'].items():
        rec=v['recall_def_v2']; con=v['contra_v2']
        result[k]={'recall':rec,'strict':v['recall_strict_v2'],'contradiction':con,
          'point_threshold_met':rec['diff']>=.10 and con['diff']<=.05,
          'ci_supports_both':rec['ci95'][0]>=.10 and con['ci95'][1]<=.05,
          'interpretation':'개발 자료의 조건 비교; 방법 효과/외부 일반화/신규성 입증 아님'}
    write_new(OUT/'eval/decision_inputs.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=1))


if __name__=='__main__': main()
