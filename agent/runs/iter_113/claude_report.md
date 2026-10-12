# 요약

- **핵심 결과:** 사전 고정 규칙에서 **양성 탐색(positive_exploratory)** 으로 판정됐다. 12건 검토(N=47)에서 CURE–MedGrounder 불일치 순위는 공식 주석 오류 9건, MedGrounder confidence 순위는 6건을 잡아 차이가 +3이다. 사전 문턱은 ceil(0.05×47)=3건이어서 정확히 문턱에 걸린다.
- **근거:** 사전 조건 4개를 모두 충족했다. 순이득이 문턱(+3) 이상이고, D-only 오류가 7명에 분산되며, 보수적 최소가 +2(>0)이고, 환자 제거 분석에서 음수가 0건(최소 +2, 최대 +3)이다. 독립 재계산 19/19 일치, fixture 36/36 통과.
- **미검증·주의:** 환자 bootstrap 95% 구간이 [-2, 6]이라 0을 포함한다(차이>0 비율 0.82, 차이<0 비율 0.077). 보수적 하한 +2는 최소 이득 3보다 낮다. 반복 개발 자료이고, 새로 잡은 오류(7건)와 새로 놓친 오류(4건)가 함께 있다. 신규 기여, confidence 대체, 시각 근거의 인과적 사용은 주장하지 않는다.
- **다음:** 독립 환자 확인과 일반 ensemble 대조의 가치·비용을 사용자 승인 대상으로 제안한다.

# Work Performed

- 사전 승인된 CPU 전용 diagnostic이다. GPU, 새 추론, 학습, 다운로드, 설치는 모두 0이다.
- `nr107_geom.py`와 `nr107_spec.py`를 반입했다. 출처 blob과 일치함을 확인했다(`6ed0535…`, `d0b6a95…`).
- 저장 자산을 연결한 ledger를 만들었다. 이 단계에서는 순위나 정답 오류를 계산하지 않았다.
  - 입력: iter_107 items, CURE M47 shard, iter_046 MG V96_A_w2b4 raw, final_selection, iter_039 manifest_private.
  - 연결 검증: 원 hash, 완료 기록, 중복·누락, 문장 hash, 영상 hash, ckpt hash, 정답 대응, MG 원본과 파생 box/score 일치.
  - 결과: 47개 전부 연결, 제외 0건. CURE 상태는 valid_nonempty 45건, no_box 2건이다. malformed·truncated·coord_invalid는 0건이라 순위 제외도 0건이다. 36명이다.
- 분석 규칙을 코드와 입력 hash로 잠갔다. 잠금 시각은 2026-10-12T04:40:45Z이다. fixture 통과 후, 순위와 GT 오류를 계산하기 전이다. 반복 개발 자료이므로 미사용 test 사전등록이 아니다.
- 고정 비교를 1회 실행하고 독립 재계산으로 검증했다. 완료 봉인 `completion.json`이 있다.

# Files Changed

새 파일(모두 `research/`, 미커밋):

- `nr113_core.py`: 연결 ledger, 위험 D·B, 오류 E, 순위, 동률·주석 범위(정확한 DP), 환자 bootstrap, leave-one-patient-out.
- `nr113_run.py`: link → lock → analyze → seal. 덮어쓰기 거부, 잠금 위반 시 중단.
- `nr113_tests.py`: fixture 36개.
- `nr113_verify.py`: 독립 재계산.
- 반입: `nr107_geom.py`, `nr107_spec.py`(미수정).

결과는 `results/iter_113/` 아래에 있다: `ledger.json`, `protocol.json`, `report.json`, `per_item.json`, `bootstrap_diffs.json`, `verify.json`, `completion.json`, `tests/fixtures.json`.

# Commands / Experiments

- `python nr113_tests.py`: 성공, 36/36.
- `python nr113_run.py link`: 성공, 47/47 연결, 제외 0.
- `python nr113_run.py lock`: 성공.
- `python nr113_run.py analyze`: 성공. 분석 wall은 0.61초(bootstrap 10,000회 포함)이고 GPU는 0이다.
- `python nr113_verify.py`: 성공, 19/19 PASS.
- `python nr113_run.py seal`: 성공.

# Results

| 항목 | 값 |
|---|---|
| N / K / 환자 | 47 / 12 / 36 |
| 공식 주석 오류 (union IoU<0.3) | 15건 |
| D(불일치) 포착 / precision | 9 / 0.75 |
| B(confidence) 포착 / precision | 6 / 0.50 |
| 차이 | +3 (차이/N = 0.064) |
| 경계 동률 | 없음, 범위 [3,3] |
| 주석 확정 오류 / 확정 정상 / 미확정(불일치) / 미확정(대체 주석 없음) | 10 / 27 / 7 / 3 |
| 주석 모호성 범위 | [2, 7] |
| 동률+모호성 결합 범위 | [2, 7] |
| bootstrap 평균 / 95% CI | 2.28 / [-2, 6] |
| bootstrap 차이>0 / =0 / <0 | 0.821 / 0.102 / 0.077 |
| leave-one-patient-out 최소 / 최대 / 음수 | +2 / +3 / 0 |

상보성(오류 기준):

| | 오류 수 | 환자 수 |
|---|---|---|
| D-only | 7 | 7 |
| B-only | 4 | 4 |
| 공통 | 2 | 2 |
| 둘 다 놓침 | 2 | 2 |

D가 추가로 잡은 7건에 대해 B가 따로 잡은 오류가 4건이다. 결합 선택의 성능은 K건 검토 성능이 아니므로 주장하지 않는다.

사전 판정 조건:

- 순이득 ≥ 3: 충족. 정확히 문턱이다.
- D-only 오류 ≥ 2명: 충족(7명).
- 보수적 최소 > 0: 충족(2).
- LOO 음수 없음: 충족.

# Goal Progress / Reused Assets

- **시험 설정:** 이번 고정 설정(MG 0.8, 12건 검토)은 사전 기준을 충족했다. 한 건 차이에서 문턱이 갈리는 최소 충족이다.
- **연구 관찰:** 이 개발 자료에서는 CURE 불일치가 MG confidence 순위가 놓친 주석 불일치 오류를 일부 잡았다. 반대로 놓친 오류(B-only 4건, 둘 다 놓침 2건)도 있다. 신호의 강건성은 bootstrap으로 약하게만 지지된다.
- **연구 질문:** 독립 환자·일반 ensemble 대조 없이는 판단할 수 없다. 단순 ensemble disagreement의 성공이며 신규 기여가 아니다.
- **재사용:** nr107_geom/spec은 blob 일치와 import를 확인했다. 호출 경계에 유한·범위·양의 면적 검사를 넣었고(`box_ok`), 47개 원시 CURE 출력을 원문·EOS에 연결했다. 합성 fixture(동일·분리·중복·부분 중첩·빈 집합·malformed·범위 밖)도 통과했다. 새 순위·모호성·동률·bootstrap 계산은 `nr113_verify.py`(포함-배제 면적, 전수 brute force, 동일 bootstrap 절차 재구현)로 대조했다.
- **비용:** 지배 비용은 코드 작성과 검증이었다. 분석 실행은 0.61초이다. 두 모델을 서비스에서 함께 돌리는 비용은 미측정이다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정:** 없음. 코드는 이번 고정 입력 전용이다.
- **추후 개선 / 한계:**
  - 문턱 충족이 한 건 차이이고, bootstrap 95% CI가 [-2, 6]으로 0을 포함하므로 불확실성이 크다.
  - 보수적 하한(+2)은 최소 이득 문턱(3)보다 낮다. 사전 기준의 문자 그대로는 ">0"이라 충족으로 판정했다.
  - CURE의 사전학습 노출과 두 모델의 전처리 차이(uint16 대 u8)는 미확인이다.
  - 공유 누락(둘 다 빈 출력)은 D가 못 잡는다. 2건은 둘 다 놓쳤다.
  - 환자 7명이 D-only 오류를 가진다는 사실이 시각 근거의 인과적 사용을 뜻하지 않는다.
  - 주석 모호성 7건은 미확정이며 전문의 판정을 대신 만들지 않았다.

# Recommendation to GPT

- 사전 규칙상 결과는 양성 탐색이다. 다만 한 건 차이와 CI가 0을 포함한다는 점을 반영해 독립 확인 제안 시 판별력 있는 규모를 따져 달라. 점수·threshold 순회로 확대하지 말고, 새 환자에 대한 동일 고정 규칙 확인과 단순 ensemble disagreement 대조(비용 포함)를 하나의 최소 비교로 검토하길 권한다.
- 대안은 이 묶음 투자 보류이다. 한계 근거는 CI의 0 포함과 문턱 경계 충족이다. 추가 전문가나 GPU 요구는 없다.
- 다음 반복은 사용자 승인 이후에만 진행한다.

SELF_CHECK: PASS
SUMMARY: 저장된 CURE·MedGrounder 출력 47개 소견(36명)에서 불일치 순위가 K=12 기준 오류 9건 대 confidence 6건(+3)을 잡아 사전 기준을 정확히 문턱(3)에서 충족했다(양성 탐색). bootstrap CI [-2,6]이 0을 포함하고 독립 확인은 미실시이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: sed -i 's/ and f != "nr113_verify.py"//' nr113_run.py && grep -n "code_sha256" nr113_run.py | head -3
