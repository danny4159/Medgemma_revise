# Research Index


### 연구 목표 1 (iter_001부터): legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.

- iter_001 [CONTINUE] (deep/light/light) <기존 점수 집계와 근거 기반 해석: improve> 21행 요약과 문서 근거는 확인됐으며, 재사용 시 오류를 만드는 본문 생성 로직의 소규모 보완이 남았다. → 다음: 본문에도 누락·null 처리를 적용하고 저장 점수와 표본 수를 JSON에서 읽도록 수정한다. DeepLesion 문서 해석은 해당 과제에만 연결하고, 기본 입력 및 누락·null·최저 과제 변경 사례를 CPU에서 확인한다.
- iter_002 [DONE] (light/light/light) <기존 점수 집계와 근거 기반 해석: success> 💾f213214 GPU 실행 없이 점수 요약 스크립트를 완성했으며, DeepLesion bbox의 낮은 저장 점수와 문서에 기록된 평가 한계를 구분해 정리했다.

### 연구 목표 2 (iter_003부터): [최종 목표]

- iter_003 [CONTINUE] (deep/creative/deep) <3D 근거 보존 context 안정화: abandon> 294개 본실행 결과를 확인했으며, context 민감성은 관찰됐지만 paired 보정은 정확도와 안정성을 모두 악화시켰다. → 다음: 재사용할 파이프라인의 예산 축소·hash 검증 결함을 수정하고, 다음 후보인 질문 조건부 2D 근거 선택을 검토한다. unique-slice mean을 필수 baseline으로 두고 GT 없는 선택 규칙, 해부학적 confound 대조군, 독립 subject 평가 및 선행 방법과의 차별성을 갖춘 소규모 실험을 설계한다.
- iter_004 [CONTINUE] (deep/heavy/normal) <질문 조건부 2D 근거 선택: abandon> 1,680건 실험 완료를 확인했지만 contrastive 선택의 개선은 작고 위치 prior보다 낮았으며, 재사용 파이프라인의 검증 결함도 남아 있다. → 다음: 해부구조→병변 grounding 전이의 선행 방법·데이터·경량 학습 가능성을 비교하고 최소 반증 실험을 설계한다. 재사용할 코드에는 실제 입력 hash 재검증, verification 완료 강제, selection digest 연결 검증을 먼저 보완한다.
- iter_005 [CONTINUE] (deep/heavy/normal) <Grounding 데이터·측정 기반 구축: improve> NIH 160명 확보와 SCR 정답 노출 차단은 확인했지만, 준비 완료 판정과 QES 검증에 결함이 남아 있다. → 다음: NIH bbox 좌표 기준의 명시적 근거를 확보하고 readiness를 보강한다. QES verification 집합을 결정적으로 재생성해 대조하고 실패 시 이전 완료 산출물을 무효화한다. 이후 클래스별 target 정의를 확정해 pooling probe로 진행한다.
- iter_006 [CONTINUE] (normal/heavy/normal) <Grounding 데이터·측정 기반 구축: success> 💾68117cf CPU 검사 184건 통과와 NIH 160명 자료 보존을 확인했으며, 측정 기반은 보완됐지만 좌표 canvas 근거 부족으로 GPU probe는 아직 진입 불가다. → 다음: 공식 NIH README·FAQ·bbox 파일을 제한된 소량 조회로 확인해 canvas 및 미러 차이를 정리한다. 이어 RGBA 전처리와 probe 학습·평가 규약을 확정하고, 좌표 gate가 해결되면 train 소표본으로 추출 비용을 측정한 뒤 pooling 전후 frozen feature probe를 수행한다.
- iter_007 [CONTINUE] (normal/heavy/normal) <Pooling 전후 frozen feature probe: abandon> 24개 학습의 실제 실행과 원시 결과를 확인했으며, pooling 전후 MLP 차이 +0.000304는 사전 투자 기준을 충족하지 못했다. → 다음: 재사용 코드의 완료 판정·provenance 검증·GPU 가시성 처리를 보완하고, 남은 anatomy→lesion grounding 전이를 우선 검토한다. 직접 병변 학습 대비 전이 이득을 반증할 최소 실험과 독립 평가 자료를 설계하며, decoder 병목은 별도 미검증 후보로 비교한다.

## 이전 목표들의 접근법 (참고용, 시도 횟수 제한에는 안 들어감)

- 기존 점수 집계와 근거 기반 해석 [approach/scores-summary]: 2회, 최근 판정: success, 커밋: f213214

## 접근법 기록 — 현재 목표 (같은 접근법 최대 3회)

- 3D 근거 보존 context 안정화 [approach/context-evidence-stability]: 1회 (iter_003), 최근 판정: abandon, 커밋: 없음
- 질문 조건부 2D 근거 선택 [approach/question-evidence-selection]: 1회 (iter_004), 최근 판정: abandon, 커밋: 없음
- Grounding 데이터·측정 기반 구축 [approach/grounding-data-audit]: 2회 (iter_005, iter_006), 최근 판정: success, 커밋: 68117cf
- Pooling 전후 frozen feature probe [approach/pooling-feature-probe]: 1회 (iter_007), 최근 판정: abandon, 커밋: 없음

현재 연구 브랜치: approach/pooling-feature-probe (코드 위치: /SSD1_1TB/home/milab/daniel/08_medgemma/research)

### 최근 계획의 대안 순위

1. Pooling 전후 frozen feature probe: 동일 coarse loss와 readout으로 pooling 전후 공간 정보 접근성을 비교한다.
2. 해부구조에서 병변으로 grounding 전이: 윤곽선 없는 anatomy 입력을 확보한 뒤 직접 병변 학습과 비교한다.
3. 독립 grounding 데이터에서 재검증: NIH 좌표 가정에 모순이 발견되면 좌표 정의가 명확한 자료로 측정 대상을 바꾼다.
