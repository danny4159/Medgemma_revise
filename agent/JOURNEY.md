# 연구 흐름 (JOURNEY)

## 🎯 연구 목표 변경 (iter_001부터, 2026-09-24 01:26)

- 이전: 현재 MedGemma 평가 코드와 기존 결과를 전체적으로 검토하고, 현재 평가에서 가장 중요한 한 가지 문제 또는 개선 가능성을 찾은 뒤 검증 가능한 작은 실험을 설계하라.
- 새 목표: legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.

## 🏁 기존 평가 점수의 재사용 가능한 요약과 근거 기반 해석 완성
*iter_002 · 2026-09-24 01:36 · 판정: DONE / success*

**고민**: 서로 다른 metric과 평가 조건을 가진 기존 점수를 한 표로 정리하면서 낮은 점수를 모델의 능력 부재로 오해하지 않아야 했다.
**시도**: iter_001에서 JSON 기반 21행 표와 문서 설명을 만들었으나, 본문의 결측 처리와 고정된 수치·설명 때문에 입력 변경 시 오류가 남았다.
**개발**: iter_002에서 후보 선정, 입력 수치 표시, DeepLesion 문서 설명 연결을 분리하고 후보 부족 처리를 추가했다.
**검증**: CPU에서 결측·후보 부족·수치 변경 사례를 실행했으며, 테스트 이름 오타로 실패한 최저 과제 변경 사례는 수정 후 별도 실행했다.
**결과**: G1 3행·G2 6행·G3 12행이 원본과 일치했고, bbox mean_iou는 DeepLesion 0.0061, BraTS 0.1084, VinDr 0.1276이었다.
**의미**: 초기 형식 오류와 입력 조건 제약을 근거로 설명하면서 별도 재평가 수치와 인과적 추정을 구분했다. GPU 실행 없이 요청한 요약 목표를 완료했다.

- 접근법: 기존 점수 집계와 근거 기반 해석 (`approach/scores-summary`), 시도: iter_001, iter_002
- 커밋: f213214
- 자세히: DECISIONS.md의 iter_002, `agent/runs/iter_002/review.md`

## 🎯 연구 목표 변경 (iter_003부터, 2026-09-24 02:07)

- 이전: legacy/eval_results/scores.json을 읽어 과제별 성능을 한 표로 정리하는 스크립트를 research/에 만들고, 성능이 가장 낮은 과제 하나와 그 이유를 legacy/docs 기록을 근거로 짧게 정리하라. GPU 실행은 하지 않는다.
- 새 목표: [최종 목표]
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

## 🏁 첫 기전 pilot에서 GT reference 가산 보정의 투자 기준 실패 확인
*iter_003 · 2026-09-24 04:11 · 판정: CONTINUE / abandon*

**고민**: iter_001–002의 기존 점수 정리를 마친 뒤, 의료 VLM의 한계를 실제로 개선할 논문 방향을 찾기 시작했다.
**시도**: 후보 중 3D context 안정화를 우선해, 같은 context가 만드는 공통 점수 변화를 별도 reference로 상쇄하는 가설을 골랐다.
**개발**: BraTS 3 case의 T1CE/T2에서 근거 packet을 고정하고 7개 presentation, 단순 baseline, oracle paired 보정을 비교하는 파이프라인을 구현했다.
**검증**: 본실행 294개 요청과 예비 실행을 합쳐 5.75 device-minutes를 사용했으며, 원시 결과·입력 hash·실행 로그를 확인했다.
**결과**: 측정 가능성과 context 민감성 기준은 통과했지만, 보정 후 drift는 4.491→4.620, BA는 0.964→0.917, worst-context 정확도는 0.833→0.667로 악화됐다.
**교훈**: 이번 공통 가산 보정은 3/3 case에서 drift를 줄이지 못했으며, 동일 reference를 빼는 구조로는 E–N margin도 복원할 수 없다.
**의미**: 이 보정 가설에 대한 추가 조정을 중단하고 근거 선택 대안으로 전환한다. unique-slice mean의 BA 0.988을 후속 baseline으로 삼되, 해부학적 confound와 독립 subject 검증은 남아 있다.

- 접근법: 3D 근거 보존 context 안정화 (`approach/context-evidence-stability`), 시도: iter_003
- 커밋: 없음
- 자세히: DECISIONS.md의 iter_003, `agent/runs/iter_003/review.md`

## 🏁 2D contrastive occlusion의 투자 기준 실패를 확인하고 grounding 전이 후보로 전환
*iter_004 · 2026-09-24 04:47 · 판정: CONTINUE / abandon*

**고민:** 의료 VLM의 근거 활용을 개선할 방법을 찾는 과정에서 iter_003의 3D 가산 보정은 정확도와 안정성을 악화시켰다.
**시도:** 다음 후보로 질문 간 공통 제거 반응을 빼는 2D contrastive 선택을 고정하고, raw occlusion·crop·위치 prior와 비교했다.
**개발:** GT를 읽지 않는 selector와 bbox union 평가, 질문·영상 교환 대조군을 구현했다.
**결과:** VinDr 개발 영상 10개에서 1,680요청을 11.28 device-min에 완료했다.
**결과:** C_blur U는 0.511로 raw-D 0.499보다 소폭 높지만 위치 prior 0.615보다 낮았고, 개선 영상은 1/9이었다.
**판단:** 사전 기준 1–3 실패는 fp32-head 분석에서도 유지돼 고정 contrastive 후보의 추가 조정을 중단한다.
**의미:** 모든 grounding의 한계로 일반화하지 않고, 다음 후보인 해부구조→병변 grounding 전이와 독립 평가 설계로 이동한다.

- 접근법: 질문 조건부 2D 근거 선택 (`approach/question-evidence-selection`), 시도: iter_004
- 커밋: 없음
- 자세히: DECISIONS.md의 iter_004, `agent/runs/iter_004/review.md`

## 🏁 Coarse grounding에서 pooling 이전 feature의 추가 이득이 관찰되지 않음
*iter_007 · 2026-09-24 06:08 · 판정: CONTINUE / abandon*

**고민:** 의료 VLM의 grounding 한계가 vision projector의 공간 pooling에서 비롯되는지 확인할 필요가 있었다.
**시도:** 앞선 context 보정과 질문 조건부 선택은 성능 개선 근거가 부족해 종료했고, NIH 160명의 측정 기반을 구축했다.
**개발:** 좌표 가정을 명시한 탐색 gate 아래 동일 coarse loss·초기화·학습 순서로 Z와 U(P(Z))의 linear·MLP probe 24개를 실행했다.
**결과:** test 48명에서 MLP 차이는 +0.000304, 95% CI [−0.001012, +0.001611]로 투자 기준 0.03에 미달했다.
**대조:** Z는 위치 prior보다 +0.0823, image-swap보다 +0.0991 높았고, linear 두 조건은 수치적으로 일치했다.
**의미:** 현재 coarse 평가에서는 pooling 보존형 adapter를 개발할 근거가 부족하다. 일반적 정보 무손실이나 decoder 병목을 주장하지 않고, anatomy→lesion 전이 등 남은 방향으로 이동한다.

- 접근법: Pooling 전후 frozen feature probe (`approach/pooling-feature-probe`), 시도: iter_007
- 커밋: 없음
- 자세히: DECISIONS.md의 iter_007, `agent/runs/iter_007/review.md`

## 🏁 정상 사용 조건에서도 남는 RSNA opacity grounding 오류를 실제 출력으로 검증

*iter_009 · 2026-09-24 22:29 · 판정: CONTINUE / success*

정상 사용을 통제한 실제 생성 출력에서 반복적 위치 불일치를 확인해 방법 개발의 근거를 확보했다.
**고민:** 과거 grounding 저점수에는 좌표·출력 길이·사용법 문제가 섞여 있었다.
**시도:** context·pooling 접근의 제한된 근거를 전체 능력으로 일반화하지 않고, 사용자 보완으로 anatomy 전이 계획을 보존한 채 진단으로 전환했다.
**개발:** 공식 사용법 sanity, RSNA 환자 분할, 세 prompt 생성, 엄격 parser와 bbox 평가를 연결했다.
**결과:** 평가 양성 200명 중 두 정상 prompt의 공통 위치 불일치는 134명, 67.0%(95% CI 60.2–73.1%)였다.
**비교:** 공식 prompt F1@0.3 0.147은 단일 box prior 0.269보다 낮았다.
**의미:** 특정 RSNA 조건의 한계는 validated로 갱신한다. 내부 원인과 해결책은 미확인으로 남기고, 다음에는 강한 baseline을 갖춘 방법 개발을 진행한다.

- 접근법: 정상 사용 조건의 병변 grounding 검증 (`approach/grounding-usage-diagnostic`), 시도: iter_009
- 커밋: 39aa49a6fa5943ca0d3e0327a7874e68a2c878cb
- 자세히: DECISIONS.md의 iter_009, `agent/runs/iter_009/review.md`
