# 요약

- **판정:** `success`, `valid_experiment=true`, `CONTINUE`. 직접 LoRA SFT baseline의 독립 확인을 완료했다.
- **핵심 근거:** 확인 양성 400명에서 prior_set 대비 평균 F1@0.3 차이 +0.2156, 95% CI [0.1715, 0.2591]. 원시 응답을 별도로 파싱·matching한 결과가 정확히 일치했다.
- **의미·한계:** 경량 적응으로 실제 grounding 출력을 개선했다. 새 방법론의 contribution과 외부 데이터셋 일반화는 아직 증명하지 않았다. 실행기 결함과 미보존 파일 때문에 전체 코드 재사용은 승인하지 않는다.
- **다음:** 충분한 직접 SFT와 비교할 후속 방법을 잔여 오류·선행 방법에 근거해 선정한다. 기존 confirm을 반복적인 방법 선택에 사용하지 않는다.

# Assessment

계획한 직접 적응 가설은 실제 검증됐다. `SELF_CHECK: FAIL`에 적힌 문제들은 이번 완료 결과를 무효화하는 문제와 재사용 결함이 혼재돼 있다. 부모 재사용 경로는 실패했지만 새 base validation 800요청을 생성했고, 보조 실행기로 확인 평가까지 완료했다. `rest.stdout.log`에는 최종 evaluator 실행과 exit 0이 남아 있다. 리뷰의 독립 점수 재계산도 일치하므로 이번 반복을 execution_failed로 판정할 이유는 없다.

검토 대상은 SHA `783d2d04671ae296f3dc0c700e575f8af8e021c9`다. 구현 전후 diff와 현재 소스를 읽었으며 tracked 파일은 해당 SHA와 모두 일치했다. 미추적 `test_rsna_iter010_gpu.py`는 승인 대상에서 제외했다. 별도 execution_amendment.md는 없고, 재실행 사유와 보조 실행기 사용은 parent_audit·코드 설명·보고서에 기록돼 있다. 리뷰에서는 파일을 수정하거나 테스트·GPU 실험을 재실행하지 않고 저장 결과를 읽어 검증했다.

# Key Findings

**실험 규모와 선택**

- train/validation/confirm은 2,400/400/800명이다. 세 분할 간 환자 및 pixel hash 교집합은 0이었다. 현재 영상 3,600개의 file/pixel hash도 manifest와 일치했다.
- 두 LR의 seed17, 선택 LR의 seed29/43까지 총 4개 trajectory가 각각 750 steps·12,000 presentations를 완료했다. 합계 3,000 steps·48,000 presentations이며 학습 child 종료 코드는 모두 0이다.
- 20개 epoch의 validation 8,000요청을 재집계해 저장된 생성 점수와 불일치 0을 확인했다. 선택 파일이 참조한 train config·adapter 파일·원시 요청·metric·completion hash도 일치했다.
- 두 LR 모두 사전 연장 조건을 충족하지 않았다. LR 2e-4는 epoch4→5 utility가 0.01717 증가했지만 validation loss 비율이 1.03008로 증가했다. LR 2e-4와 각 seed의 epoch 5 선택은 기록된 규칙과 일치한다.
- validation의 6개 단순 비교군 점수를 재계산했고 prior_set의 F1@0.3=0.380이 가장 높았다. comparator는 confirm 생성 전에 고정됐다.

**독립 확인 결과**

| 비교군 | 양성 F1@0.3 | 양성 F1@0.5 |
|---|---:|---:|
| official_long | 0.1650 | 0.0208 |
| concise | 0.0812 | 0.0063 |
| prior_set | 0.4243 | 0.1619 |
| SFT seed17 | 0.6308 | 0.3487 |
| SFT seed29 | 0.6359 | 0.3133 |
| SFT seed43 | 0.6528 | 0.3638 |

위 값은 confirm 원시 응답의 별도 JSON 파싱과 최대 cardinality matching 계산으로 확인했다. 환자별 세 seed 평균과 prior_set의 차이를 10,000회 bootstrap한 결과도 저장값과 같았다: +0.2155833, 95% CI [0.1715271, 0.2591139].

확인 생성은 base 1,600요청과 SFT 2,400요청으로 총 4,000개이며 각 디렉터리에 중복·누락 없이 완료됐다. SFT는 세 seed 모두 800/800 유효 출력이었다. Normal의 빈 응답은 195–196/200, NoOpacity/NotNormal은 133–144/200으로 concise base의 153/200·39/200보다 높았다. 사전 성공 기준 5개를 모두 충족한다.

**복구 검증과 자원**

CPU 검사 결과는 iter_009 재사용 59/59, iter_010 70/70, iter_012 36/36이다. GPU 기록은 59/59다. 결정적 D 모드의 두 LR 각각 12 steps, M 모드의 본학습 입력 설정 각각 4 steps에서 U1/U2/R의 원시 loss·batch ID·token digest·LR·RNG·optimizer step 일치를 직접 대조했다. D의 재개 5회와 M의 중간-step 재개 1회가 기록돼 있다. 이는 수정된 실행 경로의 근거이며 과거 부모 trajectory의 소급 인증은 아니다.

두 GPU에서 독립 학습을 병렬 수행했고, 별도 추론은 GPU당 2 worker를 사용했다. development base 처리량은 2.376요청/분으로 기존 2 worker의 1.39요청/분보다 높았고, 과거 4 worker 출력과 48/48 token 일치가 기록됐다. 생성 자원 로그를 재집계한 GPU 전체 관측 최대는 17,988MiB로 2 worker의 여유를 고려한 20,480MiB 기준 이내였다. 학습 GPU당 1개 배치는 약 12GB 점유와 추가 프로세스 여유를 고려하면 타당하다. 임의 시간 상한이나 불필요한 pilot 반복으로 본실험을 축소하지 않았다.

# Problems / Concerns

현재 SFT 개선 결론을 무효화하는 문제는 발견하지 못했다. 다만 다음 재사용에는 아래 수정이 필요하다.

1. `generate.run_worker`의 부모 재사용 분기는 `lock_protocol`이 정의되지 않아 실제 실패했다. 이번 base validation 전량 재생성은 유효한 복구였지만 코드 결함은 남아 있다.
2. `pipeline.py`와 `run_iter012_rest.py`는 기존 `confirm_result.json`을 내용 검증 없이 건너뛴다. `gen_check`도 기존 decision 파일을 그대로 반환한다. 이는 계획의 모든 건너뛰기 검증 요구를 완전히 충족하지 않는다. 이번 final 결과는 실제 새로 계산됐으므로 현재 결론을 무효화하지 않는다.
3. gen_check는 출력 일치 수치를 기록하지만 worker 선택의 필수 조건으로 강제하지 않는다. 현재 48/48 일치는 확인됐으나 다음 재사용 전에 gate를 보완해야 한다.
4. 보조 실행기는 protocol 잠금 밖이다. 이번에는 잠긴 함수·CLI를 호출하고 설정·평가 집단을 유지했음을 소스와 로그로 확인했다. 후속 실행에서는 정식 경로에 통합하고 기존 산출물과의 호환 범위를 기록해야 한다.
5. iter_011 회귀 검사는 42개 통과 뒤 오래된 select fixture의 protocol digest 누락으로 중단됐다. 미실행 migration 검사를 통과했다고 간주할 수 없다. 이번에는 부모 학습 trajectory를 사용하지 않아 현재 비교를 막지 않는다.
6. GPU 검사기의 장치 0/1 고정은 이번 허용 범위에서는 문제가 없지만 범위가 달라질 때 재사용할 수 없다. 미보존 파일도 남아 있어 전체 스냅샷 승인은 보류한다.

보고서의 원인 해석도 좁혀야 한다. 수정된 결정적 경로의 동등성과 기본 kernel의 변동은 확인됐지만, 과거 FAIL 5건 모두가 kernel 비결정성 때문이었다는 인과 결론까지 입증하지는 않았다. 부모 이관 검사는 부모 trajectory를 사용하지 않는 결정으로 우회됐다.

# Interpretation

사용자의 정상 사용 검증 우선 지시를 따른다. iter_009에서 검증한 문제에 연결해 method 단계에 진입했고 anatomy 전이를 자동 선택하지 않았다. 부모 결과와 실패 기록은 보존했으며, 이번 개선은 같은 확인 집단에서 비교했다.

의미 있는 진전은 경량 언어층 적응만으로 실제 생성 grounding이 개선됐다는 점이다. 반면 위치 정밀도와 양성 미검출은 남아 있다. SFT의 F1@0.5는 0.313–0.364이며 양성 빈 응답은 61–74/400명이다. 작은 병변 성능 차이는 원인 후보를 제공하지만 내부 표현 병목이나 특정 해결책의 필요성을 확정하지 않는다.

세 seed 모두 마지막 epoch를 선택했으므로 baseline의 추가 학습 가능성을 검토해야 한다. 사전 연장 규칙을 지켰다는 사실과 충분한 수렴은 별개다. 환자 bootstrap은 학습 seed 불확실성 전체를 반영하지 않으며, 주석 경계와 사전학습 노출의 불확실성도 유지한다. 이번 success는 baseline 확립이지 top-tier 방법론 contribution 또는 최종 목표 달성이 아니다.

# Recommended Next Experiment

실행기 재사용 결함을 필요한 범위에서 수정하면서 방법 개발을 준비한다. 이미 성공한 본실험을 단순 코드 정비 때문에 반복할 필요는 없다.

train/validation에서 추가 학습한 직접 SFT와 잔여 오류를 겨냥한 후보를 비교할 계획을 세운다. 가까운 선행 방법과 차별성을 확인해 후보 하나를 고르고, 실제 생성 성능으로 가능성을 판단한다. 새 계획에는 대표 subset·1개 seed 탐색, 공정한 학습량 비교, 확대·보류 기준과 두 번째 데이터셋 검증을 고정한다. 유망성이 확인되면 필요한 다중 seed·독립 확인으로 확대한다.

이번 confirm의 잔여 오류를 방법 설계에 활용하면 개발 자료로 전환한다. 새로운 확인 환자 집단을 보존하고, 확인 결과에 맞춰 checkpoint·목적함수·평가 기준을 조정하지 않는다.