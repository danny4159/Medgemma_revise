# 사고 라운드 1

### 확인한 기록과 코드
- `agent/GOAL.md`, `agent/INDEX.md`, `agent/runs/iter_003/review.md`, `claude_report.md`, 이전 사고 기록과 관련 코드를 읽었다. `context-evidence-stability`는 abandon이므로 다시 선택하지 않는다. 이번에는 파일 수정·생성·실험 실행을 하지 않았다.
- 직전 리뷰에서 검증한 결과는 concat BA 0.964, paired BA 0.917, unique-slice mean BA 0.988이다. paired의 drift도 4.491→4.620으로 악화됐다. 이는 가산 보정을 중단할 근거이며, 모든 근거 선택 방법의 실패를 뜻하지 않는다.
- `research/run_context_pilot.py`에서 순회 중 `todo` 재할당으로 예산 축소가 적용되지 않는 결함과 정상 종료 때만 budget을 저장하는 구조를 확인했다. `research/analyze_context_pilot.py`는 version/status만 확인하고 ID별 마지막 결과를 채택한다. 재사용 전에 실제 PNG·요청·config hash 검증과 미완료 판정을 보완해야 한다.

### 데이터가 만드는 설계 제약
- `hf_cache` 파일 목록에서 확인한 BraTS 원본 volume은 기존 개발 case인 00000·00002·00005뿐이다. 원본 volume의 독립 holdout이 로컬에 있다고 가정하면 안 된다.
- `legacy/eval_samples/not_in_training/brats2023/meta.json`에는 10개 2D 영상과 mask가 있다. 00008-000과 00008-001을 같은 subject로 보수적으로 묶으면 총 9개 subject 그룹이며, 기존 volume 3개를 제외하면 최대 6개 추가 그룹이다. 그러나 이 영상들도 legacy 평가에 사용됐으므로 완전히 미노출된 최종 test set은 아니다.
- 이 10개 영상은 `download_brats_samples.py`에서 GT 종양 면적이 최대인 slice를 추출한 자료다. 종양이 없는 영상의 평가나 GT 없는 slice 탐색 성능을 증명할 수 없다. 다만 동일 slice 내 공간적 근거 선택의 개발용 자료로는 검토할 수 있다.
- 기존 E/N 구성은 종양 영역과 다른 해부학적 높이의 annotation-empty slice를 비교한다. 따라서 종양 근거와 뇌 면적·해부 수준의 효과가 섞여 있다. 같은 slice의 비병변 영역도 임상적으로 정상이라는 보장은 없고, crop·삭제는 별도의 분포 변화를 만든다.
- MRI-GBM-MET의 README를 다시 열었으나 웹 도구 오류로 내용을 확보하지 못했다. 이전 기록의 90 subject 설명을 이번에 재검증한 사실로 취급하지 않으며, license·subject 대응·mask·split은 여전히 미확인이다.

### 선행 방법과의 경계
- SECOND는 attention에 따른 multi-scale patch 선택과 단계별 contrastive decoding을 이미 결합한다. 따라서 질문 관련 영역을 선택하고 crop 점수를 대비하는 것만으로 신규성을 주장할 수 없다. 이번에 본문 §3–4를 확인했다. [SECOND 논문](https://arxiv.org/html/2506.08391v1)
- MMedPO는 병변 영역 noising으로 시각적 근거 누락을 유도하고 clinical relevance를 반영한 preference optimization을 제안한다. 제거 민감도나 병변 기반 학습 자체도 기존 방법과 구분해야 한다. [MMedPO 논문](https://arxiv.org/abs/2412.06141)
- MedPruner v2는 pixel L1 기반 slice filtering과 vision encoder self-attention 기반 token 선택을 결합한다. 본문의 이 선택 규칙은 질문별 답변 근거를 직접 검증하는 규칙과는 다르다. 그러나 이것만으로 우리 방법의 신규성이 확보되는 것은 아니다. [MedPruner v2 §2](https://arxiv.org/html/2603.11625v2)

### 이번 라운드의 판단
우선 해결할 문제는 선택 알고리즘 구현보다 평가의 식별 가능성이다. 질문에 맞는 근거를 골랐는지, 단지 Yes 점수가 높은 입력을 골랐는지 구분할 설계가 필요하다. 기존 단일 질문·양성 중심 자료만으로는 질문 조건부 선택의 이점을 검증하기 어렵다. 다음 라운드는 데이터와 선택 규칙을 함께 좁히는 데 사용한다.

## 다음에 파고들 질문
- 추가 다운로드 없이 가능한 2D 자료 중 동일 영상에 서로 다른 질문과 신뢰할 수 있는 양성·음성 label을 연결할 수 있는 것은 무엇인가? VinDr 원본 annotation과 subject 정보를 확인하고, 미주석 소견을 음성으로 간주하지 않는 평가 단위를 정할 수 있는가?
- GT 없이 후보 영역을 만들고 근거의 충분성·제거 민감도로 선택하는 규칙은 SECOND 및 기존 counterfactual visual grounding·선택 방법과 정확히 어디서 다른가? 단순 confidence 선택과 구별되는 최소 수식과 반증 가능한 예측을 정할 수 있는가?
- 같은 해부학적 위치·면적의 대조군과 질문 교환 대조군을 구성할 수 있는가? crop 또는 삭제의 분포 변화와 동일 점수로 선택·평가하는 순환성을 어떻게 분리할 것인가?
- 독립 subject 확보와 음성 label 검증이 이번 범위에서 어렵다면, 로컬 자료로 수행할 타당한 기전 pilot의 범위는 어디까지인가? 필요한 최소 추가 데이터의 출처·사용 조건·크기와 GPU 요청 수를 확인해 구현 여부를 결정할 수 있는가?
