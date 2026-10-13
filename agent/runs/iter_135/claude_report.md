# 요약

- **핵심**: 이번 반복은 준비 확인뿐이라 유효 실험이 아니다. 결정은 RadGenome–BraTS FLAIR의 고정 존재 설계를 보류하는 것이다. 후속 GPU 비교는 제안하지 않는다.
- **근거**: 공식 mapping 파일(`syn51615438`)은 읽을 수 없고(HTTP 403) 이용 근거도 확인하지 못했다. 한편 MedGemma의 thought 표식은 NONE 출력에만 있었다.
- **주의**: 이 판단은 이 설계에만 해당하며 MRI 관측·통합 질문 전체의 기각이 아니다. final 상태는 점수화하지 않았다.
- **다음**: Synapse 접근을 얻거나, 내부 개발용으로만 쓴다는 선언이 있으면 재개한다. 그 뒤에야 계약 초안 한 개(근거 뒤 최종 범주 출력)를 검토한다.

# Work Performed

- 기준 계획 `agent/runs/iter_134/plan.md`와 iter_134 결과 235개 파일의 SHA256을 기록했다. 감사 전후가 같아 원 결과·review는 바뀌지 않았다.
- **자료 증거표**: 기술 4명과 평가 32명 총 36 case를 대상으로 다음을 확인했다.
  - HF 미러와 RadGenome의 revision, license 문자열, README 해시
  - RadGenome split과 report key 연결
  - Synapse 공개 metadata와 접근 요건
- **출력 구조 감사**: 저장 출력 360건(main 320 + technical `Tb_w2` 40)을 봤다. 로컬 tokenizer로 token 100(`<unused94>`)과 101(`<unused95>`)을 확인했고, 이 id 위치로 thought/final 경계를 찾았다. 문자열 삭제나 상태 단어 검색은 쓰지 않았다.
- **불일치 후보**: 기존 `i134_spec.audit` 정규식으로 첫 줄과 설명의 불일치 후보를 추출했다. 후보일 뿐이며 임상 정답 여부는 판정하지 않았다.

# Files Changed

- 코드: `i135_audit.py`, `i135_report.py` (신규)
- 결과(`results/iter_135/`):
  - `data_evidence.json`, `output_structure_audit.json`, `contradiction_candidates.json`
  - `baseline_hashes_before.json`, `invariance.json`, `followup_feasibility.json`
  - `data_evidence/official/`(README와 작은 json)
- 기존 파일은 수정하지 않았다.

# Commands / Experiments

- `python i135_audit.py`: 성공. `ok 235 files unchanged; candidates 49`
- `python i135_report.py`: 성공. 집계 출력만 한다.
- 소량 다운로드 4건과 Synapse 공개 REST 조회 5건은 성공했다. mapping 파일 download 조회 1건만 403으로 실패했고 우회하지 않았다.
- GPU 사용 0, 신규 생성 0, MRI 다운로드 0. 실측 wall은 해시 0.42초, 자료 증거 4.15초, 구조 감사 0.02초다.

# Results

- **연결**: 36/36 case가 RadGenome modal-wise `t2f` report key를 가진다. 모두 RadGenome `train` split이다. HF 미러에도 `t2f`와 `seg` 파일이 36/36 있다.
- **이용 근거**:
  - HF 미러(`b032d353`)는 비공식이다. 카드는 cc-by-4.0이고 BraTS data-use 인증 문구는 없다.
  - RadGenome(`0348ba42`) README는 `license: mit` 한 줄뿐이다.
  - Synapse 프로젝트의 accessRequirement 목록은 비어 있다.
  - mapping 파일은 항목은 존재하지만 내용 조회가 403이다(unmet access requirements). 인증정보가 없어 우회하지 않았다.
- **MSD 관계와 환자 독립성**: 미확인이다. MSD는 익명 ID라 mapping이 있어도 연결 다리가 없다. 36 case 안에 같은 5자리 prefix 중복은 없다. 다만 7개 case는 같은 prefix의 다른 scan ID가 미러에 있다.
- **thought 표식**:
  - NONE에서만 나타났다(main 32/32, technical 4/4). 순서 위반은 없고 final은 모두 추출된다.
  - 36건 final의 첫 줄은 모두 UNKNOWN이다. NONE의 strict 유효 0/36은 thought 앞머리 때문이다.
  - 영상 조건 출력 324건에는 표식이 없다. 영상 조건 중 main 10/288건은 표식 없이도 strict-invalid라 이 경계로 설명되지 않는다.
  - 360건 전부 EOS로 종료했다.
- **모순 후보 49건**: 17명 환자의 main 출력이다. 모두 첫 줄이 PRESENT인데 설명은 병변 부재를 말한다. 전부 종양 annotation 0인 slice 조건에서 나왔다(N1 10, N2 10, N1N1 11, N1N2 8, N2N1 10). P·PP·PN1·N1P에는 없다.

# Goal Progress / Reused Assets

- **진전**: NONE의 형식 실패는 영상 없이 병변을 단정한 것이 아니라 출력 경계 문제로 분리됐다. 영상 조건의 첫 줄·설명 불일치는 경계로 해소되지 않는다는 점도 구조적으로 확인했다.
- **미검증**:
  - 이용 근거와 개별 release의 byte 동등성
  - MSD·사전학습 독립성
  - 설명문의 임상적 정답 여부
  - 응답 순서 변경의 효과
- **재사용**: `i134_spec.py`의 `parse`와 `audit`을 읽기 용도로만 호출했다. `reuse_assets`는 비어 있었다.

# Problems

- **현재 결론 무효**: 없음. 준비 단계라 유효 실험을 주장하지 않는다.
- **재개 전 필요**: 공식 mapping 접근 또는 이용 선언. 사용자 개입이 필요한 권한은 이것 하나다.
- **추후 개선**: 불일치 후보는 정규식이라 부정 범위가 모호하다.

# Recommendation to GPT

현재 고정 존재 설계에는 더 투자하지 않는 것을 권한다. 재개 조건은 `followup_feasibility.json`에 적었다. 다음 후보는 두 가지다.

- **다른 질문으로 옮기기**: 공개 정답이 있는 병변 속성 질문이나 다른 slice 통합 과제를 택한다. 이용 근거가 이미 확인된 자료를 쓴다.
- **접근이 열릴 때까지 보류**: Synapse 접근 또는 이용 선언이 생기면 근거 뒤 최종 범주 출력 diagnostic 한 개만 검토한다.

SELF_CHECK: PASS
SUMMARY: RadGenome–BraTS FLAIR 존재 설계는 mapping 403·이용 근거·MSD 독립성 미확인으로 보류. thought 표식은 NONE에만 있어 NONE 형식 실패는 경계 문제로 분리되나, 영상 조건의 첫 줄·설명 불일치 후보 49건은 남음. 신규 GPU 0.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
import json
e=json.load(open('results/iter_135/data_evidence.json'))
print({k:e[k] for k in ('n_cases','n_technical','n_main')})
print(json.dumps(e['linkage'],ensure_ascii=False,indent=1)[:2500])
print(e['mirror']['revision'],e['radgenome']['revision'])
a=json.load(open('results/iter_135/output_structure_audit.json'))
for j in a: 
    print(j,a[j]['n'],a[j]['totals'])
    for c,v in a[j]['by_condition'].items(): print(' ',c,v)
c=json.load(open('results/iter_135/contradiction_candidates.json'));
import collections;print(collections.Counter((x['job'],x['id'].split('__')[1],x['strict_state']) for x in c))
EOF
