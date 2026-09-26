# 사고 라운드 1

## 새로 확인한 것

직접 SFT 이후의 방법 개발은 가능하다. 다만 현재 결과만으로 작은 병변용 방법이나 공간 preference 학습을 바로 선택하기에는 두 가지 문제가 있다. checkpoint 선택과 위치 성능이 완전히 일치하지 않으며, 기존 small 지표도 개별 병변 크기를 측정하지 않는다. 새로 확인한 가까운 선행 연구는 단순 IoU 보상·공간 token·GT 기반 teacher의 차별성도 제한한다.

이번에는 문서·소스·저장 JSON을 읽고 기존 수치를 메모리에서 요약했다. 코드 수정, 파일 생성, 테스트, 모델 추론·학습은 하지 않았다.

## 1. 유지·보류·변경

- `agent/GOAL.md`, `agent/LIMITATIONS.md`, iter_009 원본 review.json, iter_012 review.md·claude_report.md, `agent/CODE_ASSETS.md`, 운영·자원·보고 정책을 확인했다. 현재 목표와 validated 주장 `lesion-grounding-generalization`을 유지한다.
- iter_009의 정상 사용 검증과 iter_012의 직접 적응 개선을 유지한다. 독립 확인 양성 400명에서 prior_set 대비 평균 F1@0.3 차이 +0.2156이라는 값은 직전 리뷰의 독립 재계산 근거를 인용하며, 이번 라운드에서 다시 계산하지 않았다.
- legacy 중대 정정과 `agent/runs/iter_003/think/round_03.md`를 읽었다. MedGemma 1.5에 grounding 경로 자체가 없다는 주장은 사용하지 않는다. 공식 사용법 sanity를 다시 반복할 필요도 없다. 새로운 학습·추론 경로를 바꾸면 해당 연결만 검증한다.
- iter_008 anatomy 전이는 보존 후보다. 자동 재개하지 않는다. pooling·decoder 병목도 확정하지 않는다.
- 기존 confirm의 잔여 오류가 이번 방법 선정에 활용됐으므로 후속 개발에서는 해당 800명을 개발 자료로 취급해야 한다. 과거 독립 확인의 역사적 유효성은 유지하되 새 방법의 독립 확인으로 다시 주장하지 않는다.

## 2. 학습 부족 외에 checkpoint 선택의 영향도 분리해야 한다

`research/results/iter_012/train/*/epoch_*/val_metrics.json`의 저장값을 읽었다. validation은 양성 200명과 두 음성 층 각 100명이다.

- LR 2e-4, seed17의 epoch4→5: F1@0.3 0.62117→0.64050, F1@0.5 0.35467→0.35500, utility 0.71058→0.72775, val_loss 0.61052→0.62888이다. F1@0.3은 올랐지만 더 엄격한 위치 지표는 거의 같았다.
- 같은 LR, seed29의 epoch4→5: F1@0.3 0.61983→0.59567, F1@0.5 0.36950→0.33250인데 utility는 0.68992→0.70283으로 올랐다. 양성 valid_empty도 31/200→40/200으로 늘었다.
- LR 1e-4, seed17도 epoch4→5의 F1@0.3 0.61683→0.59017, F1@0.5 0.37367→0.33767 감소와 utility 증가가 함께 나타났다.
- LR 2e-4, seed43은 epoch4→5에서 F1@0.3 0.59783→0.62817, F1@0.5 0.34300→0.36533으로 개선됐다. 따라서 마지막 epoch 선택을 일률적인 오류나 수렴 증거로 해석할 수 없다.

`rsna_diag/sft_eval.py`의 utility는 양성 F1@0.3에 0.5, 두 음성 층 valid_empty율에 각각 0.25를 준다. 원 계획은 이 기준을 올바르게 적용했다. 다만 새로운 방법이 위치 정밀도를 목표로 한다면 동일한 선택 규칙의 SFT와 비교하고, 음성 성능 제약 아래 checkpoint를 선택하는 단순 대안도 검토해야 한다. 기존 결과를 사후에 다시 선택해 과거 성공 기준을 바꾸지는 않는다.

`rsna_diag/train.py:lr_at`에서는 첫 5 epochs에 cosine LR이 거의 0까지 감소하고, 연장 구간은 peak의 0.1배에서 시작한다. 따라서 추가 학습의 부재와 특정 LR schedule의 영향도 구분해야 한다. 이전 규칙을 지켰다는 사실은 충분한 수렴의 증명이 아니며, 추가 학습이 반드시 개선한다는 증거도 아직 없다.

## 3. small 지표의 정확한 의미

`rsna_diag/sft_eval.py`에서 `gt_area_frac`는 환자의 모든 GT box union 면적을 계산한다. `area_edges`는 train 양성 환자의 이 값으로 삼분위 경계를 정하고, `by_gt_area_tertile`은 환자별 F1@0.3을 집계한다.

따라서 보고서의 small은 **GT 전체 union 면적이 작은 환자군**이다. 개별 작은 병변의 recall이나 작은 병변을 포함한 다중 병변 환자의 성능을 직접 측정하지 않는다. 현재 값은 틀린 metric이 아니라 해석 범위를 좁혀야 하는 metric이다.

후속 분석에서는 기존 지표를 유지하면서 개별 box 면적별 recall, GT 개수, 유효 빈 응답, 예측 개수, one-to-one matching 이후 위치 오차를 구분해야 한다. 작은 병변·단일 병변·총 병변 면적의 연관을 분리하기 전에는 작은 병변 전용 방법을 우선할 근거가 불충분하다. 이번 라운드는 저장 지표와 정의만 대조했으며 새 오류 분해 계산은 하지 않았다.

## 4. 선행 연구: 다시 읽은 이유와 새 후보

기존 `agent/runs/iter_010/think/round_01.md`와 plan.md의 조사를 먼저 읽었다. 당시에는 직접 SFT baseline이 없었고 지금은 생성 개선과 잔여 오류가 확인됐다. 이번 재조회 목적은 이미 알려진 논문의 존재 확인이 아니라, SFT 이후에 추가할 목적함수와 가까운 대조군을 정하는 것이다.

- **SPR:** 생성 답변을 semantic·localization 점수로 평가하고, 위치를 정제한 선호 답변과 낮은 점수 답변을 짝지어 LoRA DPO를 수행한다. 단순히 bbox가 좋은 답변을 선호시키는 것만으로는 새 contribution이 되기 어렵다. 집합 오류별 preference를 제안하더라도 일반적인 공간 preference보다 무엇을 추가하는지 명시해야 한다. [SPR 원문](https://arxiv.org/html/2510.14374v1)
- **GETok:** grid token과 offset·DELETE token, 단계적 위치 정제, box IoU 및 corner 거리 보상이 이미 제시돼 있다. 좌표 token 추가나 반복 수정 자체를 새 기여로 선택하지 않는다. [GETok 원문](https://arxiv.org/html/2512.10554v1)
- **새로 확인한 MedLoc-R1, CVPR 2026:** 의료 grounding에서 GRPO의 고정 IoU threshold가 만드는 희소 보상을 다루며, 학습 성능에 따라 threshold를 높인다. 논문은 단일 target box를 정식화하고 SFT·Raw-IoU·고정 threshold·단계별 schedule을 비교한다. 우리 과제의 무병변·복수 box 집합은 별도 설계가 필요하지만, 이 차이만으로 novelty가 자동 성립하지는 않는다. [CVPR 공식 기록](https://openaccess.thecvf.com/content/CVPR2026/html/Yang_MedLoc-R1_Performance-Aware_Curriculum_Reward_Scheduling_for_GRPO-Based_Medical_Visual_Grounding_CVPR_2026_paper.html), [원문 v1](https://arxiv.org/html/2603.28120v1)
- MedLoc-R1 원문 설정은 Qwen2.5-VL 계열, 4×H800 80GB, rollout group 8이다. 공식 저장소는 조회 시 README만 보이며 코드 공개 지연을 알린다. 저자 구현을 즉시 재사용할 수 있다고 계획하면 안 된다. 원문 기반 축소 대조와 원논문 재현을 구분해야 한다. [공식 저장소](https://github.com/MembrAI/MedLoc-R1)
- **새로 확인한 IoU-PD:** 원영상 student와 GT box가 표시된 영상·힌트를 받는 frozen teacher를 사용하고, SFT에 기하학·teacher 신뢰도를 반영한 token distillation을 더한다. 따라서 GT 표시 teacher나 좌표 token 가중치만으로는 차별성이 부족하다. 원문 주설정은 Qwen3-VL-4B, 300K 예제, 3 epochs, full-parameter tuning이다. MedGemma LoRA와 동일 비용의 결과로 간주하지 않는다. [IoU-PD 원문 v1](https://arxiv.org/html/2607.15732v1)

**설계에 주는 의미:** 현재 잠정 1순위는 영상 조건부 집합 grounding을 이어가며 충분한 SFT와 집합 오류별 학습을 비교하는 방향이다. 그러나 무병변·누락·추가 box·위치 오차를 단일 scalar reward로 합치는 것보다 명확한 이점이 있는지 아직 확인하지 못했다. 다음 라운드는 이 차이를 수식과 ablation으로 명시할 수 있는지에 집중한다. 차이가 없다면 새 이름을 붙이지 않고 강한 baseline 및 가까운 방법 대조를 먼저 수행한다.

## 5. 독립 확인 자원과 두 번째 데이터셋

`research/results/iter_010/manifests/reserve_patients.json`의 목록 크기는 opacity 496명, Normal 5,562명, NoOpacity/NotNormal 2,050명이다. `data_audit/audit_summary.json`의 reserve_sizes와 일치한다. 이는 저장 manifest의 수량이며 이번에 실제 영상 hash·새 exclusion을 재검증한 수량은 아니다. 양성 reserve를 개발에 소모하지 말고 후속 확인 규모와 정밀도를 먼저 설계해야 한다.

Kvasir-SEG는 이전 계획에 공식 배포·중복·patient/video 정보 확인 대상으로 들어 있지만, 확인한 iter_010 보고서에는 공식 저장소 조회가 기록돼 있을 뿐 다운로드·분할 gate 완료 근거는 없다. 실제 사용 가능성이 확정됐다고 가정하지 않는다. RSNA와 다른 modality에서 같은 학습법의 효과를 보이는 것과 외부 흉부 기관으로의 zero-shot 전이는 구분한다.

## 6. 코드 재사용과 필요한 수정

`research/`에서 git status, diff, ls-files와 HEAD를 확인했다. HEAD는 `783d2d04671ae296f3dc0c700e575f8af8e021c9`이고 tracked diff는 없다. 미추적 `test_rsna_iter010_gpu.py`는 그대로 존재하며 승인·반입 대상으로 취급하지 않는다.

현재 브랜치에 geometry.py, parse.py, metrics.py, sft_eval.py, lora.py와 학습·생성·평가 실행기가 모두 있다. 이번 잠정 방향은 같은 브랜치를 이어가므로 외부 파일 반입을 요청할 이유가 없다. `reuse_assets=[]`는 전체 스냅샷 승인이라는 뜻이 아니다.

직전 리뷰와 실제 소스에서 다음을 확인했다.

- generate.py의 `lock_protocol` import는 main의 지역 범위에 있고 run_worker의 부모 재사용 분기는 이를 참조한다. 해당 경로를 쓰기 전에 NameError를 수정하고 부모 입력·config·protocol 검증을 실제 검사해야 한다.
- pipeline.py의 gen_check는 기존 decision을 그대로 반환한다. 새 decision 계산도 출력 일치 수치를 기록할 뿐 worker 채택의 필수 조건으로 강제하지 않는다.
- pipeline.py는 기존 final 결과를 파일 존재만으로 건너뛴다. 새 실행에서는 요청 완전성·선택 근거·protocol·adapter 연결을 재검증해야 한다.
- 필요한 iter_011 fixture를 최신 provenance 형식으로 갱신하고, GPU 검사기의 고정 0/1 매핑을 상속된 허용 집합에 맞춰야 한다. 부모 trajectory 이관을 사용하지 않으면 무관한 migration 확장은 미룰 수 있다.

이 결함들은 새 실행의 필수 수정 사항이며, 이미 독립 재계산으로 확인된 iter_012 결과를 무효화하거나 재실행할 이유는 아니다.

## 7. 자원 판단

직전 보고서의 실측은 학습 GPU당 약 12.2GB, 두 병렬 trajectory의 학습·validation 묶음 약 5.3시간이다. SFT 확인 생성은 800요청당 약 15분으로 보고됐다. 미적응 모델은 긴 출력 때문에 훨씬 느리므로 base 처리량을 SFT 비용 추정에 그대로 쓰지 않는다.

새 목적함수는 추가 forward·reference·rollout 수가 달라 실제 메모리를 다시 측정해야 한다. 두 GPU에 독립 비교 조건을 배정하고, 추론은 기존 GPU당 2 worker 실측을 출발점으로 batch 확대 또는 worker 구성 비교를 수행한다. 새 출력 경로의 정합성·전체 peak·worker당 2GB 여유가 필수다. 임의 시간 상한은 두지 않는다. 구체적인 wall-clock과 단계별 규모는 목적함수·평가 일정 확정 후 산출한다.

## 대규모 GPU 필요 후보

GETok 전체 SFT/RL, MedLoc-R1 원논문 설정의 4×H800 GRPO, IoU-PD의 300K·full-parameter teacher/student 학습을 별도 후보로 보존한다. 현재 두 RTX 3090에서 LoRA와 순차 reference 계산으로 축소할 가능성은 미검증이며, 원문 자원 규모를 모든 경량 변형의 불가능 근거로 사용하지 않는다.

## 남은 판단

추가 조사는 후보 선택을 실제로 바꿀 수 있다. checkpoint 선택만으로 위치 성능이 상당 부분 달라지면 그 baseline을 먼저 강화해야 한다. 개별 병변 크기별 오류가 확인되지 않으면 small-lesion 방향의 우선순위를 낮춘다. 집합 학습이 SPR·MedLoc-R1과 구별되지 않으면 새 방법 구현을 확정하지 않는다. 다음 라운드에서는 이 세 갈림길과 외부 평가 가능성을 해결해 구현 가능한 후보 하나로 좁힌다.

## 다음에 파고들 질문
- 기존 validation 원시 출력에서 개별 GT box 면적·GT 개수·환자 union 면적을 분리하면, 미검출과 위치 오차 중 어느 문제가 주로 남는가? checkpoint별 양성 성능과 두 음성 층 성능의 관계는 방법 선택을 어떻게 바꾸는가?
- SPR의 sequence-level preference와 MedLoc-R1의 IoU curriculum을 넘어, 무병변·누락·추가 box·위치 오차를 다루는 집합 학습에 검증 가능한 차이가 있는가? 목적함수와 필수 ablation을 구체적으로 정의할 수 있는가?
- 현재 5-epoch SFT에서 출발하는 추가 학습 baseline의 LR schedule·학습량·checkpoint 선택 기준을 어떻게 고정해야 하는가? 동일 시작점·노출량·선택 예산의 1-seed 탐색과 확대 기준은 무엇인가?
- reserve 양성 496명을 보존하면서 필요한 독립 확인 정밀도를 확보할 수 있는가? Kvasir-SEG 등 두 번째 데이터셋의 실제 파일·주석·중복·분할 근거를 확인해 이번 계획의 조건부 확대 단계에 포함할 수 있는가?
