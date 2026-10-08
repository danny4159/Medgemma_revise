# 사고 라운드 1

# 이번 라운드의 핵심

현재 CURE 8영역 회복 후보와 기존 R/G 추가 epoch·seed의 보류를 유지한다. 다음 투자 후보는 **학습률을 분리한 직접 판독 baseline 대조**로 좁혔다. 기존 관찰과 가까운 선행의 구체적 결과를 연결할 수 있지만, 실행할 최소 조건과 평가의 신뢰성을 확정하기 위해 한정된 설계 판단이 남았다.

## 확인한 원본과 현재 상태

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, 현재 `RESEARCH_FOCUS.md`, 관련 `LIMITATIONS.md`와 `CODE_ASSETS.md`를 확인했다.
- iter_088·092·093·094·096의 원 리뷰, iter_095 계획, iter_092의 인계 계획과 관련 `review.json/code_assets`를 읽었다.
- 현재 research HEAD는 `23a37396b79a169850f5a8fcd2c5a2c4109ffc7f`이며 `git status --short` 출력은 없었다. 필요한 report90/94/95/96 파일은 현재 브랜치에 있다. 소스 반입이나 재구현을 발주하지 않았다.
- iter_090의 사용자 인계 작업은 iter_092에서 네 trajectory 각각 384 updates와 E128 평가까지 완료됐다. 오래된 R277/G256에서 재개할 이유가 없다. 완료 대기·원본 보존 운영 지시만 계속 적용한다.

## 이어받는 관찰과 해석 경계

1. **iter_092:** recall 적격 94명에서 R/G/base/CURE strict recall은 각각 0.011525/0.016844/0.078369/0.164716이었다. G−R +0.532pp는 한 환자의 추가 회복에 의존했다. 보조 grounding F1@0.3은 R 0/G 0.25였다. 위치 출력 학습과 낮은 판독 성능의 공존은 유지하지만, 충분히 작동하는 직접 판독 baseline 이후의 위치 효과는 미확인이다.
2. **iter_093~094:** 원 선택 규칙 위반은 배제됐다. V32의 recall 적격 20명에서 R epoch1→6은 0.125→0.200, 차이 CI는 [-0.100, 0.250]이었다. 후반 회복은 있었지만 오류 비용을 포함한 충분한 baseline 회복은 확인하지 못했다. 같은 V32에 checkpoint를 더 추가하는 선택 진단은 종료한다.
3. **iter_095~096:** 좌표 요구를 제거해도 영역 간 불일치는 남지만 정확한 충돌률과 추가 회복 가치는 평가 결함·해부 대응에 의존한다. 현재 8영역 회복 후보를 재개할 독립적인 의미·위치 근거는 이번에 확보하지 않았다. 기존 수치를 최종 검증치로 사용하지 않는다.
4. `padchest-regional-report-concatenation-conflict`는 iter_088의 제한된 observed 근거다. 이번 baseline 가설의 증명이나 새로운 method 진입 근거로 바꾸지 않는다.

## 새로 확인한 문헌 근거

[CURE v2, Table 15 및 §9.3.3](https://arxiv.org/html/2601.15408v2)은 위치 점수와 판독 지표가 함께 좋아지는 경우만 보고하지 않는다. 같은 계열의 v8→v11 비교에서 PadChest-GR IoU는 0.207→0.265, CheXbert F1-Micro는 0.552→0.507이다. 두 조건은 학습률 2e-5와 2e-4를 사용한다. 저자도 높은 학습률에서의 위치 개선과 판독 지표 저하를 논의한다. 이는 우리 결과의 재현이나 내부 원인 증명이 아니라, 최적화 강도를 분리해야 할 구체적인 선행 근거다.

[공식 CURE 저장소](https://github.com/PabloMessina/CURE)는 정상 해부구조에서도 이상을 만들어내는 편향과 이를 줄이는 anatomy supervision·error-aware sampling을 이미 다룬다. 따라서 '위치는 맞지만 판독이 틀린다'는 질문 자체를 새로운 기여로 선택하지 않았다. 공개 adapter가 MedGemma 1 기반이라는 점도 유지한다.

[MAIRA-2](https://arxiv.org/abs/2406.04449)는 grounding과 판독 사실성·완전성을 함께 평가하는 가까운 선행이다. 위치 점수만을 최종 판독 이점의 대리값으로 사용할 수 없다는 기존 판단을 유지한다.

## 새로 확인한 로컬 구현·자료

- `report90_train.py`와 `report90_recovery_train.py`의 학습률 후보는 1e-4/2e-4다. 기존 실험은 2e-5의 직접 판독 대조를 포함하지 않았다.
- `report89_model.py`에서 R/G는 환자별 report token 평균 CE에 grounding token 평균 CE를 가중치 0/1로 더한다. 언어층 LoRA와 고정된 batch·seed 경로를 사용한다. CURE의 전체 학습 조건과 같다고 볼 수 없다.
- `report90_select.py` 및 원 리뷰상 epoch6 NLL로 LR을 선택한 뒤 공통 epoch를 고른다. 모든 LR×epoch의 최저 NLL을 고르는 규칙과 다르지만, 이미 확인한 사전 설계이며 오류로 재분류하지 않는다.
- 실제 `T512/manifest.json`의 512개 target과 `V64/manifest.json`의 64개 target은 Findings 표제를 포함하지 않는다. 반면 입력 prompt는 Findings와 Impression 구성을 요구한다. 이는 원 계획이 문장 연결 target을 지정한 결과이며 새로 발견한 구현 위반은 아니다. 형식 차이가 정상문 편중을 유발했는지는 미확인이다.
- T512에서 정확히 같은 target 문구의 빈도는 `No significant findings.` 38명, `Within normal limits.` 25명, `No relevant findings.` 22명, `No significant radiological findings.` 10명이다. 빈도 자체를 원인 증거로 쓰지 않는다.
- V64에는 lateral view에서 확인되지 않는 apparent cardiomegaly를 기술한 target 1건이 있다. 제한된 명시적 view 표현 검색에서는 T512 0건/V64 1건이었다. 전수 임상 적합성 검사나 원 baseline 저하의 설명은 아니다.

## Strategy Check / 연구 방향 판단

**시험 설정:** 현재 높은 LR recipe의 추가 epoch·seed와 CURE E32 재채점은 보류한다. 낮은 LR의 표준 직접 SFT는 같은 설정을 무조건 연장하는 것이 아니라 아직 분리하지 않은 최적화 설명을 시험하는 후보다. 다만 선행의 LR 효과를 근거로 우리 baseline이 회복될 것이라고 가정하지 않는다.

**연구 관찰:** 위치 출력과 판독의 차이, NLL과 실제 생성 회복의 차이, 영역별 불일치는 보존한다. 선택 위반이라는 설명은 줄었으나 인식·선택·결합의 내부 원인은 구분되지 않았다.

**연구 질문:** 위치 supervision의 효과를 보려면 직접 판독 baseline의 적합성부터 확보해야 한다. 가까운 선행도 최적화·sampling에 따른 trade-off를 다루므로, 단순 현상 발견과 새 contribution을 구분해야 한다.

세 선택을 비교했다. 첫째, baseline 재구성은 새 문헌 근거와 기존 코드에서 빠진 LR 대조를 연결할 수 있다. 둘째, CURE grounding의 사실성 진단은 선행과 중복되고 현재 reference의 판별력도 제한적이다. 셋째, 연구 묶음을 보류하면 비용을 줄일 수 있으나 구체적인 최적화 설명 하나가 남는다. 따라서 첫째를 우선 검토하되, 실행 가능한 평가와 명확한 종료 행동을 정하지 못하면 셋째를 선택한다. 이는 같은 현상의 원인 탐구이며 새 데이터·모델 후보 순회가 아니다.

직전 리뷰의 '변경할 조건과 판별력이 있을 때만 baseline 재구성' 권고를 유지한다. 변경 후보를 학습률로 특정한 것이 이번 진전이다. 기존 학습·생성 비용보다 의미 검토와 재작업의 부담도 중요하지만 정확한 비용 비율은 측정되지 않았다.

## 재사용과 남은 작업

현재 파일 존재와 제한된 모듈 승인은 확인했다. `report90_train.py`, `report90_recovery_train.py`, `report90_stable_v2.py`, `report89_model.py` 및 데이터 manifest가 후보 자산이다. 다음 라운드에서 실제 사용할 경로의 원 code_assets·수치 gate·의존성을 연결하고 변경 범위를 고정한다. 기존 결과 경로·config digest를 바꿔 과거 학습을 이어가는 방식은 사용하지 않는다.

iter_094의 의미 평가와 iter_095~096 평가기를 범용 승인본으로 사용하지 않는다. 특히 일반 정상문, 급성 부정, 위치 누락, 시간 근거의 처리 오류가 baseline 확대 판정을 다시 좌우하지 않도록 평가 범위를 먼저 정해야 한다.

## 대규모 GPU 필요 후보

여러 backbone과 충분한 판독 학습량에서 위치 supervision·sampling·학습 범위의 trade-off를 교차 비교하는 후보를 보존한다. 현재 두 GPU에서는 표준 직접 SFT의 한정 대조부터 검토하며 full fine-tuning을 자동 처방하지 않는다.

이번 라운드는 read-only 조사였다. 파일 변경·환경 구성·학습·신규 생성·알림 전송을 실행하지 않았다.

## 다음에 파고들 질문
- 현재 report90의 수치 gate와 원 code_assets를 계승하면서 LR만 2e-5로 바꾸는 직접 SFT가 어떤 update 수·평가 시점에서 기존 1e-4/2e-4와 공정하게 비교 가능한가? 동일 학습량 대조와 낮은 LR의 학습 부족을 구분할 조건을 확정한다.
- 기존 V64 reference·출력 중 명시적 소견 회복과 명확한 오류만으로 baseline 확대 여부를 판단할 수 있는가? 일반 정상문·위치 누락·lateral-view 1건의 모호성이 판단을 바꾸는지 확인하고, 새 범용 평가기 없이 고정할 규약과 종료점을 정한다.
- R-only 가능성 탐색을 통과했을 때만 같은 조건의 G를 추가하는 설계와 처음부터 R/G를 두 GPU에 배정하는 설계 중 어느 쪽이 비용 대비 더 판별력 있는가? 기존 실측 처리량·메모리와 필수 비교량으로 한 가지를 선택한다.
