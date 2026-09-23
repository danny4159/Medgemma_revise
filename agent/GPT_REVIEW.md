# Assessment

판정은 **“부분 검증, 기존 결론은 기각 또는 최소한 보류”**입니다.

Claude Code의 원래 보고만 놓고 보면 스크립트를 실행하지 않았으므로 가설을 실제로 검증하지 못했습니다. 다만 이번 검토에서 직접 실행한 결과 모든 assertion이 통과했고, [결과 JSON](/SSD1_1TB/home/milab/daniel/08_medgemma/eval_results/diagnostics_classification_estimand.json)이 생성됐습니다.

실행 결과는 다음을 지지합니다.

- CheXpert pooled AUC 0.700과 기존 p=0.0043은 재현된다.
- 그러나 label-controlled 분석에서는 통계적 근거가 사라진다.
- 따라서 “CheXpert에 영상 기반 변별 신호가 확실히 존재한다”는 기존 결론은 지지되지 않는다.

다만 `unlabeled→negative`가 AUC를 얼마나 부풀렸는지는 검증되지 않았습니다. Explicit-only 표본이 너무 희소해 비교 자체가 불가능하기 때문입니다. 즉 가설의 “label offset” 부분은 지지되지만, “unlabeled 정책의 인과적 영향”은 확인되지 않았습니다.

# Key Findings

| 분석 | CheXpert | NIH |
|---|---:|---:|
| Pooled AUC | 0.700 | 0.673 |
| 기존 global permutation p | 0.0043 | 0.0206 |
| Macro AUC | 0.588, 6 labels | 0.733, 5 labels |
| Within-label macro p | 0.1970 | 0.0306 |
| Within-label pooled p | 0.0629 | 0.0001 |
| Label-only baseline AUC | 0.659 | 0.477 |
| Macro bootstrap 95% CI | [0.444, 0.866] | [0.639, 1.000] |

주요 해석은 다음과 같습니다.

- CheXpert within-label permutation 귀무분포의 평균 자체가 0.637입니다. 즉 질문 라벨별 점수·유병률 차이만으로 pooled AUC가 상당히 높아질 수 있습니다.
- 모든 영상을 사용한 순수 label-mean baseline도 AUC 0.666입니다. 다만 AUC 차이를 “몇 %가 설명됐다”처럼 선형 분해해서는 안 됩니다.
- Explicit-only에서는 Pneumothorax만 계산 가능하며 표본은 1 positive / 2 negative, AUC 0.0입니다. CheXpert 전체 성능은 추정 불가능합니다.
- CheXpert macro AUC 0.588도 `No Finding` AUC 0.920의 영향을 크게 받습니다. 이를 제외하면 disease-only macro AUC는 0.521, 탐색적 within-label p≈0.44입니다.
- NIH에서는 label-controlled 신호가 유지됩니다. 따라서 분석법이 무조건 보수적인 것은 아닙니다. 그러나 NIH 표본 자체가 10장 중 7장이 Hernia여서 일반화 가능한 대조군은 아닙니다.

# Problems / Concerns

1. **표본 추출과 독립성 문제가 가장 큽니다.**

   CheXpert와 NIH 모두 community mirror의 `train` split에서 스트리밍 순서상 첫 10장을 가져옵니다: [download_eval_samples.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/01_data/download_eval_samples.py:96). 무작위 표본이 아닙니다.

   CheXpert에는 동일 연령·성별·라벨을 가진 frontal/lateral 영상 쌍이 보여 동일 환자 또는 연구일 가능성이 큽니다. 그런데 원래 patient/study ID를 버리고 `00.jpg` 형식으로 바꿔 저장했기 때문에 확인하거나 patient-level clustering을 할 수 없습니다. 따라서 “10개 독립 영상”을 전제로 한 bootstrap도 낙관적일 수 있습니다.

2. **Permutation test가 영상 단위 의존성을 보존하지 않습니다.**

   [현재 구현](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/03_diagnosis/audit_classification_estimand.py:107)은 각 라벨의 정답을 서로 독립적으로 섞습니다. 이는 라벨별 유병률은 보존하지만, 한 영상 안의 질환 공존 구조와 예측점수 상관을 파괴합니다.

   더 적절한 검정은 환자 단위로 전체 라벨 벡터와 점수 벡터의 대응을 함께 섞는 synchronized cluster permutation입니다. 현재 결과가 비유의라는 방향은 설득력 있지만 p-value 자체를 확정값으로 취급하면 안 됩니다.

3. **Bootstrap macro AUC의 estimand가 반복마다 달라집니다.**

   재표집할 때마다 양성과 음성이 모두 남은 라벨만 평균하므로 bootstrap replicate별로 서로 다른 라벨 집합을 측정합니다: [audit script](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/03_diagnosis/audit_classification_estimand.py:138). 표본도 10개 cluster뿐이라 percentile CI의 안정성이 낮습니다.

4. **Explicit-only는 더 좋은 gold standard가 아닙니다.**

   현재 데이터는 radiologist image annotation이 아니라 `train` 보고서에서 자동 추출된 라벨입니다. `absent`는 보고서에 명시적으로 부정된 경우이고, `unlabeled`는 언급되지 않은 경우입니다. Explicit-only는 특이도가 높을 수 있지만 심한 선택 편향을 가집니다.

   따라서 이를 “정답 분석”으로, blank-as-negative를 “오류”로 표현하면 과장입니다. 또한 현재 방식은 uncertain을 제외하므로 일반적으로 uncertain을 0으로 바꾸는 “U-zero”와도 다릅니다. 정확한 명칭은 `unmentioned-as-negative + uncertain-ignore`가 낫습니다. 공식 CheXpert 평가에서는 별도의 radiologist-consensus validation/test set을 사용합니다. [CheXpert 원 논문](https://arxiv.org/abs/1901.07031)

5. **Pooled AUC는 triage metric으로 부적절합니다.**

   서로 다른 질환 질문의 점수는 동일한 척도로 보정되어 있지 않습니다. 실제 triage는 일반적으로 특정 질환 내에서 환자를 순위화하므로 per-label AUC 또는 사전에 고정한 macro AUC가 맞습니다. `No Finding`, 질환, `Support Devices`를 하나의 순위로 합치는 현재 pooled AUC는 임상적 의미가 불명확합니다.

6. **LOIO label-only baseline 구현이 순수 label-only 점수가 아닙니다.**

   [구현](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/03_diagnosis/audit_classification_estimand.py:67)은 현재 행의 점수를 평균에서 제외합니다. 이 때문에 같은 라벨 안에서도 baseline이 현재 점수와 반대 방향으로 변합니다. 순수한 기술적 label-offset baseline이라면 라벨별 전체 평균을 모든 행에 동일하게 부여해야 합니다. 그 값은 0.666입니다. 확증적 baseline은 별도 calibration set에서 추정해야 합니다.

7. **`No Finding`이 결과를 크게 좌우합니다.**

   `No Finding`은 다른 병변들과 논리적으로 상보적이며 가장 높은 AUC를 보입니다. 이를 질환별 macro에 동일 가중으로 넣으면 영상의 정상/비정상 구분 능력을 병변별 식별 능력으로 오인할 수 있습니다.

8. **직접적인 answer leakage는 보이지 않지만 contamination은 배제되지 않았습니다.**

   프롬프트에는 질환명만 들어가며 정답 자체는 들어가지 않습니다. 반면 `not_in_training` 디렉터리명만으로 모델과 데이터의 비중복을 보장할 수는 없습니다. MedGemma 모델 카드도 공개 의료 데이터 평가에서 사전학습 contamination 위험을 명시적으로 경고합니다. 특히 ChestX-ray14는 모델 카드 데이터 항목에도 등장합니다. [MedGemma 1.5 모델 카드](https://developers.google.cn/health-ai-developer-foundations/medgemma/model-card)

9. **로그확률 계산도 검증이 필요합니다.**

   원래 추론 코드는 `"Yes"`, `"yes"`, `" Yes"` 각각의 토큰화 결과에서 첫 토큰만 사용하고 `logsumexp`합니다: [remedy_logprob_classification.py](/SSD1_1TB/home/milab/daniel/08_medgemma/scripts/05_remedy/remedy_logprob_classification.py:51). 다중 토큰 표현이거나 동일 토큰 ID가 중복되면 확률을 잘못 합산할 수 있습니다. tokenizer별 single-token 여부와 ID 중복 assertion이 필요합니다.

10. **사후 분석입니다.**

    현재 문제와 분석법은 이미 AUC 0.700을 본 뒤 선택됐습니다. 감사 목적에는 유효하지만 새 p-value를 확증적 발견으로 취급해서는 안 됩니다. 기존에 여러 remedy를 시도한 다중성도 반영되지 않았습니다.

# Interpretation

현재 결과가 의미 있는 이유는 **성능을 입증해서가 아니라 기존 성능 주장의 estimand가 잘못되었음을 보여주기 때문**입니다.

정당한 결론은 다음과 같습니다.

- CheXpert pooled AUC 0.700은 재현 가능한 기술 통계다.
- 그러나 그 수치가 질환별 영상 판별 능력을 나타낸다는 근거는 부족하다.
- 현재 표본으로는 CheXpert의 영상 기반 분류 성능이 있는지 없는지 판단할 수 없다.
- 비유의 결과는 “신호가 없다”는 증명이 아니라 “유효 표본이 너무 적어 입증하지 못했다”는 뜻이다.
- 따라서 기존 문서의 “성공”, “견고한 성과”, “triage 도구로 사용” 표현은 철회하거나 `exploratory pooled result; not estimable per condition`으로 낮춰야 한다.
- NIH 결과는 이 10장 안에서는 고무적이지만, 편향된 표본과 contamination 가능성 때문에 외부 성능 근거로 사용할 수 없다.

# Recommended Next Experiment

가장 작은 확증 실험은 **2–3개 질환에 대한 patient-disjoint, explicit-reference 평가**입니다.

1. 공식 CheXpert radiologist-annotated validation set에서 Cardiomegaly, Edema, Pleural Effusion 등 2–3개 질환을 사전 지정합니다.
2. 질환마다 최소 30 positive / 30 negative를 무작위 추출하고, 환자당 한 study만 사용합니다. 예산이 작다면 20/20은 pilot으로만 표시합니다.
3. patient ID, study ID, view를 보존합니다. 가능하면 frontal 영상으로 제한합니다.
4. 정답과 무관하게 선택된 모든 이미지–라벨 쌍을 추론해 missingness가 정답에 의존하지 않게 합니다.
5. 1차 endpoint는 질환별 AUROC와 AUPRC로 고정합니다. Pooled AUC는 계산하지 않습니다.
6. 고정된 라벨 집합의 macro AUC, patient-cluster bootstrap CI, synchronized patient-level permutation을 사용합니다.
7. 영상 신호를 직접 검증하기 위해 동일 라벨 안에서 correct-image 점수와 patient-shuffled-image 점수를 비교합니다. Text-only 또는 blank-image 점수는 질문 prior 대조군으로 추가할 수 있습니다.
8. `present/absent` radiologist reference를 primary로 하고, unmentioned/uncertain 정책은 별도 sensitivity analysis로 둡니다.
9. tokenizer에서 `Yes`/`No` 완성문의 전체 sequence log-likelihood를 계산하거나, single-token·unique-ID임을 assertion으로 검증합니다.
10. 분석 코드와 임계값을 잠근 뒤 현재 10장과 겹치지 않는 untouched 표본에서 한 번만 실행합니다.

현재 10장에 통계 기법만 더 적용하는 것은 한계가 있습니다. 다음 자원은 재분석보다 **환자 독립적이고 라벨별 균형이 잡힌 확증 표본 확보**에 쓰는 것이 맞습니다.