# 요약

- **이번에 할 일:** 기존 MRI 판독 출력에서 VLM–분류기 불일치가 검토할 오류를 더 잘 찾는지 확인한다.
- **필요한 이유:** 자동 등급 교정은 투자 기준에 미달했지만, 오류를 찾아 검토 대상으로 보내는 효용은 검사하지 않았다.
- **확인할 기준:** 같은 25% 검토량에서 강한 confidence baseline보다 두 등급 이상 오류를 더 포착하는지, 이득이 여러 환자에 걸치는지 본다.
- **주의·다음:** 반복 개발 분석이며 새 방법·임상 안전성의 증명이 아니다. 추가 정보가 있을 때만 ensemble 대조와 독립 확인을 위한 한정 보완을 검토한다.

## 알림 맥락

- 연구: MRI 오류 검토 대상 선택
- 데이터: 척추 sagittal T2 MRI와 부위별 Pfirrmann 등급 정답인 SPIDER
- 모델: 기존 MedGemma 1.5 영역 판독 SFT와 공유 ResNet18, 신규 학습 없음
- 과제: 두 모델의 저장 답변과 분류기 확률로 검토할 부위의 우선순위를 출력
- 가설: 등급 불일치가 분류기 confidence에 없는 오류 정보를 제공할 수 있다
- 질문: 같은 수의 부위를 검토할 때 모델 간 의견 차이가 큰 등급 오류를 더 찾아주는가?
- 변경: 방향 전환
- 연결: 자동 등급 교정의 이득은 불확정이었다 → 같은 SPIDER 출력으로 오류 식별이라는 새 질문을 한정 검토한다
- 작업: 불일치와 confidence 순위를 비교해 후속 검증에 투자할지 현재 후보를 보류할지 결정한다

# Current Understanding

iter_081은 iter_080의 미완료 실험을 Codex가 인계해 완료한 유효한 실험이다. 보완 ID `20261005_214738_9d40c388`의 일회성 인계는 끝났으므로 재실행하지 않는다. Codex 담당, 원본 보존, GPU 권한과 smart 운영 원칙은 유지한다.

E24 24명·held ordinal 2/4의 47개에서 Q의 class-standardized MAE는 0.77690, C는 0.77619, 영상+자동 등급 A는 0.73286이었다. A−C의 95% CI는 [−0.19584, 0.08730]이다. 현재 자동 교정 후보의 투자 종료는 유지한다. C의 두 등급 이상 오류는 7/47, 일반 오답은 23/47이다.

이번 목표는 C의 예측을 고치는 것이 아니라 오류가 있을 부위를 정해진 검토량 안에 넣는 것이다. 검토 후 사람이 실제로 오류를 고친다는 실험은 하지 않는다. ‘두 등급 이상 오류’는 정답표에 대한 연구용 사건 정의이며 임상 위해의 검증된 대리지표가 아니다.

# Strategy Check / 연구 방향 판단

**실제 선택은 기존 MRI 판독·참고영상·자동 교정 묶음의 투자 보류와 오류 식별 후보로의 전환이다.** 직전 리뷰의 권고를 유지한다. 이번은 context 또는 F/R 차이의 원인 규명이 아니다.

이어받는 관찰과 판단은 다음과 같다.

- iter_064: MedGemma의 다른 slice 추가 손실과 Qwen 비재현은 유지한다. 충분한 인식 이후의 선택 실패·결합 실패는 미확정이며 이번에 설명하지 않는다.
- iter_077: 영역 입력의 영상 대응 신호와 F−R 차이 0.29357은 유지한다. 해상도·context·별도 학습의 기여는 미분리다. C 대비 VLM 정확도 이점은 불확정이다.
- iter_078: 참고영상의 추가 가치 미확보를 유지한다. 참고 수·검색기 순회는 선택하지 않는다.
- iter_079: longitudinal 정답 연결 실패다. 모델 능력에 관한 반증으로 사용하지 않는다.
- iter_080/081: 영상 교환이 답에 영향을 준다는 진전은 있으나 유용한 자동 교정은 확보하지 못했다. 원 기준과 종료 판정을 유지한다.
- iter_029: RSNA에서 entropy가 강한 오류 식별 대안이었다. 새 후보도 confidence 이후의 추가 정보를 입증해야 한다.

현재 방법 개선은 효과 연결이 약하고, F/R 원인 진단은 결과가 바꿀 사용 가치가 미정이다. 새 자료 탐색은 입력·정답 연결 비용을 다시 요구한다. 기존 출력 분석은 새 모델 실행 없이 ‘confidence 이상의 검토 정보가 있는가’를 직접 답하므로 우선한다.

새 track `medical-error-review-selection`은 인식·선택·결합에서 오류 검토 순위로 큰 질문이 달라졌기 때문이다. 과거 오류 탐지 질문인 iter_029와 현재 MRI 자산·실패 이력을 related_iterations로 연결한다. 파일 재사용을 원인 설명의 진전으로 세지 않는다.

이번 지배 작업은 작은 통계 분석과 필요한 출처 확인이다. iter_077의 본학습 worker wall 합계 약 2.73시간과 iter_081의 본생성 wall 약 82.7초는 원 리뷰의 측정 범위로만 인용한다. 전체 준비·감사 비용 비율이나 절감률은 추정하지 않는다.

# Hypothesis

- H1: Q/C 등급 차이가 C confidence만으로는 낮게 순위화되는 실제 오류를 추가로 포착한다.
- H0: 불일치의 효용은 C의 낮은 confidence 또는 순서형 posterior 위험으로 설명되며 같은 검토량에서 추가 이득이 없다.
- H2: 불일치가 주로 Q의 오류를 반영해 C 정답까지 검토 대상으로 보내거나 이득이 소수 환자에 의존한다.

이번은 기존 출력의 진단이다. 학습된 검토 정책, 새 loss, 자동 교정 알고리즘을 개발하지 않는다. 양성도 인과 기전이나 VLM 고유성의 증명이 아니다.

# Limitation Evidence / Correct Usage Checks

이번 오류 식별 한계는 아직 등록·검증되지 않았으므로 limitation_ids는 비운다. `spider-regional-reading-input-gap`과 `mri-explicit-target-context-effect`는 관련 배경이며 오류 순위의 결함을 대신 입증하지 않는다. 원문과 사용법 검사를 확인했으며 상태를 변경하지 않는다.

iter_077·081의 공식 template, 동일 세 sagittal T2 crop, 고정 parser·32-token cap·EOS, checkpoint 선택과 ID 연결 검증을 재사용한다. 새 생성이 없으므로 tensor·GPU 재현 검사를 반복하지 않는다. 이번에 읽는 파일은 보존 hash와 대조하고 Q/C/정답의 행 연결을 다시 확인한다.

대상 자료는 V8 8명·24개와 E24 24명·47개뿐이다. V8은 ordinal 1/3/5, E24는 held ordinal 2/4여서 위치 분포가 다르다. 두 집단 모두 이미 노출된 개발 자료이며 이번 잠금이 독립성을 복원하지 않는다. oracle anatomy 지원·단일 적응 checkpoint·단일 자료 조건을 유지한다.

# Contribution Path / Baselines / Reuse

가까운 방법은 [최대 softmax 확률 기반 오류 탐지](https://arxiv.org/abs/1610.02136), [selective classification](https://papers.neurips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html), [deep ensembles](https://arxiv.org/abs/1612.01474)다. 이번 불일치 순위 자체를 새로운 방법이라고 부르지 않는다.

확인하려는 실패 조건은 ‘C 자체 확률로는 낮은 위험으로 분류되지만, 다른 판독 출력과의 차이가 검토 가치 있는 오류를 드러내는가’다. 양성이어도 일반적인 두 모델 ensemble이면 충분할 수 있다. 후속 대조에서 두 번째 경량 분류기와 비용을 비교하기 전 VLM 특이 효용을 주장하지 않는다. 타 계열 VLM의 새 적응은 현재 추가 정보 선별보다 비용이 크므로 이번에 보류한다.

Q는 기존 직접 SFT 결과, C는 같은 대상 영상과 T24 supervision을 사용한 전문 분류기다. 같은 검토량으로 비교하지만 Q+C는 C-only보다 계산이 많다. cached 분석 비용을 온라인 시스템 비용으로 보고하지 않는다.

현재 HEAD는 `6139c4ea9165ca9dba28687d54f956dbaaa3fa26`이다. 새 approach의 자동 기반은 현재 규칙상 iter_006이므로 승인된 `sp75_metrics.py`만 reuse_assets로 반입한다. 의존성은 numpy·hashlib다. 기존 오류 정의와 회귀 확인만 재사용하며 새 순위 bootstrap은 별도로 구현한다.

결과 자산은 다음을 읽는다.

- `results/iter_081/data/baseline_V8.json`, `baseline_E24.json`, `source_audit.json`.
- `results/iter_081/protocol_V8.json`, `protocol_E24.json`, `completion.json`의 관련 보존 hash.
- `results/iter_075/data/manifest.json`의 허용 ID 행.
- `results/iter_078/features.json`과 `data/labels_V8.json`, `labels_E24.json`의 허용 ID.
- `results/iter_077/gen/V8/R_lr2e-4_ep16/gen_worker0.jsonl` 및 `gen/E24/R_adapted/gen_worker0.jsonl`, 각각의 env 기록.

`a81_prepare.py`, `rf78_launch.py`, 이전 위험 평가 CLI는 호출하지 않는다. 사용하지 않는 결함을 정비하거나 해결했다고 기록하지 않는다. 기존 source가 없거나 hash가 다르면 조용히 재구성·재생성하지 않고 해당 분석을 중단한다.

# Proposed Experiment

## 1. 동작 확인과 입력 고정

기존 baseline의 ID 집합·환자 분리·ordinal·정답·Q suffix 및 request_id·C 확률을 원 자료와 연결한다. 예상 표본은 24/47개다. E24의 나머지 supervised 항목, T24의 새 정답 분석, F139·reserve는 사용하지 않는다.

C 확률은 5개이며 유한·비음수, 합의 오차 1e-5 이내인지 검사한다. C는 저장 확률 argmax와 일치해야 한다. Q는 원 whole-string parser와 EOS 규칙으로 대조한다. 현재 승인 자료의 invalid=0과 불일치하면 자료 회귀 실패로 처리하고 임의 fallback을 추가하지 않는다.

원본은 읽기 전용으로 두고 신규 산출물은 `results/iter_082/`에만 쓴다. 규칙·입력 hash·코드·seed를 저장한 후 분석한다. 기술 fixture에는 label을 바꿔도 위험 순위가 변하지 않는 검사를 포함한다.

## 2. 점수와 검토량

모든 점수는 클수록 위험하다. g는 1–5, c는 C argmax, p_g는 C 확률이다.

1. `posterior_ge2 = Σ p_g · 1[|g−c|≥2]`.
2. `expected_abs = Σ p_g · |g−c|`.
3. `entropy = −Σ p_g log(p_g)`; 0 log 0=0.
4. `one_minus_max = 1−max(p)`.
5. `one_minus_margin = 1−(p_top1−p_top2)`.

이 다섯 개가 C-only baseline이다. 같은 source posterior에서 계산하며 E24에서 calibration이나 temperature를 적합하지 않는다.

주 검토율은 25%이고 k=ceil(0.25N)이다. V8은 6/24개, E24는 12/47개다. 이는 제한된 검토 예산을 가정한 연구 운영점이며 임상 표준이 아니다. 보조 검토율 10%·50%에서는 각각 V8 3/12개, E24 5/24개를 보고한다. 보조 결과로 주 운영점을 바꾸지 않는다.

모든 순위의 최종 동률은 `SHA256('iter082-review-v1|' + id)` 오름차순으로 처리한다. 위험 점수는 순위 비교에서 소수점 12자리로 반올림한다. 마지막 동률 구간이 경계를 가르면 가능한 포착 건수의 최솟값·최댓값도 보고하며 유리한 tie seed를 고르지 않는다.

## 3. V8 baseline 선택과 불일치 순위 고정

V8 상위 6개에서 두 등급 이상 오류 포착 수 → 일반 오답 포착 수 → 포착한 절대오차 합계 순으로 최대인 C-only 점수 B*를 선택한다. 완전 동률은 위 점수 나열 순서를 따른다. V8 사건이 없어도 선택 규칙은 실행하고 근거 부족을 표시한다.

주 불일치 순위 D는 `(|Q−C|, B*)`를 내림차순으로 정렬하고 최종 hash 동률 규칙을 적용한다. 가중치나 threshold는 학습하지 않는다. 보조 ablation Db는 `(1[Q≠C], B*)`로 고정한다. Db가 더 좋아도 E24 결과로 D를 교체하지 않는다.

V8 선택·입력 hash·규칙을 잠근다. 작은 V8의 효과 부호로 E24 분석을 막지 않는다. 기존 E24가 이미 노출됐음을 명시하고 선택 잠금을 독립 검증으로 부르지 않는다.

## 4. 고정 E24 분석

C의 원 예측을 모든 조건에서 유지한다. 주 사건 e2는 `|C−grade|≥2`, 보조 사건 e1은 `C≠grade`다.

각 순위에서 다음을 보고한다.

- 검토 집합의 e2·e1 포착 건수, precision, 전체 사건 대비 recall, 남은 미포착 사건 수.
- D−B*의 순 포착 차이와 양쪽만 포착한 ID·환자 수.
- 다섯 C-only 점수 각각과의 차이. E24에서 최고인 baseline은 사후 비교 상한으로 표시하며 배포 선택으로 사용하지 않는다.
- e2·e1 AUROC와 average precision, 검토하지 않은 항목의 평균 절대오차. 단일 사건 class이면 정의 불가로 표시한다.
- grade·ordinal별 건수 및 Q가 틀려 생긴 경보를 포함한 전체 결과. 유리한 subgroup만 추출하지 않는다.

환자 paired bootstrap 10,000회, seed8201을 사용한다. E24 환자를 복원 추출하고 각 환자의 모든 허용 행을 함께 넣는다. 각 replicate에서 N과 k를 다시 계산하고 순위를 다시 적용한다. B*는 다시 선택하지 않는다. 복제 행은 bootstrap occurrence index를 마지막 동률 key로 사용한다. 주 차이는 포착 건수 차이와 recall 차이의 percentile 95% CI다. 사건이 없는 replicate에서 recall은 undefined로 기록하고 건수 통계는 유지한다. CI는 반복 개발·고정 선택에 조건부이며 확증 보장이 아니다.

E24 환자를 한 명씩 제거하는 24개 분석도 수행한다. 매번 k=ceil(0.25N)을 다시 적용하고 B*를 유지한다. 이 검사는 이득이 한 환자에 의존하는지 확인하는 용도이며 추가 독립 실험이 아니다.

## 5. 규모·독립 확인·자원

이번 본분석은 기존 E24 전체 47개까지이며 새 요청·학습·seed·자료 확대는 없다. 동작 확인 후 별도 GPU gate 없이 통계 분석을 끝낸다. 신규 모델 checkpoint도 없다. 독립 확인은 미실행이다.

CPU-only를 택한 실제 투자 blocker는 ‘confidence 이후에도 추가 검토 정보가 남는가’의 미검증이다. 이 비교는 저장된 실제 출력으로 완결된다. 같은 출력을 GPU에서 재생성해도 독립 근거가 되지 않는다.

CPU 계산 wall-clock은 초기 추정 수분∼수십 분이며 실측이 아니다. 10,000 bootstrap 중 최초 200회의 처리량으로 남은 시간을 갱신한다. 이 200회는 본계산에 포함하고 seed를 다시 고르지 않는다. 구현·출처 확인 시간은 별도로 기록한다. 시간 상한은 추가하지 않는다.

단계별 입력 hash와 선택 결과를 원자적으로 저장하고 기존 출력 충돌을 거부한다. 재개는 입력·코드·규칙이 같은 완료 단계만 허용한다.

이번 GPU 메모리·배치는 해당 없음이다. 양성 이후의 별도 GPU 계획에서는 두 장에 Q와 두 번째 경량 분류기 작업을 나누고 배정 직전 nvidia-smi를 확인한다. iter_081의 짧은 출력 2/4-worker 측정은 참고할 수 있으나 새 입력·모델에 자동 적용하지 않는다. 실제 peak+worker당 2 GiB와 처리량·출력 정합성을 기준으로 batch 확대 또는 복수 worker를 선택한다.

# Implementation Tasks for Claude

실제 담당은 Codex, standard다.

1. 승인 모듈 선별 반입과 기존 결과의 필요한 출처를 확인한다. 새 branch·commit은 orchestrator가 관리한다.
2. `review82_analysis.py`에 허용 ID 로딩, label과 점수 계산의 분리, 고정 ranking·V8 선택·E24 통계·종료 판정을 구현한다. 기존 모델 실행기와 무관한 리팩터링은 하지 않는다.
3. 작은 `test_review82.py`에서 위험 방향, 0 확률, argmax 동률, 검토량 ceil, 경계 동률, 사건 0개, 환자 복제, label 비의존 ranking, V8/E24 선택 혼용, 덮어쓰기 거부를 검사한다.
4. `review82_verify.py`는 production 순위·선택 함수를 호출하지 않고 원 baseline·원시 Q·C 확률을 연결해 선택·포착 수·주 CI를 독립 재계산한다. 이전 Q/C 지표와 C 사건 7/47도 회귀 확인한다.
5. `results/iter_082/`에 protocol, V8 선택, label 없는 rank 목록, 평가 표, bootstrap·환자 제거·동률 민감도, verification, report를 보존한다. completion에는 실제 산출물 hash와 완료 범위를 연결한다.
6. 보고서에 실행 유효성, 오류 식별 이득, 가설 지지, 신규 기여 가능성을 구분한다. 새 모델 호출 0건과 cached 비용의 해석 한계를 명시한다.

# Evaluation (성공/실패 기준 포함)

실행 유효성은 원시 연결·고정 규칙·전체 허용 표본·독립 재계산을 통과했을 때 인정한다. 테스트 통과 자체는 가설 지지가 아니다.

**양성 탐색 기준은 모두 충족해야 한다.**

- 주 운영점 E24 12개에서 D가 B*보다 e2를 최소 2개 더 포착한다. 이는 같은 검토량에서 precision +16.7 pp에 해당하는 탐색 투자 기준이며 임상 MCID가 아니다.
- D에만 포함된 e2가 최소 2명의 환자에 걸친다.
- 다섯 C-only 점수 중 어느 것도 D의 e2 포착 수와 같거나 높지 않다. 약한 V8 선택 하나를 이긴 결과만으로 확대하지 않기 위한 조건이다.
- 환자 한 명씩 제거한 모든 비교에서 D−B*의 순 e2 포착 차이가 음수가 되지 않는다.
- 경계 동률의 허용 배열 때문에 D−B* 이득이 사라질 수 있으면 양성으로 판정하지 않는다.

95% CI가 0을 제외하는 것은 이번 탐색의 필수 gate가 아니다. 구간과 사건 수를 그대로 보고한다. 주 기준을 통과해도 독립 효과·VLM 고유 효용·새 contribution은 미확정이다. 다음 권고는 같은 과제의 두 번째 경량 분류기 대조와 독립 환자 확인을 묶는 한정 보완이다. 새 method나 reserve 개방은 별도 계획·리뷰를 거친다.

**음성:** D의 주 e2 포착 수가 B* 이하이면 현재 고정 불일치 순위 후보의 투자를 종료한다. 보조 운영점의 결과는 보존하되 주 기준을 바꾸지 않는다. 현재 ranking의 추가 가치 미확보이며 정보의 절대 부재는 아니다.

**불확정:** 나머지, 즉 작은 이득·다른 C-only 점수와 동률·환자나 동률 의존·사건 부족은 후보 보류다. 같은 자료에서 가중치·검토율을 조정하거나 한정 없는 추가 진단을 붙이지 않는다. 독립적인 추가 정보 근거 또는 명확한 ensemble 판별 가치가 생길 때만 새 계획으로 재개한다.

**기술 실패:** 출처·ID·확률·parser 연결이 어긋나면 영향받은 분석만 미판정으로 남긴다. 기존 MRI 결과나 모델 가설의 음성으로 바꾸지 않는다.

# Risks / Checks

- 기존 E24는 반복 노출됐다. 사전 고정이라는 표현은 이번 분석 규칙에만 적용하며 test 독립성을 뜻하지 않는다.
- 사건 7개에서 CI·환자 제거 검사는 불확실성을 드러내는 장치다. 통계적 비유의성을 효과 없음으로 해석하지 않는다.
- 부위 12개 검토는 환자 12명 또는 동일한 임상 검토 시간을 뜻하지 않는다. 선택된 고유 환자 수도 함께 보고한다.
- C+Q의 정보 이득을 비용 우위로 바꾸지 않는다. Q의 기존 runtime은 참고 범위로만 보존하며 전체 온라인 비용 우위는 이번에 판정하지 않는다.
- posterior 위험은 추정치이지 calibration된 실제 오류 확률이 아니다. E24에서 보정하지 않는다.
- Q/C 불일치가 유용해도 두 번째 작은 분류기로 같은 효과를 얻을 수 있다. 이 경쟁 설명은 양성 이후의 핵심 비교다.
- 등급 정답의 관찰자 차이, oracle anatomy, 위치 분포 차이와 모델 사전학습 노출 불확실성은 남는다. 임상 안전성·일반 MRI 능력으로 확대하지 않는다.

## 대규모 GPU 필요 후보

오류의 독립성을 유도하는 다중 의료 VLM 학습과 근거 조건부 검토 정책의 대규모 post-training은 장기 후보로 보존한다. 여러 기관·과제의 검토 정답과 강한 ensemble 이후의 잔여 가치가 먼저 필요하다. 현재는 그 전제 근거가 없으므로 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/runs/iter_081/review.md`와 `review.json`을 확인했다. 유효한 실험이며 blocking issue는 없다. E24 24명·47개에서 A−C MAE는 −0.04333, 95% CI [−0.19584, 0.08730]이다. C의 두 등급 이상 오류는 7개다. 자동 교정 후보 종료와 오류 식별 후보의 한정 검토 권고를 유지한다.
- `iter_064`, `iter_077`, `iter_078`, `iter_079` 리뷰 원문을 연결했다. context 손실, 전체/영역 입력 차이, 참고영상 추가 가치 불확정, longitudinal 자료 연결 실패는 서로 다른 관찰이다. 이번 분석은 그 원인을 설명하지 않는다.
- `iter_029` 계획·리뷰에서 entropy AUROC 0.8225가 재질의 0.8154보다 높았음을 확인했다. 새 confidence 실패를 가정하지 않고 강한 단순 대안을 먼저 비교한다.
- `results/iter_081/data/baseline_V8.json`과 `baseline_E24.json`은 각각 24/47행이며 id·patient·ordinal·grade·C·Q·5-class probabilities·Q 원시 출처를 포함한다. 파일 크기는 10,877/21,083 bytes다. 원시 Q에는 text·EOS·suffix·입력 hash·adapter digest가 있다. 순위 성능은 이번 계획 단계에서 계산하지 않았다.
- 현재 research HEAD는 `6139c4ea9165ca9dba28687d54f956dbaaa3fa26`이고 작업 트리는 깨끗하다. 새 브랜치 자동 기반 선택 규칙을 확인했으며 현재 승인 기반은 iter_006이다. 따라서 필요한 승인 모듈 `sp75_metrics.py`만 선별 반입한다.
- `a81_prepare.py`의 현재 HEAD 출처 비교 결함과 `rf78_launch.py`의 전체 CLI 결함은 이번 저장 출력 분석 경로에서 호출하지 않는다. 해당 결함을 해결했다고 기록하지 않는다.

## 의미와 설계 선택

기존 출력만으로 검토 우선순위의 추가 정보를 판단할 수 있으므로 새 생성·학습은 필요하지 않다. CPU 진단을 택한 이유는 GPU 회피가 아니라, 새 투자 결정을 막는 미확인 비교가 저장 출력에 이미 들어 있기 때문이다. 사건 7개에서 확증을 요구하지 않되 한두 사례의 이득을 방법 개발 근거로 과장하지 않도록 실제 포착 건수·환자 분포·동률·leave-one-patient-out을 함께 고정한다.

오류는 순서형 등급이므로 일반적인 confidence 세 종류에 더해 posterior 중대오류 확률과 기대 절대오차를 사용한다. 단순 baseline의 과제 불일치로 VLM을 유리하게 만들지 않기 위한 대조다.

## 가까운 선행 확인

- 최대 softmax 확률을 오류 탐지 baseline으로 제시한 [Hendrycks & Gimpel, ICLR 2017](https://arxiv.org/abs/1610.02136)을 확인했다.
- coverage와 risk의 trade-off를 다루는 [Selective Classification for Deep Neural Networks, NeurIPS 2017](https://papers.neurips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html)을 확인했다. 이번 작은 반복 개발 집단에 해당 연구의 보장 조건을 적용했다고 주장하지 않는다.
- [Deep Ensembles, NeurIPS 2017](https://arxiv.org/abs/1612.01474)은 복수 모델 기반 uncertainty의 가까운 대안이다. Q/C 불일치가 유용해도 VLM 고유 가치인지는 별도 비교가 필요하다.

이 문헌들은 비교 설계의 근거이며 사용자 추천이나 현재 후보의 신규성 증명이 아니다.
