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

## 🏁 직접 LoRA SFT로 RSNA grounding 개선을 독립 확인

*iter_012 · 2026-09-26 07:41 · 판정: CONTINUE / success*

정상 사용에서도 남던 RSNA grounding 오류가 직접 LoRA SFT로 크게 개선됨을 확인했다.
**고민:** iter_009에서 위치 불일치를 검증했지만, 경량 적응으로 실제 출력을 개선할 수 있는지는 미확인이었다.
**시도:** anatomy 전이를 바로 도입하지 않고 직접 병변 SFT와 좌표 보정·box prior를 먼저 비교했다.
iter_010·011은 실행 복구와 평가 연결 문제로 본실험을 끝내지 못해 방법의 효과를 판정하지 못했다.
**개발:** 재개 상태와 선택 근거를 검증하고, 부모 trajectory의 불확실성을 피하기 위해 새 경로에서 원래 학습을 완료했다.
**결과:** 확인 양성 400명에서 세 seed의 F1@0.3은 0.631–0.653으로 prior_set 0.424를 넘었다. 평균 차이는 +0.216, 95% CI는 [0.172, 0.259]였다.
**의미:** 후속 방법을 비교할 직접 적응 baseline을 확보했다. 새 방법의 기여, 더 충분한 SFT 대비 이득과 다른 데이터셋 재현은 다음 과제다.

- 접근법: 영상 조건부 집합 grounding (`approach/conditional-set-grounding`), 시도: iter_010, iter_011, iter_012
- 커밋: 5581ed255a350e42a0ad422065edf13c56a33bf6, 8b030717b813bcbff85a2ffc5f52c9561a73f452, 783d2d04671ae296f3dc0c700e575f8af8e021c9
- 자세히: DECISIONS.md의 iter_012, `agent/runs/iter_012/review.md`

## 🏁 Grounding 적응의 QA 저하를 형식 효과와 잔여 변화로 분리

*iter_016 · 2026-09-27 12:20 · 판정: CONTINUE / success*

QA 형식 실패를 의미 능력 손실로 오해하지 않도록 실제 출력에서 두 효과를 분리했다.
**고민:** 직접 SFT로 bbox는 개선됐지만, QA에서도 능력이 유지되는지는 알 수 없었다.
**시도:** iter_014의 GIoU 추가 이득이 입증되지 않은 뒤 기존 checkpoint 진단으로 전환했고, iter_015에서는 형식 gate가 본평가를 막았다.
**개발:** 질문별 최소 semantic parser를 고정하고 E180에서 사전 기준에 따라 E600까지 확대했다.
**결과:** 신규 6,180건에서 B0−M0의 strict 차이 −0.255는 semantic −0.0317로 줄었다. 예측 bbox reader는 동일 P180 direct M0보다 +0.0778 높았다.
**의미:** 큰 형식 효과를 확인했지만 category별 변화와 evidence 효과는 남았다. 새 loss보다 문구·검출 정보·좌표를 구분하는 진단의 가치가 높아졌으며, 원인과 신규 기여는 아직 미확인이다.

- 접근법: 질문 대상과 음성 의미 보존 진단 (`approach/target-scope-diagnostic`), 시도: iter_015, iter_016
- 커밋: 3265f117bf3f4de99ba084f2c9b4e476568f24bd, 6a4fb41d490305061028de9cab863c0b5e9747ad
- 자세히: DECISIONS.md의 iter_016, `agent/runs/iter_016/review.md`

## 🏁 bbox reader의 이득을 검출 정보·개수·인터페이스 효과로 좁힘

*iter_017 · 2026-09-27 13:39 · 판정: CONTINUE / success*

기존 bbox reader 개선을 좌표 활용의 성과로 해석할 근거가 약해져 다음 투자 방향을 재검토하게 됐다.
**고민:** iter_016에서 reader가 direct M0보다 좋았지만 문구와 검출·개수·좌표가 함께 바뀌었다.
**시도:** 추가 grounding loss 학습을 이어가지 않고 같은 영상과 공통 문구에서 전달 정보만 달리했다.
**개발:** 정보 미제공 U, 검출 B, 개수 K, 좌표 L의 요청·평가·조건부 확대를 구현했다.
**결과:** E600 신규 4,800건에서 B−U +0.0533, K−B +0.0150을 확인했고 L−K의 정답 쌍 차이는 0이었다.
**한계:** L−direct M0는 +0.0117 [−0.0150, 0.0400]으로 불확정이며 NoOpacity/NotNormal 정확도는 40/200에서 4/200으로 낮아졌다.
**의미:** 현재 좌표 방향의 추가 투자는 보류한다. 단순 baseline을 보존하고 질문 범위 오류의 독립 진단과 다른 중요한 연구 질문으로의 전환을 비교한다.

- 접근법: 질문 대상과 음성 의미 보존 진단 (`approach/target-scope-diagnostic`), 시도: iter_015, iter_016, iter_017
- 커밋: 3265f117bf3f4de99ba084f2c9b4e476568f24bd, 6a4fb41d490305061028de9cab863c0b5e9747ad, d12ef5ccea60d05b9163519980cdb1624b3fa682
- 자세히: DECISIONS.md의 iter_017, `agent/runs/iter_017/review.md`

## 🏁 RSNA 위치 학습의 개선만으로는 신뢰할 만한 사분면 전체 선택이 확보되지 않았다

*iter_027 · 2026-09-29 03:47 · 판정: CONTINUE / success*

기존 위치 학습의 성과와 미학습 영역 선택 능력을 구분하는 제한적 음성 근거를 확보했다.
**고민:** iter_012의 직접 LoRA는 bbox 검출을 크게 개선했지만 다른 공간 질문으로의 전이는 미확인이었다.
**시도:** 사분면 yes/no는 oracle 해석 gate를 통과하지 못해, 학습된 bbox 출력 형식을 유지하는 선택 과제로 옮겼다.
**개발:** 전체 bbox 복사·bbox+규칙·영상+bbox reader를 비교하고 E60의 불확실성을 사전 E200 확대로 줄였다.
**결과:** primary 160명에서 B0−M0 S는 +0.1943이지만 복사 대비 +0.0181은 불확정이었다.
**결과:** 다중 사분면 66명에서 직접 전체 선택은 0명, bbox+규칙은 26명이 성공해 사전 음성 기준을 충족했다.
**의미:** 검출 향상과 신뢰할 만한 선택 전이는 구분해야 한다. 부분 질의 반응과 oracle 실패가 남으므로 일반적인 전이 부재는 미확정이며, 다음 투자는 최소 원인 진단과 전환의 가치를 비교해 결정한다.

- 접근법: RSNA 영역 질의 전이 진단 (`approach/rsna-spatial-transfer`), 시도: iter_023, iter_024, iter_025, iter_026, iter_027
- 커밋: 3271c85f34c135081bba28352baa31468125f842, d60460f8be761e11e1dbce306aa571173e4229db, 89b2975a679c6eed3d9a356d2c01d85b7950a1bf, b8be58c9f3c92266e885ca8c3f5384dbe412b4bd, ed966685298f152e194069d4de3d856e065886bc
- 자세히: DECISIONS.md의 iter_027, `agent/runs/iter_027/review.md`

## 🏁 RSNA 누락 후보는 이어쓰기로 일부 회복되지만 전체 검출 성능은 악화됐다

*iter_031 · 2026-09-29 09:49 · 판정: CONTINUE / success*

기존 SFT가 반환한 목록을 늘리면 일부 누락은 회복되지만, FP 비용 때문에 전체 검출은 나빠진다는 관찰을 확보했다.
**고민:** iter_012의 RSNA SFT 개선 이후에도 반환된 목록 밖에 병변이 남는 경우를 어떻게 구분할지 미해결이었다.
**시도:** 빈 출력에서는 entropy가 강한 baseline이었으므로, nonempty 목록의 종료 분기와 부분 누락으로 질문을 좁혔다.
**개발:** iter_030의 미완료 실행을 이어 C201·E402에서 원래 출력과 단일 continuation 개입을 비교했다.
**결과:** 누락 사건은 C 8/20, E 11/27에서 회복됐지만 E 전체 F1@0.3은 0.6276→0.4738로 하락했다.
**결과:** Q의 baseline 대비 AUROC 차이는 -0.0011로 추가 이득 기준을 충족하지 못했다.
**의미:** 단순히 더 생성하는 것으로 충분한 검출 개선은 얻지 못했다. 후보 회복의 활용 가치와 다른 연구 질문을 비교할 근거가 생겼으며, 독립 일반화·신규 기여는 남아 있다.

- 접근법: RSNA 부분 누락 위험 진단 (`approach/rsna-partial-omission-risk`), 시도: iter_030, iter_031
- 커밋: 5bdcbe2f56b219de1e5319c8a890061ec672a774, 8dad463392de9bb0e9fe7d93d64b9c374492de9b
- 자세히: DECISIONS.md의 iter_031, `agent/runs/iter_031/review.md`

## 🏁 RSNA에서 detector의 위치 정밀도·속도 이점과 SFT의 상보적 검출을 확인했다

*iter_035 · 2026-09-29 22:04 · 판정: CONTINUE / success*

실제 전용 detector 비교로 기존 LoRA SFT의 강점과 잔여 차이를 구체화했다.
**고민:** 직접 SFT가 base보다 크게 개선됐지만 전용 detector 대비 가치가 확인되지 않았다.
**시도:** VinDr 승인 대기 동안 같은 annotation budget의 RSNA 비교를 선택했다. iter_033·034는 실행·재개 결함으로 비교를 끝내지 못했다.
**개발:** LR·RNG 재개와 평가 연결을 복구하고 detector17 26 epoch, detector29 38 epoch를 완료했다.
**결과:** 양성400명에서 detector17−SFT17의 F1@0.5는 +0.0669 [0.0122, 0.1220], F1@0.3은 −0.0491 [−0.1000, 0.0018]이었다.
**관찰:** IoU0.3에서 detector-only/SFT-only GT는 71/589·77/589개였고, 단독 평균 추론은 detector가 약70배 빨랐다.
**의미:** 전반적 우위를 선언할 수는 없지만 위치 정밀도·confidence·미검출을 구분할 근거가 생겼다. 개발 집단의 관찰이며 외부 일반화와 새 contribution은 다음 판단으로 남는다.

- 접근법: RSNA 전용 detector와 SFT 비교 (`approach/rsna-detector-comparison`), 시도: iter_033, iter_034, iter_035
- 커밋: a60224c1f7d54e4f59e8c4dc16285d62faf004b5, bc80f2deede564fb56b4222e530eda5621b31069, 615c61ec51cfe9d84d564bfcaab434a3a5c78cb1
- 자세히: DECISIONS.md의 iter_035, `agent/runs/iter_035/review.md`

## 🏁 RSNA에서 SFT만 검출한 병변 대부분은 detector의 낮은 score 후보에도 있었다

*iter_036 · 2026-09-29 23:40 · 판정: CONTINUE / improve*

RSNA의 detector–SFT 상보성을 큰 후보 발견 능력 차이로 해석할 근거가 약해졌다.
**고민:** 직접 LoRA SFT는 개선됐지만, 빠르고 정밀한 전용 detector 대비 어떤 가치가 남는지 불분명했다.
**시도:** iter_035는 양성400명에서 양방향 상보성을 확인했다. 이를 바로 새 loss나 ensemble의 근거로 삼지 않고 저장 후보를 분해했다.
**개발:** 고정 threshold와 GT 일대일 matching을 유지하며 선택 제외·대응 경쟁·인접 위치 오차를 구분했다.
**결과:** SFT-only GT의75/77개·80/87개가 두 detector의 threshold 아래 대응 후보와 연결됐다.
**결과:** IoU0.3 대응 후보가 없는 잔여량은1/589·7/589이고97.5% CI 상한은0.68%·2.24%였다. 리뷰에서 원시 출력과 CI를 독립 재현했다.
**의미:** 큰 후보 coverage 차이를 전제로 한 추가 학습의 우선순위를 낮춘다. FP 비용의 전체 비교·코드 보완과 외부 재현은 남으며, 실용적 detector 우위나 새로운 contribution을 확정하지 않는다.

- 접근법: RSNA 전용 detector와 SFT 비교 (`approach/rsna-detector-comparison`), 시도: iter_033, iter_034, iter_035, iter_036
- 커밋: a60224c1f7d54e4f59e8c4dc16285d62faf004b5, bc80f2deede564fb56b4222e530eda5621b31069, 615c61ec51cfe9d84d564bfcaab434a3a5c78cb1, f9bfbc250058ce1785f819dd404b1148998918b9
- 자세히: DECISIONS.md의 iter_036, `agent/runs/iter_036/review.md`
