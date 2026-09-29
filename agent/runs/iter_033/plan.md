# 요약

- **이번에 할 일:** VinDr 승인 대기 동안 공식 Faster R-CNN을 RSNA에 적응시켜 기존 MedGemma LoRA와 정확도·오류·비용을 비교한다.
- **필요한 이유:** 기존 bbox+규칙은 전용 detector가 아니다. 실제 대안과의 비교가 있어야 VLM 내부 grounding의 추가 투자 가치를 판단할 수 있다.
- **확인할 기준:** 같은 annotation, 충분한 detector 학습, validation 선택, 동일 환자 paired 평가와 추론 비용을 확보한다.
- **주의·다음:** 기존 confirm 800명은 개발 비교다. 외부 일반화·새 contribution은 미검증으로 유지하고, 결과에 따라 후속 질문을 정한다.

# Current Understanding

iter_009는 정상 사용에서도 남는 RSNA opacity grounding 오류를 검증했다. iter_012는 직접 LoRA SFT로 확인 양성 400명의 F1@0.3을 seed별 0.631–0.653으로 개선했다. 이 성과는 유지하지만 실제 전용 detector와의 비교는 아직 없다.

iter_031의 continuation은 E402에서 누락 사건 11/27을 회복했으나 F1@0.3을 0.6276에서 0.4738로 낮췄다. 현재 continuation 방법에 대한 추가 투자를 종료한 판단을 유지한다. 남은 분석은 저장 출력으로 보완한다.

사용자 보완 ID `20260929_131450_4dda5b89`를 적용한다. GOAL·MedGemma 1.5·LoRA checkpoint·기존 결과를 유지한다. iter_032의 외부 전이 계획은 승인 대기로 보존하며 실패나 완료로 표시하지 않는다. VinDr 승인 통지 전 다운로드와 외부 본평가를 하지 않는다. MRI F139와 기존 reserve는 열지 않는다.

# Strategy Check / 연구 방향 판단

**중요한 능력과 사용 과제:** 의료 VLM의 위치 출력이 전용 검출 대안에 비해 어떤 가치를 갖는지 확인한다. 정확도뿐 아니라 놓치는 병변, FP 비용, 계산 비용이 후속 post-training의 목적을 결정해야 한다.

**확인된 사실과 경쟁 설명:** SFT의 RSNA 검출 개선은 유효하다. 그러나 그 개선이 전용 detector보다 유리한지, 같은 오류를 더 큰 비용으로 만드는지, 조건별 상보성이 있는지는 미확인이다. continuation의 후보 회복도 FP 비용을 해결하지 못했다.

**선택 비교:** 현재 loss·continuation 개선은 강한 대안 대비 필요성이 불명확하다. 실제 detector 비교는 같은 자료와 저장 출력으로 이 불확실성을 직접 줄인다. 외부 전이는 승인 대기이며, 언어·근거 과제로의 전환에는 사용 목적과 정답을 별도로 구체화해야 한다.

**결정:** 이번에는 빠진 detector 비교군을 확보한다. detector가 정확도·비용에서 유리하고 오류도 겹치면 단순 bbox 개선의 우선순위를 낮춘다. SFT의 조건별 이점이나 상보성이 남으면 외부 확인 후보로 보존한다. 어느 결과도 자동으로 앙상블·새 loss 학습을 예약하지 않는다.

# Hypothesis

주질문은 동일 annotation budget에서 전용 detector와 보존된 SFT 사이의 위치 정확도·FP 비용·추론 비용 차이다. detector 우위나 SFT 우위를 미리 가정하지 않는다.

부질문은 두 방식의 미검출이 얼마나 겹치고, 어느 조건에서 한쪽만 GT를 검출하는지다. 이런 상보성은 후속 과제 선택의 근거이지 실제 결합 방법의 성능 증거가 아니다.

이번 역할은 diagnostic이다. 알려진 detector를 학습하는 목적은 새 방법 개발이 아니라 비교와 투자 판단이다.

# Limitation Evidence / Correct Usage Checks

- `lesion-grounding-generalization`은 iter_009·012의 원본 리뷰에서 validated다. 범위는 고정 MedGemma revision과 RSNA opacity 조건이다.
- `rsna-partial-omission-continuation`은 observed다. 후보 회복과 전체 검출 악화를 함께 유지한다.
- MedGemma revision은 `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`다. 원본 prompt·processor·adapter·출력 길이·EOS·parser 규약을 유지한다.
- detector의 원본 uint8 영상, RGB 복제, 0–1 변환, 내부 resize, pixel xyxy와 기존 padded yxyx 변환을 검증한다. 이중 normalization이나 이중 resize를 피한다.
- 기존 출력 재사용 전에 환자×모델×prompt 예상 집합, source/completion/protocol/adapter 및 현재 image hash를 검사한다. 과거 protocol의 소스는 해당 보존 버전과 대조하며 현재 코드로 원본 hash를 덮어쓰지 않는다.
- pretraining 노출과 legacy 익명 영상의 완전한 독립성은 입증하지 못했다. 이번에는 기존 train/validation/개발 비교 집단의 환자·SOP·decoded pixel 중복과 연결을 확인한다.

# Contribution Path / Baselines / Reuse

## 비교군

1. **전용 detector:** `torchvision.models.detection.fasterrcnn_resnet50_fpn_v2`, 명시적 `COCO_V1` 가중치. COCO predictor를 로드한 뒤 배경+opacity의 2-class predictor로 교체한다. [공식 모델 문서](https://docs.pytorch.org/vision/0.21/models/generated/torchvision.models.detection.fasterrcnn_resnet50_fpn_v2.html)
2. **직접 SFT:** iter_012 seed17·29·43의 선택된 checkpoint와 저장 concise 출력. 주비교는 사전 고정 B0=seed17이다. 다른 seed는 모두 별도로 보고하고 유리한 seed를 대표로 고르지 않는다.
3. **미적응 base:** 기존 official_long과 concise 저장 출력을 함께 보고한다. 낮은 prompt 결과만 선택하지 않는다.
4. **진단용 상한:** 동일 GT에 대한 두 방식의 검출 합집합. GT를 이용한 선택·FP 제거의 실용 성능으로 부르지 않는다.

주 비교 자료는 train 2,400명(양성1,200/Normal600/NoOpacity·NotNormal600), validation 400명(200/100/100), 기존 confirm 800명(400/200/200)이다. 각각 GT box는 1,774/309/589개다. 모든 음성 범주를 유지한다.

같은 annotation budget만 맞춘다. detector의 COCO 사전학습·전체 backbone 적응·증강·800-pixel resize와 MedGemma의 의료 사전학습·언어층 LoRA·기존 processor 차이를 공개한다. 기존 SFT의 완전 수렴이나 최적 성능을 전제하지 않는다. 같은 epoch/step을 계산량 동등성으로 해석하지 않는다.

## 재사용과 기반

`reuse_iteration=6`으로 새 접근법 기반을 요청하고 JSON의 두 reuse_assets 묶음을 선별 반입한다. 해당 SHA·파일·의존성·충돌 부재는 계획 단계에서 확인했다. branch·commit은 orchestrator가 관리한다.

geometry·parse·metrics·sft_eval·LoRA 구성요소를 재사용한다. generate에서는 모델·영상·입력·단일 요청 함수만 latency 경로에 연결한다. 과거 run_worker·launch·continuation pipeline을 호출하거나 일괄 정비하지 않는다. lock_protocol의 과거 전체 파일 목록을 새 실험에 그대로 적용하지 말고 필요한 digest 함수와 새 필수 잠금 목록을 사용한다.

risk30_eval·risk28_eval의 사용 범위는 iter_031 보완 분석이다. 입력 검증과 분모 결함을 먼저 보완한다. 과거 출력은 읽기 전용이며 모든 신규 결과는 `research/results/iter_033/` 아래에 저장한다.

# Proposed Experiment

## 0. 환경·자료·규약 고정

기본 관리·MedGemma Python은 상속된 medgemma 환경을 유지한다. detector만 `/home/test/.conda/envs/natten_py310/bin/python`을 subprocess 실행기로 지정한다. `conda activate`, `pip install`, 환경 간 PYTHONPATH 혼합은 하지 않는다. 해당 환경과 모델 캐시를 수정하지 않는다. 구현 단계에서 필요한 임시 파일은 이번 결과 경로에 둔다.

실행 호스트에서 기존 launcher/worker의 PID·starttime·lock을 먼저 확인한다. 타인의 프로세스나 살아 있는 기존 작업을 종료하지 않는다. detector 환경의 torch·torchvision·numpy·Pillow 버전, CUDA build·driver, import, CPU/CUDA NMS 및 ROIAlign forward·backward를 확인한다. 실패하면 정확한 오류와 필요한 환경 조치를 보고하고 detector 성능 판정을 보류한다.

공식 COCO 가중치는 공식 URL에서만 확보한다. 전용 결과 경로에 저장하고 torchvision의 hash 검증 및 전체 SHA256·URL·크기를 기록한다. hf_cache에는 쓰지 않는다. 공식 구현과 모델 state를 확인한 뒤 predictor 교체 및 trainable parameter 수를 검증한다.

iter_010의 GT/infer manifest와 세 ID 파일, iter_012 selection·checkpoint·원시 출력·completion을 잠근다. 영상 file hash와 decoded pixel hash, GT 연결, 분할 교집합을 검사한다. 중복이나 provenance 불일치는 조용히 제외하지 않고 원인을 해결한다.

표본 선택은 결과를 보기 전에 고정 salt와 patient ID hash 순서로 수행한다. category, 양성 GT 개수(1/2/3 이상), train에서 정한 면적 구간을 반영해 비례 배분하고 희귀 층을 보존한다. 한 환자를 반복 평가하더라도 환자 수가 늘어난 것으로 세지 않는다.

## 1. 동작 확인

train D32는 양성16명·두 음성 범주 각8명으로 구성한다. 양성에 작은 병변과 복수 병변을 포함한다. 이 중 별도 표시한 8명은 overfit 동작 검사에 사용한다. validation V100은 50/25/25명으로 고정하고 이후 전체 학습 추세 검사에도 같은 집합을 쓴다.

검사 내용은 다음과 같다.

- 실제 영상과 bbox overlay, 비정사각 synthetic 좌표 왕복, horizontal flip 좌표, 빈 `(0,4)` GT와 Int64 label 처리.
- 공식 모델의 loss별 finite 값, predictor와 backbone gradient, optimizer update, train/eval 전환 및 BatchNorm 정책.
- 8명 overfit에서 초기 대비 loss와 실제 위치 출력 개선. 100 update에서 확인하고 개선 중이면 200 update까지 보완한다. 실패는 구현/학습 경로 문제이며 일반화 실패로 판정하지 않는다.
- optimizer-step 경계 저장·중간 epoch 재개에서 sample 순서·augmentation RNG·optimizer·scheduler·scaler·update index 복원. 중단 전후 저장 상태는 정확히 대조한다. CUDA 수치 차이는 동일 조건의 uninterrupted 반복 변동과 분리해 기록한다.
- detector 추론 24명 중단/재개와 부모 종료, 손상 tail 보존·복구, 중복/누락 및 source·checkpoint·completion 변조 거부.

동작 확인 checkpoint는 본학습 초기값으로 사용하지 않는다.

## 2. 가능성 탐색: train600·V100·seed17

train600은 300/150/150명으로 고정한다. GT 개수·면적 층을 비례 유지한다. COCO 가중치부터 시작해 6 epoch, effective batch8로 총 450 optimizer update를 수행한다. epoch3·6에서 V100 실제 검출을 평가한다. 무작위로 초기화한 2-class predictor의 epoch0 결과도 V100에서 보존한다.

고정 recipe는 다음과 같다.

- RGB 0–1 입력, detector 내부 short side800·max side1333, 내부 기본 normalization.
- horizontal flip 확률0.5만 적용하고 crop·색상 증강은 사용하지 않는다. 원본 annotation은 추가하지 않는다.
- trainable_backbone_layers=5. backbone/FPN/RPN/ROI head를 적응한다. 소규모 microbatch의 영향을 줄이기 위해 BatchNorm running statistics는 고정하고 affine parameter는 학습한다. 매 train 모드 전환 뒤 이 정책을 강제한다.
- SGD, momentum0.9, weight_decay1e-4, LR0.005, 첫 1 epoch linear warmup. 탐색 6 epoch에서는 이후 LR을 유지한다.
- 기본 FP32로 동작·수치 검사를 한다. AMP 적용은 D에서 finite gradient·loss·출력과 메모리·처리량을 확인하고 precision 정책을 본학습 전에 잠근다.
- effective batch8을 유지하며 microbatch2와 4 중 실측으로 선택한다. OOM이면 microbatch를 줄이고 accumulation으로 같은 effective batch를 유지한다.

**확대 기준:** 구현 gate를 통과하고 실제 검출이 발생하며, epoch0 대비 V100 양성 F1@0.3이 0.05 이상 또는 utility가 0.02 이상 개선되면 full-train으로 진행한다. 이 수치는 VLM 우위/열위 판정 기준이 아니라 detector 학습 신호를 확인하는 운영 기준이다.

기준에 못 미쳐도 유한한 학습과 실제 출력 개선 추세가 있으면 같은 recipe로 탐색을 12 epoch까지 보완한다. 그 뒤에도 신호가 없으면 입력·gradient·scale·pretraining 연결을 감사하고 학습 충분성 미확인으로 종료한다. 약한 detector 결과를 VLM의 장점으로 해석하지 않는다. 다른 architecture나 여러 LR 전수 탐색을 자동 실행하지 않는다.

## 3. 본학습과 수렴 보완

확대 시 subset checkpoint를 이어 쓰지 않고 동일 COCO 초기값에서 train2,400 전체로 seed17을 다시 시작한다. annotation budget은 기존 SFT와 동일하다.

기본 학습은 26 epoch, effective batch8, 총 7,800 update다. recipe는 탐색과 같고 epoch16·22 완료 뒤 LR을 각각 0.1배로 낮춘다. V100 실제 검출 평가는 epoch6·12·18·22·26에서 수행한다. 매 epoch 전체 validation은 하지 않는다.

V400은 epoch12와 epoch26, 그리고 V100에서 선택한 최고 checkpoint가 이 둘과 다를 때 해당 checkpoint에서 수행한다. 최종 후보는 동일 V400 범위에서 비교한다. V100의 최고 checkpoint는 utility, F1@0.5, 이른 epoch 순으로 정한다.

**수렴 보완:** V100에서 epoch22→26 utility 또는 F1@0.5가 0.01 이상 증가하거나, epoch26이 최고점에 근접한 상태에서 마지막 4 epoch의 평균 train loss가 이전 4 epoch 대비 10% 이상 감소하면 12 epoch를 추가한다. 현재 낮아진 LR을 유지하고 epoch32·38에서 V100을 확인한다. epoch38와 확장 구간 V100 최고 후보를 V400에서 평가한다. 최대 38 epoch는 이번 사전 학습 블록이며 보편적인 충분성 상한이 아니다. 여전히 명확히 상승 중이면 수렴 미확인으로 보고하고 전반적 우열 주장을 보류한다.

학습 loss·validation 검출·과적합·낮은 LR 구간의 변화로 학습 충분성을 설명한다. detector가 SFT보다 낮다는 이유로 중단하거나 유리한 checkpoint만 남기지 않는다.

**조건부 seed:** seed17의 V400 선택 후, B0와 F1@0.3 또는 F1@0.5 절대 차이가 0.03 이상이거나 한쪽만 검출한 GT 비율이 0.05 이상이면 seed29를 같은 고정 recipe로 학습한다. 두 detector seed의 B0 대비 차이 부호가 바뀌거나 차이 크기가 0.03 이상 달라지면 seed43도 추가한다. seed 판단은 개발 비교800의 detector 결과를 열기 전에 validation으로 끝낸다. 추가 seed는 동일 평가 일정과 수렴 규칙을 사용하고 모두 보고한다. 확대하지 않으면 단일 detector seed의 관찰임을 명시한다.

## 4. Confidence·NMS·checkpoint 선택

NMS IoU=0.5, detector score floor=0.001, detections_per_img=100을 사전 고정한다. 이는 공식 출력 상한이며 GT 최대 개수로 후보를 자르지 않는다. threshold 이전 후보와 confidence를 저장한다. V400에서 선택된 operating point가 cap에 걸리는 경우는 평가 한계로 기록하고, 해결 전 개발 비교800으로 진행하지 않는다.

threshold 후보는 `{0.01,0.025,0.05,0.10,0.15,…,0.95,0.975,0.99,1.0}`으로 고정한다. confidence가 threshold 이상인 box를 유지한다. checkpoint×threshold는 V400의 기존 utility를 최대화해 선택한다. 동률은 양성 F1@0.5, 작은 FP/환자, 이른 epoch, 높은 threshold 순이다. detector에는 label1만 opacity로 인정한다.

주 선택 checkpoint에서 별도로 FP/환자 budget 0.25·0.5·1.0을 만족하는 validation threshold를 정한다. 각 budget 아래 최대 lesion recall, 동률은 적은 FP·높은 threshold 순이다. 이 operating point는 개발 비교800에서도 그대로 사용한다. 평가800에 맞춘 threshold나 NMS 조정은 하지 않는다.

VLM은 기존 strict parser, 생성 목록과 순서, EOS 및 invalid 규약을 유지한다. 임의 NMS나 confidence를 추가하지 않는다. invalid는 양성 end-to-end F1=0이며 음성 정답 빈 출력으로 세지 않는다.

## 5. 개발 비교800과 오류 분석

설정·checkpoint·threshold·seed 집합을 잠근 뒤 기존 confirm800에 detector 추론을 수행한다. 이 집단은 이미 연구 개발에 사용됐으므로 독립 확인이라고 부르지 않는다. base와 SFT의 저장 본출력은 재생성하지 않는다.

주지표는 양성400명의 환자 평균 F1@0.3과 F1@0.5다. detector seed17−B0의 두 차이에 각각 97.5% paired bootstrap CI를 제공한다. bootstrap은 환자를 단위로 10,000회 수행하며 동일 resample을 모든 비교에 적용한다. seed를 독립 환자처럼 합치지 않는다.

함께 보고할 지표는 다음과 같다.

- 양성 환자 recall·precision, lesion 단위 recall, 양성 전체 미검출 및 valid-empty/invalid.
- 전체800 및 양성·Normal·NoOpacity/NotNormal별 FP/환자와 적어도 하나의 FP가 있는 환자 비율.
- GT 1개/2개/3개 이상, 기존 train 양성 union-area 삼분위, 별도 train 개별 GT 면적 삼분위에 따른 작은 병변 recall. 경계는 train에서만 정한다.
- validation에서 고정한 FP budget별 detector recall과 SFT의 고정 출력점. SFT에 임의 score를 붙여 AP를 비교하지 않는다.
- 같은 GT의 both-hit, detector-only, SFT-only, both-miss와 환자별 전체 검출 성공. IoU0.3·0.5를 모두 보고한다.

GT matching은 cardinality 우선, 총 IoU, 기존 동점 규칙을 유지한다. 예측 수가 많을 때는 GT subset DP를 사용한다. GT 최대4를 확인하며 GT 수 증가에 조용한 truncation을 하지 않는다. 동점 fixture와 실제 VLM 목록에서 exhaustive 기준과 대조한다. 상보성의 GT identity가 matching 동점에 민감한 경우 별도 표시하고, 단순 best-IoU cover 분석은 one-to-one 검출 지표와 분리한 민감도로만 제공한다.

FP 비용의 invalid 처리에서 전체 N으로 나눈 관측 FP는 하한이고 valid-only 평균은 조건부 값이다. 둘을 혼동하지 않는다. 누락된 실행 record는 invalid로 점수화하지 않고 평가를 중단한다.

## 6. 비용과 GPU 배치

실행 직전 `nvidia-smi`로 허용된 두 GPU의 UUID·여유를 확인한다. 상속된 허용 집합 안에서만 subprocess 장치를 나누고 논리/물리 index를 기록한다. 타인의 프로세스를 건드리지 않는다.

메모리 사전 예상은 detector FP32 microbatch2 학습 약6–12GiB, batch4 약10–18GiB, MedGemma bf16 추론 약8–10GiB다. 모두 미측정 추정치다. 실제 allocated/reserved와 GPU 전체 점유, optimizer·activation·긴 출력 peak를 확인해 각 worker당 최소2GiB 여유를 확보한다.

우선 한 GPU에 detector 학습, 다른 GPU에 immutable checkpoint validation 또는 MedGemma의 소규모 비용 측정을 배정한다. 독립 seed가 허용되면 두 GPU에 나눈다. 단일 학습만 남을 때는 D 단계에서 비교한 batch 확대/DDP 처리량 근거로 장치를 배정하며 불필요한 실험으로 채우지 않는다.

D 입력으로 학습 microbatch2/4의 유효 이미지/초와 peak를 비교한다. detector 추론은 batch1/4부터 비교하고, 남은 독립 shard가 충분하며 더 유망할 때 GPU당 worker2를 비교한다. batch 확대와 worker 확대를 모두 전수 탐색하지 않는다. 채택 기준은 출력·metric 정합성, worker당 안전 여유, 전체 처리량 개선과 오류 없음이다. worker1을 유지하면 메모리·처리량·의존성 근거를 기록한다.

공정한 latency는 validation에서 고정한 L64(양성32/음성 각16명)를 사용한다. 같은 GPU에서 detector와 B0를 각각 단독 resident 상태로 실행한다. 8건 warmup 후 동일64명×3회, 고정 순서 교차와 CUDA synchronize로 측정한다. 모델 로드 시간, 전처리 포함 end-to-end, 모델 실행 구간, 평균·p50·p95, peak VRAM을 구분한다. B0는 원래 concise·greedy·cap ladder를 유지하며 기존 validation token과 대조한다. 이 재생성은 비용 측정 표본에 한정한다. 두 모델의 framework와 precision 차이를 함께 기록한다. 전체 처리량 측정은 단독 batch1 latency와 별도로 보고한다.

기존 validation의 긴 출력 사례도 별도 stress 입력으로 확인한다. 저장 시간이 다른 worker 구성에서 측정됐다는 이유로 단순 속도비를 만들지 않는다.

예상 비용은 탐색 0.3–1.5시간, full seed당 약1.5–6시간, 수렴 보완은 full의 약46%, 비용 측정·평가는 약0.5–2시간이다. 이는 가정이며 시간 상한이 아니다. D에서 얻은 images/초로 `600×탐색epoch/r + 2400×본epoch/r + 평가·저장 비용`을 다시 산출해 실행 전에 남긴다. 조건부 seed와 두 GPU 병렬 wall-clock을 구분한다.

checkpoint는 최소 매 epoch와 100 optimizer update마다 optimizer-step 경계에 원자적으로 저장한다. model·optimizer·scheduler·scaler·RNG·환자 순서·cursor·protocol digest를 포함한다. 새 attempt와 immutable completion을 사용하며 기존 claim·원시 결과를 삭제하거나 실패 로그를 덮어쓰지 않는다.

## 7. iter_031 저장 출력 보완

C201/E402의 원시1,206건, source manifest/audit, 기존 protocol과 GT를 잠근 뒤 `results/iter_033/analysis_iter031/`에 저장한다. O/F 생성은 다시 하지 않는다.

원래 예측 box 수1/2 이상, 양성/두 음성 범주별로 회복·추가 TP/FP·F1·invalid를 계산한다. IoU0.5와 center-in-GT 기준은 민감도 분석으로 명시한다. 중심 기준은 추가 box 중심이 GT 내부에 있는지로 정의하고 위치 IoU 검증과 구분한다. 원래 엄격 누락 사건 정의와 H1/H2 판정은 바꾸지 않는다.

원본·중복 제거 민감도, 전체 N 기준 관측 FP 하한과 valid-only 평균, 생성 token·벽시계·추가 후보당 비용을 보고한다. 과거 구성 차이로 직접 비교할 수 없는 비용은 결측/비교 불가로 표시한다. iter_032 조사에서 이미 확인한 중복 제거 후 FP 증가를 다시 미확인으로 돌리지 않는다.

## 8. 독립 확인

이번 반복에서 새 독립 환자 집단을 열지 않는다. 학습 seed 재현은 환자 독립 확인과 다르다. VinDr 승인 통지 후 실제 권한·파일과 target 차이를 확인하고, 이번 detector 결과를 반영한 별도 계획에서 외부 확인을 설계한다. 기존 reserve와 MRI F139는 유지한다.

# Implementation Tasks for Claude

1. reuse manifest와 실제 반입 blob·의존성을 확인한다. 기존 프로세스 상태와 detector 환경 gate를 먼저 검사한다.
2. 이번 결과 경로에 data audit, 고정 D32/train600/V100/L64 manifest와 protocol을 만든다. 과거 source와 결과는 읽기 전용으로 연결한다.
3. 공식 detector 적응·추론·checkpoint와 새 실행기의 소유권·원자 저장·재개를 구현한다. 기본 MedGemma 환경을 교체하지 않는다.
4. 승인된 geometry/parser/sft_eval을 연결하고 bounded-GT DP matching을 기준 exhaustive와 검증한다. 기존 SFT 주수치를 독립 재현한다.
5. D 동작·자원·재개 gate를 완료하고 탐색→본학습→수렴/seed의 사전 decision을 코드에서 강제한다. 직접 worker 실행으로 gate를 우회하지 못하게 한다.
6. validation에서 선택을 잠근 뒤 개발 비교800·오류 상보성·latency를 완료한다. 미완료 결과로 completion이나 최종 decision을 만들지 않는다.
7. iter_031의 보완 분석을 새 경로에서 수행한다. 현재 실험과 무관한 과거 pipeline 정비는 하지 않는다.
8. 보고서에 실제 도달 단계, 표본·update·GPU별 peak·처리량·wall-clock, 선택 근거, 모든 실패 명령과 복구, 미실행 seed·독립 확인을 기록한다. `SELF_CHECK: PASS/FAIL`과 `SUMMARY:` 형식을 유지한다.

# Evaluation (성공/실패 기준 포함)

## 실행 유효성과 baseline 확보

환경·입력·좌표·재개·provenance gate, 유효한 학습과 validation 선택, 완전한 개발 비교가 있어야 valid_experiment=true로 판단할 수 있다. fixture나 overfit만으로 성공으로 보고하지 않는다. 충분한 비교군과 해석 가능한 차이를 확보하면 baseline diagnostic은 성공할 수 있지만 새 contribution이나 GOAL 달성과는 다르다.

## 양성: detector가 유리한 근거

투자 판단용으로 detector−B0의 F1@0.3·F1@0.5 CI 하한이 모두0보다 크고 적어도 한 점추정 차이가0.03 이상이며, 전체 FP/환자 증가의95% CI 상한이0.05 이하인지 확인한다. 단독 latency가2배 이상 빠른지 함께 보고한다. 이것은 임상 허용 한계가 아니라 다음 연구 투자 기준이다.

이 조건과 낮은 SFT-only 검출 비율이 함께 나타나면 현재 조건의 단순 bbox 개선 우선순위를 낮춘다. SFT-only GT 비율의95% CI 상한이5% 이하일 때 상보성이 작다는 근거로 사용한다. seed나 주요 층에서 반전되면 조건부 결론으로 낮춘다. 의료 VLM 전체 또는 detector+VLM 언어 과제의 우위를 주장하지 않는다.

## 음성 또는 SFT의 조건별 이점

반대 방향의 F1 차이, 적은 FP, 작은·복수 병변 등 사전 층의 이점이 남으면 해당 조건을 보존한다. detector의 입력·수렴·threshold·사전학습 연결을 통과한 경우에만 SFT의 제한된 장점으로 해석한다. 같은 조건을 VinDr 승인 후 확인할 후보로 남기며 즉시 새 loss를 시작하지 않는다.

## 오류 상보성

한쪽만 검출한 GT 비율이5% 이상이고 최소20명에 걸쳐 나타나며 환자 bootstrap에서도 양의 비율이 유지되는지 본다. IoU0.3/0.5, seed, FP budget에 대한 민감도를 함께 제시한다. 표본이 작거나 matching 동점에 민감하면 탐색적 관찰로 남긴다. GT 기반 union은 활용 가능한 여지의 진단이지 실제 결합 개선이 아니다.

## 불확정

CI가 의미 있는 양방향 차이를 포함하거나 학습이 계속 상승 중이면 우열을 보류한다. validation의 사전 수렴·seed 규칙으로 줄일 수 있는 불확실성만 이번 반복에서 보완한다. 평가800을 본 뒤 threshold·NMS·층 경계·prompt를 바꾸지 않는다. 추가 표본은 승인된 독립 자료가 생긴 뒤 별도 계획으로 다룬다.

환경 실패·data leakage·좌표 오류·완료 검증 실패는 execution_failed 범위로 기록한다. 짧은 탐색의 무개선은 detector 계열이나 의료 VLM 전체의 실패가 아니다. 모든 결과에서 같은 loss 탐색으로 이어가지 않고, 비교 우위·상보성·미확인 조건에 따라 다음 투자를 달리한다.

# Risks / Checks

- 기존 detector 환경의 CUDA 실행은 아직 미검증이다. 파일 존재나 import metadata를 실제 학습 성공으로 취급하지 않는다.
- BatchNorm·microbatch·AMP·학습률 변경은 결과를 본 뒤 임의 적용하지 않는다. OOM 복구는 effective batch와 precision 영향을 기록하고 안전하게 재개한다.
- detector confidence 선택과 VLM 고정 목록의 차이가 결과에 영향을 준다. 공통 utility와 FP budget별 결과를 함께 제시한다.
- small/multi 분석은 train 기반 경계와 모든 적격 환자를 사용한다. GT3개 이상 누락, invalid 제외에 따른 분모 변경, seed를 환자로 합치는 오류를 검사한다.
- 800명은 재사용된 개발 집단이다. bootstrap CI는 이 집단의 조건부 불확실성이며 새 독립 일반화의 보증이 아니다.
- GPU별 memory margin은 전체 점유에 worker당2GiB를 더해 판단한다. 처리량 개선이 없으면 동시성을 늘리지 않는다.
- 원본 결과·protocol·checkpoint·iter_032 계획을 보존한다. 선택한 실행 경로에 필요한 수정만 하며 관리 코드나 GOAL을 바꾸지 않는다.

## 대규모 GPU 필요 후보

다기관·다소견에서 vision encoder와 언어 모델을 공동 적응시키는 post-training은 장기 후보로 보존한다. 위치 검출과 언어·근거 연결을 함께 개선하려면 더 큰 데이터와 연산이 필요할 수 있다. 이번에는 두 RTX3090 안에서 전용 detector와 경량 VLM 적응의 실제 차이를 확보해 그 투자 필요성을 판단한다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드의 결론

앞 라운드의 세 질문에 답했고 구현 계획으로 진행한다. VinDr 승인 대기, RSNA detector 비교 우선, 기존 LoRA 성과·분할·출력 보존이라는 사용자 지시를 유지한다. 이번 라운드도 문서·코드·metadata·Git 자산만 읽었으며 파일 변경, 가중치 다운로드, GPU 실험은 하지 않았다.

### 1. 실행 환경

기본 medgemma 환경은 유지한다. detector 전용 subprocess는 이미 존재하는 `/home/test/.conda/envs/natten_py310/bin/python`을 명시적으로 호출하는 경로로 정한다. 이는 `conda activate`나 패키지 설치가 아니며, 다른 환경의 package를 medgemma에 섞지 않는다. 공통 관리와 MedGemma는 상속된 기본 Python을 계속 사용한다.

앞 라운드에서 확인한 torch 2.6.0+cu124·torchvision 0.21.0+cu124 환경에 공식 Faster R-CNN v2 소스가 실제 존재한다. 이번에는 해당 소스와 ROI postprocessing을 읽었다. `_C.so`의 단독 ldd에는 미해결 항목이 있지만 torch/lib의 libtorch·libc10·CUDA library와 nvidia/cuda_runtime의 libcudart 파일이 존재한다. torch import의 선행 로딩이 반영되지 않은 ldd 결과만으로 실행 가능 또는 불가능을 확정하지 않는다. 이전 import는 read-only 환경의 임시 디렉터리 문제에서 끝났으므로, 구현 단계의 쓰기 가능한 이번 결과 경로에서 import 및 CUDA NMS/ROIAlign forward·backward를 필수 gate로 둔다. 실패 시 환경 오류로 기록하며 약한 자체 detector로 바꾸거나 pip 설치로 우회하지 않는다.

### 2. 공식 detector와 학습 recipe

Faster R-CNN ResNet-50 FPN v2의 공식 COCO_V1 가중치를 선택한다. 공식 문서의 COCO mAP 46.7은 출발 baseline의 근거이며 RSNA 예상 성능이 아니다. [Torchvision 0.21 모델 문서](https://docs.pytorch.org/vision/0.21/models/generated/torchvision.models.detection.fasterrcnn_resnet50_fpn_v2.html)

실제 설치 소스는 COCO class 수로 가중치를 로드한 뒤 predictor를 교체해야 하는 경로와 BatchNorm 사용을 보여준다. 입력은 0–1 tensor와 pixel xyxy이며, 모델 내부 resize 후 반환 box는 입력 영상 좌표로 복원된다. [공식 v0.21 구현](https://raw.githubusercontent.com/pytorch/vision/v0.21.0/torchvision/models/detection/faster_rcnn.py)

공식 reference는 SGD·momentum 0.9·weight decay 1e-4와 batch에 따른 LR 조정을 사용한다. 이를 참고하되 아래의 RSNA 적응 recipe는 이번 계획의 사전 선택이다. 공식 COCO 학습을 그대로 재현한다고 주장하지 않는다. [공식 학습 reference](https://raw.githubusercontent.com/pytorch/vision/v0.21.0/references/detection/train.py)

선택 recipe는 전체 backbone 학습, BatchNorm running statistics 고정·affine 학습, effective batch 8, SGD LR 0.005, 1 epoch warmup이다. train 600명·seed17의 6 epoch 탐색에서 실제 validation 검출 개선을 확인한 뒤, 원래 COCO 가중치부터 train 2,400명으로 26 epoch 적응한다. LR은 epoch16·22 뒤 0.1배로 낮춘다. subset loss 감소만으로 확대하지 않으며, 약한 초기 detector를 근거로 VLM 우위를 주장하지 않는다. V100 추세와 milestone V400 선택, 사전 수렴 보완 및 조건부 seed 규칙을 계획에 고정했다.

### 3. 기존 SFT와 공정하게 연결할 평가

보존된 iter_012 `sft_eval.py`를 직접 읽었다. 기존 utility는 `0.5×양성 F1@0.3 + 0.25×Normal valid-empty + 0.25×NoOpacity/NotNormal valid-empty`다. detector checkpoint·threshold에도 같은 utility를 사용하며 F1@0.5를 tie-break와 별도 핵심 지표로 유지한다. 빈 출력이 많아지는 방식의 선택 효과는 양성 recall·FP·FROC operating point로 함께 드러낸다.

NMS=0.5와 표준 detections_per_img=100은 사전 고정한다. 낮은 score floor에서 후보를 보존하고 validation에서 threshold만 선택한다. 현재 GT는 최대 4개이므로 matching은 GT 부분집합을 상태로 하는 DP로 바꿀 수 있다. 계산량은 예측 수 P에 대해 선형인 O(P×G×2^G)이며, 작은 G를 확인한 이번 자료에 적합하다. 기존 cardinality 우선·총 IoU·동점 규칙을 유지하고 exhaustive 함수와 대조한다. 이는 detector 후보를 임의로 잘라 평가하는 조치가 아니다.

오류 상보성은 같은 GT에 대한 두 모델의 matching을 환자 단위로 묶어 집계한다. GT 기반 합집합은 FP 제거까지 가능한 실용 앙상블 성능이 아니다. SFT에는 detector confidence와 같은 score가 없으므로 임의 AP를 만들어 비교하지 않는다. detector의 validation에서 정한 FP budget별 operating point와 SFT의 고정 출력점을 함께 보고한다.

### 4. 재사용 자산의 추가 확인

현재 HEAD `8dad463392de9bb0e9fe7d93d64b9c374492de9b`의 status/diff는 비어 있다. 11개 반입 후보의 blob과 현재 bytes가 일치하고 iter_006 기반에서 충돌하지 않음을 확인했다. `sft_eval.py`는 현재 브랜치에는 없지만 `783d2d04671ae296f3dc0c700e575f8af8e021c9`에 보존돼 있다. 누락을 새 구현으로 대체하지 않고 이 파일을 선별 반입한다. 해당 파일의 metrics·parse 의존성은 현재 승인 모듈과 bytes가 동일하다.

iter_012의 seed17 설정은 train 2,400명, effective batch16, microbatch2, lr2e-4, rank16, 언어층 238개 대상, trainable parameter 29,802,496개다. 선택 checkpoint는 epoch05다. detector와 동일 annotation을 사용해도 학습량·사전학습·입력·정밀도가 같지는 않다. 기존 SFT의 완전 수렴 역시 증명되지 않았으므로 이번 결과의 범위를 보존된 조건에 한정한다.

### 5. 전략과 남은 불확실성

실제 detector 비교는 승인된 방향이며 다음 투자 판단에 필요한 빠진 근거다. 현재 grounding loss·continuation 추가 투자보다 정보 이득이 명확하다. 외부 전이는 VinDr 승인 통지 후 재검토하고, 언어·근거 연결 과제는 이번 bbox 비교로 대신 평가했다고 주장하지 않는다.

남은 불확실성은 detector 환경의 실제 CUDA 동작, 실측 처리량·메모리, RSNA 적응의 학습 추세다. 모두 구현 초반 gate와 단계별 규칙으로 확인할 수 있어 추가 사고 라운드는 필요하지 않다. 새 contribution이나 detector의 우위는 아직 확인되지 않았다.

### 대규모 GPU 필요 후보

다기관·다소견에서 vision encoder와 언어 모델을 공동 적응하고 위치·언어·근거 연결을 함께 평가하는 post-training은 장기 후보로 보존한다. 이번 비교는 그 필요성을 판단할 자료이며 해당 학습을 실행하는 계획은 아니다.

이전 사고 라운드 노트: agent/runs/iter_033/think/
