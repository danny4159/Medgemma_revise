# Current Understanding

현재 평가는 VQA, 흉부 X-ray 다중라벨 분류, 병변 위치 추정, 공식 형식의 3D CT/MR까지 포함합니다. 기존 로그가 지적한 3D 프롬프트 누출도 중요하지만, 더 넓은 결과와 실무 권고에 영향을 주는 최우선 문제는 **CheXpert 분류의 정답 구성과 AUC 추정 방식**입니다.

- 메타데이터는 `unlabeled`, `uncertain`, `absent`, `present`를 구분합니다: [fix_chexpert_meta.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/01_data/fix_chexpert_meta.py:14)
- 그러나 생성 응답 채점은 uncertain만 제외하고, present가 아닌 모든 라벨을 `no`로 처리합니다: [score_eval.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/02_eval/score_eval.py:219)
- 로그확률 평가도 같은 방식으로 `gt = int(label in present)`를 사용합니다: [remedy_logprob_classification.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/05_remedy/remedy_logprob_classification.py:73)

현재 10개 CheXpert 영상의 140개 image-label pair는 다음과 같습니다.

| 상태 | 개수 |
|---|---:|
| present | 16 |
| absent | 14 |
| uncertain | 7 |
| unlabeled | 103 |

따라서 보고된 133개 평가쌍의 음성 117개 중 103개, 즉 88%가 명시적 absent가 아니라 unlabeled입니다.

또한 서로 다른 14개 질문 라벨의 점수를 하나의 pooled AUC로 합쳤습니다. 이 경우 영상 판별력이 없어도 모델이 특정 라벨 질문에 더 높은 `yes` 점수를 주는 것만으로 AUC가 상승할 수 있습니다. 그럼에도 문서는 CheXpert AUC 0.700, p=0.0043을 “변별 신호가 실재한다”고 해석합니다: [MEDGEMMA_1.5_평가정리.txt](/SSD1_1TB/home/milab/daniel/08_medgemma/docs/MEDGEMMA_1.5_평가정리.txt:668)

기존 결과를 수정하지 않고 재계산한 예비 수치는 다음과 같습니다.

- 현재 방식 pooled AUC: 0.700
- 라벨별 평균 점수만 사용한 baseline AUC: 0.666
- 라벨별 AUC의 macro 평균: 0.588
- 라벨 내부에서만 정답을 순열한 검정: p≈0.064
- 명시적 present/absent만 남기면 30쌍이며, 양성과 음성이 모두 존재하는 라벨은 Pneumothorax 하나뿐입니다(1 positive, 2 negative).

즉, 현재 표본으로는 CheXpert의 영상 기반 분류 능력을 안정적으로 추정하기 어렵습니다.

# Hypothesis

**주가설:** 보고된 CheXpert AUC 0.700의 상당 부분은 영상과 정답의 대응이 아니라 다음 두 요인에서 발생한다.

1. `unlabeled → negative` 정책  
2. 서로 다른 질환 질문의 점수 offset을 합친 pooled AUC

따라서 라벨별 기저율을 보존하는 검정과 명시적 present/absent 분석에서는 “유의한 영상 변별 신호” 결론이 약화되거나 추정 불가능해질 것이다.

반대 결과는 여러 개별 라벨에서 AUC가 일관되게 0.5를 넘고, 영상 대응을 라벨 내부에서 섞었을 때 실제 AUC가 유의하게 높게 남는 경우입니다.

# Proposed Experiment

새 추론 없이 기존 [remedy_logprob.jsonl](/SSD1_1TB/home/milab/daniel/08_medgemma/eval_results/remedy_logprob.jsonl)만 재분석하는 **CheXpert estimand sensitivity audit**를 수행합니다.

세 가지 분석을 나란히 보고합니다.

| 분석 | 정답 정책 | 통계 단위 |
|---|---|---|
| A: 현재 방식 재현 | uncertain 제외, unlabeled=negative | 전체 pooled AUC |
| B: label-controlled | A와 동일 | 라벨별 AUC, macro AUC, 라벨 내부 순열검정 |
| C: explicit-only | present/absent만 사용 | 라벨별 AUC; 불가능하면 `not estimable` |

추가 대조군:

- 각 라벨의 다른 영상들에서 계산한 평균 점수를 사용하는 leave-one-image-out label-only baseline
- NIH 데이터에 동일한 label-controlled 분석 적용  
  - NIH 결과가 유지되고 CheXpert만 붕괴하면 분석법 자체가 무조건 보수적인 것이 아님을 확인할 수 있습니다.
- 불확실성은 133개 pair를 독립 표본으로 간주하지 말고, 10개 영상을 cluster 단위로 bootstrap합니다.

# Implementation Tasks for Claude

1. `scripts/03_diagnosis/audit_classification_estimand.py`를 추가한다.
2. CheXpert 메타데이터와 기존 로그확률 결과를 `(file, label)`로 결합한다.
3. 각 행에 `present/absent/uncertain/unlabeled` 상태를 명시적으로 부여한다.
4. 다음 개수를 assertion으로 검증한다.
   - present 16
   - absent 14
   - uncertain 7
   - unlabeled 103
5. 외부 의존성을 추가하지 않고 NumPy 기반 pairwise AUC를 구현한다.
6. 다음 결과를 출력한다.
   - 현재 pooled AUC 재현
   - 라벨별 `n_pos`, `n_neg`, AUC
   - evaluable label만의 macro AUC
   - leave-one-image-out label-only baseline
   - 라벨 내부 정답 순열검정 10,000회
   - image-cluster bootstrap 95% CI
7. explicit-only 분석에서 양성과 음성이 모두 없는 라벨은 0.5로 대체하지 말고 `not estimable`로 기록한다.
8. NIH에 같은 분석을 적용해 대조군 결과를 출력한다.
9. 결과는 `eval_results/diagnostics_classification_estimand.json`에 저장하되, 기존 점수·문서·추론 파일은 수정하지 않는다.
10. 이번 단계에서는 모델 재실행, 새 데이터 다운로드, 임계값 재최적화는 하지 않는다.

# Evaluation

가설을 지지하는 기준:

- pooled AUC 0.700은 재현되지만 label-controlled permutation p≥0.05 또는 cluster-bootstrap CI가 0.5를 포함한다.
- macro AUC가 pooled AUC보다 현저히 낮다.
- label-only baseline이 pooled AUC의 대부분을 설명한다.
- explicit-only 조건에서는 평가 가능한 라벨이 부족하여 CheXpert 성능이 `not estimable`로 판정된다.

가설을 반박하는 기준:

- 최소 2개 이상의 라벨에서 양성과 음성이 모두 충분히 존재하고,
- label-controlled macro AUC가 일관되게 0.5를 넘으며,
- 영상 단위 bootstrap CI와 순열검정이 모두 신호를 지지한다.

현재 예비 재계산은 가설을 지지하는 방향입니다. 따라서 감사 결과가 확정되면 CheXpert AUC 0.700을 “성공한 remedy” 또는 triage 근거로 사용해서는 안 됩니다. NIH 결과는 별도로 유지될 수 있습니다.

# Risks / Checks

- `unlabeled→negative`는 특정 CheXpert 평가 관행에서 선택 가능한 정책일 수 있습니다. 따라서 오류라고 단정하기보다 `U-zero` 정책으로 명시하고 explicit-only 결과와 함께 보고해야 합니다.
- explicit-only 30쌍은 라벨별 균형이 없어 pooled AUC 역시 해석하면 안 됩니다.
- 133개 image-label pair는 독립 표본 133개가 아닙니다. 유효 영상 수는 10개입니다.
- 같은 라벨 안에서 양성과 음성을 비교하지 않는 pooled AUC는 질환별 질문 편향을 영상 판별력으로 오인할 수 있습니다.
- 이후 확장이 필요하면 먼저 2–3개 질환을 정하고 각 질환별 positive/negative를 균형 있게 사전 선택해야 합니다. 현재처럼 “첫 10개 영상 × 모든 라벨”을 늘리는 방식은 피해야 합니다.
- 이번 검토에서는 실제 코드나 결과 파일을 수정하지 않았습니다.