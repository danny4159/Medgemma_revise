# 사고 라운드 1

## 새로 확인한 것

최종 GOAL과 iter_070 plan/review, iter_083 review, iter_132 review를 읽었다. iter_070/124/129/132의 review.json에서 모듈별 재사용 범위와 관련 limitation 근거를 확인했다. 파일 생성·수정·다운로드·모델 실행은 하지 않았다.

### 1. iter_070은 위치 지원의 효과를 충분히 구분한 실험이 아니다

`agent/runs/iter_070/review.md`에서 실제 비교는 FLAIR 15사례, HIGH 4·MIXED_HIGH_LOW 11, P/G 각각 BA 0.613636이었다. 예측 mask와 annotation mask의 Dice 평균은 0.920396, 최소는 0.835393이다. 따라서 P/G 차이 부재는 위치를 알려줘도 설명을 못 한다는 일반적 근거가 아니다. 원래의 frozen 후보 종료 판정은 유지한다.

`git show 02a8adade58f7cea84638f9e96bf963a0fb64d55:ar70_run.py`를 직접 읽었다. G는 원 segmentation의 `seg>0`이며, P/G 모두 동일한 예측 anatomy mask를 사용한다. 실제 mask의 모든 양성 label을 합친 영역과 보고서가 말하는 병변의 신호 대상이 일치하는지는 별도의 문제다. 이 구현을 확인한 것은 과거 결과를 무효화한다는 뜻이 아니다.

### 2. 로컬 자료는 존재하지만 대상 의미와 이용 근거를 나누어 확인해야 한다

`research/results/iter_070/data/brats_manifest.json`에는 MedOtter/brats2023-gli-dataset revision `b032d353a3e80911a5f850bc54e6fb575298a354`의 FLAIR·seg 15쌍, 총 30개 파일 hash가 있다. 이번에는 manifest 내용을 읽었으며 파일 전체 hash를 새로 계산하지 않았다.

보존된 RadGenome `modal_wise_finding.json`은 920개 sequence별 항목, `global_finding.json`은 230개 scan 항목이다. 이는 독립 환자 수가 아니다. `label_table.json`의 revision은 `0348ba42fad134da57b50e736ba858a8e73eb086`이다.

실제 원문 예: 00012의 FLAIR 기술은 병변의 mixed high/low와 주변 edema를 분리한다. 00184도 병변의 혼합 신호와 주변 edema를 별도로 기술한다. 따라서 whole-tumor union을 무조건 신호 판독의 정확한 ROI로 취급하면 평가 대상이 달라질 수 있다. 반대로 tumor core를 임의 선택하는 것도 원문이 보장하지 않는다.

`research/results/iter_083/preflight_a1/release_evidence.json`에는 공식 설명이 2021/2023 영상 동일성과 ET label 4→3 변경을 뒷받침한다고 기록돼 있다. 동시에 개별 mirror 파일의 동일성·사용 권한 인증은 아니라고 한정한다. mapping 익명 다운로드 403은 모든 합법적 접근이 불가능하다는 뜻이 아니다. 다음 확인에서 이 과거 근거를 재사용하고, 같은 익명 요청만 반복하지 않는다.

### 3. 가까운 기존 방법이 설계 선택을 바꾼다

AutoRG 공식 README는 anomaly mask 제공과 자동 예측을 모두 지원하며, RadGenome 평가에 RGv2의 `given_mask`를 안내한다. RGv2는 RadGenome으로 학습됐고 segmentation 모델도 여러 공개 병변 자료로 학습됐다. 따라서 이 모델을 미노출 외부 대조로 간주하지 않는다. RadGenome 설명은 연구자가 병변 영역에 대해 작성한 보고서이며 실제 진료 판독문과 구분한다. [공식 AutoRG 구현](https://github.com/ljy19970415/AutoRG-Brain)

로컬 공식 보충 문서 `research/results/iter_070/external/raw/Supplementary.md`는 정확한 segmentation 이후에도 인접 구조의 이름이나 여러 영역에 걸친 병변의 해부학 기술이 틀릴 수 있다고 논의한다. 이는 저자의 문헌 주장이지 이번에 재현한 관찰이 아니다.

새로 확인한 가까운 대안은 MIDL 2026 BTReport다. 정량 영상 특징 추출과 문장 구성을 분리한다. 공개 구현은 최소 T1n과 NCR/ED/ET subregion mask를 요구하며 VASARI·midline shift 등의 경로를 제공한다. 따라서 위치·크기·해부학 관계만 골라 VLM 실패를 측정하면 강한 모듈형 대안 이후의 가치가 남지 않을 수 있다. 반면 현재 확인한 README만으로 FLAIR의 HIGH/MIXED 판독까지 해결한다고 단정할 수 없다. [논문 원문 페이지](https://proceedings.mlr.press/v315/heras-rivera26a.html), [공식 구현](https://github.com/KurtLabUW/BTReport)

BTReport-BraTS의 보고서는 합성 산출물이므로 임상 정답으로 대체하지 않는다. 전체 70B/120B 생성 파이프라인 설치를 발주하지 않는다. 필요한 특징 추출 부분의 실제 지원 범위를 먼저 확인한다. 논문 추천은 아직 하지 않는다.

### 4. 재사용 상태

현재 research 작업 트리는 깨끗하다. 추적 목록에는 mr132 계열과 mr123_data.py가 있지만 ar70 계열은 없다. ar70 소스는 위 전체 SHA에서 조회 가능하므로 소실된 것이 아니다.

`agent/CODE_ASSETS.md`와 iter_070 review.json상 ar70_labels.py는 기존 23건 수동 label 기록으로만 승인됐다. ar70_run/launch/patch는 재개·배타성·공식 경로 대조·tensor 검증 보완이 필요하다. evaluator에는 HIGH와 heterogeneous 동시 표현 처리 문제가 있다. 이번에는 어느 파일을 실행에 사용할지 확정하지 않아 reuse_assets를 비웠다. 실행 계획을 만들 때 필요한 파일과 의존성만 지정해야 한다.

## Strategy Check / 연구 방향 판단

1. 중요한 문제: 위치를 찾는 능력과 찾은 영역을 정확히 설명하는 능력을 분리해야 적절한 개입을 선택할 수 있다.
2. 현재 근거: MR-RATE 고정 양성 관찰과 iter_070의 제한적 음성은 유지한다. 새로 확인한 것은 mask 구성과 보고서 대상의 잠재적 차이, 그리고 BTReport의 공개 모듈형 대안이다. 새로운 모델 한계는 아직 관찰하지 않았다.
3. 쉬운 해결책: mask+정량 규칙, AutoRG 영역 판독, 위치 표시를 검토한다. 특히 정량 규칙이 직접 지원하는 출력만으로 새 방법 필요성을 주장하지 않는다.
4. 남은 설명: 관측 부족, 대상 지정 부족, 내용 판독 부족, 정답 대상 불일치다. 아직 이들을 구분할 평가 속성 하나를 확정하지 못했다.
5. 다음 결정: 병변 속성 판독을 주후보로 유지하되, 실제 정답 관계와 강한 대조의 지원 범위를 확인한 뒤 조건부 GPU 비교 하나로 확정한다.

## 왜 한 라운드를 더 쓰는가

처음의 후보는 위치 지원 전후 판독이었다. 조사에서 whole-mask와 보고서의 대상 차이가 드러났고 BTReport가 강한 대안으로 추가됐다. 이는 문서 보완이 아니라 평가 대상과 비교군을 바꾸는 근거다. 다음에는 과거 이력을 다시 읽지 않고 아래 세 질문에만 답한다. 현재 방향을 유지하는 한정 설계 판단이므로 deep_medium으로 낮춘다.

## 대규모 GPU 필요 후보

3D encoder·connector·언어 모델을 병변 subregion과 sequence별 설명으로 공동 적응하는 후보는 보존한다. 현재 정답 연결과 단순 대안 이후의 잔여 문제가 미확정이므로 대규모 학습 투자는 승인하지 않는다.

## 다음에 파고들 질문
- 보존 RadGenome FLAIR 원문과 BraTS label 의미에서, 병변과 edema를 혼동하지 않고 평가할 속성 하나를 결정할 수 있는가? label_table.json·modal_wise_finding.json의 기존 val 항목만 확인하고, 성립 여부에 따라 위치 지원 비교의 출력과 정답을 정한다.
- BTReport의 vasari_features 구현은 선택 속성을 영상에서 직접 계산하는가, segmentation label 의미로 대체하는가? 공식 관련 모듈을 확인해 필수 모듈형 대조와 oracle 정보 차이를 확정한다.
- 같은 slice·해상도의 위치 표시 비교로 구분할 수 있는 설명은 무엇이며, 충분한 관측이나 임상 정답을 가정하지 않고도 다음 투자를 바꿀 결과는 무엇인가? 기존 15사례의 재사용 가치와 한정 추가 자료 필요량을 정하고, 자료 검사 통과 시 실제 비교까지 포함한 계획 또는 명시적 보류로 끝낸다.
