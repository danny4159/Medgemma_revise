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
- iter_008 [사용자 보완으로 전환 → iter_009] 기존 기록 보존, 성공·실패 판정 아님 (Claude 구현)
- iter_009 [CONTINUE] (deep/standard/normal) <정상 사용 조건의 병변 grounding 검증: success> 💾39aa49a6fa5943ca0d3e0327a7874e68a2c878cb 독립 평가 양성 200명 중 공통 위치 불일치 134명(67.0%)을 재확인해 RSNA 조건의 한계를 validated로 갱신한다. 실행기 재사용 결함과 방법론 효과 검증은 후속 과제로 남는다. → 다음: 검증된 lesion-grounding-generalization에 연결되는 방법 후보를 선행 방법·오류 분포·두 GPU 실행 가능성으로 비교해 하나를 선택한다. 직접 병변 LoRA/adapter와 강한 단순 baseline을 포함하고, 현재 평가 300명은 개발 자료로 전환한다. 새 환자 분할 및 추가 데이터셋의 확인 계획을 고정한 뒤, 필요한 재사용 결함만 보완하고 development에서 batch 확대 또는 GPU당 복수 worker의 처리량·peak VRAM·출력 정합성을 측정해 본실험으로 진행한다. anatomy 전이를 자동 선택하지 않는다.
- iter_010 [CONTINUE] (deep/standard/normal) <영상 조건부 집합 grounding: execution_failed> 💾5581ed255a350e42a0ad422065edf13c56a33bf6 LoRA 학습 경로와 4 worker 처리량 개선은 확인했지만 본학습·독립 평가는 미완료이며, 실행 복구와 평가 검증 보완 후 원 계획을 이어가야 한다. → 다음: 먼저 실행 호스트에서 기존 학습·추론·대기 프로세스와 소유 lock, checkpoint, 종료 코드를 확인한다. 살아 있는 작업은 중복 실행하지 않는다. 원본 결과를 보존하면서 epoch validation 복구, 학습 run lock, 입력·선택 ID provenance, 최종 평가의 완전성·seed 검사를 보완하고 필요한 중단·재개 검사를 수행한다. protocol 변경과 기존 결과의 호환 범위를 명시적으로 연결한다. 안전한 GPU 배치에서 iter_010의 기존 학습량·매 epoch validation·확장 규칙·3개 seed·확인 800명 계획을 유지해 완료하고 실제 비교 결과를 보고한다. iter_011 이후 규모 기준을 이 미완료 실험의 축소 근거로 소급 적용하지 않는다.
- iter_011 [CONTINUE] (normal/standard/normal) <영상 조건부 집합 grounding: execution_failed> 💾8b030717b813bcbff85a2ffc5f52c9561a73f452 복구 기능과 epoch 1 실제 생성 결과는 확인했지만 재개 검사 5건 실패와 본실험 미완료로 가설 판정을 보류한다. 보고서의 LR별 점수도 서로 뒤바뀌어 정정이 필요하다. → 다음: 실행 호스트에서 기존 train·launcher·pipeline의 PID/starttime·lock·checkpoint·종료 상태를 먼저 확인해 중복 실행을 막는다. 원본을 보존하며 재개 수치 실패를 통제 실험으로 분리하고, 실제 중간-step 재개 및 선택 provenance·pipeline 소유권·completion 처리를 보완한다. 변경 전후 protocol과 기존 산출물 호환 범위를 기록한 뒤, 영향받지 않은 결과를 재사용해 원래 두 LR 5→8 epoch 규칙, 매 epoch validation 400명, seed17/29/43, confirm 800명 계획을 완료한다. 확인 평가 전에 수정된 4 worker 생성 경로의 정합성과 메모리를 검사하고 모든 자식 종료 코드를 수집한다.

## 이전 목표들의 접근법 (참고용, 현재 목표의 재평가 횟수에는 안 들어감)

- 기존 점수 집계와 근거 기반 해석 [approach/scores-summary]: 2회, 최근 판정: success, 커밋: f213214

## 접근법 기록 — 현재 목표 (유효한 실험 3회부터 방향 재평가)

- 3D 근거 보존 context 안정화 [approach/context-evidence-stability]: 1회 (iter_003), 유효한 실험 0회, 미분류 1회, 최근 판정: abandon, 커밋: 없음
- 질문 조건부 2D 근거 선택 [approach/question-evidence-selection]: 1회 (iter_004), 유효한 실험 0회, 미분류 1회, 최근 판정: abandon, 커밋: 없음
- Grounding 데이터·측정 기반 구축 [approach/grounding-data-audit]: 2회 (iter_005, iter_006), 유효한 실험 0회, 미분류 2회, 최근 판정: success, 커밋: 68117cf
- Pooling 전후 frozen feature probe [approach/pooling-feature-probe]: 1회 (iter_007), 유효한 실험 0회, 미분류 1회, 최근 판정: abandon, 커밋: 없음
- 해부구조에서 병변으로 grounding 전이 [approach/anatomy-lesion-transfer]: 1회 (iter_008), 유효한 실험 0회, 미분류 0회, 최근 판정: 사용자 보완으로 전환 (검증 미완료), 커밋: 없음
- 정상 사용 조건의 병변 grounding 검증 [approach/grounding-usage-diagnostic]: 1회 (iter_009), 유효한 실험 1회, 미분류 0회, 최근 판정: success, 커밋: 39aa49a6fa5943ca0d3e0327a7874e68a2c878cb
- 영상 조건부 집합 grounding [approach/conditional-set-grounding]: 2회 (iter_010, iter_011), 유효한 실험 0회, 미분류 0회, 최근 판정: execution_failed, 커밋: 5581ed255a350e42a0ad422065edf13c56a33bf6, 8b030717b813bcbff85a2ffc5f52c9561a73f452

현재 연구 브랜치: approach/conditional-set-grounding (코드 위치: /SSD1_1TB/home/milab/daniel/08_medgemma/research)

### 최근 계획의 대안 순위

1. 영상 조건부 집합 grounding: 현재 checkpoint를 검증해 직접 병변 SFT와 강한 단순 baseline 비교를 완료한다.
2. 공간 선호 학습: 충분한 SFT 이후 잔여 오류와 SPR·CORAL·CoMedPO 대비 차별성이 확인되면 검토한다.
3. 별도 box decoder와 공간 토큰: 생성 경로의 잔여 문제와 기존 방법 대비 이점이 확인된 뒤 검토한다.
4. 해부구조에서 병변으로 grounding 전이: iter_008을 보존하고 직접 적응보다 유리할 새로운 근거가 있을 때 재검토한다.
