# 요약

- **핵심 결과**: CURE만 포착한 오류 7개와 MSPC만 포착한 6개 사이에서, 서로 다른 기하학적 실패 조건이 일관되게 갈리는 패턴은 보이지 않았다. 사전 계획의 "음성 탐색" 분기에 해당하므로 CURE 특화 오류 검토 투자는 보류를 권한다.
- **근거**:
  - CURE-only 7개 중 3개는 CURE가 박스를 하나도 내지 않아(`no_box`) 선택된 사례였다. 이는 공간 불일치가 아니다. 나머지 4개는 CURE 순위가 18~22위로 K=22 경계에 가까웠다.
  - MSPC-only 6개 중 4개가 `partial_low_coverage`였지만, 전체 오류 37개에서도 이 유형이 13개(35%)라 특이 조건이라 하기 어렵다. MSPC-only 6개는 5명에 속한다.
  - 13개 중 대체 주석에서 오류가 사라진 사례가 5개, 유형이 같게 유지된 것은 2개, 바뀐 것은 2개, 대체 주석이 없는 것은 4개다. 패턴이 주석 선택에 크게 의존한다.
- **미검증·주의**: 사후 탐색이다. 이 규약은 이미 집계를 본 뒤 정했고, 독립 검증이나 눈가림 평가가 아니다. iter_114의 A/B 불확정 판정은 그대로 유지한다.
- **다음**: 새 실험은 제안만 하고 사용자 승인을 기다린다.

# Work Performed

- 입력 연결 점검(`nr115_run.py prov`): iter_114 `stage_lock_final`이 기록한 원시 출력 파일의 digest를 현재 파일과 대조했다. 영상 raw/u8 pixel hash, ledger↔items(GT/ALT/문장), ledger↔원시 request id 연결도 확인했다. 문제는 없었다.
- 분류 규약·코드 hash·provenance digest를 `protocol.json`에 기록했다(2026-10-12 실제 시각, 분석 전). 사후 규약임을 명시했다.
- 전체 87행의 기하표, 6개 군(오류×선택, 비오류×선택)별 집계, 차별 포착 13개 사례표와 overlay 13장을 만들었다.
- 독립 검산(`nr115_verify.py`)은 기존 기하·분류 모듈을 import하지 않는다. numpy 좌표 격자로 면적·IoU·u_j·유형을 다시 계산해 87행 표와 대조했다.
- 봉인 후 보조 기술 통계(`nr115_simple.py`)를 추가했다. 빈 출력, 개수 불일치, 순위 경계, 대체 주석 유지 여부를 센 것이다.
- 모델 요청, 학습, 다운로드, GPU 사용은 모두 0이다.

# Files Changed

- 신규 코드: `nr115_core.py`, `nr115_run.py`, `nr115_verify.py`, `nr115_tests.py`, `nr115_simple.py`
- 신규 결과: `results/iter_115/` (provenance, protocol, table87, groups, cases13, verify, simple_explanations, completion, tests/fixtures, overlays 13장)
- 기존 파일 수정과 iter_113/114 결과 덮어쓰기는 없다.

# Commands / Experiments

- `python nr115_tests.py`: 성공(17/17). 경계 fixture, 독립 격자 대조 200개, 원시 파일 변조 검출, 덮어쓰기 거부를 포함한다.
- `python nr115_run.py prov`: 성공(문제 없음).
- `python nr115_run.py lock`: 성공.
- `python nr115_run.py analyze`: 첫 실행은 `overlays/` 디렉터리가 없어 FileNotFoundError로 실패했다. 코드를 고치면 lock hash가 깨지므로 디렉터리만 만들고 같은 코드로 재실행해 성공했다.
- `python nr115_verify.py --write`: 성공(11개 검사 모두 PASS).
- `python nr115_run.py seal`: 성공. 현재 모든 입력·코드·산출물 digest가 lock 당시와 같을 때만 `completion.json`을 만든다.
- `python nr115_simple.py`: 성공. 이 파일은 봉인 이후에 추가했고 completion 대상이 아니다.
- overlay 1장(`mspc_only_94e7785c...`)을 실제 영상으로 열어 확인했다. 이 사례는 예측 박스가 작은 공식 GT 박스보다 훨씬 크고 대체 주석 박스와는 겹친다. 캡션의 한글은 폰트 때문에 깨졌다. 나머지 12장은 열어보지 않았으므로 시각 감사 판정은 쓰지 않는다.

# Results

경로: `research/results/iter_115/`

- 독립 검산이 재현한 값: 87항목·68명·공식 오류 37개·K=22, 포착 16/15/13, CURE-only 7·MSPC-only 6·공통 9·미포착 15, 두 판독자 불일치 26·대체 주석 없음 16.
- 6개 군의 구성(항목/환자):

| 군 | 항목 | 환자 | confidence 선택 |
|---|---|---|---|
| CURE-only 오류 | 7 | 7 | 3 |
| MSPC-only 오류 | 6 | 5 | 4 |
| 공통 포착 오류 | 9 | 8 | 4 |
| 양쪽 미포착 오류 | 15 | 15 | 2 |
| 비오류, 선택됨 | 12 | 12 | 5 |
| 비오류, 미선택 | 38 | 35 | 4 |

- 87개 항목 모두 공식 GT 박스가 2개 이상이다(다중 영역 자료).
- 기하 유형은 오류 37개 전체와 차별 포착 13개를 나란히 보면 아래와 같다.

| 유형 | 오류 37개 | 차별 포착 13개 |
|---|---|---|
| partial_low_coverage | 13 | 8 |
| all_covered_area_mismatch | 18 | 4 |
| no_overlap | 3 | 0 |
| other_overlap | 2 | 0 |
| empty_pred | 1 | 1 |

- CURE의 `no_box`는 전체 11개이고, 이 중 10개가 CURE 선택에 포함됐다. 그 11개 중 오류는 5개였다.
- 공식 GT 대비 기본 위치 오류는 CURE 34/87, MSPC 32/87로 비슷하다.
- 개수 불일치는 `n_C ≠ n_M`이 오류 17/37, 비오류 9/50이다.
- 차별 포착 사례의 순위:
  - CURE-only 7개의 CURE 순위: 1, 4, 9, 18, 19, 21, 22
  - MSPC-only 6개의 MSPC 순위: 1, 9, 10, 14, 18, 22
  - 경계(K=22)에서 위험 점수 동률은 없다.
- MG 예측이 빈 항목은 1개이고, 이 항목은 MSPC-only이자 confidence 선택이다.

# Goal Progress / Reused Assets

- **시험 설정**: iter_113/114의 순위·운영점·검토율은 그대로 보존했고 새로 최적화하지 않았다.
- **연구 관찰**:
  - CURE-only의 일부는 출력 부재 규칙으로 설명된다.
  - 나머지는 경계 부근의 작은 순위 차이이며, 유형이 오류 전체 분포와 크게 다르지 않다.
  - 5개 항목은 대체 주석에서 오류가 사라진다. 주석 입자도에 의존하는 패턴이다.
- **연구 질문**: 단순 설명 이후 남는 구체적 잔여 질문은 확인하지 못했다. 현재 CURE 특화 오류 검토 투자는 보류를 권한다.
- 이 보류는 불일치 정보 전체나 의료 VLM 연구의 기각이 아니다. 보류 범위는 이 고정 파이프라인의 CURE 특화 투자에 한정한다.
- 재사용한 코드: `nr107_geom.py`, `nr113_core.py`, `nr114_core.py`. 순위·기하 계산 범위의 기존 승인을 인용했고 `nr114_run.py`는 재사용하지 않았다.
- `nr114_run.py`의 seal 결함(원시 입력을 재대조하지 않음)은 이번 새 경로에서 `provenance()`와 `cmd_seal`로 보완했다. 변조 검출 fixture도 통과했다.

# Problems

- **현재 결론 무효**: 없다.
- **재사용 전 수정**: provenance는 원시 출력 파일 digest와 request id 연결까지만 대조한다. 원시 logits에서 박스를 만드는 후처리는 재계산하지 않았다(iter_114 verify를 인용). `nr115_simple.py`는 봉인 이후에 추가해 completion 대상이 아니다. 대신 입력 `table87.json`과 자기 코드의 hash를 출력에 남겼다.
- **추후 개선**: overlay 캡션 한글 폰트가 깨졌다. 13장 중 1장만 육안 확인했다. 유형 규약은 사후 정의이고 `t=0.3`은 설명용 기준이다. 소수 항목, 한 환자 2항목, 대체 주석 부재 4개가 있어 해석에 한계가 있다.

# Recommendation to GPT

- 계획의 "음성 탐색" 분기에 따라 현재 CURE 특화 오류 검토 투자는 보류를 권한다. 일관된 차이가 없고, 단순 속성으로 설명되는 부분이 있으며, 주석 선택에 따라 패턴이 달라진다.
- iter_114의 A/B 불확정 판정은 유지한다. 새 실험은 이번에 제안하지 않는다.
- 이 분석으로 이 오류 검토 묶음의 추가 가치는 확인되지 않았다. 다음은 사용자의 승인 후 중요한 다른 질문으로 전환하는 선택지를 권한다.

SELF_CHECK: PASS
SUMMARY: CURE/MSPC 차별 포착 MG 오류 13개와 전체 87개를 기하로 분류·독립 검산했다. 반복되는 특이 실패 조건은 없고 일부는 CURE의 빈 출력 등 단순 속성으로 설명되어, CURE 특화 투자는 보류를 권한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd results/iter_114/mg/INIT_A_w2b4 && head -c 900 raw_worker0.jsonl; echo; head -c 400 mapping.json; cd ../../cure/INIT_w2 && ls . cure/shard0 && head -c 700 cure/shard0/outputs.jsonl
