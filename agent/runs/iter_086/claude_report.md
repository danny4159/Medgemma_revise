# 요약

- **핵심 결과**: PadChest-GR E96(abnormal 48명, no_abnormal 48명)에서 8개 조건을 비교했습니다. RSNA adapter(B0)는 MedGemma 1.5(M15)보다 확정 recall이 약간 높았지만 불확정입니다. CURE(C-G)는 MedGemma 1(M1-G)보다 recall이 올랐고 contradiction과 possible 주장이 줄었습니다. CURE hybrid(C-H)는 recall이 더 올랐지만, 내부 모순·추가 주장·모순이 크게 늘었습니다.
- **근거**:
  - 아래 수치는 abnormal 48명의 pos_def 소견 기준 recall_def입니다. 전체 contradiction은 abnormal 48명과 보고서에 명시적 부정이 있는 no_abnormal 7명, 총 55명 기준입니다.
  - 확정 recall은 M15-R 0.146, B0-R 0.177입니다. 차이 +0.031의 95% CI는 [−0.021, +0.104]이므로 불확정입니다.
  - C-G − M1-G recall은 +0.153 [0.038, 0.271]입니다. contra_primary 차이는 −0.200 [−0.327, −0.091]입니다.
  - C-H − C-G recall은 +0.061 [0.010, 0.123]입니다. 반면 internal +0.823, xd +2.47, xp +1.20이고, contra_primary는 +0.291 [0.164, 0.418]입니다.
  - C-H 평균 출력은 약 1,339 token, 비EOS 종료 1건입니다.
- **미검증·주의**:
  - 판정은 assistant 한 명이 눈가림 상태에서 했습니다. 전문의 판독이 아니고 임상 정답도 아닙니다.
  - 고정 24명 재판정은 같은 평가자가 다시 본 intra-rater 일치도입니다.
  - E192x 확대는 실행하지 않았습니다.
  - 수동 token 회귀 8건 중 2건이 불일치했고 원인은 분리하지 못했습니다.
  - 계획의 "recall +10pp, contradiction 증가 ≤5pp" 기준을 만족하는 조건은 이 결과에서 확정하지 못했습니다.
- **다음**: 위치 학습이 판독에 주는 이득과 추가 언급 비용을 구분하려면 독립 평가자의 표본 판정이나 E192x 확대가 필요합니다.

# Work Performed

- 고정 24명의 2차 눈가림 재판정을 끝내고 `recheck_parts/rpart01~06.txt`에 저장했습니다.
- 1차(`judgments_E96_v2.txt`)와 2차의 일치도 비교기 `report86_recheck_compare.py`를 작성해 실행했습니다.
- 2차 판정 작성 중 P062 파일에 형식 오류가 있었습니다. neg_specific 소견 F4를 소견 판정란에 넣었는데, 파서는 pos 계열 소견만 요구합니다. F4를 빼고 F5·F6만 남기도록 `rpart04.txt`를 고쳤습니다. 이 수정은 판정 파일의 형식 정정이고, 판정 내용이나 문턱은 바꾸지 않았습니다.
- v2 판정과 `eval_v2/report.json`에 `report86_verify.py`를 다시 돌려 통과를 확인했습니다.
- `hf_cache`에 새로 쓰인 파일이 없는지 확인했습니다.
- 잠금 이후 변경 기록 `E_lock_amendment.json`을 만들었습니다.
- 이 세션 앞부분의 작업은 D8 검증, E96 표본 선정·잠금, 생성·병합, 평가기와 독립 검증기, exposure 점검이며 아래 Results에 요약했습니다.

# Files Changed

- 새 코드: `report86_recheck_compare.py`. 그 밖의 `report86_*.py`와 `test_report86*.py`는 이번 반복에서 이미 만든 미추적 파일입니다.
- 새 결과:
  - `results/iter_086/E96/recheck_parts/rpart01~06.txt`
  - `results/iter_086/E96/recheck_compare.json`
  - `results/iter_086/E96/verify_v2.json`
  - `results/iter_086/E96/E_lock_amendment.json`
- 기존 iter_084/085 원본과 수동 RSNA 파일은 수정하지 않았습니다.
- git commit과 checkout은 하지 않았습니다.

# Commands / Experiments

- `python report86_view.py E96 <index 목록>`: 눈가림 보기. 성공했습니다.
- `python report86_recheck_compare.py E96 ...judgments_E96_v2.txt ...recheck_parts ...recheck_compare.json`: 성공했습니다.
- `python report86_verify.py E96 ...judgments_E96_v2.txt ...eval_v2/report.json ...verify_v2.json`: `pass=true`. 확인 값 7,848개와 CI 40개 모두 불일치 0입니다.
- `find hf_cache -newer inheritance_manifest.json -type f`: 결과 없음(신규 쓰기 없음).
- 이 세션 앞부분에서 실행한 GPU 생성은 앞서 요약한 단계(D8, E96)에 포함됩니다. `test_report86.py`는 10/10 통과했습니다.

# Results

**2차 재판정 일치도 (24명, 소견 판정 160건, intra-rater)**

- 상태 일치 0.9375 (150/160).
  - 불일치는 N→U 5건, U→P 3건, D→P 1건, U→N 1건입니다.
- 둘 다 D인 24건 중 위치 접미사 일치는 0.792입니다.
- 환자 단위 지표(pass1 → pass2, 평균 절대차):
  - recall_def: 0.234 → 0.224 (차 0.010)
  - recall_incl_possible: 0.248 → 0.274 (차 0.026)
  - contra_primary: 0.458 → 0.458 (차 0)
  - internal: 0.130 → 0.125
  - xd: 0.526 → 0.516
  - xp: 0.146 → 0.188
- 지표 평균은 안정적이지만 hedged 표현(P)과 위치 접미사의 일치는 약합니다.
- 결과 파일: `results/iter_086/E96/recheck_compare.json`

**E96 조건별 지표 (abnormal 48명 pos_def recall, 모순은 55명 기준)**

| 조건 | recall_def | contra_primary | xd | xp | internal |
|---|---|---|---|---|---|
| M15-R | 0.146 | 0.564 | 0.146 | 0 | 0.021 |
| B0-R | 0.177 | 0.509 | 0.188 | 0 | 0.063 |
| M1-G | 0.115 | 0.218 | 0.458 | 0.167 | 0 |
| C-G | 0.267 | 0.018 | 0.531 | 0.021 | 0 |
| C-H | 0.328 | 0.309 | 3.0 | 1.219 | 0.823 |

- 위 표는 `eval_v2/report.json`에서 가져왔고, `verify_v2.json`이 같은 값을 독립 코드로 재계산했습니다.
- 주 비교의 95% CI는 앞 요약에 있습니다.
- 정밀도 범위(supported/(supported+contradicted+unverifiable)의 하한~상한):
  - C-G: 지지 16, 모순 0, 검증 불가 53.
  - C-H: 지지 26, 모순 9, 검증 불가 405.
- unverifiable 비중이 커서 임상 precision이 아닌 범위로만 해석해야 합니다.

# Goal Progress / Reused Assets

- 확인한 것:
  - RSNA adapter의 추가 이득은 이 표본에서는 작거나 불확정입니다.
  - CURE 공식 GRG 출력은 같은 평가에서 recall이 오르고 확정 모순이 줄었습니다.
  - CURE hybrid는 recall이 더 오르지만 반복 출력에 따른 모순·미검증 주장 비용이 큽니다.
- 미검증: 전문의 판정, 독립 평가자 일치도, E192x 확대, 다른 데이터·모델 일반화, 학습 노출 통제입니다.
- 재사용: iter_084/085의 82개 inheritance 출력(0건 격리)과 `pg43_run`, `generate`, `lora` 경로를 썼습니다. 일부는 이 반복에서 기술 검증을 했습니다. 승인된 범용 실행기로 간주하지는 않습니다.

# Problems

- **현재 결론을 무효로 만드는 결함**: 없음을 확인했습니다. 다만 평가자가 한 명이라 임상 결론은 낼 수 없습니다.
- **재사용 전 수정**:
  - 수동 token 회귀 8건 중 2건 불일치의 원인 분리.
  - hedged(P)와 위치 접미사 판정 규약을 더 구체화하는 일.
- **추후 개선**:
  - 독립 평가자 표본 점검, E192x 확대.
  - xd와 xp 집계를 사실 단위로 세분화.
  - 퇴행 출력의 압축 보기를 원문과 대조.

# Recommendation to GPT

- 이 결과는 "위치 학습이 판독을 개선한다"를 확정하지 않습니다. CURE 계열 GRG 출력은 가까운 선행으로서 확정 모순을 줄인 반면, hybrid는 비용이 큽니다.
- 다음 계획은 같은 E96 입력으로 독립 평가자 표본 판정을 먼저 하는 쪽을 권합니다.
  - 평가자 일치가 높으면 E192x 확대와 최소 개입을 검토합니다.
  - 일치가 낮으면 평가 규약을 먼저 고칩니다.
- `internal`, `xd`, `xp`가 폭증한 C-H는 hedged 처리와 중복 문장을 줄이는 후처리와 함께 비교해야 합니다. 새 loss나 전체 재학습은 아직 권하지 않습니다.

SELF_CHECK: FAIL
SUMMARY: E96에서 8개 조건 판독을 평가해, C-G는 MedGemma 1 대비 recall이 올랐고(+0.153) 모순이 줄었지만 C-H는 recall이 더 올랐어도 내부 모순과 추가 주장이 폭증했습니다. 판정자가 assistant 한 명이고 24명 재판정 상태 일치가 0.9375인 intra-rater 수준이며 E192x와 독립 전문 검증이 없어 FAIL입니다.