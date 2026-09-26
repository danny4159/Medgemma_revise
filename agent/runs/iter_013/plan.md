# 요약

- **이번에 할 일:** 같은 SFT adapter에서 추가 SFT, 좌표 가중 CE, DIST²Loss 자리별 이식안을 학습하고 실제 생성 bbox를 비교한다.
- **필요한 이유:** 위치 정밀도 오류가 남지만, 추가 학습·숫자 가중·거리 supervision 중 무엇이 도움이 되는지 아직 모른다.
- **확인할 기준:** 같은 학습량의 SFT 대비 위치 지표 개선과 음성 성능 유지 여부다. 대표 subset·1개 seed에서 유망할 때만 확대한다.
- **주의·다음:** 이번은 선행 목적함수 비교다. 새 방법의 contribution이나 독립 일반화 증명으로 표현하지 않으며, reserve는 후속 독립 확인용으로 보존한다.

# Current Understanding

iter_009에서 정상 사용 조건의 RSNA grounding 한계를 검증했고 iter_012에서 직접 LoRA SFT 개선을 독립 확인했다. 현재 validated 주장은 `lesion-grounding-generalization`이다. 기준 모델은 MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`다.

라운드 02의 개발 분석에서 validation 양성 200명, GT 309개 중 seed17 epoch5의 IoU≥0.3 matching은 197개, IoU≥0.5는 111개였다. 빈 응답 영상에 GT 48개가 있고, 비어 있지 않은 응답에서 best IoU가 0.3 미만인 GT가 64개다. 작은 개별 box의 Recall@0.5는 22/113이었다. 이는 위치 정밀도와 빈 응답 문제를 함께 감시할 근거이며 내부 병목의 증명이 아니다.

기존 checkpoint 선택은 원 계획에 맞았다. 다만 기존 utility와 위치 정밀도는 다른 지표이므로 새 비교에서는 모든 조건에 같은 선택 규칙을 적용한다. 과거 점수·선택 파일·성공 판정은 변경하지 않는다.

유지할 것은 정상 사용 검증, 직접 SFT baseline, 환자 분할, 원본 산출물이다. 보류할 것은 anatomy 전이와 최소 수정 preference다. 변경할 것은 후속 목적함수 비교와 명시적인 추가 적응 단계다. 사용자 보완의 diagnostic 우선 요구는 이미 충족됐으므로 공식 sanity 전체를 반복하지 않는다.

# Hypothesis

추가 SFT 이후에도 자리별 거리 supervision이 숫자 token의 관계를 학습시키면 실제 생성 위치 정밀도를 높일 수 있다. 추가 좌표 CE만으로 같은 효과가 나면 거리 분포의 추가 이득은 지지되지 않는다.

세 조건을 비교한다.

- **C — 추가 SFT:** 기존 assistant-only CE.
- **H — 좌표 가중 CE:** C에 좌표 숫자의 자리 가중 hard-target CE를 추가한다.
- **D — DIST²Loss 이식:** C에 좌표 숫자의 자리 가중 거리 분포 loss를 추가한다.

공통 시작점 **B0**도 평가한다. C−B0는 추가 적응 효과, H−C는 좌표 supervision 증가, D−H는 해당 거리 분포의 추가 효과를 보여준다. 어느 비교도 모델 내부 원인의 인과 증명으로 확대하지 않는다.

# Limitation Evidence / Correct Usage Checks

근거는 `agent/runs/iter_009/review.json`, `agent/runs/iter_012/review.md`, `agent/LIMITATIONS.md`, iter_013 조사 라운드 01·02다. 과거 confirm 800명은 후속 개발 자료로 표시한다. 새 reserve에는 평가 요청을 보내지 않는다.

전처리·좌표·정렬·prompt·parser는 기존 규약을 유지한다. 생성은 concise, greedy, 기존 1000→2000→4000 출력 길이 재시도와 EOS 판별을 그대로 사용한다. 형식 실패·잘림·valid_empty·위치 오류는 따로 집계한다. 추가 loss는 생성 경로를 바꾸지 않는다.

새 경로에서 필수 확인할 것은 다음과 같다.

1. JSON AST에서 `box_2d`의 네 정수 문자 구간을 얻고 실제 chat sequence의 token 위치에 연결한다. key의 `2`, label, 괄호, 공백, `<end_of_turn>`에는 거리 loss를 적용하지 않는다.
2. 모든 학습 target에서 좌표 숫자 token이 기대한 한 자리 숫자로 분해되는지 확인한다. 미지원 tokenization을 조용히 제외하거나 tokenizer를 바꾸지 않는다. 실패하면 해당 연결을 해결한 뒤 학습한다.
3. 0/9/10/39/40/99/100/999/1000 경계, 빈 목록, 복수 box, padding, 다음-token shift를 검사한다. 39↔40과 같은 올림·내림 관계를 이번 loss가 완전하게 표현하지 못함을 명시한다.
4. alpha=0에서 기존 CE·gradient와 일치하고, H와 D의 추가 항이 지정 위치에만 적용되는지 독립적인 작은 FP32 기준 계산으로 대조한다.
5. 기존 학습용·생성용 prefix와 pixel tensor 일치, 입력 file/pixel hash, patient ID·GT·split digest 검사를 유지한다.

# Contribution Path / Baselines / Reuse

DIST²Loss의 CE+거리 분포 supervision 및 자리 가중 아이디어를 이식한다. 아래 수식의 정규화·temperature는 이번 실험의 명시적인 선택이다. 원논문 전체 재현이나 새로운 방법으로 부르지 않는다. [DIST²Loss 원문](https://arxiv.org/html/2503.02379v3)

R-VLM은 box 기하 supervision의 후속 대안이다. 최소 수정 preference는 TD-DPO와 겹치는 핵심 설계 때문에 이번에 구현하지 않는다. [R-VLM](https://arxiv.org/html/2507.05673v1), [TD-DPO](https://arxiv.org/html/2607.18304v1)

현재 `approach/conditional-set-grounding`을 유지한다. HEAD `783d2d04671ae296f3dc0c700e575f8af8e021c9`에 필요한 코드가 있으므로 `reuse_assets=[]`다. 전체 스냅샷 재사용 승인을 뜻하지 않는다.

- 승인 범위 재사용: `rsna_diag/__init__.py`, `geometry.py`, `parse.py`, `metrics.py`, `sft_eval.py`, `lora.py`. 기존 좌표·parser·matching fixture와 새 입력 연결을 확인한다.
- 수정 후 사용: `sft_data.py`, `train.py`, `inputs.py`, `select.py`, `eval_gate.py`, `pipeline.py`, `lock_protocol.py`. 새 loss·분할·초기화·평가 일정을 protocol과 연결한다.
- 실행기 필수 수정: `generate.py`의 부모 재사용 NameError, `pipeline.py`의 final/gen_check 존재 기반 건너뛰기, 출력 일치 채택 gate. 재사용 산출물은 요청 집합·입력·protocol·adapter·선택 근거를 재검증한다.
- `run_iter012_rest.py`는 이번 실행에 사용하지 않는다. 새 실행 진입점과 의존 파일을 protocol에 등록한다.
- 필요한 `test_rsna_iter011.py` fixture를 최신 provenance에 맞추고, 재사용 GPU 검사기의 고정 장치 매핑을 상속된 허용 집합에 맞춘다. 사용하지 않는 부모 trajectory migration의 확장 검사는 미룬다.
- 미추적 `test_rsna_iter010_gpu.py`와 모든 과거 결과는 보존한다. Git 관리는 orchestrator가 수행한다.

# Proposed Experiment

## 목적함수와 공정한 비교

A는 effective batch의 assistant 학습 token 위치, E는 그중 좌표 숫자 위치다. N=|A|, g_t는 정답 숫자다. 숫자 오른쪽부터 자리 가중 w_t를 1,2,3,4로 둔다. p_t는 기존 softcap 이후 전체 vocabulary softmax다.

- `L_C = sum_A[-log p_t(g_t)] / N`
- `L_H = L_C + 0.1 * sum_E[w_t * (-log p_t(g_t))] / N`
- `q_t(v) = exp(-(v-g_t)^2 / 1.0) / sum_{u=0..9} exp(-(u-g_t)^2 / 1.0)`
- `L_D = L_C + 0.1 * sum_E[w_t * sum_{v=0..9} q_t(v) log(q_t(v)/p_t(v))] / N`

q는 전체 vocabulary에서 숫자 이외 위치의 질량이 0인 분포로 해석한다. p를 숫자 10개로 다시 정규화하지 않는다. E가 비어 있으면 추가 항은 0이다. H와 D는 같은 위치·가중·분모를 쓴다. 모든 조건에서 CE, 추가 항, 전체 loss, gradient norm을 따로 기록한다. tau·alpha·자리 가중은 이번 결과에 맞춰 탐색하지 않는다.

공통 초기 adapter는 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`다. 파일 hash와 config 연결을 검증한다. base와 언어층 LoRA 범위는 유지하고 optimizer는 새로 초기화한다. rank16/alpha32/dropout0.05, AdamW와 clipping은 기존 설정을 유지한다. 새로운 적응 단계와 같은 단계의 중단·재개를 구분한다.

## 1. 동작 확인

train에서 16명(양성 8명, 두 음성 층 각 4명)을 고정한다. 양성에는 단일·복수 box와 크기 층을 포함한다. 세 loss의 입력·수치 검사를 수행하고 C와 D의 실제 학습 경로에서 gradient 및 checkpoint 재개를 확인한다. 작은 overfit은 경로 검사로만 해석한다.

실제 모델에서 최소 한 번의 optimizer 중간-step 중단·재개를 수행한다. batch ID, token/mask digest, loss 성분, LR, optimizer step과 RNG를 대조한다. 결정적 검사와 본실험 kernel의 수치 허용 범위를 분리한다. 통과 후에는 아래 가능성 탐색을 진행한다.

## 2. 가능성 탐색

기존 train 2,400명 중 1,200명: opacity 600명, Normal 300명, NoOpacity/NotNormal 300명. 양성은 개별 box 면적·box 개수·환자 union 면적의 층을 반영해 결정적으로 추출한다. 작은 층을 제외하지 않고 추출 수와 원분포를 기록한다. 동일 환자를 여러 번 넣지 않는다. seed와 추출 규칙을 결과 확인 전에 고정한다.

validation 400명 중 200명(양성 100명, 두 음성 층 각 50명)을 V200으로 고정한다. 전체 V400과 겹치는 개발 subset이며 독립 검증으로 표현하지 않는다. 모든 조건이 같은 train 순서와 V200을 사용한다.

C/H/D 각각 seed17, 추가 3 epochs, effective batch16, 75 updates/epoch, 총 225 updates·3,600 presentations다. peak LR 2e-5, 5% warmup 뒤 이 단계 225 updates에 걸친 cosine을 사용한다. 기존 5→8 epoch schedule을 사용하지 않는다.

V200 생성은 시작점과 update75/150/225에서 한다. 각 조건의 최종 checkpoint와 V200에서 선택한 checkpoint를 V400으로 평가한다. 두 checkpoint가 같으면 중복 생성하지 않는다. B0의 V400 출력은 현재 입력·adapter·생성 조건의 호환성을 검증하면 기존 응답을 재사용할 수 있다.

선택 기준은 아래 Evaluation을 따른다. 각 조건에 동일한 checkpoint 기회를 준다. 선택 결과와 고정 최종 checkpoint 결과를 모두 보고한다.

## 3. 규모 확대

D의 V400 결과가 C보다 S_loc 0.03 이상 높고 운영 제약을 만족하면 확대한다. 점추정이 0.03 미만이어도 paired 95% CI 상한이 0.03 이상이며 V200의 마지막 구간에서 D의 S_loc가 0.01 이상 개선됐다면, 정밀도·학습량 부족을 구분하는 확대를 한 번 수행할 수 있다. 이 조건과 근거를 실행 전에 기록한다. 동작 확인이나 loss 감소만으로 확대하지 않는다.

확대는 기존 train 2,400명 전체, seed17, 공통 B0에서 새 optimizer로 시작한다. C와 D 각각 LR 2e-5/5e-5, 추가 3 epochs·450 updates·7,200 presentations의 네 trajectory를 실행한다. 이는 가능성 탐색에서 유망성이 확인된 뒤의 제한된 LR 비교다. V200은 update150/300/450, V400은 최종 및 선택 checkpoint에 사용한다.

D의 선택 LR에서 H를 동일 표본·순서·450 updates로 실행한다. H는 해당 설정의 기전 ablation이며 H의 최적 LR를 찾았다고 주장하지 않는다. C와 D는 같은 LR·checkpoint 선택 예산으로 비교한다. 추가 항의 실측 비용이 C보다 10% 이상 크면 유망 D에 한해 측정 GPU 비용을 맞춘 C도 보조 비교로 둔다. 이 비교의 update 수는 학습 처리량으로 산출해 시작 전에 잠그고, 평가 비용은 별도로 보고한다.

확대 후 D가 가장 강한 C보다 S_loc 0.03 이상, 같은 설정 H보다 0.01 이상 높고 운영 제약을 만족하면 seed29/43으로 C와 D를 재현한다. 각 seed의 기존 `lr2e-4_s{seed}/epoch_05/adapter.pt`를 공통 시작점으로 사용한다. 선택한 LR와 450-update 일정을 고정하며 같은 V200/V400 평가 규칙을 적용한다. 두 번째 단계 seed만 바꾼 것인지 부모 학습 seed까지 바꾼 것인지 명확히 기록한다.

학습 말기에 생성 성능이 계속 오르거나 LR별 결과가 크게 갈리면 충분한 수렴을 선언하지 않는다. 미정의 추가 schedule을 임의 실행하지 않고 해당 비교를 inconclusive로 보고하며 다음 판단에 필요한 학습량 근거를 남긴다. 반대로 이득이 추가 SFT나 H로 설명되면 D의 다중 seed 확대를 중단한다.

## 4. 독립 확인과 두 번째 데이터셋

이번 반복은 개발 비교까지다. 기존 선행 loss의 이식 효과만으로 새 방법의 독립 확인을 시작하지 않는다. reserve opacity 496명과 음성 집단을 보존한다. 향후 새로운 방법·가장 강한 baseline·설정이 고정되면 양성 496명과 두 음성 층 각 248명, 총 992명을 확인 후보로 삼는다. 실제 file/pixel hash·과거 exclusion 검증 후 최종 수를 고정해야 하며 지금 접근·독립성 gate가 완료됐다고 가정하지 않는다.

양성 496명에서 paired 차이 SD가 0.3–0.5라면 CI 반폭은 약 0.026–0.044라는 이전 계산을 계획 참고로만 사용한다. 실제 효과의 정밀도와 seed 변동은 별도로 검토한다.

Kvasir-SEG는 두 번째 modality 후보로 유지한다. 공식 archive·bbox/mask 일치·중복·patient/video 분할 근거를 확인하기 전에는 학습·test 수를 확정하지 않는다. RSNA 확대가 유망하면 이 데이터 gate를 후속 방법 계획에 필요한 범위에서 조사해 기록한다. 파일 접근 실패가 현재 RSNA 실험을 막지는 않는다. 양성 polyp 데이터로 무병변 suppression이나 환자 독립성을 주장하지 않는다.

## GPU 배치와 예상 비용

실행 직전 `nvidia-smi`로 허용된 두 GPU의 여유를 확인하고 UUID와 논리 index 대응을 기록한다. 다른 사용자의 프로세스는 변경하지 않는다.

학습은 두 GPU에 독립 조건을 하나씩 배정하는 구성을 출발점으로 삼는다. 기존 약 12.2GB/worker에서는 worker당 2GB 여유를 포함한 학습 worker 두 개가 한 장에 들어가지 않으므로 무조건 증설하지 않는다. microbatch2와 유망한 확대 후보 microbatch4를 train pilot에서 비교하되 effective batch16을 유지한다. 메모리·출력·학습 정합성이 유지되는 빠른 구성을 선택한다.

추론은 train에서 고정한 48명으로 GPU당 1 worker와 2 workers를 비교한다. 이미 검증한 동등 구성의 실측을 재사용할 수 있으면 중복 비교 비용과 근거를 적는다. greedy token 출력 일치, 요청 수·중복·누락 0, 전체 처리량, GPU별 peak, 긴 출력 지연, OOM 및 CPU/RAM/I/O 경합을 확인한다. 출력 일치 실패 구성은 채택하지 않는다. 각 GPU의 동시 peak와 다른 점유에 worker당 2GB 여유를 더해 용량 이내여야 한다.

기존 750-update 병렬 학습·평가 약 5.3시간을 거칠게 환산하면 가능성 탐색은 준비·생성을 포함해 약 3–5시간, full-train의 네 비교와 H는 추가 약 8–12시간, 조건부 두 seed 재현은 추가 약 6–9시간으로 추정한다. 새 loss의 실제 비용은 미측정이다. pilot 후 `updates/학습 처리량 + 생성 요청 수/생성 처리량 + 준비·저장 비용`으로 다시 산출한다. 이 시간은 중단 상한이 아니다.

# Implementation Tasks for Claude

1. 기존 PID/starttime·소유 lock과 checkpoint를 먼저 확인해 살아 있는 작업을 중복 실행하지 않는다. 이번 산출물은 모두 `research/results/iter_013/` 아래 새 경로에 저장한다.
2. 필요한 실행기 결함을 수정하고 오래된 final/gen_check를 내용 검사 없이 재사용하는 경로를 제거한다. 자식 종료 코드를 모두 수집하고 completion을 원자적으로 기록한다.
3. 현재 trainer에 명시적인 추가 적응 설정을 연결한다. subset을 `--pilot`으로 우회하지 않는다. 초기 adapter hash, 새 optimizer 여부, 단계 전체 update 수, train/V200/V400 ID, loss 설정, 평가 일정과 선택 근거를 protocol에 잠근다. 과거 protocol은 보존한다.
4. JSON 좌표 span과 token 연결, H/D loss를 구현한다. 기존 assistant loss 함수와 LoRA 코드를 재사용한다. auxiliary metadata가 모델 forward 인자로 전달되지 않게 한다.
5. 필수 CPU 수치·mask·provenance 검사와 실제 GPU 재개 검사를 수행한다. 통과하면 C/H/D 가능성 탐색을 실행하고 사전 기준에 따라 확대한다.
6. checkpoint에는 adapter·optimizer·RNG·batch 위치·loss 설정·입력 digest를 저장한다. 매 50 updates와 평가 milestone에서 저장하고 pending validation을 재개한다. 결과 파일은 worker별로 분리하며 claim·중복·누락 검증을 유지한다.
7. 저장 원시 응답에서 F1과 오류 분해를 재집계한다. 최종 선택 근거·완전성·adapter/protocol 연결을 검사한 뒤 보고서를 만든다. 필요한 소스는 orchestrator의 체크포인트 보존 대상에 포함하며 모델·결과 파일을 코드 커밋에 넣지 않는다.

# Evaluation (성공/실패 기준 포함)

주지표는 V400 양성 환자 평균 `S_loc=(F1@0.3+F1@0.5)/2`다. 환자별 최대 cardinality one-to-one matching을 유지한다. box를 독립 표본으로 취급하지 않고 환자 단위 paired bootstrap 10,000회로 차이의 CI를 계산한다. 개발 자료에서 선택한 checkpoint의 CI는 탐색적 수치이며 확증 검정으로 표현하지 않는다.

checkpoint 선택은 유효 출력률 99% 이상, B0 대비 두 음성 층 valid_empty 감소 각각 3 percentage points 이내를 만족한 후보에서 S_loc 최대다. 동률이면 빠른 checkpoint를 택한다. 이는 운영상 guardrail이며 임상적 비열등성 기준이 아니다. 적격 후보가 없으면 실패를 숨기기 위해 규칙을 완화하지 않는다. 기존 utility도 병기한다.

보고 항목은 F1@0.3/0.5, 양성 valid_empty, 두 음성 층 valid_empty, 형식 실패·잘림, 예측 개수, 개별 box 크기별 recall, GT 개수별 성능, 환자 union 면적별 성능이다. 크기 경계는 기존 train 전체에서 고정하고 서로 다른 small 정의를 혼용하지 않는다.

- **가설 지지:** D가 공정하게 강화한 C와 H를 넘어 사전 확대 기준을 충족한다. 다중 seed를 실행했다면 각 seed 차이와 범위를 모두 제시한다. 이는 이식안의 개발 성능 근거다.
- **유효한 음성 결과:** 수치·입력·생성이 유효하지만 이득이 C 또는 H로 설명되거나, 제약을 지키는 D의 이득이 작다. 이번 설정의 추가 가치가 약하다고 판정한다.
- **inconclusive:** 표본 정밀도·학습 추세·LR 민감성 때문에 판단이 바뀔 여지가 남는다. 필요한 추가 검증을 특정한다.
- **execution_failed:** 입력 누수, span/gradient 오류, 요청 누락, protocol 불일치 등으로 비교가 무효다. 학습 가설 실패로 기록하지 않는다.

이번 반복을 마쳐도 새로운 방법론 기여, 다중 데이터셋 일반화, 연구 목표 달성은 미완료다.

# Risks / Checks

자리별 거리 loss는 숫자 길이 변화·carry·box 전체 기하·누락 결정을 직접 해결하지 못한다. 개선이 없으면 그 범위로 해석한다. 작은 box와 병변 개수의 confound, 주석 경계 모호성, 사전학습 노출과 legacy 익명 영상 중복 불확실성을 유지한다.

C/H/D의 분모·가중·token 위치 차이는 비교를 무효화할 수 있으므로 최우선 검사한다. 전체 vocabulary logits에 추가 대형 복사를 만들지 않고 기존 logits에서 숫자 열을 취한다. 메모리 부족 시 batch·동시성을 조정하되 표본·metric·성공 기준은 바꾸지 않는다.

OOM·비정상 수치·진행 정체는 원인을 확인하고 안전한 checkpoint에서 재개한다. 기존 완료 파일이나 claim을 무조건 삭제하지 않는다. 선택적 리팩터링과 사용하지 않는 migration 보완으로 GPU 비교를 지연시키지 않는다.

## 대규모 GPU 필요 후보

GETok 전체 SFT/RL, MedLoc-R1의 원논문 GRPO, IoU-PD full-parameter teacher/student 학습과 R-VLM의 전체 vision 적응을 보존한다. 현재 두 RTX 3090에서는 경량 이식과 순차 계산 가능성을 별도로 평가한다.

# 계획의 근거 (GPT 조사 노트)

## 이번 판단

추가 SFT와 가까운 선행 목적함수를 비교하는 구현으로 넘어간다. 최소 수정 preference는 독립적인 기여를 확보하지 못해 보류한다. 이번 라운드는 문서·소스·저장 설정·tokenizer JSON을 읽었으며 코드 수정, 파일 생성, 테스트, 모델 실행은 하지 않았다.

## 1. 이전 질문: DIST²Loss와 R-VLM 중 무엇을 먼저 이식할 것인가?

DIST²Loss를 먼저 선택한다. 현재 `rsna_diag/train.py:assistant_loss_sum`은 assistant 예측 위치의 logits를 계산한 뒤 CE를 구한다. 같은 logits에 좌표 위치의 추가 loss를 계산할 수 있어 모델·attention·영상 입력 변경 없이 목적함수를 비교할 수 있다.

DIST²Loss 원문의 Appendix A는 다자리 숫자에서 credit assignment의 한계를 인정한다. 특히 자리값 가중은 천/백/십/일에 4/3/2/1을 사용하며, 1000/100/10/1 가중과 다르다. contrastive target augmentation도 제안하지만 세부 구현을 현재 코드에 그대로 재현할 근거는 부족하다. 따라서 이번에는 자리별 거리 항과 자리 가중을 명시적으로 정의한 이식안만 평가한다. 전체 숫자 거리나 box IoU를 최적화한다고 표현하지 않는다. [원문 v3](https://arxiv.org/html/2503.02379v3)

저자 저장소에는 조회 시 training/inference code가 Coming Soon으로 표시돼 있다. 저자 구현의 재현이 아니라 원문 기반 이식으로 기록한다. ICLR 공식 기록은 확인했으나 OpenReview 최종 PDF는 browser challenge로 본문을 읽지 못했다. 최종본과 v3의 세부 수식 동일성을 확인했다고 주장하지 않는다. [저자 저장소](https://github.com/JiwanChung/dist2loss), [ICLR 공식 기록](https://proceedings.iclr.cc/paper_files/paper/2026/hash/13b45b44e26c353c64cba9529bf4724f-Abstract-Conference.html)

R-VLM의 Section 3.3은 GT 주변 pseudo box의 CE를 GIoU로 가중한다. 여러 label을 묶기 위해 attention 차단과 position 재사용을 적용한다. 기하 supervision은 더 직접적이지만, 현재 복수 병변 JSON에 적용하려면 대체 label·정렬·종료 token과 연산량을 추가로 정해야 한다. 이번에는 목적함수 하나의 차이를 명확히 비교할 수 있는 DIST²Loss 이식안을 우선한다. 이 선택은 R-VLM의 열등함을 뜻하지 않는다. [R-VLM 원문](https://arxiv.org/html/2507.05673v1)

## 2. tokenizer와 학습 경로에서 확인한 것

고정 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`의 tokenizer JSON을 직접 읽었다. 숫자 0–9의 vocabulary ID는 각각 236771, 236770, 236778, 236800, 236812, 236810, 236825, 236832, 236828, 236819다. 조회한 10/39/40/100/1000 항목은 없다. 이것은 vocabulary 확인이며 실제 chat sequence에서 좌표 span 연결을 검증한 결과는 아니다.

`sft_data.py`는 0–1000 정수 yxyx 좌표를 결정적으로 정렬해 JSON을 만들고 assistant 본문과 `<end_of_turn>`만 학습한다. 추가 loss는 `box_2d` 값의 숫자에만 적용해야 한다. key 이름의 `2`, label, 괄호, 공백, 종료 token을 좌표로 잡는 정규식은 부적절하다. 실제 template sequence의 token offset과 JSON 좌표 구간 대조를 구현 진입 검사로 지정한다.

`train.py`는 effective-batch 전체 assistant token 수로 CE 합을 나눈다. 추가 loss도 동일 분모를 사용해야 microbatch·양성 비율·응답 길이에 따라 비교 조건이 달라지는 것을 막을 수 있다. softcap 이후 FP32 logits와 기존 전체 vocabulary 정규화를 유지한다.

또한 기존 trainer는 본실험 ID 경로와 5→8 epoch 규칙을 고정한다. 새 subset 학습을 `--pilot`으로 우회해서는 안 된다. 새 protocol에 등록된 분할·초기 adapter·학습 일정·평가 일정을 검증하는 명시적인 적응 단계가 필요하다.

## 3. 이전 질문: 최소 수정 preference의 차별성이 남는가?

새로 확인한 TD-DPO는 minimal-edit pair와 차이 token 가중을 함께 제안한다. 의료 대화 연구이며 bbox 성능 근거는 아니지만, 앞선 후보의 핵심 설계와 직접 겹친다. 단순히 수정 구간에 높은 가중치를 주는 것을 새 목적함수로 선택할 근거가 부족하다. [TD-DPO 원문 v1](https://arxiv.org/html/2607.18304v1)

좌표 교정은 JSON 필드의 문자 구간을 token 구간에 연결할 수 있다. 추가·삭제는 양쪽 응답을 따로 정렬하고 쉼표·닫는 괄호·종료 결정을 포함해야 한다. 삭제된 쪽에는 대응 token 자체가 없으며 수정 이후 같은 문자열도 prefix가 달라 조건부 확률이 달라진다. 전체 suffix를 포함하면 sequence preference에 가까워지고, 제외하면 다른 surrogate 목적함수가 된다. 기술적으로 정의할 수 있다는 사실만으로 차별성이 생기지는 않는다.

따라서 이번에는 pair 생성·DPO 학습을 구현하지 않는다. 후속 재검토에는 SPR·TD-DPO, 같은 수정 정답의 SFT, 같은 pair의 sequence DPO를 넘어서는 차이와 최소 반증 실험이 필요하다. 방법 전체의 불가능 판정은 아니다.

## 4. 이전 질문: 비교 규모와 선택 예산을 어떻게 고정할 것인가?

공통 시작점은 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`다. 저장 train config에서 rank16/alpha32/dropout0.05, effective batch16, microbatch2, 238개 LoRA 대상과 29,802,496개 학습 parameter를 확인했다. 새 단계에서는 optimizer를 새로 만들고 부모 학습 trajectory를 그대로 재개했다고 주장하지 않는다.

train 1,200명·seed17·225 updates의 세 조건 비교 후 실제 생성 결과로 확대한다. 주지표는 양성 환자의 `S_loc=(F1@0.3+F1@0.5)/2`다. 좌표 가중 CE를 함께 두어 거리 분포의 효과와 숫자 supervision 증가를 분리한다. 전체 validation은 시작점·최종 checkpoint·subset에서 선택한 checkpoint에 사용한다. 구체적인 일정과 확대 기준은 실행 계획에 고정했다.

이번 비교는 선행 목적함수의 개발 평가다. reserve 양성 496명을 이 비교에 사용하지 않는다. 기존 confirm 800명은 이미 방법 선정에 활용됐으므로 개발 자료로 취급하되 과거 독립 확인 결과의 역사적 유효성은 유지한다.

## 5. 재사용과 자원

`agent/GOAL.md`, `LIMITATIONS.md`, iter_009 원본 review.json, iter_012 review.md, `CODE_ASSETS.md`와 운영 정책을 확인했다. `research/` HEAD는 `783d2d04671ae296f3dc0c700e575f8af8e021c9`이며 tracked diff는 없다. 필요한 파일은 현재 브랜치에 존재한다. 미추적 `test_rsna_iter010_gpu.py`는 보존하며 승인 대상으로 편입하지 않는다.

실제 protocol 경로는 `research/results/iter_012/protocols/main_protocol.json`이다. 기존 생성은 concise prompt, greedy, 출력 길이 1000→2000→4000의 재시도 규약을 사용한다. 동일 조건을 이어가며 실행기 변경 때문에 과거 protocol 파일을 고치지 않는다.

직전 실측의 학습 GPU별 약 12.2GB와 두 trajectory 750 updates의 병렬 실행 약 5.3시간을 비용 추정의 출발점으로 삼는다. 이번 추가 loss의 메모리·처리량은 미측정이다. 두 GPU에서 조건을 병렬 실행하고, 추론은 GPU당 복수 worker를 포함한 구성의 정합성과 안전 여유를 확인한다.

## 대규모 GPU 필요 후보

기존 GETok 전체 SFT/RL, MedLoc-R1 원논문 GRPO, IoU-PD full-parameter teacher/student 학습을 보존한다. R-VLM의 전체 모델·vision 경로 적응과 효율적 다중 label 학습도 장기 비교 후보로 둔다. 원문 규모가 크다는 이유로 LoRA 축소판까지 불가능하다고 판단하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_013/think/
