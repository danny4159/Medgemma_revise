# 요약

- **이번에 할 일:** 기존 원시 logits로 Presence 방향, C 대표 선택, calibration과 E 비교를 교정한다.
- **필요한 이유:** Presence에 반대 부호가 적용되어 영상 재질의의 대표 비교와 해석이 잘못됐다. entropy의 유효한 관찰은 유지한다.
- **확인할 기준:** 원본 연결과 완전성을 검증하고, C에서 고정한 절차를 E에 적용해 사전 기준을 다시 판정한다.
- **주의·다음:** 새 GPU 생성·학습 없이 완료한다. 기존 결과는 보존하고 독립 일반화·새 방법의 기여는 주장하지 않는다.

# Current Understanding

iter_012의 직접 LoRA SFT 개선은 유효한 baseline이다. iter_027의 영역 선택 결과는 현재 인터페이스의 제한된 음성 근거이며 일반적인 공간 전이 부재를 확정하지 않는다. iter_028은 같은 RSNA target과 checkpoint에서 빈 출력의 미검출 위험을 검사했다.

직전 리뷰는 E 빈 출력 398명 중 미검출 70명에서 entropy AUROC 0.8225와 상위 80명 검토 시 43명 포착을 재현했다. Presence의 역상관은 평가 부호 오류다. C에서 재선택할 대표 V는 리뷰 계산상 presence_b0이며, 정식 calibration과 비교 결과를 복구해야 한다.

사용자 보완의 기존 SFT 성과·checkpoint 우선 활용과 원본 보존을 유지한다. 사분면 prompt 탐색, 새 loss, MRI F139, reserve 및 iter_022 longitudinal 계획은 보류한다. 이미 답한 형식 효과나 검출 정보 전달 실험을 반복하지 않는다. 이번에 바뀔 결정은 추가 confidence 방법의 필요성이다.

# Strategy Check / 연구 방향 판단

이번은 iter_028 전략 판단을 실행 가능한 결론으로 복구하는 제한된 보완이다. 새로운 대규모 투자 전의 전략 재검토를 대신하지 않는다.

1. 현재 방법 개선: 강한 단순 baseline과의 비교가 잘못된 상태에서 새 head/loss를 개발할 근거가 없다.
2. 원인·능력 진단: 저장 logits의 의미와 평가 방향을 교정하면 새 모델 실행 없이 경쟁 설명을 구분할 수 있다. 가장 직접적인 정보 이득이 있다.
3. 다른 질문 또는 외부 확인: 유망한 후보지만 현재 비교를 마친 뒤 사용 가치·독립 자료·차별성으로 판단해야 한다.

따라서 평가 교정을 먼저 완료한다. 교정 후에도 token baseline이 사전 목표를 충족하고 재질의의 큰 추가 이득이 없으면 현재 confidence 방법 개발은 보류한다. 중요한 잔여 실패의 식별 가능한 질문이나 외부 확인의 가치가 있을 때만 다음 투자로 연결한다.

# Hypothesis

- H1: 동일한 유효 빈 출력에도 미검출 위험을 순위화하는 정보가 있다. 기존 entropy 관찰을 보존·재현한다.
- H2: 의미에 맞게 방향을 교정한 영상 재질의가 token 또는 seed baseline보다 사전 기준 이상의 추가 정보를 제공하는가?
- 부호 오류 수정은 모델 행동의 변화가 아니다. 교정 결과를 새 환자 실험이나 독립 재현 횟수로 세지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`의 validated 범위와 iter_012의 잔여 미검출에 연결한다. 빈 출력 confidence의 일반적 실패는 검증된 주장으로 승격하지 않는다.

사건은 B0의 유효 빈 출력에서 RSNA opacity GT가 존재하는 경우다. NoOpacity/NotNormal을 임상적 정상으로 바꾸지 않는다. C400의 빈 출력 199명·사건 36명, E800의 빈 출력 398명·사건 70명을 유지한다.

실제 사용 검증은 iter_028 리뷰가 확인한 범위로 한정한다. input_ids 대조와 suffix 재현을 전체 공식 tensor 동등성으로 표현하지 않는다. generation output_scores를 조건 없이 raw logits라고 부르지 않으며, 저장 generation 설정과 processor 적용 여부를 기록한다. 현재 교정은 저장된 동일 Yes/No 값의 의미 방향을 바로잡는 작업이다.

C/E 생성 당시 protocol digest 차이를 확인한다. 현재 protocol을 과거 실행의 증명으로 대체하거나 원본 digest를 새 값으로 덮어쓰지 않는다. 기록에서 복원 가능한 실행 코드·설정·입력·checkpoint 연결을 새 감사 자료에 남긴다. 복원이 불완전한 항목은 현재 score 해석에 미치는 영향과 함께 표시한다. 원시 값·환자·질문·adapter 연결에 설명되지 않는 불일치가 있으면 해당 비교의 유효 판정을 보류한다.

# Contribution Path / Baselines / Reuse

새 기여는 미확정이다. token uncertainty, seed disagreement, Presence, P(True)의 강한 직접 비교를 정확히 확보하는 것이 이번의 의사결정 가치다. 관련 confidence 방법의 재현이나 detector 대비 우위를 이번에 주장하지 않는다.

현재 브랜치와 HEAD `9d5739203730647fd401caccc3deccd6ecbab317`를 이어간다. 필요한 파일이 모두 존재하므로 reuse_assets는 비운다.

- `rsna_diag/risk28_eval.py`: 승인된 AUROC·동점 포착률·bootstrap 계산을 재사용한다. 입력 유한성·사건 구성과 calibration 수치 검증은 별도로 수행한다.
- `run_iter028_eval_c.py`, `run_iter028_eval_e.py`: 방향·입력 검증·출력 경로를 보완한다. 과거 기본 경로로의 쓰기를 막고 명시적인 새 결과 경로를 요구한다.
- `rsna_diag/risk28.py`, `rsna_diag/risk28_source.py`: 저장 schema, 요청 ID, source 규약을 재사용한다. 중복을 덮어쓰는 load_all을 그대로 평가에 사용하지 않는다. GPU 실행기는 이번에 호출하지 않는다.
- `verify_e_independent.py`, `test_rsna_iter028.py`: 기존 검증을 참고하되 원시 logits부터 독립 계산하고 경계 동점을 정확히 처리한다.
- `rsna_diag/__init__.py`와 기존 source·parser 의존 파일은 현재 기반을 유지한다. 실제 호출하는 경로만 검사한다.

Token-NLL, EOS 포함 NLL, entropy, seed disagreement, Presence M0/B0, P(True) M0/B0를 모두 보존한다. 세 seed 비용과 재질의의 추가 forward 비용을 구분한다. Random은 임의 난수 한 번의 성적 대신 같은 검토 인원에서의 무작위 기대값을 사용한다. 기존 난수 결과는 과거 산출물로 보존한다.

# Proposed Experiment

## 1. 동작 확인과 출처 감사

새 결과 루트는 `results/iter_029/`다. 기존 C/E raw JSONL, source_manifest, protocol, worker env, launch 결과, 평가 파일 및 관련 코드의 hash를 읽어 잠근다. 과거 파일을 변경하지 않는다.

C의 실제 생성 행렬은 400명×5조건=2,000건이며 주평가는 빈 출력 199명×5조건=995건이다. E는 빈 출력 398명×5조건=1,990건이다. 전체 C의 추가 생성 1,005건은 감사 대상이며 주분석에 섞지 않는다. 예상 행렬은 source와 요청 규약에서 구성하고 관측 결과에서 역으로 정하지 않는다.

중복·누락·잉여·잘린 JSONL·비유한 값·질문 및 variant 불일치·source/adapter/protocol 연결을 검사한다. C/E 환자 중복과 현재 입력 hash를 검증한다. launch 종료 코드를 확인하고, 사후 작성하는 평가 검증 기록을 과거 생성 completion처럼 표현하지 않는다.

fixture는 Presence=logit_yes−logit_no, P(True)=logit_no−logit_yes를 직접 검사한다. Yes/No 동점, 극단값, label 반전, 대표 선택 동점 순서, 경계 score 동점, 누락·중복·출처 변조와 기존 결과 덮어쓰기 거부를 포함한다.

## 2. 가능성 탐색의 교정: C

새 GPU 탐색은 생략한다. 이미 유효한 전체 C 원시 score가 존재하고 오류가 평가 방향에 한정되기 때문이다.

빈 출력 199명 전체에서 원시 logits로 score를 재구성한다. T는 token_nll, token_nll_eos, entropy 중 raw AUROC 최대값, V는 presence_m0, presence_b0, ptrue_m0, ptrue_b0 중 최대값으로 선택한다. 동점은 해당 나열 순서를 따른다.

각 score의 Platt mapping은 C 평균·표준편차만 사용하고 비음수 slope, 평균 logistic loss와 slope L2 계수 0.01, intercept 무벌점이라는 기존 규약을 유지한다. 상수 score는 Jeffreys 보정 사건 비율을 사용한다. 목적함수·gradient 또는 경계 최적 조건, 유한성·수렴을 확인한다. calibration을 E에서 재적합하지 않는다.

기존 C 확대식을 재계산해 교정 전후 판단을 비교한다. 이는 이미 실행한 E의 역사적 진입을 다시 승인하는 절차가 아니다. C 표·선택·calibration·코드와 입력 hash를 확정한 뒤 E 평가기가 이 결과를 읽도록 한다.

## 3. 규모 확대 단계의 재집계: E

기존 E 빈 출력 398명 전체를 재사용한다. 새로운 표본·seed·생성 요청은 0건이다. C에서 확정한 대표와 calibration을 그대로 적용하고 전체 평가를 한 번 완료한다.

환자 paired bootstrap 10,000회, seed 28017을 유지한다. 개별 AUROC·Capture@20%는 95% CI, V−T와 V−seed의 AUROC 차이는 각각 97.5% CI로 계산한다. E bootstrap에서 대표나 calibration을 다시 선택하지 않는다.

Brier, 고정 10-bin ECE, category 구성, 세 seed 공통 빈 출력, 전체 valid/invalid 분모, 검토 후 잔여 사건을 보고한다. 단일 class 하위집단의 AUROC는 정의 불가로 표시한다. 퇴화 bootstrap을 조용히 버리거나 점수 0으로 바꾸지 않는다.

## 4. 독립 확인

이번에는 미실행이다. C와 E는 기존 개발 자료이며 교정본도 독립 확인이 아니다. reserve·MRI F139를 열지 않는다. 별도 독립 확인은 교정 이후 연구 가치와 필요한 정밀도를 정한 후 새 계획으로 설계한다.

## 5. 자원·예상 시간·재개

이번 CPU-only의 실제 blocker는 방향 오류로 손상된 대표 비교와 calibration이다. 이를 기존 GPU 산출물의 재집계로 해소한다. 모델 로드·GPU 사용·학습 step은 0이다. 불필요한 처리량 pilot이나 모델 재생성을 하지 않는다.

CPU 감사·통계·검증은 약 30–120분의 미실측 추정이며 시간 상한이 아니다. 초기 처리량으로 예상 완료 시간을 갱신한다. 계산 중 단계별 상태와 입력 digest를 저장하고, 동일 입력·코드가 확인된 완료 단계만 재사용한다. 최종 산출물은 원자적으로 확정하며 기존 경로가 있으면 충돌을 거부한다.

새 GPU 실행이 필요한 실제 source 불일치가 발견되면 영향 범위와 필요한 요청을 보고하고 해당 비교를 보류한다. 이번 평가 수정 중 임의로 재생성을 추가하지 않는다. 후속 GPU 계획에서는 시작 직전 메모리 확인, 두 GPU 배치, 동일 요청의 2/4 worker 또는 batch 비교, worker당 2GiB 여유와 GPU 전체 peak를 포함한다.

# Implementation Tasks for Claude

1. 기존 관련 작업의 생존 여부를 확인하고 실행 중인 소스·claim을 건드리지 않는다. 현재 branch와 변경 범위를 기록한다.
2. 기존 산출물의 읽기 전용 source 감사와 새 평가 provenance를 구성한다. C 실행 당시 protocol 복원 가능 범위는 stream·checkpoint·worker 기록으로 확인한다.
3. 의미별 score 방향과 엄격한 record 로딩을 구현하고, 새 출력 경로를 명시적으로 요구한다. 기존 protocol·report·JSONL을 재잠금하거나 덮어쓰지 않는다.
4. fixture를 통과한 뒤 C 대표 선택·calibration·확대식, E 지표·paired CI·기계 판독 decision을 순서대로 계산한다.
5. 독립 검증은 파생 c_table/e_table에만 의존하지 않는다. 원시 Yes/No 값과 GT/source에서 별도로 방향·rank AUROC·동점 포착률·대표 선택을 계산하고 주요 paired CI를 대조한다.
6. 방향 수정으로 변한 값과 유지돼야 할 token·seed 지표를 분리한다. 기존 entropy 재현값은 회귀 확인용이며 결과를 그 값에 맞추지 않는다.
7. 보고서에 실행 유효성, 위험 식별 성능, 가설 지지, 신규 기여 가능성을 나누고 교정 전후 차이·미확인 출처·독립 확인 미실행을 명시한다. GPU 실행기 전체 정비는 후속 재사용 문제로 남긴다.

# Evaluation (성공/실패 기준 포함)

평가 교정의 완료 조건은 원본 보존, 예상 행렬과 출처 확인, C 전용 선택·적합, E 적용, 독립 계산 일치 및 같은 근거를 사용하는 decision이다. 테스트 통과만으로 진단 완료나 가설 지지를 선언하지 않는다.

주지표 정의와 iter_028의 기준을 유지한다. Capture@20%는 round(0.2×n)명을 검토하며 경계 동점은 기대값으로 계산한다. C는 40/199, E는 80/398의 실제 검토 비율을 함께 표시한다. 동점으로 포착 사건 기대값이 소수가 될 수 있다. Random 기대 포착률도 정확히 k/n으로 보고한다.

- **단순 baseline 양성:** E에서 고정 score가 AUROC≥0.75, 95% CI 하한≥0.65, Capture@20%≥0.50을 충족하면 개발 조건의 유용한 위험 신호로 판단한다. token 또는 seed로 충족하면 새 confidence head/loss를 보류한다.
- **재질의 추가 정보 양성:** C 선택 V−T의 AUROC 차이≥0.10, 97.5% CI 하한>0, Capture@20%도 같은 방향이면 추가 영상 재질의의 정보 이득으로 해석한다. V−seed도 함께 보고하며 신규 방법의 증명으로 부르지 않는다.
- **음성:** 모든 score의 95% CI 상한이 기존 실용 목표에 미달하면 현재 score 집합의 제한적 음성 근거다. confidence 연구 전체나 모든 경량 학습을 기각하지 않는다.
- **불확정:** CI가 기준을 가로지르면 현재 범위를 유지한다. 새 표본이 투자 결정을 바꿀 정밀도를 제공할 때만 후속 확대를 검토한다. 단순 baseline 양성과 재질의 추가 이득 불확정은 동시에 성립할 수 있다.
- **검증 실패:** 원시 값·정답·질문·checkpoint 연결 또는 완전성에 설명되지 않는 오류가 있으면 해당 비교 판정을 보류한다. 유효한 entropy 근거까지 자동 기각하지 않는다.

교정 이후에는 외부 확인, 중요한 잔여 미검출 진단, 다른 연구 질문의 정보 이득을 비교하도록 리뷰에 전달한다. 어느 결과에서도 새 loss를 자동 예약하지 않는다.

# Risks / Checks

- E 결과는 이미 알려져 있다. 이번 수정은 원 계획 의미를 복구하는 것으로 기록하고 새 사전등록 실험처럼 표현하지 않는다.
- 전체 1,200명 감사와 빈 출력 597명 위험 분석의 분모를 구분한다. 임상 유병률·안전성·전체 grounding 오류로 일반화하지 않는다.
- calibration 개선은 순위 개선과 다르다. 선택과 calibration의 불확실성 전체를 E 조건부 bootstrap이 반영하지 않음을 적는다.
- 과거 protocol bytes 복원 실패와 실제 score 연결 오류를 구분한다. 누락된 근거를 추정으로 채우거나 현재 hash로 과거 전체 실행을 인증하지 않는다.
- 알려진 GPU 실행기 재사용 결함은 이번 CPU 분석을 위해 전면 수정하지 않는다. 관련 미해결 사항은 다음 실제 GPU 사용 전에 처리한다.

## 대규모 GPU 필요 후보

다기관 image–finding–bbox 및 일반 QA를 결합한 vision–language 공동 post-training과 미검출 위험 학습을 후보로 보존한다. 대규모 전체 모델 학습·여러 seed·외부 평가에는 추가 자원이 필요할 수 있다. 이번 진단은 필요성을 입증하지 않으며, 두 24GB GPU에서 가능한 경량 적응을 배제하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 것

- agent/GOAL.md, agent/REPORTING_STYLE.md, agent/LIMITATIONS.md, agent/CODE_ASSETS.md 및 iter_012·028 원본 리뷰, iter_028 계획과 실제 평가 소스를 확인했다.
- 현재 research HEAD는 `9d5739203730647fd401caccc3deccd6ecbab317`이며 git status와 diff --stat 출력은 비어 있다. 필요한 risk28 모듈·평가 스크립트·검증 스크립트는 현재 브랜치에 존재한다. 선별 반입은 필요 없다.
- `run_iter028_eval_c.py::build_table`은 Presence와 P(True)에 모두 `risk_no_minus_yes`를 적용한다. `risk28.py::score_yes_no`는 `logit_yes`, `logit_no`를 저장하므로 새 생성 없이 의미에 맞는 방향을 복구할 수 있다.
- C/E 평가 스크립트는 `results/iter_028/`에 결과를 직접 덮어쓰며, 평가 진입점의 입력·완료 검증이 없다. `verify_e_independent.py`는 기존 파생 표만 읽고 포착률의 경계 동점을 처리하지 않아 독립 검증을 보강해야 한다.
- iter_028 리뷰의 독립 계산에서 E entropy AUROC는 0.8224739, Capture@20%는 43/70=0.6142857이다. 교정된 Presence B0는 AUROC 0.8153746, Capture@20% 0.5755102이며 C 대표 V는 presence_b0로 변경된다. 이 수치는 이번 계획 단계에서 새로 계산한 결과가 아니라 원본 리뷰의 근거다.
- 같은 리뷰는 교정 V−entropy AUROC 차이 −0.0070993, 97.5% CI [−0.0304403, 0.0151615]를 보고한다. calibration과 정식 decision은 아직 교정되지 않았다.

## 의미와 남은 확인

부호 오류의 원인과 복구 경로가 명확하므로 추가 조사 라운드나 GPU 재생성보다 평가 교정의 정보 이득이 크다. 현재 protocol만으로 C 실행 당시 코드 전체를 증명할 수 없으므로 stream·checkpoint·worker 기록에서 복원 가능한 출처와 미확인 범위를 구분해야 한다. 기존 연구 방향 판단은 iter_028 계획·리뷰를 유지하며, 교정 이후의 큰 투자는 별도 전략 판단으로 넘긴다. 이번에는 새 문헌의 사실관계나 신규성을 주장하지 않아 문헌 재검색을 하지 않았다.
