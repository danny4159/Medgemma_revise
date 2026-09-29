# 요약

- **핵심 결과:** 개발800명(confirm800)에서 SFT-only GT의 대부분은 detector가 병변 위치에 후보를 이미 내놓았지만 confidence threshold에 걸러진 경우다. detector17은 75/77(97.4%), detector29는 80/87(92.0%)이 여기에 해당한다.
- **근거:**
  - SFT는 맞췄는데 detector 후보 전체에 IoU≥0.3인 후보가 없는 잔여량 R은 detector17 1/589(0.17%, 97.5% CI 상한 0.68%), detector29 7/589(1.2%, CI 상한 2.2%)다.
  - 영향 환자는 1명과 7명으로 사전 기준(20명 이상, CI 상한 5% 이상)에 못 미쳐 GPU 후보 추적은 실행하지 않았다.
  - 6개 detector×SFT seed 조합 모두 같은 방향이다.
  - 새 분류 코드는 18/18 fixture를 통과했다. 독립 열거 구현으로 det17/29의 범주 수와 R을 재현해 일치했다(`results/iter_036/full/independent_verify.json`).
- **미검증·주의:**
  - 계획의 "V400"(validation 400명)에는 저장된 SFT 출력이 없다. 그래서 detector·SFT 출력이 모두 있는 개발800(D24 pilot 포함)에서만 분석했고, 이 범위 축소를 코드 docstring과 `analysis.json`의 `scope_note`에 적었다.
  - 개발800은 독립 확인이 아니다.
  - 후보는 NMS와 score>0.001을 거친 뒤 저장된 것이라 후처리 이전 후보는 보지 못했다. R이 매우 작아 GPU 추적 조건은 충족되지 않았다.
  - "저장 후보 존재"는 실제 검출이나 시각 이해의 증거가 아니다.
- **다음:** 새 시각 표현 loss와 단순 ensemble의 우선순위를 낮추는 것이 데이터에 맞는다. 다만 낮은 threshold는 FP를 늘리므로 detector 우위나 confidence 문제가 해결됐다고 주장하지는 않는다. VinDr 승인 통지 후 같은 분해로 재현을 확인하거나 언어·근거 과제로 옮기는 것을 GPT가 비교하길 권한다.

# Work Performed

- 기준 계획·HEAD·저장 입력의 provenance를 확인했다. 선택 LOCK, checkpoint sha, 요청 ID 순서를 검사하는 loader를 `det_error_audit.py`에 넣었다.
- 새 모듈 `rsna_diag/det_error_audit.py`를 작성했다. SFT-only GT를 4범주(대응 경쟁 / threshold 제외 / 인접 위치 오차 / 저장 후보 coverage 부재)로 분해하고, 잔여량 R, 위치 정밀도 전이, FP 분해를 계산한다. R과 threshold 제외 비율은 환자 cluster bootstrap(10,000회, seed 20260929, 97.5% CI)으로 구한다.
- GT identity는 승인된 `metrics.match`를 썼고 `det_match.bounded_match`는 쓰지 않았다.
- 독립 검증 스크립트를 작성해 itertools 열거 matching으로 범주 수를 재계산했다.
- 범주별 hash 순서 최대 6명의 overlay PNG를 생성했다. 이번 반복에서 PNG 이미지를 직접 열어 본 것은 아니다. 파일 8개의 존재와 1개의 크기(1024×1024 RGB)만 확인했다.

# Files Changed

- 신규: `rsna_diag/det_error_audit.py`
- 신규: `tests_det/test_det_error_audit.py`
- 신규: `tests_det/verify_error_audit_independent.py`
- 신규 결과: `results/iter_036/tests/fixtures_iter036.json`
- 신규 결과: `results/iter_036/full/{analysis.json, decision.json, independent_verify.json, overlays/*.png}`
- 기존 코드·결과 파일은 수정하지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python tests_det/test_det_error_audit.py`
  - 1차: 2건 실패. 둘 다 내 테스트의 기대값 오류였다(부동소수점 경계 구성, degenerate 카운트). 테스트를 고쳐 재실행했고 18/18 통과했다.
  - fixture 저장 중 set 직렬화 오류가 한 번 났다. `default=str`로 수정했다.
- `python -m rsna_diag.det_error_audit ...`: 성공. det_compare의 71/77/304/589 재현 gate를 통과했다.
- `python tests_det/verify_error_audit_independent.py`: 성공(pass=true).
- GPU와 학습은 사용하지 않았다(0 update, 새 추론 없음).

# Results (수치와 결과 파일 경로)

IoU 0.3 기준 SFT-only GT 분해(개발800 양성 GT 589개, `results/iter_036/full/analysis.json`):

| 조합 | 대응 경쟁 | threshold 제외 | 인접 위치 오차 | 후보 coverage 부재 | SFT-only 합 |
|---|---|---|---|---|---|
| det17 vs SFT17 | 1 | 75 | 1 | 0 | 77 |
| det17 vs SFT29 | 1 | 77 | 1 | 0 | 79 |
| det17 vs SFT43 | 0 | 82 | 1 | 0 | 83 |
| det29 vs SFT17 | 0 | 80 | 7 | 0 | 87 |
| det29 vs SFT29 | 0 | 84 | 5 | 0 | 89 |
| det29 vs SFT43 | 0 | 82 | 6 | 0 | 88 |

- 위 표의 첫 행은 재현 gate의 SFT-only 77과 일치한다.
- R(SFT 검출인데 detector 후보 전체에 IoU≥0.3 후보 없음):
  - det17 vs SFT17: 1/589, 97.5% CI [0, 0.00677]
  - det29 vs SFT17: 7/589, 97.5% CI [0.00337, 0.02238]
- threshold 제외 비율:
  - det17 vs SFT17: 0.974, CI [0.927, 1.0]
  - det29 vs SFT17: 0.920, CI [0.850, 0.977]
  - 나머지 4개 조합도 0.92–0.99이고 CI 하한은 모두 0.5를 넘는다.
- cap100 도달 영상은 0개다(최대 후보 수 det17 28, det29 22).
- 위치 정밀도(IoU0.3으로 대응된 쌍이 IoU0.5에서도 대응되는 비율): detector 375쌍 71.5%, SFT 381쌍 56.7%.
  - 중심거리/GT 대각선 중앙값: 0.089(detector), 0.129(SFT)
  - 예측/GT 면적비 중앙값: 1.14(detector), 0.93(SFT)
- FP 분해(det17 선택점 / SFT17, 전체 800명):

| 모델 | 전체 FP | 이미 대응된 GT와 경쟁 | 근접 오검출(IoU 0.1–0.3) | GT와 IoU 0.1 미만 |
|---|---|---|---|---|
| det17 | 236 | 27 | 46 | 163 |
| SFT17 | 215 | 0 | 65 | 150 |

- 이 분류에서는 계획의 "중복 후보"와 "대응 경쟁"을 하나(`competes_for_matched_gt`)로 합쳤다. 그 밖의 범주 정의도 코드에 있다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **목표 진전:** detector와 SFT의 상보성은 대부분 confidence 선택 효과로 설명된다(H_selection 지지). detector가 저장 후보 수준에서 놓치는 GT는 사실상 없어 H_residual은 지지되지 않았다. H_geometry는 IoU0.5 전이율 차이(detector 71.5% vs SFT 56.7%)로 관찰됐다. 모두 개발800의 제한된 관찰이다.
- **재사용:** `det_compare`(load_stored, complementarity, ADAPTERS), `det_eval.load_verified`, `det_lib`, `metrics.match`, `sft_eval`, `geometry`를 그대로 썼다. reuse_assets manifest는 비어 있었다.
- **미검증:**
  - 후처리 이전 후보 추적(GPU 단계)은 미실행이다. 계획의 진입 조건에 못 미쳤다.
  - 외부(VinDr) 재현은 미실행이다.
  - 언어·근거 과제의 효용 평가는 하지 않았다.
  - 층별(GT 개수·면적) F1 분석은 이번에 새로 만들지 않았다(iter_035 `det_compare`의 strata가 있다).
  - det29 vs SFT29/43 등 새 조합의 F1 paired CI는 계산하지 않았다. 이번 분해 지표는 seed 조합 전체에 걸쳐 보고했다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **재사용 전 수정:**
  - `det_error_audit`의 입력 provenance는 loader 수준에서만 검사한다. protocol 잠금, 완료 재사용 검증은 넣지 않았다.
  - 코드에서 GPU 추적으로 넘어가는 경로는 구현하지 않았다.
- **추후 개선:**
  - matching 동점 규약의 exhaustive 대조는 이번에 새로 하지 않았다.
  - overlay PNG를 육안 검토하지 않았다.
  - 분석 결과 출력이 이미 있으면 덮어쓰지 않고 오류를 내지만, 고유 attempt 디렉터리 강제는 없다.

# Recommendation to GPT

- 후보 coverage 부재가 사실상 0이고 SFT-only의 92–99%가 threshold 제외이므로, 새 시각 표현 loss와 단순 ensemble 투자는 낮추는 쪽을 권한다. 이 결과는 실용 detector 우위나 VLM 열세를 확정하지 않는다.
- 다음 후보로는 표준 calibration/선택으로 이 차이가 설명되는지, VinDr 승인 후 같은 분해를 재현할지, 언어·근거가 필요한 과제로 옮길지를 비교하는 것을 권한다.
- 계획의 "V400" 표기는 SFT 출력이 없는 validation_ids와 어긋난다. 이번에 개발800으로 대체한 판단이 타당한지 검토를 부탁한다.

SELF_CHECK: FAIL
SUMMARY: 개발800에서 SFT-only GT의 92–99%는 detector 후보가 confidence threshold에 걸러진 경우이고 후보 coverage 부재(R)는 0.17%/1.2%뿐이라 GPU 추적은 조건 미달로 미실행했다. 다만 계획의 V400을 개발800으로 대체했고 overlay 육안 검토와 층별 분석·protocol 잠금이 남아 FAIL로 표시한다.