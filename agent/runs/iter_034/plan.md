# 요약

- **이번에 할 일:** detector 실행·재개·평가 결함을 수정하고 RSNA detector–LoRA 비교를 완료한다.
- **필요한 이유:** detector 탐색은 개선됐지만 본학습과 공정한 비교가 끝나지 않아 다음 투자 판단이 막혀 있다.
- **확인할 기준:** 실제 학습 경로의 재개, 충분한 학습, validation 선택, paired 정확도·FP·상보성·비용 평가를 완료한다.
- **주의·다음:** VinDr 승인 대기를 유지한다. 기존 LoRA·탐색 출력은 보존하며 800명은 개발 비교로 보고한다.

# Current Understanding

iter_009의 RSNA 정상 사용 한계와 iter_012 직접 LoRA의 개선은 유지한다. iter_033 탐색 train600·450 update에서 V100 양성 50명의 F1@0.3은 0→0.4113으로 개선됐다. 본학습은 현재 저장 로그 기준 594/7,800 update이며 최종 비교가 없다. 이 탐색 수치를 다른 집단의 SFT 점수와 직접 비교하지 않는다.

사용자 보완 `20260929_131450_4dda5b89`를 계속 적용한다. GOAL·MedGemma 1.5·기존 SFT·분할·결과를 유지하고, iter_032 외부 전이 계획은 승인 대기로 보존한다. VinDr 승인 통지 전 접근·다운로드·외부 본평가를 하지 않는다. MRI F139·reserve·새 loss·continuation은 열지 않는다.

이번 변경은 실행 수명, 증강 RNG, 실제 재개, 필수 provenance와 평가 완성이다. 기존 core recipe·표본·선택·확대 기준은 유지한다. 모든 신규 결과는 `research/results/iter_034/`에 저장한다.

# Strategy Check / 연구 방향 판단

iter_033 계획과 리뷰의 전략 비교가 여전히 유효하다. 중요한 질문은 위치 출력의 추가 post-training이 실제 전용 대안에 비해 어떤 이점을 주는가이다. SFT의 검출 개선은 확인됐지만 정확도·비용 우위와 상보성은 미확인이다.

현재 grounding 개선은 빠진 비교군 때문에 투자 근거가 약하다. detector 비교 완료는 같은 자료와 저장 출력으로 이 불확실성을 직접 줄인다. 외부 전이는 승인 대기이며 언어·근거 과제 전환은 별도 정답과 사용 목적이 필요하다. 이번은 승인된 비교의 복구이므로 전략 탐색을 다시 시작하지 않는다. 완료 후 정확도·비용·상보성에 따라 계속·외부 확인·질문 전환을 판단한다.

# Hypothesis

충분히 적응한 전용 detector와 기존 직접 SFT 사이에는 후속 연구 선택을 바꿀 정확도·FP·비용 차이 또는 조건별 오류 상보성이 있을 수 있다. 방향은 미리 가정하지 않는다. 알려진 detector를 학습하는 목적은 비교 진단이며 새로운 방법 개발이 아니다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`은 validated다. iter_009 양성 200명 중 정상 prompt 공통 불일치 134명, iter_012 SFT F1@0.3 0.631–0.653의 범위를 유지한다. `rsna-partial-omission-continuation`은 observed이며 회복과 FP 악화를 함께 보고한다.

MedGemma revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, 기존 concise·greedy·출력 길이·EOS·parser·adapter를 유지한다. 비용 측정 전에 실제 입력의 전체 tensor key/shape/dtype/value와 공식 구성, 기존 suffix 재현을 확인한다.

detector는 RGB 0–1, pixel xyxy, 내부 resize·normalization, 반환 원본 좌표와 기존 정규화 yxyx 변환을 검사한다. 원본 영상·GT 연결, 빈 GT, flip, 비정사각 padding과 실제 overlay를 확인한다. 기존 geometry 검사와 환경·overfit 결과는 source hash와 조건이 같으면 재사용하고 변경 영향을 받는 검사만 다시 한다.

# Contribution Path / Baselines / Reuse

비교군은 iter_033과 같다. Faster R-CNN ResNet-50 FPN v2 COCO_V1의 2-class predictor와 전체 backbone 적응, 기존 base 두 prompt, SFT seed17·29·43이다. 주비교는 detector seed17−SFT seed17(B0)이다. annotation은 train2,400명으로 같지만 사전학습·해상도·학습 범위·계산량은 다르다. 동일 epoch를 공정한 계산량으로 주장하지 않는다. GT union은 진단용 상한이다.

현재 `approach/rsna-detector-comparison`을 유지한다. `reuse_iteration=0`, `reuse_assets=[]`이며 새 기반이나 다른 commit 반입을 요청하지 않는다. 현재 `rsna_diag/{geometry,parse,metrics,sft_eval,det_match,generate,lora,prompts,queue_lock,lock_protocol,risk28_eval,risk30_eval}.py`와 `__init__.py`를 필요한 범위에서 재사용한다. geometry의 제한 승인을 전체 detector 승인으로 확대하지 않는다.

현재 `results/iter_033/`의 `detector_lib.py`, `run_detector.py`, `run_natten.py`, `build_manifests.py`, `eval_on_manifest.py`, `eval_confirm800.py`, `analyze_confirm800.py`, `select_threshold.py`, `select_fp_budget.py`, `latency_bench.py`, `env_check.py`, `tests/test_det_geometry.py`, `tests/test_det_match.py`는 보존된 원본이다. 구현 시작 시 각각 bytes SHA256·경로·의존성을 기록하고 원본을 유지한 채 `research/`의 추적 가능한 소스·검사 경로로 편입한다. 새 구현으로 대체하거나 results를 강제로 Git에 포함하지 않는다. 새 위치의 import와 CLI를 검증하고 실행별 source digest를 연결한다. commit·branch 관리는 orchestrator가 수행한다.

# Proposed Experiment

## 0. 실행 상태 확인과 보존

실행 호스트에서 기존 task·PID/starttime·명령행·lock·checkpoint·자식 종료 코드를 확인한다. 현재 lock의 PID만으로 소유권이나 생존을 확정하지 않는다. 살아 있는 작업과 중복 실행하거나 실행 중인 소스를 수정하지 않는다. 기존 작업이 남아 있으면 소유 상태와 안전한 종료·checkpoint 경계를 확인한 뒤 수정본을 별도 경로에서 실행한다. 타인의 프로세스는 건드리지 않는다.

짧은 subprocess timeout을 제거하고 장시간 child를 소유·감시하는 경로를 사용한다. 주기적으로 진행량과 자원을 수집하고 실제 종료 코드를 회수한다. 예약 wakeup이나 background 시작만으로 최종 응답을 반환하지 않는다. 완료 또는 구체적인 안전 중단까지 진행한다. 실패한 attempt와 원본 report는 덮어쓰지 않는다.

기본 Python은 medgemma를 유지하고 detector만 기존 `/home/test/.conda/envs/natten_py310/bin/python`을 사용한다. 환경 설치·혼합·hf_cache 수정은 없다. 실행 호스트의 환경 버전과 공식 가중치 hash를 기존 기록에 연결한다.

## 1. 입력·선택 규약 고정

기존 train2,400/validation400/개발비교800과 D32·overfit8·train600·V100·L64 ID를 유지한다. 이미 결과를 본 subset을 면적 층화 때문에 다시 뽑지 않는다. 원 계획과 다른 면적 층화 누락을 기록하고 train 기준 면적 분포·희귀층 대표성을 보고한다. 전체 학습과 최종 층별 평가는 모든 적격 환자를 포함한다.

현재 전체 3,600명 file/pixel hash, 가능한 SOP 연결, 환자·pixel 중복, GT manifest를 검증한다. SOP 자료가 없으면 정확한 미검증 범위를 명시한다. 중복·불일치를 조용히 제외하지 않는다. 기존 base와 세 SFT의 예상 환자×prompt×seed 집합, 중복·누락·완료 상태·adapter·원본 protocol 연결을 검증하고 기존 주수치를 재계산한다. 과거 protocol은 보존 소스 버전과 대조한다.

## 2. 동작 확인과 재개 복구

증강 RNG는 epoch 시작에서 한 번 초기화하고 이후 상태를 이어가도록 수정한다. checkpoint에는 실제 permutation·sample cursor·dataset RNG·Python/NumPy/CPU/CUDA RNG·model·optimizer·scheduler·precision/scaler·update·설정·입력/source digest를 저장한다. 매 update의 실제 sample ID·flip·적용 LR을 기록한다. sample 순서나 RNG를 재개 때 새로 만드는 경로를 막는다.

수정된 `cmd_train` 자체를 별도 프로세스로 실행해 같은 초기 state의 uninterrupted와 중간 epoch optimizer-step 중단/재개를 비교한다. effective batch8과 실제 accumulation을 사용한다. warmup 내부, warmup 종료, LR 감소 경계를 작은 검사 일정으로 포함한다. 복원 직후 저장 state·다음 sample·flip·LR·cursor는 정확히 일치해야 한다. 먼저 다음 update의 입력과 forward RNG를 동일하게 맞춰 비교한다. CUDA 비결정성이 남으면 동일 조건 반복 대조를 함께 보고하고 임의 3배 noise 허용만으로 통과시키지 않는다. 제어 상태 불일치는 무조건 실패다. 수치 차이가 반복 변동으로 설명되지 않으면 본학습을 막고 원인을 분리한다.

lock은 원자적 생성과 PID/starttime·소유 token을 사용하고 자기 lock만 해제한다. 비유한 loss·gradient는 optimizer update 전에 중단한다. checkpoint는 최소 매 epoch와 100 update마다 원자 저장하며 SIGTERM에서 안전한 경계 저장과 자식 종료를 처리한다.

추론은 D의 고정 24명으로 실제 부모/worker 중단·재개, 손상 tail 보존·복구, 정확한 ID 집합·중복 방지, source/checkpoint/completion 변조 거부를 검사한다. 내부 손상 행을 무조건 건너뛰거나 재추론의 근사 유사성을 provenance 검증으로 대신하지 않는다. stage gate는 직접 CLI와 정상 실행 모두에서 강제한다.

## 3. 가능성 탐색의 재사용과 본학습

기존 탐색 450 update와 epoch0/3/6 출력은 원 조건의 학습 신호로 보존한다. 수정된 D 경로에서 입력·학습·재개 gate를 통과하면 같은 탐색 전체를 재실행하지 않고 본학습으로 간다. 이는 기존 유효한 학습 신호를 활용한 확대이며 새 RNG recipe의 일반화 검증을 이미 했다는 뜻은 아니다.

기존 full trajectory에는 반복 flip 문제가 있으므로 COCO 초기값에서 새 detector attempt를 시작한다. 이전 checkpoint는 보존하되 수정 trajectory와 연결하지 않는다. 기존 SFT는 재학습하지 않는다.

recipe는 FP32, effective batch8, LR0.005 SGD momentum0.9/weight_decay1e-4, 첫 1 epoch warmup, horizontal flip0.5, short side800/max1333, trainable_backbone_layers5, BatchNorm running statistics 고정·affine 학습을 유지한다. 새 AMP 탐색은 추가하지 않는다.

기본 seed17은 26 epoch·7,800 updates다. epoch16·22 후 LR을 0.1배로 낮춘다. V100은 epoch6/12/18/22/26, V400은 epoch12/26 및 V100 최고 후보가 다를 때 평가한다. V100 최고 선택은 utility→F1@0.5→이른 epoch 순이다.

수렴 보완은 원 기준을 유지한다. epoch22→26 utility 또는 F1@0.5가 0.01 이상 증가하거나, epoch26이 최고점에 근접하고 마지막 4 epoch loss가 이전 4 epoch보다 10% 이상 감소하면 낮아진 LR로 12 epoch를 추가한다. V100 epoch32/38, V400 epoch38 및 확장 최고 후보를 평가한다. '최고점 근접'의 실행 가능한 정의가 기존 잠금 설정에 없으면 full 결과를 보기 전에 utility 최고점 대비 0.01 이내로 명시해 고정한다. 38 epoch 뒤에도 상승 중이면 수렴 미확인으로 우열을 보류한다.

V400에서 B0 대비 F1@0.3 또는 F1@0.5 절대 차이≥0.03이거나 한쪽만 검출한 GT 비율≥0.05이면 seed29를 같은 규칙으로 학습한다. detector 두 seed의 차이 부호가 바뀌거나 차이 크기가≥0.03 달라지면 seed43을 추가한다. 각 seed의 선택과 이 판단은 detector 개발비교800을 열기 전에 끝낸다.

## 4. 선택과 개발 비교

NMS0.5·score floor0.001·detections_per_img100을 유지한다. threshold는 `{0.01,0.025,0.05,0.10,0.15,…,0.95,0.975,0.99,1.0}`이다. V400 checkpoint×threshold 선택은 utility→양성 F1@0.5→작은 전체 FP/환자→이른 epoch→높은 threshold 순이다. utility는 `0.5×양성 F1@0.3 + 0.25×Normal valid-empty + 0.25×NoOpacity/NotNormal valid-empty`다. FP 값 누락은 오류로 처리한다. FP budget0.25/0.5/1.0별 threshold도 V400에서 recall→작은 FP→높은 threshold로 정한다. 선택점이 후보 cap에 걸리면 해결 전 800명 평가를 보류한다.

잠긴 seed·checkpoint·threshold로 개발비교800 detector 출력을 생성한다. 누락 record를 invalid로 점수화하지 않는다. SFT invalid는 양성 F1=0이며 음성 정답 빈 출력으로 세지 않는다.

양성400명의 환자 평균 F1@0.3·F1@0.5에서 detector17−B0 각각 97.5% paired bootstrap CI를 계산한다. 10,000회 환자 resample을 공유하고 seed를 환자로 합치지 않는다. 기존 95% 함수의 label만 바꾸지 않는다. 별도 구현으로 핵심 수치와 CI를 대조한다.

recall·precision·lesion recall·전체 미검출, 전체800 및 category별 FP/환자·FP 보유율, GT1/2/3개 이상, train union-area 및 개별 GT 면적 삼분위, FP budget별 recall을 보고한다. 전체 N 기준 관측 FP 하한과 valid-only 평균을 구분한다.

matching은 cardinality→총 IoU→기존 동점 규약을 유지한다. 실제 동점·겹친 GT fixture와 기존 VLM 목록에서 exhaustive 기준의 GT identity까지 대조한다. both-hit/detector-only/SFT-only/both-miss를 IoU0.3/0.5에서 산출한다. matching 동점 민감도와 best-IoU cover는 별도 분석으로 표시한다.

## 5. GPU 배치·비용·완료

직전 microbatch2/4 실측 8.89/9.55 images/s와 reserved4,124/7,796MiB를 참고한다. 수정 D 입력에서 유망한 batch4와 기존 batch2를 짧게 대조해 finite 학습·실제 effective batch·처리량·전체 peak와 안전 여유를 확인한다. microbatch 변경은 학습 수치가 완전히 같다고 가정하지 않고 full 전에 고정한다.

실행 직전 `nvidia-smi`로 허용 GPU UUID·여유·논리/물리 대응을 확인한다. 한 GPU에는 detector 학습, 다른 GPU에는 immutable checkpoint 평가 또는 비용 측정을 배정한다. 조건부 seed가 생기면 두 GPU에 나눈다. 독립 추론은 batch1/4를 우선 비교하고 추가 worker가 유망하면 GPU당2개도 측정한다. 전체 동시 peak와 다른 점유에 worker당2GiB 여유를 더해 용량 안에 들어야 한다. 출력·평가 정합성과 전체 처리량이 유지될 때만 확대한다.

공정한 latency는 고정 L64, 8건 warmup, 동일64명×3회다. 동일 GPU에 비교 모델을 각각 단독 resident로 두고 그 GPU의 다른 자체 작업을 겹치지 않는다. 모델 순서는 반복별 교차한다. CUDA synchronize, 로드 시간, 전처리 포함 end-to-end와 모델 구간, 평균/p50/p95·peak·원시 요청 시간을 기록한다. B0 기존 validation suffix와 대조하고 긴 출력 stress를 따로 확인한다. batch throughput은 단독 batch1 latency와 분리한다.

기존 처리량으로 seed당 순수 26 epoch 학습은 약1.8–2.0시간이다. 검증·저장·경합을 포함해 seed당 약2–4시간, 12 epoch 보완은 순수 약0.8–0.9시간으로 추정한다. gate·latency·분석을 합친 단일 seed 경로는 약3–6시간, 조건부 seed 포함 경과시간은 약5–12시간을 예상하되 상한이 아니다. 수정 경로 실측으로 실행 전에 갱신한다. 진행량·loss·LR·자원·종료 코드와 ETA를 기록하고 checkpoint로 재개한다.

## 6. iter_031 분석과 독립 확인 경계

C201/E402 원시1,206건·audit·protocol·GT를 연결해 `results/iter_034/analysis_iter031/`에 보완한다. 원래 예측 box1/2 이상과 category별 회복·추가 TP/FP·F1·invalid, IoU0.5 및 추가 box 중심의 GT 포함 민감도, 원본/중복 제거, FP 분모·token·벽시계·추가 후보 비용을 보고한다. 비교 불가능한 비용은 결측으로 남긴다. 기존 strict 누락 정의·H1/H2와 continuation 투자 종료를 바꾸지 않고 GPU 출력을 재생성하지 않는다.

이번에는 새 독립 환자를 열지 않는다. seed 재현은 환자 독립 확인이 아니다. VinDr 승인 통지 후 별도 계획에서 실제 권한·target 차이와 현재 결과를 반영한다.

# Implementation Tasks for Claude

1. 호스트 작업 소유·종료 상태를 확인하고 원본 소스·부분 결과의 목록과 digest를 보존한다.
2. results 내 핵심 소스를 추적 경로에 편입하고 새 결과 경로·import·실행 환경을 연결한다.
3. 실제 학습 RNG·checkpoint·lock·finite 처리와 장시간 실행 수명을 수정한다. 수정 전후 호환 범위를 기록한다.
4. 전체 입력·기존 SFT 출력 감사, 실제 학습/추론 재개·변조 검사, matching identity·threshold 선택·97.5% CI 회귀 검사를 통과시킨다.
5. 처리량·메모리로 배치를 확정하고 새 detector full 학습·조건부 수렴/seed·validation 선택·800명 비교·latency를 완료한다.
6. iter_031 저장 출력 분석을 마무리한다. 보고서에 계획 대비 실제 규모·재사용/재실행 사유·수렴·선택·한계·모든 종료 코드를 기록하고 `SELF_CHECK: PASS/FAIL`, `SUMMARY:`를 포함한다. background 대기 문장으로 최종 보고를 대신하지 않는다.

# Evaluation (성공/실패 기준 포함)

**실행 완료:** 필수 gate, 계획된 학습·조건부 확대, 잠긴 validation 선택, 완전한 비교·비용·잔여 분석이 있어야 진단을 완료했다고 판단한다. fixture 통과와 연구 결론을 구분한다.

**양성 — detector 우위:** 두 F1 차이의97.5% CI 하한>0, 적어도 한 점추정≥0.03, 전체 FP/환자 증가의95% CI 상한≤0.05를 원 기준으로 유지한다. 단독 latency≥2배 이점도 함께 확인한다. SFT-only GT 비율95% CI 상한≤5%이며 seed·주요 층 반전이 없으면 현재 단순 bbox 개선의 우선순위를 낮춘다. 의료 VLM 전체의 가치나 언어 과제 우위로 일반화하지 않는다.

**음성 또는 조건별 SFT 이점:** 충분한 detector 학습·입력·선택을 확인한 뒤 반대 F1 차이·낮은 FP·사전 층 이점을 조건부 근거로 보존한다. 외부 확인 후보로 삼고 새 loss는 자동 시작하지 않는다.

**상보성:** 한쪽만 검출한 GT 비율≥5%, 최소20명에 분포하고 환자 bootstrap에서도 양의 비율이 유지되는지 확인한다. IoU·seed·FP budget·matching 민감도를 함께 보고한다. GT union을 실제 결합 방법 성능으로 주장하지 않는다.

**불확정:** 의미 있는 양방향 차이를 포함한 CI, seed 반전, 수렴 미확인은 우열 보류다. 사전 validation 보완만 수행하고 800명을 본 뒤 선택 기준을 바꾸지 않는다. 추가 표본은 별도 독립 확인 계획에서 판단한다.

**실행 실패·중단:** 입력 불일치·재개 상태 불일치·비유한 학습·소유권 불명·완료 검증 실패는 해당 경로를 중단한다. OOM은 batch/동시성을 낮춰 유효한 checkpoint에서 복구하며 학습 조건 변경을 기록한다. 시간 경과나 짧은 탐색 무개선만으로 detector 계열을 기각하지 않는다.

# Risks / Checks

기존 full checkpoint는 수정 RNG trajectory의 연속 재개로 사용하지 않는다. 원본 표본·결과·protocol은 덮어쓰지 않는다. 저장 소스 존재와 재사용 승인을 구분한다. 무관한 과거 pipeline 정비·새 benchmark·새 architecture 탐색은 추가하지 않는다.

학습 충분성은 양쪽 최적 모델의 보증이 아니다. 기존 SFT의 완전 수렴·사전학습 미노출·외부 일반화는 여전히 미확인이다. 결과800은 개발 자료이며 paired CI가 독립 일반화를 보증하지 않는다.

## 대규모 GPU 필요 후보

다기관·다소견 vision encoder와 언어 모델 공동 post-training을 장기 후보로 유지한다. 이번 두 RTX3090 비교는 그 필요성을 판단하는 근거이며 해당 대규모 학습을 실행하는 계획은 아니다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/runs/iter_033/plan.md`, `review.md`, `claude_report.md`, `agent/GOAL.md`, `REPORTING_STYLE.md`, `LIMITATIONS.md`, `CODE_ASSETS.md` 및 iter_009·012·031 원본 리뷰를 읽었다.
- 현재 research HEAD는 `a60224c1f7d54e4f59e8c4dc16285d62faf004b5`이며 `git status --short`와 `git diff --stat` 출력은 비어 있다. 필요한 공통 모듈은 현재 브랜치에 있다. 다른 commit의 선별 반입은 필요 없다.
- 핵심 detector 소스는 실제로 `research/results/iter_033/`에 남아 있다. `run_detector.py`, `detector_lib.py`, `build_manifests.py`, 평가·선택·latency 스크립트와 두 검사 파일을 확인했다. 소실된 코드가 아니며 원본을 보존한 채 추적 경로에 편입해야 한다.
- `run_detector.py::cmd_train`은 매 optimizer update마다 `ds.set_epoch_rng(seed*1000+epoch)`를 호출한다. epoch 내 각 batch 위치에 같은 flip 패턴이 반복된다. checkpoint에는 dataset RNG가 없고 `ids_order`에는 실제 permutation 대신 원래 ID 목록이 저장된다. 기존 resume 검사는 실제 cmd_train이 아닌 별도 loop이며 같은 프로세스에서 재구성한다.
- 본학습 로그 마지막 update는 593이다. lock에는 PID 1569646과 생성 시각만 있다. 이 파일만으로 호스트 작업의 생존·종료를 판정할 수 없다.
- `select_threshold.py`는 FP 입력 누락을 0으로 대체하고 checkpoint 간 이른 epoch 동점을 처리하지 않는다. `latency_bench.py`에는 원래 계획의 명시적 synchronize·모델 로드 시간·반복별 원시 기록이 충분히 연결되지 않았다.
- 직전 리뷰는 탐색 450 update와 F1@0.3 0/0.3367/0.4113을 독립 재현했다. microbatch2/4 처리량은 8.89/9.55 images/s, peak reserved는 4,124/7,796 MiB였다. 이 수치는 학습 가능성 근거지만 안전한 배치 확정이나 최종 비교가 아니다.

## 의미와 선택

iter_033의 전략 판단을 유지한다. 새로운 문헌 후보나 loss보다 승인된 실제 detector 비교의 완료가 우선이다. augmentation 변경은 학습 trajectory를 바꾸므로 기존 full checkpoint의 연속 재개로 포장하지 않는다. 기존 탐색 출력은 과거 학습 신호로 재사용하고 수정된 full 학습은 COCO 초기값에서 새 attempt로 수행한다. 탐색 전체 재실행은 필요하지 않지만 수정된 실제 학습 경로의 작은 동작·재개 검사는 필수다.

현재 버전의 공식 detector 소스·가중치 선택은 iter_033의 조사와 고정된 설치 버전을 이어받는다. 아키텍처나 공식 recipe를 새로 선택하지 않으므로 광범위한 문헌 조사를 반복하지 않는다. 이번에는 파일 읽기만 수행했으며 코드 변경·실험·다운로드는 하지 않았다.

## 대규모 GPU 필요 후보

다기관·다소견 vision encoder–language model 공동 post-training은 장기 후보로 유지한다. 현재 비교가 그 투자 필요성을 판단할 근거이며 이번 실행 범위는 아니다.
