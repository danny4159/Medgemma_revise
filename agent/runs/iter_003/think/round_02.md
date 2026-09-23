# 사고 라운드 2

## 이전 기록 재확인
`agent/GOAL.md`, `JOURNEY.md`, `INDEX.md`, `DECISIONS.md`, `iter_002/review.md`와 research의 전체 커밋·브랜치를 확인했다. 이전 목표는 `f213214`에서 완료됐으며, 새 연구 구현은 없다. `agent/PAPERS.md`는 여전히 없다. 이번 라운드에서는 파일 생성·수정, 모델 로딩, 실험 실행을 하지 않았다.

## 질문 1: 선행 방법과 실제 공백
- **CORAL**: 본문에서 이미지 전체 교체·corruption과 hard-negative answer-change 보상을 확인했다. 학습은 Qwen2.5-VL-7B LoRA지만 GRPO를 포함하며, 보고된 환경은 4×80GB H100이다. 따라서 LoRA라는 이유만으로 현재 서버에서 원형 재현이 저렴하다고 볼 수 없다. 본문·검색에서 실행 가능한 저자 코드 링크는 확인하지 못했다. 또한 서로 다른 질문에 붙은 answer label이 다르다는 조건만으로 교체 영상의 현재 질문에 대한 정답이 달라지지는 않는다. 이는 retrieval pair의 질문 조건부 타당성을 따로 확인해야 한다는 우리 측 방법론적 판단이다. [CORAL 본문](https://arxiv.org/html/2607.03647v1)
- **Attention Without Grounding**: 공개 `run_counterfactuals.py`는 256-patch occlusion 외에 ROI-delete, 같은 크기의 무작위 영역 대조군, JPEG null-edit, mild-contrast 안정성을 이미 구현한다. 따라서 이전 라운드의 제거·보존 진단 조합 자체는 새로운 contribution이 아니다. 무작위 박스 생성에는 시도 실패 시 overlap을 허용할 수 있는 fallback도 있어 그대로 복사하면 안 된다. [개입 코드](https://raw.githubusercontent.com/thedatasense/medicalvlm_attention_without_grounding/main/scripts/cxr/run_counterfactuals.py)
- 이 연구의 `constants.py`는 기준 모델을 **`google/medgemma-4b-it`**로 지정한다. MedGemma 1.5 결과로 인용해서는 안 된다. 고정 yes/no token ID와 직접 조립한 prompt도 사용하므로 현재 모델의 chat template으로 옮길 때 별도 검증이 필요하다. [설정 코드](https://raw.githubusercontent.com/thedatasense/medicalvlm_attention_without_grounding/main/scripts/cxr/constants.py)
- **SECOND, ICML 2025**: 저자 설명에서 attention 기반 multi-scale patch 선택과 단계별 contrastive decoding을 확인했다. 공개 실행 스크립트는 LLaVA-v1.6-Vicuna-7B, POPE, 4단계 recursion을 사용한다. MedGemma에 즉시 적용되는 코드로 확인된 것은 아니며, 전체 내부 구현 검토는 남았다. 단순 crop+contrastive decoding은 차별화하기 어렵다. [저자 방법 설명](https://aidaslab.github.io/SECOND/), [실행 코드](https://raw.githubusercontent.com/AIDASLab/SECOND/main/lmms-eval-vicuna/run.sh)
- **MedGround v2**: expert mask에서 box를 만들고 referring query를 합성·검증하는 데이터 및 SFT 접근이다. 35,480 triplet 중 train 25,420, test 10,060으로 보고한다. 본문에는 human audit의 전체 평가와 표본 평가 표현이 혼재하므로 정제된 test의 정확한 분모를 확인해야 한다. 초록은 acceptance 이후 코드·데이터 공개 예정이라고 명시한다. 공개 완료를 가정하지 않는다. [본문](https://arxiv.org/html/2601.06847v2), [공개 상태](https://arxiv.org/abs/2601.06847)
- **추가로 발견한 직접 비교 대상**: MMedPO는 이미 lesion-localized noise와 clinical relevance 가중 preference optimization을 다룬 ICML 2025 논문이다. 일반 VLM에서도 causal sufficiency·necessity를 결합한 token reward와 GRPO가 제안됐다. 따라서 ‘병변 제거를 이용한 LoRA’나 ‘필요성·충분성을 함께 최적화’만으로 신규성을 주장하기 어렵다. [MMedPO](https://proceedings.mlr.press/v267/zhu25v.html), [필요성·충분성 기반 학습](https://arxiv.org/html/2508.04182v1)
- CoMedPO라는 추가 후보를 발견했지만 저자 저장소는 현재 비어 있고 논문 원문을 확인하지 못했다. 학회·방법·성능에 대한 2차 요약은 확정 근거에서 제외한다. [저자 저장소](https://github.com/zxgapollo/CoMedPO)

## 질문 2: 데이터와 평가 가능한 질의
- **로컬 VinDr**: 다운로드 코드는 `sunday-hao/vindr-cxr-testset`에서 No finding을 제외하고 클래스별 앞쪽 영상을 선택한다. 10개 영상은 대표 표본이나 정상 대조군이 아니다. 캐시 CSV에는 image_id와 box·영상 크기가 있지만 patient_id가 없다. 따라서 현재는 image-cluster 분석까지만 가능하며 환자 독립성을 보증할 수 없다. 근거: `legacy/scripts/01_data/download_vindr_cxr_samples.py`, `legacy/eval_samples/not_in_training/vindr_cxr/meta.json`, 캐시 `test.csv`.
- 원본 VinDr는 train 15,000/test 3,000이며 공식 배포 접근에는 credential·DUA가 필요하다. 제3자 mirror가 보인다는 사실로 원본 접근 조건이나 annotation 동등성을 확정할 수 없다. 현재 영상에서는 주석된 finding에 대한 class-conditioned localization·점수 변화가 가능하지만, 미주석 영역을 정상으로 간주하거나 box 부재를 곧바로 음성 label로 사용하면 안 된다. [원본 데이터 설명](https://physionet.org/content/vindr-cxr/1.0.0/)
- **로컬 BraTS**: 10개의 종양 최대면적 slice와 binary mask가 있다. `BraTS-GLI-00008-000`과 `00008-001`은 같은 subject일 가능성이 있어 보수적으로 묶어야 한다. subject prefix 기준으로는 9개이며 공식 mapping 확인 전 환자 수로 단정하지 않는다. mask는 NCR·ED·ET 합집합이므로 이를 모두 enhancing tumor라고 질문하면 label 오류다. 정상 환자 대조군은 없다.
- BraTS NIfTI 캐시를 실제 확인하니 **3개 case × 4 MRI sequence와 segmentation = 15개 파일**이다. 10개 case 전체 volume이 캐시에 있다고 가정하면 안 된다. 확장 접근은 공식 Synapse 절차를 확인해야 한다. [BraTS 접근 안내](https://www.synapse.org/Synapse%3Asyn51156910/discussion/threadId%3D10562)
- **추가 후보 CheXlocalize**: 공식 저장소는 validation 234영상/200환자, test 668영상/500환자, 10개 pathology의 pixel mask와 별도 GT label CSV를 명시한다. 분류와 근거 평가를 연결하기에 VinDr mirror보다 명세가 명확하다. 실제 접근 가능 여부와 로컬 확보 여부는 아직 확인되지 않았다. 선행 논문의 ‘validation 643 samples’를 독립 영상 수로 받아들이면 안 된다. [CheXlocalize 공식 명세](https://raw.githubusercontent.com/rajpurkarlab/cheXlocalize/master/README.md)

## 질문 3: 공식 사용법과 우선 수정
- 공식 모델 카드는 Gemma 3 기반 MedGemma 1.5, 896×896 입력과 영상당 256 token, `apply_chat_template` 사용을 명시한다. 로컬 snapshot `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`의 `preprocessor_config.json`도 896×896·256 token이며 `do_pan_and_scan`은 null이다. 실제 processor가 적용한 기본값과 crop 수를 기록해야 한다. [공식 모델 카드](https://huggingface.co/google/medgemma-1.5-4b-it)
- 우선순위는 **① yes/no scoring과 생성 답변의 구분 → ② 조건 간 동일 prompt·전처리 → ③ 영상·annotation 좌표 대응 → ④ 3D orientation·windowing**이다. legacy logprob 코드는 문자열의 첫 token만 사용하고 중복 ID를 제거하지 않으며, 두 후보 점수 비교를 `greedy`라고 부른다. 이는 전체 vocabulary에서 실제 생성한 답변과 다르다.
- legacy detect의 좌표 규약은 코드에서 확인했지만, 파일 설명 자체가 ‘모델 탐색으로 발견’했다고 명시한다. 공식 anatomy·CT notebook의 존재는 확인했으나 이번 도구에서는 notebook 본문을 읽지 못했다. 따라서 정확한 공식 prompt·좌표·CT 전처리 대조는 완료됐다고 보고하지 않는다. [공식 notebook 목록](https://raw.githubusercontent.com/Google-Health/medgemma/main/notebooks/README.md)
- MRI는 `np.rot90`만으로 anatomical orientation을 보장하지 않는다. NIfTI affine 기반 영상·mask 동시 변환, volume 단위 intensity 범위 고정이 선행돼야 한다. 병변 없는 slice도 정상 환자는 아니며, mask 밖에 다른 이상이 없다고 보증하지 않는다.

## 질문 4: 방향과 작은 실험
현재 확실한 결론은 2D 제거·보존 **진단 자체를 논문 contribution으로 삼을 수 없다는 것**이다. 여전히 쓸모 있는 것은 annotation과 유효한 개입을 이용한 baseline 진단이다. 방법론 후보는 질문 조건부 근거 선택 학습과 3D에서 근거를 고정한 context 추가·중복 효과로 좁힌다. 후자는 인위적 병변 삭제 없이 자연 slice로 검사할 수 있지만, slice-selection 선행 연구와 실제 확장 데이터가 추가로 필요하다.

실행 예산의 잠정 상한은 2D 19개 subject/image cluster 이하·cluster당 한 질의·최대 8조건, 또는 캐시된 3D 3개 case·최대 8조건이다. 두 안을 동시에 실행하지 않는다. GPU 총 사용량 60 device-minutes를 상한으로 두고, 추론 전 2개 사례의 시간·메모리로 실행량을 줄이는 설계를 고려한다. 이는 실행시간 예측이나 검정력 보장이 아니며, 현재 소표본은 pipeline과 효과 방향 확인에만 쓸 수 있다.

## 다음에 파고들 질문
- MMedPO 본문·코드와 causal sufficiency/necessity 학습은 질문 조건부 정답이 검증된 개입, 근거 보존 대조군, 해부학적 context를 어디까지 다루는가? 그대로 재현할 baseline과 남는 방법론 차이를 각각 한 문장으로 정의할 수 있는가?
- 3D slice-selection 선행 연구와 MedGemma 1.5 평가에서, 동일 병변 근거를 유지한 채 자연 context·중복·순서만 바꾸는 실패를 이미 다뤘는가? 이를 고치는 경량 방법이 단순 top-k selection을 넘을 여지가 있는가?
- 공식 anatomy·CT notebook 본문과 로컬 processor 구현을 읽어 prompt·좌표·crop·orientation 규약을 확정할 수 있는가? CheXlocalize 또는 대체 데이터에서 추가 확보 없이 시작할 표본과 향후 환자 단위 확장 경로는 무엇인가?
- 앞의 비교를 바탕으로 2D 근거 선택과 3D context 민감성 중 하나를 선택하고, 기존 baseline·주효과·분모·중단 기준이 고정된 60 device-minutes 이내 진단 계획을 완성할 수 있는가?
