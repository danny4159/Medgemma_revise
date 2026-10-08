# 요약

- **이번에 할 일:** LR2e-5의 직접 판독 SFT를 기존과 같은384 updates로 비교한다. R이 회복될 때만 같은 조건의 G를 실행한다.
- **필요한 이유:** 기존 R/G는 base보다 낮았다. 기존 두 LR보다 낮은 최적화 강도는 아직 비교하지 않았다.
- **확인할 기준:** 명확한 소견 recall 개선, 여러 환자의 회복, 명시적 오류와 평가 모호성을 함께 확인한다.
- **주의·다음:** 탐색용 진단이다. 낮은 LR의 실패를 위치 학습 전체의 실패로, 성공을 신규 기여로 해석하지 않는다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray PadChest-GR T512/V64와 기존 V32
- 모델: MedGemma 1.5, 표준 언어층 LoRA SFT
- 과제: 영상에서 판독문을 생성하고 조건부로 정답 소견의 위치를 출력한다
- 가설: 기존 높은 학습률의 판독 저하가 위치 보조 효과를 가렸을 수 있다
- 질문: 학습률을 낮춰 판독 baseline을 회복하면 위치 보조의 효과를 판단할 수 있는가?
- 변경: 구체화
- 연결: 기존 R/G의 낮은 판독과 선택 진단을 이어받아 아직 시험하지 않은 LR 설명 하나를 구분한다
- 작업: 같은 학습량의 R 비교 후 통과할 때만 G를 추가해 다음 투자 여부를 정한다

# Current Understanding

iter_092에서 네 trajectory는 각각384 updates까지 완료됐다. E128 recall 적격94명의 R/G/base recall은1.152%/1.684%/7.837%였다. 위치 출력 학습은 있었으나 충분한 판독 baseline 이후의 효과는 미확인이다. iter_094의 V32 후반 회복은 오류 비용까지 포함한 충분성을 입증하지 못했다. iter_095~096의 CURE 8영역 회복 후보와 의미 규칙 반복 보완은 보류한다.

iter_090 인계 작업은 완료됐으므로 오래된 checkpoint에서 재개하지 않는다. 기존 학습·선택·E128 판정은 변경하지 않는다. 이번은 새 결과 경로의 별도 LR 대조다.

# Strategy Check / 연구 방향 판단

**시험 설정:** 높은 LR의 추가 epoch·seed 대신 LR2e-5 한 조건을 시험한다. CURE v2의 LR별 위치–판독 trade-off는 이 대조의 근거지만, 우리 설정의 원인을 증명하지 않는다. prompt·target·sampling까지 동시에 바꾸지 않는다.

**연구 관찰:** 위치 출력과 판독 성능의 차이, NLL과 실제 생성의 차이는 보존한다. 선택 규칙 위반 설명은 배제됐지만 인식·선택·결합의 내부 원인은 미분리다.

**연구 질문:** 작동하는 직접 판독 baseline 이후 위치 supervision이 무엇을 바꾸는지 여전히 중요하다. 다만 CURE가 이미 최적화·sampling trade-off를 다루므로 이번 비교만으로 새 기여를 주장할 수 없다.

현재 설정 개선 / 원인 진단 / 연구 묶음 보류를 비교하면, 빠진 LR 대조는 구체적인 설명 하나를 줄일 수 있다. 따라서 같은 현상 탐구를 선택한다. 새로운 모델·자료 후보 탐색이 아니다. 직전 리뷰의 조건부 baseline 재구성 권고를 유지한다. R이 회복되지 않거나 의미 모호성이 결정을 좌우하면 이 재구성 경로를 보류한다. 다음 loss나 modality로 자동 전환하지 않는다.

지배 비용은 trajectory당 수 시간의 학습과 사례 의미 검토다. R 우선으로 불필요한 G 투자를 줄인다. 정확한 비용 절감률은 추정하지 않는다.

# Hypothesis

동일한 학습량에서 낮은 LR이 높은 LR보다 명확한 소견 회복을 보존하거나 개선할 수 있다. 회복된 R과 같은 조건의 G를 비교하면 위치 보조 CE의 제한된 효과를 더 해석 가능하게 볼 수 있다. 경쟁 설명은 수렴 부족, target 구성·prompt 불일치, 제한된 supervision, 실제 보조 CE 무효과다.

# Limitation Evidence / Correct Usage Checks

이번 baseline 가설에 해당하는 별도 validated limitation은 없다. limitation_ids는 빈 배열이며 method gate를 요청하지 않는다. iter_088의 observed 충돌 한계를 이 가설의 증거로 전용하지 않는다.

iter_092·094의 유효한 실제 출력 관찰을 사용하되 의미 평가기의 needs_fix를 유지한다. MedGemma 1.5의 기존 revision·processor·template·전처리·assistant mask·좌표·생성 cap·CE 정의를 고정한다. recovery/training_gate.json의 evidence hash와 실제 의존 소스를 연결한다. 불변 수치 검사는 재사용하고 변경된 LR·경로·resume wrapper만 추가 검사한다. 원 수치 문턱은 logits0.125, NLL0.002, gradient relative L2 0.02, 공식 CE2e-5이며 동일 shape λ=0의 결정적 일치 조건도 유지한다.

# Contribution Path / Baselines / Reuse

가까운 선행은 [CURE v2](https://arxiv.org/html/2601.15408v2)와 [MAIRA-2](https://arxiv.org/abs/2406.04449)다. 단순 LR 조정·공동 CE·위치–판독 차이 자체는 contribution이 아니다. 이번에는 직접 SFT 적합성을 판단하며 detector/grounder+reporter보다 우수하다고 주장하지 않는다.

현재 브랜치 HEAD는23a37396b79a169850f5a8fcd2c5a2c4109ffc7f이며 필요한 파일이 있으므로 선별 반입은 없다. report90_train.py, report90_recovery_train.py, report90_stable_v2.py, report90_stable.py, report90_numeric.py, report89_model.py, report86_common.py와 rsna_diag의 train/lora/sft_data/generate를 제한 재사용한다. 생성은 report94_gen.py의 격리 방식과 report90_recovery_gen.py·report90_gen.py·report90_gen_safe.py를 활용한다. 동적 patch 의존성까지 config에 기록한다.

iter_092의 report92_manifest.py·report86_common.py 승인 범위는 출처 연결이다. iter_094의 blind/check 승인 범위 역시 연결·hash 검사이지 의미 평가가 아니다. report92/94/96 의미 판정기를 범용 승인본으로 호출하지 않는다. launcher의 완료 전 세션 종료, 생성 wrapper의 중복 거부·완료 재개 검사 누락을 실제 재사용 경로에서만 보완한다.

# Proposed Experiment

## 1. 자료와 평가 규약 잠금

기존 T512/V64 manifest와 V32 환자를 그대로 사용한다. 환자·study·영상 중복 검사와 원 입력 hash를 계승한다. 새 표본을 성능에 따라 고르지 않는다. V32는 반복 개발 자료이며 독립 test가 아니다. E128은 열어 재선택하지 않는다.

새 출력 전에 V32 reference를 원문 인용과 함께 작은 사례표로 고정한다. 소견 존재·위치·속성·시간·부정 범위를 분리하고 명확한 확정 양성 fact와 평가 불가 fact를 표시한다. 위치 누락은 strict 회복이 아니며 type-only 보조로 남긴다. 양측 fact를 한쪽으로 회복 처리하지 않는다. 원인 hedge와 소견 존재 hedge를 구분한다. lateral view 의존 fact는 단일 frontal 입력에서 판정 불가로 사전 표시하며 환자 전체를 편의상 제거하지 않는다.

일반 정상문, no acute, no other, resolved, 위치 누락, 양측/한쪽, 원인 불확실성을 다루는 대조 사례를 먼저 검사한다. 현재 facts와 출력 span의 대응표를 사용하며 새 범용 NLP 평가기를 만들지 않는다. 오류는 reference가 명시적으로 반박하는 주장과 미지원·판단 불가 주장을 분리한다. reference에 없다는 이유만으로 hallucination으로 확정하지 않는다.

## 2. 동작 확인

새 iter_097 wrapper에서 결과·runtime cache·config를 격리한다. 기존 trainer와 과거 config는 수정하지 않는다. LR2e-5의 새 base 초기화, optimizer LR, seed·batch 순서·loss 가중치를 검증한다. 작은 기존 기술 입력으로 1 update 및 중단/재개 연결을 확인하고 기술 checkpoint는 본학습에 섞지 않는다. 과거 원자료·cache를 덮어쓰지 않는다.

## 3. R 가능성 탐색

T512, seed17, rank16/alpha32/dropout0.05, effective batch8, 검증된 microbatch1, 기존 optimizer·정밀도·stable_v2 연산을 사용한다. R의 위치 CE 가중치는0이며 기존과 같은 전체 입력을 유지한다. 변경은 LR2e-5와 새 결과 경로다.

R을 epoch6, 총384 updates까지 실행한다. NLL은 기존 평가 시점1/2/4/6의 V64로 기록한다. 생성은 epoch2와6의 V32 각32건이다. epoch2 결과는 추세 기록이며 성능으로 중간 종료하거나 checkpoint를 선택하지 않는다. 기술 실패·비정상 수치는 즉시 처리한다.

주대조는 고정 epoch6의 base, R LR1e-4, R LR2e-4다. 저장 출력이 같은 조건이면 재사용하고 LR1e-4 epoch6의 V32 결측만 최대32건 생성한다. 모든 조건을 이번 고정 의미 규약으로 비교하되 과거 수치는 덮어쓰지 않는다.

## 4. 조건부 G 비교

아래 R 가능성 기준을 충족할 때만 G를 동일 새 base 초기값·LR2e-5·384 updates로 학습한다. R과 같은 환자 순서·입력·report target·optimizer 조건을 유지하고 위치 CE 가중치만1로 바꾼다. G도 epoch2/6 V32 출력을 생성하고 주비교는 epoch6다. R/G/base의 기존 V16 보조 grounding은 동일 prompt·IoU@0.3으로 비교하며 동일 출력이 없을 때만 생성한다.

## 5. 규모 확대와 독립 확인

이번 최대 규모는 R/G 각384 updates다. 낮은 LR의 학습 부족 가능성이 있어도 epoch12·추가 seed·다른 LR을 자동 실행하지 않는다. 양성 탐색이면 full review에서 독립 환자 비교 또는 method pilot 가치를 별도로 판단한다. 이번 V32를 독립 확인이라고 부르지 않는다.

# Implementation Tasks for Claude

1. 기준 원본은 iter_097 think/round_01.json, iter_092/094/096 review.json과 recovery/training_gate.json이다. 완료된 인계를 반복하지 않는다.
2. 새 wrapper와 protocol에 LR·출력 루트·의존 소스 hash·자료 hash·평가 규약·분기 기준을 잠근다. 과거 training_gate의 단순 passed 복사 대신 불변 증거와 이번 변경 검사를 구분한다.
3. 실제 사용하는 생성 경로에서 소스/config 변경·중복 실행·완료 파일 변조 거부, 고유 요청 ID·shard 누락/중복·resume를 검사한다. 조건별 결과 파일을 분리한다.
4. reference 사례표를 먼저 완성하고, 새 출력은 조건명을 제거한 화면에서 원문 span과 연결한다. assistant 검토를 독립 평가자나 전문의 검토로 쓰지 않는다. 모든 회복·소실·반박·판단 불가 사례에 실제 설명을 남기며 일괄 reviewed=true를 사용하지 않는다.
5. R 실행 및 사전 분기 판정, 조건부 G 실행을 supervisor로 관리한다. checkpoint에 adapter/optimizer/RNG/다음 batch/pending validation을 보존한다. 기존32 updates·epoch 경계 저장을 계승한다.
6. 프로그램 완료 대기를 사용하고 supervisor가 pending인 동안 최종 완료 응답을 내지 않는다. 실제 종료 code·완료 hash·요청 수를 확인한다.
7. 원시 대응표에서 별도 집계로 recall·오류·분기를 재계산한다. 연결·산술 검사 통과와 의미 타당성은 구분한다. 보고서와 모든 신규 결과는 results/iter_097에 저장한다.

# Evaluation (성공/실패 기준 포함)

주지표는 명확한 확정 양성 reference fact를 가진 환자의 macro strict recall이다. type-only recall, 명시 반박 환자 수, 미지원 주장·판단 불가 환자 수, 형식 실패와 일반 정상문 빈도를 따로 보고한다. 일반 정상문을 자동 정상 판독으로 승인하지 않는다.

**R→G 가능성 기준:** epoch6 저LR R은 base와 두 고LR epoch6 R 각각에 대해 strict recall이 최소5pp 높아야 한다. 각 비교에서 recall 증가 환자 수−감소 환자 수가 최소3명이어야 하며, 한 환자 제거 시 차이의 방향이 양수여야 한다. 명시 반박 환자는 각 비교보다 최대1명까지만 증가할 수 있다. 이는 V32의 탐색 투자 문턱이며 임상 비열등성 기준이 아니다. 모호한 회복을 모두 제외하고 명백히 가능한 반박을 포함하는 보수적 판정에서도 통과해야 한다. 그 범위를 원문으로 정할 수 없으면 불확정이다. 가정적으로 모든 미지원 주장을 참/거짓으로 만드는 비현실적 경계는 사용하지 않는다.

환자 bootstrap10,000회·seed97017의95% CI와 환자별 변화표를 보고하되 CI 하한>0을 탐색의 일률적 hard gate로 요구하지 않는다. NLL 감소만으로 G를 실행하지 않는다.

**양성:** R 기준 통과 시 G를 실행한다. G−R도 recall 최소5pp, 순증가 최소3명, leave-one-out 양의 방향, 명시 반박 증가 최대1명 및 의미 민감도 보존을 충족하면 제한된 양성 탐색으로 기록한다. 독립 확인과 강한 대안 비교의 투자 가치를 후속 리뷰에서 판단한다.

**음성:** R이 회복하지 못하거나 명백한 오류 증가가 기준을 넘으면 G를 실행하지 않고 현재 LR 재구성을 보류한다. R은 회복하지만 G 이득이 없거나 악화되면 직접 판독 baseline 자산을 보존하고 현재 위치 보조 CE의 추가 투자를 보류한다. 위치 학습 전체의 무용성으로 확대하지 않는다.

**불확정:** 개선이 작거나 수렴·의미 모호성이 결정을 좌우하면 이번 범위에서 종료한다. NLL4→6과 생성2→6의 방향을 함께 보고하되 추가 epoch를 처방하지 않는다. 재개에는 어떤 추가 근거가 판단을 바꿀지 명시해야 한다. 같은 V32의 규칙 탐색을 반복하지 않는다.

# Risks / Checks

- 두 GPU를 사용하되 의존성이 있는 R→G를 불필요하게 병렬화하지 않는다. R 학습 중 다른 GPU는 고LR baseline 결측 생성·기술 검사에 배정한다. 생성 shard는 두 GPU로 나눈다. 독립 작업이 끝나면 GPU를 채우기 위한 실험을 만들지 않는다.
- 실행 직전 nvidia-smi와 허용 GPU의 물리/논리 대응을 확인한다. 과거 학습 peak13.51GiB·추론10.61GiB와 worker당2GiB 여유를 합산하면 동일 GPU 두 worker는24GiB를 초과한다. 따라서 기존 microbatch 비교·단일 worker 근거를 재사용한다. 새 실측이 이 조건과 다르고 안전 여유·독립 작업이 있으면 development 입력에서 batch 확대 또는 복수 worker 중 유망한 하나를 비교해 처리량·긴 출력·정합성·OOM으로 선택한다.
- 과거38–42초/update 기준 R 약4.1–4.5시간, 조건부 G도 비슷하다. 최대 학습 약8.1–9.0 worker-hours에 validation·적재·생성·의미 검토가 추가된다. 첫 실제 update 묶음으로 추정치를 갱신하며 시간 상한으로 사용하지 않는다.
- prompt와 target 형식 차이는 유지되므로 LR 대조의 결과가 이를 해소했다고 주장하지 않는다. foundation의 학습 노출과 임상 reference 완전성은 미확인이다.
- 기본 환경·hf_cache는 변경하지 않는다. 필요한 격리 설치는 먼저 알리고 승인된 정책 안에서 진행한다. HF_TOKEN_PATH 값은 출력하지 않는다.
- **대규모 GPU 필요 후보:** 여러 backbone·충분한 판독 학습량·학습 범위·sampling을 교차 비교하는 연구를 보존한다. 이번 결과만으로 full fine-tuning을 자동 처방하지 않는다.

# 계획의 근거 (GPT 조사 노트)

이전 round_01.json 원문과 iter_092/094 review.json, iter_091의 수치·메모리 검증 기록, report90_train.py·report90_recovery_train.py·report90_stable_v2.py·report89_model.py·report94_gen.py 및 recovery/training_gate.json을 확인했다. 현재 HEAD는 23a37396b79a169850f5a8fcd2c5a2c4109ffc7f이며 작업 트리는 깨끗하다.

첫 질문: T512/effective batch8은 epoch당64 updates이며 기존 trajectory는384 updates다. LR2e-5도384 updates에서 비교하고 epoch2/6만 생성하면 동일 학습량과 추세를 분리할 수 있다. 낮은 LR의 수렴 충분성은 보장하지 않으므로 추가 학습 없이 불확정 범위를 남긴다.

둘째 질문: 기존 자동 의미 판정을 승인하지 않는다. 생성 전에 V32 reference를 원자 단위로 고정하고 명확한 회복·명시적 반박·판단 불가를 분리한다. 일반 정상문을 자동 안전 또는 자동 모순으로 처리하지 않으며, 모호한 사례가 확대를 결정하면 보류한다. 작은 사례표와 인용 검토로 한정하고 범용 평가기를 만들지 않는다.

셋째 질문: R 우선이 낫다. 기존 R 자체가 약하므로 G를 동시에 학습하면 핵심 blocker를 해결하지 못한 채 학습 비용을 두 배로 쓸 수 있다. R 학습 동안 다른 GPU에서 필요한 기존 baseline 결측 생성·기술 검사를 처리한다. 조건부 G 학습 후 생성 shard는 두 GPU에 배정한다. 과거 training peak13.51GiB와 inference peak10.61GiB에 worker당2GiB를 더하면 같은 GPU의 두 worker 배치는24GiB를 초과하므로 현재 구성 재사용이 타당하다.

문헌은 앞 라운드가 확인한 CURE v2 Table15/§9.3.3(https://arxiv.org/html/2601.15408v2)와 MAIRA-2(https://arxiv.org/abs/2406.04449)를 계승한다. 새 문헌 재조회나 모델 호출은 하지 않았다. 파일 변경·실험 실행은 없었다.

이전 사고 라운드 노트: agent/runs/iter_097/think/
