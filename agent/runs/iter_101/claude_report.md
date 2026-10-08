# 요약

- **핵심 결과:** 별도 PadChest-GR train 28명에서 CURE 원출력을 만들었다. 자연 충돌은 24명 중 3명뿐이었고 셋 모두 reference가 흉수 양성인 환자였다. 이 6명(충돌 3 + 보존 대조 3)에서 사전 분기는 `negative_V_no_gain_hold_frozen_interface`가 나왔다. 현재 frozen 교정 인터페이스를 보류하는 쪽이며, 영상 교정 전체의 기각은 아니다.
- **근거:** 안전한 정답 환자 수는 K 6, A 2, T 4, V 3, W 0이다(최대 6명). V−T는 −1, V−W는 +3이다. 양성 기준(V−T≥3 등)은 한 개 항목도 충족하지 못했다. 음성 상태 충돌이 없어 양방향 개선 기준은 구조적으로 도달할 수 없었다.
- **주의:** T 출력 6건 중 5건이 문장 교정이 아니라 bbox JSON이었다. 따라서 T의 4/6은 형식 실패 출력이 내용상 안전으로 계산된 값이다. 형식이 정상인 출력만 보면 T 1, V 3(V−T +2)이고 여전히 양성 기준(+3)에는 못 미친다. 텍스트만 교정으로 충분한지는 이번에 검증되지 않았다.
- **다음:** GPT 리뷰에서 투자 판단을 한다. 같은 자료의 prompt·표본 조정은 계획대로 종료한다.

# Work Performed

- **자료 선정 (CPU):** 공식 train 3,185영상에서 흉수 양성·음성 문장 whitelist(assistant가 수동 검토, 전문의 검토 아님)를 만들었다.
  - 보호 manifest(iter_039/040의 held 포함)와 E96, D8, iter_100 환자·study·영상·pixel 중복을 제외했다. 보호 pixel 중복은 0이다.
  - 양성 34명·음성 40명이 남았고, 상태별 앞 2명(D4)과 다음 12명(S24)을 hash 순으로 잠갔다.
  - 풀 40영상의 contact sheet 2장을 실제 영상으로 열어 확인했다. 모두 정면 흉부 영상이고 제외는 없었다. PA/AP는 판별할 수 없다.
- **CURE 원출력:** D4 12건과 S24 72건을 생성했다. 전부 EOS 종료다.
- **자연 충돌 잠금:** S24 24명의 원출력에서 흉수 존재·부재 주장을 수동 판정표로 기록하고, 충돌은 규칙으로 도출했다. 이 판정은 교정 생성 전에 잠갔다.
  - 충돌 3명(S24 index 12, 16, 23)은 모두 양성 reference다.
  - 보존 대조는 충돌 집단과 같은 상태 구성으로 3명(index 5, 6, 15)을 골랐다.
  - W용 donor는 반대 상태 환자를 순환 배정했고 재사용은 없다.
- **교정 생성:** 동결 MedGemma 1.5(no LoRA)로 T(텍스트만), V(올바른 영상), W(반대 상태 환자 영상)를 만들었다. D4에서 12건, 본 실험에서 18건이다. 프롬프트는 D4 이전에 고정했고 오답을 본 뒤 바꾸지 않았다.
- **눈가림 판정:** K, A, T, V, W 30건을 blind ID로 묶어 assistant가 사실을 판정했다(원문 quote 연결). 이후 평가·독립 산술 검증·비용 요약을 수행했다.

# Files Changed

새 코드(모두 미추적): `report101_data.py`, `report101_cure.py`, `report101_gen.py`, `report101_req.py`, `report101_lock.py`, `report101_blind.py`, `report101_eval.py`, `report101_verify.py`, `report101_summary.py`, `report101_tests.py`, `report101_tech.py`. 기존 파일은 수정하지 않았다. 결과는 `results/iter_101/`에 저장했다.

# Commands / Experiments

모두 `CUDA_VISIBLE_DEVICES=0,1` 안에서 실행했다. 장시간 작업은 supervisor가 관리하고 `../experiment_wait.py --pid`로 기다렸다.

| 실행 | 결과 |
|---|---|
| `report101_data.py enumerate` / `extract` / `lock` | 성공. 첫 열거는 보호 manifest 규칙이 빠져 있어 `data_superseded_v0/`로 옮기고 규칙 추가 후 재열거했다. |
| CURE D4 (2 worker) | 성공. wall 110.7초. |
| CURE S24 (2 worker) | 성공. wall 442.0초. |
| `report101_lock.py` | 성공. 처음 1회는 leak check 오탐으로 실패했다. CURE 초안이 reference 문장과 우연히 같은 것을 누출로 잘못 센 것이며, 모델이 만든 입력 구간을 제외하도록 고쳐 재실행했다. |
| 교정 D4 w2 / w4 | 성공. wall 1168초 / 614초. 12건 token이 모두 같다. |
| 교정 main (4 worker) | 성공. 18건, wall 664.4초. |
| `report101_tech.py` | 공식 경로 대조 통과. |
| `report101_tests.py --cpu` | 13/13 통과. |
| `report101_tests.py --gpu` | 세션 종료로 중단됐다. CURE 재개는 끝까지 완료됐고 교정 재개는 수동으로 마무리했다(아래 Results 참조). |
| `report101_verify.py` | 최초 실행에서 `lock` 항목에 `pass` 키가 없어 실패했다. 키를 추가해 재실행하니 통과했다. |

# Results

**자료 (`results/iter_101/data/`)**
- 열거: 양성 34명, 음성 40명. 제외는 related_nonwhitelist 317건, 보호·이전 선정 중복 25건이다.
- S24의 과거 사용 기록: 양성 12명·음성 12명 모두 이전 반복 파일에 등장하며 `eval/summary.json`에 기록했다. 이전 train 노출은 독립 test라는 뜻이 아니며 CURE 사전학습 노출도 배제하지 못한다.

**자연 충돌 (`data/lock/selection.json`)**
- C=3(전부 양성), 음성 충돌 0, 모호 사례 0, M=6이다.
- D4에서도 충돌 1명을 관찰했다. D4는 평가에 포함하지 않았다.

**평가 (`eval/report.json`, 환자 6명, 최대 6)**

| | K | A | T | V | W |
|---|---|---|---|---|---|
| 안전한 정답 환자 | 6 | 2 | 4 | 3 | 0 |
| P 손상·명시 오류 환자 | 0 | 4 | 2 | 3 | 6 |

- V−T = −1(V만 안전 2, T만 안전 3), V−W = +3.
- 환자 bootstrap 95% CI: V−T [−5, 3], V−W [1, 5]. 표본이 작고 gate가 아니다.
- leave-one-out: V−T는 −2~0, V−W는 2~3.
- 민감도: 모호 atom 제외 시 V−T 0, 검증 불가 증가 제외 시 −2, 형식 정상 출력만 보면 V−T +2·V−W +3.
- 양성 기준 6개 항목은 모두 미충족이다(예: V−T≥3, 양방향 개선, V harm ≤ K·T). 단, `V−W≥2`는 충족했다.

**출력 형식 (판정표 기준)**
- T는 plain 1건, bbox JSON 5건이다.
- V는 plain 6건이다.
- W는 plain 4건, non-EOS의 반복 출력 2건이다.
- 이 중 non-EOS 최종 출력은 총 4건(T 2, W 2)이다.
- 형식 실패는 모델 오답과 분리해서 기록했다.

**비용·병렬화 (`eval/summary.json`)**
- CURE는 worker당 peak가 약 10.0GiB여서 GPU당 2개는 admission 불가라 GPU당 1개로 유지했다.
- 교정은 worker당 peak가 약 9.0GiB였다. 4 worker(GPU당 2개)가 GPU별 peak 17.3~17.9GiB로 admission을 통과했다. 2 worker 대비 wall 1.9배 빠르고 token은 같아 본 실험에 4 worker를 채택했다.
- 의미 검토·자료 감사 시간은 미측정이다.

**검증**
- 독립 산술 검증(`eval/verify.json`) 5개 항목이 통과했다. 검증 범위: blind 텍스트와 원 record의 일치, 모든 quote의 원문 존재, 충돌 재도출, donor/요청 영상 연결, 환자·조건별 safe 재계산, 분기 라벨, bootstrap/LOO.
- assistant 의미 판정의 임상적 정확성은 검증하지 않았다.
- 기술: text-only에서 `pixel_values`와 image token이 없음을 확인했다(`tech/tech_D4.json`). image+text는 공식 chat template과 tensor가 같고 adapter가 없다. 공식 무패치 generate token과 저장 출력이 4건 모두 일치한다.
- 런타임 CPU 검사(변조·동시 launcher·허용 GPU·소스 digest 변경 거부)는 13/13이다.
- 재개 검사 결과:
  - CURE: 12건을 중단→torn tail→재개로 완료했고 token이 원본과 일치한다.
  - 교정: 6건이 재개로 완료됐고 token이 일치한다. 이 교정 재개는 의도한 `--limit` 단계가 아니라 세션 종료로 실제 중단된 상태(완결 행 0건 + 주입한 torn tail)에서 재개한 것이다.

# Goal Progress / Reused Assets

- **시험 설정:** 동결 MedGemma 1.5의 frozen 교정 인터페이스(긴 프롬프트·두 영역 설명·단일 지시)는 이 6명에서 사전 기준을 충족하지 못했다. 같은 자료의 prompt·표본 조정은 종료한다.
- **연구 관찰:** 이번에 새로 확인한 것은 세 가지다.
  - 자연 충돌이 흔하지 않다(24명 중 3명, 모두 reference 양성).
  - 영역 설명을 받은 T는 문장 교정 대신 bbox JSON을 출력하는 경우가 많았다.
  - V/W는 초안과 영역 설명을 무시하고 자체 normal 보고서를 출력하는 경우가 많았다.
  - 이 중 V/W의 자체 normal 보고서 출력은 W에서는 영상 연결이 실제 모델 입력에 영향을 준다는 방증이다.
  - 이 현상들은 이 인터페이스 한정 관찰이며 일반적 능력·내부 원인을 입증하지 않는다.
- **연구 질문:** 영상이 충돌 해소에 추가 기여하는지는 아직 판단하지 못했다. T가 형식 실패로 대부분 무효여서 텍스트 편집 충분성도 미검증이다.
- **재사용:** 기존 Claude 보관본 코드는 반입하지 않았다(`reuse_assets` 없음). `pg39_data.load_inputs`와 `zip_index`/`open_image_zip`, `report86_common`, `rsna_diag.generate`(`load_image`·`build_inputs`·`build_inputs_text`·`generate`), `pg43_run.repair_tail`을 import로 사용했다. 사용한 부분의 기존 승인 범위와 이번 새 입력은 별도이며, 새 입력에서의 검증은 위 기술 검사로 수행했다.

# Problems

**현재 결론 무효 위험:** 없음. 입력·요청·digest 연결과 독립 산술이 일치했다.

**해석 한계 (결론의 범위)**
- 표본이 6명이라 한 명의 영향이 크다. CI는 gate가 아니다.
- 판정은 assistant가 했고 전문의 검토가 아니다. blind도 문체(JSON·`FINDINGS:` 머리말·`**Revised Report:**`)로 조건이 드러나 완전하지 않다.
- A의 일부 출력에서 지역 부정에 side label이 없어 "내부 충돌"로 읽은 판단이 있다(판정표 `note`에 기록).
- 판정표에서 T/V/W의 `unverifiable_added` 등 일부 분류는 모호하다.
- 투자 분기는 T의 JSON 형식 출력에 크게 의존한다(위 요약 참조).

**재사용 전 수정 필요**
- `report101_cure.py`와 `report101_gen.py`는 protocol에 소스 digest를 넣었으므로 편집하면 기존 완료 검증이 실패한다. 의도된 동작이다.
- 앞선 보관본에서 지적된 허용 GPU·동시 launcher·소스 변경 거부·변조 거부는 새 경로에서 실제 검사로 확인했다.
- `report101_tests.py --gpu`는 중단됐고, 결과 JSON은 수동으로 작성했다(일부 중단 시점이 계획과 다름을 `note`에 기록했다).

**추후 개선:** 의미 판정 정규화는 이 결론에 영향을 주지 않으므로 하지 않았다.

# Recommendation to GPT

- 계획의 사전 분기상 `negative_V_no_gain_hold_frozen_interface`다. 보류 범위는 "이 frozen 교정 인터페이스, 이 자료, 이 6명"으로 한정하는 것을 권한다.
- 별개로, 이번 실행에서 보이는 두 가지 인터페이스 문제(T의 bbox JSON 출력, V/W의 초안·notes 무시)는 모델 내용 오류가 아니다. 영상 가치 질문을 이어가려면 같은 자료가 아니라 짧은 텍스트 입력이나 구조화 출력 같은 다른 인터페이스에서의 최소 비교가 필요하다. 이는 계획이 종료한 "같은 자료의 prompt 조정"과 구분해야 하므로 별도 근거로 결정해 주기 바란다.
- 자연 충돌 빈도(24명 중 3명, 음성 상태 0)는 개발 집단 한정 관찰이며 일반 빈도로 쓰지 않는다.

SELF_CHECK: FAIL
SUMMARY: PadChest-GR train 28명 CURE 원출력→자연 충돌 3명(모두 양성)+대조 3명에서 T/V/W 교정을 비교해 사전 분기는 V가 T를 개선하지 못함(안전 정답 K6/A2/T4/V3/W0, V−T=−1, V−W=+3)이었으나, T의 5/6이 bbox JSON 형식 실패라 텍스트 편집 충분성은 미검증이다(FAIL 사유: GPU 재개 테스트 일부가 중단돼 수동 마무리).