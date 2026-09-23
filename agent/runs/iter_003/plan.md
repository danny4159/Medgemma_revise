# 이전 기록에서 가져올 것

- 이전 점수 요약 목표는 `f213214`에서 완료됐다. 새 접근법의 첫 시도이며, 이전 접근법의 시도 횟수를 이어받지 않는다.
- `research/summarize_scores.py`의 분모 보존 원칙, legacy의 JSONL 출력과 multi-image 입력 구성, 분류 감사의 case별 평가 방식을 재사용한다. 새 브랜치에 기존 파일이 없으면 orchestrator가 관리하는 이력을 참고하되 직접 브랜치를 변경하지 않는다.
- legacy에서 배운 핵심은 모델 버전·prompt·정답 정의·평가 단위가 바뀌면 기존 수치를 직접 비교할 수 없다는 것이다. 낮은 bbox 점수, pooled AUC, MRI 안내문이 달랐던 3D 결과를 새로운 연구 가설의 확정 근거로 쓰지 않는다.
- 모든 산출물은 `research/`에 작성한다. `legacy/`와 `hf_cache/`는 읽기 전용으로 유지한다. 이번 계획 단계에서는 파일 변경이나 실험을 수행하지 않았다.

# Current Understanding

MedGemma 1.5의 병변 근거를 유지한 presentation 변화에 대한 불안정성은 이미 보고됐다. 이번 연구의 가치는 이를 다시 발견하는 데 있지 않고, 정확도를 유지하면서 해결할 수 있는 기전을 찾는 데 있다. [Stable Evidence, Unstable Decisions](https://aclanthology.org/2026.findings-acl.1303/)

우선순위는 3D 근거 보존 context 안정화다. MedPruner의 중복 제거·token 집계와 비교할 필요가 있지만, 먼저 점수 수준에서 context 효과를 분리할 수 있는지 확인한다. 전체 MedPruner 재현과 대규모 학습을 이번 pilot에 포함하지 않는다. [MedPruner v2](https://arxiv.org/html/2603.11625v2)

공개 MRI-GBM-MET는 유망한 확장 후보지만 archive 내부 구조와 사용 조건이 미확인이다. 이번에는 로컬 BraTS 3 case의 T1CE/T2를 사용한다. 이는 3개 독립 case의 기전 pilot이며, 임상 진단 benchmark나 다중 데이터셋 증명이 아니다.

# Hypothesis

**H1:** 병변 근거 packet의 픽셀을 고정해도 context의 내용·중복·위치에 따라 답변 log-odds가 바뀌며, 그 변화 중 일부는 같은 context에 놓인 별도 reference packet에서도 관찰되는 공통 성분이다.

**H2:** 이 공통 성분을 paired score로 상쇄하면, 단순 concatenation보다 근거 packet 단독 점수에 가까워지면서 annotation 기반 구분 능력을 유지할 수 있다.

질문 q에 대한 점수를 `m(X)=log P(Yes|X,q)−log P(No|X,q)`로 정의한다. 근거 packet S, 별도 reference R, context C에 대해 다음 고정식만 검사한다.

`m_corrected(S,C)=m(S,C)−m(R,C)+m(R)`

계수는 1로 고정하고 결과를 보고 조정하지 않는다. R은 S 및 context와 겹치지 않는 annotation-empty slice packet이다. 이는 GT 기반 reference를 사용하는 **oracle probe**다. 배포 가능한 방법이나 신규 contribution으로 주장하지 않는다. 각 presentation의 보정값을 따로 계산하며, 여러 presentation에 하나의 답변을 복사하지 않는다.

# Proposed Experiment

## 1. 데이터와 packet 구성

- case: `BraTS-GLI-00000-000`, `BraTS-GLI-00002-000`, `BraTS-GLI-00005-000`.
- sequence: `t1c`, `t2w`. 총 6 case-sequence지만 독립 case는 3개다.
- 영상·segmentation의 shape와 affine을 검증하고 동일하게 canonical orientation으로 변환한다. 영상과 mask의 보간 없는 축 변환을 우선하며, 불일치를 임의 resampling으로 숨기지 않는다.
- intensity는 case-sequence별 비영점 voxel의 1st/99th percentile로 한 번 정하고 모든 slice·조건에 동일하게 적용한다. RGB 복제와 resize 설정도 고정한다.
- 양성 packet E는 `seg>0` 면적이 큰 서로 다른 두 slice로 구성한다. 이는 전체 종양 관련 annotation의 합집합이며 enhancing tumor로 부르지 않는다.
- 음성 proxy packet N, reference R, context A/B는 각각 서로 다른 annotation-empty slice 두 장으로 구성한다. E/N/R/A/B 사이에 source slice 중복을 허용하지 않는다.
- empty 후보는 annotation이 있는 z 범위에서 최소 5 slice 떨어지고, 비영점 영상 면적이 해당 volume 최대의 25% 이상인 slice로 제한한다. 가능한 범위에서 E와 영상 면적 차이가 작은 후보를 선택하며 동률은 z-index로 정한다. 선택 규칙·seed·모든 제외 이유를 추론 전에 저장한다.
- 적격 slice가 부족하면 기준을 조용히 완화하지 않는다. 해당 case-sequence를 제외하고, 3 case 모두에서 최소 한 sequence를 구성하지 못하면 GPU 기전 실험을 중단한다.
- montage와 mask overlay는 선택·정렬 오류 확인용이다. 임상적 음성 판정이나 radiologist 검증을 대체하지 않는다.

## 2. 고정된 질문과 presentation

모든 입력에 동일하게 MRI sequence를 명시하고, 제공된 영상에서 tumor-associated abnormality가 보이는지 Yes/No로 묻는다. 파일명·GT·packet 역할·case label은 prompt에 넣지 않는다. 비연속·중복 slice를 contiguous volume이라고 설명하지 않는다.

S를 E, N, R로 각각 바꾸어 다음 7개 조건을 구성한다.

| 조건 | 입력 | 비교 목적 |
|---|---|---|
| P0 | S | packet 단독 기준 |
| P1 | A + S | 기본 context |
| P2 | B + S | P1과 길이·packet 위치가 같은 context 교체 |
| P3 | S + A | P1과 영상 multiset이 같은 위치·순서 변경 |
| P4 | A + A + S | 반복 context 추가 |
| P5 | A + B + S | P4와 같은 길이에서 중복·다양성 비교 |
| P6 | A + B + A + B + S | 동일 context 반복량 증가 |

E/N의 픽셀은 모든 조건에서 같아야 한다. P1 대 P4, P5 대 P6는 길이와 반복량이 함께 달라지므로 순수 길이 효과로 해석하지 않는다. 최대 영상 수는 10장이다.

## 3. 비교 방법

1. 원본 concatenation 점수와 결정.
2. 입력에 포함된 slice의 독립 점수 mean 및 max. 동일 slice 재등장은 기본적으로 multiplicity를 반영하고, unique-slice 집계도 추가 GPU 없이 보조 분석한다.
3. P1/P3 점수 평균을 사용하는 2-order ensemble. 이 baseline의 해석은 해당 두 조건으로 제한한다.
4. P1/P3 결정이 일치할 때만 답하는 consistency 기권 baseline. coverage와 selective error를 함께 보고한다.
5. MedPruner 본문의 IAF만 구현한 slice-filtering ablation: [0,1] RGB에서 현재 anchor와의 mean L1이 0.05를 초과하면 유지한다. 유지된 E slice 수와 token 수를 기록한다. 이를 전체 MedPruner 재현이라고 부르지 않는다.
6. 위 수식의 paired 보정. P0 점수와 각 조건의 R 점수를 재사용한다.
7. oracle packet-only 결과. context를 제거했을 때의 기준이며, 안정성이 구조적으로 높다는 사실 자체를 방법의 성과로 세지 않는다.

보정은 단순 감산 probe이며, contrastive decoding 계열과의 차별성이 확정된 방법은 아니다. 이 pilot이 통과해야 mask-free reference 선택과 더 넓은 선행 연구 비교에 투자한다.

## 4. 입력 scoring과 실행 예산

- 정확히 `google/medgemma-1.5-4b-it`의 로컬 snapshot을 bf16으로 사용한다. model/processor revision, transformers 버전, image processor 설정, tensor shape, image token 수를 기록한다.
- 공식 모델 카드의 `apply_chat_template(..., add_generation_prompt=True)`를 따른다. MRI 전처리는 연구용으로 명시한다.
- Yes/No 각각의 **전체 continuation token**에 대한 log probability를 계산한다. assistant prefix 경계, tokenizer의 공백 처리, candidate 길이, token 중복·충돌을 검사한다. 첫 token만 임의로 선택하지 않는다.
- 12개 E/N 단독 입력에서 greedy 생성도 최대 8 token으로 확인한다. 비정형 응답·잘림·scoring 결정과의 불일치를 모두 보고하며 임의 label로 바꾸지 않는다. 주평가는 제한된 답변 likelihood 평가라는 점을 명시한다.
- 최대 요청 수는 기본 126개, 독립 slice 최대 60개, E/N의 P1–P6 IAF 최대 72개로 총 258개 scoring 입력이다. 각 입력의 Yes/No scoring forward 수는 별도로 센다. 생성 확인 12개가 추가된다.
- 실행 직전 `nvidia-smi`로 허용된 GPU의 여유 메모리를 확인한다. 기본은 여유가 가장 큰 GPU 한 장에서 한 프로세스다. 실제 peak와 2GB 여유를 확인하고 필요할 때만 두 번째 허용 GPU를 사용한다. `CUDA_VISIBLE_DEVICES`를 직접 덮어쓰지 않는다.
- 로딩·예비 실행·모든 worker 시간을 합산하여 **55 device-minutes에서 중단**한다. 예비 입력의 속도로 남은 비용을 추정하고, 예산 초과가 예상되면 결과를 보지 않고 사전에 정한 공통 축소 규칙으로 전체를 T1CE만 실행한다. 그것도 불가능하면 미완료로 기록하고 중단한다. 일부 방법만 누락된 결과로 우열을 선언하지 않는다.

# Implementation Tasks for Claude

1. `research/`에 데이터 manifest 생성, 추론, 집계를 분리한 작은 실행 파이프라인을 만든다. 예: `context_pilot/`, `run_context_pilot.py`, `analyze_context_pilot.py`.
2. 추론 전 config와 manifest에 source 경로·hash, case ID, sequence, z-index, annotation 면적, packet 구성, 조건별 순서를 저장한다. 모델 입력과 평가 label을 분리한다.
3. CPU에서 의미 있는 검증을 수행한다: 영상-mask 정렬, 근거 픽셀 불변, packet 비중복, 조건별 image 수, 순서 변경 시 multiset 보존, repeated slice multiplicity, IAF의 작은 수동 예제, case 단위 집계와 기권 분모.
4. full-continuation scoring을 작은 수동 계산 또는 독립적인 teacher-forced 계산과 대조한다. 저장 형식에 raw score, candidate token, 예측, latency, 메모리, 실패 상태를 포함한다.
5. 예산 안에서 실행하고 조건·방법별 결과와 case별 원자료를 보존한다. 중단 후 재개 시 동일 config와 입력 hash만 재사용한다.
6. `research/results/iter_003/`에 manifest, config, predictions JSONL, metrics JSON, 보고서를 작성한다. 소표본 분모와 oracle 사용 여부를 모든 성능 표에 표시한다.
7. `research/`의 선행 연구 노트에 네 사고 라운드의 핵심 출처, 이번에 갱신한 MedPruner 공개 상태, MRI-GBM-MET의 확인·미확인 항목을 기록한다. `agent/PAPERS.md` 부재도 보고서에 알린다. orchestrator가 관리하는 브랜치·커밋·agent 기록은 직접 변경하지 않는다.

# Evaluation (성공/실패 기준 포함)

## 평가 단위와 metric

- 독립 단위는 case 3개다. sequence·packet·presentation 수를 환자 수로 세지 않는다. case 안에서 먼저 집계하고 case 평균과 원시 결과를 병기한다. 소표본 p-value로 일반화 주장을 하지 않는다.
- 주 기전 metric: 각 S의 P0 대비 log-odds drift `|m(S,C)−m(S)|`. 보정에도 같은 계산을 적용한다. E/N을 동일 가중하고 case별 결과를 보고한다.
- 동반 metric: E/N annotation-proxy balanced accuracy, 각 packet이 모든 context 조건에서 맞는지 보는 worst-context 정확도, P0 대비 flip 수, 양성·음성별 오류, E–N margin.
- 기권 baseline은 coverage·selective error·전체 분모 기준 정답 비율을 모두 보고한다. forced-choice 방법과 기권을 제외한 accuracy만 비교하지 않는다.
- IAF는 정확도 외에도 근거 slice 보존율·입력 token 수·시간을 보고한다. 전체 MedPruner를 이겼다는 결론은 내리지 않는다.

## 사전 진행 기준

다음은 논문 성공 기준이 아니라 다음 반복 투자 기준이다.

1. **측정 가능성:** packet-only E/N 구분이 6 case-sequence 중 최소 4개에서 올바른 margin 방향을 보이고, annotation-proxy balanced accuracy가 0.67 이상이어야 한다. 미달이면 context 보정보다 기본 인식·label 타당성 문제가 우선이다.
2. **불안정성 신호:** 같은 길이 비교 P1↔P2 또는 P1↔P3에서 최소 2개 case에 decision flip 또는 절대 log-odds 차이 0.5 이상이 있어야 한다. 동일 입력 반복 오차가 이 차이를 설명하면 측정 오류로 판정한다.
3. **보정의 유망성:** paired 보정이 concatenation 대비 평균 drift를 25% 이상 줄이고, 최소 2개 case에서 같은 방향이며, balanced accuracy와 worst-context 정확도가 낮아지지 않아야 한다.
4. **단순 baseline 확인:** mean/max·IAF·2-order ensemble이 적용 가능한 동일 조건에서 비용과 성능을 비교한다. 더 싼 baseline이 보정의 정확도·안정성을 모두 달성하면 paired 보정을 새 방법의 핵심으로 밀지 않는다.

세 기전 기준을 통과하고 단순 baseline이 해결하지 못한 잔여 문제가 있으면 `improve`로 이어가며 mask-free 설계와 독립 데이터 확보를 다음 과제로 삼는다. 보정 효과가 없거나 단순 baseline으로 충분하면 이 보정 가설은 포기한다. 3 case 결과만으로 접근법 전체의 논문 수준 success를 선언하지 않는다.

구현 검증·데이터 적격성·예산 문제로 비교를 완료하지 못한 경우에는 방법 실패와 구분해 `inconclusive`로 보고한다. 예산 초과 실행이나 사후 threshold 탐색으로 결과를 보완하지 않는다.

# Risks / Checks

- annotation-empty slice에는 미주석 이상이나 종양 관련 간접 소견이 남을 수 있다. 결과는 annotation 기반 proxy이며 정상/질병 진단 성능이 아니다. 이 한계가 관찰 효과를 좌우하면 임상 label이 있는 데이터로 넘어가기 전 방법 결론을 보류한다.
- E 선택과 R 구성에 GT를 사용한다. oracle 이득을 실제 추론 방법의 성능으로 제시하지 않는다. 후속 방법은 GT 없이 작동해야 한다.
- context는 진단에 필요한 정보일 수도 있다. 모든 context 영향의 제거가 바람직하다고 가정하지 않는다. 이번 질문과 annotation 범위에서만 검증한다.
- MRI-GBM-MET를 향후 사용하면 subject별 label·presentation 대응, 내부 license, 중복 및 split을 먼저 확인한다. 개발용 subject와 최종 평가 subject를 분리하고 현재 viewer의 `train`을 공식 split으로 사용하지 않는다.
- dataset/model 오염 가능성과 현재 표본의 비대표성은 남는다. 최종 논문은 독립 subject, 여러 데이터셋, 다른 VLM, accuracy–stability–cost 비교와 ablation이 필요하다.
- `pip install`, `conda activate`, cache 수정, 다른 사용자의 GPU 프로세스 조작은 하지 않는다. 필요한 의존성이 없으면 구체적으로 보고한다.

# 대규모 GPU 필요 후보

- 3D 공간 위치와 병변·해부학적 context를 함께 학습하는 volumetric encoder/projector 재학습: 구조적 개선 가능성이 있지만 대규모 paired volume과 학습 자원이 필요하다.
- 질문 조건부 근거 보존·근거 변화에 서로 다른 목표를 부여하는 multi-view 학습: LoRA 축소판은 후속 후보지만 충분한 데이터·negative 검증과 여러 view의 학습 비용이 필요하다.
- CORAL/MMedPO 계열을 결합한 대규모 preference 또는 reinforcement learning: 기존 방법과의 차별성을 먼저 확보해야 하며, 원형 재현 비용을 현재 두 장의 GPU에 맞는다고 가정하지 않는다.

# 계획의 근거 (GPT 조사 노트)

이번 라운드는 문서·코드·파일 목록 확인만 수행했다. 파일 변경, 모델 로딩, 실험 실행은 하지 않았다.

### 이전 기록에서 이어받을 내용
- `agent/GOAL.md`, `JOURNEY.md`, `INDEX.md`, `DECISIONS.md`, `iter_002/review.md`와 이전 사고 라운드를 확인했다. 이전 목표는 완료됐으며, `research`에는 초기 커밋 `0809430`과 점수 요약 커밋 `f213214`만 있다. `agent/PAPERS.md`는 없다.
- 재사용할 것은 JSONL 기록, 분모 보존, case별 집계, multi-image 입력 구성이다. legacy의 slice별 intensity 정규화, 조건마다 다른 MRI 안내문, 첫 token만 사용하는 답변 scoring은 그대로 재사용하지 않는다.

### 질문 1: 공개 MRI 자료의 실제 사용 가능성
- MRI-GBM-MET의 root에는 `.gitattributes`, `README.md`, 302 MB ZIP이 있다. README에는 90 subject, GBM/MET 각 45명과 slice filename을 통한 presentation 대응이 설명돼 있다. 그러나 ZIP 내부의 subject ID·진단 label·mask 파일 대응은 확인하지 못했다. README metadata에 license 항목이 없으며, viewer의 `train` 표시는 검증된 연구용 split이 아니다. shell의 HTTP 확인은 DNS 오류로 실패했다. 따라서 이번 실행의 필수 데이터로 채택하지 않는다. [파일 목록](https://huggingface.co/datasets/universitytehran/MRI-GBM-MET/tree/main), [README](https://huggingface.co/datasets/universitytehran/MRI-GBM-MET/blob/main/README.md)
- 향후 사용 시 최소 분리 단위는 subject다. 동일 subject의 두 modality와 모든 presentation을 함께 묶고, 개발에 사용한 subject는 최종 평가에서 제외해야 한다. 아직 공식 split이나 사용 조건을 확정한 상태는 아니다.

### 질문 2: 가장 가까운 방법과 검증할 차이
- MedPruner는 v2와 공개 저장소가 존재한다. 앞선 v1 기반의 공개 상태 판단을 갱신한다. v2는 anchor와의 pixel L1 차이를 이용한 slice filtering, attention 기반 token 선택, 잔여 token 집계를 설명한다. 공개 설정은 `gamma=0.05`, `tau=0.9`다. 이번에는 본문·README·설정 파일까지 확인했으며 내부 구현 전체를 검증하지는 못했다. [v2 본문](https://arxiv.org/html/2603.11625v2), [저자 저장소](https://github.com/CUHK-AIM-Group/MedPruner), [설정](https://raw.githubusercontent.com/CUHK-AIM-Group/MedPruner/main/config/config.json)
- 검증할 차이는 **시각적 중복을 제거하는 대신, 동일 context가 서로 다른 근거 packet의 답변 점수에 주는 공통 변화를 추정하여 상쇄할 수 있는가**다. 이는 질문에 조건부인 paired score 분석이다. 새로운 방법으로 확립됐다는 뜻은 아니며, GT 기반 reference를 쓰는 oracle 기전 실험부터 시작한다.
- 독립 slice mean/max는 slice 간 상호작용을 버리고, permutation ensemble은 순서 변화를 평균하며, consistency 기권은 coverage를 낮춘다. 이번 후보는 각 presentation에 별도로 점수 보정을 적용하여 정확도와 안정성이 함께 회복되는지 검사한다.

### 질문 3: 비교 조건과 허위 개선 방지
- 근거 packet을 고정한 상태에서 같은 길이의 context 교체, 같은 영상들의 순서 변경, 같은 길이의 중복·다양성 변경을 각각 비교한다. 길이 증가는 반복 추가 효과와 결합되므로 순수 길이 효과라고 부르지 않는다.
- 양성 packet과 annotation-empty packet을 모두 포함하고, case별 balanced accuracy·worst-context accuracy·점수 drift를 함께 본다. annotation-empty는 정상 환자나 임상적으로 확정된 음성을 뜻하지 않는다. 따라서 accuracy는 annotation 기반 proxy metric으로만 보고한다.
- 모든 presentation에 같은 최종 답을 복사하거나 기권을 늘려 얻은 안정성은 개선으로 인정하지 않는다.

### 질문 4: 이번 실행 범위 확정
- 로컬 BraTS 캐시에는 `00000-000`, `00002-000`, `00005-000`의 3 case에 대해 각각 4 MRI sequence와 segmentation이 있다. 이번에는 T1CE와 T2만 사용한다. 독립 분모는 3 case이며 6 case-sequence를 독립 환자로 세지 않는다.
- 로컬 모델 카드의 `apply_chat_template`과 생성된 suffix만 decoding하는 규약을 확인했다. 공식 CT notebook은 파일 존재만 확인했으며 코드 본문은 확보하지 못했다. 이번 MRI 입력을 공식 CT 재현이라고 부르지 않는다.
- 최대 258개 입력 scoring 요청과 12개 짧은 생성 확인을 계획하되, 모델 로딩·예비 실행을 포함한 총 GPU 사용을 55 device-minutes에서 중단한다. 데이터 추가 확보와 학습 없이 진행할 수 있다.

이전 사고 라운드 노트: agent/runs/iter_003/think/
