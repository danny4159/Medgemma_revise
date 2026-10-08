# 요약

- **핵심 결과:** 원자 사실 단위로 정정한 뒤에도 strict 기준에서 회복 집단 N=0이다. 생성·GPU 실행은 하지 않고 계획된 "자료 적합성 부족" 분기로 종료했다.
- **근거:** 비정상 48명 전체를 원문 기준으로 다시 검토했다. P-clear 14명, Q-clear(소견 수준) 2명(P085, P090)이고 교집합은 0명이다. 정정 전(iter_098)과 P·Q 집합은 같다. 바뀐 것은 P008·P033·P053의 제외 이유가 원자 사실로 분해되어 기록된 점이다.
- **미검증·주의:** 판정은 assistant 단일 수동 검토이며 전문의 검증이 아니다. 완화 시나리오에서는 N이 달라진다. 이 결과는 교정 효과에 대한 음성 결과가 아니다. 가설 H1/H2는 검증하지 못했다.
- **다음:** GPT가 아래 민감도와 권고를 보고 결정한다.

# Work Performed

- 기준 plan SHA256이 `8983be9b…`와 일치하는 것을 직접 확인했다. HEAD는 `f86dccf`이고 작업 트리는 깨끗했다. 반입 요청은 없다.
- P008·P033·P053의 reference, 초안, 영역 설명 전체 문맥을 대조했다. `view_abnormal48.txt`로 48명 전체도 확인했다. 확인 범위는 reference 사실, 초안, 영역 설명 본문이다.
- `report99_lock.py`에 원자 사실 ledger를 구현했다. 각 atom에 소견, 측면, 위치, 시간, 원인, 초안 대응, 영역 대응을 연결했고 상태는 `clear/partial/unknown/covered_by_draft/temporal/attr`로 나눴다.
- `report98_data.load_readings`가 이제 중복 ImageID/condition을 내용이 같아도 거부한다.
- 모든 인용(reference, 초안, 영역 설명)과 fact ID 검사를 통과한 뒤에만 결정 파일을 배타적·원자적으로 만든다. 실패하면 오류 기록만 남기고 잠금 파일은 만들지 않는다.
- 입력 파일 hash(`inputs_E96`, `reference_facts_E_private`, amendment, readings, linked, iter_098 결정·plan)와 실행 소스 hash를 결정 파일에 포함했다.

# Files Changed

- 수정: `report98_data.py` (중복 키 거부, `path` 인자 추가)
- 신규: `report99_lock.py`, `report99_show.py`(읽기 전용 검토 보조), `test_report99.py`
- 신규 결과 (`results/iter_099/`):
  - `data/atom_ledger.json`
  - `data/eligibility_decision.json`
  - `tests/regress_report99.json`
  - `completion.json`
  - `tests/work_*`, `tests/readings_dup.jsonl` (회귀 검사용)
- iter_098 산출물은 건드리지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python report99_lock.py` → 성공. quote/ID 검사에서 problem이 0건이어서 ledger와 결정 파일이 생성됐다.
- `python test_report99.py` → 9/9 PASS.
- `completion.json`으로 세 산출물의 hash를 봉인했다.
- GPU 실행은 없다. N=0이므로 계획의 종료 분기이며 `nvidia-smi`로 두 GPU가 비어 있음만 확인했다.

# Results (수치와 결과 파일 경로)

결과 파일은 `results/iter_099/data/eligibility_decision.json`이다.

- strict N = [], `run_generation=false`.
- P-clear 환자: 3, 8, 12, 21, 25, 33, 45, 49, 52, 53, 56, 62, 69, 70.
- Q-clear 환자: 85, 90. 둘 다 P가 없다. 초안의 `No significant findings`는 구체적 부정을 대신하지 않는다고 처리했다.
- 결정 민감 세 사례:
  - **P008:** 초안의 density/volume loss가 현재 atelectasis-condensation을 이미 표현했을 가능성이 있다(`covered_by_draft`/`unknown`). 새 회복으로 단정하지 않았고 "persistent"는 시간 atom으로 분리했다.
  - **P033:** 소견 존재와 측면은 대응하고 pneumonia hedge는 원인에만 붙는다. 그러나 reference의 vertex(apex)와 영역 설명의 upper lobe는 lobe-zone 동치가 미해결이라 `partial`로 두었다. RLL 대응은 없다. 영역 설명의 `unchanged`/`new`는 서로 충돌한다.
  - **P053:** small이라는 크기 속성(attr)만 `clear`다. 핵심 소견(retrocardiac consolidation 대 new LLL opacity)은 `unknown`이다.
- P005·P042·P082의 P 제외 사유는 ledger에 기록했다. P005와 P042는 위치 미해결(`partial`), P082는 동치 미확정(`unknown`)이다.
- 민감도(사전 정의, 생성 허용 기준 아님):

| 시나리오 | N |
|---|---|
| strict | 0명 |
| Q의 partial을 clear로 인정 | [33] |
| 위에 attr까지 인정 | [33, 53] |
| 가장 느슨한 경우 | [8, 33, 53] |

- 시간: 잠금 스크립트 실행은 수 초다. 의미 검토 시간은 별도로 계측하지 못했고 미측정이다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **구분:** 이번 작업은 자료 보완(적격성 정정)이며 새 과학적 관찰은 없다. 실행 복구와 평가 보완을 포함하지만 H1/H2는 미검증이다.
- **연구 판단:** 그대로다. 정정으로 어떤 경쟁 설명도 줄이지 못했다.
- **재사용:**
  - `report98_data.py`: 수정 후 `test_report99.py`로 중복 거부를 검증했다.
  - `report98_lock.py`: 보관만 했다.
  - 생성기(`report97_gen` 등): 이번에는 사용하지 않아 needs_fix 상태가 유지된다.
- **검증의 한계:** 산술 재계산 검사(strict/Q_partial N)는 같은 ledger에서 다시 계산한 것이어서 의미 검증이 아니다. 의미는 단일 검토자의 판단이다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론에 영향 (판단 필요):** N=0은 "partial을 clear로 보지 않는다"는 판정에 의존한다.
  - P033의 Q를 소견·측면 수준에서 clear로 인정하면 N=1이다. 계획에는 "명확한 적격자가 1명이라도 있으면 사례 탐색 가능"이라고 되어 있다.
  - 다만 양성 기준(안전한 회복 환자 3명 이상)은 N≤3에서는 거의 도달할 수 없다. 사례 연구 이상의 결정은 나오지 않는다.
  - 이 판정은 계획의 lobe-zone 불확실 동치 규칙을 따른 것이다. 결과를 보고 규칙을 바꾸는 탐색은 하지 않았다.
- **재사용 전 수정:** 생성기 needs_fix(허용 GPU 집합 검사, attempt 충돌, 변조·재개 검사)는 이번에 손대지 않았다. 생성이 필요할 때만 보완한다.
- **추후 개선:** 없음.

# Recommendation to GPT

- **권고: 이 저장 출력 기반 교정 설계를 범위를 명시해 보류한다.** strict 기준에서 명확한 적격자가 0명이고, 가장 느슨한 해석에서도 N≤3이라 사전 양성 기준을 평가할 표본이 되지 않는다. 이 보류는 "자료 적합성 부족"으로 한정한다. 교정 효과나 영역 근거 활용의 음성 결과가 아니고, 위치 학습 전체의 기각도 아니다.
- **대안:** P033 한 건(N=1, 대조 포함 M=2, 요청 6건)을 사례 탐색으로 돌린다. 생성기 필수 검사를 먼저 통과시켜야 하고 결과는 판정에 쓸 수 없다. 결정이 바뀌지 않아 권하지 않는다.
- **재개 근거:** 독립 정답 근거로 P033의 lobe-zone 동치나 P008의 초안 대응을 확정해 strict N≥3이 될 때, 또는 영역 설명이 회복 기회를 더 많이 포함하는 자료로 바뀔 때다.

SELF_CHECK: PASS
SUMMARY: 원자 사실 단위로 정정해도 strict 기준 회복 집단 N=0(P 14명·Q 2명, 교집합 없음)이라 생성 없이 자료 적합성 부족으로 종료했으며, 완화 시 N≤3이고 H1/H2는 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; python - <<'EOF'
import report98_data as D, json
R=D.load_readings(); am=json.load(open(D.REF_AMEND))["patients"]
ids=D.abnormal_ids()
idx={am[i]["patient_index"]:i for i in ids}
for pi in (8,33,53):
    i=idx[pi]; pk=D.package(i,R)
    print("=====P%03d"%pi,i)
    for f in am[i]["facts"]: print(" FACT",f["fact_id"],f["v2_class"],"|",f["sentence_en"])
    print(" DRAFT:",pk["draft"])
    for g in pk["groups"]: print(" ",g["gid"],g["regions"][:3],"|",g["body"][:300])
EOF
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research; awk '/^=== /{print ""; print; next} /^DRAFT:/{print; next} /^  F[0-9]/{print}' results/iter_098/data/view_abnormal48.txt | sed -n '60,400p'
