# 사고 라운드 1

## 새로 확인한 것

현재 1순위는 기존 checkpoint의 능력 전이 진단이다. 다만 이를 곧바로 구현할 근거는 아직 부족하다. 새로 확인한 선행 연구가 형식 유지와 공간 supervision을 이미 분리하고 있어, 단순한 grounding→QA 비교보다 구체적인 질문과 대조군이 필요하다. 다음 라운드는 실제 사용할 target·자료·비교군을 정하는 데 집중한다.

이번에는 문서·코드·저장 산출물을 읽고 문헌을 조회했다. 파일 변경, 모델 로딩, 실험 실행은 하지 않았다.

## 1. 유지하는 사실과 적용 경계

`agent/GOAL.md`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`, iter_009·012·014 원본 리뷰, iter_013·014 조사 기록과 계획을 확인했다. 사용자에게 전달된 INDEX·JOURNEY 및 운영 정책도 판단에 반영했다.

- iter_009의 양성 200명 중 공통 위치 불일치 134명은 정상 사용 조건에서 검증된 RSNA 한계다.
- iter_012 직접 SFT의 확인 양성 400명 F1@0.3은 세 seed에서 0.631–0.653이다. prior_set 대비 평균 차이는 +0.2156, 95% CI [0.1715, 0.2591]이다. 직접 적응의 유효성은 유지한다.
- iter_014 full 최종 S_loc은 C 0.50858, U 0.48150, G 0.48275다. G−C는 −0.02583, 95% CI [−0.05800, 0.00450]이며 G−U는 +0.00125다. 현재 G 설계의 추가 투자 중단을 유지한다.
- C의 V200 선택 부재와 fallback의 guardrail 탈락을 보존한다. 최종 C는 진단용으로 사전 고정할 수 있지만, 운영 기준으로 선택된 최적 checkpoint라고 표현하면 안 된다.
- 이 결과들은 영상 미사용, pooling 병목, anatomy 전이 필요성 또는 모든 기하 supervision의 실패를 증명하지 않는다.

iter_008 보완의 정상 사용 diagnostic 요구는 iter_009에서 충족됐다. `legacy/docs/MEDGEMMA_평가_전체정리.txt`의 중대 정정과 `agent/runs/iter_003/think/round_03.md`도 다시 확인했다. 좌표 출력 능력 자체가 없다는 주장은 철회 상태다. 공식 anatomy notebook의 긴 prompt와 legacy의 짧은 prompt는 동일하지 않다. 기존 revision·chat template·전처리·좌표·충분한 생성 길이 검증은 유지하고, 새 과제의 prompt·parser만 별도로 개발해야 한다.

기존 confirm 800명은 iter_013 계획에서 후속 개발 자료로 전환됐다. 과거 독립 확인의 역사적 유효성은 유지한다. `research/results/iter_010/manifests/reserve_patients.json`의 저장 목록은 opacity 496명, normal 5,562명, not_normal_no_opacity 2,050명이다. 이번에는 실제 영상 hash와 새 exclusion을 재검증하지 않았으며 reserve를 사용하지 않았다.

## 2. Strategy Check / 연구 방향 판단

중요한 능력은 의료 영상에서 학습한 위치 정보를 새로운 지시와 판단에 활용하는 것이다. 다만 localization 자체의 데이터 효율·일반화 개선도 유효한 연구 목표이므로 QA 전이를 필수 성공 조건으로 고정하지 않는다.

현재 확인된 것은 동일 RSNA target에서 직접 SFT가 실제 bbox 출력을 개선한다는 사실이다. 미확인 경쟁 설명은 다음과 같다.

1. 학습한 target과 출력 형식에 특화된 적응이다.
2. 위치 정보는 개선됐지만 새로운 질문이나 답변 형식으로 연결되지 않는다.
3. 다른 target·질문에도 활용되는 시각 능력이 개선됐다.
4. 전이처럼 보이는 결과가 답변 prior, 형식 준수 또는 bbox의 기계적 변환으로 설명된다.

세 전략의 잠정 비교:

- **기존 checkpoint 진단:** 새 학습 없이 경쟁 설명을 구분할 자산이 있다. 후속 내부 적응과 모듈형 구성의 선택을 바꿀 수 있어 정보 이득이 가장 높다. 다만 표면적인 prompt 변경만 평가하면 가치가 작다.
- **다른 연구 질문으로 전환:** 영상과 언어 단서가 충돌할 때 근거를 사용하는 능력은 중요하다. 그러나 아래 CORAL 등과 겹치므로 새로운 데이터·방법을 바로 만들기보다 정답이 보장되는 개입과 선행 방법의 범위를 확인해야 한다.
- **현재 grounding 방법 개선:** 잔여 위치 오류는 있지만 두 추가 loss 비교에서 충분한 이득이 확인되지 않았다. 새로운 원인·효율 근거 없이 다음 loss를 시도할 우선순위는 낮다. localization 전용 연구를 기각하는 판단은 아니다.

선택은 잠정적이다. 전이 진단에 유효한 정답과 식별력 있는 대조군을 확보하지 못하면 다른 질문을 우선한다. 같은 데이터에서 작은 점수 차이만 얻는 설계라면 새 학습 투자로 연결하지 않는다.

## 3. 새 선행 연구가 바꾼 설계 조건

기존 DIST²Loss·R-VLM·SPR 조사는 iter_013·014 기록을 재사용했다. 이번 검색은 후속 loss가 아니라 능력 전이와 모듈형 대안의 선행 범위를 확인하기 위한 것이다.

### Grounding과 QA의 관계는 이미 직접 연구되고 있다

[Why Does Grounding Hurt Medical VQA?, v2](https://arxiv.org/html/2604.27720v2)는 QA-only SFT, shuffled-box 형식 rehearsal, 실제 grounding 혼합을 비교한다. 또한 GT crop도 VQA를 악화시킬 수 있다고 보고한다. MedGemma checkpoint revision은 고정하지 않았고 공통 xyxy prompt를 사용하므로, 그 MedGemma 수치를 우리 1.5 정상 사용 결과와 동일시하지 않는다. grounding 평가 영상의 학습 중복도 따로 보고한다.

**설계에 대한 판단:** 형식과 공간 학습의 분리 자체는 신규 기여가 아니다. crop-only의 음성 결과로 근거 활용 불가능을 결론내릴 수도 없다. 원본 영상에 영역 정보를 추가하는 조건과 정답·split 검증이 필요하다. 이 논문 결과를 우리 모델의 전이 실패 증거로 사용하지 않는다.

### 영상 교환 민감성만으로 새 방향을 만들기도 어렵다

[Do Medical Vision Language Models Actually See?, v1](https://arxiv.org/html/2607.03647v1)는 blank·shuffle·image-absent·hard-negative 교환과 CORAL의 contrastive grounding 학습을 제시한다. Qwen2.5-VL-7B LoRA와 네 의료 VQA benchmark의 총 400개 paired 평가를 보고하며, benchmark overlap과 보조 지표의 불확실성을 명시한다.

**설계에 대한 판단:** image-swap과 contrastive loss의 조합 자체는 차별성이 부족하다. 답변이 변하는 것과 올바른 영상 근거에 따라 변하는 것을 구분해야 한다. 다른 영상으로 바꿔도 정답이 같은 경우를 실패로 처리해서는 안 된다. 이 방향을 택한다면 label·target이 보장되는 대조가 필요하다.

### 모듈형 대안은 원본 영상과 함께 평가해야 한다

[Visual Evidence Prompting, ACL 2025](https://aclanthology.org/2025.acl-long.205/)는 작은 시각 모델의 출력을 prompt의 근거로 제공하는 접근이다. detector 결과를 언어화하는 구성 자체가 이미 비교 대상이다. 원본 영상·영역·필요한 도구를 제한해 내부 grounding에 유리한 비교를 만들지 않는다. 이번에는 공식 초록을 확인했으며 의료 데이터 이식 세부 구현은 미확인이다.

[Localizing Before Answering, IJCAI 2025](https://www.ijcai.org/proceedings/2025/0853.pdf)도 grounded medical VQA의 가까운 선행이다. 공식 PDF 연결은 확인했지만 후속 본문 조회가 실패해 데이터의 target 대응·배포 조건까지 확인했다고 기록하지 않는다.

위 문헌은 조사 자료다. 새 진단의 긍정적 실험 근거는 아직 없으므로 사용자 논문 추천으로 제시하지 않는다. 현재 `agent/PAPERS.md`는 존재하지 않았다.

## 4. 실제 자산과 데이터가 허용하는 범위

다음 두 adapter 파일의 존재와 각각 119,369,709 bytes인 크기를 확인했다. tensor digest나 재로드 검사는 수행하지 않았다.

- B0: `research/results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`. `select/pick_seed17.json`의 selected_run과 일치한다.
- 추가 SFT C: `research/results/iter_014/full/C_lr2e-05/epoch_03/adapter.pt`.

미적응 base와 이 두 checkpoint는 추가 loss 학습 없이 적응 전후의 능력 범위를 비교할 수 있는 후보 자산이다. G/U를 자동으로 모두 평가할 필요는 없다.

데이터 확인:

- RSNA는 기존 환자 분할과 양성·두 음성 범주가 있다. 존재 판단과 좌표 출력의 연결은 검사할 수 있지만, bbox에서 만든 위치·개수 QA만으로 임상 reasoning을 입증할 수 없다.
- `research/results/iter_005/nih_manifest.json`에는 160명이 있다. `grounding_data/class_targets.py`는 해당 finding의 bbox가 없으면 unknown으로 처리한다. 따라서 이 자료에서 주석 없는 finding을 음성으로 바꾼 target-switch 평가를 만들면 안 된다. RSNA와 원천 데이터도 겹치므로 외부 기관 일반화로 부를 수 없다.
- 로컬 VinDr metadata는 10영상이며 복수 클래스 bbox를 포함한다. 의미가 다른 target 선택의 동작 확인 후보지만 충분한 독립 일반화 자료가 아니다.
- 로컬 SLAKE metadata는 10영상의 QA이며 `used_in_training` 아래 있다. 이 표본을 새로운 독립 전이 benchmark로 주장할 수 없다. 정답 영역 연결도 이번에 확인하지 않았다.

이 제약 때문에 '의미가 달라진 질문'과 '근거를 활용한 판단'의 정답을 어떻게 보장할지가 다음 라운드의 핵심이다. 두 축을 모두 큰 benchmark로 만드는 계획은 아직 정하지 않는다.

## 5. 코드 재사용과 새 브랜치의 조건

`git -C research status --short`, `git diff --stat`, `git ls-files`를 확인했다. tracked diff는 없고 `test_rsna_iter010_gpu.py`만 untracked 상태다. 이를 자동 반입·승인하지 않는다. 현재 HEAD는 `698c161f51ec098b1263ea8a5acf4d2870930e0b`다.

- 현재 `rsna_diag/generate.py`에는 부모 재사용 분기의 `lock_protocol` import 수정이 있다. iter_012의 NameError를 아직 미수정이라고 반복하지 않는다. 실제 사용할 부모 재사용 경로의 검증은 별개다.
- `generate.py`는 모델 revision, 값 보존 전처리, chat template, 1000→2000→4000 cap과 EOS 기록을 갖고 있다. 새로운 질문·답변 형식에서는 기존 bbox parser를 그대로 적용할 수 없다.
- `run_shards.py`는 worker/GPU 수 분리, 요청별 claim, 예상 요청 집합 대조와 시도별 completion을 갖고 있다. 전체 실행기 승인을 뜻하지는 않는다.
- `gen_compare.py`의 중복 ID 덮어쓰기와 `on_gpu.py`의 GPU 조회 실패 시 실행 가능 경로를 직접 확인했다. 재사용 시 필요한 수정 대상이다. worker당 2GiB 여유도 실제 실행 경로에서 합산해야 한다.
- `adapt_geo.py`의 truncated branch 수치 검사 실패는 남아 있다. 새 진단에서 이 학습 경로를 사용하지 않으면 그 해결을 선행조건으로 삼을 필요는 없다.

중요한 브랜치 조건: 최근 전체 재사용 승인 기반 후보인 iter_006의 `68117cf`에는 `rsna_diag/generate.py`가 없다. 새 접근법을 자동 기반에서 시작할 때 현재 작업 디렉터리의 RSNA 모듈이 자동으로 따라온다고 가정하면 안 된다. 구현 계획에서는 필요한 모듈과 전이 의존성을 확정하고 실제 40자리 출처 SHA의 개별 파일을 `reuse_assets`에 넣어야 한다. 이번 빈 배열은 반입 확정이 아니라 조사 단계의 미정 상태다.

## 6. 자원과 다음 조사에서 확정할 사항

iter_014 리뷰의 생성 pilot은 1 worker 13.20 req/min, GPU당 2 worker 22.44 req/min, 48/48 greedy token 일치, GPU peak 17,765MiB다. 이는 당시 prompt·checkpoint 조건의 실측이며 새 QA 또는 base의 긴 출력 처리량으로 그대로 환산하지 않는다.

후속 구현 계획은 두 GPU의 독립 checkpoint·요청 shard 배치를 기본 후보로 하고, 새 development 요청으로 GPU당 1·2 worker 또는 유망한 batch 확대를 짧게 비교한다. 실제 peak 합계와 worker당 최소 2GiB 여유, 긴 출력 지연, 오류, 결과 정합성으로 선택해야 한다. 현재는 요청 행렬과 표본 수가 미정이므로 wall-clock을 확정하지 않는다. 임의 시간 상한도 두지 않는다.

진단 결과별 잠정 의사결정은 다음과 같다.

- **양성:** 출력 형식과 단순 규칙을 넘어선 전이가 관찰되면 내부 적응의 가치가 있는 범위를 좁히고, 강한 직접 SFT·모듈형 대안·추가 데이터에서 비교할 방법 질문을 정한다.
- **음성:** 정상 사용·정답·형식 조건을 통제해도 학습한 과제에만 개선이 남으면, 내부 grounding의 범용 효과를 전제한 추가 loss 투자를 낮춘다. 모듈형 활용 또는 다른 연구 질문을 비교한다. localization 자체의 가치를 부정하지 않는다.
- **불확정:** 표본 부족, 불완전 주석, format failure, 도메인 차이 중 무엇이 판단을 막는지 구분한다. 추가 표본이나 형식 보정이 실제 선택을 바꿀 때만 확대하고, 정답 부재를 표본 확대로 해결하려 하지 않는다.

## 대규모 GPU 필요 후보

여러 의료 modality·질문·영역 supervision을 함께 사용하는 vision encoder와 언어 모델의 공동 post-training은 보존 후보다. 순차 단일 과제 적응과 다과제 학습의 전이를 비교할 수 있지만 데이터 정합성과 대규모 학습 비용이 필요하다. 현재 두 GPU에서는 기존 checkpoint 진단과 경량 적응·모듈형 대안을 먼저 검토한다.

## 한 라운드 더 조사하는 이유

추가 확인은 최종 목표를 막연히 더 찾기 위한 것이 아니다. 유효한 semantic target을 가진 자료의 확보 여부는 질문을 바꾸고, 형식 대조의 설계는 전이 해석을 바꾸며, 모듈형 baseline과 반입 의존성은 실행 범위·비용을 바꾼다. 이 네 항목을 해결한 뒤 최소 진단을 구현하거나 더 가치 있는 질문으로 전환한다.

## 다음에 파고들 질문
- RSNA·NIH·VinDr의 기존 자료와 접근 가능한 공식 grounded-VQA 자료 중, 대상이 실제로 달라지는 질문의 정답을 보장할 수 있는 최소 자료는 무엇인가? 불완전 주석·원천 환자 중복·사전학습 노출을 고려하면 어떤 전이 범위까지 해석할 수 있는가?
- base·B0·추가 SFT C의 차이를 좌표 출력, 의미가 다른 영역 선택, 근거 활용 판단으로 나눌 때 가장 식별력 있는 최소 요청 행렬은 무엇인가? 새로운 형식 실패와 실제 능력 차이를 어떤 개발용 보정·대조로 구분할 것인가?
- 새로 확인한 grounding/QA 연구와 CORAL을 기준으로, 진단 결과가 내부 적응·모듈형 대안·다른 질문 중 선택을 실제로 바꾸는 조건은 무엇인가? 예측 bbox+규칙과 원본 영상+예측 영역 VLM 비교로 충분한가, 같은 자료로 학습한 detector/encoder+head가 이번 단계부터 필요한가?
- 선정된 진단에 필요한 RSNA 모듈의 정확한 의존성·출처 SHA·필수 수정은 무엇인가? 표본 정밀도와 checkpoint별 출력 길이를 반영해 단계별 요청 수, 확대 기준, 두 GPU 배치와 예상 시간을 어떻게 고정할 것인가?
