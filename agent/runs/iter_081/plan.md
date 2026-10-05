# 요약

- **이번에 할 일:** iter_080의 미완료 MRI 자동 등급 검증을 Codex로 인계한다.
- **필요한 이유:** Claude 사용량 제한으로 중단됐으며, 비교 결과는 아직 없다. 기존 17개 반입 파일은 보존돼 있다.
- **확인할 기준:** 원 V8/E24·A/T/X·Q/C/gate와 정확도·영상 기여·종료 기준을 그대로 적용한다.
- **주의·다음:** 새 과학적 시도나 실패가 아니다. 결과는 `results/iter_081/`에 기록하고 full review에서 후속 투자 선택을 한다.

## 알림 맥락

- 연구: MRI 근거 선택·사용
- 데이터: 척추 sagittal T2 MRI와 부위별 등급 정답인 SPIDER
- 모델: 기존 MedGemma 1.5 영역 판독 SFT와 공유 ResNet18, 신규 학습 없음
- 과제: 대상 MRI와 자동 분류기의 등급을 받아 최종 Pfirrmann grade 1–5 출력
- 가설: 자동 판정 오류를 영상으로 교정할 수 있지만 판정 복사나 단순 gate로 설명될 수도 있다
- 질문: 자동 판독 결과가 틀렸을 때 VLM은 MRI를 보고 고칠 수 있는가?
- 변경: 실행 복구
- 연결: 같은 연구 질문 유지 · Claude 사용량 제한으로 중단된 구현을 Codex가 인계한다
- 작업: 기존 조건을 구현·검증하고 실제 출력 비교를 완료해 후속 투자 판단에 필요한 근거를 얻는다

# Current Understanding

기준 문서는 `agent/runs/iter_080/plan.md`, SHA256 `a5f5ad6689d7d9d19dddaa265c1e5bcb47d8b5d57f3e409fbcf0c7cc5293d4d3`다. 구현자는 원문 전체와 이번 amendment를 함께 읽는다. 원문의 과학적 조건은 모두 유지하며, 이번 문서의 변경은 담당·결과 경로·현재 코드 상태에 한정한다.

현재 HEAD와 중단 보존 SHA는 `be903b89e6b71b5a1cf3cbc35cebd05f03f2ff13`이다. `checkpoint.json`은 interrupted/unreviewed이며 보존 제외 파일은 없다. 현재 17개 파일은 iter_078 출처 blob과 모두 일치한다. 따라서 반입은 완료됐지만 iter_080용 조건 구현과 재사용 검증은 완료되지 않았다. `results/iter_080`은 존재하지 않는다. 원 세션·계획·중단 ref는 보존한다.

**유지:** GOAL, 동일 approach/track, SPIDER 분할·grade 의미·oracle anatomy·세 crop·checkpoint·prompt·parser·평가·종료 기준.

**변경:** 구현 담당을 Codex로 바꾸고 신규 산출물을 `research/results/iter_081/`에 저장한다. 자동 Claude 복귀 예약은 만들지 않는다. 공통 보고 파일명은 기존 호환 형식을 쓴다.

**미완료:** A/T/X 요청 구성, launcher 수정, 기술·재개 검사, V8 생성·M 선택, 조건부 E24 생성, 독립 평가와 보고다. 결과 부재를 모델 실패로 해석하지 않는다.

# Strategy Check / 연구 방향 판단

이번은 원 전략의 실행 인계다. 사용자 보완에 따라 연구 방향 재선정은 하지 않는다. iter_080의 선택은 기존 Q/C의 제한적 오류 상보성 → 복사·prior·실제 교정·단순 gate 충분성이라는 경쟁 설명 → A/T/X와 M 비교 → 자동 등급 검증의 투자 가치 판단이다.

iter_077의 영역 판독 신호와 분류기 대비 불확정, iter_078의 참고영상 추가 가치 미확보 때문에 재학습·참고 수·검색기 순회를 피하고 기존 실제 오류 검증을 선택한 판단을 유지한다. 이 과제는 iter_064 context 효과나 iter_077 F/R 차이의 직접 원인 분해가 아니다. iter_080에서 선택한 자동 판정 검증 후보를 그대로 잇는 것이며 코드 인계를 설명 진전으로 세지 않는다.

이번 리뷰에서 iter_064·077·078·079 원문과 이번 실제 결과를 연결해 관찰 유지/설명 진전/미검증/투자 보류를 구분한다. MRI 근거 사용 묶음의 **집중 / 한정 보완 / 투자 보류·전환** 중 하나를 실제로 선택한다. 인계 시점에 이 결정을 미리 내리거나 원 기준을 완화하지 않는다.

# Hypothesis

원 H1–H4를 유지한다. 실제 영상이 자동 판정 오류의 일부를 교정할 수 있는지, 판정 복사·영상 없는 prior인지, Q/C confidence gate로 충분한지, 현재 표본에서 불확정인지 구분한다. 다중 영상 결합이나 순수 내부 원인을 증명하는 실험은 아니다.

# Limitation Evidence / Correct Usage Checks

대상은 observed `spider-regional-reading-input-gap`이다. iter_077 유효 리뷰에는 blocking issue가 없고 공식 template·입력 hash·정답 연결·EOS/parser·checkpoint 선택 검증이 있다. F/R MAE 차이 0.29357은 별도 적응·해상도·context 등이 섞인 관찰이며 자동 조언 수용 실패의 근거로 전용하지 않는다. 이번은 diagnostic, method_stage=none을 유지한다.

고정 모델 revision과 R adapter, bf16·greedy·32 new tokens·whole-string grade parser를 유지한다. 비EOS 및 형식 오류는 invalid, 절대오차4로 처리한다. 모델 오답이나 자동 등급 복사를 기술 실패로 처리하지 않는다. 원 Pfirrman grade 1–5와 환자·ordinal 연결을 유지하며 ordinal을 임상 level로 바꾸지 않는다.

# Contribution Path / Baselines / Reuse

원 계획의 가까운 선행과 신규성 미확정 판단을 계승한다. 이번 인계를 위해 문헌 전수 조사를 반복하지 않는다. 직접 SFT Q와 동일 T24 supervision의 공유 분류기 C가 강한 대조다. 기존 자동 판정 제공 방식의 효과만으로 새 contribution을 선언하지 않는다.

같은 branch를 유지하므로 `reuse_iteration=0`, `reuse_assets=[]`다. 이미 있는 파일을 다시 반입하지 않는다. 현재 17개 파일은 `rf78_gen.py`, `rf78_vlm.py`, `rf78_launch.py`, `sp75_gen.py`, `sp75_vlm.py`, `sp75_metrics.py`, `sp75_data.py`, `g71_data.py`, `sp67_data.py`, `rsna_diag/__init__.py`, `rsna_diag/generate.py`, `rsna_diag/lora.py`, `rsna_diag/queue_lock.py`, `rsna_diag/geometry.py`, `rsna_diag/prompts.py`, `rsna_diag/mi19_mha.py`, `rsna_diag/mi19_render.py`다. 출처는 `b5426526827d986e9962f5439d5191bfbd064634`, 보존은 현재 HEAD에 연결한다.

iter_078 review.json의 승인은 고정 입력·Q/L/I/D 경로에 한정된다. 새 A/T/X는 실제 검증한다. `sp75_metrics.py`의 invalid=4·present-class 평균·환자 bootstrap 정의를 재사용한다. `rf78_eval.py`의 Combo, `sp77_stage`와 기존 비용 실행기는 사용하지 않는다. `generate.py` standalone main의 미반입 의존 경로를 호출하지 않는다.

# Proposed Experiment

## 입력과 범위

- manifest: `results/iter_075/data/manifest.json`.
- adapter: `results/iter_077/train/R_lr2e-4/epoch_16`.
- C probabilities/predictions: `results/iter_078/features.json`.
- query 연결: `results/iter_078/data/refs_V8.json`, `refs_E24.json`의 query 부분.
- 기존 Q: iter_077/078의 검증된 대상 단독 원시 출력.
- V8 8명·24개, E24 24명·held ordinal 2/4 47개만 사용한다. T24 추가 grade·E24 supervised 71개·F139는 열지 않는다.

기존 파일 존재는 확인했지만 새 실행 시 provenance·hash·ID 연결은 필요한 범위에서 검증한다. GT는 평가 파일로 분리하고 생성 요청에 넣지 않는다. 과거 산출물은 덮어쓰지 않는다.

## 조건과 baseline 고정

A는 원 PROMPT_R 앞에 원 계획의 문구 `An automated image classifier estimated Pfirrmann grade {c} for this target disc. This estimate may be correct or incorrect. Use the MRI to determine the final grade.`를 넣고 대상 세 crop을 제공한다. confidence·GT·환자 ID는 제공하지 않는다.

T는 같은 자동 등급과 grade 설명을 사용하되 이미지를 제거하고 `No MRI images are available in this condition.`을 명시한다. X는 A의 텍스트·자동 등급을 유지하고 영상만 split 내 동일 ordinal의 다른 환자로 교환한다. 숫자 patient ID순 다음 환자로 순환 배정하며 grade·모델 출력은 donor 선택에 쓰지 않는다. 구성 불가 행은 원 계획대로 사전 보고하고 공통 비교 집합을 표시한다.

V8에서 M 후보는 Q, C argmax, C posterior median, 그리고 C max probability가 τ 미만이면 Q를 사용하는 gate다. τ={0.2,0.4,0.6,0.8,1.01}, Q invalid이면 C argmax를 쓴다. posterior median은 누적확률이 처음 0.5 이상인 grade다. 선택 순서는 class-standardized MAE → 일반 MAE → VLM 호출 수 → 작은 τ다. A/T/X 결과로 후보나 threshold를 바꾸지 않는다. 기존 C_argmax도 별도 보고한다.

## 단계와 종료

1. **동작 확인:** V8 patient·ordinal순 첫 4개로 Q tensor·suffix 재현, A/X 세 영상과 동일 자동 등급, T 무영상, GT 차단·donor 연결·재개를 검사한다. 정답률 gate는 추가하지 않는다.
2. **가능성 탐색:** V8의 A/T/X 72건을 생성하고 기존 Q/C로 M을 고정한다. A의 유효 grade가 12/24 미만이면 원 계획의 인터페이스 부적합으로 종료한다. 그 외에는 작은 V8 효과 부호로 중단하지 않는다.
3. **규모 확대:** prompt·parser·donor·M·checkpoint·입력·코드·환경을 잠근 뒤 E24 A/T/X 141건을 생성한다. 기존 Q/C는 provenance가 일치할 때만 재사용한다.
4. **독립 확인:** 이번에는 없다. E24는 반복 개발 자료다. 학습·추가 seed·새 모델·표본 확대를 하지 않는다.

## GPU·비용·재개

구현 단계는 승인된 Codex danger-full-access에서 GPU 0,1을 사용한다. shell login을 끄고 실제 Python 경로를 기록한다. 각 worker 배정 직전 허용 GPU의 UUID·여유 메모리를 다시 읽고 여유순으로 배정한다. 동시 시작 예약량을 포함해 다른 프로세스 점유와 각 worker peak+2 GiB 여유를 확보한다.

iter_078 peak 10,465/10,393 MiB는 참고값이다. 개발 입력에서 이번 A/T/X peak를 측정한다. 안전하면 GPU당 worker 1개와 2개 구성을 짧게 비교한다. 안전하지 않으면 batch 확대 후보 하나를 검토하거나 비교 비용이 남은 작업의 예상 절약보다 큰 근거를 남긴다. 처리량·긴 출력 지연·OOM·전체 메모리·출력 정합성으로 선택하며 정답 점수로 실행 구성을 선택하지 않는다.

과거 V8/E24 생성 wall 121.06/190.02초를 이번 확정 시간으로 환산하지 않는다. 초기 예상은 적재·검증 포함 수십 분 단위이며 V8 실측 후 남은 141건의 wall-clock을 갱신한다. 임의 timeout을 추가하지 않는다.

request digest에 조건·자동 등급·donor·pixel·checkpoint·prompt·generation 설정을 포함한다. worker별 원시 token·EOS·parser·시간·입력 hash를 원자적으로 보존한다. 중복·누락·변조 거부·중단 재개를 기술 요청에서 확인한다. 기존 claim을 지우지 않는다. 모든 자식 종료와 출력 seal을 확인한 뒤 보고한다. cached Q/C 재사용 비용과 온라인 재실행 비용을 구분한다.

# Implementation Tasks for Claude

이 절의 실제 담당은 **Codex**다.

1. 기준 plan SHA와 현재 보존 파일·의존성, 기존 결과 provenance를 확인하고 새 결과 경로만 만든다. 이미 완료된 반입을 반복하지 않는다.
2. 기존 생성·저장 패턴에 A/T/X와 새 request manifest를 구현한다. 원 prompt·parser·조건을 변경하지 않는다.
3. launcher의 배정 직전 재확인·여유순 배정·허용 GPU 매핑을 수정한다. 현재 코드의 무조건적인 `pixel_values` 접근은 T에서 이미지 없는 processor 출력을 정상 처리하도록 수정하고 `n_images=0`을 검증한다. 가짜 영상으로 대체하지 않는다.
4. C 예측과 GT 분리, donor 독립성, T 무영상, invalid 처리, gate threshold·동률·fallback, 요청 digest 변조·중복·재개 fixture를 실행한다. Q와 A/X 입력 경로의 회귀 검사를 함께 한다.
5. V8 기술 확인·72건·M 고정 후 protocol을 잠그고 원 gate에 따라 E24 141건을 완료한다.
6. production 평가와 독립 계산으로 지표·오류 전환·bootstrap을 대조한다. 완료량·미완료·사용량·환경·실제 backend와 후속 판단 한계를 보고한다. 코드 커밋은 orchestrator가 관리한다.

# Evaluation (성공/실패 기준 포함)

원 기준을 그대로 적용한다. 주지표는 class-standardized MAE다. 일반 MAE, 두 등급 이상 오류, invalid, 자동 등급 일치율을 함께 보고한다. paired patient bootstrap 10,000회·seed7501을 사용하며 class 누락 replicate는 present-class 평균과 누락 횟수를 보고한다.

주비교는 A−M, A−T, A−X다. 영상 기여는 A−T와 A−X가 모두 개선 방향이고 각각 95% CI 상한<0일 때 지지한다. 최소 가치 있는 차이는 MAE 0.10이며 임상 MCID가 아니다.

- **양성 탐색:** A−M≤−0.10, CI 상한<0, 영상 기여 충족, A의 두 등급 이상 오류가 M보다 많지 않으면 기존 방식의 유망성을 보존한다. 신규 기여나 자동 확대 승인은 아니다.
- **method pilot 검토 후보:** 위 실용 기준은 미달하지만 영상 기여를 충족하고, C 오차를 A가 줄인 환자≥2명이며 Q가 C보다 좋은 항목에서 A가 C 쪽으로 이동해 Q보다 오차를 키운 환자≥2명이면 교정과 과도한 수용 공존을 보고한다. 단순 M 이후의 잔여 가치는 full review에서 판단한다.
- **음성:** 영상 교정 근거와 M 대비 최소 이득이 없으면 현재 자동 등급 검증 후보 투자를 종료한다. 복사 일치율만으로 내부 기전을 확정하지 않는다.
- **불확정:** 나머지는 후보 보류다. 결과를 본 뒤 사례·문구를 추가하지 않는다.

C 정답일 때의 훼손, C 오답일 때의 교정, Q/C 불일치에서의 이동을 모두 보고한다. 하위집단은 기존 출력으로 정의한 사후 개발 분석임을 표시한다. 원 실험 판정과 이후 연구 묶음 투자 선택을 분리한다. 리뷰는 사용자 보완에 따라 관찰 하나와 최소 개입에 집중할지, 새 근거가 있는 한정 보완을 할지, 범위를 명시해 보류·전환할지 결정한다.

# Risks / Checks

E24 반복 노출, 제한된 14개 Q/C 불일치, GT anatomy 지원, 세 crop의 임상 충분성 미확인, grade-only 적응과 조언 prompt 사이의 분포 차이를 유지한다. T의 prompt 차이와 X의 임의 donor 교환은 순수 원인 증명을 제한한다. X에 원 대상 정답을 연결한 결과를 donor의 임상 판독 정확도로 해석하지 않는다.

새 실행의 필수 검증 전에는 중단 checkpoint를 승인본으로 취급하지 않는다. 누락 자산이나 provenance 불일치는 필요한 경로에서 해결하며 무관한 범용 정비로 확대하지 않는다. 원 기록·결과·HF 캐시·기본 환경·다른 사용자 프로세스를 변경하지 않는다.

## 대규모 GPU 필요 후보

원 계획의 다기관 MRI·다양한 자동 도구 신뢰도 변화에 대한 multimodal post-training 후보를 보존한다. 이번에는 잔여 문제와 독립 자료 근거가 부족하므로 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

원 계획 agent/runs/iter_080/plan.md를 전부 확인했고 SHA256 a5f5ad6689d7d9d19dddaa265c1e5bcb47d8b5d57f3e409fbcf0c7cc5293d4d3가 사용자 지정값과 일치했다. 현재 research HEAD는 be903b89e6b71b5a1cf3cbc35cebd05f03f2ff13이며 working tree 변경은 없다. checkpoint.json은 interrupted/unreviewed이고 unpreserved_paths는 없다. 반입 17개 실제 파일의 git blob이 iter_080/reuse_manifest.json의 iter_078 출처 blob과 모두 일치한다. results/iter_080은 없으며 원 manifest·R adapter·features·V8/E24 refs 경로는 존재한다. claude_stream.jsonl에서 사용량 제한 종료와 당시 결과 부재를 확인했다.

iter_077/078 review.md와 review.json/code_assets, LIMITATIONS의 SPIDER 항목을 확인했다. 기존 metrics와 고정 입력 경로의 제한된 승인은 유지되지만 launcher는 worker 배정 직전 메모리 재확인·여유순 배정 수정이 필요하다. 실제 rf78_vlm.build_inputs와 rf78_gen.run_one은 pixel_values를 무조건 참조하므로 무영상 T를 구현할 때 이미지 없는 정상 processor 출력 처리가 필요하다. 이는 새 과학적 변경이 아니라 원 설계 실행에 필요한 수정이다. Combo evaluator와 sp77_stage·과거 비용 실행기는 사용하지 않는다. 새로운 문헌 조사·실험·파일 수정은 수행하지 않았다.
