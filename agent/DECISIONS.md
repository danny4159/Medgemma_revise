# 결정 기록 (DECISIONS)

반복마다 계획 → 결정 → 개발 → 검증 흐름. 큰 흐름은 JOURNEY.md, 원본은 agent/runs/.

## iter_001 — 기존 점수 집계와 근거 기반 해석 (1번째 시도) · 2026-09-24 01:26

- 🎯 **연구 목표 변경**: legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.
  - 이전 목표: 현재 MedGemma 평가 코드와 기존 결과를 전체적으로 검토하고, 현재 평가에서 가장 중요한 한 가지 문제 또는 개선 가능성을 찾은 뒤 검증 가능한 작은 실험을 설계하라.
- ▶ 실행 시작 (orchestrator e0b3e72)
- 🧭 **계획** (GPT deep): scores.json의 21개 과제를 한 표로 재현하는 CPU 전용 스크립트를 만들고, DeepLesion bbox의 낮은 성능을 정정된 legacy 기록에 근거해 짧게 설명한다.
  - 대안: 1) 기존 점수 집계와 근거 기반 해석: 저장된 metric과 분모를 보존한 표 및 문서 근거가 있는 최저 성능 과제 설명을 생성한다. · 2) 원시 출력 재채점: 채점 의미를 다시 검증할 수 있지만 지정된 scores.json 요약 범위를 넘고 기존 수치와 불일치할 수 있다. · 3) 문서 수동 요약: 구현 비용은 작지만 JSON을 읽는 재사용 가능한 스크립트라는 요구를 충족하지 못한다.
  - 1순위 선택 근거: 입력 구조와 설명 근거가 확인됐고, 표준 라이브러리만 사용하는 작은 집계 작업으로 목표를 달성할 수 있다. GPU나 추가 데이터가 필요하지 않다.
- ▶ **결정**: 자동 진행 (smart) — 1순위로 진행
- 🔧 **Claude** (light): 21행 과제별 표와 최저 과제(DeepLesion bbox, mean IoU 0.0061) 요약을 생성했으나, docs 주석 근거 미확인과 임시 파일 `_peek.py` 삭제 실패가 남았다. [자체 검증 FAIL, 파일 4개 변경]
  - 새 브랜치 `approach/scores-summary` ← base (0809430)
  - ⚠ 권한 거부 5건
- 🔍 **리뷰** (GPT light): [CONTINUE / improve] 21행 요약과 문서 근거는 확인됐으며, 재사용 시 오류를 만드는 본문 생성 로직의 소규모 보완이 남았다.
  - 접근법 판단: 현재 입력의 집계는 정확하지만, 본문의 누락·null 처리와 하드코딩된 저장 점수·과제 해석을 수정해야 한다.
  - 다음: 본문에도 누락·null 처리를 적용하고 저장 점수와 표본 수를 JSON에서 읽도록 수정한다. DeepLesion 문서 해석은 해당 과제에만 연결하고, 기본 입력 및 누락·null·최저 과제 변경 사례를 CPU에서 확인한다.
- 📁 원본: `agent/runs/iter_001/`

## iter_002 — 기존 점수 집계와 근거 기반 해석 (2번째 시도) · 2026-09-24 01:32

- ▶ 실행 시작 (orchestrator b37b41a)
- 🧭 **계획** (GPT light): 요약 본문의 누락·null 처리와 입력값 반영을 보완하고 CPU 회귀 검증으로 표와 최저 과제 설명의 일관성을 확인한다.
  - 대안: 1) 기존 점수 집계와 근거 기반 해석: 기존 스크립트의 본문 생성 결함을 수정하여 재사용 가능한 요약을 완성한다. · 2) 원시 출력 재채점: 지정된 집계 범위를 넘어가며 현재 결함 해결에 필요하지 않다. · 3) 문서 수동 요약: 구현은 간단하지만 재사용 가능한 JSON 요약 스크립트 요구를 충족하지 못한다.
  - 1순위 선택 근거: 직전 리뷰와 코드에서 결함이 명확하며, 기존 구현의 작은 CPU 전용 수정으로 해결할 수 있다.
- ▶ **결정**: 자동 진행 (smart) — 1순위로 진행
- 🔧 **Claude** (light): report()의 누락·null·후보 부족·최저 과제 변경 처리를 보완하고 회귀 사례를 모두 통과했다. DeepLesion bbox 0.0061이 최저이며 보고서를 재생성했다. [자체 검증 PASS, 파일 2개 변경]
  - 브랜치 `approach/scores-summary`에서 계속
- 🔍 **리뷰** (GPT light): [DONE / success] GPU 실행 없이 점수 요약 스크립트를 완성했으며, DeepLesion bbox의 낮은 저장 점수와 문서에 기록된 평가 한계를 구분해 정리했다.
  - 접근법 판단: 21행 집계의 정확성과 본문 결측 처리·수치 갱신·과제별 설명 분기를 코드 및 실행 기록에서 확인했다.
- 💾 **커밋** `f213214` (approach/scores-summary): 과제별 점수 요약과 결측에 안전한 최저 bbox 과제 해석 구현
- 🏁 **마일스톤**: 기존 평가 점수의 재사용 가능한 요약과 근거 기반 해석 완성 — JOURNEY.md
- 📁 원본: `agent/runs/iter_002/`

## iter_003 — 3D 근거 보존 context 안정화 (1번째 시도) · 2026-09-24 02:07

- 🎯 **연구 목표 변경**: [최종 목표]
CVPR·ICML 같은 top-tier 학회 논문을 목표로, 의료 Vision-Language Model(VLM)의 중요한 한계를 찾아 이를 해결하는 새로운 방법론을 개발하고, 기존 방법 대비 분명한 contribution을 실험으로 증명한다.

[기준 모델]
MedGemma 1.5 (google/medgemma-1.5-4b-it). MedGemma 1이 아니다.
MedGemma 1.5로 연구하는 것 자체가 큰 제약이라고 판단되면, 근거를 들어 더 적절한 의료 VLM으로 바꿔도 된다.

[진행 단계]
1. 연구 방향 탐색
   - 의료 VLM 선행 연구와 최신 동향(특히 top-tier 학회)을 조사한다.
   - 여러 의료 데이터셋으로 MedGemma 1.5를 inference해 한계를 찾는다.
   - legacy/의 이전 한계 분석(스크립트, 결과, legacy/docs 정리 문서)이 도움이 되면 적극 활용한다.
2. 방향 선정: 후보들을 아래 기준으로 비교해 우선순위 1위 방향 하나를 정하고 진행한다.
   - 우리 서버(RTX 3090 24GB x2)에서 실험·검증할 수 있을 것
     (예: inference 기반 분석, training-free 방법, LoRA 등 경량 학습·적응)
   - 너무 좁은(minor) 문제가 아니라, 널리 쓰일 수 있는 한계를 풀거나
     모델의 근본적(foundational) 측면을 개선할 것. 취업·연구 경력에 의미 있는 주제여야 한다.
   - 기존 방법 대비 명확한 contribution을 만들 수 있을 것
3. 방법론 개발
   - 이 분야의 기존 방법을 구현·재현해 성능을 확인한다.
   - 부족하면 이유를 분석하고, 그 분석을 바탕으로 새 방법론을 설계·구현한다.
4. 증명
   - baseline 대비 개선을 여러 데이터셋에서 정량적으로 보이고, ablation 등으로 왜 개선되는지 분석한다.

[함께 기록할 것]
대규모 GPU가 있어야 가능한 해결책(모델 재학습 등 근본적 수정)도 버리지 말고,
계획 노트에 "대규모 GPU 필요 후보" 섹션으로 후보와 이유를 기록해 둔다.
지금은 제한된 GPU로 가능한 연구를 우선한다.
  - 이전 목표: legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.
- ▶ 실행 시작 (orchestrator 23cecd6)
- 🔎 **사고 라운드 1** (GPT deep): 기존 분류·3D 결론의 평가 교란과 최신 grounding 연구의 중복을 확인했으므로, 추가 읽기 전용 조사로 차별성과 유효한 실험 조건을 좁힌다.
  - 스스로 던진 질문: CORAL, Attention Without Grounding, SECOND, MedGround의 본문과 공개 코드는 어떤 개입·학습 목적·대조군을 이미 다루는가? 근거 제거에 대한 민감성과 근거 보존 변화에 대한 불변성을 함께 개선하는 방향에 실제 공백이 있는가? · VinDr, BraTS 및 공개 추가 후보에서 환자 식별자·병변 annotation·양성/음성·split·접근 조건이 확인되는 데이터 조합은 무엇인가? 정상 표본 부족과 미주석 병변을 고려해 어떤 질의를 정직하게 평가할 수 있는가? · MedGemma 1.5 공식 모델 카드·노트북과 legacy 구현을 대조하면 prompt, 좌표, resizing/cropping, MRI orientation, yes/no scoring 중 무엇을 먼저 바로잡아야 하는가? · 시각 근거 선택성, 3D 근거 선택, 해부구조→병변 전이 중 어느 방향이 선행 방법 대비 명확한 차이와 검증 가능한 신호를 동시에 갖는가? 이를 판별할 1시간 이내 소규모 실험의 조건·분모·중단 기준은 무엇인가?
- ⏳ 사용 한도 도달 (GPT 사고 라운드 2) → 대기
- ⏹ 중단: 정지 요청 (GPT 사고 라운드 2 중)
- ↻ 재실행: '계획' 단계부터 이어서 (orchestrator 6ab5ccf)
- 🔎 **사고 라운드 2** (GPT deep): 제거·보존 진단의 선행 연구 중복과 데이터 분모 제약을 확인했으므로, 질문 조건부 근거 학습과 3D context 민감성의 차별성을 한 라운드 더 비교한다.
  - 스스로 던진 질문: MMedPO 본문·코드와 causal sufficiency/necessity 학습은 질문 조건부 정답이 검증된 개입, 근거 보존 대조군, 해부학적 context를 어디까지 다루는가? 그대로 재현할 baseline과 남는 방법론 차이를 각각 한 문장으로 정의할 수 있는가? · 3D slice-selection 선행 연구와 MedGemma 1.5 평가에서, 동일 병변 근거를 유지한 채 자연 context·중복·순서만 바꾸는 실패를 이미 다뤘는가? 이를 고치는 경량 방법이 단순 top-k selection을 넘을 여지가 있는가? · 공식 anatomy·CT notebook 본문과 로컬 processor 구현을 읽어 prompt·좌표·crop·orientation 규약을 확정할 수 있는가? CheXlocalize 또는 대체 데이터에서 추가 확보 없이 시작할 표본과 향후 환자 단위 확장 경로는 무엇인가? · 앞의 비교를 바탕으로 2D 근거 선택과 3D context 민감성 중 하나를 선택하고, 기존 baseline·주효과·분모·중단 기준이 고정된 60 device-minutes 이내 진단 계획을 완성할 수 있는가?
- 🔎 **사고 라운드 3** (GPT deep): MedGemma 1.5의 근거 보존 context 불안정성은 이미 보고됐으므로, 마지막 조사에서 이를 해결할 방법의 차별성과 공개 데이터 사용 가능성을 확인한다.
  - 스스로 던진 질문: MRI-GBM-MET의 실제 파일 구조·license·subject ID·label·ROI 대응·split을 확인할 수 있는가? 공개 평가자료를 학습자료로 오용하지 않고 pilot과 최종 평가를 분리할 수 있는 최소 단위는 무엇인가? · 3D context 안정화를 위한 질문 조건부 근거 집계는 MedPruner, 독립 slice 점수 평균·max, permutation ensemble, consistency 기반 기권과 어떻게 다른가? 가장 가까운 방법의 수식·코드와 비교해 검증할 차이 하나를 명시할 수 있는가? · 고정된 병변 근거에서 context의 내용·중복·길이·위치를 분리하는 최소 비교는 무엇이며, 정확도와 안정성을 동시에 평가해 상수 예측·과도한 기권을 배제할 주효과와 중단 기준을 어떻게 고정할 것인가? · 확장 데이터의 사용 가능 여부에 따라 공개 데이터 소규모 재현 또는 로컬 BraTS 3 case 기전 pilot 중 무엇을 택할 것인가? 공식 입력 규약과 scoring을 확인하고, 60 device-minutes 안의 실행량·baseline·분모를 확정할 수 있는가?
- 🧭 **계획** (GPT deep): 로컬 BraTS 3개 case에서 근거를 고정한 context 변화와 paired 점수 보정을 비교하여, 3D 안정화 방법 개발에 필요한 기전과 개선 여지가 있는지 검증한다.
  - 대안: 1) 3D 근거 보존 context 안정화: 로컬 volume으로 context 효과의 분리 가능성과 paired 보정의 개선 여지를 먼저 검증한다. · 2) 질문 조건부 2D 근거 선택: 병변 근거와 해부학적 context를 구분하되 MMedPO·SECOND 등과의 차별성과 적절한 음성 label 확보가 필요하다. · 3) 해부구조에서 병변으로 grounding 전이: localization adapter나 LoRA를 검토하되 정답 정의·데이터 확장·기존 grounding 방법 재현 부담이 더 크다.
  - 1순위 선택 근거: MedGemma 1.5의 관련 실패가 선행 연구에서 확인됐고, 로컬 데이터만으로 55 device-minutes 이내의 반증 가능한 pilot을 실행할 수 있다. 이번 결정은 논문 주제 확정이 아니라 방법 개발에 투자할 근거를 얻는 저비용 검증이다.
- ▶ **결정**: 자동 진행 (smart) — 1순위로 진행
- ⏳ 사용 한도 도달 (Claude 구현/실험) → 대기
- ↻ 끊겼던 Claude 세션을 이어서 진행
- ↻ 끊겼던 Claude 세션을 이어서 진행
- ▶ 사용 한도가 풀려 재개 (Claude 구현/실험, 60분 대기)
- 🔧 **Claude** (creative): BraTS 3 case pilot을 끝까지 실행(294 요청, 5.75 device-min)해 측정 가능성·불안정성 기준은 통과했지만, GT reference paired 보정은 drift를 줄이지 못해(−2.9%, BA·worst 하락) 가설을 기각했고, context가 양성 근거를 선택적으로 희석한다는 사후 신호와 IAF(γ=0.05)의 병변 slice 제거 문제를 발견했다. [자체 검증 FAIL, 파일 84개 변경]
  - 새 브랜치 `approach/context-evidence-stability` ← approach/scores-summary (f213214)
  - ⚠ 권한 거부 1건
- 🔍 **리뷰** (GPT deep): [CONTINUE / abandon] 294개 본실행 결과를 확인했으며, context 민감성은 관찰됐지만 paired 보정은 정확도와 안정성을 모두 악화시켰다.
  - 접근법 판단: 이번 접근법의 핵심인 GT reference 가산 보정은 사전 진행 기준을 실패했고 3개 case 모두 drift가 증가했다. 계수·reference의 사후 조정을 중단하고 남은 근거 선택 대안으로 전환한다.
  - 다음: 재사용할 파이프라인의 예산 축소·hash 검증 결함을 수정하고, 다음 후보인 질문 조건부 2D 근거 선택을 검토한다. unique-slice mean을 필수 baseline으로 두고 GT 없는 선택 규칙, 해부학적 confound 대조군, 독립 subject 평가 및 선행 방법과의 차별성을 갖춘 소규모 실험을 설계한다.
- 🏁 **마일스톤**: 첫 기전 pilot에서 GT reference 가산 보정의 투자 기준 실패 확인 — JOURNEY.md
- 📁 원본: `agent/runs/iter_003/`

## iter_004 — 질문 조건부 2D 근거 선택 (1번째 시도) · 2026-09-24 04:14

- 🔎 **사고 라운드 1** (GPT deep): 질문 조건부 2D 근거 선택은 검토할 가치가 있지만, 독립 평가자료와 음성 label이 부족하고 선행 선택 방법과 겹쳐 평가 설계와 방법 차이를 한 라운드 더 좁힌다.
  - 스스로 던진 질문: 추가 다운로드 없이 가능한 2D 자료 중 동일 영상에 서로 다른 질문과 신뢰할 수 있는 양성·음성 label을 연결할 수 있는 것은 무엇인가? VinDr 원본 annotation과 subject 정보를 확인하고, 미주석 소견을 음성으로 간주하지 않는 평가 단위를 정할 수 있는가? · GT 없이 후보 영역을 만들고 근거의 충분성·제거 민감도로 선택하는 규칙은 SECOND 및 기존 counterfactual visual grounding·선택 방법과 정확히 어디서 다른가? 단순 confidence 선택과 구별되는 최소 수식과 반증 가능한 예측을 정할 수 있는가? · 같은 해부학적 위치·면적의 대조군과 질문 교환 대조군을 구성할 수 있는가? crop 또는 삭제의 분포 변화와 동일 점수로 선택·평가하는 순환성을 어떻게 분리할 것인가? · 독립 subject 확보와 음성 label 검증이 이번 범위에서 어렵다면, 로컬 자료로 수행할 타당한 기전 pilot의 범위는 어디까지인가? 필요한 최소 추가 데이터의 출처·사용 조건·크기와 GPU 요청 수를 확인해 구현 여부를 결정할 수 있는가?
- 🔎 **사고 라운드 2** (GPT deep): 로컬 자료는 양성 grounding 개발 검사로 범위를 제한하고, 새로 확인한 CSGR와의 차별성 및 환자 단위 평가 데이터 확보 가능성을 확인한 뒤 구현 여부를 결정한다.
  - 스스로 던진 질문: CSGR의 관련 연구와 SECOND의 선택식을 기준으로, 질문 간 공통 제거 반응을 제거하는 C(q,R,t)가 기존 contrastive attribution과 어떻게 다른가? 공유 근거·co-occurrence 때문에 실패하는 경우까지 포함해 검증할 가설 하나를 고정할 수 있는가? · CheXlocalize 공식 다운로드 안내에서 데이터 사용 조건, 파일 크기, patient별 영상·명시적 label·mask 연결을 확인할 수 있는가? 소규모 환자 분할을 확보할 수 없다면 로컬 양성 grounding pilot만으로 다음 투자 여부를 판단할 가치가 있는가? · 로컬 VinDr의 어떤 소견 쌍이 공간적으로 구별되며, 고정 후보 grid가 이들을 분리할 수 있는가? 질문 교환·동일 질문의 영상 교환·단순 crop confidence 대조군을 포함한 최소 요청 목록과 사전 성공 기준을 확정할 수 있는가?
- 🧭 **계획** (GPT deep): 재사용 파이프라인의 검증 결함을 고친 뒤 VinDr 10영상에서 질문 간 contrastive 영역 선택이 단순 제거·crop confidence·위치 prior를 넘는지 제한된 개발 pilot으로 판정한다.
  - 대안: 1) 질문 조건부 2D 근거 선택: 고정 질문·영역 후보에서 contrastive occlusion 선택을 재현하고 독립 bbox 및 질문·영상 교환 대조군으로 추가 투자 가치를 검증한다. · 2) 해부구조에서 병변으로 grounding 전이: 첫 후보가 투자 기준을 통과하지 못하면 annotation을 활용한 adapter·LoRA와 기존 grounding 학습법 비교로 전환한다.
  - 1순위 선택 근거: 선행 방법과의 중복을 인정한 기전 pilot으로 범위를 좁혔고, 로컬 자료에 평가 가능한 질문 쌍이 확인됐다. 추가 데이터 취득 없이 누적 45 device-minutes 이내에서 중단할 수 있어 사람의 가치 판단이나 대규모 실행 승인이 필요하지 않다.
- ▶ **결정**: 자동 진행 (smart) — 1순위로 진행
- 🔧 **Claude** (heavy): VinDr 10영상 1,680요청(11.3 device-min)을 끝까지 실행했고 scoring 검증(teacher-forced 차이 7e-7, 반복 0)도 통과했지만, contrastive 선택 C_blur(U 0.511)는 raw-D(0.499)와 선택이 17/20 같고 GT 위치 prior(0.615)보다 낮아 사전 기준 1–3이 FAIL이다. 또한 greedy 생성이 8/12에서 Yes/No가 아닌 설명문으로 시작해 margin의 타당성에 우려가 있다. [자체 검증 FAIL, 파일 54개 변경]
  - 새 브랜치 `approach/question-evidence-selection` ← f213214 (f213214); 이전 브랜치 미커밋 작업은 stash와 `stashed.patch`로 보관
  - ⚠ 권한 거부 1건
- 🔍 **리뷰** (GPT normal): [CONTINUE / abandon] 1,680건 실험 완료를 확인했지만 contrastive 선택의 개선은 작고 위치 prior보다 낮았으며, 재사용 파이프라인의 검증 결함도 남아 있다.
  - 접근법 판단: 고정 contrastive occlusion 후보는 사전 기준 1–3을 실패했다. 계수·질문 bank 조정을 중단하고 해부구조→병변 grounding 전이 후보로 넘어간다.
  - 다음: 해부구조→병변 grounding 전이의 선행 방법·데이터·경량 학습 가능성을 비교하고 최소 반증 실험을 설계한다. 재사용할 코드에는 실제 입력 hash 재검증, verification 완료 강제, selection digest 연결 검증을 먼저 보완한다.
- 🏁 **마일스톤**: 2D contrastive occlusion의 투자 기준 실패를 확인하고 grounding 전이 후보로 전환 — JOURNEY.md
- 📁 원본: `agent/runs/iter_004/`

## iter_005 — Grounding 데이터·측정 기반 구축 (1번째 시도) · 2026-09-24 04:50

- 🔎 **사고 라운드 1** (GPT deep): 해부구조→병변 grounding 전이는 선행 연구와 중복이 크고 평가 형식·독립 데이터가 미확정이므로, 최소 반증 실험을 정하기 전에 이를 한 라운드 더 확인한다.
  - 스스로 던진 질문: MedGemma 1.5의 기술보고서·공식 localization 예제·로컬 checkpoint는 각각 어떤 prompt와 좌표 규약을 사용하는가? legacy의 해부구조–병변 격차에서 출력 형식과 대리 annotation의 영향을 어떻게 분리할 것인가? · 현재 접근 가능한 공식 데이터 중 해부구조 annotation, 병변 annotation, patient 단위 분할을 확보할 수 있는 조합은 무엇인가? Chest ImaGenome 접근 없이 가능한 대체 조합과 그 한계는 무엇인가? · AnatomiX·CURE·F-LMM·AG-KD 및 VGMED의 상세 설정과 비교했을 때, anatomy supervision의 효과를 추가 데이터량·위치 prior·출력 decoder 적응과 구분하는 최소 실험과 잠재적 contribution은 무엇인가? · 설치된 라이브러리와 모델 구조에서 frozen feature/head, attention decoder, LoRA 중 어떤 경로가 RTX 3090 24GB에서 가능한가? 다음 구현 반복을 1시간 미만 GPU 예산으로 제한할 때 확보 가능한 비교군과 평가 표본은 무엇인가?
- 🔎 **사고 라운드 2** (GPT deep): frozen feature 기반 검증의 실행 가능성을 확인했으며, 새로 발견한 EasyLens와의 중복 및 독립 annotation 확보 경로를 더 확인해 전이 실험의 범위를 확정한다.
  - 스스로 던진 질문: EasyLens v3의 MedGemma1.5 적용 위치, prototype 구축 supervision, patient split, 데이터와 공개 코드 수준은 무엇인가? anatomy transfer 후보에 기존 방법과 구분되는 검증 가능한 차이가 남는가? · JSRT/SCR의 영상·수동 anatomy mask·nodule metadata 또는 NIH bbox·patient metadata·CheXmask를 실제로 연결할 수 있는 공식 파일 경로와 schema는 무엇인가? 작은 다운로드만으로 충분한 독립 평가 집단을 구성할 수 있는가? · pooling 전·후 동일 head 비교에서 정보 손실, 출력 해상도, probe 용량 효과를 어떻게 분리할 것인가? anatomy 보조 학습까지 넣는 것보다 이 반증 실험을 먼저 수행해야 하는가? · 좌표 규약이 명시된 MedGemma 1.5 공식 예제를 확보할 수 있는가? 확보하지 못하면 두 고정 prompt와 독립 anatomy calibration으로 parser를 고정하는 절차 및 45 device-min 이내 요청 수를 어떻게 정할 것인가?
- 🔎 **사고 라운드 3** (GPT deep): EasyLens와의 중복 및 선형 pooling 비교의 한계를 확인했으며, 마지막 라운드에서 데이터 접근과 fine/coarse probe의 평가 조건을 확정한다.
  - 스스로 던진 질문: NIH bbox·patient CSV와 개별 PNG를 결제 설정·대용량 전체 다운로드 없이 확보할 수 있는 경로가 있는가? 원본 provenance를 추적할 수 있는 미러에서 실제 header와 영상 ID 대응까지 확인할 수 있는가? · NIH 경로가 불가능하면 SCR archive의 실제 해상도·파일명과 JSRT nodule metadata를 확인할 수 있는가? 병변 annotation이 연결되지 않으면 이번 반복을 GPU 없는 데이터 준비·검증 구현으로 제한할 것인가? · 확인된 annotation이 bbox인지 mask인지에 맞춰, pooling probe의 fine/coarse target·표본 수·patient split·효과크기 기준을 어떻게 고정할 것인가? 선형 교환법칙과 비선형 readout 차이를 구분하는 최소 비교를 45 device-min 안에 구성할 수 있는가?
- 🧭 **계획** (GPT deep): GPU 없이 NIH/SCR의 annotation·영상·subject 연결과 평가 무결성을 검증해, grounding 전이 및 pooling 가설을 독립 데이터에서 시험할 기반을 만든다.
  - 대안: 1) Grounding 데이터·측정 기반 구축: 소량 데이터 확보·분할·좌표·캐시 검증을 먼저 완료해 후속 표현 분석의 실행 가능성을 확정한다. · 2) Pooling 전후 frozen feature probe: 병변 데이터 요건 충족 후 동일 readout과 fine/coarse 평가로 공간 정보 접근성 차이를 검증한다. · 3) 해부구조에서 병변으로 grounding 전이: 표현 분석과 데이터 확보 이후 동일 supervision·학습 예산의 직접 병변 학습과 anatomy 보조 학습을 비교한다.
  - 1순위 선택 근거: 현재 가장 큰 병목은 독립 평가 데이터와 검증 가능한 측정 체계의 부재다. CPU 작업과 제한된 다운로드로 해결할 수 있으며, 성공 여부와 관계없이 후속 연구의 실행 조건을 명확히 할 수 있어 사람의 가치 판단이나 대규모 GPU 승인이 필요하지 않다.
- ▶ **결정**: 자동 진행 (smart) — 1순위로 진행
- 🔧 **Claude** (heavy): QES 검증 결함 3개를 고쳐 진입점 테스트 25/25를 통과했고, NIH bbox 160명 patient-disjoint split을 `lesion_probe_ready`로 확보했습니다(118 MiB, GPU 0). 공개 SCR은 영상에 정답 윤곽선이 그려져 있고 mask 정의가 문서에 없어 `anatomy_only_ready=false`이며, 미러 원본 동일성은 미검증이라 GPT 리뷰가 필요합니다. [자체 검증 FAIL, 파일 507개 변경]
  - 새 브랜치 `approach/grounding-data-audit` ← f213214 (f213214); 이전 브랜치 미커밋 작업은 stash와 `stashed.patch`로 보관
  - ⚠ 권한 거부 4건
- 🔍 **리뷰** (GPT normal): [CONTINUE / improve] NIH 160명 확보와 SCR 정답 노출 차단은 확인했지만, 준비 완료 판정과 QES 검증에 결함이 남아 있다.
  - 접근법 판단: 데이터 확보는 확인됐으나 NIH 좌표 근거와 readiness 조건, QES 고정 verification 집합 검증을 보완해야 한다.
  - 다음: NIH bbox 좌표 기준의 명시적 근거를 확보하고 readiness를 보강한다. QES verification 집합을 결정적으로 재생성해 대조하고 실패 시 이전 완료 산출물을 무효화한다. 이후 클래스별 target 정의를 확정해 pooling probe로 진행한다.
- 📁 원본: `agent/runs/iter_005/`

