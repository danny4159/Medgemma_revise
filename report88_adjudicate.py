"""점수 계산 전 고정한 재점검 수정. 원문 판정 파일은 보존한다."""
import copy
import json
import re
import shlex

import report87_eval as E
from report86_common import sha
from report86_view import blind_order
from report88_check import load_all, part_paths, provenance_checks
from report88_handoff import OUT, write_new

NOTES = {
0: '흉벽/유두 음영을 폐 정상으로 부정하지 않음. O5 가능 결절과 약화 정상의 내부 긴장 누락 보완. F2/F3 중복 민감도.',
10: '정상 폐/심종격 사실 연결 확인. O4 약화 정상/가능 음영 내부 긴장 보완. O8 방사선불투과 이물 부재를 유방 보형물 부재로 확장한 판정 수정.',
13: 'generic 정상에서 질환 음성을 만들지 않음. C-H 폐 영역별 내부 모순 근거 확인.',
17: '상동. relatively clear의 p 긴장과 C-H d 모순 분리 확인.',
20: '측만과 no acute bone은 양립 가능. 폐 가능 음영의 p 긴장 확인.',
25: 'dorsolumbar 대 thoracic 부분 위치/속성 일치 유지. 측만과 포괄 골 정상은 p 긴장만.',
32: 'apical tracts와 포괄 chronic은 같은 개념 확정 불가. 지역 hilar/폐 정상 범위 모호성 민감도에 포함. blunting과 effusion을 동치로 확대하지 않음.',
42: '좌하부 침윤 개념 회복과 left cardiac border strict 불일치 분리. 반복/비EOS는 원 기록 유지.',
43: 'generic 정상의 S는 포괄 문구에 한정. C-H 심비대/정상 및 양쪽 폐 음영 내부 모순 확인.',
53: 'small parapneumonic effusion에서 원인 속성 누락으로 strict 실패. O8 fluid 감별진단 대응은 모호 민감도. 약화 정상/가능 침윤 i 누락 보완.',
55: 'generic 정상 일관. C-H 지역 부정에서 임상 음성 gold를 만들지 않음.',
57: '심장 크기 정상은 심방 종괴 부재 아님: 같은 오류 전수 검색. 육아종 가능성과 명시 음영 문장은 분리.',
59: '석회화 육아종 U와 연부조직 결절 N 구분(A7). 영역 밖 음영을 reference 결절로 매칭하지 않음.',
61: 'generic 정상; 양쪽 폐 지역 음영과 clear의 d, 상대적 clear의 p 분리.',
62: '액와 음영에 clear lungs 적용 안 함. intense 대 mild는 attr c, moderate는 a 유지.',
64: 'generic 정상과 p 음영/clear 긴장 확인.',
65: '석회화 육아종 A7 전 조건 일관. subtle interstitial markings의 확정 질병 대응 불확실성을 민감도에 보존.',
67: 'diaphragm normal 대 lobulation만 N. well-defined는 정상 동치 아님. weak reference의 precision/모순 민감도.',
68: 'S 근거에 잘못 붙은 Disclaimer 제거. nf로 별도 보존.',
70: '확정 심비대와 projection 가능 원인 분리. probable old fracture와 lesion 대응/골 intact 범위는 민감도.',
71: 'generic 정상 반복은 집계 단순화 한계 기록. 약화 정상과 possible opacity의 p 확인.',
82: 'interstitial pattern 대 chronic pleuroparenchymal 개념 부분 대응은 모호 민감도. chronic/pleural 속성 누락 strict 실패.',
91: 'generic 정상과 C-H 좌우 폐 모순 확인. reference 미기재 이상은 U.',
95: '반복과 접속 목록의 단순화 유지. precision은 임상적 원자 사실 precision이 아님.'}


def blocks():
    out, patient, oid = {}, None, None
    for p in part_paths():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            if re.fullmatch('P[0-9]{3}', line):
                patient = line; out[patient] = {}; oid = None
            elif re.fullmatch('O[1-8]', line):
                oid = line; out[patient][oid] = []
            else: out[patient][oid].append(line)
    return out


def render(b):
    return '\n'.join(x for p, outputs in b.items() for x in [p, *[z for o, lines in outputs.items() for z in [o, *lines]]]) + '\n'


def main():
    rows, reads, amend, v1, initial = load_all()
    b = blocks(); before = copy.deepcopy(b); changes = []
    def change(p,o,lines,reason):
        if lines != b[p][o]:
            changes.append({'patient':p,'output':o,'reason':reason,'before':b[p][o], 'after':lines})
            b[p][o] = lines
    # 같은 오류의 모든 환자/조건을 검색한다. 심장 크기와 intracardiac mass는 양립 가능.
    for p, outputs in list(b.items()):
        for o, lines in list(outputs.items()):
            change(p,o,[l for l in lines if not(l.startswith('i ') and 'atrial mass' in l)],
                   '§4 같은 소견 조건: 정상 크기/윤곽이 심방 종괴 부재를 뜻하지 않음; 개별 주장 U는 유지')
    # 방사선불투과 이물 부재 -> 유방 보형물 부재, effusion 부재 -> blunting 부재는 성립하지 않음.
    for p,oid,fid in [('P010','O8','F1'),('P069','O3','F1')] + [('P076','O'+str(k),'F2') for k in (2,4,5,6,8)]:
        lines=[]
        for l in b[p][oid]:
            t=shlex.split(l)
            if t[:2]==['f',fid]:
                l=f'f {fid} U -- iter088 범위 수정: 해당 부재가 reference 소견 부재를 함의하지 않음'
            elif t[0]=='c' and t[1]=='C.pos' and fid in t[2].split(','):
                refs=[x for x in t[2].split(',') if x!=fid]
                l=l.replace('c C.pos '+t[2]+' ', ('c C.pos '+','.join(refs)+' ') if refs else 'c U - ',1)
            lines.append(l)
        change(p,oid,lines,'§2 정상/부재 범위의 비대칭 적용 오류 수정; 사실 회복 분모와 기준 유지')
    # 명백한 전사 오류와 누락된 불확정 내부 긴장.
    ls=[l.replace('||Disclaimer','') for l in b['P068']['O7']]+['nf "Disclaimer"']
    change('P068','O7',ls,'면책은 사실 근거가 아닌 nf (§3)')
    additions={('P000','O5'):'i p presence "The lungs appear generally clear" "a possible nodule in the right lung"',
               ('P010','O4'):'i p presence "The lungs appear relatively clear" "subtle opacities may be present"',
               ('P053','O8'):'i p presence "The lungs appear relatively clear" "There is a possible opacity in the left lower lung field"'}
    for (p,o),l in additions.items(): change(p,o,b[p][o]+[l],'§4 약화 정상과 가능 이상 간 긴장 누락')
    change('P094','O6',[l.replace('c S F1 -d "No acute cardiopulmonary process"','c U - -d "No acute cardiopulmonary process"') for l in b['P094']['O6']],
           'generic normal reference를 급성 질환 음성 정답으로 확장하지 않음; 다른 조건과 동일 적용')
    text=render(b)
    jud=E.parse_v3(text,rows,amend,reads,v1)
    errs,linked=provenance_checks(jud,reads)
    assert not errs,errs
    assert all(p['claim_ids'] for v in linked.values() for i in v['internal'] for p in i['parts'])
    out=OUT/'adjudication'
    out.mkdir(parents=True,exist_ok=True)
    with (out/'judgments_final.txt').open('x') as f: f.write(text)
    write_new(out/'changes.json',{'changes':changes,'n_output_edits':len(changes),'before_parts':{str(p):sha(p) for p in part_paths()},'after_sha256':sha(out/'judgments_final.txt')})
    write_new(out/'recheck24.json',{'indices':list(NOTES),'n_patients':24,'n_outputs':192,'notes':NOTES,
      'rater':'Codex 재점검: 원 판정 일부는 Claude, P082/P091/P095는 같은 Codex의 두 번째 검사. 독립 전문가 합의 아님.',
      'blinding':'O 순서 유지, 원문/현재 판정을 함께 검토하므로 독립 blind 재평가 아님; C-H 형식은 식별 가능.',
      'scope':'전체 raw text·reference·fact/claim/internal 연결을 확인; 전문 영상 재판독 아님',
      'remaining_ambiguity':'별도 sensitivity_spec; 이 검사가 임상적 정답을 확정하지 않음'})
    write_new(out/'linked.json',linked)
    write_new(out/'sensitivity_spec.json',{
      'locked_before_aggregation':True,
      'variants':['initial_annotations','merge_P000_F2_F3','exclude_weak_reference_support','include_weak_normal_contradictions','ambiguous_mapping_to_U','C-H_explicit_region_only','exclude_nonEOS'],
      'ambiguous_fact_pairs':[['P000','F3'],['P032','F1'],['P053','F3'],['P070','F1'],['P082','F1'],['P084','F1']],
      'ambiguous_scope':'유두/폐 결절, 포괄 chronic/국소 tract, fluid/pleural effusion, lesion/old fracture, interstitial/pleuroparenchymal, prosthesis/osteosynthesis; 모든8조건에 같은 보수적 U 적용',
      'C-H_explicit_region_only':'C-H의 모든 C.pos/C.neg와 내부 d를 제외하는 상한적 stress test. 정확한 대안 채점이 아닌 과도한 영역범위 연결에 대한 보수적 하한.',
      'precision_limit':'접속 목록 C>S>U와 포괄 정상의 단순화 및 source별 반복 때문에 임상 precision 아님. 서로 다른 정상/질환 표본 구성을 함께 보고.'})
    print(json.dumps({'patients':len(jud),'outputs':sum(map(len,jud.values())),'edits':len(changes),'rechecked':len(NOTES)},ensure_ascii=False))


if __name__=='__main__': main()
