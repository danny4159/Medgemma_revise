# Research Index


### 연구 목표 1 (iter_001부터): legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.

- iter_001 [CONTINUE] (deep/light/light) <기존 점수 집계와 근거 기반 해석: improve> 21행 요약과 문서 근거는 확인됐으며, 재사용 시 오류를 만드는 본문 생성 로직의 소규모 보완이 남았다. → 다음: 본문에도 누락·null 처리를 적용하고 저장 점수와 표본 수를 JSON에서 읽도록 수정한다. DeepLesion 문서 해석은 해당 과제에만 연결하고, 기본 입력 및 누락·null·최저 과제 변경 사례를 CPU에서 확인한다.
- iter_002 [DONE] (light/light/light) <기존 점수 집계와 근거 기반 해석: success> 💾f213214 GPU 실행 없이 점수 요약 스크립트를 완성했으며, DeepLesion bbox의 낮은 저장 점수와 문서에 기록된 평가 한계를 구분해 정리했다.

### 연구 목표 2 (iter_003부터): [최종 목표]

- iter_003 [CONTINUE] (deep/creative/deep) <3D 근거 보존 context 안정화: abandon> 294개 본실행 결과를 확인했으며, context 민감성은 관찰됐지만 paired 보정은 정확도와 안정성을 모두 악화시켰다. → 다음: 재사용할 파이프라인의 예산 축소·hash 검증 결함을 수정하고, 다음 후보인 질문 조건부 2D 근거 선택을 검토한다. unique-slice mean을 필수 baseline으로 두고 GT 없는 선택 규칙, 해부학적 confound 대조군, 독립 subject 평가 및 선행 방법과의 차별성을 갖춘 소규모 실험을 설계한다.

## 이전 목표들의 접근법 (참고용, 시도 횟수 제한에는 안 들어감)

- 기존 점수 집계와 근거 기반 해석 [approach/scores-summary]: 2회, 최근 판정: success, 커밋: f213214

## 접근법 기록 — 현재 목표 (같은 접근법 최대 3회)

- 3D 근거 보존 context 안정화 [approach/context-evidence-stability]: 1회 (iter_003), 최근 판정: abandon, 커밋: 없음

현재 연구 브랜치: approach/context-evidence-stability (코드 위치: /SSD1_1TB/home/milab/daniel/08_medgemma/research)

### 최근 계획의 대안 순위

1. 3D 근거 보존 context 안정화: 로컬 volume으로 context 효과의 분리 가능성과 paired 보정의 개선 여지를 먼저 검증한다.
2. 질문 조건부 2D 근거 선택: 병변 근거와 해부학적 context를 구분하되 MMedPO·SECOND 등과의 차별성과 적절한 음성 label 확보가 필요하다.
3. 해부구조에서 병변으로 grounding 전이: localization adapter나 LoRA를 검토하되 정답 정의·데이터 확장·기존 grounding 방법 재현 부담이 더 크다.
