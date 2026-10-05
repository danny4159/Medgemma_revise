# 요약

- **이번에 할 일:** iter_075의 실행 복구와 미완료 F/R/C/H 비교를 끝낸다.
- **필요한 이유:** 자료·C/H 선택은 있으나 VLM 본학습과 E24 평가가 없어 과학적 판단을 하지 못했다.
- **확인할 기준:** 필수 기술 검사 통과, 원 학습·평가 완결, 원 판정 기준과 독립 재계산이다.
- **주의·다음:** OAI 중단·기존 자산 보존을 유지한다. 새 결과는 results/iter_076에 기록하며 방법 효과·신규성은 자동 승인하지 않는다.

# Current Understanding

기준 문서는 agent/runs/iter_075/plan.md이며 SHA256은 `ea40768f17ae65b10f0027ca9ca9423205bb106198ebf891af7ec0bf17a73b8b`다. Claude는 원문 전체와 iter_075/review.json을 읽는다. 과학적 조건은 원 계획을 상속하고 이번 문서는 실행 복구·새 결과 경로·검증 보완만 규정한다.

**유지:** manifest, 기술 제외, 환자·위치 split, 영상·grade·prompt·parser, baseline, 학습 recipe, 선택·연장·종료 기준, C/H 선택과 OAI 중단 지시.

**변경:** 동결 증거, loss gate 재사용, 재개 검사, GPU 배치 확정, 사전 선택 잠금, 완료 흐름 및 새 출력 경로.

**미완료:** A validation/B 재개 검사, 네 VLM trajectory, V8 생성·선택·조건부 연장, E24와 비용 및 독립 검증.

# Strategy Check / 연구 방향 판단

iter_075의 전략 판단을 유지한다. 현재 새 관찰은 실행 중단이며 인식·선택·결합의 과학적 반증이 아니다. 남은 설명은 위치 prior, 기본 판독 적응 부족, 대상 지정·해상도, 공유 분류기 충분성이다. 최소 비교는 이미 설계된 F/R/C/H다. 이 비교가 바꿀 결정은 현재 부위별 판독에 VLM 방법 투자를 할 가치가 있는지 하나다.

새 자료 탐색보다 기존 준비 자산을 사용한 완료의 정보 가치가 높다. 타 계열 학습은 원 계획대로 이번에는 보류한다. 큰 방법 투자 전에는 별도 확인을 판단한다. 준비·검증·재작업이 직전 반복의 주요 작업이었으며 정확한 비용 비율은 미산출이다.

# Hypothesis

원 계획 H1–H4를 유지한다. 다른 위치로 영상 판독이 전이되고 모듈형 대안 이후 가치가 남는 경우, 모듈형으로 충분한 경우, R만 강한 경우, 모든 시스템의 적응이 부족한 경우를 구분한다. F/R 차이만으로 순수 선택 실패나 다중 영상 결합을 주장하지 않는다.

# Limitation Evidence / Correct Usage Checks

이번 Pfirrmann 과제의 유효 한계 관찰은 아직 없으므로 limitation_ids는 비운다. MRI context observed 주장을 방법 개발 근거로 전용하지 않는다.

기존 공식 3영상 입력·assistant-only label·공식 loss 대조·LoRA 항등 및 기술 과적합 근거는 입력과 의존 코드가 불변이면 재사용한다. 변경된 경로만 회귀 검사한다. 5/5 기술 과적합은 일반화 근거가 아니다.

직전 리뷰의 빈 SHA256 설명에는 부정확함이 있다. 실제 parameter 집합·byte 수를 조사해 별도 정정하고 과거 리뷰는 보존한다. hash 두 개가 같다는 이유만으로 동결을 통과시키지 않는다.

# Contribution Path / Baselines / Reuse

기여·VLM 가치 모두 미확정이다. 가장 가까운 대안은 원 계획에서 확인한 직접 SFT, 공유 ROI ResNet18, SPIDER radiomics다. 새 문헌 전수 조사는 하지 않는다.

현재 브랜치 HEAD `31f4bb49b6169d78b0bfaedb95fff0fb27e392ac`를 이어간다. `sp75_metrics.py`는 제한 승인이고 나머지 학습·평가 경로는 needs_fix다. 필요한 파일은 현재 존재하므로 reuse_assets=[]다.

수정 대상은 `sp75_train.py`, `sp75_resume_test.py`, `sp75_tech.py`, `sp75_pipeline.py`, `sp75_gen.py`, `sp75_eval.py`, `sp75_cost.py`, `sp75_verify.py`, `test_sp75.py`와 실제 영향이 있는 `sp75_vlm.py`, `sp75_data.py`, `rsna_diag/train.py`, `rsna_diag/lora.py`, `rsna_diag/queue_lock.py`다. `sp75_c.py`, `sp75_h.py`의 기존 선택은 검증 후 읽기 전용 재사용한다. 무관한 과거 경로는 수정하지 않는다.

# Proposed Experiment

## 1. 보존·복구 범위 고정

호스트의 PID·명령·시작 시각·GPU UUID와 lock 소유권을 확인한다. 계획 세션의 제한된 ps 결과로 잔존 작업이 없다고 가정하지 않는다. 다른 사용자 프로세스는 건드리지 않는다.

iter_075 결과는 그대로 보존하고 새 ledger·검사·학습·평가는 `results/iter_076/`에 쓴다. 기존 data와 C/H는 출처·hash로 연결한다. 기존 ref/A 복구가 필요하면 가변 checkpoint와 로그를 새 경로로 복사하고 원본 hash를 기록한다. 원본을 수정하는 hardlink를 사용하지 않는다.

코드 변경에 따른 train_digest 불일치는 검사를 삭제해서 해결하지 않는다. 원 config·checkpoint·입력·adapter·optimizer·RNG를 먼저 대조하고 허용된 실행 복구 변경만 명시한 migration 기록을 만든다. 학습 의미가 달라진 기존 trajectory를 동일 실행으로 위장하지 않는다.

## 2. 필수 기술 복구

- **동결:** LoRA parameter 객체와 비LoRA parameter를 정확히 분리한다. 이름 정규화 충돌, parameter 수·numel·byte 수 0을 거부한다. 비LoRA requires_grad=False, optimizer 미포함, 실제 update 전후 전체 byte digest 일치와 LoRA 변화가 함께 있어야 PASS다. 재사용 가능한 기존 항등·과적합 전체를 불필요하게 반복하지 않는다.
- **loss gate:** PASS 상태, 유한 수치, 공식 loss 상대오차1e-6와 유효 token 수, 모델·입력·코드 provenance를 검사한다. 실패·손상·불일치 파일은 학습을 차단한다. 기록은 원자적으로 저장하고 파일 존재만으로 통과시키지 않는다. 실패 gate의 재실행 우회와 변조를 실제 진입점으로 검사한다.
- **재개:** 기존 ref/A의 완료 step과 validation을 재사용하고 A의 미완료 validation·B를 보완한다. 중간 step 및 epoch checkpoint 직후 중단에서 adapter·optimizer·RNG·LR·batch 순서·다음 step·validation 상태를 확인한다. 중복/누락 step과 validation의 학습 상태 변경은 허용하지 않는다.
- **수치 차이 분리:** ref/A는 중단 전 step2부터 달랐으므로 loss 차이만으로 복구 결함이라고 하지 않는다. 같은 장치·동일 초기 checkpoint·같은 batch와 RNG에서 짧은 연속/저장복구 대조를 실행한다. 결정적 연산 설정을 기술 검사에 적용하고 최초 불일치의 logits/loss/gradient/update를 추적한다. 상태 복원은 정확히 일치해야 한다. 연속 반복도 달라지는 경우 이를 별도 기록하며 사후 허용오차 확대로 통과시키지 않는다. 결정적 경로에서도 복구 후 차이가 남으면 본학습을 막고 결함을 수정한다. 기술 검사 설정과 본실행 설정의 차이도 기록한다.
- **완료 판정:** 검사 결과에 명시적 PASS/FAIL과 비정상 종료 코드를 넣는다. 정상 return code만으로 출력 완전성을 대신하지 않는다.

## 3. GPU 배치와 가능성 탐색

원 effective batch8을 유지한다. 기존 micro1/micro5 비교는 4.77% gradient 차이가 있어 micro5를 자동 채택하지 않는다. dropout·padding·loss 정규화·수치 kernel의 영향을 기술 입력에서 구분한다. batch 확대 시 마지막 불완전 batch까지 예제·token 가중치와 update 수를 보존한다.

기존 peak allocated는 micro1 약10.12GiB, micro5 약17.35GiB이며 전체 점유가 아니다. 실행 직전 nvidia-smi로 실제 여유가 큰 허용 GPU부터 배치한다. 두 GPU에 독립 trajectory를 배정한다. 안전 여유가 있으면 micro1 두 worker/GPU 또는 effective batch8에 맞는 batch 확대 중 유망한 구성 하나를 짧게 비교한다. 실제 총 peak와 worker당2GiB 여유가 충족되지 않으면 두 worker를 실행하지 않는다. 처리량·오류·정합성으로 선택하고 GPU당1개 유지 시 측정 근거를 남긴다.

기술 제외 후 train70개로 epoch당9 updates다. F/R 각각 LR2e-5·2e-4, seed17, rank16/alpha32/dropout0.05, AdamW·weight decay0.01·clip1과 원 32-epoch horizon의 warmup/cosine을 유지한다. epoch8·16에 V8 24개 생성·CE를 평가한다. 방식별 LR 선택과 동률 규칙은 원문을 그대로 적용한다. 선택 trajectory의 epoch8→16 CE가5% 감소하거나 primary MAE가0.10 개선되면 epoch32까지 한 번 연장한다. epoch32만 추가 평가한다.

## 4. 선택 잠금·평가·비용

C의 LR1e-4·epoch40, H의 config1 선택은 hash와 실제 checkpoint 연결 확인 후 유지한다. 재학습·재선택하지 않는다.

첫 E24 출력 전에 F/R/C/H 선택 checkpoint, 전처리·prompt·parser·metric, 입력 manifest·환경·코드 및 선택 근거를 고정한다. 생성 출력은 사전 잠금에 포함하지 않고 완료 후 별도 seal로 묶는다. 실행기는 잠금 불일치를 거부한다.

E24 118행(학습 위치71, 미제공 위치47)을 평가한다. base F/R 및 선택 F/R의 신규 최종 생성은472건이다. 기존 whole-string parser와 greedy32 token, invalid 오차4, 보조 후보 likelihood를 유지한다. 후보 scoring을 primary로 바꾸지 않는다. C/H·prior·고정 ordinal 내 예측 교환을 함께 계산한다.

원 T2 읽기부터 답변 저장까지 네 paired 비용 block을 V8의 원 고정 workload로 측정한다. loading 포함/제외, H feature 추출과 C 전체 영역 처리·조회, GPU device 시간과 wall-clock을 구분한다. GT anatomy 확보 비용은 미측정이라고 적는다.

## 5. 규모·시간·종료

최대864 updates, V8 기본192건과 조건부48건, 최종472건이며 기술·비용 호출은 별도 ledger에 집계한다. 원 초기3–10시간은 불확실한 추정이다. 기존 micro 측정은 optimizer·validation·전체 동시 비용을 포함하지 않으므로 본 trajectory 초기 실측 update/s와 생성 처리량으로 잔여 시간을 갱신한다. 임의 timeout은 두지 않는다.

이번 확대는 원 validation 기반 epoch32까지다. 추가 seed·환자·F139·새 VLM·sequence와 독립 확인은 이번 범위 밖이다. checkpoint에는 원 상태와 완료 validation·출력 ID를 보존한다. background 자식의 종료·반환값·출력 완전성을 확인하기 전에 구현 세션을 완료하지 않는다. 실제 장애가 생기면 안전한 checkpoint와 정확한 미완료 범위를 보고한다.

# Implementation Tasks for Claude

1. 기준 계획 hash와 현재 소스·결과·호스트 작업 상태를 확인하고 복구 manifest를 만든다.
2. 위 동결·loss gate·재개와 코드 변경 provenance만 수정하고 실제 실행 경로의 회귀 검사를 수행한다.
3. 기존 데이터·C/H·완료 기술 검사를 연결하고 새 결과 경로를 인자로 분리한다. 기존 결과에 쓰는 hardcoded 경로를 차단한다.
4. launcher에 안전한 GPU 배치, 소유권·중복 방지, 네 학습·V8 선택·연장·사전 잠금·E24·비용의 완료 흐름을 연결한다.
5. 변경된 학습·평가 경로를 검증하고 원 기준으로 전체 비교를 실행한다. 동일 hash의 불변 기하·자료 검사를 반복하지 않는다.
6. 원시 응답에서 주지표·CI·판정 flags를 독립 재계산한다. C/H 예측의 중복·누락도 명시적으로 거부한다. 원 계획의 0.10 이하 등 경계 조건이 코드와 일치하는지 검사한다.
7. 보고서에 기술 복구, 실제 사용량, 가설 결과, 비용, 남은 한계·종료 결정을 분리한다.

# Evaluation (성공/실패 기준 포함)

Primary는 ordinal2/4의 class-standardized MAE이며 grade별 동일 가중, invalid 오차4다. 원 일반 MAE·macro-F1·큰 등급 오류·invalid·학습 위치 분석도 유지한다. 환자 paired bootstrap10,000회·seed7501을 사용하고 class 누락 replicate의 처리·개수를 보고한다. 누락 class를0으로 채우지 않는다.

**양성 후보:** F 또는 R의 primary≤1.0, prior 및 교환보다 각각≥0.20 개선, C보다≥0.20 개선을 요구한다. H보다0.10 넘게 나쁘면 실용 우위는 미확정이다. CI가0을 포함하면 확증으로 부르지 않고 유용한 이득·손해를 모두 포함하면 불확정으로 남긴다. 후속 방법 시험은 별도 판단이다.

**음성 투자 판단:** C가 기본 영상 신호를 보이고 best VLM보다 MAE가0.10 이상 나쁘지 않으며 네 block 모두 전체 시간이 절반 이하이면 원 대안 충분성 후보 기준을 적용한다. 정확도 CI가±0.20의 유용한 차이를 넓게 포함하면 충분성을 확정하지 않는다. 현재 oracle 영역 VLM 투자 보류와 MRI 전체 기각을 구분한다.

**불확정:** 모든 시스템의 적응 부족·환자 변동·입력 충분성이 남으면 허용한 연장 후 종료한다. E24를 보고 조건을 바꾸지 않는다. R만 강한 차이는 해상도·context·대상 지정이 얽힌 관찰이며 모듈형 대비 가치 없이 새 방법을 발주하지 않는다.

**기술 실패:** gate·ID·loss·재개·누수 결함은 해당 경로를 막는다. 수정 불가하면 정확한 blocker와 산출물을 남기며 과학적 실패로 해석하지 않는다.

# Risks / Checks

- 기존 환자·grade 분포는 개발 자료이며 독립 test가 아니다.
- ordinal은 실제 해부학 이름이 아니다. supervision 미제공 위치 전이를 미관측 anatomy 일반화로 부르지 않는다.
- 세 slice의 임상 충분성과 사전학습 노출은 미확인이다. H는 더 많은 관측 정보를 쓴다.
- 입력·학습 의미가 달라지는 수정은 단순 provenance migration으로 숨기지 않는다.
- 호스트 작업 확인, 원본 보존, checkpoint 복구와 모든 자식 프로세스 완료를 확인한다.
- OAI·MR-RATE 대기 및 신규 frozen 후보 탐색을 재개하지 않는다.

## 대규모 GPU 필요 후보

여러 위치·기관의 영역별 임상 supervision을 공유하는 vision encoder–connector–language 공동 적응 후보를 보존한다. 이번 비교는 그 필요성이나 신규성을 승인하지 않는다.

# 계획의 근거 (GPT 조사 노트)

원문 agent/runs/iter_075/plan.md·review.md·review.json·claude_report.md, GOAL, CODE_ASSETS의 iter_075 항목, LIMITATIONS의 MRI context 항목과 현재 실행 소스를 확인했다. 기준 계획 SHA256은 ea40768f17ae65b10f0027ca9ca9423205bb106198ebf891af7ec0bf17a73b8b이며 실제 계산과 일치한다. research HEAD는 31f4bb49b6169d78b0bfaedb95fff0fb27e392ac이고 git status는 깨끗하다. 필요한 모듈이 현재 브랜치에 있어 별도 반입은 필요 없다.

기존 ref/A checkpoint와 epoch adapter는 존재하지만 A epoch2 validation, B 및 최종 비교 파일은 확인되지 않았다. 계획 세션의 ps는 격리된 namespace만 보여 호스트 잔존 프로세스 부재를 확정하지 못했다. 구현 시작 때 실제 호스트와 GPU에서 다시 확인해야 한다.

sp75_train.py는 loss gate 파일 존재만으로 검사를 생략하고 코드 hash가 바뀌면 기존 checkpoint 재개를 거부한다. 따라서 안전한 명시적 복구 provenance 연결 없이 hash 검사를 제거해서는 안 된다. sp75_pipeline.py는 학습 worker 수를 GPU당1로 고정하고 V8 생성까지만 제공하므로 선택·조건부 연장·최종 평가의 완료 흐름을 실제로 연결해야 한다.

tech_F.json의 micro1/micro5는 5예제당8.764/7.785초, peak allocated10.117/17.352GiB, gradient 상대 차이0.047704다. 총 GPU 점유가 아니며 micro5를 바로 본학습에 채택할 근거는 아니다. effective batch8을 유지해야 한다.

직전 리뷰의 'e3e19f4387647450은 빈 SHA256 prefix'라는 설명은 정확하지 않다. 표준 빈 입력 SHA256은 e3b0c44298fc1c14로 시작한다. 기존 hash만으로 동결 검사를 인정하지 않는 판단은 유지하되, 실제 parameter 열거·byte 수와 전후 동일성을 검사하여 원인을 확인한다. 과거 리뷰를 덮어쓰지 않고 별도 정정한다.

OAI 중단 지시는 iter_075 전략에 이미 반영됐다. 이번은 이를 유지하는 한정 복구이므로 문헌·자료 선택을 재시작하지 않는다.
