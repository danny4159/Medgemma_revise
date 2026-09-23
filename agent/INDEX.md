# Research Index


### 연구 목표 1 (iter_001부터): legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.

- iter_001 [CONTINUE] (deep/light/light) <기존 점수 집계와 근거 기반 해석: improve> 21행 요약과 문서 근거는 확인됐으며, 재사용 시 오류를 만드는 본문 생성 로직의 소규모 보완이 남았다. → 다음: 본문에도 누락·null 처리를 적용하고 저장 점수와 표본 수를 JSON에서 읽도록 수정한다. DeepLesion 문서 해석은 해당 과제에만 연결하고, 기본 입력 및 누락·null·최저 과제 변경 사례를 CPU에서 확인한다.
- iter_002 [DONE] (light/light/light) <기존 점수 집계와 근거 기반 해석: success> 💾f213214 GPU 실행 없이 점수 요약 스크립트를 완성했으며, DeepLesion bbox의 낮은 저장 점수와 문서에 기록된 평가 한계를 구분해 정리했다.

### 연구 목표 2 (iter_003부터): [최종 목표]

- iter_003 [CONTINUE] (deep/creative/deep) <3D 근거 보존 context 안정화: abandon> 294개 본실행 결과를 확인했으며, context 민감성은 관찰됐지만 paired 보정은 정확도와 안정성을 모두 악화시켰다. → 다음: 재사용할 파이프라인의 예산 축소·hash 검증 결함을 수정하고, 다음 후보인 질문 조건부 2D 근거 선택을 검토한다. unique-slice mean을 필수 baseline으로 두고 GT 없는 선택 규칙, 해부학적 confound 대조군, 독립 subject 평가 및 선행 방법과의 차별성을 갖춘 소규모 실험을 설계한다.
- iter_004 [CONTINUE] (deep/heavy/normal) <질문 조건부 2D 근거 선택: abandon> 1,680건 실험 완료를 확인했지만 contrastive 선택의 개선은 작고 위치 prior보다 낮았으며, 재사용 파이프라인의 검증 결함도 남아 있다. → 다음: 해부구조→병변 grounding 전이의 선행 방법·데이터·경량 학습 가능성을 비교하고 최소 반증 실험을 설계한다. 재사용할 코드에는 실제 입력 hash 재검증, verification 완료 강제, selection digest 연결 검증을 먼저 보완한다.
- iter_005 [CONTINUE] (deep/heavy/normal) <Grounding 데이터·측정 기반 구축: improve> NIH 160명 확보와 SCR 정답 노출 차단은 확인했지만, 준비 완료 판정과 QES 검증에 결함이 남아 있다. → 다음: NIH bbox 좌표 기준의 명시적 근거를 확보하고 readiness를 보강한다. QES verification 집합을 결정적으로 재생성해 대조하고 실패 시 이전 완료 산출물을 무효화한다. 이후 클래스별 target 정의를 확정해 pooling probe로 진행한다.

## 이전 목표들의 접근법 (참고용, 시도 횟수 제한에는 안 들어감)

- 기존 점수 집계와 근거 기반 해석 [approach/scores-summary]: 2회, 최근 판정: success, 커밋: f213214

## 접근법 기록 — 현재 목표 (같은 접근법 최대 3회)

- 3D 근거 보존 context 안정화 [approach/context-evidence-stability]: 1회 (iter_003), 최근 판정: abandon, 커밋: 없음
- 질문 조건부 2D 근거 선택 [approach/question-evidence-selection]: 1회 (iter_004), 최근 판정: abandon, 커밋: 없음
- Grounding 데이터·측정 기반 구축 [approach/grounding-data-audit]: 1회 (iter_005), 최근 판정: improve, 커밋: 없음

현재 연구 브랜치: approach/grounding-data-audit (코드 위치: /SSD1_1TB/home/milab/daniel/08_medgemma/research)

### 최근 계획의 대안 순위

1. Grounding 데이터·측정 기반 구축: 소량 데이터 확보·분할·좌표·캐시 검증을 먼저 완료해 후속 표현 분석의 실행 가능성을 확정한다.
2. Pooling 전후 frozen feature probe: 병변 데이터 요건 충족 후 동일 readout과 fine/coarse 평가로 공간 정보 접근성 차이를 검증한다.
3. 해부구조에서 병변으로 grounding 전이: 표현 분석과 데이터 확보 이후 동일 supervision·학습 예산의 직접 병변 학습과 anatomy 보조 학습을 비교한다.
