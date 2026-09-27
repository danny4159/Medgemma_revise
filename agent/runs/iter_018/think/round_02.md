# 사고 라운드 2

## 핵심

부분 evidence 진단을 잠정 1순위로 유지한다. 다만 새 독립 진단에 필요한 정답 자료를 아직 확정하지 못했다. 이번에는 기존 cache의 실제 내용과 NIH–RSNA 연결을 확인했고, CheXpert 전문가 판독 자료로 이어질 구체적인 경로를 찾았다. 또한 다음 실험의 주지표를 정답 쌍 정확도보다 질문별 손상·회복으로 좁혔다.

파일 수정·생성, 모델 로딩, 새 실험은 수행하지 않았다. 아래 재집계는 기존 자료의 읽기 전용 분석이다.

## 1. 이전 질문: 다른 finding의 정답과 환자 식별을 확보할 수 있는가?

### 로컬 VinDr와 NIH 전문가 주석

`hf_cache/hub/datasets--sunday-hao--vindr-cxr-testset`의 실제 cache에는 revision `8a094b209bf9ca10706ca4f8e6457f541ad8070a`의 `test.csv` 470,517 bytes가 있었다. 공식 image-level label 파일은 확인되지 않았다. 기존 다운로드 코드는 bbox 행에서 10개 영상을 선택한다. 이 파일을 finding별 명시적 음성 주석으로 바꿔 해석하지 않는다.

프로젝트의 `hf_cache/`, `legacy/`, `research/results/`에서 확인한 범위에서는 NIH의 `four_findings_expert_labels`와 `all_findings_expert_labels` 원본을 찾지 못했다. 공식 페이지는 전문가 주석 접근용 form과 Google Cloud 영상의 Requester Pays를 구분한다. NIH 영상 자체의 공개 여부와 전문가 주석의 현재 확보 여부는 별개다. [NIH 공식 데이터 설명](https://docs.cloud.google.com/healthcare-api/docs/resources/public-datasets/nih-chest)

### 이미 있는 NIH bbox를 RSNA에 연결하는 대안도 검사함

다음 파일을 영상 ID와 SOPInstanceUID로 연결했다.

- `research/results/iter_007/official/BBox_List_2017.csv`
- `research/results/iter_009/source/raw/pneumonia-challenge-dataset-mappings_2018.json`
- 같은 디렉터리의 `pneumonia-challenge-annotations-adjudicated-kaggle_2018.json`
- iter_005 NIH manifest, iter_009·010 GT manifest, iter_010 이전 환자 제외 목록과 reserve 환자 목록

NIH bbox에는 다른 finding의 명시적 양성이 있지만, 이것만으로 finding별 음성이 생기지는 않는다. 실제 연결에서 RSNA Normal과 함께 존재하는 NIH bbox 영상은 Cardiomegaly 8개, Nodule 7개, Atelectasis 6개 등이었다. 이는 서로 다른 판독 범위·기준의 불일치이며 어느 쪽의 오류인지 이번 분석으로 판정하지 않았다. 따라서 RSNA Normal을 모든 NIH finding의 확정 음성으로 사용하는 설계는 채택하지 않는다.

현재 제외 목록과 reserve 보존을 그대로 적용하면 연결 가능한 신규 환자는 0명이었다. 참고로 실제 manifest에 등장한 환자와 reserve만 제외하고 보수적 이전 제외 목록을 적용하지 않으면 Atelectasis 환자 2명이 남았다. 두 환자는 `iter_005/nih_audit.json` 때문에 기존 제외 목록에 포함돼 있다. 이 차이를 발견했다고 제외 규칙을 완화하지 않았으며, 2명은 새 독립 진단의 근거로도 부족하다. 이 연결 경로를 추가 생성으로 확대하는 선택은 우선순위에서 내린다.

### CheXpert는 구체적인 후속 확인 후보

기존 cache의 `danjacobellis/chexpert` revision `ca5a840e438b5d2d0fa07f560782f196b38a84aa`에는 README만 있었다. 해당 schema는 `Path`를 보존하고, train 223,414영상과 validation 234영상을 구분한다. label encoding은 `0=unlabeled, 1=uncertain, 2=absent, 3=present`다. 공개 viewer의 train 경로에는 `patient00001/study1/...` 같은 환자·검사 식별자가 실제로 있다. legacy metadata는 이 Path를 보존하지 않았으므로 원본 경로를 복구하지 않고 환자 독립성을 주장할 수 없다. [기존 CheXpert 배포 경로](https://huggingface.co/datasets/danjacobellis/chexpert)

공식 설명은 validation 200 studies에 대해 세 판독자의 합의를 사용한다고 명시한다. 공식 사이트가 연결하는 연구진 저장소에는 test 500 studies/500 patients의 `groundtruth.csv`와 영상 접근 링크도 있다. 따라서 전문가 정답과 환자 ID를 함께 확보할 수 있는 구조는 확인됐다. [CheXpert 공식 설명](https://stanfordmlgroup.github.io/competitions/chexpert/), [연구진 test 자료 설명](https://github.com/rajpurkarlab/cheXpert-test-set-labels)

그러나 validation parquet의 실제 label·Path 연결, 공식 자료와의 일치, 현재 허용된 영상 접근 경로는 아직 확인하지 못했다. shell의 읽기 전용 HTTP 조회는 DNS 오류로 실패했고, web 도구의 validation viewer/API 조회도 실패했다. 이 실패를 데이터가 없거나 접근이 거부됐다는 증거로 해석하지 않는다. 새 등록·약관 동의·유료 접근은 수행하지 않았다.

추가 주의점은 study-level 정답이다. 234영상과 200 studies의 차이를 무시하고 각 영상을 독립 환자로 셀 수 없다. 원본 study의 frontal/lateral 구성을 확인하고, 단일 frontal만 사용할 경우 정답이 여러 view의 판독에 기반했다는 범위를 명시해야 한다.

## 2. 이전 질문: 최소 대조는 무엇인가?

단순히 scope 설명을 처음 추가하는 실험은 부적절하다. `qa_spec.py`와 `ev17_spec.py`에 이미 범위 설명이 있다. 다음 설계에서는 질문·영상·정보값을 고정하고 바뀌는 문장을 하나로 한정해야 한다.

최소 비교의 역할을 다음과 같이 좁혔다.

- **D:** 원본 영상과 질문만 제공한다. 실용 기준선이다.
- **U:** 정보값 없이 전문 도구 안내문만 제공한다. 안내문 자체의 영향을 측정한다.
- **B/K:** 기존 RSNA 예측 검출 유무·개수 조건이다. 과거 결과와 연결하되 다른 finding용 검출기로 확장하지 않는다.
- **T:** 동일 영상의 명시적 정답에서 finding A의 참인 값 하나만 제공한다. 검출 오류를 제거하는 oracle 진단이다.
- **T_scope:** T의 값과 구조를 유지하고, A의 판정이 다른 finding의 존재·부재를 결정하지 않는다는 한 문장만 추가한다.
- **R:** 질문 대상과 관계없는 evidence를 제외한다. 단일 finding 질문에서는 D와 같은 입력이 될 수 있으므로 별도 생성으로 요청 수를 늘리지 않는다.

RSNA에서 B/K의 문구 대조를 하고, 새 자료에서는 T/T_scope로 참인 정보의 영향을 분리하는 두 역할을 구분한다. 전체 조건을 모든 데이터에 기계적으로 곱하지 않는다.

다른 finding들이 통계적으로 연관될 수 있으므로, evidence를 받은 답변이 달라졌다는 사실만으로 오류를 선언하지 않는다. 정답 대비 손상과 회복을 함께 측정하고, A/B 정답의 네 조합을 구분한다. A와 B의 값이 반대인 사례만 모아 전체 성능이라고 보고하지 않는다.

단순 evidence 제외가 모든 손실을 해결하면 그것을 강한 baseline으로 보존한다. 필요하다면 이후에 두 finding을 함께 요구하는 질문을 검토할 수 있지만, Boolean 조합 문제의 개선을 임상 reasoning의 증거로 삼지 않는다. 현재 단계에서 새 복합 benchmark를 추가하기로 결정한 것은 아니다.

## 3. 이전 질문: 선행 연구와 구별되는가?

[Visual Evidence Prompting, ACL 2025](https://aclanthology.org/2025.acl-long.205/)은 전문 시각 모델 출력을 언어화하여 제공하는 가까운 방법이다. 공식 초록은 확인했지만 최종 PDF 조회는 파일 크기 제한으로 실패했다. 이전 OpenReview 초안을 ACL 최종본과 동일하게 취급하지 않는다. 따라서 관련 방법의 세부 대조를 완전히 끝냈다고 기록하지 않는다.

[Medical Context Distorts Decisions v1](https://arxiv.org/html/2605.17436v1)은 영상–텍스트 충돌, 무관한 과거 기록, 문구 민감성을 다루며 단일 condition으로 제한한 MIMIC-CXR 집단을 사용한다. 같은 영상의 참인 부분 정보와 다른 finding의 공존은 구별 가능한 진단 조건이다. 하지만 조건이 다르다는 사실만으로 새로운 방법론의 기여가 되지는 않는다. 단순 scope 문구·질문별 선택을 넘어서는 잔여 실패와 실용 이득이 필요하다.

시간 변화 판단은 중요한 대안이지만 즉시 더 쉬운 경로는 아니다. 새로 확인한 [MedGemma 1.5 공식 기술 보고서](https://arxiv.org/html/2604.05081v1)는 Chest ImaGenome의 sequential image 자료 39,968개를 RL 학습에 사용했다고 기술하며, MS-CXR-T를 OOD 평가로 표시하지 않는다. 이는 test 환자 누수의 증거가 아니다. 다만 MS-CXR-T를 새 외부 일반화 자료로 자동 간주할 수 없다는 뜻이다. [MS-CXR-T 공식 자료](https://physionet.org/content/ms-cxr-t/1.0.0/)의 접근과 원천 환자 연결도 확인해야 한다.

## Strategy Check / 연구 방향 판단

중요한 사용 과제는 전문 도구의 도움을 받으면서 도구가 판단하지 않은 소견도 원본 영상에서 계속 평가하는 것이다.

1. **부분 evidence 진단:** 실제 출력의 출발점과 재사용 실행기가 있다. 단순 문구·도구 오류·범위 해석을 구분할 정보 이득이 크다. 다만 독립 정답 자료를 확보하지 못하면 기존 RSNA 현상의 재서술에 머문다.
2. **시간 변화 판단으로 전환:** 임상적 중요성은 높다. 그러나 접근 가능한 longitudinal 영상과 학습 원천 중복 통제가 추가로 필요하다. 현재 자료 준비 비용이 더 낮다는 근거는 없다.
3. **현재 grounding 개선:** 강한 SFT baseline은 유효하지만 새 loss의 효과와 좌표 전달의 추가 이득은 입증되지 않았다. 이번 데이터 확인 결과가 grounding 학습 재개를 정당화하지는 않는다.

잠정 순위는 유지한다. 다음 판단을 바꿀 핵심은 CheXpert 전문가 정답과 실제 입력의 연결 가능성이다. 접근·정답 조건이 맞지 않으면 이 후보를 보류하고 대안을 선택한다. 데이터셋 이름이나 novelty 표현만 바꾸어 같은 진단을 계속하지 않는다.

## 4. 이전 질문: 효과·정밀도·비용은 어느 정도인가?

기존 원시 출력에 별도 whole-string parser를 적용해 NoOpacity/NotNormal 200명의 Q_A 전이를 재확인했다. 설명문 응답은 정답 문구가 포함돼 있어도 구제하지 않았다.

| 비교 조건 | direct 정답→오답 | direct 오답→정답 | Q_A 정확도 차이 |
| --- | ---: | ---: | ---: |
| U | 49명 | 0명 | −0.245 |
| B | 18명 | 5명 | −0.065 |
| K | 18명 | 9명 | −0.045 |

모든 비교의 direct 정답 분모는 107명이다. 따라서 K의 negative flip rate는 18/107이고, 전체 환자 기준 순손실은 9/200이다. direct에는 invalid 1건, U/B/K에는 invalid 0건이 있다. 정답 쌍 정확도에서 관찰한 큰 손실을 Q_A 자체의 같은 크기 손실로 해석하면 안 된다.

K−direct의 correctness 불일치율 q=27/200=0.135, 순차이 절댓값 0.045를 사용하면 paired 평균의 근사 표준오차는 sqrt((q−delta²)/n)이다. 같은 분포라는 가정 아래 95% 반폭은 n=200에서 약 0.0505, n=600에서 0.0292다. 반폭 0.03에는 약 568명, 0.025에는 약 818명이 필요하다. 이는 해당 질문·하위집단의 환자 수이며 E600 전체 수와 혼동하지 않는다. 새 자료의 불일치율을 보장하는 power 계산도 아니다.

따라서 CheXpert validation 200 studies만으로 작은 잔여 손실의 부재를 강하게 결론 내릴 수 없다. 처음에는 큰 손실의 재현·단순 문구 해소 여부를 판별하고, 불확정이면 실제 discordant pair 수와 확보 가능한 독립 자료를 기준으로 확대 여부를 정해야 한다. 정밀도 부족과 자료 접근 불가능은 별도 사유다.

iter_017의 4,800요청/901.18초는 전체 약 320 req/min의 참고 처리량이다. 예를 들어 200명×2질문×6개 실제 고유 조건이면 2,400요청, 같은 속도에서 생성·stage wall-clock 약 7.5분에 해당한다. 이는 새 입력의 실측 예산이 아니며 데이터 준비·모델 로딩·긴 출력·재개 검사를 추가해야 한다. 최종 행렬과 환자 수가 결정되면 다시 산정한다.

두 GPU의 총 4 worker는 계속 후보로 둔다. 새 development 입력에서 총 2 worker와 4 worker 또는 유망한 batch 확대를 비교하고, token 정합성·전체 처리량·GPU별 peak와 worker당 2GiB 여유를 확인한다. 긴 응답에서는 기존 짧은 QA peak를 그대로 적용하지 않는다.

## 코드 재사용과 남은 구현 결정

현재 research HEAD는 `d12ef5ccea60d05b9163519980cdb1624b3fa682`이며 작업 diff는 비어 있었다. `qa_spec.py`, `ev17_spec.py`, `qa_data.py`, `qa_protocol.py`, `qa_gen.py`, `qa_run.py`, `rsna_data.py`를 직접 확인했다.

기존 parser의 Normal/Abnormal 대응은 Q_A에만 적용된다. 새 finding에는 복사하지 않는다. 기존 실행기에는 RSNA 질문·출력 경로와 protocol의 필수 코드 목록이 연결돼 있으므로 새 데이터 이름만 바꾸면 작동한다고 가정하지 않는다.

재사용 전 필수 작업은 label/set/reuse manifest 잠금, 평가 시 해당 입력 hash 강제, 사용한 source completion·request·record의 연결 검증, 현재 수정본의 실제 중단·재개 검사다. 사용하지 않을 학습·기하 loss 경로의 결함은 이번 작업에 포함하지 않는다.

새 브랜치의 정확한 반입 파일 목록은 데이터와 실행 경로가 결정된 implement 계획에서 고정한다. 현재 `reuse_assets=[]`는 조사 상태를 뜻하며 전체 스냅샷의 승인이나 누락 모듈의 재구현 허가가 아니다.

## 양성·음성·불확정의 의사결정 가치

- **양성:** 같은 영상의 참인 부분 정보에서도, 단순 scope 문구 이후 독립 환자·다른 finding에 중요한 순손실이 남으면 조건을 명시한 한계 검증과 방법 비교로 진행한다.
- **음성:** 단순 문구 또는 질문별 evidence 선택으로 해소되면 그 baseline을 보존하고 이 방향의 새로운 방법 투자를 보류한다.
- **불확정:** 효과와 discordant pair가 추가 표본으로 판단 가능할 때만 확대한다. 명시적 정답 부재·study 연결 실패·접근 경로 미확인은 추가 생성으로 해결하지 않는다.

## 대규모 GPU 필요 후보

다중 finding과 전문 도구의 범위를 함께 학습하는 vision–language 공동 post-training, longitudinal 영상의 변화 표현 학습을 보존한다. 현재 진단이 강한 단순 baseline 이후에도 남는 문제를 확인했을 때 LoRA·모듈형 대안과 비용 대비 가치를 비교한다.

## 한 라운드 더 필요한 이유

이번 조사로 로컬 NIH–RSNA 연결을 새 독립 평가의 지름길로 사용하는 선택을 제외했고, CheXpert의 구체적인 전문가 정답·환자 경로를 찾았다. 다음 라운드는 이 경로의 실재성과 실행 가능성을 확인하고 조건·표본·반입 파일을 고정하는 데 사용한다. 같은 일반 문헌 검색이나 기존 E600 재집계를 반복할 필요는 없다.

## 다음에 파고들 질문
- CheXpert validation의 실제 Path·정답·study별 view를 공식 자료에 연결할 수 있는가? 현재 공개·허용 경로의 파일 metadata와 접근 조건을 확인하고, 실패하면 전문가 정답 자료 확보를 보류할지 결정한다.
- VEP 최종본의 evidence 선택·불완전 evidence 대조가 이번 최소 진단과 얼마나 겹치는가? 최종본의 해당 부분만 확인하여 단순 질문별 제외 baseline 이후 남을 연구 질문을 확정하거나 후보를 보류한다.
- 확보 가능한 환자·finding 조합을 기준으로 단일 주대조, 탐색과 독립 평가의 분할, 정밀도에 따른 확대 기준을 고정할 수 있는가? 가능하면 현재 SHA의 정확한 의존 파일 반입 목록과 GPU 요청 행렬을 포함한 implement 계획으로 마친다.
