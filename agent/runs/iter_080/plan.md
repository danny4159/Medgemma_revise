# 요약

- **이번에 할 일:** 기존 척추 MRI 자동 등급을 VLM에 제공하고, 대상 영상으로 교정하는지 검사한다.
- **필요한 이유:** 기존 두 모델의 전체 오차는 비슷하지만 서로 다른 오류가 있다. 참고영상의 추가 가치는 없었으며 자동 판정의 검증은 아직 시험하지 않았다.
- **확인할 기준:** 실제 영상의 교정 기여, 맞는 자동 판정의 훼손, 단순 confidence gate 대비 정확도다.
- **주의·다음:** 반복 개발 자료의 탐색이다. 기존 방법으로 충분하면 보존하고, 영상 교정 근거가 없거나 불확정이면 현재 후보를 종료한다.

## 알림 맥락

- 연구: MRI 근거 선택·사용
- 데이터: 척추 sagittal T2 MRI와 부위별 등급 정답인 SPIDER
- 모델: 기존 MedGemma 1.5 영역 판독 SFT와 공유 ResNet18, 신규 학습 없음
- 과제: 대상 MRI와 자동 분류기의 등급을 받아 최종 Pfirrmann grade 1–5 출력
- 가설: 자동 판정의 오류 일부를 영상으로 교정할 수 있지만 판정 복사로 설명될 수도 있다
- 질문: 자동 판독 결과가 틀렸을 때 VLM은 MRI를 보고 고칠 수 있는가?
- 변경: 구체화
- 연결: LUMIERE의 정답 연결 실패 후, 정답·영상·자동 분류기가 이미 검증된 SPIDER에서 같은 근거 검증 질문을 시험한다
- 작업: 실제 영상·영상 없음·환자 영상 교환과 단순 gate를 비교해 후속 투자 여부를 결정한다

# Current Understanding

iter_079는 자료 gate에서 종료됐으며 모델 가설을 검증하지 않았다. LUMIERE의 다른 RANO 과제로 바꾸거나 OAI·MR-RATE 확보를 재개하지 않는다.

iter_077에서 영역 직접 SFT Q와 공유 분류기 C의 E24 held class-standardized MAE는 0.77690/0.77619였다. iter_078의 참고영상 I는 0.82619로 추가 가치 기준에 미달했다. 이 판정은 유지한다.

이번 계획의 읽기 전용 재분석에서 Q/C 불일치는 14/47개였다. Q가 절대오차를 줄인 항목은 6개, C가 줄인 항목은 8개다. 정답을 알고 둘 중 낮은 오차를 고른 분석용 oracle은 0.58786이었다. 이는 상보성의 사후 탐색이며 실제 선택기의 성능이나 임상적 개선 가능성을 보장하지 않는다.

유지할 것은 기존 환자 분리, grade 의미, oracle anatomy, 세 crop, checkpoint와 과거 판정이다. 보류할 것은 단일 판독 추가 학습, 참고 수·검색기·seed 변경과 독립 reserve 개방이다. 새 결과는 `results/iter_080/`에만 저장한다.

# Strategy Check / 연구 방향 판단

상위 질문은 필요한 근거를 선택하고 사용하는가이다. 해결된 질문은 현재 적응 R에 기본 영상 대응 신호가 있다는 것이다. 남은 설명은 자동 등급 복사, 영상 없는 prior, 실제 영상 교정, 단순 confidence gate의 충분성이다.

현재 방법의 추가 학습은 VLM의 추가 사용 가치를 확보하지 못한 채 비용을 늘린다. F/R 입력 차이의 원인 분해는 유효하지만 지금 교정하려는 자동 오류와 직접 연결되지 않는다. 새 자료 탐색은 다시 정답 연결 부담을 만든다. 따라서 기존 실제 오류에 대한 한정 검증을 우선한다.

이번 결과가 바꿀 결정은 **자동 판정과 영상 사이의 선택을 최소 방법 연구로 발전시킬 근거가 있는가** 하나다. 단순 대안으로 충분하거나 영상 교정 신호가 없으면 해당 후보를 끝낸다. 이 실험은 필수적인 다중 영상 결합을 검증하지 않는다.

타 계열 비교는 이번에는 보류한다. 현재 grade 과제에서 같은 supervision으로 적응한 다른 계열 checkpoint가 없고, 먼저 실제 오류 검증의 가치부터 판단해야 한다. 기존 Qwen의 다른 MRI 결과를 이 과제의 비교로 전용하지 않는다. 큰 방법 투자나 광범위한 주장 전에는 타 계열 적응 및 가까운 해결책 비교가 필요하다.

이력에서 자료 연결·실행 복구가 큰 부담이었다. 이번에는 기존 결과와 실행 경로를 선별 재사용한다. 누적 비용 비율이나 절감률은 측정하지 않았으므로 주장하지 않는다.

# Hypothesis

- H1: 자동 등급이 틀린 일부 사례에서 실제 대상 영상이 교정에 기여한다.
- H2: 최종 답변은 자동 등급 또는 등급 prior에 주로 의존하며 영상 제공의 추가 가치가 없다.
- H3: 상보성은 있지만 기존 Q/C confidence gate로 충분하다.
- H4: 현재 표본·checkpoint에서는 구분이 불확정이다. 고정 탐색 종료 후 후보를 보류한다.

# Limitation Evidence / Correct Usage Checks

`spider-regional-reading-input-gap`의 원문과 iter_077 리뷰의 evidence·usage checks를 확인했다. 이는 현재 자료에서 입력별 성능 차이가 있다는 observed 근거이며 자동 조언 수용 실패의 증거는 아니다. 이번은 diagnostic, method_stage=none이다.

원 `Pfirrman grade` 1–5와 환자·ordinal·영상 연결을 유지한다. ordinal을 임상적 척추 level로 바꾸지 않는다. 위치는 GT anatomy 지원이며 실제 자동 위치 검출의 성능을 주장하지 않는다. 세 crop의 임상적 충분성도 확정하지 않는다.

공식 chat template, 고정 모델 revision, 기존 R adapter, bf16·greedy·32 new tokens 및 whole-string grade parser를 유지한다. 비EOS·형식 오류는 invalid이며 오차4로 처리한다. 모델의 오답은 기술 실패가 아니며 100% 정답 gate를 만들지 않는다.

# Contribution Path / Baselines / Reuse

[VIPER](https://arxiv.org/html/2509.21979v7)은 의료 VLM의 사회적 압력과 영상 우선 답변을, [PTA](https://papers.miccai.org/miccai-2026/0807-Paper4746.html)는 별도 auditor의 검증·교정을 다룬다. 자동 판정 교정이나 evidence-first 지시 자체를 신규성으로 부르지 않는다. 이번에는 실제 분류기의 자연 오류와 유용한 조언이 섞인 조건을 확인한다. 선행 대비 미해결 조건은 아직 입증되지 않았다.

강한 대조는 기존 직접 SFT Q와 공유 분류기 C다. 둘은 같은 T24 70개 grade supervision을 사용했다. V8에서 다음 후보 중 M을 선택한다: Q, C argmax, C posterior median, 그리고 max C probability가 τ 미만이면 Q를 쓰고 그 외에는 C argmax를 쓰는 gate. τ는 {0.2,0.4,0.6,0.8,1.01}로 고정한다. Q invalid이면 gate는 C argmax를 사용한다. 선택 순서는 class-standardized MAE, 일반 MAE, VLM 호출 수, 작은 τ다. posterior median은 누적확률이 처음 0.5 이상인 grade다.

iter_078에서 선택된 C_argmax 결과도 별도로 보고한다. 새 gate가 선택됐다고 기존 비교군을 숨기지 않는다. T는 영상 없는 대조, X는 영상 교환 진단이며 실용 방법이 아니다. GT 최소오차 선택은 oracle로 분리한다.

JSON reuse_assets의 17개 파일은 실제 SHA의 blob과 import 연결을 확인했다. 현재 브랜치에는 없으므로 선별 반입한다. `rf78_eval.py`의 알려진 Combo 결함 경로는 사용하지 않는다. 기존 `sp77_stage`와 비용 실행기도 사용하지 않는다. 과거 자료를 다시 렌더하거나 학습기를 재구현하지 않는다.

# Proposed Experiment

## 1. 자료와 기존 출력 연결

- manifest: `results/iter_075/data/manifest.json`.
- R adapter: `results/iter_077/train/R_lr2e-4/epoch_16`.
- C 확률·예측: `results/iter_078/features.json`.
- 요청 연결: `results/iter_078/data/refs_V8.json`, `refs_E24.json`의 query 부분만 사용한다.
- Q: iter_077/078에서 검증된 대상 단독 원시 출력.
- 개발 선택: V8 8명·24개.
- 최종 탐색: E24 24명·held ordinal 2/4 47개.

T24 추가 grade, E24 supervised 71개, F139는 열지 않는다. E24는 반복 개발 집단임을 모든 결과에 표시한다. 대상 grade는 평가 파일로 분리하고 생성기에 전달하지 않는다. C 예측과 대상 grade를 혼동하지 않는 fixture를 둔다.

## 2. 세 신규 조건

A는 기존 PROMPT_R 앞에 `An automated image classifier estimated Pfirrmann grade {c} for this target disc. This estimate may be correct or incorrect. Use the MRI to determine the final grade.`를 넣고 같은 대상 세 crop을 제공한다. 원 grade 설명과 한 자리 답변 요구는 유지한다. confidence 값·GT·환자 ID는 제공하지 않는다.

T는 A의 자동 등급과 grade 설명을 유지하되 이미지를 제거하고 `No MRI images are available in this condition.`을 명시한다. 이미지가 있다고 거짓 안내하지 않는다. A−T는 입력 유무에 따른 대조이며 순수한 내부 원인의 증명은 아니다.

X는 A와 텍스트·자동 등급·영상 수가 같고 세 crop만 다른 환자의 것으로 바꾼다. split 안에서 동일 ordinal의 환자를 숫자 ID순으로 정렬한 뒤 다음 환자로 순환 배정한다. grade·모델 출력은 donor 선택에 쓰지 않는다. 다른 ordinal이나 자기 환자로 대체하지 않는다. 구성 불가능한 행은 사전 보고하고 A/T에서도 같은 비교 집합을 표시한다.

X는 원 대상 정답에 대한 영상 의존성 대조다. donor 영상의 임상 정답을 원 대상 정답으로 취급하거나 X 자체의 판독 정확도로 해석하지 않는다. A−X와 답변 변화율을 함께 보고한다.

## 3. 동작 확인 → 가능성 탐색

V8 patient·ordinal순 첫 4개를 기술 입력으로 고정한다. 기존 Q의 tensor·suffix 재현, A/X의 세 영상, T의 무영상, 동일 C 등급, target GT 차단을 검사한다. 모델이 자동 등급을 따르거나 틀리는 것은 실행 gate 실패가 아니다.

V8 24개에서 A/T/X 72건을 생성한다. M은 V8의 기존 Q/C와 정답만으로 선택하며 A/T/X 성능에 따라 후보나 threshold를 바꾸지 않는다. 새 prompt도 V8 성능을 보고 수정하지 않는다.

A가 24개 중 12개 미만에서 유효 grade를 출력하면 현재 교정 인터페이스의 부적합으로 종료한다. 그 외에는 작은 V8 효과 부호를 확대 gate로 쓰지 않고 고정 E24로 진행한다. 추가 141건으로 기존 전체 개발 비교를 완성하는 것이 목적이다.

## 4. 규모 확대와 독립 확인 경계

V8 종료 후 prompt·parser·donor mapping·M·checkpoint·입력·코드·환경을 잠근다. E24 held 47개에서 A/T/X 141건을 생성한다. 기존 Q/C는 원시 출력과 provenance가 일치할 때만 재사용한다. 기술 차이가 있으면 원인을 먼저 확인하며 유리한 출력만 교체하지 않는다.

이번의 규모 확대는 V8에서 E24로의 이동뿐이다. 학습·추가 seed·새 모델·표본 확대는 없다. 독립 확인은 실시하지 않으며, 후속 리뷰가 필요성을 별도 판단한다.

## 5. GPU·비용·재개

각 worker 시작 직전 nvidia-smi로 허용 GPU 0/1의 UUID·여유를 확인하고 여유가 큰 장치부터 배정한다. 다른 프로세스는 변경하지 않는다. A/T/X의 독립 요청을 두 GPU에 나눈다.

기존 iter_078의 peak 약 10.4 GiB/worker는 참고값이다. 이번 3영상·무영상 조건의 peak를 측정하고 worker당 2 GiB 여유를 포함한다. GPU당 두 worker가 안전하게 들어가면 개발 요청으로 1개 대비 처리량을 비교한다. 메모리가 부족하면 batch 확대 후보 하나를 확인하거나 검증 비용이 남은 작업의 예상 절약을 넘는 이유를 기록하고 기존 구성을 쓴다. 출력 정합성을 확인하지 않은 batch는 사용하지 않는다.

213건의 생성은 과거 141건 wall 190.02초보다 요청 수가 많고 영상은 적지만, 이를 선형 환산한 확정 비용으로 쓰지 않는다. 초기에는 모델 적재·검증을 포함해 수십 분 단위의 불확실한 추정으로 두고, V8에서 조건별 처리량·적재 시간·peak를 측정한 뒤 남은 141건의 예상 wall-clock을 갱신한다. timeout은 설정하지 않는다.

신규 학습 checkpoint는 없다. 요청별 원시 token·EOS·parser·입력 hash와 실행 시간을 worker별 파일에 원자적으로 보존한다. 조건·C 등급·donor·checkpoint·prompt를 request digest에 포함한다. claim·worker lock·완료 seal로 중복·누락을 검사하고 기술 요청에서 중단 재개를 확인한다.

비용에는 새 생성의 호출 수·token·wall·GPU별 점유를 기록한다. 기존 C/Q 산출물을 재사용한 비용과 온라인으로 C/Q를 다시 실행해야 하는 비용을 구분한다. 이번에는 cached 결과의 비교만으로 전체 시스템 비용 우위를 선언하지 않는다.

# Implementation Tasks for Claude

1. 선별 반입 파일과 기존 결과 provenance를 확인하고 새 결과 경로를 만든다.
2. 기존 생성·저장 코드를 바탕으로 iter_080 조건과 request manifest를 추가한다. 새 범용 실행기를 만들지 않는다.
3. rf78 launcher의 배정 직전 메모리 확인·여유순 배정을 수정하고 새 경로에서 검증한다.
4. grade와 자동 예측의 분리, donor 독립성, T 무영상, parser/invalid, gate 동률·fallback, 중복·재개 fixture를 실행한다.
5. V8 기술 확인·본출력·M 선택 후 protocol을 잠그고 조건부 E24를 완료한다.
6. production 평가기와 독립 스크립트로 주요 지표·오류 전환·환자 bootstrap을 대조한다. 자식 종료와 출력 완전성을 확인한 뒤 보고한다.

# Evaluation (성공/실패 기준 포함)

주지표는 기존 class-standardized MAE다. 일반 MAE, 두 등급 이상 오류, invalid, 자동 등급 일치율도 보고한다. 환자 paired bootstrap 10,000회·seed7501을 사용하고 class가 빠진 replicate는 기존 present-class 평균 정의와 그 횟수를 보고한다.

주비교는 A−M, A−T, A−X다. 영상 기여는 A−T/A−X가 모두 개선 방향이고 각각 95% CI 상한이 0 미만일 때 지지된다고 판정한다. 임의 donor 교환의 한계와 T의 prompt 차이를 함께 적는다. CI가 겹친다는 이유만으로 동등성을 선언하지 않는다.

최소 가치 있는 정확도 차이는 MAE 0.10으로 고정한다. 이는 이번 개발 자료의 분석용 Q/C oracle 여지 약 0.188의 절반 정도를 회수해야 추가 VLM 검증을 검토할 가치가 있다는 투자 기준이며 임상적 MCID가 아니다.

- **기존 방식의 유망성:** A−M≤−0.10, paired CI 상한<0, 영상 기여 기준 충족, A의 두 등급 이상 오류가 M보다 많지 않으면 기존 자동 등급 제공 방식의 양성 탐색으로 보존한다. 새 방법 기여로 부르지 않는다.
- **최소 방법 pilot 검토 가능:** 위 실용 기준은 미달하지만 영상 기여 기준을 충족하고, A가 C의 오차를 줄인 환자가 2명 이상이며 반대로 Q가 C보다 좋은 항목에서 A가 C 쪽으로 이동해 Q보다 오차를 키운 환자도 2명 이상이면 교정과 과도한 수용이 공존하는 후보로 보고한다. 단순 gate M의 전체 성능과 비교해 실제 잔여 가치가 있는지 full review가 판단한다. 이것은 method 자동 승인이 아니다.
- **음성:** 영상 교정 근거가 없고 M 대비 최소 이득도 없으면 현재 자동 등급 검증 후보의 투자를 종료한다. A≈T 또는 높은 C 일치율은 복사 설명의 단서이며 내부 기전 확정은 아니다.
- **불확정:** 나머지는 현재 후보를 보류한다. 작은 오류 집단의 비율과 CI를 그대로 보고하며 사례를 추가하거나 문구를 바꾸지 않는다.

C가 맞을 때의 A 훼손, C가 틀릴 때의 A 교정, Q/C 불일치에서의 이동을 모두 보고한다. 기존 출력으로 정의한 하위집단은 사후 개발 분석임을 명시한다. 성공 사례만 제시하지 않는다. 기술 무효와 유효한 음성·불확정을 구분한다.

# Risks / Checks

- 상보성은 14개 불일치에 근거하며 표본이 작다. oracle 여지를 실현 가능한 개선으로 오해하지 않는다.
- E24는 반복 개발 자료다. 과거 결과를 보고 선택한 이번 질문을 독립 확인으로 부르지 않는다.
- 교정 prompt는 기존 grade-only 적응과 다른 입력 분포다. 실패를 일반적인 영상 무사용으로 확대하지 않는다.
- 자동 grade는 원래 모델의 출력이다. 전문가 판단이나 정답으로 소개하지 않는다.
- 영상 교환은 원인 분리용이며 실제 임상 운영이나 잘못 연결된 환자 영상의 사용을 제안하는 것이 아니다.
- 현재 limitation을 자동 승격하지 않는다. 새 observed 주장은 실제 출력·사용법 검사·full review 뒤 판단한다.
- OAI·MR-RATE 대기와 LUMIERE 추가 감사를 재개하지 않는다. 기존 원본과 결과를 보존한다.

## 대규모 GPU 필요 후보

다기관 MRI·다양한 자동 도구의 신뢰도 변화에 대해 영상 우선 판단과 유용한 조언 수용을 함께 학습하는 대규모 multimodal post-training은 장기 후보로 남긴다. 현재는 독립 자료와 잔여 문제의 근거가 부족하므로 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

### 새로 확인한 것

- `agent/GOAL.md`, INDEX의 접근법 기록, iter_077~079 원 리뷰, iter_078 원 계획, LIMITATIONS의 SPIDER 항목, CODE_ASSETS 및 해당 review.json의 모듈 판정을 확인했다.
- iter_079는 LUMIERE의 명시적 음성과 비교 검사 연결을 확보하지 못한 자료 실패다. 자동 판정 검증 능력은 미실험이다.
- `results/iter_077/eval/per_row.json`의 held 47개를 읽기 전용으로 재계산했다. Q/C 불일치 14개, Q가 낮은 절대오차 6개, C가 낮은 절대오차 8개, Q만 정확 4개, C만 정확 7개다. C/Q/oracle 최소오차의 class-standardized MAE는 0.77619/0.77690/0.58786이다. 이 분석은 이미 노출된 개발 자료의 사후 투자 판단이며 새 독립 증거가 아니다.
- `results/iter_078/features.json`에 기존 C 확률과 예측이 있고, V8/E24 요청에 대상 PNG 연결이 있다. 새 자료 확보 없이 실제 자동 등급을 사용할 수 있다.
- 현재 research 브랜치의 추적 파일에는 SPIDER 실행 모듈이 없으나 iter_078 SHA에 필요한 17개 blob이 보존돼 있다. import 의존성을 확인했다.

### 가까운 선행과 의미

[VIPER 논문 v7](https://arxiv.org/html/2509.21979v7)은 사회적 압력 아래 의료 VLM의 답변 변화와 정보 정제·영상 우선 답변을 다룬다. [PTA의 MICCAI 원문 페이지](https://papers.miccai.org/miccai-2026/0807-Paper4746.html)는 초음파에서 별도 auditor의 검증·교정을 다룬다. 따라서 자동 판정 교정이나 evidence-first prompt 자체는 새 기여가 아니다. 이번 질문은 실제 분류기의 맞고 틀린 판정이 섞인 조건에서 영상 교정과 유용한 조언 수용이 동시에 가능한지다. 선행이 이 조건을 해결하지 못했다고 단정하지 않는다.

### 판단

현재 자료에서 교정 가능한 오류의 상보성이 제한적으로 존재한다. 그러나 47개 중 Q가 더 나은 경우가 6개뿐이므로 큰 학습 투자에는 부족하다. 한 번의 고정 출력 비교로 영상 교정 가능성과 단순 gate 충분성을 함께 확인하는 것이 새 자료 준비나 참고영상 튜닝보다 판단 가치가 높다. 이번은 diagnostic이며 신규 한계 등록이나 방법 pilot 진입은 후속 리뷰의 실제 출력 근거에 달려 있다.
