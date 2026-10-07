"""고정 민감도 변환을 별도로 구성해 모든 paired 수치를 재검산한다."""
import copy
import json
from pathlib import Path
from report88_verify import OUT, ROOT, parse, calculate, compare, order
from report86_common import STAGES, sha
from report88_handoff import write_new


def main():
    rows=json.loads(STAGES['E96']['inputs'].read_text())
    a=json.loads((ROOT/'results/iter_087/reference_amend_E96.json').read_text())['patients']
    s=json.loads((OUT/'eval/judgments_structured.json').read_text())
    j=parse((OUT/'adjudication/judgments_final.txt').read_text(),rows,s)
    reports=json.loads((OUT/'eval/sensitivity.json').read_text());counts={}
    spec=json.loads((OUT/'adjudication/sensitivity_spec.json').read_text())
    reads=[json.loads(l) for l in (ROOT/'results/iter_086/E96/readings.jsonl').read_text().splitlines()]
    bad={x['ImageID'] for x in reads if not all(x['final_eos'])}
    for variant in ['merge_P000_F2_F3','ambiguous_mapping_to_U','exclude_weak_reference_support','include_weak_normal_contradictions','C-H_explicit_region_only','exclude_nonEOS']:
        jj=copy.deepcopy(j);aa=copy.deepcopy(a);rr=rows
        if variant=='merge_P000_F2_F3':
            img=rows[0]['ImageID'];aa[img]['facts']=[f for f in aa[img]['facts'] if f['fact_id']!='F3']
            for (i,c),o in jj.items():
                if i!=img:continue
                f=o['facts'];rank={'D':4,'P':3,'N':2,'n':1,'U':0}; x=f.pop('F3')
                if rank[x['s']]>rank[f['F2']['s']]:f['F2']=x
                o['claims']=[(k,list(dict.fromkeys('F2' if z=='F3' else z for z in refs)),pc,n) for k,refs,pc,n in o['claims']]
        elif variant=='ambiguous_mapping_to_U':
            for pid,fid in spec['ambiguous_fact_pairs']:
                img=rows[int(pid[1:])]['ImageID']
                for (i,c),o in jj.items():
                    if i!=img:continue
                    o['facts'][fid]={'s':'U','loc':None,'attr':None}
                    cs=[]
                    for k,refs,pc,n in o['claims']:
                        if fid in refs:
                            refs=[z for z in refs if z!=fid]
                            if not refs:k='U'
                        cs.append((k,refs,pc,n))
                    o['claims']=cs
        elif variant=='exclude_weak_reference_support':
            for (i,c),o in jj.items():
                fs={f['fact_id']:f for f in aa[i]['facts']}
                o['claims']=[('U' if k=='S' and refs and all(fs[z]['weak'] for z in refs) else k,refs,pc,n) for k,refs,pc,n in o['claims']]
        elif variant=='include_weak_normal_contradictions':
            for p in aa.values():
                for f in p['facts']:f['weak']=False
        elif variant=='C-H_explicit_region_only':
            for (i,c),o in jj.items():
                if c!='C-H':continue
                for f in o['facts'].values():
                    if f['s'] in ('N','n'):f.update(s='U',loc=None,attr=None)
                o['claims']=[('U' if k in ('C.pos','C.neg') else k,refs,pc,n) for k,refs,pc,n in o['claims']]
                o['internal']=[]
        else:
            rr=[r for r in rows if r['ImageID'] not in bad]
            jj={k:v for k,v in jj.items() if k[0] not in bad}
        flat={key:calculate(o,{f['fact_id']:f for f in aa[key[0]]['facts']})[0] for key,o in jj.items()}
        counts[variant]=compare(flat,reports[variant],rr,list(next(iter(flat.values()))))
    write_new(OUT/'verify/sensitivity.json',{'passed':True,'checks_by_variant':counts,'files':{str(p):sha(p) for p in [OUT/'eval/sensitivity.json',OUT/'adjudication/sensitivity_spec.json',Path(__file__),ROOT/'report88_verify.py']},
      'note':'초기 판정 비교는 원본 보존용으로 별도 저장. 이 검사는 최종 판정에 대한 사전 고정 6개 변환의 수치·CI를 검증한다.'})
    print(counts)


if __name__=='__main__':main()
