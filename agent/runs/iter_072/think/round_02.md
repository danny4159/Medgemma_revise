# 사고 라운드 2

## 핵심 판단

**3DReasonKnee는 부위별 임상 등급 후보로 남기되, 지금은 구현을 발주하지 않는다.** 공개 정답 구조는 구체화했지만 프로젝트에서 사용할 원본 OAI 영상 경로와 접근 상태가 확인되지 않았다. 필요한 질문은 연구 방향의 재승인이 아니라 영상 이용 가능 여부다. 같은 근거로 자동 사고 라운드를 반복하지 않는다.

## 이전 라운드 질문에 대한 답

### 1. 실제 등급 과제를 정의할 수 있는가?

후보를 **질문이 지정한 연골 부위의 MOAKS size grade 0–3 판독**으로 좁힐 수 있다. 예를 들어 question 19는 medial central femur에 연결되고, 정답 구조는 `femur_medial_central_cartilage_lesion.size`와 `depth`를 별도로 둔다. 이번 후보는 두 속성을 섞지 않고 size를 대상으로 한다. [공식 question–subregion mapping](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/blob/main/data/question_files/question_subregion_mapping.json), [grade 구조](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/blob/main/data/question_files/grade_dict.json)

`cot_question_mapping.json`의 question 19에는 각 size/depth 등급에 대응하는 고정 설명이 있다. 따라서 이 CoT는 환자마다 독립적으로 관찰·작성한 근거 정답으로 취급할 수 없다. grade가 연결된 CoT를 추론 입력에 넣으면 정답 누출이다. 설명 생성의 유창성도 시각적 판독 증거가 아니다. [공식 CoT mapping](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/blob/main/data/question_files/cot_question_mapping.json)

논문은 OAI MOAKS 등급과 DESS MRI의 연결, 환자 중복 없는 분할을 보고한다. 다만 대부분의 영역 box는 수동 annotation으로 학습한 nnU-Net 예측에서 만들어졌다. 공개 box는 해부학적 영역 지원이며 수동 병변 oracle가 아니다. 논문에는 이미 Qwen 직접 SFT와 GT-region이라고 명명한 crop 대조가 있다. 따라서 같은 비교의 반복 자체는 신규성이 없다. [3DReasonKnee 원문 §3–4](https://arxiv.org/html/2510.20967v1)

**아직 확인하지 못한 것:** 원본 MOAKS 열과 배포된 size 정답의 case별 일치, 결측값 처리, 실제 영상 좌표 연결이다. 확인한 `code/` 배포 트리에는 DICOM 변환 경로가 있으나 전체 정답 생성·학습 경로를 재현할 코드를 확보한 것은 아니다. `grade_dict.json`의 기본값 0을 결측 등급의 정답으로 사용해서는 안 된다.

### 2. 환자 분리와 영상 접근은 성립하는가?

배포에는 `all_studies.csv`, `train_split.csv`, `val_split.csv`, `test_split.csv`가 있다. train CSV 원문 접근까지 확인했지만 세 split의 환자 교집합을 계산하지는 않았다. 환자 분리 가능성과 실제 분리 검증 완료를 구분한다. 시점·좌우 무릎도 같은 환자 cluster에 묶어야 한다. [공식 split 파일](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/tree/main/data/split_files)

배포 설명은 원본 DICOM을 OAI에서 따로 받도록 안내하며 NDA 계정이 필요하다고 명시한다. 실제 HF `data/OAI/`에는 segmentation·subregion 폴더가 보인다. 이를 원본 MRI 배포로 해석하지 않는다. [배포 및 접근 안내](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee), [OAI 폴더](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/tree/main/data/OAI)

NDA의 OAI 안내에는 로그인 후 원본 영상 package를 받거나 필요한 자료만 제한해 내려받는 경로가 있다. 일반 NDA 자료의 승인 조건을 OAI에 그대로 적용해 추가 IRB·기관 승인이 반드시 필요하다고 단정하지 않는다. 현재 필요한 것은 사용자의 실제 OAI 이용 가능 여부다. [NDA OAI 다운로드 안내](https://nda.nih.gov/general-query.html?q=query%3Dfeatured-datasets%3AOsteoarthritis+Initiative+%28OAI%29)

로컬 `agent/`·연구 코드의 OAI/MOAKS 관련 기록 검색과 프로젝트 내 이름 기반 영상 경로 확인에서는 이전 조사 노트 외 사용 가능한 OAI 자산을 찾지 못했다. 이는 연구실 전체에 자료가 없다는 증명이 아니다. 비밀번호·토큰은 검색하거나 요청하지 않았다. 로컬 Python HTTP 조회는 DNS 오류였고, 공개 웹 도구로 문서·파일 구조 확인을 계속했다. 이 네트워크 오류를 데이터 접근 거부로 기록하지 않는다.

확인한 HF main의 표시 commit은 `7a611f92fd3ad3954e8b62feef49ee12bfef725a`다. 웹 캐시의 파일별 시점이 달라 실행 시에는 동일 revision의 실제 파일을 고정해야 한다. [배포 commit](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee/commit/7a611f92fd3ad3954e8b62feef49ee12bfef725a)

### 3. 강한 비교와 최소 실험을 지금 확정할 수 있는가?

모듈형 비교의 근거는 있다. ISMRM 2022의 `Knee Osteoarthritis: Automatic Grading with Deep Learning`은 DESS에서 segmentation으로 영역을 추출하고 3D DenseNet으로 연골 이상을 분류했다. 다만 그 과제는 큰 연골 영역의 이진 분류이므로 이번 부위별 4등급의 성능 기준으로 수치를 옮길 수 없다. [원 연구](https://cds.ismrm.org/protected/22MProceedings/PDFfiles/4617.html)

후속 비교의 핵심은 직접 SFT와 영역 추출+분류기에 같은 영상·등급 학습 기회를 주는 것이다. 공개 예측 영역 지원은 실용 대조로 분리한다. crop은 위치뿐 아니라 해상도·배경·계산량을 함께 바꾸므로 개선을 순수한 선택 능력 회복으로 단정하지 않는다. 영상 없이 부위·box 좌표만 사용하는 대조도 label prior 여부를 확인하는 데 필요하다.

그러나 현재는 실제 입력·적격 환자 수·등급 분포·영상 접근이 확인되지 않았다. 이 상태에서 표본 수, 학습 epoch, 최소 효과, GPU 시간을 정하면 근거 없는 실행 계획이 된다. 따라서 학습 발주 대신 접근 여부를 먼저 확정한다. 접근 이후에도 기본 신호가 부족한 frozen 비교를 반복하지 않고, 공정한 직접 적응과 모듈형 대조가 투자 결정을 바꾸는 설계인지 판단한다.

## Strategy Check / 연구 방향 판단

상위 질문과 `mri-volume-evidence-use` track을 유지한다. iter_071은 위치 출력에서 강한 단순 대안을 확인했지만 부위 내부의 질환 등급 판독은 검증하지 않았다. 이전 라운드가 검토한 기존 grounding 개선·context 추가 진단의 자동 재개는 계속 보류한다.

이번에 배운 것은 새 데이터셋의 존재가 아니라 **임상 등급, 생성된 설명, 예측 영역을 서로 다른 근거로 취급해야 한다는 구체적인 설계 조건**이다. 유효한 신규 모델 실패는 아직 관찰하지 않았다. `mri-explicit-target-context-effect`는 계보상 관련될 뿐 이 무릎 과제의 method 근거가 아니므로 `limitation_ids=[]`로 둔다. 과거 limitation 상태는 변경하지 않는다.

## 재사용·실행 경계

`agent/runs/iter_072/think/round_01.json`, `agent/GOAL.md`, iter_071 review 원문, 관련 LIMITATIONS·CODE_ASSETS 항목을 확인했다. 현재 research 작업 트리는 clean이다. iter_071의 bbox parser 승인과 학습·재개·GPU 배치의 needs_fix는 보존한다. 아직 필요한 실행 경로를 선택하지 않았으므로 소스 반입이나 전면 정비를 발주하지 않는다.

원본 영상·모델·환경 다운로드, 코드 변경, GPU 실험은 수행하지 않았다. 접근 확인 전 준비 전용 iteration을 만들어 진행으로 세지 않는다. 이번 문헌은 사용자 추천 논문으로 등록하지 않는다.

## 다음과 종료점

사용자에게 승인된 OAI 영상 경로 또는 본인 계정의 다운로드 가능 여부를 질문했다. 답변으로 접근이 확인되면 같은 후보의 한정 자료 연결과 실행 설계를 마무리한다. 없으면 이 후보를 접근 문제로 보류한다. 답변 없이 동일 조회를 반복하거나 과거 설계로 자동 복귀하지 않는다.

## 대규모 GPU 필요 후보

다기관 MRI의 vision encoder–connector–language 공동 적응은 장기 후보로 보존한다. 현재 자료 검토만으로 필요성이나 효과를 주장하지 않는다.

## 다음에 파고들 질문
- 사용자가 이용 가능한 OAI DESS 영상 경로 또는 NDA 접근 상태를 알려주면, 그 경로가 공식 환자·시점·좌우 무릎·series와 연결되는가? 연결되지 않으면 후보를 보류한다.
- 접근이 확인된 경우, 고정 revision의 MOAKS 원본 열·결측 처리·환자 split과 실제 영상 연결이 연골 size grade 비교를 지지하는가? 지지할 때만 직접 SFT와 모듈형 대조의 규모·판정 기준을 확정한다.
