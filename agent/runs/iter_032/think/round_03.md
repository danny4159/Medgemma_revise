# 사고 라운드 3

## 핵심 판단

합성 padding·translation 진단을 바로 구현하지 않는다. 동일 픽셀의 위치 효과를 분리하는 대조는 가능하지만, 알려진 변환을 되돌리는 단순 전처리가 정확한 해결책이 되는 조건이다. 이 결과만으로 새 학습 방법의 필요성을 보이기는 어렵다.

외부 grounding 전이의 타당성을 다음 확인 대상으로 올린다. 다만 현재 확인한 로컬 자료는 본평가를 시작하기에 부족하며, 외부 Lung Opacity를 RSNA의 pneumonia-suspicious opacity와 동일 정답으로 취급해서는 안 된다. 새로운 방법과 contribution은 여전히 미확정이다.

이번에는 문서·공개 코드·자료 설명·로컬 metadata를 읽었다. 파일 생성·수정, 모델 로딩, 실험 실행은 하지 않았다.

## 질문 1의 답: 선행의 LoRA 위치에 대한 이전 판단을 정정한다

라운드 02는 MedFM-Robust 논문 §2.2의 vision encoder attention LoRA 설명을 근거로 우리 언어층 LoRA와 구분했다. 논문에 그런 설명이 있다는 사실은 유지된다. 그러나 이를 실제 구현의 확정된 차이로 사용하면 안 된다. [MedFM-Robust 원문](https://arxiv.org/html/2605.19027v1)

이번에 확인한 공개 `VLM/eval_vlm_perturbation.py`에서 MedGemma와 1.5는 같은 `MedGemmaFineTuner`를 사용한다. `prepare_model`은 `q_proj/k_proj/v_proj/o_proj/gate_proj/up_proj/down_proj`를 이름으로 지정하며 vision-only 경로 제한이 없다. 모델·processor는 로컬 경로에서 불러오고 revision을 고정하지 않는다. 추론은 RGB 영상과 system/user 메시지를 `apply_chat_template`에 전달한다. 따라서 실제 학습 모듈·모델 revision·processor 설정은 논문 실행의 checkpoint와 환경 기록 없이는 확정할 수 없다. [공개 평가·학습 코드](https://raw.githubusercontent.com/AbnerAI/MedFM-Robust/main/VLM/eval_vlm_perturbation.py)

같은 코드의 `MeCoVQAAdapter.get_ground_truth`와 `run_evaluation`은 원본 conversation 또는 원본 mask에서 GT를 얻는다. 변환 종류·행렬을 받아 GT 좌표를 옮기는 경로는 확인되지 않았다. 공개 변환 코드는 scale에서 축소 후 중앙 배치하고 translation에서 영상 이동과 반사 경계를 사용하지만, 해당 행렬을 annotation에 연결하지 않는다. 이 공개 경로 그대로라면 기하 변화의 점수에 정답 좌표 불일치가 섞일 수 있다. 논문의 모든 보고 수치가 잘못됐다고 단정하지 않는다. [변환 코드](https://raw.githubusercontent.com/AbnerAI/MedFM-Robust/main/VLM/generate_perturbation.py)

이는 논문 재현 감사 연구를 새로 시작할 근거가 아니다. 우리 실험에서 기하 GT를 함께 변환해야 한다는 근거이며, 선행 구현의 불확실성을 우리 신규성으로 계산하지 않는다. 공개 main의 전체 commit SHA는 이번 조회에서 확보하지 못했다. 후속 기록에는 조회일 2026-09-29와 확인 함수 범위를 남기고, 논문 실행 버전과 동일하다고 표현하지 않는다.

## 질문 2의 답: 위치 효과는 분리할 수 있지만 정보 손실 전체를 분해할 수는 없다

로컬 고정 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`의 `preprocessor_config.json`과 `config.json`을 확인했다. 입력 크기는 896×896, resample=2, patch_size=14이며 `do_pan_and_scan=null`이다. `research/rsna_diag/generate.py::load_image/build_inputs`는 값 보존 RGB·정사각 padding·공식 chat template 경로를 사용한다. 실제 processor의 해석은 실행 시 tensor 대조로 확인해야 한다.

최소 대조의 구성 가능성은 다음과 같다. 이는 실행 확정안이 아니다.

- 전체 원본 영상을 한 번 축소한 동일한 672×672 RGB 배열 P를 만든다.
- 896×896 검은 canvas에 P를 중앙 `(x,y)=(112,112)`, 왼쪽 `(0,112)`, 오른쪽 `(224,112)`에 붙인다. 세 조건은 P의 픽셀·크기·보간이 같고 영상 내용이 잘리지 않는다.
- 원본 정사각 기준 정규화 좌표 x에 대해 출력 canvas 좌표는 `x'=0.75*x+1000*offset_x/896`이다. y도 같은 식이다. GT와 예측을 같은 좌표계에서 비교한다.
- processor 이후에도 payload가 동일한 정규화 픽셀 배열인지, crop 수·영상 token 수가 같은지 검사해야 한다. 경계에 있는 예측을 임의 clipping해 FP를 없애면 안 된다.

중앙과 좌우 조건의 차이는 추가 downsampling 없이 위치·경계 문맥 변화에 대한 민감성을 검사한다. 그러나 이를 언어 decoder 좌표 prior만의 인과 효과라고 부를 수는 없다. vision encoder의 위치 반응과 경계 문맥도 변한다.

원본 896 입력과 중앙 672 배치를 비교하면 정보량·병변 크기·padding이 함께 달라진다. 672→896 재확대 대조를 추가해도 보간과 공간 주파수가 변하므로 정보 손실의 완전한 분해가 되지 않는다. 라운드 02에서 제시한 '정보 손실과 좌표계 변화 분리'는 이 제한 안에서만 가능하다.

### metric과 단순 대조

M0의 clean 점수가 낮으므로 상대 하락률이나 단순 하락폭만으로 SFT가 더 취약하다고 판정하지 않는다. 각 조건의 절대 F1@0.3·F1@0.5, 양성 recall, 음성 FP/환자, invalid를 함께 보고, 환자별 중앙 대비 이동 차이와 해당 조건에서의 B0−M0 이득을 paired 방식으로 계산해야 한다. GT는 평가에만 사용한다.

중앙 예측을 좌표만 이동한 결과는 영상 재추론 없이 계산 가능한 기준이다. 중앙 예측을 그대로 복사한 위치 고정 대조와도 비교할 수 있다. 하지만 가장 강한 GT-free 대안은 전처리 metadata로 payload를 재중앙화한 뒤 예측을 원래 canvas로 돌리는 것이다. 이 구성에서는 재중앙화가 중앙 입력을 정확히 재현한다. 그 성공은 새로운 시각 능력이나 독립적인 효과의 증거가 아니다.

## 질문 3의 답: 합성 배치 실험의 투자 가치는 제한적이며 외부 경로도 아직 실행 가능하지 않다

합성 배치 대조가 양성이면 정보가 같은 입력에서도 위치 민감성이 있다는 제한적 근거를 얻는다. 음성이면 해당 이동 범위에서 SFT 이득이 유지됨을 알 수 있다. 불확정이면 paired 정밀도를 늘릴 수 있다. 그러나 세 결과 모두 현재 과제에서는 알려진 전처리 역변환을 넘어 새 방법이 필요한 사용 조건을 제시하지 못한다. 따라서 지금 대규모 robustness 평가나 증강 학습으로 연결하지 않는다. 후속 외부 실패를 해석할 보조 검사로 보존하는 편이 타당하다.

외부 확인은 SFT의 실제 확장성을 판단한다는 가치가 있다. 이번에는 이전에 미확인으로 남긴 접근·정답 조건을 공식 설명과 로컬 파일로 좁혔다.

### VinDr-CXR

공식 자료는 Lung opacity·Consolidation 등을 local finding으로, Pneumonia를 global diagnosis로 구분한다. test annotation은 여러 판독자의 합의 결과다. 따라서 pneumonia 양성 영상의 모든 Lung Opacity box를 pneumonia 원인 병변이라고 간주할 수 없다. 공식 파일 접근에는 credentialing·교육·DUA가 필요하다. [VinDr-CXR 공식 설명과 접근 조건](https://physionet.org/content/vindr-cxr/1.0.0/)

로컬 `legacy/eval_samples/not_in_training/vindr_cxr/meta.json`은 10개 영상이다. Lung Opacity box 2개, Consolidation 2개, Infiltration 1개가 있으며, 이 세 label 중 하나라도 있는 영상은 3개다. `legacy/scripts/01_data/download_vindr_cxr_samples.py`는 이상 소견 class별 첫 영상을 모아 선택했다. 대표성 있는 외부 표본이 아니다. 이는 iter_028의 접근·표본 한계를 뒤집는 새 자료가 아니라, 실제 선택 방식과 관련 영상 수를 추가 확인한 것이다.

원래 다운로드 출처는 `sunday-hao/vindr-cxr-testset`이다. 이번 웹 도구로 해당 dataset card에 접근하지 못했고, 설정된 HF_HOME의 해당 표준 cache 디렉터리도 없었다. 이 사실로 계정 권한 부재나 전체 서버의 자료 부재를 단정하지 않는다. 토큰 파일을 읽거나 다운로드 스크립트를 실행하지 않았다.

### CheXlocalize

공식 repository는 CheXpert validation/test 영상에 대한 Lung Opacity·Consolidation 등을 포함한 radiologist segmentation을 설명한다. validation은 234영상·200환자, test는 668영상·500환자다. mask에서 만든 connected component를 RSNA의 개별 병변 box와 자동으로 동등하게 취급해서는 안 된다. [CheXlocalize 자료 설명](https://github.com/rajpurkarlab/CheXlocalize)

로컬 `research/results/iter_018/source/medaug_valid.csv`에는 234행이 있고 Lung Opacity 양성 126행, Consolidation 양성 33행, Pneumonia 양성 8행이다. 이는 영상 수준 label 수이며 환자 수나 위치 정답 수가 아니다. 기존 `chexpert_validation.parquet`의 존재는 확인했지만, `research/results/`에서 `gt_*segment*.json`에 해당하는 파일은 찾지 못했다. 이 검색 범위를 넘어 segmentation이 없다고 단정하지 않는다.

공식 다운로드 안내는 StanfordAIMI 로그인·등록·약관 동의를 요구한다. 기존 영상 mirror를 갖고 있다는 이유로 segmentation 접근 권한도 확보됐다고 볼 수 없다. [공식 다운로드 안내](https://raw.githubusercontent.com/rajpurkarlab/cheXlocalize/master/download_instructions.md)

따라서 현재 '동일 opacity의 외부 확인'이라는 이름부터 조건부다. pneumonia-suspicious opacity와 더 넓은 Lung Opacity 간 target 이동을 명시해야 한다. 정답 대응을 확보하지 못하면 외부 점수 하락을 순수한 기관 일반화 실패로 해석할 수 없다.

## Strategy Check / 연구 방향 판단

중요한 사용 과제는 직접 SFT로 얻은 병변 검출 이득이 실제 입력·원천 변화에서도 유효한지 확인하는 것이다. 새로운 corruption 점수표나 문헌 구현 결함 자체는 최종 contribution이 아니다.

1. **외부 grounding 전이의 타당성 점검 — 잠정 1순위.** 기존 checkpoint의 확장 여부라는 투자 결정을 바꿀 수 있다. 다음 확인은 정답 의미·자료 provenance·실제 사용 가능한 annotation에 한정한다. 외부 데이터셋 추가 자체의 신규성은 주장하지 않는다.
2. **동일 픽셀의 위치 변화 진단 — 우선순위 하향.** 통제 가능한 대조는 설계했지만 정확한 재중앙화 대안 때문에 단독 방법 개발 경로는 약하다. 실제 외부 실패가 생겼을 때 보조 진단으로 검토한다.
3. **후보 수·순서 추가 진단 — 종료 권고 유지.** 라운드 02의 비용 비교와 Pix2Seq 중복을 뒤집을 새 근거가 없다. 추가 sampling이나 순서 변경 학습을 예약하지 않는다.
4. **다른 post-training 질문 — 대안 유지.** 외부 과제의 정답·사용 조건을 구성할 수 없으면 명시적으로 비교한다. 접근 부담만으로 MRI·longitudinal에 조용히 이동하지 않는다.

think_more를 선택한 이유는 구현 세부가 부족해서가 아니다. 이전 차별화 전제가 수정됐고, 실행 가능한 합성 대조의 결과가 후속 방법 투자를 바꾸는 힘이 약하다는 점이 드러났기 때문이다. 다음 라운드에서 새로운 광범위한 benchmark 목록을 만들지 않는다.

## 기존 지시·자산·미완료 작업

iter_012의 SFT 성과와 iter_031의 제한적 후보 회복을 유지한다. QA 형식 효과·evidence 전달·사분면 선택·빈 출력 위험·continuation 진단을 미실행 과제로 되돌리지 않는다. 일반적인 공간 능력 전이와 외부 일반화는 미해결이다. 새 학습, MRI F139, 기존 reserve, iter_022 longitudinal은 보류한다.

`agent/GOAL.md`, `REPORTING_STYLE.md`, `LIMITATIONS.md`, `CODE_ASSETS.md`, iter_031 원본 리뷰와 이전 조사 기록을 대조했다. `lesion-grounding-generalization`은 기존 RSNA 조건에서 validated이며, 새 입력 안정성·외부 전이 주장은 그 상태를 자동 상속하지 않는다.

research HEAD는 `8dad463392de9bb0e9fe7d93d64b9c374492de9b`이고 status/diff는 비어 있다. 현재 `generate.py`, `geometry.py`, `parse.py`, `metrics.py`, `lora.py`, `risk30_source.py`, `risk30_eval.py` 및 의존 파일을 확인했다. `roi26_run.py`는 현재 브랜치에 없으며 과거 보존 커밋의 자산이다. 이를 소실로 간주하거나 재구현하지 않는다.

새 브랜치의 승인 기반과 선별 반입 목록은 실행 경로를 정한 뒤 고정한다. 현재 빈 reuse_assets는 전체 코드 재사용 승인이나 누락 파일 대체 허용이 아니다. iter_031의 층별·IoU≥0.5·center-in-GT·비용 분석은 여전히 새 결과 경로에서 정식 보완해야 한다. C/E GPU 본실험을 재생성할 필요는 없다.

이번에는 GPU 표본 수와 실행 시간을 확정하지 않았다. 구현 계획에서는 실제 입력의 2/4 worker 또는 batch 확대 비교, 전체 peak와 worker당 2GiB 여유, 출력 정합성, 단계별 확대·재개 기준을 고정한다. GPU 회피를 방향 선정 기준으로 삼지 않는다.

## 대규모 GPU 필요 후보

다기관·다소견의 정답 범위를 정렬한 자료로 vision encoder와 언어 모델을 공동 적응시키고, grounding·일반 질의·입력 안정성을 함께 유지하는 post-training을 후보로 보존한다. 충분한 해상도·batch·seed와 외부 평가에는 더 큰 자원이 필요할 수 있다. 필요성과 신규성은 미확정이며 현재 두 GPU에서 가능한 경량 적응을 배제하지 않는다.

## 다음에 파고들 질문
- 기존 자료의 출처 기록과 공개 metadata에서 VinDr 또는 CheXlocalize의 이용 가능한 annotation·영상 연결을 확인할 수 있는가? 확보된 자료와 추가 계정·약관 동의가 필요한 자료를 구분하고, 필요한 경우 어느 자료의 어떤 접근만 사용자에게 요청해야 하는가?
- RSNA의 pneumonia-suspicious opacity와 외부 Lung Opacity·Consolidation 사이에서 정답이 보장되는 평가 범위를 정의할 수 있는가? target 이동을 명시한 전이 진단이 가능한지, 단순 기관 일반화 비교가 불가능한지를 결정하라.
- 위 조건을 충족하는 외부 진단의 양성·음성 결과가 직접 SFT 유지, 모듈형 대안 비교, 새로운 방법 투자 중 무엇을 바꾸는가? 구체적 분기가 없으면 합성 robustness 실험으로 되돌아가지 말고 다른 질문 또는 필요한 사용자 결정을 확정하라.
