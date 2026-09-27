# 사고 라운드 3

## 핵심

MedSG Task3·4의 실제 영상 쌍과 독립 case 수는 이번에도 확인하지 못했다. 따라서 해당 자료로 GPU 진단을 바로 확정하지 않는다. 대신 **원천 segmentation으로 reference 선택 쌍을 구성하는 경로**와 **MedSAM2라는 직접적인 모듈형 비교군**을 확인했다. 다음 조사에서는 이 경로의 실행 여부를 결정한다.

새 후보 SPIDER에는 공개 환자 218명의 MRI와 instance segmentation이 있다. 다만 주석 숫자는 임상적인 L1–L5 이름이 아니다. 이 차이를 무시하면 존재하지 않는 해부학적 정답으로 모델 오류를 만들 수 있다. 원천 자료 접근성이 좋아졌다는 사실과 실제 진단 집단을 확보했다는 사실은 구분한다.

이번에는 문서·코드·공개 파일 목록만 읽었다. 파일 생성·수정, 영상 저장, 모델 로딩, GPU 실험은 하지 않았다.

## 이전 질문 1: MedSG에서 같은 target에 서로 다른 reference 정답을 연결할 수 있는가?

**아직 입증하지 못했다.** round_02의 Task3·4 metadata 관찰은 유지한다. 이번에는 raw·resolve·blob 조회가 모두 실패했고, 로컬 HTTPS 조회도 DNS 오류였다. 앞 라운드의 관찰을 부정하는 결과가 아니라 현재 조회 환경의 제한이다. 같은 주소 재시도를 다음 라운드의 주작업으로 삼지 않는다.

원본 JSON과 Task3/4 ZIP을 연결하는 기존 최소 경로는 남아 있다. 그러나 파일명에 같은 case가 보인다는 이유로 target pixels가 같다고 판단할 수 없다. 서로 다른 장기 질문을 만들면서 장기별로 slice나 crop을 골랐다면 두 행은 유효한 reference 교체 쌍이 아니다. 이는 가능한 confound이며 현재 배포에서 실제 발생했다고 확인한 것은 아니다.

추가로 설계상의 식별 한계를 확인했다. **같은 target에서 reference box만 바꾸어 두 정답을 모두 맞혔다고 해서 reference 영상의 시각 정보를 사용했다고 단정할 수 없다.** box 좌표가 장기·상하 위치를 알려줄 수 있기 때문이다. 위치 복사 외에도 target+reference 좌표만 남긴 정보 제거 대조를 검토해야 한다. 이 조건은 정보 사용 진단이며 완전한 입력을 받는 실용 baseline과 구분한다. 정보 제거 조건의 실패 자체를 모델 결함으로 세지 않는다.

따라서 현재 MedSG 후보를 보류하는 근거는 낮은 모델 성능이 아니라, 선택한 연구 질문을 식별할 실제 쌍과 독립 단위가 아직 연결되지 않았다는 점이다.

## 이전 질문 2: 원천 case·주석·이용 조건과 독립 분할을 연결할 대안이 있는가?

### SPIDER 원저자 배포가 새 경로를 제공한다

[원저자 Zenodo v4](https://zenodo.org/records/10159290)는 공개 218명·447 series, 영상 ZIP 3.7 GB, mask ZIP 58.2 MB, overview.csv와 디스크 수준별 radiological_gradings.csv를 제공한다. [ZIP 내부 목록](https://zenodo.org/records/10159290/preview/images.zip?include_deleted=0)에서 `241_t1.mha`, `241_t2.mha`, `241_t2_SPACE.mha`처럼 case와 sequence를 연결할 파일명이 실제로 보인다. 영상 bytes·header·mask 값은 아직 읽지 않았다. CSV 직접 조회도 실패했으므로 적격 T1/T2 쌍 수나 최종 평가 환자 수를 확보했다고 보고하지 않는다.

[2024년 최종 논문](https://d-nb.info/1328551350/34)의 Methods에서 다음을 확인했다.

- 공개 자료는 218명이며 별도 비공개 test 39명이 있다. 공개 train/validation은 179/39명이다.
- 공개 T1/T2/T2 SPACE series는 각각 196/210/41개다. 이는 paired 환자 수가 아니다.
- 원천 자료의 공개 조건은 CC BY 4.0이다.
- instance는 아래에서 위로 번호를 붙였다. 가장 아래 lumbar vertebra의 label 1을 L5라고 해석하면 안 된다.
- 일부 T1/T2 mask는 T2 SPACE mask를 resampling한 뒤 움직임에 따른 misalignment를 검토·수정했다.

2023년 [arXiv v2](https://arxiv.org/html/2306.12217v2)는 218명의 179/39 분할을 설명하지만, 최종 논문은 별도 비공개 test까지 명시한다. 다음 계획은 최종 논문과 Zenodo v4를 기준으로 삼고 비공개 39명을 사용 가능한 확인 집단에 포함하지 않는다.

이 자료는 같은 target slice의 서로 다른 instance를 각각 reference로 지정할 수 있는 **주석상 경로**를 제공한다. 실제로 동일한 target pixels에서 두 instance가 충분히 보이는지, series 간 instance 번호가 맞는지, reference와 target의 공간 관계가 타당한지는 구현 전 자료 gate가 필요하다. 해당 관계를 확보하면 원천 환자 단위로 개발·확인 집단을 나눌 수 있다. 모델 사전학습에 노출되지 않았다는 주장까지 보장하지는 않는다.

### 원본을 읽는 이유가 분명하다

조회한 [제3자 SPIDER loader](https://raw.githubusercontent.com/cdoswald/SPIDER/main/SPIDER.py)는 배열 shape에 따른 축 변경과 영상·mask 변환을 수행한다. 이 코드를 원저자의 영상 방향 규약으로 간주하지 않는다. 후속 구현은 원본 MHA header와 정수 label을 먼저 확인하고, 표시용 변환과 GT 변환의 연결을 검증해야 한다.

원천 대안 WORD도 확인했다. [저자 논문](https://luoxd1996.github.io/files/WORD-MedIA2022.pdf)은 150명·16개 복부 장기 주석·100/20/30 분할을 기술한다. [공식 저장소](https://github.com/HiLab-git/WORD)는 이전 다운로드 승인 요구를 제거했다고 명시하지만 별도의 이용 조건을 제시한다. MedSG 전체의 CC-BY 표기를 원천 자료 전체에 일괄 적용하지 않는다. WORD는 대안으로 보존하며 이번에 영상 확보를 수행하지 않았다.

### 주장 범위

MedSG-188K 전체 감사가 없어도 미적응 MedGemma의 원천 환자 분리 진단은 설계할 수 있다. 반면 MedSeq-Grounder를 독립 일반화 비교군으로 쓰려면 해당 모델의 학습 원천·case 중복을 별도로 확인해야 한다. SPIDER를 사용한다고 자동으로 OOD 또는 미노출 자료가 되는 것은 아니다.

## 이전 질문 3: 어떤 모듈형 baseline이 필요한가?

### 같은 volume의 slice 추적에는 MedSAM2가 직접적인 비교군이다

[MedSAM2 공식 저장소](https://github.com/bowang-lab/MedSAM2)와 [3D 추론 코드](https://raw.githubusercontent.com/bowang-lab/MedSAM2/main/medsam2_infer_3D_CT.py)를 확인했다. reference slice의 box로 predictor를 초기화하고 앞뒤 slice로 mask를 전달하는 경로가 있다. 따라서 slice 추적 과제에서 임의의 frozen feature matching만 두고 강한 모듈형 비교를 완료했다고 할 수 없다.

공정한 사용은 benchmark가 입력으로 제공하는 reference box만 초기화에 쓰고 target mask는 평가에만 쓰는 것이다. 예제의 GT 기반 prompt 생성 함수를 target에 적용하면 oracle이 된다. 동일 입력 slice 조건과 전체 volume을 허용한 실용 조건은 입력량·비용을 함께 보고해야 한다. sparse slice 사이의 간격과 서로 다른 MRI contrast는 별도 조건이며 MedSAM2가 이를 잘 처리한다고 아직 가정하지 않는다.

### 서로 다른 MRI series에는 기하학적 대조도 필요하다

원본 header의 물리 좌표와 registration으로 대응을 해결할 수 있다면 이를 허용해야 한다. 편의상 원본 header나 주변 slice 접근을 막아 VLM의 상대 성능을 높이지 않는다. 반대로 잘못된 orientation이나 공간 대응을 그대로 사용하는 registration 결과를 강한 baseline으로 제시하지 않는다. 같은 volume의 slice 추적과 T1→T2 대응 중 하나를 먼저 고르면 비교군도 작게 유지할 수 있다.

[TotalSpineSeg 공식 README](https://raw.githubusercontent.com/neuropoly/totalspineseg/main/README.md)는 SPIDER를 학습 자료로 명시한다. 유용한 실용 비교군 후보지만, SPIDER에서의 점수를 미노출 zero-shot 일반화 근거로 쓰면 안 된다. 정확한 학습 환자 집합은 아직 확인하지 않았다.

### VLM 연구의 투자 가치를 바꾸는 기준

기존 round_02에서 확인한 MedSeq-Grounder·Migician·GeM-VG와의 중복 판단을 유지한다. 이번에 MedSAM2까지 확인했으므로 단순한 영역 전달 자체의 신규성은 더 약해졌다. 다음 투자는 VLM에서 중요한 reference 선택 실패가 재현되는지, 그리고 강한 모듈형 방법 대비 데이터 효율·새 조합 일반화·비용상 이점을 겨냥할 근거가 있는지에 달려 있다.

SPIDER의 소견 등급은 장차 선택한 영역에 대한 판단을 평가할 가능성을 제공한다. 그러나 segmentation 번호와 임상 level 연결, grade 판독에 필요한 영상 범위를 확인하기 전에는 QA 정답을 만들지 않는다. 한 slice나 crop만 제공하고 전체 검사에서 판정한 grade를 반드시 맞혀야 한다고 요구해서도 안 된다. 이번에는 임상 grading을 새 최종 목표로 고정하지 않는다.

## 이전 질문 4: 최소 GPU 행렬과 단계별 규모를 고정할 수 있는가?

**행렬의 구성은 좁혔지만 최종 규모는 아직 확정할 수 없다.** MedSG의 독립 case 수는 미확인이다. SPIDER의 공개 총 환자 수는 확인했지만, 조건을 만족하는 reference–target 쌍 수는 다르다.

검토할 최소 행렬은 joint, 명시적 영상 ID, 예측 설명을 거치는 분리 실행, 위치 정보만 남긴 대조, 해당 관계에 맞는 모듈형 baseline이다. localization oracle은 실제 주석이 허용하는 경우에만 추가한다. SPIDER에서는 label을 L5 같은 이름으로 바꾸는 oracle을 사용할 수 없다. 전체 집단과 oracle 성공 부분집합은 따로 보고한다.

정밀도에도 한계가 있다. round_02의 q=0.25, 95% CI 반폭 0.05 근사에 필요한 약 385개의 독립 쌍은 SPIDER 전체 218명보다 많다. 같은 환자의 slice·instance 수를 늘려 이 독립 표본 수를 채웠다고 해석할 수 없다. 따라서 좁은 효과 부재를 입증하는 설계보다 중요한 크기의 실패를 식별할 진단인지 먼저 판단하고, 환자 cluster를 반영한 규모를 정해야 한다. 218명은 사용 가능한 상한 정보이며 이번 계획의 확정 표본 수가 아니다.

후속 구현을 선택하면 동작 확인 → 고정 개발 집단 탐색 → 정밀도와 정보 이득에 따른 확대 → 보존 환자 확인을 구분한다. 적격 쌍 부재·주석 연결 불명확·모든 비교가 좌표 복사 문제로 환원되는 경우에는 본생성을 시작하지 않는다. 자료 gate 실패를 MedGemma 능력의 실패로 판정하지 않는다.

## Strategy Check / 연구 방향 판단

현재 1순위는 다중 영상 대응 질문을 유지하되, MedSG 조회를 반복하는 대신 원천 instance 주석을 사용하는 좁은 진단의 실행 가능성을 확정하는 것이다. 중요한 능력은 여러 영상에서 사용자가 지정한 근거의 정체성을 유지하는 것이다. 해당 실패와 새 방법의 필요성은 아직 확인되지 않았다.

- **현재 grounding 개선:** 직접 SFT의 효과는 검증됐지만 새 loss의 추가 가치가 없어 후순위다. 기존 checkpoint와 음성 결과를 보존한다.
- **원인·능력 진단:** 원천 자료가 대상 선택 쌍을 보장한다면 실제 출력으로 경쟁 설명을 나눌 수 있다. MedSAM2와 기하학적 baseline을 포함해 선택적 대응 학습의 필요성을 판단할 수 있다.
- **다른 연구 질문:** MedThinkVQA의 실제 다중 영상 진단은 대안으로 유지한다. 이미 다뤄진 설명·통합 오류 분석을 반복하지 않을 구체적 질문이 필요하다. SPIDER의 grade 자료가 있다고 해서 즉시 임상 QA로 전환하지 않는다.
- **기존 범위 민감성:** iter_018 F105, 추가 문구 탐색, 새 loss는 계속 보류한다. 관련 evidence가 꼭 필요한 사용 과제 없이 연장할 정보 이득은 낮다.

양성 결과라면 정상 입력과 강한 baseline을 통제한 실패의 빈도·크기를 확인한 후 방법 개발을 검토한다. 음성이면 위치·registration·기존 모듈형 해법을 보존하고 새 대응 학습 투자를 낮춘다. 불확정이면 표본 정밀도와 과제 식별성 중 어떤 문제가 판단을 막는지 구분한다. 주석이 불명확한 요청을 더 생성해 해결하지 않는다.

## 기존 근거·재사용·운영

`agent/GOAL.md`, `LIMITATIONS.md`, `REPORTING_STYLE.md`, 자원·연구·Claude 정책, `CODE_ASSETS.md`, iter_003·009·012·018 원본 리뷰와 legacy 중대 정정을 확인했다. iter_009의 RSNA 한계와 iter_012의 직접 SFT 개선은 유지하며 새 다중 영상 한계로 확대하지 않는다. `context-sensitivity`는 관련 observed 주장일 뿐 이번 후보의 validated 근거가 아니다. iter_008 보완의 일회성 정상 사용 검증을 다시 시작하지 않는다.

현재 research HEAD는 `4e453bbba4b0e798c0deeb6a940644dd62707fa3`이며 status와 diff에 변경이 없었다. tracked 파일 목록과 `geometry.py`, `generate.py`, `qa_gen.py`를 확인했다. 모델 로더의 고정 revision, 좌표 변환, parser·metric은 재사용 후보다. 단일 영상 request·hash·completion 경로는 다중 영상에 그대로 적용할 수 없다. 과제 확정 후 순서별 영상 hash, image-token 연결, 자료 잠금, 예상 요청 집합, 현재 버전의 중단·재개 검사를 포함해야 한다.

`reuse_assets=[]`는 조사 단계의 미확정 값이다. 기존 코드를 새로 작성하라는 뜻이 아니다. 구현 계획에서는 승인 기반과 실제 필요한 파일·의존성을 대조해 전체 SHA를 가진 반입 목록을 완성해야 한다. iter_018에서 지적된 원본 삭제·cache 변경을 반복하지 않고 새 결과 경로와 append-only 실행 이력을 유지한다.

두 RTX 3090 사용 방침은 유지한다. 다중 영상 입력의 실제 peak를 측정한 뒤 batch 확대 또는 GPU당 2 worker를 비교한다. 전체 처리량·출력 정합성·긴 출력 peak 및 worker당 2GiB 여유로 선택한다. 다른 사용자 프로세스는 건드리지 않는다. 기존 yes/no 처리량으로 이번 wall-clock을 추정하거나 임의 시간 상한을 두지 않는다.

## 대규모 GPU 필요 후보

원천별 대응 관계를 포함하는 vision encoder–언어 모델 공동 post-training과 일반 능력을 보존하는 혼합 학습을 보존한다. 현재 두 GPU의 진단·LoRA 가능성과 대규모 공동 학습 비용을 구분한다. 이번 조사로 대규모 학습의 필요성이 입증된 것은 아니다.

## 한 라운드 더 필요한 이유와 종료 조건

추가 조사는 새로운 문헌 목록보다 **SPIDER의 비해부학적 instance label을 이용한 유효한 대응 과제와 공정한 baseline의 확정**에 집중한다. 이는 잘못된 L1–L5 정답을 피하고, 같은 volume 추적과 cross-series 대응 중 어떤 질문에 투자할지를 바꾼다. 원본 배열을 읽어야만 알 수 있는 적격 수·pixel 검사는 조건부 구현 gate로 넘길 수 있지만, GT 정의와 비교 원리를 Claude의 임의 판단에 맡기지 않는다.

다음 라운드에서 정의가 성립하면 gate와 실패 시 종료 조건을 갖춘 한정된 GPU diagnostic 계획을 완성한다. 성립하지 않으면 이 후보를 보류하고 다른 질문을 선택한다. 같은 MedSG URL 재시도나 benchmark 평균 점수 산출을 위해 조사 라운드를 연장하지 않는다. 새 방향의 긍정적 실험 근거가 없으므로 논문 추천은 보류한다.

## 다음에 파고들 질문
- SPIDER 최종 논문·배포 규약에서 instance label의 series 간 대응과 mask–영상 방향을 어디까지 보장하는가? 같은 volume의 slice 추적과 T1→T2 대응 중 하나를 선택하고, 임상 level 이름 없이 유효한 정답·oracle을 정의할 수 있는가?
- 선택한 관계에서 위치 복사·물리 좌표/registration·MedSAM2와 Migician식 분리 실행을 공정하게 비교하는 최소 행렬은 무엇인가? 이 비교가 새 VLM 학습의 투자 판단을 바꾸지 못한다면 후보를 보류할 것인가?
- 공개 218명 상한과 실제 적격 수 확인 gate를 사용해 환자 분할·주효과 크기·탐색 및 확대 기준·요청 수를 고정할 수 있는가? 기존 코드의 정확한 반입 목록과 다중 영상 입력·재개 검증을 포함한 조건부 구현 계획을 완성할 수 있는가?
