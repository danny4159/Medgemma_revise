# Work Performed

## 요약

- **핵심 결과:** 새 GPU 요청 없이 iter_095 E32 저장 출력 544건의 의미 판정을 다시 만들었다. 급성 부정, 원인 hedge, 정상 폐 실질 표현, lobe/zone, 시간 표현을 분리한 결과, 원 계획의 확대 분기 (a)(b)(c)는 모두 primary 조건에서 미충족이다.
- **근거:** 확정 충돌 환자는 Locate L8 20/32, Describe D8 25/32이다(iter_095는 10/32, 14/32). 세부 영역의 추가 회복(strict)은 1명이고, 이 1명도 원인 표현에 기댄 인정이다. 산술 검증 90/90, fixture 22/22가 통과했다.
- **주의:** (a)는 lobe–zone 대응 인정 여부에 따라 3명으로 바뀌므로 해부 선택에 의존하는 불확정이다. 이번 판정은 assistant가 이미 출력을 본 상태에서 한 것이다. 전문의 검토도, 독립 눈가림도 아니다.
- **다음:** 현재 CURE 폐 영역 회복 후보는 보류를 권고한다. 이는 위치 학습 연구 질문 전체의 기각이 아니다.

## 수행한 작업

- **기준 확인:** iter_095 plan.md의 SHA256이 계획에 적힌 값과 일치했다. HEAD `aaaf9c0`, 작업 트리는 깨끗했다.
- **입력 잠금** (`report96_lock.py`)
  - 환자 32명 × 17출력 = 544건(G 32, L 256, D 256)의 요청 ID·조건·영역·record digest를 확인했다. 중복과 누락은 없다.
  - 비EOS는 환자 7의 Locate left lung 1건이다. 같은 문장을 반복해 4096 token을 채운 출력이다. 원출력을 유지했고, 이 출력을 뺀 민감도도 계산했다.
  - 결정 관련 집합 28명(양성 reference 9명 + 이전 회복/충돌 환자)을 재판정 전에 고정했다. 나머지 4명(환자 9·10·15·23)은 SHA256(`iter096-audit95017|ImageID`) 규칙으로 전원 audit했다.
- **의미 규약** (`report96_sem.py`)
  - 소견 존재(definite/hedged), 원인(hedged/probable/concern), 시간(new/unchanged/again/still/resolved), 부정 종류(specific/clear/qualified), 범위(측면·level·lobe/zone/lung)를 필드로 나눴다.
  - 급성 수식 부정과 "clear condensations"는 qualified로 분류해 확정 충돌에서 뺐다.
  - "The lungs are clear", "parenchyma normal" 같은 정상 폐 표현은 clear 부정으로 기록했다.
  - 번들 안에서 반복된 동일 주장은 첫 번째만 세고 `dup_claims`로 남겼다.
- **문장 단위 검토:** 고유 문장 198개 중 143개가 claim을 갖는다. 나머지 55개는 효과·혈관·심비대·전반 정상 같은 비폐실질 문장이다. 검토 중 규칙 오류 5건을 고쳤다.
  - clear 판정이 neg 분기에 가려진 순서 문제
  - 빈 문장 처리
  - "in comparison"을 new로 분류한 오류
  - nodule 정규식
  - 시간 모순 규칙에서 'increase' 대 'new'를 모순으로 본 것
  - 문장 단위 override는 2개이며 이유를 `OVERRIDES`에 남겼다.
- **평가·검증**
  - `report96_ref.py`는 reference 10사실과 음성 reference 8명을 수동 인코딩했다.
  - `report96_eval.py`는 report95_eval 함수를 호출하지 않고 집계한다.
  - `report96_verify.py`는 셀 집합 기반의 별도 산술이다. 원본 `outputs.jsonl`에서 텍스트를 다시 읽어 모든 quote의 start/end와 text sha를 대조한다. 기존 상수 True 검사를 대체했다.
  - `report96_diff.py`, `report96_review.py`, `report96_decide.py`, `report96_seal.py`는 각각 환자별 차이 추적, 환자별 검토 기록, 원 기준 판정, 산출물 봉인을 맡는다.
- 규칙 초안과 산출물은 v1~v3으로 이력을 남겼다. 최종은 judgments v3, report v3b이다.

# Files Changed

신규 소스 (모두 `research/`, 기존 파일 수정 없음):

- `report96_sem.py`, `report96_ref.py`, `report96_lock.py`, `report96_eval.py`
- `report96_verify.py`, `report96_diff.py`, `report96_review.py`, `report96_decide.py`, `report96_seal.py`
- `test_report96.py`

신규 결과:

- `results/iter_096/lock/input_manifest.json`
- `results/iter_096/judging/` — `judgments_E32_{v1,v2,v3}.json`, `sentence_review_{v1,v2,v3}.json`, `case_review_E32_v3.json`, `outputs_view_E32*.txt`
- `results/iter_096/eval/` — `report_E32_*`, `verify_E32_*`, `correction_diff_E32_v3b.json`, `decision_E32_v3b.json`
- `results/iter_096/tests/fixtures_report96_{a,b,c}.json`
- `results/iter_096/completion_v3b.json`

개발 중간 파일은 삭제하지 않았다.

- `judgments_E32.json`: 첫 draft
- `report_E32_v3excl_nonEOS.json`: 변수 shadowing으로 이름이 잘못 붙은 v3 산출물(내용은 v3와 동일하며 최종 아님)
- `verify_E32_v2.json`: manifest self-sha 검사 오류로 FAIL이 기록된 첫 검증. 고친 뒤 `_r2`에서 통과했다.

# Commands / Experiments

모두 성공했다. GPU 요청은 없고(0), 모두 CPU 작업이다.

- `python report96_lock.py` — 544건 연결, 비EOS 1건
- `python report96_eval.py judge v1|v2|v3`, `eval v3 b`
- `python report96_verify.py v3 b` — 90/90 PASS
- `python test_report96.py fixtures_report96_c.json` — 22/22 PASS
- `python report96_diff.py v3 b`, `report96_review.py v3`, `report96_decide.py v3 b`, `report96_seal.py v3 b fixtures_report96_c.json`

실행 실패와 수정 이력:

- 한 번의 verify FAIL은 코드 오류였고 고쳤다.
- 한 번의 보고서 이름 오류는 변수 shadowing 때문이었다.
- 샌드박스가 따옴표 포함 f-string heredoc을 막아 파일 스크립트로 바꿨다.

Wall-clock은 판정표 생성·평가·검증 각각 수 초~수십 초 수준이다(정밀 측정은 하지 않음).

# Results

원 결과: `results/iter_096/eval/report_E32_v3b.json`, `decision_E32_v3b.json`. 수치는 모두 E32 개발 자료(32명, 양성 reference 9명·10사실) 기준이다.

**확정 충돌 환자 수** (같은 번들 안, 긍정 소견 vs 겹치는 범위의 정상/부정 서술)

| 번들 | iter_095 | primary | 복수 "lungs"를 질문 영역으로 좁힘 | lobe=zone 인정 | iter_095식 하한(원인 hedge 양성 제외) |
|---|---|---|---|---|---|
| L8 | 10 | 20 | 19 | 21 | 9 |
| D8 | 14 | 25 | 23 | 25 | 15 |
| CG, L2, D2 | 0 | 0 | 0 | 0 | 0 |
| L6, D6 | — | 1 | 1 | 3 | 1 |

- D8−L8 = +0.156 (95% CI [−0.031, 0.344]). 하한 변형에서는 +0.1875 [0.0, 0.375]이다. 어느 변형에서도 Describe가 Locate보다 충돌을 줄이지 않았다.
- 차이의 주원인: 원인 hedge가 붙은 문장을 존재 불확실로 읽던 iter_095 규칙을 정정한 것(신규 충돌 23쌍). 정상 폐 표현 누락 정정이 1쌍이다.
- 급성 부정을 확정 충돌에서 뺀 것이 L8 환자 4·18의 구 충돌을 제거했다.
- 환자 4의 기타 1쌍은 lobe 양성 vs zone 부정의 같은 level 대응을 불확실로 분류해 제외한 것이다.
- 충돌은 거의 전부 광역 출력("lungs/right lung is clear")과 세부 영역 출력의 opacity 사이에서 생긴다. 세부 영역끼리만(L6/D6) 보면 1명이다.
- 한 번들 안에서 회복한 사실이 직접 부정된 경우는 L8 환자 1(P001 F1) 1건이다.

**회복** (양성 reference 10사실)

| 번들 | strict | lenient(시간 일치) |
|---|---|---|
| CG | 0 | 2 |
| L2, D2 | 각 1 (환자 2의 지속 atelectasis, 광역 출력이 이미 회복) | 각 1 |
| L8, D8, L6, D6 | 각 2 | 5~6 |

- 세부 영역이 CG ∪ 같은 형식 광역 영역을 넘어 추가로 회복한 환자는 strict 1명(환자 1)이다. lenient는 5명(0, 1, 4, 5, 6)이다. 이 5명은 일반 opacity 대 infiltrate/consolidation이거나 lobe–zone 불확실 대응이다.
- strict 1명은 "consistent with pneumonia"의 원인 지원으로 opacity를 infiltrate로 인정한 것이다. 원인 지원을 빼면 0명이다.
- lobe=zone을 인정하면 3명(1, 4, 5)이다.

**원 계획 기준별 판정**

| 기준 | 판정 |
|---|---|
| (a) 세부 영역이 광역이 놓친 명확한 소견을 ≥2명에서 회복 | **미충족** (strict 1명). 해부/원인 인정 민감도에 따라 3명까지 바뀌므로 **불확정** |
| (b) 회복을 보존하며 충돌을 줄임 (≥2명) | **미충족** (최대 1명) |
| (c) 사건은 적지만 남은 reference에 판단 기회 | **미충족** (E64 양성·명시적 부재 기회 0) |
| 최소 pilot 양성 (추가 회복 ≥3, 충돌 ≥5, 모호 제외·한 명 제거 후 유지) | **미충족**. 충돌 ≥5는 D8 25명으로 충족하지만 D6 단독은 1명이다 |
| E96 운영 기준 (회복 손실 ≤1명, 충돌 감소 ≥5) | **미평가** (E96 비실행). E32만으로 선언하지 않음 |

(b)의 이 계산은 "L8의 추가 회복을 A도 회복하면서, L8에는 충돌이 있고 A에는 없는 환자"를 센 것이다. 계획 문장의 해석이므로 판단 범위에 포함한다.

**오류 비용** (D8 / L8)

- 양성 주장 94 / 74건 중 reference에 매칭된 것은 23 / 19건이다.
- 시간 주장 41 / 36건 중 reference가 뒷받침한 것은 6 / 6건, 모순은 5 / 3건이다.
- 원인 제시 주장 66 / 48건 중 reference 지지가 없는 것은 64 / 46건이다.
- 음성 reference 8명에서 직접 모순은 0건이다. opacity는 reference의 qualified 부정에만 걸렸다.

**검증**

- 산술 90/90: manifest hash, request ID 544 유일, record digest, 모든 quote의 offset 일치, 충돌·회복·bootstrap 별도 재계산
- fixture 22/22: P001/P004/P005/P018 실제 문장, 반대 예제, offset·quote·text hash 변조 거부

# Goal Progress / Reused Assets

**목표 진전**

- **시험 설정:** CURE 폐 영역 8영역 회복 후보는 추가 회복이 작고 해부 대응에 의존한다. 이 설정의 투자는 보류를 권고한다.
- **연구 관찰(유지):** 광역 "lungs/right lung is clear"와 세부 영역의 opacity 서술이 같은 환자에서 자주 공존한다(L8 20/32, D8 25/32). 수정한 의미 규칙에서도 확인된다.
  - 이 중 상당수는 원인 hedge 문장을 존재 확정으로 읽은 결과이므로, hedge를 존재 불확실로 읽는 하한(9/15)과 함께 해석해야 한다.
- **연구 질문:** 위치 학습이 판독 정확성에 더하는 가치는 이번 결과로 판단할 수 없다. 이번 결과는 한 공개 checkpoint의 한 인터페이스와 작은 개발 자료에 대한 것이다.

**미검증:** 독립 의미 검증(전문의, 다른 평가자), lobe–zone 대응의 독립 근거, 양성 reference가 더 많은 자료, 어느 쪽 서술(광역 정상 vs 세부 opacity)이 맞는지의 판정.

**재사용**

- `report95_view.outputs_for`, `report95_common`, `report86_common`(hash·저장·digest)을 호출했다.
- `report95_eval` 함수는 비교용 읽기 전용으로만 호출했다.
- `reuse_assets`는 비어 있어 반입은 없었다. 위 모듈은 모두 needs_fix 상태였고 그 결함을 이번 경로에서 수정하지 않았다. 일반 재사용 승인은 하지 않는다.

# Problems

**현재 결론 무효: 없음.** 단, 위 한계를 전제로 한다.

**재사용 전 수정**

- `report96_sem.py`는 이 E32 문장 198개에 맞춘 규칙 기반이다. 새 자료의 범용 의미 평가기가 아니다.
- 이 의미 판정은 assistant가 한 것이고, 이미 E96 일부를 본 평가자이다. 영역 이름은 가려지지 않는다. 조건명(G/L/D)만 O-id로 가렸다.
- 환자별 검토는 결정 관련 28명과 audit 4명 모두 원문을 읽고 `case_review_E32_v3.json`에 notes를 남겼다. 그러나 `case_review`에 메모가 있는 환자는 0–8·9·10·15·23뿐이다. 나머지 21명은 claim 목록만 있고 개별 메모가 없다. 이들은 고유 문장 표 검토로 커버했다.
- 재판정 후 새로 결정 관련이 된 환자는 10, 15다. 둘 다 이미 audit 집합에 있어 교체하지 않았다.
- 이 정정 판정은 iter_095 판정을 대체하지 않는다. 별도 결과 경로에 병기한다.

**추후 개선**

- 위치 reference에 박스 좌표가 있으면 lobe–zone 대응을 독립 근거로 확정할 수 있다.
- report95_gen / report95_launch의 resume·메모리 예약 결함은 CPU 분석이라 이번에 쓰지 않았고 수정하지 않았다. GPU 재사용 전에 해결해야 한다.
- 보고서에 쓴 (b) 기준 계산 방식은 계획 문장의 한 해석이다.

# Recommendation to GPT

1. **현재 시험 설정은 보류:** 현재 CURE 폐 영역 회복 후보(8영역 Describe/Locate)는 보류를 권고한다. 근거는 (a)(b)(c) 미충족, (a)의 해부 선택 의존, 세부 영역 추가 회복 strict 1명이다. E64 확대는 reference 기회가 없어 판단을 바꾸지 못한다.
2. **연구 관찰은 유지:** 광역 정상 서술과 세부 opacity 서술의 불일치(수정 규칙에서도 20~25/32, 하한 9~15/32)는 제한된 관찰이다. 이 불일치의 어느 쪽이 맞는지는 미판정이다. "위치 학습 무용"이나 "CURE 재현 실패"로 확대하지 않는다.
3. **연구 질문은 미판정:** 재개 조건은 lobe–zone 대응을 좌표로 확정할 수 있고, 양성 reference가 더 많은 자료(예: 박스가 있는 PadChest-GR 전체)에서 독립 의미 검증을 하는 것이다. 같은 E32의 규칙 조정은 하지 않는다.
4. **다음 후보:** 지금 세션에서 새 실험을 만들지는 않았다. 박스 기반 대응 확정은 CPU 분석이라 비용이 낮다. 다음 투자는 그 분석 / 중요한 다른 잔여 질문 / 범위를 명시한 보류 중 하나로 결정해 주기 바란다.

SELF_CHECK: FAIL
SUMMARY: E32 저장 출력 544건의 의미 판정을 정정해 확정 충돌 L8 20/32·D8 25/32(iter_095 10/14)를 얻었으나 세부 영역 추가 회복은 strict 1명(lobe–zone 해석에 따라 최대 3명)뿐이라 확대 분기 (a)(b)(c) 모두 미충족이므로 현재 CURE 폐 영역 후보 보류를 권고한다. 판정은 assistant 단독이며 독립 의미 검증과 일부 환자 메모는 미완이라 FAIL로 표시한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd results/iter_095; python -c "
import json
r=json.load(open('lock/reference_target.json'));s=json.load(open('lock/selection.json'))
print(s.keys(),len(s['E32']))
for i,img in enumerate(s['E32']):
    x=r[img];print(i,img,x['layer'],[ (f['fact_id'],f['sentence']) for f in x['pos_facts']],[(f['class'],f['sentence']) for f in x['neg_facts']])
"; wc -l judging/*.txt; head -c 1500 eval/report_E32_v2.json; ls ../../../agent/runs/iter_095/ | head -30
- Bash: python - <<'EOF'
import json
r=json.load(open('results/iter_096/eval/report_E32_v1.json'))
for b,d in r['bundles'].items():
    print(b,d['conflict_patients'],d['pair_status_patients'],d['cause_conflict_patients_pneumonia'])
for lv in ['strict','strict_ti','lenient','lenient_timeok']:
    print(lv,{b:r['bundles'][b]['facts_recovered_'+lv] for b in r['bundles']})
EOF
- Bash: python - <<'EOF'
import json
r=json.load(open('results/iter_096/eval/report_E32_v1.json'))
J=json.load(open('results/iter_096/judging/judgments_E32_v1.json'))
idx={}
for o in J['outputs']:
    for si,s in enumerate(o['sentences']):
        for ci,c in enumerate(s['claims']):
            idx[f"{o['p']}:{o['oid']}:{si}:{ci}"]=(o['cond'],o['region'],s['quote'][:70],c['kind'])
for b in ['CG','L2','D2','L6','D6']:
    print('==',b)
    for p,fs in r['cases'][b]['recoveries'].items():
        for f,dd in fs.items():
            print(p,f,{k:[idx[c][1]+'|'+idx[c][2] for c in v][:3] for k,v in dd.items()})
d=r['detail']['main']
for lv in ['strict','lenient_timeok']:
    print(lv,{k:(v['patients'],v['facts']) if isinstance(v,dict) else v for k,v in d[lv].items()})
print(r['patient_table'])
print(r['leave_one_patient_out'])
EOF
- Bash: sed -i "s/if k != 'rows'}))/if k not in ('rows', 'sha256')}))/" report96_verify.py && grep -n "'rows', 'sha256'" report96_verify.py && python - <<'EOF'
import os
os.remove('results/iter_096/eval/verify_E32_v2.json') if False else None
EOF
ls results/iter_096/eval
- Bash: cat > /tmp/ignore_marker 2>/dev/null; python - <<'EOF'
import json, time
import report95_eval as E95, report96_eval as E
from report86_common import save
from report96_lock import R96
J=json.load(open(str(R96)+'/judging/judgments_E32_v3.json'))
claims, outs_text, _ = E95.load_judgments(['E32'])
B=E95.bundle_outputs(outs_text)
cl=E.flat_claims(J)
sel=json.load(open('results/iter_095/lock/selection.json'))['E32']
old_rep=json.load(open('results/iter_095/eval/report_E32_v2.json'))
res={}
for b in E.BUNDLES:
    old=E95.conflicts(claims,B[b],mode='question')
    oldp={sel.index(i) for i,v in old.items() if v}
    assert len(oldp)==old_rep['bundles'][b]['conflict_patients']['primary'], (b,len(oldp))
    newc=E.conflicts(cl,b,'primary')
    new=set(newc)
    ent={'old_patients':sorted(oldp),'new_patients':sorted(new),'new_only':{}, 'old_only':{}}
    for p in sorted(new-oldp):
        reasons=set()
        for pos,neg,st in newc[p]:
            oc=claims.get((sel[p],pos['oid']),[]); on=claims.get((sel[p],neg['oid']),[])
            if any(c['pol']=='Pu' for c in oc): reasons.add('원인 hedge가 있는 문장 전체를 존재 불확실(Pu)로 처리했던 규칙 -> 존재 확정으로 정정')
            elif not on: reasons.add('정상 폐 실질 표현을 iter_095가 부정으로 기록하지 않음 -> 정정')
            else: reasons.add('기타(범위·종류 규칙 변경)')
        ent['new_only'][str(p)]=sorted(reasons)
    for p in sorted(oldp-new):
        reasons=set()
        for pr in old[sel[p]]:
            # pr = (pos oid, neg oid)
            nn=[c for c in claims.get((sel[p],pr[1]),[]) if c['pol']=='N']
            txt=' '.join(c['quote'] for c in nn)
            reasons.add('급성(acute) 수식 부정을 소견 부정으로 처리했던 규칙 -> 확정 충돌에서 제외(qualified)' if 'acute' in txt.lower() else '기타')
        ent['old_only'][str(p)]=sorted(reasons)
    res[b]=ent
save(R96/'eval/correction_diff_E32_v3.json',{'note':'iter_095 판정(report95_eval 함수, 읽기 전용 호출)과 iter_096 v3 판정의 primary 충돌 환자 비교. 사유는 환자 쌍의 원 판정 필드로 자동 분류한 것이며 단일 원인 귀속이 아니다.','bundles':res})
for b in ('L8','D8'): print(b,len(res[b]['old_patients']),len(res[b]['new_patients']),{k:v for k,v in res[b]['old_only'].items()}, len(res[b]['new_only']))
from collections import Counter
print(Counter(r for b in ('L8','D8') for v in res[b]['new_only'].values() for r in v))
EOF
