# 사고 라운드 1

## 핵심

방법 개발의 진입 근거는 충분하다. 다만 새 방법을 고르기 전에 확인해야 할 차별성 문제가 구체적으로 드러났다. 기존 출력에는 위치·크기 오류와 함께 prompt별 box 개수 편향이 있다. 공간 토큰, 별도 box decoder, 의료 영상 hard-negative 학습도 이미 선행 연구에 존재한다. 이를 대조하지 않고 구현을 시작하면 기존 방법의 축소 재현에 머물 수 있다.

이번에는 문서·코드·결과·대표 overlay를 읽고, 저장된 JSON의 개수만 메모리에서 집계했다. 파일 생성·수정, 테스트, 모델 추론·학습은 하지 않았다.

## 1. 유지할 판단과 사용자 보완의 반영

- `agent/GOAL.md`, `agent/LIMITATIONS.md`, `agent/runs/iter_009/review.md`와 `review.json`, 구현 보고서, 코드 재사용 기록을 확인했다. 연구 목표는 유지한다.
- 정상 사용 조건의 RSNA 공통 위치 불일치 134/200명, 67.0%라는 직전 검증을 유지한다. 이번 라운드에서 이 주지표를 다시 독립 재계산한 것은 아니다.
- `legacy/docs/MEDGEMMA_평가_전체정리.txt`의 중대 정정을 읽었다. MedGemma 1.5의 grounding 경로 자체가 없다는 주장은 다시 사용하지 않는다.
- iter_008 anatomy 전이는 보존 후보로 남긴다. 정상 사용 진단을 우선하라는 일회성 보완은 iter_009에서 충족했으므로 같은 sanity 실험을 반복할 이유는 없다. 새 학습·입력 경로의 정합성 검사는 별도로 필요하다.
- 이번에 기존 평가 300명의 오류 분포를 추가로 검토했으므로 후속 연구에서는 개발 자료다. 새로운 확인 집단의 결과를 보고 방법·조건을 고르는 일을 막아야 한다.

## 2. 새로 확인한 오류 구조

출처는 `research/results/iter_009/eval/diagnostics.json`, `eval/eval/positive_case_table.json`, `manifests/gt_manifest.json`이다. 개수는 저장 결과를 읽어 직접 집계했다.

- 양성 평가 200명의 GT box 개수는 1개 110명, 2개 87명, 3개 3명이다. 따라서 90/200명에는 여러 병변 box가 있다.
- 공식 긴 prompt의 예측은 200명 모두 box 1개다. 간결 prompt의 평가용 예측 개수는 0개 20명, 2개 173명, 3개 5명, 8개 1명, 14개 1명이다. 0개에는 빈 답과 형식·잘림 실패가 함께 포함되므로 모두 미검출로 해석하지 않는다.
- 단일 GT 환자 110명에서도 유효한 비어 있지 않은 예측의 모든 IoU가 0.3 미만인 경우가 공식 prompt 96명, 간결 prompt 92명이다. 따라서 다중 병변 개수 불일치만으로 위치 오류를 설명할 수 없다.
- 공식 prompt의 평균 예측 union 면적은 전체 영상의 0.220567, 평균 GT union 면적은 0.089005다. 두 평균의 비는 약 2.48이며, 환자별 면적비의 평균과는 다르다.
- 공식 prompt의 평균 max-IoU는 원래 규약 0.1840, x/y 교환 0.1450이다. 간결 prompt는 원래 규약 0.1546, 교환 0.1961이다. 이는 간결 prompt에서 좌표 혼동이 부분적으로 기여할 가능성을 남기지만, parser를 사후 변경해 주평가를 구제할 근거는 아니다.
- `eval/eval/cases/common_error_ind_00000103.png`를 직접 보았다. 공식 예측은 GT보다 넓고, 간결 예측은 GT에서 중앙 방향으로 벗어난다. 한 사례의 overlay 확인이며 임상 재판독이나 전체 분포의 증명은 아니다.

보존된 공식 notebook의 prompt는 JSON 목록을 허용한다. 따라서 공식 출력이 항상 한 box였다는 사실을 출력 schema의 강제 제한으로 설명할 수 없다. 반대로 prompt 문구 때문에 개수 편향이 생겼다는 원인도 아직 확정할 수 없다.

**설계에 주는 의미:** 단일 box의 크기 보정만으로 끝내지 말고, 병변 개수·미검출·추가 box를 포함하는 집합 평가가 필요하다. 영상 비의존 보정과 직접 SFT를 먼저 강하게 만들어야 새 방법의 이득을 해석할 수 있다.

## 3. 가까운 선행 방법과 후보 순위에 미치는 영향

1. **직접 경량 적응은 필수 baseline이다.** 기존 iter_008에서 확인한 CURE를 이번에는 학습 설정 확인 목적으로 다시 읽었다. MedGemma-4B-IT에 rank 16 LoRA와 4-bit 학습을 사용한다. 기준 모델은 MedGemma 1.5가 아니므로 가중치를 그대로 사용하는 공정한 baseline과는 구분해야 한다. 단순 anatomy curriculum이나 LoRA 적용 자체를 새 기여로 주장할 수 없다. [CURE 원문](https://arxiv.org/html/2601.15408v1)

2. **공간 토큰과 반복 좌표 보정은 이미 강한 선행 방향이다.** GETok은 2D grid token과 offset token으로 위치를 표현하고 반복 보정을 수행한다. 본문은 Qwen2.5-VL-7B, LoRA rank 64 및 8×A800 실행을 보고한다. MedGemma에 공간 토큰을 추가하는 것만으로는 차별성이 부족하다. 축소 재현의 가능성과 전체 원논문 재현 비용은 구별해야 한다. [GETok 원문](https://arxiv.org/html/2512.10554v1)

3. **별도 box decoder도 새 발상이 아니다.** uMedGround의 공식 저장소는 BOX token과 vision encoder-decoder를 연결하고 uncertainty-aware grounding을 사용한다고 설명한다. frozen feature에 head를 붙이는 접근은 이 계열과 비교해야 하며, 단순 head 개선을 MedGemma 생성 개선으로 바꾸어 표현할 수 없다. [uMedGround 공식 저장소](https://github.com/Cocofeat/uMedGround)

4. **의료 영상 hard-negative 학습도 선행 연구가 있다.** CORAL은 hard-negative image swap에 대한 답변 불변성을 벌점화하는 contrastive grounding objective와 LoRA를 사용한다. 평가 대상은 의료 VQA이며 bbox 집합 생성과는 다르지만, 영상 의존성을 높인다는 동기 자체는 이미 제시돼 있다. 논문이 명시한 train/eval overlap 등의 제한도 함께 읽어야 한다. [CORAL 논문](https://arxiv.org/abs/2607.03647)

5. **Counterfactual preference 계열의 추가 대조가 필요하다.** CoMedPO는 저자 연구실의 논문 목록에서 확인했다. 연결된 공식 GitHub 저장소는 현재 비어 있어 구현을 재사용할 수 있다고 판단하지 않았다. 다음 라운드에서는 저자 원문을 찾아 목적함수와 비교 범위를 확인해야 한다. 검색된 비공식 요약의 기전 설명을 검증된 사실로 채택하지 않았다. [저자 논문 목록](https://www.ece.ucdavis.edu/~chuah/rubinet/publications/bydate.html), [공식 저장소](https://github.com/zxgapollo/CoMedPO)

6. **대규모 의료 grounding 적응도 비교 배경에 포함한다.** LocAnyMed는 약 200K 의료 grounding instruction과 단일·복수 box 및 no-target 출력을 다룬다. 기술보고서 단계이며, 직접 domain SFT만으로도 강한 성능을 얻을 수 있다는 비교 필요성을 보여준다. 수치를 우리 RSNA 점수와 직접 비교하지 않는다. [LocAnyMed 원문](https://arxiv.org/abs/2608.03322)

7. **attention을 곧바로 정답 근거로 쓰는 방법은 후순위다.** Attention Without Grounding은 의료 VLM의 attention·saliency와 영상 의존성·주석 일치를 구분해 평가한다. 이는 우리 생성 bbox의 원인 증명이 아니지만, attention map을 그대로 pseudo-GT로 사용하는 설계에는 별도 검증이 필요하다는 근거다. [원문 v2](https://arxiv.org/abs/2607.18577v2)

현재 1순위는 직접 병변 SFT 위에서 영상별 위치·크기·개수 구별을 학습하는 후보군이다. 단순 좌표 jitter나 image-swap loss를 추가하는 수준을 넘는 차별성이 있는지는 아직 미확인이다. 그 차이를 찾지 못하면 새 방법 이름을 붙이지 않고 직접 적응 baseline의 잔여 오류부터 확인하는 것으로 범위를 좁혀야 한다.

## 4. 데이터와 독립 확인의 실행 가능성

- `data_audit/audit_summary.json`의 기존 환자 제외 후 pool은 양성 2,536명, Normal 6,532명, NoOpacity/NotNormal 3,020명이다. 여기에는 iter_009에서 선택한 380명이 포함되므로 모두 미사용 환자라고 표현하면 안 된다. 알려진 기존 380명을 추가 제외하면 양성은 산술상 2,296명이 남지만, 신규 split 및 추가 중복 검사는 아직 수행하지 않았다.
- 이 pool은 다중 category 환자를 양성 우선으로 배정한다. 원래 모집단의 prevalence나 자연스러운 음성 집단으로 해석하면 안 된다.
- 공식 RSNA ZIP 3,978,753,654 bytes와 annotation·mapping·provenance 파일이 이미 로컬에 있다. 대규모 재다운로드가 후속 학습의 필수 전제는 아니다.
- RSNA와 NIH는 원천 자료가 겹친다. 새 NIH 환자를 추가하는 것만으로 외부 데이터셋 일반화를 증명할 수 없다.
- VinDr 접근·정합성 문제는 `agent/runs/iter_009/think/round_02.md`에서 이미 확인한 사실이다. 이번에는 새 접근 권한이 생겼다고 가정하지 않았다.
- 외부 modality 후보로 Kvasir-SEG 공식 저자 저장소를 확인했다. 1,000개 polyp 영상, mask, bbox JSON과 Data-split 디렉터리가 있다. 원본 polyp class에서 13개 영상을 교체했다고 명시한다. 기존 `legacy/eval_samples/not_in_training/kvasir_vqa`와의 중복 및 patient/video 단위 분리 가능성은 미확인이다. 공식 배포 웹페이지 조회는 실패했고 실제 다운로드 가능성도 확인하지 않았다. [Kvasir-SEG 공식 저장소](https://github.com/DebeshJha/Kvasir-SEG)

Kvasir를 쓰면 별도 modality에서 같은 학습 방법의 효과를 검증하는 것이다. RSNA 학습 모델의 외부 흉부 기관 일반화와 동일한 주장으로 묶을 수 없다. 환자 식별이 불가능하면 그 평가 독립성의 한계를 명시해야 한다.

## 5. 코드 재사용 확인

`research/`에서 `git status --short`, `git diff`, `git ls-files`를 확인했다. 연구 저장소의 변경 출력은 없으며 HEAD는 `39aa49a6fa5943ca0d3e0327a7874e68a2c878cb`다. 새 브랜치 기반 후보인 승인 iter_006의 전체 SHA는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`로 확인했다.

- 승인된 최소 평가 모듈은 `rsna_diag/__init__.py`, `geometry.py`, `parse.py`, `metrics.py`다. 적용 범위는 기존 uint8 입력과 정규화 bbox 규약이다.
- `evaluate.py`의 `load_gen`은 중복 요청을 덮어쓴다. 신규 평가에는 요청 집합·중복·입력/config/protocol 연결 검사가 필요하다.
- `run_shards.py`는 worker 수를 GPU 수 이하로 제한하고 기존 claim을 삭제한다. 후속 실행에는 worker/GPU 분리, 실행 lock, 안전한 claim 회수와 worker별 출력이 필요하다.
- 완료 환자의 입력 hash 검증 누락, 새 DICOM 표시 태그 gate, mapping/ZIP 충돌 중단 조건은 직전 리뷰의 필수 수정 사항으로 유지한다.
- 새 브랜치를 iter_006에서 만들면 rsna_diag 파일은 그 기반에 없다. 구현 계획을 확정할 때 필요한 파일과 의존 파일을 iter_009 전체 SHA로 `reuse_assets`에 명시해야 한다. 현재 빈 배열은 반입 승인이 아니라 방법·의존 범위를 아직 확정하지 않았다는 뜻이다.
- 현재 계획용 Python의 package metadata 조회에는 torch·transformers·peft 등이 없었다. 실제 Claude 학습 환경의 미설치 증거로 일반화하지 않는다. 학습 계획 확정 전 실제 conda 경로와 설치된 버전을 읽기 전용으로 확인할 필요가 있다.

## 6. 자원 판단

직전 보고서의 실측은 추론 프로세스당 torch peak 8.17–8.23 GB, nvidia-smi 최대 9,039 MiB이며, 평가 900요청은 두 worker에서 11,095초였다. 이는 학습 메모리 추정치가 아니다.

후속 계획에는 development에서 2개 GPU×1 worker와 2개 GPU×2 worker 또는 batch 확대 중 유망한 구성을 비교하도록 넣는다. worker마다 최소 2GB 여유를 확보하고 긴 출력의 KV cache까지 포함한 전체 peak, 처리량, 정합성으로 선택한다. 학습은 별도 forward/backward 실측 후 두 GPU에 독립 seed·조건을 배정한다. 본실험 규모와 시간은 방법 및 신규 split을 확정한 다음 처리량으로 산출하며 임의 시간 상한은 두지 않는다.

## 대규모 GPU 필요 후보

- GETok 전체 SFT/RL 재현: 원문은 8×A800을 사용한다. 현재 장비에서 수행하는 축소 대조와 구별해 보존한다.
- RadGrounder 규모의 다중 과제 학습: CT/MRI grounding 자료와 PaliGemma 2를 사용하며 단일 H100에서 약 2.5일 학습을 보고한다. 데이터 규모·학습 설정을 그대로 재현하는 후보는 별도 자원 항목으로 남긴다. [RadGrounder 원문](https://arxiv.org/html/2606.20477v1)
- 대규모 의료 instruction으로 vision encoder까지 공동 적응하는 방향: 현재 경량 방법의 실패만으로 필요성을 확정하지 않고 후속 후보로 유지한다.

## 다음 조사에서 결정할 것

추가 조사는 단순 문헌 수집이 아니다. 가까운 선행 목적함수, 강한 단순 baseline으로 남는 오류, 독립 평가 자료를 확인해 다음 구현을 직접 SFT 중심으로 할지, 공간 대조 학습까지 포함할지 결정한다. 위 정보는 방법 선택과 실험 범위를 실제로 바꿀 수 있으므로 이번 라운드는 think_more로 마친다.

## 다음에 파고들 질문
- CORAL·CoMedPO·Spatial Preference Rewarding의 원문 목적함수와 대조할 때, 영상별 bbox 집합의 위치·크기·개수를 학습하는 후보에 어떤 명확한 차이가 남는가? 차이가 없다면 직접 병변 SFT와 잔여 오류 확인으로 이번 구현 범위를 좁혀야 하는가?
- 저장된 development 출력에서 단일·복수 GT별 위치와 크기 오류를 분리하면, 단순 좌표 보정·개수 prior·prompt 보완으로 설명 가능한 범위는 어디까지인가? 새 방법이 반드시 넘어야 할 단순 baseline을 어떻게 고정할 것인가?
- RSNA의 미사용 환자를 train/validation/확인 집단으로 얼마나 배정하고, Kvasir-SEG 또는 접근 가능한 다른 외부 자료에서 어떤 분할·중복 검사를 적용할 수 있는가? 같은 방법의 다중 데이터셋 검증과 zero-shot 전이를 어떻게 구별할 것인가?
- 실제 medgemma 환경에 있는 학습 라이브러리와 공식 fine-tuning 예제를 기준으로, MedGemma 1.5의 assistant-only loss·LoRA 대상 모듈·정밀도·checkpoint 경로를 어떻게 고정할 것인가? 필요한 재사용 파일과 필수 수정 범위는 무엇인가?
