# Research Index


### 연구 목표 1 (iter_001부터): legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.

- iter_001 [CONTINUE] (deep/light/light) <기존 점수 집계와 근거 기반 해석: improve> 21행 요약과 문서 근거는 확인됐으며, 재사용 시 오류를 만드는 본문 생성 로직의 소규모 보완이 남았다. → 다음: 본문에도 누락·null 처리를 적용하고 저장 점수와 표본 수를 JSON에서 읽도록 수정한다. DeepLesion 문서 해석은 해당 과제에만 연결하고, 기본 입력 및 누락·null·최저 과제 변경 사례를 CPU에서 확인한다.
- iter_002 [DONE] (light/light/light) <기존 점수 집계와 근거 기반 해석: success> 💾f213214 GPU 실행 없이 점수 요약 스크립트를 완성했으며, DeepLesion bbox의 낮은 저장 점수와 문서에 기록된 평가 한계를 구분해 정리했다.

## 접근법 기록 — 현재 목표 (같은 접근법 최대 3회)

- 기존 점수 집계와 근거 기반 해석 [approach/scores-summary]: 2회 (iter_001, iter_002), 최근 판정: success, 커밋: f213214

현재 연구 브랜치: approach/scores-summary (코드 위치: /SSD1_1TB/home/milab/daniel/08_medgemma/research)

### 최근 계획의 대안 순위

1. 기존 점수 집계와 근거 기반 해석: 기존 스크립트의 본문 생성 결함을 수정하여 재사용 가능한 요약을 완성한다.
2. 원시 출력 재채점: 지정된 집계 범위를 넘어가며 현재 결함 해결에 필요하지 않다.
3. 문서 수동 요약: 구현은 간단하지만 재사용 가능한 JSON 요약 스크립트 요구를 충족하지 못한다.
