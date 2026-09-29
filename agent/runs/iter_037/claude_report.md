# 요약

- **핵심 결과:** 고정 FP budget별 비용 표, GT·후보 감사 행, 같은 대응쌍의 IoU0.5 통과율, 독립 재매칭 표를 저장 출력만으로 완성했다. GPU 0, 학습 0이다. criterion_a/b는 두 detector 모두 미충족이라 GPU 확대는 하지 않았다.
- **근거:** confirm800(개발800)에서 R의 영향 환자는 detector17 1명, detector29 7명이고 97.5% CI 상한은 0.68%·2.24%다. cap100 도달은 0건이다. SFT-only GT 대부분은 threshold 제외였다(detector17 75/77, detector29 80/87). 회귀 147/147, 독립 재계산 533건(V400)·943건(confirm800) 모두 불일치 0, fixture 57/57과 기존 18/18이 통과했다.
- **미검증·주의:** 개발800과 V400은 선택에 쓰였으므로 독립 확인이 아니다. detector가 SFT보다 우위라고 말할 수 없다(아래 참고). post-NMS 후보만 다뤘고 외부 일반화·VLM 고유 효용은 미검증이다.
- **다음:** VinDr 승인 대기 중이다. 같은 개발800에서 분석을 더 늘리지 않는 것을 권고한다. 자세한 권고는 마지막 절에 적었다.

# Work Performed

- 기준 계획(iter_036 plan, SHA256 `d00ffbce…`)과 iter_036 코드·결과를 확인했다. 실제 수정 대상 loader와 통계 코드를 읽었다.
- **새 모듈 `rsna_diag/det37.py`:**
  - 저장 출력 loader를 fail-closed로 만들었다. LOCK 5개 파일 hash와 seed 집합, 선택 파일 잠금, checkpoint·source digest·batch1 대조, shard record의 요청 집합·중복·provenance·raw_preds 일치, 영상 file hash와 크기, boxes/scores/labels 길이·유한성·좌표·label·cap을 검사한다.
  - SFT는 prompt hash, EOS, pad affine, 영상 경로를 추가로 검사한다.
  - 분석 출력은 flock 단일 소유, 덮어쓰기 거부(`os.link`), 단위별 config·입력 digest 재개를 갖춘다.
- **분석 내용:** 모든 operating point(선택점과 FP budget 0.25/0.5/1.0)에서 F1@0.3/0.5, lesion recall, 전체·범주별 FP 총수·FP/환자·분모·invalid, 두 IoU의 both/det-only/SFT-only/both-miss를 냈다. 통합 FP 범주와 두 IoU의 범주 합=전체 FP 검사, R 불변성 검사, GT별 감사 행(원래 candidate index, 최대 IoU 후보와 최고 score 후보 구분, 부재는 None)을 포함한다.
- **대응쌍 분석:** IoU0.3의 원래 대응쌍을 고정한 뒤 그 쌍의 IoU≥0.5 여부와 독립 IoU0.5 재매칭 GT 검출을 따로 집계했다.
- **criterion_a/b:** cap 환자의 미대응 GT를 양극단(회복 불가/가능)으로 두는 `criterion_ab`를 구현하고 fixture 4종으로 검사했다.
- **재사용:** `det_error_audit.py`는 iter_036 결과의 재현성을 위해 수정하지 않았다. 계획은 이 파일을 수정 대상으로 적었지만, 이번에는 새 모듈에서 fp_decompose·stratified_d24·ratio_ci_cluster를 import해 썼다.
- **overlay:** `det37_overlay.py`로 범주별 hash 순서 최대 6명을 그렸다. 분류 근거인 threshold 아래 후보의 index·score와 최대 IoU 후보를 함께 표시한다. 3장을 직접 열어 GT·후보 좌표와 영상 방향을 확인했다.

## 정정 사항(V400 출력 부재 설명)

iter_036 `det_error_audit.py` docstring은 "validation_ids에 저장된 SFT 출력이 없다"고 적었다. 사실이 아니다.

- `results/iter_012/train/lr2e-4_s17/epoch_05/val_gen/`에 SFT17의 400개 고유 요청이 있고, completion은 누락·중복 0이다.
- SFT29/43의 V400 출력은 이번에 사용·검증하지 않았다.
- 기존 보고서와 결과는 수정하지 않았고, 이 정정은 이 보고서와 `det37.py` docstring에만 남긴다.
- V400은 원래 계획의 사전 gate가 아니다. iter_036 이후 수행한 사후 회귀 검사이며 사전 검사를 소급 복원한 것이 아니다.

# Files Changed

새 파일만 만들었고 기존 파일은 수정하지 않았다(`git status`: untracked 5개).

- `rsna_diag/det37.py`
- `rsna_diag/det37_overlay.py`
- `tests_det/test_iter037.py`
- `tests_det/regress_iter037.py`
- `tests_det/verify_iter037_independent.py`

# Commands / Experiments

모두 성공했고 오류 후 재실행은 아래 두 건뿐이다. GPU는 쓰지 않았다(`nvidia-smi`: 두 장 모두 사실상 유휴).

- `python rsna_diag/det37.py --split V400 --d24 --out results/iter_037/a1/d24_V400 --workers 4` — D24 동작 확인, 9개 unit.
- `python rsna_diag/det37.py --split V400 --out results/iter_037/a1/V400 --workers 4` — 9 unit, 단위 계산 합 3.7초.
- `python rsna_diag/det37.py --split confirm800 --out results/iter_037/a1/confirm800 --workers 4` — 11 unit, 단위 계산 합 19.8초.
- `python tests_det/regress_iter037.py …` — 처음에 문자열 비교 버그로 실패해 `chk`를 고친 뒤 재실행했고, 이번 결과는 147/147 PASS다.
- `python tests_det/verify_iter037_independent.py --split V400|confirm800 …` — 각각 PASS.
- `python tests_det/test_iter037.py results/iter_037/tests/fixtures_iter037.json` — 57/57 PASS. 처음에 env 접두어 권한 문제로 인자 방식으로 바꿨다.
- 기존 `tests_det/test_det_error_audit.py`를 새 결과 경로로 재실행해 18/18 PASS.
- `det37_overlay.py`를 detector17과 detector29에 각각 실행했다.

**규모·비용:** CPU 분석은 detector 추론을 반복하지 않아 매우 짧았다(단위 계산 합 약 24초). ETA 추정은 필요 없었다. worker 병렬은 CPU 4 worker(fork Pool)였고 GPU 병렬 비교는 GPU 미진입이라 수행하지 않았다.

# Results

경로는 모두 `results/iter_037/a1/` 아래다. 도달 단계는 동작 확인 → V400 사후 회귀 → 개발800 본보완까지이고, 독립 확인은 미실행이다.

## 회귀·검증

- `regression.json`: 147/147 PASS(V400은 선택 파일 수치·`val_metrics`, confirm800은 iter_036 분해·R·CI·위치·FP 분해와 iter_035 FP budget·상보성·요약). 수치 오차 1e-8 이내, count는 정확 일치.
- `independent_V400.json` 533건, `independent_confirm800.json` 943건, 불일치 0.
- 독립 구현 범위: IoU, itertools 열거 matching, padding 좌표 변환, F1·recall·FP·통합 FP 범주·상보성·4범주·R·pair 통과율.
- 공유(독립 아님): SFT parser, GT manifest, 선택 threshold, raw_preds의 img_hw. bootstrap CI는 독립 재계산하지 않고 회귀와 iter_036 리뷰의 재현에 의존한다.
- `tests/fixtures_iter037.json`: 57/57. 배열 길이·NaN·Inf·범위·label 거부, LOCK 변조 3종, 잠기지 않은 선택 파일, shard 중복·누락·digest·hash·raw 불일치, 영상 hash 변조, source digest 변조, 덮어쓰기 거부, 동시 실행 거부, 강제 중단(3 unit)→재개 결과가 무중단과 동일, 다른 입력 재개 거부, 변조된 unit 재사용 거부, criterion fixture 4종이 포함된다.
- `tests/fixtures_iter036_rerun.json`: 18/18.
- 조건 확인: R 분자는 12개 조합 모두 threshold와 무관하게 불변이다. cap100 도달은 0건(최대 후보 수 28/22)이다. V400 SFT17은 400건 모두 EOS이며 valid_empty 199·valid_nonempty 201이다.

## 개발800(양성 400명·GT 589개)

F1은 양성 환자 평균이다. FP/환자는 IoU0.3 기준 전체 800명 하한이다(invalid 0이라 하한이 아님). ΔF1은 detector−SFT17이다.

| 모델 / 조건 | F1@0.3 | F1@0.5 | lesion recall@0.3 | FP/환자 | ΔF1@0.3 [97.5% CI] | ΔF1@0.5 [97.5% CI] |
|---|---|---|---|---|---|---|
| SFT17 | 0.6308 | 0.3487 | 0.647 | 0.269 | – | – |
| det17 선택점(thr0.70) | 0.5816 | 0.4155 | 0.637 | 0.295 | −0.049 [−0.100, 0.002] | +0.067 [0.012, 0.122] |
| det17 budget0.25(thr0.75) | 0.5740 | 0.4079 | 0.616 | 0.254 | −0.057 [−0.107, −0.005] | +0.059 [0.004, 0.115] |
| det17 budget0.5(thr0.50) | 0.6222 | 0.4504 | 0.725 | 0.451 | −0.009 [−0.058, 0.041] | +0.102 [0.048, 0.156] |
| det17 budget1.0(thr0.15) | 0.5844 | 0.4385 | 0.818 | 1.008 | −0.046 [−0.096, 0.005] | +0.090 [0.036, 0.145] |
| det29 선택점(thr0.60) | 0.5739 | 0.4064 | 0.621 | 0.274 | −0.057 [−0.108, −0.006] | +0.058 [0.001, 0.114] |
| det29 budget0.25 | 0.5642 | 0.4052 | 0.606 | 0.245 | −0.067 [−0.118, −0.015] | +0.057 [0.000, 0.112] |
| det29 budget0.5 | 0.5950 | 0.4255 | 0.710 | 0.501 | −0.036 [−0.084, 0.013] | +0.077 [0.021, 0.133] |
| det29 budget1.0 | 0.5962 | 0.4433 | 0.781 | 0.791 | −0.035 [−0.084, 0.015] | +0.095 [0.042, 0.147] |

- SFT29/43: F1@0.3 0.6359/0.6528, F1@0.5 0.3132/0.3638, FP/환자 0.254/0.243.
- FP/환자는 detector가 F1@0.3에서 SFT를 앞서는 점이 없고(ΔF1@0.3의 부호는 대부분 음수 또는 CI가 0을 포함), F1@0.5에서는 detector가 앞선다. 즉 지표에 따라 방향이 다르다. nominal budget이 같아도 실제 FP/환자는 서로 다르므로(det29 budget1.0은 0.791) 하나의 수치로 우위를 선언하지 않는다.
- budget 0.25/0.5/1.0 비교는 탐색적이며 유리한 operating point를 새 주비교로 고르지 않았다.

## 상보성과 잔여량 R(IoU0.3, det17 선택점 vs SFT17)

- both/det-only/SFT-only/both-miss = 304/71/77/137. IoU0.5는 149/119/67/254.
- SFT-only 77개의 분해는 matching_competition 1, threshold_excluded 75, adjacent 1, no_coverage 0이다.
- R 분자는 1개(영향 환자 1명), R 97.5% CI [0, 0.00677], threshold 제외 비율 0.974(CI [0.927, 1]).
- det29 선택점 vs SFT17은 threshold_excluded 80, adjacent 7이다. R은 7개(영향 환자 7명), CI [0.00337, 0.02238]이고 threshold 제외 비율은 0.920(CI [0.85, 0.977])이다.
- IoU0.5 민감도(탐색적): det29의 R은 16개(영향 환자 16명), CI 상한 0.0425로 5% 기준에 가깝지만 기준 미달이다. det17은 6개, CI 상한 0.0204다.
- FP budget이 커질수록 SFT-only가 줄고(det17 선택점 77 → budget1.0 23) FP/환자는 늘어난다. 후보 회복은 FP 증가와 함께 나타난다.
- SFT29·43과의 비교도 report에 있으며 같은 방향이다.

## 대응쌍 vs 독립 재매칭(selected op)

- IoU0.3 대응쌍의 IoU≥0.5 통과율은 detector17 0.715(375쌍), SFT17 0.567(381쌍)이다.
- 독립 IoU0.5 재매칭 GT 검출률은 통과율과 정확히 같다. "쌍은 실패, 재매칭은 성공"이나 그 반대 사례는 모든 op·모델에서 0이다.
- 따라서 이번 자료에서는 IoU0.3에서 0.5로의 위치 차이가 대응 변경이 아니라 같은 쌍의 위치 정밀도 차이로만 나타난다.
- iter_036 보고서의 `transfer_rate`는 이 재매칭 검출률이었다.

## 통합 FP 범주

`competes_for_matched_gt`는 중복 후보와 GT 대응 경쟁을 합친 통합 범주다. 두 원인을 따로 검증했다고 말하지 않는다. 범주 합=전체 FP는 모든 op·IoU·범주(전체·양성·Normal·NoOpacity/NotNormal)에서 통과했다.

## V400 사후 검사

- det17 선택점 vs SFT17의 SFT-only는 42개다(threshold_excluded 41, adjacent 1). R 영향 환자 1명, CI 상한 0.0127이다.
- det29는 SFT-only 48개, R 영향 환자 4명, CI 상한 0.0379이다.
- criterion 미충족이며 V400은 선택 자료이므로 독립 근거가 아니다.

## criterion·판단

- `decision.json`: criterion_a는 두 detector 모두 거짓, criterion_b는 cap 환자가 0명이라 비해당이다. escalate_to_gpu_trace=false, GPU 사용 0이다.
- criterion_b 구현의 제한: 양극단을 (관측 R / cap 환자만 0)으로 두면 하한 ≤ 상한이므로 b는 a가 참일 때만 참이 될 수 있다. 즉 b는 승격 조건을 새로 만들지 않고 승격의 cap 민감성을 표시하는 역할이다. fixture로 이 동작을 검사했다.

## 결과 파일

- `V400/report.json`, `confirm800/report.json`
- `confirm800/audit/*__gt_audit.jsonl` (GT별 감사 행), `confirm800/audit/*__pairs.jsonl` (대응쌍 행)
- `confirm800/overlays_det17/`, `confirm800/overlays_det29/`
- `regression.json`, `independent_V400.json`, `independent_confirm800.json`, `decision.json`, `tests/`

# Goal Progress / Reused Assets

## 목표 진전

- detector와 SFT의 오류 상보성은 후보 존재 차이가 아니라 threshold 선택과 연결된다는 iter_036 관찰이 FP 비용을 포함해 유지됐다. det17 기준 SFT-only GT의 97.4%가 낮은 score 후보로 저장돼 있었다.
- 후보 회복은 FP 증가와 함께 나타났고, 고정 FP budget 표에서 detector가 F1@0.3을 SFT보다 크게 높이는 점은 없었다. F1@0.5에서는 detector가 앞선다. 실용적 우위 결론은 지표·운영점에 따라 달라 한 방향으로 확정하지 않는다.
- 큰 후보 발견 차이라는 설명은 두 detector 모두 약하다. R은 CI 상한이 5% 기준보다 훨씬 낮다.
- 미검증: 후처리 전 후보(RPN·NMS 이전)의 영향, confidence 교정의 실효, 외부 일반화, 언어·근거 과제에서의 VLM 고유 효용.

## 실행 유효성 / 성능 / 가설 / 신규성

- **실행 유효성:** 입력 연결, provenance, 독립 수치 대조와 재개·소유권 검사가 통과했다.
- **성능 개선:** 새 방법이 없으므로 성능 개선은 해당 없다.
- **가설 지지:** H_selection은 지지가 유지되고, H_residual의 조건부 GPU 확대 기준은 미충족이다. 두 detector의 seed 결과를 독립 환자로 합치지 않았다.
- **신규 기여:** TIDE 류 오류 분해의 적용이며 신규 방법이 아니다. 신규성은 주장하지 않는다.

## 재사용 출처

| 재사용 파일 | 검증 |
|---|---|
| `geometry.py`, `parse.py`, `metrics.py`, `sft_eval.py`, `det_compare.py`, `det_eval.py`, `det_lib.py` | 코드 수정 없음. 회귀 147/147과 독립 재계산으로 현재 사용 범위(좌표·matching·집계·loader)를 확인했다 |
| `det_error_audit.py` | 수정하지 않고 함수만 재사용. 기존 fixture 18/18 재통과 |
| `det_match.bounded_match` | 사용하지 않았다(iter_036 리뷰의 GT identity 미승인 조건 유지) |

- 생성 코드 source digest는 현재 `det_eval.py`·`det_lib.py`·`geometry.py`가 `f40b8b7b…`로, iter_035 생성 시점과 같음을 확인했다. 과거 metadata는 갱신하지 않았다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정(미해결):**
  - `det37.py`의 loader 보호는 이번 사용 경로(V400·confirm800 저장 출력)만 검증했다. 다른 실행기(`det_jobs.py`, 학습 연장, latency, continuation)의 결함은 해결됐다고 보고하지 않는다.
  - 저장 pair 행과 감사 행은 exact tie 없이 일치했다. 다만 `metrics.match`와 열거 matching의 tie 규약이 다른 자료에서도 같은지는 이번 범위 밖이다.
- **추후 개선:**
  - `criterion_ab`의 b가 a에 종속되는 정의.
  - V400 SFT29/43 출력은 사용하지 않았다.
  - 독립 검증기는 parser와 GT manifest를 공유하고 bootstrap CI를 독립 재계산하지 않는다.
  - SFT invalid 응답은 FP 0으로 세는 하한이지만 이번 자료의 invalid는 0이다.
- **한계:** 개발800·V400은 선택·분석에 쓰였으므로 독립 확인이 아니다. 후처리 후 후보만 다뤘고 RPN 이전 후보는 미추적이다. 사전학습 노출과 SOP 수준 독립성 불확실성은 그대로다.

# Recommendation to GPT

**전략 판단(Strategy Check 요약):** 계획의 세 선택 중 **2번(원인·선택 진단 마무리)을 이번에 완료**했고, 다음 우선순위는 **3번(언어·근거가 필요한 질문)**을 권고한다.

- **근거:** 후보 coverage 부재(R)가 아니라 threshold 선택과 FP 비용이 detector와 SFT의 차이를 만든다. 이 차이는 F1@0.3에서는 SFT가 앞서거나 비슷하고, F1@0.5에서는 detector가 앞선다. bbox 정확도·비용 비교만으로는 VLM에 투자할지 판단할 근거가 더 나오지 않는다.
- **하지 않을 것:** 같은 개발800에서 분석 종류를 더 늘리지 않는다. 새 loss·표준 calibration·단순 ensemble은 이번 결과로는 우선순위가 낮다. 후처리 전 후보 trace도 R이 작아 정보 가치가 낮다.
- **방향을 바꿀 조건:** VinDr 승인 후 외부 자료에서 R이 커지거나 detector 우위가 사라지면 재검토한다. 언어·근거 과제는 유효한 정답·사용 목적·강한 모듈형 비교군(detector+VLM)을 갖춘 별도 계획으로 설계한다.
- **한 줄 조언:** iter_036의 기존 결과·보고서는 그대로 두고, 이번 정정(V400 SFT17 출력 존재)은 이 반복의 기록으로만 인용한다.

SELF_CHECK: PASS
SUMMARY: RSNA detector17/29 대 SFT의 FP budget별 비용·성능 표, GT·후보 감사, 대응쌍 vs 재매칭을 저장 출력만으로 완성했고 회귀 147/147·독립 재계산 불일치 0으로 검증했다. criterion_a/b 미충족이라 GPU 0이며 detector 우위는 F1@0.5에서만 확인되고 F1@0.3에서는 SFT가 비슷하거나 앞선다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: ls results/iter_035/select results/iter_035/select/seed17 results/iter_035/eval results/iter_035/eval/seed17 results/iter_035/eval/seed17/V400_e18 results/iter_036/full results/iter_036/tests; nvidia-smi --query-gpu=index,uuid,memory.used,memory.total --format=csv; echo $CUDA_VISIBLE_DEVICES
- Bash: DET37_FIXTURES_OUT=results/iter_037/tests/fixtures_iter037.json python tests_det/test_iter037.py 2>&1 | tail -20
