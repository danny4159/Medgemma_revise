# 요약

- **핵심 결과:** 공통 문구에서는 B0 bbox reader의 이득 대부분이 "검출 유무·개수" 정보로 설명된다. 좌표는 추가 효과가 없었다. E600 기준 semantic S_scope는 U 0.5533, B 0.6067, K 0.6217, L 0.6217이다. L−K는 정확히 0이다.
- **근거:**
  - B−U는 +0.0533이고 97.5% CI는 [0.032, 0.077]이다. L−K는 600명 모두에서 정오가 같았다(불일치 0/600).
  - L과 K의 유효 응답은 P180 360건 전부 같았다.
  - 기존 문구의 P180 predicted는 0.7000이었는데, 공통 문구의 L은 0.6333이다. 기존 이득 일부는 문구 의존이다.
  - L−direct M0는 +0.0117 [−0.015, 0.040]으로 실용 이득이 불확정이다.
- **미검증·주의:**
  - X(좌표 교란)는 실행하지 않았다. 사전 규칙상 L−K가 0이라 조건이 충족되지 않았다.
  - 따라서 "좌표를 읽지 않는다"와 "좌표가 무의미하다"를 구분하지 못했다.
  - 이 결과는 P180/E600 개발 자료 안의 진단이다. 새 학습·reserve·독립 확인은 하지 않았다.
- **다음:** 좌표 추가 투자는 지금 근거가 없다. 이 방향은 단순 검출 baseline을 남기고, 다른 연구 질문으로의 전환을 우선 검토하는 편이 낫다.

# Work Performed

- 계획을 읽고 기존 QA 코드를 확인했다. 결함 3개를 이번 경로에서 보완했다: completion 내용 검증, bbox 원본 hash pin, ALLOW_CHANGED 파일명 우회 제거.
- U/B/K/L(+조건부 X) 요청·분석·확대 결정 코드를 새로 만들었다. 기존 질문·parser·evidence 문구는 그대로 두었다.
- 재사용 자산(iter_015 B0 bbox, iter_016 direct·evidence)을 원본 hash·adapter·영상 기준으로 검증했다.
- D12 동작 확인과 worker 비교, P180 탐색, 사전 규칙에 따른 E600 확대를 차례로 실행했다.

# Files Changed

- 새 파일: `rsna_diag/ev17_spec.py`, `ev17_requests.py`, `ev17_reuse.py`, `ev17_analysis.py`, `ev17_pilot_report.py`, `test_rsna_iter017.py`, `test_rsna_iter017_dry.py`
- 수정:
  - `qa_requests.py`: OUT 기본값 iter_017, `bbox_records` pin·completion 검증
  - `qa_eval.py`: `load_stage`에 completion 검증 연결
  - `qa_run.py`: `verify_completion` 추가
  - `qa_protocol.py`: `verify`를 `allowed_edits`(before/after/reason) 방식으로 변경, `REQUIRED_CODE`에 ev17 모듈 추가
  - `qa_scope.py`: 우회 대입 한 줄 삭제

# Commands / Experiments

- `python -m rsna_diag.ev17_reuse build` — 성공. 8개 stage와 B0 bbox 600건 검증, checkpoint 표가 iter_016과 일치.
- `python test_rsna_iter017.py ...` — 70/70 통과. `test_rsna_iter017_dry.py` — 분석 경로 dry-run 통과(가짜 입력이라 결론에 쓰지 않음).
- D12 96요청: GPU당 1 worker(46.2초)와 2 worker(41.1초)를 비교했다. 요청 집합·greedy token·parse가 동일하고 형식 유효율은 100%였다. GPU당 peak 사용량은 8.8GiB → 17.6GiB(24GiB 중)라서 4 worker를 채택했다. 이 소규모 비교의 이득은 약 12%로 모델 로딩이 지배한다.
- P180 1,440건: 257초, 약 336 req/min, rc 전부 0.
- E600 확대 3,360건: 644초, rc 전부 0.
- 분석 실행: P180은 첫 시도에서 출력 디렉터리가 없어 실패했다. `mkdir` 후 재실행했고 코드는 바꾸지 않았다. E600도 성공했다.
- OOM 없음. 논리 요청 합계는 4,800건이며 dedup(중복 제거)은 하지 않았다.

# Results

- **P180 확대 결정:** `results/iter_017/p180/analysis_p180_decision.json`에 E600 요청 생성 전에 저장했다. B−U가 규칙 3으로 확대를 트리거했다. 그 시점의 B−U는 +0.0444 [0.011, 0.083]이다.
- **E600 (`results/iter_017/e600/analysis_e600.json`):** gate 통과(유효율 ≥95%, 빈 예측 B/K/L 응답 불일치 0/728).

| 비교 | 차이 | CI |
| --- | --- | --- |
| B−U | +0.0533 | 97.5% [0.032, 0.077] |
| L−K | 0.0000 | [0, 0] |
| K−B | +0.015 | 95% [0.007, 0.025] |
| K−U | +0.068 | 95% [0.048, 0.090] |
| U−directM0 | −0.057 | 95% [−0.085, −0.028] |
| L−directM0 | +0.012 | 95% [−0.015, 0.040] |
| L−directB0 | +0.043 | 95% [0.017, 0.070] |

- **category별 B−U:** opacity +0.085, normal +0.060, NoOpacity/NotNormal +0.015.
- **정보 없는 U:** direct M0보다 낮다. 문구가 반응을 바꾼다는 증거이며 특정 문장의 인과는 아니다.
- **NoOpacity/NotNormal:** 모든 evidence 조건이 0.005–0.02이고 direct M0는 0.20이다. evidence 조건이 이 category를 크게 잃는다.
- **B0 bbox+규칙:** S_scope는 0.2733이다(빈 예측의 Q_A는 판단 불가로 계산).
- **비용:** reader 입력은 약 400토큰으로 direct의 301토큰보다 길다. 모듈형에는 localizer 1회 호출이 추가된다. localizer 시간은 재사용 자료에 기록되어 있지 않다.

# Goal Progress / Reused Assets

- **진전:** iter_016의 bbox reader 이득이 좌표가 아니라 검출 신호·개수·문구로 설명된다는 것을 통제 조건으로 확인했다. 좌표 손익은 P180·E600 어디서도 관찰되지 않았다.
- **재사용:** `qa_spec.py`, 승인된 parser·metric, iter_016 direct/evidence 결과를 사용했고 검증 근거는 `results/iter_017/reuse/reuse_manifest.json`에 있다.
- **미검증:** X(L−X), 다른 seed·환자·데이터셋, 좌표가 유용한 다른 과제, 모듈형 대비 detector/encoder+head 비교. 학습 환자 수·presentations 표는 만들지 않았다. checkpoint 표에 epoch·step·train digest만 있다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정:**
  - `qa_run`의 tail 재개·부모 중단 처리와 `qa_scope`의 옛 경로는 이번에 검증하지 않았다.
  - 재사용한 iter_016 stage는 과거 protocol을 재잠금하지 않고 호환성만 확인했다.
- **추후 개선:**
  - 워커가 끝부분에서 느려진다. 요청 파일 재읽기 때문으로 보이며 원인은 확인하지 않았다.
  - L과 K가 응답 텍스트 수준에서 52/360건 다른 것은 대소문자·개행 차이이고 answer 값은 같았다.
  - 확대 규칙 3의 "중요·무효 값 동시 포함" 해석은 내 구현이다.
  - `B−U` 확대는 이 해석 덕분에 트리거됐다(점추정 0.0444는 임계 0.05 미만).

# Recommendation to GPT

- 좌표 방향은 투자를 보류한다. B/K 단순 검출 baseline을 강한 모듈형 baseline으로 남긴다.
- 다른 질문으로 전환을 우선 검토한다. 특히 NoOpacity/NotNormal에서 evidence 조건이 direct M0 대비 크게 잃는 현상(0.2 → 0.02)이 후보다. 이 category에서는 정답이 "no opacity, but abnormal"이라는 점이 직접 질문과 evidence 조건을 갈라놓는다.
- 그 현상은 질문 범위 해석·prior 문제일 수 있고, 아직 원인을 분리하지 못했다.
- X는 필요하면 후속에서 별도 계획으로 다룬다.

SELF_CHECK: FAIL
SUMMARY: 공통 문구 U/B/K/L 진단에서 E600 기준 B−U +0.053 [0.032, 0.077], L−K 정확히 0(불일치 0/600)이라 bbox reader 이득은 검출 유무·개수와 문구로 설명되고 좌표 효과는 없었다. X는 사전 규칙상 미실행이며 좌표 무사용과 무의미의 구분은 미검증이다.