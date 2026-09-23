# 사고 라운드 1

### 현재 기록과 코드 확인
- `agent/GOAL.md`, `agent/INDEX.md`, `agent/runs/iter_004/review.md`를 읽었다. 이전 두 접근법은 abandon이므로 재선택하지 않는다.
- iter_004의 C_blur macro U=0.5106은 raw-D=0.4987보다 조금 높지만 위치 prior=0.6147보다 낮았다. 영상별 개선도 1/9이므로 해당 선택 규칙을 추가 조정할 근거는 없다.
- `research/evaluate_qes.py`, `research/select_qes.py`, `research/qes/store.py`에서 리뷰의 검증 결함을 확인했다. evaluator는 verification 통과와 selection의 predictions digest를 강제하지 않으며, 중복 prediction 검사는 `m`만 비교한다. 재사용할 경우 실제 입력·request 재해시, verification 완료 조건, 전체 사용 결과 필드의 digest 연결을 먼저 보완해야 한다.

### 전이 가설의 출발점에도 재검증이 필요하다
- `legacy/docs/MEDGEMMA_평가_전체정리.txt`의 중대 정정을 먼저 읽었다. 해부구조 IoU≈0.256과 병변 IoU≈0.071은 소규모 개발 관측이며, 해부구조 평가에는 심비대 등 병변 박스를 대리 정답으로 사용했다. 이 차이만으로 해부구조→병변 전이 실패의 원인을 확정할 수 없다.
- MedGemma 1.5 기술보고서는 Chest ImaGenome localization mean IoU=38.0을 보고하며 Appendix B, Table 12의 질문은 `Where is the {object}?`이다. legacy에서 공식 형식으로 부른 `Detect the ... box_2d ...`와 문구가 다르다. 두 형식의 공식 출처와 좌표 규약을 대조해야 한다. 이것만으로 기존 결과가 무효라는 뜻은 아니다. [MedGemma 1.5 기술보고서](https://arxiv.org/html/2604.05081v1)

### 선행 연구와 겹치는 부분
- **AnatomiX**는 해부구조 검출·지역 특징·검색한 설명을 MedGemma-4B 기반 LLM에 연결하고 LoRA로 학습한다. 따라서 '해부구조 정보를 넣어 병변 grounding을 개선한다' 자체는 contribution이 아니다. 논문은 APM에 237,000개 이상 Chest ImaGenome 샘플을 사용하고, 전체 학습에 H100 80GB 4장·약 125시간을 보고한다. 대상은 MedGemma 1.5라고 명시된 모델이 아니다. [AnatomiX 원문](https://arxiv.org/html/2601.03191v1)
- **CURE**는 해부구조·phrase grounding 등을 공동 학습하고 task/class 오류에 따라 sampling을 조절한다. 단순 anatomy multitask 또는 curriculum 추가도 차별성이 약하다. [CURE 원문](https://arxiv.org/html/2601.15408v1)
- **F-LMM, CVPR 2025**는 frozen LMM의 word–image attention을 학습 가능한 mask decoder로 읽고 SAM 기반 refinement를 적용한다. 따라서 frozen backbone에 grounding head를 붙이는 것 역시 기존 방법이다. 공식 코드는 transformers 4.39.1 등을 사용하므로 현재 환경에 바로 적용 가능하다고 가정하면 안 된다. [F-LMM 논문](https://openaccess.thecvf.com/content/CVPR2025/papers/Wu_F-LMM_Grounding_Frozen_Large_Multimodal_Models_CVPR_2025_paper.pdf), [공식 코드](https://github.com/wusize/F-LMM)
- **AG-KD**는 형태·위치·밀도 등으로 병변 설명을 분해하고 Florence-2 0.23B를 학습한다. VinDr 16,087 training pairs와 PadChest의 known/unknown 병변 평가를 사용하므로 저비용 semantic grounding 비교군으로 검토할 가치가 있다. [AG-KD 원문](https://arxiv.org/html/2503.03278v1)
- **VGMED, ICLR 2026**도 의료 MLLM의 visual grounding과 semantic grounding을 구분한다. 우리 연구 역시 '병변을 못 찾는다'는 현상 확인을 넘어 어느 단계가 제한인지 구분해야 한다. 이번에는 abstract까지 확인했다. [ICLR 공식 페이지](https://proceedings.iclr.cc/paper_files/paper/2026/hash/999a7fa10ed25ce8b836b14ff003ad50-Abstract-Conference.html)

### 데이터와 실행 가능성
- `legacy/scripts/01_data/download_vindr_cxr_samples.py`는 비공식 testset 미러에서 No finding을 제외하고 클래스 다양성을 기준으로 10영상을 선택한다. 저장 metadata에는 image ID는 있지만 patient ID는 없다. 이 자료로 학습 효과나 환자 일반화를 검증해서는 안 된다.
- 로컬 문서는 MIMIC-CXR/Chest ImaGenome을 확보하지 못했다고 기록한다. Chest ImaGenome의 공식 배포도 credentialed access다. 현재 접근 권한은 확인되지 않았으므로 사용할 수 있다고 가정하지 않는다. [Chest ImaGenome 공식 배포](https://physionet.org/content/chest-imagenome/1.0.0/)
- 지금까지 확인한 연구 코드는 추론·평가 파이프라인이다. MedGemma 1.5 LoRA 학습의 설치 의존성, activation memory, step 시간은 아직 확인하지 않았다. 추론 VRAM 8–10GB를 학습 예산으로 사용할 수 없다.

이번 라운드는 파일 읽기와 웹 조사만 수행했으며 코드 수정·파일 생성·실험 실행은 하지 않았다.

## 다음에 파고들 질문
- MedGemma 1.5의 기술보고서·공식 localization 예제·로컬 checkpoint는 각각 어떤 prompt와 좌표 규약을 사용하는가? legacy의 해부구조–병변 격차에서 출력 형식과 대리 annotation의 영향을 어떻게 분리할 것인가?
- 현재 접근 가능한 공식 데이터 중 해부구조 annotation, 병변 annotation, patient 단위 분할을 확보할 수 있는 조합은 무엇인가? Chest ImaGenome 접근 없이 가능한 대체 조합과 그 한계는 무엇인가?
- AnatomiX·CURE·F-LMM·AG-KD 및 VGMED의 상세 설정과 비교했을 때, anatomy supervision의 효과를 추가 데이터량·위치 prior·출력 decoder 적응과 구분하는 최소 실험과 잠재적 contribution은 무엇인가?
- 설치된 라이브러리와 모델 구조에서 frozen feature/head, attention decoder, LoRA 중 어떤 경로가 RTX 3090 24GB에서 가능한가? 다음 구현 반복을 1시간 미만 GPU 예산으로 제한할 때 확보 가능한 비교군과 평가 표본은 무엇인가?
