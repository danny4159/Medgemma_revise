# 사고 라운드 2

### 1. 로컬 자료의 label·독립성 확인
- `agent/GOAL.md`, `agent/INDEX.md`, `agent/runs/iter_003/review.md`, `claude_report.md`와 관련 코드를 다시 확인했다. 기존 접근법의 abandon 판정은 유지한다. 이번에는 파일 읽기와 저장된 metadata 집계만 했으며, 파일 생성·수정·모델 실행은 하지 않았다.
- `legacy/scripts/01_data/download_vindr_cxr_samples.py`는 `No finding`을 제외하고 소견 종류를 따라 10개 영상을 고른다. 로컬 `vindr_cxr/meta.json`의 영상마다 서로 다른 양성 소견이 2–6개 있으며, 총 37개 image–finding 조합이다. 따라서 같은 영상에서 질문을 교환하는 양성 grounding 검사는 가능하다.
- 캐시의 VinDr `test.csv`는 4,748행, 3,000 image ID, `No finding` 영상 2,051개다. 열은 image ID·소견·bbox·영상 크기뿐이며 환자 ID와 명시적 질환별 음성 label은 없다. 로컬 PNG는 10개이므로 CSV의 3,000개를 실행 가능한 영상 수로 세면 안 된다.
- 공식 VinDr에는 별도 `image_labels_test.csv`가 있으며 양성 1·음성 0을 제공한다. 반면 image ID는 SOP Instance UID에서 만든 영상 식별자이고 patient ID는 비식별화 과정에서 제거된다. 따라서 영상 ID 분할을 환자 독립 분할이라고 주장할 수 없다. 공식 페이지는 test 정상 영상을 2,052개로 설명하므로 로컬 변환 CSV와의 대응도 확인해야 한다. [VinDr 공식 설명](https://physionet.org/content/vindr-cxr/1.0.0/)
- 로컬 CheXpert는 frontal 7개에서 질환별 명시적 양성 6쌍·음성 8쌍을 제공한다. `No Finding`·`Support Devices`를 제외하면 같은 영상에 양성과 음성이 모두 있는 것은 `04.jpg`의 Edema/ Pneumothorax 한 사례다. mask·환자 ID도 없어 독립 검증 자료로는 부족하다. 근거: `legacy/eval_samples/not_in_training/chexpert/meta.json`, `legacy/scripts/01_data/fix_chexpert_meta.py`.
- SLAKE에는 같은 영상의 명시적 Yes/No 질문이 있지만, 확인한 예시는 장기 존재 질문 비중이 높다. 로컬 NIH metadata도 환자 ID·명시적 음성 annotation을 제공하지 않는다. 현재 자료만으로 독립 환자의 질환별 양성·음성·grounding을 모두 만족하는 평가를 구성할 수 있다고 확인하지 못했다.

### 2. 방법 신규성에 관한 중요한 추가 발견
- SECOND는 attention 기반 영역 선택과 contrastive decoding을 결합한다. crop confidence와 제거 반응을 조합한다는 설명만으로 차별화하기 어렵다. [SECOND](https://arxiv.org/html/2506.08391v1)
- 이번에 확인한 CSGR는 질문별 후보 영역을 제안하고, inpainting 후 정답 confidence 감소로 영역을 선택하며, 여러 judge의 결과를 결합한다. 본문 §3은 gold answer를 사용한다. 따라서 질문 조건부 counterfactual 영역 선택 자체는 이미 선행 방법이다. GT answer 없이 inference에서 선택한다는 차이는 검토할 수 있지만, 이것만으로 contribution을 확정할 수는 없다. [CSGR 원문 §3](https://arxiv.org/html/2609.13228v1)
- 의료 VLM에서도 patch occlusion, 질문 margin 변화, annotation overlap, 같은 크기의 무작위 영역 대조군, gray/blur 비교를 수행한 최근 preprint가 있다. 단순히 이러한 평가를 MedGemma 1.5에서 반복하는 것으로는 방법론 신규성이 부족하다. 해당 논문의 모델 명세를 우리 기준 모델과 동일하다고 확인한 것은 아니다. [Attention Without Grounding](https://arxiv.org/html/2607.18577v1)
- 남은 후보는 제거 반응의 크기보다 **질문 간 선택성**을 이용하는 것이다. 예를 들어 `D(q,R,t)=m(I,q)−m(T_t(I,R),q)`에서 고정된 다른 질문들의 평균 반응을 뺀 `C(q,R,t)=D(q,R,t)−mean_q' D(q',R,t)`를 검토할 수 있다. 이 값은 crop의 높은 Yes confidence와는 다른 정보를 측정하지만, co-occurrence·질문별 점수 척도·공유 근거 때문에 잘못된 보정도 가능하다. 아직 채택한 방법이 아니라 다음 라운드에서 반증할 후보 수식이다.

### 3. 대조군과 순환성에 대한 답
- 같은 영상에서 동일한 영역 변형을 여러 질문에 적용하면 영상·좌표·면적·변형 방식은 고정된다. 질문 교환 검사는 가능하지만, 질문마다 기대되는 해부 위치가 다르므로 질문 조건부 해부학적 prior까지 제거하지는 못한다.
- 동일 질문에서 다른 영상의 선택 지도를 가져오는 대조군과 같은 크기·유사 해부 위치의 영역 대조군을 추가해야 한다. 대조군을 맞출 수 없는 사례는 별도 표시하고 완전한 해부학적 통제로 표현하지 않는다.
- 고정 grid로 후보를 만들고 GT bbox/mask는 선택 이후 평가에서만 읽도록 분리한다. 주평가는 독립 annotation overlap과 원본 영상의 명시적 label로 하며, 선택에 사용한 margin 증가를 개선의 증거로 삼지 않는다.
- blur와 mean-fill은 임상적으로 정상인 counterfactual을 만들지 않는다. 제거 후 정답을 자동으로 No로 바꾸지 않으며, 두 변형의 결과 일치는 제한적인 강건성 검사로만 해석한다.

### 4. 실행 가능한 범위와 추가 데이터
- 추가 다운로드 없이 가능한 범위는 VinDr 10개 영상의 **양성 grounding 개발 pilot**이다. 이는 독립 환자 일반화, 음성 specificity, 진단 개선의 증명이 아니다. 기존 legacy 평가에 사용된 자료라는 점도 유지한다.
- 추가 데이터의 우선 후보는 CheXlocalize다. 공식 저장소는 validation 234영상/200환자, test 668영상/500환자와 10개 소견의 segmentation, 별도 영상별 label, patient 식별자가 포함된 annotation 형식을 설명한다. 643은 validation annotation 수이지 독립 환자 수가 아니다. [CheXlocalize 공식 저장소](https://github.com/rajpurkarlab/cheXlocalize)
- 공식 Stanford 다운로드 링크는 열었지만 본문을 확보하지 못했다. 사용 조건·실제 다운로드 크기·소규모 부분 취득 가능성은 미확인이다. 저장소의 MIT license를 데이터 license로 간주하지 않는다. [공식 데이터 배포 링크](https://stanfordaimi.azurewebsites.net/datasets/23c56a0d-15de-405b-87c8-99c30138950c)
- 비용 산정 예시: 영상 10개, 고정 질문 K개, 후보 9개, 원본 1회·crop 9회·두 제거 방식 18회이면 `280K` scoring 요청이다. K=4이면 1,120회이며 baseline concat·생성 검증 요청은 별도다. 실제 시간은 새 CXR 해상도와 processor 입력을 확인하기 전에는 기존 MRI 실행시간으로 확정할 수 없다.

### 판단
새로 확인한 선행 연구가 기존 가설과 직접 겹친다. 이번에는 구현보다 질문 간 선택성의 차별성과 CheXlocalize 취득 경로를 한 라운드 더 확인하는 편이 낫다. 막연한 추가 탐색 대신 다음 라운드에서 제한된 개발 pilot 진행 또는 다음 대안 전환을 결정한다.

## 다음에 파고들 질문
- CSGR의 관련 연구와 SECOND의 선택식을 기준으로, 질문 간 공통 제거 반응을 제거하는 C(q,R,t)가 기존 contrastive attribution과 어떻게 다른가? 공유 근거·co-occurrence 때문에 실패하는 경우까지 포함해 검증할 가설 하나를 고정할 수 있는가?
- CheXlocalize 공식 다운로드 안내에서 데이터 사용 조건, 파일 크기, patient별 영상·명시적 label·mask 연결을 확인할 수 있는가? 소규모 환자 분할을 확보할 수 없다면 로컬 양성 grounding pilot만으로 다음 투자 여부를 판단할 가치가 있는가?
- 로컬 VinDr의 어떤 소견 쌍이 공간적으로 구별되며, 고정 후보 grid가 이들을 분리할 수 있는가? 질문 교환·동일 질문의 영상 교환·단순 crop confidence 대조군을 포함한 최소 요청 목록과 사전 성공 기준을 확정할 수 있는가?
