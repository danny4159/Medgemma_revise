# 사고 라운드 1

### 이전 기록 확인
- `agent/GOAL.md`, `JOURNEY.md`, `INDEX.md`, `DECISIONS.md`, `agent/runs/iter_002/review.md`를 읽었다. 이전 목표는 완료됐으며 이어받을 미완료 과제는 없다. `agent/PAPERS.md`는 존재하지 않는다.
- `git -C research log --all --oneline`에는 초기 커밋 `0809430`과 점수 요약 구현 `f213214`가 있다. 브랜치는 `base`, `approach/scores-summary`이며 새로운 연구 방법론이나 학습 코드는 아직 없다.
- 두 legacy 정리 문서와 분류 감사·로그확률 추론·공식 형식 위치 추정·3D CT/MR 코드를 확인했다. 이번 라운드에서는 파일 변경이나 실험 실행을 하지 않았다.

### 새 목표에 중요한 발견과 정정
1. **최저 저장 점수가 곧 최우선 연구 문제는 아니다.** 초기 bbox 평가는 비공식 좌표 형식이었다. 별도 detect 형식 평가에서 BraTS IoU는 약 0.229, VinDr 병변은 0.071, DeepLesion은 0.007로 기록돼 있지만, 소표본·모달리티·정답 정의가 달라 그대로 능력 순위를 만들 수 없다. VinDr 심비대 박스를 해부구조 정답으로 사용한 결과도 공식 해부구조 benchmark 재현이 아니다.
2. **문서의 로그확률 분류 ‘성공’은 감사 결과를 반영해 제한해야 한다.** `legacy/eval_results/diagnostics_classification_estimand.json`에서 CheXpert pooled AUC는 0.7003이지만 label-only 기준선은 0.6592, 평가 가능한 6개 label의 macro AUC는 0.5879, within-label permutation의 macro p는 0.1970이다. 원래 140쌍 중 unlabeled가 103개이며, explicit-only 30쌍에서는 양성과 음성을 모두 가진 label이 Pneumothorax 하나뿐이다. NIH는 macro AUC 0.7333, within-label macro p=0.0306으로 다른 양상을 보이지만 독립 영상은 10장이고 7장이 Hernia다. 이는 CheXpert 시각 신호의 부재를 증명하지도, pooled AUC로 시각 신호를 입증하지도 못한다.
3. **3D 개선에는 텍스트 교란이 있다.** `rerun_ct3d_official.py`의 다중 슬라이스 조건만 안내문에 CT를 명시한다. 따라서 CT 모달리티 2/3→3/3은 시각 인식 개선의 독립적 증거가 아니다. MR도 다중 슬라이스 조건에만 MRI/brain 안내문이 추가된다. MR 코드의 실제 windowing은 slice별인데 설명은 volume별이라고 적혀 있다. ‘슬라이스 수만 변경했다’는 문서 해석은 성립하지 않는다.
4. **위치 추정의 기존 채점은 진단용에 가깝다.** `rerun_localization_official.py`는 GT 클래스명을 질의하고 모든 예측·GT 조합 중 최대 IoU를 사용한다. 이는 class-conditioned localization이며 추가 오검출을 벌점 없이 허용한다. 반복 질의 수를 독립 환자 수로 해석해서도 안 된다.
5. **기존 실패에서 얻을 교훈은 유용하다.** 단순 bbox 축소는 거의 개선되지 않았고, attention map은 무관 질문 대조군과 같았으며, gradient 기반 위치 추정은 데이터셋 간 일관성이 없었다. 그러나 일부 방법 실패만으로 모든 training-free 접근이 소진됐다고 판단할 수는 없다. 합성 마커의 위치 정보 보존도 실제 병변 의미가 충분히 인코딩됐다는 증거는 아니다.
6. **재사용 가능한 기반은 있다.** `research/summarize_scores.py`의 분모 보존 원칙, `audit_classification_estimand.py`의 label별 평가·image-cluster 분석, detect 좌표 변환, 3D 입력 구성, 기존 JSONL 출력이 출발점이다. 다만 감사 스크립트에는 legacy 이동 전 절대경로가 남아 있고, 로그확률 코드는 yes/no 문자열의 첫 token만 취하므로 token 길이·중복 ID·실제 생성 답변과의 대응을 재확인해야 한다.

### 선행 연구와 novelty 위험
- MedGemma 1.5의 anatomical localization, 3D, longitudinal 기능은 실제 추가된 기능이다. 현재 모델을 교체해야 할 근거는 없다. [MedGemma 1.5 Technical Report](https://arxiv.org/abs/2604.05081)
- CVPR 2025 MIMO는 visual referring 입력과 pixel grounding 출력을 함께 다룬다. 단순 segmentation 결합이나 grounding fine-tuning 자체를 contribution으로 삼기 어렵다. [MIMO](https://openaccess.thecvf.com/content/CVPR2025/html/Chen_MIMO_A_Medical_Vision_Language_Model_with_Visual_Referring_Multimodal_CVPR_2025_paper.html)
- ICML 2025 SECOND는 multi-scale 시각 정보 선택과 contrastive decoding을 다룬다. crop과 decoding을 결합하는 방향은 이 방법과의 차이를 확인해야 한다. [SECOND](https://proceedings.mlr.press/v267/park25c.html)
- 2026년 7월 preprint CORAL은 blank·shuffle·image-absent·hard-negative 교체 평가와 answer invariance를 억제하는 LoRA 학습까지 제시한다. 단순 이미지 의존성 진단이나 hard-negative LoRA는 이미 직접적인 선행 방법이 있다. [Do Medical Vision Language Models Actually See?](https://arxiv.org/abs/2607.03647)
- 2026년 iMIMIC workshop 논문은 MedGemma 계열을 포함해 attention/saliency와 patch occlusion의 불일치를 평가한다. ‘의료 VLM attention이 병변 근거와 다르다’는 관찰만으로는 차별성이 부족하다. [Attention Without Grounding](https://arxiv.org/abs/2607.18577)
- MedGround는 expert mask에서 검증된 referring grounding 데이터를 만들고 학습하는 방법이다. 2026-09-06 수정본이 있어 최신 본문 확인이 필요하다. [MedGround](https://arxiv.org/abs/2601.06847)

현재 논문 확인은 주로 공식 초록과 서지 수준이다. 본문·공개 코드·평가 split까지 검토하기 전에는 차별성을 확정하지 않는다.

## 다음에 파고들 질문
- CORAL, Attention Without Grounding, SECOND, MedGround의 본문과 공개 코드는 어떤 개입·학습 목적·대조군을 이미 다루는가? 근거 제거에 대한 민감성과 근거 보존 변화에 대한 불변성을 함께 개선하는 방향에 실제 공백이 있는가?
- VinDr, BraTS 및 공개 추가 후보에서 환자 식별자·병변 annotation·양성/음성·split·접근 조건이 확인되는 데이터 조합은 무엇인가? 정상 표본 부족과 미주석 병변을 고려해 어떤 질의를 정직하게 평가할 수 있는가?
- MedGemma 1.5 공식 모델 카드·노트북과 legacy 구현을 대조하면 prompt, 좌표, resizing/cropping, MRI orientation, yes/no scoring 중 무엇을 먼저 바로잡아야 하는가?
- 시각 근거 선택성, 3D 근거 선택, 해부구조→병변 전이 중 어느 방향이 선행 방법 대비 명확한 차이와 검증 가능한 신호를 동시에 갖는가? 이를 판별할 1시간 이내 소규모 실험의 조건·분모·중단 기준은 무엇인가?
