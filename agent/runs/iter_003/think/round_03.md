# 사고 라운드 3

## 이전 기록 재확인
`agent/GOAL.md`, `JOURNEY.md`, `INDEX.md`, `DECISIONS.md`, `iter_002/review.md`, 사고 라운드 02 기록과 research의 전체 git 이력을 확인했다. 이전 목표는 `f213214`에서 완료됐고 새로운 방법론 구현은 없다. `agent/PAPERS.md`는 없다. 이번 라운드는 문서·코드 읽기만 수행했으며 파일 변경, 모델 로딩, 실험 실행은 하지 않았다.

## 질문 1 — MMedPO와 필요성·충분성 학습의 실제 범위
- **MMedPO 본문**은 원본 영상과 병변 영역을 noising한 영상에 동일한 정답을 붙이고, 전자를 선호하도록 clinical relevance 가중 DPO를 적용한다. 개입 후 별도의 임상 정답을 검증하는 설계와는 다르다. [MMedPO 본문 §3](https://arxiv.org/html/2412.06141v4)
- **공개 curation 코드에서 중요한 차이**를 확인했다. `inference_attention-map_score.py`는 질문별 병변을 선택하지 않고 MedKLIP의 고정 `disease` heatmap을 사용한다. heatmap의 mean−std를 threshold로 삼아 영역을 Gaussian noise로 대체하며, preferred/rejected conversation에는 같은 답변을 넣는다. 마지막 JSON 저장 부분은 주석 처리돼 있다. 따라서 논문 수식, 공개 코드, MedGemma 이식판을 구분해야 한다. [저자 curation 코드](https://raw.githubusercontent.com/aiming-lab/MMedPO/main/curation/Sample_Zero-Shot_Grounding_RSNA/inference_attention-map_score.py)
- **재현 baseline 한 문장**: MMedPO는 visual-tool 기반 영역 noising과 clinical relevance 가중 multimodal DPO를 재현할 대상이며, GT mask noising만 구현하면 전체 방법의 재현이라고 부를 수 없다. 공개 training 예제는 LLaVA-Med와 4 GPU를 사용하므로 이번 작은 진단에 전체 학습까지 넣지 않는다. [저자 저장소](https://github.com/aiming-lab/MMedPO)
- **남는 방법론 후보 한 문장**: 질문에 따라 보존해야 하는 근거와 허용 가능한 context 변화를 구분하면서 정확도를 유지하는 학습·추론 규칙은 검토할 가치가 있지만, 질문 조건부 mask나 consistency loss의 추가만으로 신규성이 확보되지는 않는다.
- **Hacking Hallucinations**의 개입 단위는 생성된 추론 token이다. prefix별 reward 차이와 token perturbation을 GRPO reward로 결합하며, expert lesion과 해부학적 context의 분리 실험은 아니다. 본문의 necessity 수식은 perturbation 후 reward를 최대화하는 형태여서 ‘제거 후 성능 저하’라는 설명과의 대응을 구현 전에 확인해야 한다. 현재 확인 범위에서는 실행 가능한 저자 코드를 확보하지 못했다. [본문 Methods](https://arxiv.org/html/2508.04182v1)

## 질문 2 — 3D 후보에 대한 직접적인 선행 연구 발견
- **MedPruner, 2026 preprint**는 이미 MedGemma-1.5-4B를 평가한다. 인접 anchor와의 pixel L1 차이로 slice를 선택하고, vision attention의 누적 질량으로 token을 줄인다. M3D accuracy는 원본 32.717→43.718, token retention은 4.87%로 보고한다. 단순 중복 제거·attention 선택·경량 pruning은 직접 비교 대상이다. 다만 보고 환경 8×H20이 소규모 재현에도 필수라는 뜻은 아니다. [본문 및 Table 1](https://arxiv.org/html/2603.11625v1)
- **Stable Evidence, Unstable Decisions, Findings of ACL 2026**은 이전 라운드의 3D 진단 가설과 매우 가깝다. 병변을 유지하는 FullVolume·ROISlices·ROICrops를 비교하고 **MedGemma-1.5-4B-IT**의 decision flip을 보고한다. FullVolume↔ROISlices는 T1CE 35.8%, T2 14.1%; FullVolume↔ROICrops는 각각 61.0%, 75.0%다. UNSURE 전환도 flip에 포함되므로 이를 모두 정답→오답으로 해석하면 안 된다. 이 논문은 진단 안정성과 모델이 보고한 근거의 관계를 평가하며 해결 방법을 제안한 논문은 아니다. 따라서 실패를 새로 발견했다는 주장은 철회하고, 방법 개발의 benchmark로 활용해야 한다. [공식 논문](https://aclanthology.org/2026.findings-acl.1303/)
- **Evaluating the Diagnostic Robustness…, 2026-08 preprint**도 reverse/shuffle, ROI-first/last, label 순서 변경, lesion-slice 제거를 평가한다. 여기의 의료 모델은 **MedGemma-27B**이므로 1.5-4B 결과와 섞지 않는다. 순서 민감성 진단 자체도 신규성이 부족하다. [본문](https://arxiv.org/html/2608.04885v1)
- ICCV 2025 workshop에서도 energy·K-center slice selection을 비교했다. 따라서 ‘slice를 잘 골라서 성능을 높인다’는 수준을 넘어서는 기전과 baseline이 필요하다. [공식 논문 페이지](https://openaccess.thecvf.com/content/ICCV2025W/VADH/html/Chen_Adapting_Vision-Language_Models_for_3D_CTMRI_Understanding_on_PMBB_via_ICCVW_2025_paper.html)

## 질문 3 — 입력 규약과 데이터 확보 경로
- **공식 anatomy notebook 본문을 확인했다.** 좌표는 `[y0,x0,y1,x1]`, 0–1000이다. 그러나 공식 prompt는 좌표 규약·환자 좌우·reasoning·Final Answer 형식을 명시하는 긴 지시문이며 legacy의 짧은 `Detect the …`와 동일하지 않다. 공식 예제는 `max_new_tokens=1000`과 thinking trace 처리도 사용한다. 따라서 legacy의 ‘공식 형식 평가’는 좌표 규약이 맞는 별도 prompt 평가로 표현해야 한다. 최신 notebook과 과거 실행 당시 버전이 같은지는 미확인이다. [공식 notebook](https://raw.githubusercontent.com/Google-Health/medgemma/main/notebooks/cxr_anatomy_localization_with_hugging_face.ipynb)
- 로컬 `/home/test/.conda/envs/medgemma/lib/python3.11/site-packages/transformers/models/gemma3/processing_gemma3.py`에서 `do_pan_and_scan=False` 기본값과 영상당 256 image token 확장을 확인했다. snapshot 설정은 896×896이며 image processor는 pan-and-scan 비활성 시 crop 없이 resize한다. 실행 시 실제 processor 종류·kwargs·pixel tensor·token 수를 함께 기록해야 한다.
- **공식 CT notebook의 코드 본문은 아직 확보하지 못했다.** raw URL은 도구 오류, GitHub 페이지는 notebook 내용 미노출, shell의 HTTP 읽기는 DNS 오류였다. 따라서 legacy의 HU window·sampling·orientation이 공식 구현과 정확히 일치한다는 주장은 계속 보류한다. MRI는 CT 규약을 그대로 적용할 수 없고 affine 기반 영상·mask 동시 변환과 volume 단위 intensity 고정이 필요하다.
- 추가 확보 없이 가능한 데이터는 기존 VinDr 10영상, BraTS 10영상/보수적 subject prefix 9개, BraTS volume 3 case다. 프로젝트의 `legacy`, `hf_cache`, `research`에서 CheXlocalize 고유 파일명은 찾지 못했다. 공식 CheXlocalize 다운로드 안내는 StanfordAIMI 계정·등록·약관 동의 후 SAS URL을 받는 절차다. 즉시 다운로드 가능한 로컬 데이터로 계획하면 안 된다. [다운로드 안내](https://raw.githubusercontent.com/rajpurkarlab/cheXlocalize/master/download_instructions.md)
- **새 확장 후보 MRI-GBM-MET**: 위 ACL 논문의 저자 데이터 페이지가 공개돼 있다. 카드에는 90명, GBM/MET 각 45명, T1CE/T2, 4,091 JPG, 총 302 MB와 subject별 4가지 presentation이 명시돼 있다. 정상 환자는 없지만 GBM 대 MET 분류에는 두 클래스가 있다. 현재 viewer는 label parsing 오류를 표시한다. 원시 파일·mask 배포 범위·license·split은 아직 확인하지 못했으므로 사용 가능 확정이나 다운로드 완료로 보고하지 않는다. [저자 데이터 카드](https://huggingface.co/datasets/universitytehran/MRI-GBM-MET)

## 질문 4 — 지금 구현으로 넘기지 않는 이유
2D 제거·보존 진단뿐 아니라 3D 근거 보존 context 진단도 직접적인 선행 연구가 확인됐다. 반면 3D에는 실제 MedGemma 1.5 실패와 작은 공개 데이터 후보가 있어 해결 방법 연구의 우선순위는 높아졌다. 마지막 사고 라운드는 새로운 실패를 주장하기 위한 검색을 넓히지 않고, **context 안정화 방법이 단순 선택·평균·다수결·기권보다 나을 수 있는지**와 데이터의 실제 사용 가능성을 확인하는 데 집중한다. 아직 특정 방법과 주효과를 정당화하지 못했으므로 60 device-minutes 실험을 확정하는 것은 이르다.

## 다음에 파고들 질문
- MRI-GBM-MET의 실제 파일 구조·license·subject ID·label·ROI 대응·split을 확인할 수 있는가? 공개 평가자료를 학습자료로 오용하지 않고 pilot과 최종 평가를 분리할 수 있는 최소 단위는 무엇인가?
- 3D context 안정화를 위한 질문 조건부 근거 집계는 MedPruner, 독립 slice 점수 평균·max, permutation ensemble, consistency 기반 기권과 어떻게 다른가? 가장 가까운 방법의 수식·코드와 비교해 검증할 차이 하나를 명시할 수 있는가?
- 고정된 병변 근거에서 context의 내용·중복·길이·위치를 분리하는 최소 비교는 무엇이며, 정확도와 안정성을 동시에 평가해 상수 예측·과도한 기권을 배제할 주효과와 중단 기준을 어떻게 고정할 것인가?
- 확장 데이터의 사용 가능 여부에 따라 공개 데이터 소규모 재현 또는 로컬 BraTS 3 case 기전 pilot 중 무엇을 택할 것인가? 공식 입력 규약과 scoring을 확인하고, 60 device-minutes 안의 실행량·baseline·분모를 확정할 수 있는가?
