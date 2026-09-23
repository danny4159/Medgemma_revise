# Work Performed
`research/summarize_scores.py`의 `report()`를 계획대로 수정했다.
- 유효한 숫자 `mean_iou`(0 포함, bool·NaN·null·누락 제외)만 bbox 후보로 쓴다.
- 후보가 0개면 "선정 불가", 1개면 "비교 대상 부족"으로 표시한다. 후보 수는 실제 후보 수에서 계산한다.
- 본문의 `n`, `n_parsed`, `iou@`, 기준선은 `f()`로 표시하고 누락·null은 N/A로 나온다.
- 기준선은 값과 차이(`+0.0020`)를 중립적으로 표시한다. 기존의 "사실상 가깝다" 문구는 제거했다.
- DeepLesion 전용 docs 해석은 `deeplesion_ct`가 최저일 때만 붙인다. 다른 과제가 최저이면 "원인을 docs 근거로 확인하지 않았다, 기여도 미검증"이라고만 쓴다.
- 별도 재평가의 약 0.007(n=20)은 docs 인용으로 두고, 현재 JSON 값과 구분해 적었다.
- 공통 설명에 n의 단위가 QA·image-label 질의·영상으로 다르며 합산하지 않는다고 명시했다.

# Files Changed
- `research/summarize_scores.py`
- `research/results/scores_summary.md`(재생성)

# Commands / Experiments
- `python -c` 회귀 검증(메모리에서 JSON 변형): 성공.
- 기본 보고서 재생성: `python research/summarize_scores.py --output research/results/scores_summary.md`(성공, 정상 종료).
- GPU 실행, 모델 로딩, 패키지 설치는 하지 않았다.
- 첫 회귀 실행에서 데이터셋 이름을 잘못 써서(`brats_mri`) KeyError가 났다. 테스트 코드의 오타였고, 이름을 `brats2023`으로 고쳐 다시 실행했다.

# Results
- 기본 입력: G1 3행, G2 6행, G3 12행으로 표는 총 21행이다. 최저 과제는 DeepLesion bbox `mean_iou`=0.0061, `n_parsed`=10/10이고 다른 두 데이터셋은 brats2023 0.1084, vindr_cxr 0.1276이다. 유효 후보는 3개다.
- 누락·null: `mean_iou`, `n`, `n_parsed`, `iou@0.3`, `iou@0.5`, `whole_image_baseline_iou`를 각각 삭제하거나 null로 바꿨다. 모두 예외 없이 처리됐다. `mean_iou`가 결측이면 후보에서 빠져 최저가 brats2023으로 바뀐다.
- 후보 부족: 모든 `mean_iou`가 null이거나 bbox가 없으면 "선정 불가"가 나온다. 후보가 하나뿐이면 "다른 과제보다 낮다고 판단할 수 없다"로 나온다.
- 0값: `mean_iou`=0을 넣으면 결측이 아닌 유효값으로 처리되어 0.0000으로 표시된다.
- 수치 변경: DeepLesion을 0.02, n=7, n_parsed=5로 바꾸면 보고서에 0.0061과 n=10이 사라지고 0.0200이 나온다.
- 최저 과제 변경: brats2023이나 vindr_cxr을 최저로 바꾸면 제목과 비교 수치가 바뀐다. CT 설명과 0.007 인용은 붙지 않는다.
- 결과 파일: `research/results/scores_summary.md`

# Problems
- 회귀 검증은 일회성 `python -c`로 했고 파일로 남기지 않았다(임시 스크립트 금지 규칙).
- 누락·null 처리는 기존 JSON 구조 안의 필드에 한정했다. `scores["G3"]` 같은 상위 키가 통째로 없는 경우는 다루지 않았다(계획 범위 밖).

# Recommendation to GPT
검증 기준을 모두 통과했으므로 목표 완료로 제안한다. 추가 개선이 필요하면 회귀 케이스를 `research/`의 테스트 파일로 남기는 것을 고려할 수 있다.

SELF_CHECK: PASS
SUMMARY: report()의 누락·null·후보 부족·최저 과제 변경 처리를 보완하고 회귀 사례를 모두 통과했다. DeepLesion bbox 0.0061이 최저이며 보고서를 재생성했다.