# 요약

- **핵심 결과:** 기존 MSD FLAIR E48 출력을 새 생성 없이 위치별로 다시 분석했다. DENSE의 위치 표준화 BA는 0.7167, 95% CI [0.6141, 0.8139]이다. 하한이 0.5를 넘어 사전 기준으로는 **양성**이다.
- **근거:** D에서 고른 위치 규칙의 위치 표준화 BA는 정의상 0.5이므로 DENSE와의 차이는 +0.217이다. 하지만 전체 BA 차이는 DENSE−규칙 +0.026, CI [−0.053, 0.110]으로 불확정이다. DENSE는 12 FN과 38 FP를 냈고 오류가 33개 case에 퍼져 있다.
- **미검증·주의:** 사후 개발 분석이다. 양성은 위치 index만의 설명을 넘는 연관일 뿐, 병변 인과 증명이나 임상 신뢰도가 아니다. 위치 표준화 CI는 희소 class 때문에 10,000회 중 8,388회에서만 정의됐다.
- **다음:** 전문 segmentation+OR 최소 대조를 별도 계획으로 권고한다. method pilot과 학습은 자동 승인하지 않는다.

# Work Performed

- 기준 plan.md와 plan.json, 기존 `msd56_eval.py`, `msd56_breakdown.py`, `msd56_run.py`의 parser와 record 형식을 확인했다.
- iter_056 D/E 본 실행 출력만 읽는 CPU-only 분석 `msd57_analysis.py`를 새로 작성했다. 기존 코드는 수정하지 않았다.
  - 입력 hash를 `input_manifest.json`에 잠그고, 재실행 시 hash가 다르면 거부한다.
  - 원시 `suffix_text_raw`를 `parse_answer`로 다시 해석해 저장 answer와 대조한다.
  - 요청↔record, record↔protocol digest, cond_map↔GT 행렬, 요청 영상 z 번호↔GT slice, D/E case 분리, slab 0~5를 강제 검증한다.
  - D 정답만으로 64개 위치 규칙 중 BA 최대를 고르고, E 계산 전에 `position_rule_D.json`으로 저장한다.
  - seed57·10,000회 case-cluster bootstrap을 쓴다. 같은 재표집을 모든 조건과 baseline에 공통 적용한다. 지원 위치에서 class가 사라진 replicate는 undefined로 제외하고 재가중하지 않는다.
- `test_msd57.py`로 fixture, 변조 거부, 원시 jsonl 직접 count 검산을 수행했다.

# Files Changed

- 추가: `msd57_analysis.py`, `test_msd57.py`.
- 새 결과: `results/iter_057/analysis/` (`input_manifest.json`, `position_rule_D.json`, `report.json`, `per_row_E.json`), `results/iter_057/tests/` (`fixtures_msd57.json` 및 변조 검사용 임시 복사본).
- `results/iter_056/`과 기존 코드는 변경하지 않았다.

# Commands / Experiments

- `python msd57_analysis.py --out-dir results/iter_057/analysis` — 성공. 내부 회귀 assert가 모두 통과했다.
- `python test_msd57.py` — 성공, 23/23 PASS.
- GPU·새 생성·학습·다운로드는 0이다. 실행 시간은 아래와 같다.

| 항목 | 시간 |
|---|---|
| bootstrap 추정 (첫 100회 처리량 기준) | 2.53 s |
| bootstrap 실측 | 0.22 s |
| 전체 CPU | 0.47 s |

# Results

결과 파일은 `results/iter_057/analysis/report.json`이다.

**회귀 검사 (모두 일치)**
- E 고유 요청 766개, 조건 행 1152개, D 고유 요청 97개, D 36구간, E 288구간.
- 조건별 TP/FN/TN/FP와 BA가 iter_056 `report.json`과 일치한다.
- seed56 CI가 DENSE의 [0.73186, 0.82170]과 일치한다.
- E 자체 64규칙 최댓값 0.761664와 위치 다수 class 규칙 0.719336을 재현했고, 후자는 상한이 아님을 표기했다.
- U8가 놓친 DENSE 정답 양성 5건 중 완전 annotation 누락은 0건이다.

**D 위치 규칙**
- 규칙은 slab0~5에 대해 `[0,1,1,1,0,0]`, 즉 slab1·2·3만 PRESENT로 예측한다. D BA는 0.8125이고 동률은 2개였다. D의 slab별 양성 수가 [2,5,6,6,4,1]/6이라 규칙의 불안정성은 크다.
- 이 규칙의 E 전체 BA는 0.7501이다.

**E 지원 위치**
- 지원 위치는 slab 0, 1, 2, 4, 5이다. slab3은 음성이 없어 제외했고 별도 보고했다.

**BA 비교**

| 조건 | 전체 BA | 위치 표준화 BA, 95% CI |
|---|---|---|
| DENSE | 0.7763 | 0.7167 [0.6141, 0.8139] |
| U8 | 0.7686 | 0.7665 [0.6860, 0.8439] |
| O8 | 0.7528 | 0.7368 [0.6537, 0.8170] |
| TEXT | 0.5 | 0.5 |
| D 규칙 | 0.7501 | 0.5 |

- 위치 표준화 BA의 CI는 8,388/10,000 replicate에서만 계산됐다. 나머지는 지원 위치(특히 slab0 양성 3개, slab2 음성 2개)의 class가 사라져 undefined였다.
- D 규칙의 위치 표준화 BA가 0.5인 것은 설계상 필연이다. 위치별 상수 예측은 위치마다 sens+spec=1이다. 따라서 "DENSE의 위치 표준화 BA−0.5"와 "DENSE−D 규칙"은 같은 정보다.

**전체 BA 차이 (CI는 모두 0을 포함)**

| 비교 | 차이 | 95% CI |
|---|---|---|
| DENSE−D 규칙 | +0.026 | [−0.053, 0.110] |
| U8−D 규칙 | +0.019 | [−0.060, 0.096] |
| U8−DENSE | −0.008 | [−0.059, 0.037] |

- 위치 표준화 U8−DENSE는 +0.050, CI [−0.015, 0.135]이다.
- O8−U8 위치 표준화 차이는 −0.030, CI [−0.052, −0.008]이다.

**위치별 DENSE** (TP/P, TN/N)

| slab | TP/P | TN/N |
|---|---|---|
| 0 | 2/3 | 38/45 |
| 1 | 27/33 | 10/15 |
| 2 | 43/46 | 1/2 |
| 3 | 46/48 | 음성 없음 |
| 4 | 33/33 | 9/15 |
| 5 | 26/26 | 3/22 |

- slab5의 특이도는 3/22로 낮다. 이 위치의 PRESENT 편향이 큰 FP 원천이다.

**잔여 오류**
- DENSE는 12 FN(11 case)과 38 FP(28 case)를 냈다. 오류가 있는 case는 33개이고 2건 이상 오류 case는 16개이다.
- U8는 13 FN과 39 FP로 30개 case에 오류가 있다.
- 오류 겹침은 다음과 같다. 각 항목의 n_where_rule_D_correct(D 규칙이 맞힌 수)는 `report.json`의 `error_overlap`에 있다.

| 구분 | 구간 수 | case 수 |
|---|---|---|
| 둘 다 오답 | 36 | 26 |
| DENSE만 오답 | 14 | 14 |
| U8만 오답 | 16 | 13 |

- 사전 판정은 DENSE 위치 표준화 BA가 0.5를 넘고 CI 하한도 0.5를 넘으므로 양성이다. 오류 case가 5개 이상이라는 기준도 충족한다.

**검증 검사 (23/23)**
- 변조 거부 7종: 저장 answer가 raw와 다름, record 누락, record 중복, protocol 변조, cond_map rid 교체, cond 행 누락, manifest hash 변조.
- 독립 직접 count: 조건×slab별 TP/FP, 규칙 BA, DENSE 위치 표준화 BA가 분석 결과와 일치한다.

# Goal Progress / Reused Assets

- **목표 진전:** 전체 BA의 이득 중 위치 prior로 설명되는 부분과 동일 위치 안의 구별 신호를 정량화했다. 위치 규칙 대비 전체 BA 이득은 미미하다. 위치 통제 후 신호는 CI 하한이 0.5를 넘지만 폭이 넓다. 두 관찰은 양립한다.
- **미검증:** 병변 자체의 인과적 사용, 환자 독립성, 전문 모델 대비 효용, 직접 SFT 대비 가치, 신규 방법 효과, 독립 확인.
- **재사용:** `msd56_run.py`는 parser와 `read_jsonl`만 import했다. `msd56_eval.py`와 `msd56_breakdown.py`는 호출하지 않고 정의를 참고해 재구현했다. iter_056 출력은 읽기만 했다. 승인된 `reuse_assets`는 없다(`[]`).

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 필수 수정:** 없음. 이번 범위 밖의 launch, Qwen, sanity 경로 결함은 건드리지 않았다.
- **해석 한계 (추후 개선):**
  - 위치 표준화는 slab0 양성 3개, slab2 음성 2개의 희소 class에 크게 의존한다. 동일 가중이라 이 위치들이 지표를 흔든다.
  - D 규칙은 D6로 정해져 안정성을 주장할 수 없다.
  - 정답은 BRATS annotation 존재이며, FP를 임상 오진으로 해석하지 않는다.
  - slab5에서 DENSE의 FP가 몰려 있어(19/22), 위치 표준화 BA의 신호가 slab5 이외의 위치에 의존한다. 이는 위치별 표에만 있고 별도 가중 분석은 하지 않았다.
  - 위치 표준화 평균에서 slab3을 제외했고, 이 위치는 sensitivity만 보고했다.

# Recommendation to GPT

- **권고:** 전문 segmentation(+OR 규칙) 최소 대조를 별도 계획으로 진행한다. 판단 근거는 세 가지다. 위치 통제 신호가 남았고, 오류가 여러 case에 걸쳐 있으며, 이 과제는 segmentation+OR로도 풀리기 때문이다. 이 대조가 해결해야 할 질문은 DENSE의 FP(특히 slab5)와 FN이 전문 모델에서도 같은 위치에 남는가이다. 전문 모델이 훨씬 낫다면 현재 MedGemma 구간 방법의 투자를 보류하고, 비슷하다면 언어·비용 이점을 따진다.
- method pilot은 자동 승인하지 않는다. 최소 관심 차이는 계획대로 BA 5 pp 또는 비용 감소다.
- 사전 판정의 5 case 오류 기준은 충족했다. 다만 위치 표준화 CI의 undefined 비율(16%)과 D 규칙의 불안정성은 투자 판단 시 감안해야 한다.

SELF_CHECK: PASS
SUMMARY: 기존 MSD FLAIR E48 출력의 위치 통제 재분석에서 DENSE 위치 표준화 BA 0.717 [0.614, 0.814]로 사전 양성 기준을 충족했으나 D 위치 규칙 대비 전체 BA 이득은 불확정(+0.026, CI [−0.053, 0.110])이며, 사후 개발 분석이라 전문 segmentation+OR 최소 대조를 별도 권고한다.