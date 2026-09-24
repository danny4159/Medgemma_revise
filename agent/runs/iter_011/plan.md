# 요약

- **이번에 할 일:** iter_010의 실행 상태를 확인하고 재개·평가 결함을 고친 뒤 기존 SFT 비교를 완료한다.
- **필요한 이유:** 학습 경로는 작동하지만 일반화 성능을 판단할 본학습·독립 평가가 미완료다.
- **확인할 기준:** 입력과 checkpoint의 연결, 누락 없는 epoch validation, 정확한 3개 seed, 확인 800명의 실제 생성 비교를 검증한다.
- **주의·다음:** 원래 실험 규모를 유지한다. SFT 성공은 baseline 확립이며, 후속 새 방법과 다중 데이터셋 증명은 별도로 필요하다.

# Current Understanding

`lesion-grounding-generalization`은 iter_009에서 validated다. 정상 사용 조건의 RSNA 양성 200명 중 134명에서 두 고정 prompt 모두 위치 불일치가 관찰됐다. 내부 원인이나 모든 병변의 일반화 실패가 확정된 것은 아니다.

iter_010은 직접 병변 LoRA SFT의 학습 경로와 추론 병렬 처리량을 확인했지만 본학습·독립 확인을 완료하지 못했다. 현재 저장 로그는 seed 17 두 LR의 121/107 steps와 base validation 133개 행이다. 체크포인트 파일의 존재는 확인했으나 내용과 실행 호스트 생존 상태는 구현 시 검증해야 한다.

유지할 것은 모델 revision, 데이터 분할, 모든 baseline, 학습 설정, 매 epoch 전체 validation, 확장 규칙, 3개 seed, 확인 800명과 성공 기준이다. 변경할 것은 재개 상태 관리, provenance, 평가 gate, 안전한 GPU 배치와 산출물 경로다. anatomy 전이와 새로운 preference objective는 보류한다. iter_008 보완 지시의 일회성 정상 사용 진단은 완료됐으므로 반복하지 않는다.

# Hypothesis

직접 병변 LoRA SFT는 같은 concise prompt의 미적응 모델과 영상 비의존 보정을 넘어 새 RSNA 양성 환자의 bbox 집합 F1@0.3을 개선한다. 충분한 학습 후 남는 위치·크기·개수·빈 응답·형식 오류를 확인해 후속 방법의 필요성을 판단한다.

이번 복구는 가설·split·metric을 바꾸지 않는다. 실행 완료나 loss 감소를 가설 지지로 간주하지 않는다.

# Limitation Evidence / Correct Usage Checks

근거는 `agent/LIMITATIONS.md`와 `agent/runs/iter_009/review.json`이다. 모델은 `google/medgemma-1.5-4b-it`, revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`를 유지한다. 값 보존 uint8 RGB, square padding, 공식 processor/chat template, yxyx 0–1000, strict parser, greedy 생성, 1000→2000→4000 cap과 EOS 판별을 유지한다.

기존 공식 sanity 전체를 반복할 필요는 없다. 수정한 학습·재개·평가 경로에서는 현재 file/pixel hash, prefix와 assistant-only mask, adapter 적용, prompt/config/protocol 연결을 검사한다. 실제 생성 완료 후의 형식 실패·잘림은 성능 실패로 평가하지만, 요청 자체의 누락은 실험 미완료로 차단한다.

# Contribution Path / Baselines / Reuse

이번은 방법 개발을 위한 직접 적응 baseline 완성 단계다. iter_010에 기록된 SPR·CORAL 등과의 비교를 유지하며 CoMedPO 목적함수 미확보를 해결한 것으로 표현하지 않는다. 새 loss는 추가하지 않는다.

비교군은 미적응 official_long/concise, prompt별 고정 좌표 보정, train 기반 단일 box 및 집합 prior, concise SFT다. 좌표 보정은 기존 개발 380명으로 선택한 원래 800개 후보 규칙을 유지하고 prior는 train만 사용한다. validation에서 양성 F1@0.3이 가장 높은 단순 비교군을 주 비교군으로 고정한다. 기존 tie-break도 변경하지 않는다.

현재 `approach/conditional-set-grounding`을 유지한다. HEAD `5581ed255a350e42a0ad422065edf13c56a33bf6`에 필요한 소스가 있으므로 reuse_assets는 비운다. 전체 스냅샷 재사용 승인을 뜻하지 않는다.

- 승인 범위 유지: `rsna_diag/__init__.py`, `geometry.py`, `parse.py`, `metrics.py`, 표준 LoRA 구성요소인 `lora.py`.
- 필수 수정: `train.py`, `sft_data.py`, `generate.py`, `lock_protocol.py`, `launch.py`, `run_shards.py`, `queue_lock.py`의 재개·입력·소유권 연결.
- 필수 평가 gate: `select.py`, `final_eval.py`, `sft_eval.py`, `evaluate.py`, `baselines.py`의 예상 집합·선택·adapter·protocol 검증.
- 기존 `test_rsna_iter009.py`, `test_rsna_iter010.py`를 사용하고 필요한 회귀 검사를 추가한다. 미추적 `test_rsna_iter010_gpu.py`는 원본을 보존하며 자동 저장 제외 원인을 확인한다. 실제 비밀정보를 출력하거나 검사 우회로 커밋하지 않는다. 안전한 검증 소스의 보존 및 protocol 연결을 해결한다.

# Proposed Experiment

## 1. 실행 상태 확인과 원본 보존

실행 호스트에서 학습·추론·launcher·대기 프로세스의 host/PID/starttime, run-dir, GPU UUID, lock 소유권, 로그 갱신, checkpoint, 종료 코드를 대조한다. 현재 계획 환경에서 프로세스가 안 보인다는 이유로 종료로 판정하지 않는다.

살아 있는 작업을 중복 실행하거나 claim을 삭제하지 않는다. 수정이 필요한 작업은 소유를 확인한 뒤 지원되는 정상 종료 또는 안전한 경계를 이용한다. 다른 사용자의 프로세스는 건드리지 않는다. 소유권을 확정할 수 없으면 해당 run의 재개를 보류하고 원인을 보고한다.

iter_010의 원본 protocol·결과·checkpoint는 보존한다. 새 결과는 `results/iter_011/`에 저장한다. 종료가 확인된 원본을 읽기 전용 부모로 삼아 source SHA, 경로, file hash, 기존 protocol digest, 실제 checkpoint step을 연결한 재개 manifest를 만든다. mutable 원본을 hardlink해 공유하지 않는다. 기존 로그의 checkpoint 이후 step은 원본 이력으로 남기고 복구된 trajectory의 유효 step과 분리한다.

## 2. 동작 확인: 복구 경로 검증

이번은 새 방법 탐색이 아니라 진행 중인 iter_010의 복구다. 기존 pilot을 반복하지 않고 결함에 대응하는 검사를 한다.

CPU/작은 모델 fixture에서 optimizer step 직후, epoch adapter 저장 직후, validation 일부 기록 후, 마지막 epoch validation 중단 후의 재개를 검사한다. dropout, DataLoader iterator 생성, sampler 위치, Python/NumPy/torch/CUDA RNG 영향을 포함해 uninterrupted와 resumed 경로의 다음 입력 순서·LR·optimizer state·adapter tensor를 비교한다. 허용 오차는 검사 전에 명시한다. validation 복구가 다음 학습 RNG나 optimizer 상태를 바꾸지 않아야 한다.

실제 GPU 검사는 기존 pilot16의 고정 ID를 재사용한다. train의 단일/복수 box·두 음성 층과 긴 target을 포함하는지 확인한다. 고정 validation 소표본으로 중단 후 남은 요청만 수행되는지 확인한다. 이 표본은 복구 검사이며 새로운 성능 선택 자료나 독립 확인이 아니다. pilot weight는 본학습에 이월하지 않는다.

입력 ID 하나의 변경, 중복 ID, 영상 pixel 변경, 잘못된 GT/split, adapter 불일치, epoch metric 누락, completion 손상, seed 누락·중복을 주입하면 학습/선택/평가가 실패해야 한다. 실패 후 성공 completion이 남아서는 안 된다.

## 3. 가능성 탐색과 규모 확대: 원 계획 계속

iter_011 이후의 새로운 후보에 적용되는 단계별 축소 규칙을 이 미완료 실험에 소급하지 않는다. 기존 동작 확인 근거와 사용자 지정에 따라 원래 학습량과 평가 일정을 유지한다. 새로운 탐색 subset이나 작은 결과에 따른 조기 포기를 추가하지 않는다.

분할은 기존 manifest를 유지한다. train 2,400명은 opacity/Normal/NoOpacity-NotNormal 1,200/600/600명, validation 400명은 200/100/100명, confirm 800명은 400/200/200명이다. patient/SOP/pixel 중복 검사와 exclusion을 재개 provenance에 연결한다. reserve는 사용하지 않는다.

학습은 언어층 attention/MLP 선형층의 LoRA rank16, alpha32, dropout0.05, frozen bf16 base, assistant-only CE를 유지한다. AdamW LR {1e-4,2e-4}, weight_decay0.01, betas(0.9,0.999), eps1e-8, grad clip1, effective batch16을 유지한다. 기존 두 run은 microbatch2다. 재개 시 임의로 변경하지 않는다. 기존 5% warmup/cosine 및 6–8 epoch의 사전 구현된 schedule을 보존한다.

seed17의 두 LR을 각각 5 epochs 완료하고 매 epoch validation 400명의 실제 생성과 assistant loss를 평가한다. 어느 한 LR이라도 epoch4→5 utility 증가가 0.01 이상이고 loss가 1% 이상 감소하면 두 LR 모두 8 epochs까지 연장한다. utility는 0.5×양성 F1@0.3 + 0.25×Normal valid_empty + 0.25×NoOpacity/NotNormal valid_empty다. checkpoint 동률은 F1@0.5, 다음 이른 epoch로 처리한다. LR 동률 규칙도 기존 구현을 유지한다.

선택한 LR과 총 epoch 수로 seed29·43을 학습하고 각 seed에서 같은 validation 규칙으로 checkpoint를 선택한다. 기본 4개 trajectory, 48,000 presentations/3,000 optimizer steps이며 전체 연장 시 76,800/4,800이다. 재개 전 이미 유효하게 수행한 부분은 다시 처음부터 실행하지 않는다.

## 4. 독립 확인

예정 epoch 전체의 validation이 완료되고 3개 seed의 선택 adapter, LR/epoch 설정, baseline과 주 비교군이 잠긴 뒤 confirm을 시작한다. confirm은 official_long/concise base 1,600요청과 SFT 3개 seed 각800요청, 합계4,000요청이다. 고정 보정과 prior는 추가 생성 없이 계산한다.

실행 호스트에서 확인 결과가 이미 생성됐는지도 감사한다. 이미 확인 성능을 본 뒤 설정이 바뀐 경우 독립 확인으로 주장하지 않는다. 미완료·유효 산출물은 검증 후 재사용할 수 있으나 결과에 맞춰 설정을 바꾸지 않는다.

Kvasir-SEG는 iter_010에서 예정한 공식 배포·버전·이미지/정답 대응·중복·patient/video 정보의 준비 상태만 기록한다. 이번 RSNA 실행을 외부 데이터 확보에 종속시키지 않는다. 추가 데이터셋의 효과 검증은 후속 계획이며 이번 완료 기준에 넣지 않는다.

## 5. GPU 배치와 비용

시작 직전 `nvidia-smi`로 허용 GPU0,1의 UUID·여유 메모리를 확인한다. 상속된 CUDA_VISIBLE_DEVICES 안에서만 자식을 배정하고 논리/물리 대응을 기록한다.

기본은 GPU별 학습1개이며 학습과 epoch validation 동안 같은 GPU의 추가 base 추론을 피한다. 이는 고정 worker 상한이 아니라 기존 혼합 실행에서 프로세스당2GiB 여유를 충족하지 못한 실측 때문이다. 학습 allocated peak 약9.81GiB만으로 복수 학습을 허용하지 않는다.

별도 추론 단계는 기존 2 GPU×2 worker가 우선 후보다. 이전 24명×2 prompts 비교의 약1.97배 처리량과 출력 일치를 활용한다. 동일 비교를 전부 반복하지 않고 수정한 실행기에서 고정 development 입력의 짧은/긴 출력 정합성과 동시 peak를 확인한다. 실행 코드 변경으로 근거가 무효이면 기존 thr24 ID로 2/4 worker를 다시 비교한다. 메모리가 부족하면 batch 또는 worker를 줄인다. 최종 구성은 성능 점수가 아니라 요청/분, 전체 GPU peak, worker당2GiB 여유, 긴 출력 지연, CPU/RAM/I/O 경합, 오류와 출력 정합성으로 선택한다.

학습 로그 환산은 순수 학습 기본 약6.2–7.0시간의 이상적 두 GPU 병렬 시간이다. 기본 생성12,800건, 전체 연장17,600건을 이전 base 처리량2.73요청/분으로 환산하면 약78/107시간이나 SFT 생성에는 직접 적용할 수 없다. 첫 정상 epoch validation에서 실제 생성 길이·처리량을 측정해 남은 학습/validation/base/confirm별 비용을 다시 계산한다. 학습과 validation의 작업 의존성, 이미 완료된 요청, startup 비용을 포함한다. 임의 시간 상한을 두지 않는다.

50 optimizer steps와 epoch 경계에 checkpoint를 원자적으로 저장한다. 진행량·loss·gradient·자원·실패·종료 코드·남은 예상 시간을 남긴다. OOM·비정상 수치·진행 정체는 원인을 확인해 안전한 배치로 복구한다.

# Implementation Tasks for Claude

1. 실제 실행 호스트의 소유 작업을 감사하고 기존 산출물을 보존한다. `results/iter_011/recovery/`에 출처·진행량·재사용/재실행 판단을 기록한다.
2. 학습 run-dir의 canonical 경로에 단일 writer lock을 적용한다. 직접 train 호출도 lock을 우회하지 못하게 한다. launcher와 child의 lock 소유 관계를 정해 자기 자신과 교착하지 않도록 한다. lock 파일 삭제로 소유권을 회수하지 않는다.
3. checkpoint에 학습 위치와 validation pending/completed를 명시한다. 다음 epoch로 진행하기 전 미완료 validation을 해당 epoch adapter로 복구한다. 과거 adapter로 validation할 때 현재 학습 adapter·optimizer·RNG를 훼손하지 않는다. 마지막 epoch에도 동일하게 적용한다. metric/completion은 전체 요청 검증 뒤 원자적으로 기록한다.
4. train/validation/confirm ID의 정확한 내용, manifest/GT, 현재 file/pixel hash, prompt·모델 revision·adapter·설정과 선택 이력을 digest로 연결한다. 기존 checkpoint는 현재 ID 수가 같다는 이유만으로 수용하지 않는다. 과거 고정 manifest의 split 목록·로그·현재 ID를 대조해 실제 입력 집합의 호환성을 입증한다.
5. 기존 protocol을 덮어쓰거나 검증을 건너뛰지 않는다. 새 protocol과 명시적인 migration manifest를 만들고 old→new 코드 변경, 불변 학습 의미, 입력 대응, 원본 checkpoint hash를 연결한다. 변경된 protocol은 digest를 바꾸므로 검증된 부모 checkpoint를 새 run으로 가져오는 제한된 경로가 필요하다. 단순 digest 교체는 금지한다. 학습 의미를 바꾸는 결함이 발견되면 영향받은 trajectory만 새 경로에서 재실행하고 사유를 남긴다.
6. epoch 선택·확장·주 비교군 선택·confirm의 공통 평가 gate를 만든다. 예상 ID×prompt×adapter 집합과 원시 요청 집합의 정확한 일치, 중복·추가 요청 부재, protocol/config/input 연결, completion 근거를 검사한다. seed 집합은 정확히 {17,29,43}이며 CLI 중복을 dictionary 생성 전에 거부한다. seed별 선택 기록과 실제 adapter digest를 대조한다.
7. 필요한 CPU 회귀 및 실제 GPU 복구 검사를 수행한다. 기존 승인된 기하/parser/LoRA 검증을 활용하되 변경 경로의 검사와 구분한다. GPU fixture 소스의 안전한 보존 문제를 해결한다.
8. 복구 gate를 통과하면 원래 학습·확장·seed·독립 확인을 완료한다. base validation의 기존133개 행도 검증 후 부모 출력으로 연결하고 새 요청만 별도 파일에 기록한다. provenance가 맞지 않는 산출물을 조용히 합치지 않는다.
9. launcher가 모든 소유 child의 종료 코드를 수집하도록 한다. 백그라운드 작업 시작이나 알림 대기를 완료 보고서로 제출하지 않는다. 불가피하게 중단되면 미완료 상태·소유 PID·checkpoint·남은 작업을 명시한다.
10. 최종 보고서에는 계획 대비 실제 사용량, 재사용/재실행량, 선택 이력, 원시 생성·metric 경로, 실패 및 독립 검증 범위를 기록한다. 소스 저장은 orchestrator가 담당하고 adapter·optimizer·데이터는 results에 둔다.

# Evaluation (성공/실패 기준 포함)

실행 복구 성공은 소유 run의 중복 방지, 중단 위치별 정확한 재개, 입력 변경 거부, 모든 예정 epoch validation 완료, 엄격한 seed/adapter/요청 검증으로 판단한다. 이것만으로 연구 가설이 지지되지는 않는다.

주지표는 확인 양성400명의 end-to-end 환자별 F1@0.3이다. 실제 생성의 형식 실패·잘림은0점이다. 3개 seed의 환자별 값을 평균한 뒤 고정 주 비교군과 paired bootstrap10,000회, seed20260925로95% CI를 계산한다. 각 seed 점수·차이·범위를 모두 보고한다. 이 CI가 학습 seed 불확실성을 충분히 나타낸다고 주장하지 않는다.

성공 기준은 평균 차이≥0.05, CI하한>0, 세 seed의 차이 모두 양수, 각 seed 전체 유효 출력률≥95%, 두 음성 층의 valid_empty율이 같은 concise base보다 각각5 percentage points 넘게 악화되지 않는 것이다. 원래 기준을 유지한다.

F1@0.5, precision/recall, union IoU, valid-only 성능, 잘림·형식 실패·유효 빈 목록, 음성 추가 box율을 함께 보고한다. 단일/복수 GT와 train 면적 삼분위별로 잔여 오류를 분석한다. 사후 분해를 새 사전 가설 검증으로 표현하지 않는다.

기준 일부만 충족하면 개선 범위를 구분한다. 수렴·seed 변동·정밀도가 부족하면 inconclusive로 남긴다. 충분한 학습 후 무개선이면 현재 데이터·언어층 rank16 LoRA·고정 학습 조건에 한정한 음성 결과다. 평가 gate 실패나 실행 미완료면 execution_failed이며 valid_experiment=true로 보고하지 않는다. 어떤 경우에도 이번 baseline 완료를 최종 GOAL 달성이나 DONE으로 표현하지 않는다.

# Risks / Checks

- 과거 ID 파일이 protocol에 없으므로 과거 입력의 완전한 증명을 자동 가정하지 않는다. 복구 가능한 증거와 남은 불확실성을 분리한다.
- 재개 시 DataLoader 생성과 dropout RNG, 미완료 validation의 실행 순서가 trajectory에 영향을 줄 수 있다. 작은 optimizer fixture만으로 전체 실행기 정확성을 주장하지 않는다.
- 원래 로그의 checkpoint 이후 step을 새 재개 로그와 합쳐 중복 학습량이나 단일 연속 trajectory로 세지 않는다.
- GPU sampled 점유는 순간 peak의 상한이 아니다. 긴 생성·validation·다른 프로세스의 실제 점유를 포함해 안전 여유를 확보한다.
- SFT가 대부분의 오류를 해소하면 새 loss를 억지로 추가하지 않는다. 잔여 오류와 외부 데이터셋에서 연구 가치를 다시 판단한다.
- 사전학습 노출, RSNA GT 경계 모호성, 다른 병변·기관 일반화는 여전히 미확인이다.

## 대규모 GPU 필요 후보

기존 노트의 GETok 전체 SFT/RL, RadGrounder 규모의 다중 과제 학습, CORAL형 GRPO와 vision encoder까지의 공동 적응을 보존한다. 이번 언어층 LoRA 결과만으로 이 방법들의 필요성이나 실패를 판단하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/GOAL.md`, `agent/LIMITATIONS.md`, iter_009 원본 review.json, iter_010 plan.md·review.md·claude_report.md, `agent/CODE_ASSETS.md`와 현재 소스를 읽었다. 사용자 보완의 정상 사용 진단은 iter_009에서 충족됐으며 anatomy 전이는 보존 후보다.
- 현재 research HEAD는 `5581ed255a350e42a0ad422065edf13c56a33bf6`이다. tracked diff는 없고 `test_rsna_iter010_gpu.py`가 미추적 상태다. 필요한 rsna_diag 소스가 현재 브랜치에 있어 선별 반입은 필요 없다.
- 현재 저장 로그에서도 seed 17의 LR 1e-4/2e-4는 각각 121/107 steps다. 마지막 누적 시간은 1793.03/1785.80초이고 allocated peak는 각각 약 9.81GiB다. 이 값은 GPU 전체 점유나 validation peak가 아니다. 두 train_config는 microbatch 2, effective batch 16을 기록한다.
- 두 run의 `ckpt_latest.pt`는 각각 358,218,093 bytes로 존재한다. 이번 계획 단계에서는 tensor checkpoint를 로드하지 않았으며 실제 저장 step·optimizer·RNG의 건전성은 Claude가 확인해야 한다. base validation JSONL은 133개 행이고 epoch validation metric은 발견하지 못했다.
- `train.py`는 epoch validation 전에 다음 epoch 위치를 checkpoint에 저장한다. 재개 시 미완료 validation을 건너뛰는 경로를 직접 확인했다. 선택 ID 내용은 train_digest에 없고 SFTDataset 및 val_loss는 현재 pixel hash를 버린다.
- `select.py`는 존재하는 epoch metric만으로 선택한다. `final_eval.py`는 completion/protocol을 강제하지 않으며 seed 인자를 dictionary로 처리해 중복을 덮어쓸 수 있다. 수정할 결함이 구체적이므로 추가 조사 라운드는 필요 없다.
- 현재 환경의 프로세스 조회는 실행 호스트에서의 작업 생존 여부를 확정하지 못한다. Claude는 실제 실행 호스트에서 host/PID/starttime·lock·GPU process·종료 기록을 대조해야 한다.

## 의미와 비용

iter_010 리뷰의 24명×2 prompts 처리량 비교는 2 worker 1.39 요청/분, 4 worker 2.73 요청/분이며 48개 suffix/EOS가 일치했다. 새 성능 탐색 없이 이 근거를 재사용할 수 있지만 변경된 실행기의 정합성과 현재 메모리는 다시 검사해야 한다. 혼합 학습·추론의 GPU 전체 점유 21,090/20,999MiB는 두 프로세스의 합계 4GiB 여유를 충족하지 못했다.

현재 학습 로그의 단순 시간/step은 약 14.8–16.7초다. 기본 3,000 optimizer steps를 두 GPU에 이상적으로 나누면 순수 학습 약 6.2–7.0시간에 해당하나 validation·초기화·작업 의존성은 제외한 환산이다. 기본 전체 생성은 epoch validation 8,000건+base validation 800건+confirm 4,000건=12,800건이다. 8 epoch 확장 시 17,600건이다. 이를 이전 base 처리량 2.73 요청/분으로 단순 환산하면 약 78/107시간이다. SFT 출력 길이와 epoch validation 실행 방식이 다르므로 실제 총시간 예측으로 단정하지 않는다. 원 계획의 10–40시간 추정은 보장할 수 없으며 실제 SFT validation 처리량으로 다시 산출해야 한다.

## 선행 연구와 미해결 범위

이번은 알려진 실행 결함의 복구다. iter_010 조사 기록의 SPR·CORAL 비교 및 CoMedPO 원문 미확보 상태를 유지하고 문헌 검증을 완료했다고 새로 주장하지 않는다. SFT/LoRA 자체는 novelty가 아니다. Kvasir-SEG의 추가 데이터셋 검증과 reserve의 독립 확인은 후속 과제다. 코드 수정·파일 생성·테스트·GPU 실험은 이번 계획 단계에서 수행하지 않았다.
