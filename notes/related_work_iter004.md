# iter_004 관련 연구 노트 (question-conditioned evidence selection)

이 노트는 GPT 계획(`agent/runs/iter_004/plan.md`)의 조사 내용을 옮긴 것이다. 이번 실행에서 원문을 다시 열어 검증하지는 않았다.

## 이번 pilot의 C 점수와 대수적 동치

- `m(I,q) = log P(Yes|I,q) − log P(No|I,q)`
- `D(q,R,t) = m(I,q) − m(T_t(I,R),q)` (영역 R을 변형 t로 제거했을 때 margin 감소)
- `C(q,R,t) = D(q,R,t) − mean_{q'≠q} D(q',R,t)`

contrastive score `F_q(I) = m(I,q) − mean_{q'≠q} m(I,q')`를 정의하면
`F_q(I) − F_q(T_t(I,R)) = C(q,R,t)`이다. 즉 C는 "질문 q 대 나머지 질문 평균" contrastive score의 occlusion
attribution과 정확히 같다 (`test_qes.py`에서 수치로 확인). 또한 각 R에서 `sum_q C(q,R,t) = 0`이므로,
여러 질문이 실제로 같은 영역을 근거로 쓰면 그 공유 근거는 억제될 수 있다.

## 선행 연구와의 관계 (새 방법으로 주장하지 않음)

- **SECOND** ([arXiv 2506.08391](https://arxiv.org/html/2506.08391v1)): attention 기반 patch 선택과 contrastive decoding을 결합한다. 질문별 영역 선택 자체는 새롭지 않다.
- **CSGR** ([arXiv 2609.13228](https://arxiv.org/html/2609.13228v1)): perturbation에 대한 **gold answer** confidence 반응으로 영역을 선택한다. gold answer를 알아야 하므로 추론 시 label-free가 아니다. 이번 selector는 정답과 무관하게 항상 "Yes" 대 "No" margin을 쓰며 annotation·정답을 받지 않는다.
- **CASE** ([arXiv 2506.07327 v4](https://arxiv.org/html/2506.07327v4)): 다른 class들의 평균 gradient 방향을 제거해 class-specific attribution을 만든다. "다른 class 공통 성분 제거"라는 발상은 C와 같다. 차이는 CASE가 gradient 공간의 projection을 쓰고, C는 질문별 finite-difference(occlusion) 차의 평균을 뺀다는 점이다. 이 차이를 contribution으로 주장하지 않는다.

## 이번 구현의 범위

- raw occlusion(`argmax D`), crop confidence(`argmax m(crop)`), uniform, 위치 prior는 단순 baseline이다. SECOND·CSGR·CASE의 완전 재현이 아니다.
- 로컬 VinDr 10영상은 legacy 평가에 이미 사용된 개발 자료다. 환자 일반화, specificity, 진단 개선은 주장하지 않는다.
- CheXlocalize는 계정 등록·약관 동의가 필요해 이번에는 취득하지 않았다 ([다운로드 안내](https://raw.githubusercontent.com/rajpurkarlab/cheXlocalize/master/download_instructions.md)).
