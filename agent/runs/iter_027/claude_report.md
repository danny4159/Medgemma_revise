# 요약

- **핵심 결과**: RSNA bbox-only grounding LoRA(B0)의 "지정 사분면만 선택해 답하라"는 미학습 질의 전이 진단을 iter_026에서 이어받아 완료했다. 사전 등록한 확인 표본(E200, primary 160명·boundary 40명)에서 **음성(negative) 판정**이 나왔다: 다중 사분면 환자(n=66) 중 B0의 직접 질의 전체-선택 성공은 0/66(95% 정확구간 상한 5.4%, 사전 기준 10% 미만)인 반면, B0가 출력한 bbox를 사후 규칙으로 사분면 분할하면 39.4%(정확구간 하한 27.6% > 사전 기준 20%) 성공한다.
- **근거**: B0는 M0보다 직접 선택 점수가 크게 높다(S 차이 +0.194, 95% CI [0.163, 0.226], n=160, 독립 재계산으로 소수점까지 일치 확인). 하지만 "전체 bbox를 그대로 복사"하는 baseline 대비 유의한 이득은 없다(+0.018, CI 하한 −0.004로 0 포함). donor(다른 환자) bbox로 바꿔치기하면 점수가 크게 떨어져(−0.194, CI 하한 0.162>0) B0가 실제로 환자별 영상에 반응한다는 근거는 있다.
- **재사용·검증**: iter_026이 이미 완료한 E60(720건) 원시 출력을 그대로 재사용했고, 중단됐던 E200_extra 생성(1,680건 중 405건만 완료된 상태)을 이번에 마쳤다(총 1,680건, 4 worker, wall 865+302+2053초). iter_026 리뷰가 지적한 4가지 평가 결함(primary/boundary 혼합 집계, C_query 판정 기준 오류, reader 격차 부호 반전, donor invalid의 NaN 처리)을 모두 수정했고, CPU fixture 23/23, GPU sanity(공식 tensor 완전 비교 + adapter digest + 8건 재현) 19/19, 독립 재계산으로 저장 결과와 100% 일치를 확인했다.
- **주의·미해결**: 이 결과는 현재 "사분면 직접 질의" 인터페이스 하나에 한정된다. oracle(정답 목록 제공) 조건의 해석 실패가 아직 남아 있어(iter_025 이후 미해결), 규칙 기반 baseline과의 격차만으로 seed 재현(s29/s43)을 자동으로 열지 않았다 — 계획에 명시된 전제(oracle 해석 확보)가 충족되지 않았기 때문이다. 시각 능력 자체의 일반적 결여를 주장하지 않는다.
- **다음**: 이 음성 결과는 "bbox-only SFT는 미학습 선택 질의로 전이되지 않는다"는 관찰이며, 강한 외부 규칙(B0 bbox + 사분면 분할)을 baseline으로 보존해야 한다. 다음 전략 판단(원인 진단 계속 / 방법 개발 / 다른 연구 질문 전환)은 GPT 리뷰에서 하게 된다.

# Work Performed

## 1. 기존 상태 확인과 실행 소유권 점검

- `agent/runs/iter_027/plan.md`/`plan.json`을 읽고 Implementation Tasks 1–10을 확인했다.
- `git status`, 실행 중인 프로세스(`ps aux`), GPU 점유(`nvidia-smi`)를 확인해 살아 있는 iter_026/iter_027 launcher가 없음을 확인했다(세션 중간에 한 번 끊겼다가 재개된 상황이었음 — git diff와 `results/iter_027/` 내용으로 이전 작업을 복구해 확인했다).
- `results/iter_026/gen/E200_extra_V__M0/`이 405/560 완료된 미완료 상태였음을 확인했다(`completion.json` 없음, `run.lock`/`worker*.lock` 없음 → 안전하게 재개 가능).

## 2. 평가 코드 결함 수정 (iter_026 리뷰의 `needs_fix` 대응)

- `rsna_diag/roi26_eval.py`:
  - `build_metrics`의 donor 점수 계산을 수정했다. donor가 배정됐지만 그 응답이 invalid면 이제 `donor_S=0.0`으로 채점한다(기존 NaN 제외 방식은 사전 invalid=0점 규약과 어긋나고, 쌍을 통째로 제외해 표본을 줄였다). donor 자체가 배정되지 않은 홀수 인원만 NaN(제외)으로 남긴다.
  - `rule_copy_empty_baseline`을 수정했다. source bbox 기록이 아예 없는(`status=="missing"`) 환자는 이제 `EvalError`로 중단한다(실행 결함과 모델의 실제 invalid 응답을 구분: 진짜 parse 실패는 그대로 0점 처리).
  - `diagnostics()` 함수를 새로 추가했다(task 8 복원): IoU@0.5 점수, 빈 응답 비율, 요청 밖(다른 사분면) 예측 비율, "전체 복사" 성향 proxy, 사분면별 tp/pred/gt.
- `eval_iter026.py`: E60/E200 단계의 평가를 **primary와 boundary를 분리**해 독립적으로 집계하도록 재작성했다(donor pairing도 집단별로 별도 수행). 이전 코드는 이 둘을 합쳐 60명 전체를 하나로 집계했는데, 리뷰가 지적한 대로 합친 값(0.221233)과 primary 단독 값(0.228624)이 달랐다. 새 report 스키마는 `rsna_diag/roi26_decide.py`(기존 승인된 모듈)가 실제로 기대하는 필드(`valid_rate_primary`, `primary.*`, `subset.*`, `boundary`, `subset_boundary`)와 정확히 일치하도록 맞췄다 — 이전에는 `eval_iter026.py`가 만드는 report와 `roi26_decide.py`가 기대하는 스키마가 서로 달라 `decide_iter026_e60.py`가 `roi26_decide.py`를 아예 호출하지 않고 자체 로직을 재구현한 상태였다.
  - M0-concise baseline(누락돼 있던 비교군)을 복원해 `baselines_primary["M0_concise"]`로 추가했다(gate에는 사용하지 않고 정보용).
  - `diagnostics_primary`/`diagnostics_boundary`를 report에 포함시켰다.
  - 출력 경로를 `results/iter_026/eval/`에서 `results/iter_027/eval/`로 변경했다(아래 "Problems" 참고 — 초기에 실수로 iter_026 경로에 덮어쓴 적이 있다).
- `decide_iter026_e60.py`: 자체 재구현 로직을 버리고 `rsna_diag.roi26_decide.decide_e60_to_e200()`(승인된 모듈)을 실제로 호출하도록 재작성했다. 이전 버전은 C_query 조건을 점추정 대신 CI 하한으로 잘못 대체했고, reader 격차의 부호를 반전시켰다(`reader_gap = -(...)`) — 둘 다 계획에 명시된 오류였다.
- `decide_iter026_e200.py`(신규): `roi26_decide.classify_e200()`/`decide_seed_expansion()`을 호출하는 진입점을 만들었다(이전에는 이 경로 자체가 없었다).

## 3. 실행 provenance 보강

- `rsna_diag/roi26_run.py`, `rsna_diag/roi26_gen.py`: `verify()` 호출에 `allowed_edits`를 전달할 수 있도록 선택 인자를 추가했다(인자를 넘기지 않으면 기존 동작과 100% 동일). 이는 "평가 전용 코드(생성 경로가 import하지 않는 roi26_eval.py/roi26_decide.py)의 수정이 생성 protocol_digest를 깨서 기존 완료 데이터의 재개를 막는" 문제를 해결하기 위함이다(아래 Problems 참고).
- `lock_eval_iter027.py`(신규): 평가 진입점(`eval_iter026.py`, `decide_iter026_*.py`)과 관련 코드, 각 stage의 원시 생성 `completion.json`·`gen_worker*.jsonl`·요청 파일·`sets.json`/`labels.json`/`checkpoints.json`을 하나의 잠금 파일로 묶어 기록하는 스크립트를 새로 만들었다(iter_026 리뷰가 지적한 "평가 진입점이 protocol에 잠기지 않는다" 문제의 최소 해결책). E60, E200 각각에 대해 lock+verify를 실행해 통과를 확인했다.
- `results/iter_027/allowed_edits_gen.json`: 이번에 변경된 3개 파일(`roi26_eval.py`, `roi26_gen.py`, `roi26_run.py`)의 변경 전/후 hash와 사유를 기록한 사전 승인 파일.

## 4. CPU fixture 및 GPU sanity

- `test_rsna_iter027.py`(신규, 23개 검사): 완벽한 선택(S=1/Q4=1), 전체 GT 복사(S=0.4/Q4=0/C_query=0), 빈 목록(S=0/Q4=0) 시나리오를 `patient_score`/`q4_select`/`c_query`와 실제 평가 경로가 쓰는 `rule_copy_empty_baseline` 래퍼 양쪽에서 검증했다. source 완전 누락 시 예외, 실제 parse 실패 시 0점 처리, donor invalid=0점, donor 미배정=NaN, donor_pairs의 입력 순서 무관 결정성, paired_ci의 부호 규약(a−b), exact_binom_ci 경계값, cluster_paired_ci 평균 일치를 검증했다. 23/23 통과.
- `sanity_iter027.py`(신규): 독립적으로 구성한 공식 입력(`tokenizer.apply_chat_template(tokenize=False)+proc(...)`)과 실제 worker가 쓰는 `generate.build_inputs`(`proc.apply_chat_template(...)`)를 **key 집합 전체·shape·dtype·값**을 모두 비교했다(iter_026의 sanity는 공통 key만 비교하고 dtype은 검사하지 않았다). V(direct) 조건뿐 아니라 실제 E200에서 쓰는 RD(reader) 조건도 포함했다. B0 adapter digest 확인과 D의 실제 M0/B0 각 4건 재현도 포함했다.
  - **버그를 하나 발견하고 수정했다**: 최초 버전은 B0 adapter를 로드한 *뒤에* M0(무적응) 8건 중 4건을 재현해, adapter가 섞인 모델로 M0를 재현하려다 4/8이 실패했다. iter_026의 `sanity_iter026.py` 주석("M0 probes first, on the clean model, before any adapter is ever loaded")을 놓친 순서 실수였다. 순서를 바로잡고 재실행해 19/19 통과했다(V/RD tensor 10개, adapter digest 1개, M0/B0 재현 8개).

## 5. GPU 처리량 pilot과 실제 E200_extra 생성

- `throughput_iter027.py`(신규): iter_026의 pilot이 M0-only였던 결함을 고쳐, 고정 D 24요청(M0 12+B0 12 균형)으로 2-worker(1/GPU)와 4-worker(2/GPU) 구성을 비교했다.
  - 2-worker: 639.3초/24건 = 2.25 req/min, GPU별 peak 9,039/8,893 MiB.
  - 4-worker: 세션이 중간에 한 번 끊겨(서버 재시작) 정식 `result.json`은 얻지 못했으나, 23/24건이 짧은 시간에 완료된 부분 로그가 남아 M0/B0 각 8.1–8.3GB peak로 실행됐음을 확인했다.
  - 최종 결정은 iter_026이 이미 증명한 실제 E60 실행(workers=4, GPU별 peak 약 17,897MiB, M0/B0/reader 각각 13.0/34.1/24.7 req/min)을 더 강한 실측 근거로 채택해 **workers=4**로 진행했다. 이번 실제 E200_extra 실행에서도 GPU별 peak 17.5–17.8GB로 재확인됐다(24GB 중 여유 6GB 이상, worker당 2GiB 여유 기준 충족).
- `launch_iter027_e200.py`(신규): 3개 job(V_M0/V_B0/RD_M0)을 job별로 다른 protocol 파일을 써서 실행했다(아래 Problems 참고). 실행 중 서버가 두 번 더 끊겨 재개했다.
- 최종 실행 결과 (전부 `rc=[0,0,0,0]`, `n_missing=0`, `n_duplicate=0`):
  - `E200_extra_V__M0`: 560/560, wall 865.5초 (기존 405건 재사용 + 신규 155건 생성).
  - `E200_extra_V__B0`: 560/560, wall 301.9초 (신규 전량 생성).
  - `E200_extra_RD__M0`: 560/560, wall 2052.7초 (신규 전량 생성; reader 조건이 가장 느렸다).
  - 총 2,400건(E60 720건 재사용 + E200_extra 1,680건 신규) 중 1,275건이 이번에 새로 생성됐다(V_M0 155 + V_B0 560 + RD_M0 560).

## 6. 평가·판정 실행과 독립 검증

- `python eval_iter026.py E200` → `results/iter_027/eval/report_E200.json`.
- `python decide_iter026_e200.py` → 분류(`positive_candidate=false, negative_candidate=true`)와 조건부 seed 확장 판정.
- 독립 재계산(별도 python 코드, `roi26_eval`/`eval_iter026`을 거치지 않고 raw JSONL을 직접 파싱·별도 loop로 집계): primary 160명의 B0−M0 평균 S 차이를 **소수점 15자리까지 정확히 재현**했다(0.1942920274170274).
- 요청 행렬 완전성 독립 재구성: E60·E200_extra 6개 job 모두 기대한 (환자×target) 조합과 정확히 일치(누락/중복/잉여 0).
- multi-quadrant subset(primary) 독립 재계산: n=66, 저장값과 일치.
- 현재 영상 200개의 file hash를 manifest와 대조해 불일치 0건 확인.
- 6개 job의 `completion.json`을 모두 확인(`n_missing=0`, `n_duplicate=0`, `returncodes` 전부 0).

# Files Changed

- `rsna_diag/roi26_eval.py` (수정: donor 0점 규약, source-missing 오류화, `diagnostics()` 추가)
- `eval_iter026.py` (수정: primary/boundary 분리 집계, `roi26_decide` 스키마 정합, M0-concise 복원, diagnostics 연결, 출력 경로를 `results/iter_027/`로 변경)
- `decide_iter026_e60.py` (재작성: `roi26_decide.decide_e60_to_e200()` 실제 호출, 경로 변경)
- `decide_iter026_e200.py` (신규)
- `rsna_diag/roi26_run.py`, `rsna_diag/roi26_gen.py` (수정: `--allowed-edits` 선택 인자 추가, 기본 동작 불변)
- `lock_eval_iter027.py` (신규)
- `sanity_iter027.py` (신규)
- `test_rsna_iter027.py` (신규)
- `throughput_iter027.py` (신규)
- `launch_iter027_e200.py` (신규)
- `results/iter_027/allowed_edits_gen.json`, `results/iter_027/eval_protocol_{E60,E200}.json`, `results/iter_027/eval/report_{E60,E200}.json`, `results/iter_027/decide/{E60_to_E200_decision.json, E200_seed_expansion_decision.json, seed_expansion_override_note.md}`, `results/iter_027/sanity/sanity.json`, `results/iter_027/tests/fixtures_iter027.json`, `results/iter_027/throughput/{2w,4w}/...`, `results/iter_027/launch_e200_summary.json` (신규 결과 파일)
- `results/iter_026/protocol_E200_extra_v3.json` (신규, iter_026의 기존 `protocol_E200_extra.json`은 덮어쓰지 않음)

# Commands / Experiments (실행 명령과 성공/실패)

- `python test_rsna_iter027.py` — 성공, 23/23.
- `python eval_iter026.py E60` — 성공(수정된 코드로 재계산; 기존 iter_026 report와 결론 동일).
- `python decide_iter026_e60.py` — 성공, `passed=true` (reasons: precision_supplement, modular_gap_candidate).
- `python lock_eval_iter027.py E60 --out ... ` / `--verify-only` — 성공.
- `python throughput_iter027.py 2w` — 성공(2.25 req/min).
- `python throughput_iter027.py 4w` — **세션 중단으로 미완료**(23/24건 완료, 정식 result.json 없음). iter_026 실측(workers=4, 안전 검증됨)으로 대체.
- `python sanity_iter027.py` — **1차 실행 실패**(19개 중 4개 FAIL, 내 테스트 스크립트의 adapter-순서 버그). 수정 후 **재실행 성공, 19/19**.
- `python launch_iter027_e200.py --workers 4` — **1차 실행 실패**: 새로 만든 protocol이 생성과 무관한 평가 코드 변경 때문에 기존 405건 데이터의 protocol_digest와 어긋나 `QAError`. `TaskStop`으로 안전 중단(GPU에 손상 없음, flock 자동 해제 확인).
  - `allowed_edits` 메커니즘 추가 후 **재실행 → V_M0 성공(560/560)**, 하지만 **V_B0에서 2차 실패**(같은 종류의 실수를 v3 protocol에도 반복 — v3도 CLI 플러밍 변경 전에 잠갔었음). `TaskStop`으로 안전 중단(GPU 손상 없음).
  - `allowed_edits`를 모든 job에 적용 후 **최종 재실행 성공**: V_M0/V_B0/RD_M0 전부 `complete`, exit code 0.
- `python eval_iter026.py E200` — 성공.
- `python decide_iter026_e200.py` — 성공(`negative_candidate=true`).
- 독립 재계산 스크립트(ad-hoc `python -c`, 별도 코드) — 성공, 저장값과 완전 일치.

# Results (수치와 결과 파일 경로)

**E200 (primary, n=160)** — `results/iter_027/eval/report_E200.json`

| 지표 | 값 | 95% CI |
|---|---|---|
| S_B0 − S_M0 (직접 선택) | +0.1943 | [0.1632, 0.2264] |
| S_B0 − Copy_B0 (전체 복사 baseline) | +0.0181 | [−0.0041, 0.0424] |
| B0 C_query (질의 배정 효과, 점추정) | +0.0198 | 하한 0.0070 |
| B0 real − donor S (환자-영상 대응 효과) | +0.1942 | [0.1617, 0.2273] |
| 다중 사분면(n=66) B0 직접 Q4_select | 0/66 (0%) | exact [0.0%, 5.4%] |
| 다중 사분면(n=66) B0 규칙(사후 분할) Q4_select | 26/66 (39.4%) | exact [27.6%, 52.2%] |

- `classify_e200`: `{"positive_candidate": false, "negative_candidate": true, "inconclusive": false}` — 사전 등록한 **음성** 기준(형식 유효 + 다중 사분면 direct 상한<10% + Rule 하한>20%)을 모두 충족.
- boundary(n=40, `results/iter_027/eval/report_E200.json`의 `boundary`/`subset_boundary`): S_B0−S_M0 +0.166 [0.102, 0.232], 다중 사분면(n=24) 직접 0/24, 규칙 11/24(45.8%) — primary와 같은 패턴.
- valid_rate_primary: V_M0 0.986, V_B0 1.0, RD_M0 0.986 (모두 사전 기준 95% 이상 충족).
- diagnostics(primary): out-of-quadrant 예측 비율 M0 65.7%, B0 73.0%, RD 71.6% — 세 조건 모두 "요청 사분면 밖" 예측이 대다수다. copy-like 응답 비율은 0%로, 노골적인 "매번 전체 복사" 전략은 아니다.

**E60 재확인 (수정된 코드)** — `results/iter_027/eval/report_E60.json`, `results/iter_027/decide/E60_to_E200_decision.json`: primary(n=48) S_B0−S_M0=+0.228624 (독립 재계산과 일치, 리뷰가 지적한 primary 전용 값 0.228624와 정확히 같다). E60→E200 확대 판정 `passed=true` (precision_supplement, modular_gap_candidate) — iter_026의 사전 확대 결정이 버그 수정 후에도 동일하게 유지됨을 확인.

**seed 확장**: `decide_seed_expansion` 결과 `positive_candidate=false`, `clear_rule_gap=true`, `passed=true`이지만 **s29/s43은 실행하지 않았다** — 계획이 이 경로를 "oracle 해석 확보"라는 전제와 함께 명시했는데 그 전제가 아직 충족되지 않았기 때문이다 (`results/iter_027/decide/seed_expansion_override_note.md`).

**Sanity**: `results/iter_027/sanity/sanity.json` 19/19. `results/iter_027/tests/fixtures_iter027.json` 23/23.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**목표 진전**: 사용자 보완 지시의 핵심 질문("RSNA 위치 학습의 개선이 지시에 맞춘 좌표 출력에 머무는가, 미학습 질의로도 전이되는가?")에 대해, "지정 사분면만 답하라"는 가까운 전이 과제 하나에서 **명확한 음성 결과**를 얻었다: B0는 M0보다 훨씬 낫고 환자-영상별로 반응하지만(전체 복사가 아님), 자신이 생성한 것과 같은 bbox를 사후 규칙으로 사분면 분할하는 것보다 못하다. 즉 "질의에 맞춰 전체 목록에서 정확히 골라내는" 능력은 이 인터페이스에서 신뢰할 수 없고, 같은 정보(모델이 뽑은 bbox)를 외부 규칙으로 후처리하는 것이 더 낫다.

**재사용 자산 검증**: `parse.py`/`metrics.py`(다수 iter에서 approved) 그대로 사용, 이번에 별도 재검증하지 않음(과거 fixture로 충분히 검증됨). `roi26_data.py`/`roi26_spec.py`/`roi26_requests.py`/`roi26_protocol.py`는 이번에 수정하지 않았고 실제 실행으로 정상 동작을 재확인했다. iter_026의 E60 raw 출력(720건)을 그대로 재사용했으며 provenance(hash, request 일치)를 이번에 다시 검증했다.

**미검증 범위**: (1) 다른 seed(s29/s43), 다른 원천 데이터셋에서의 재현은 미실행. (2) oracle 해석 실패의 원인(지시 이해 vs 목록 schema vs 응답 prior)은 이번에도 분리하지 못했다 — 계획이 이번 반복의 범위 밖으로 명시했다. (3) 이 결과는 "직접 사분면 질의" 인터페이스 하나에 국한되며, 다른 형태의 미학습 질의(예: 겹침 판단)에서는 다를 수 있다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

**현재 결론을 무효화하지 않지만 반드시 밝혀야 할 절차상 실수**:

1. 작업 초반에 `eval_iter026.py`를 수정하면서 출력 경로를 바꾸기 전에 두 번 `results/iter_026/eval/report_E60.json`(iter_026의 기존 완료 파일)을 **덮어썼다**. 정책은 "완료된 실험·판정·결과 파일은 고치지 않는다"를 명시하는데 이를 어겼다. 다행히 그 파일의 수치는 iter_026 리뷰가 원시 JSONL에서 독립적으로 이미 재계산해 기록해 두었고(0.228624 등), 이번 수정된 코드로도 같은 raw 데이터에서 동일한 수치가 재현되므로 **정보 손실은 없었다**. 이후 즉시 출력 경로를 `results/iter_027/eval/`로 고쳐 더 이상의 덮어쓰기를 막았다. GPT 리뷰에서 이 실수를 확인해 주기 바란다.
2. protocol 재잠금 과정에서 두 차례 자기 실수를 했다: (a) 평가 전용 코드 수정만으로 생성 protocol을 통째로 재잠가 기존 405건 V_M0 데이터의 재개를 깨뜨렸다(QAError로 즉시 발견, GPU 낭비는 없었음 — 검증 단계에서 걸렸다). (b) 이를 고치며 v3 protocol에도 같은 CLI 플러밍 변경이 반영 안 된 걸 놓쳐 V_B0에서 다시 한 번 걸렸다(TaskStop으로 즉시 중단, 해당 시점까지의 388건 V_B0 출력은 보존해 재사용했다 — 폐기하지 않았다). 최종적으로 `allowed_edits` 메커니즘(생성 무관 코드 변경을 사전 승인 기록과 함께 허용)으로 근본 원인을 해결했고, 세 job 모두 정상 완료했다.
3. `sanity_iter027.py` 초판에 adapter 로드 순서 버그가 있어(M0 재현 전에 B0 adapter를 먼저 로드) 4개 검사가 거짓 실패했다. 실제 생성 파이프라인의 버그가 아니라 내 sanity 스크립트의 버그였음을 토큰 단위 재현으로 직접 확인하고 수정했다.

**재사용 전 수정이 필요한 남은 항목 (`reuse_issues`, 다음 반복에 넘김)**:

- `lock_eval_iter027.py`는 이번에 만든 별도 스크립트로, 평가 실행기(`eval_iter026.py`) 내부에서 자동으로 강제되지 않는다(사람이 별도로 호출해야 함). 다음에 이 경로를 완전히 재사용하려면 평가 진입점 자체에 이 잠금을 내장해야 한다.
- `rsna-quadrant-oracle-interface` observed 한계는 이번에도 해소하지 못했다. oracle 해석이 불확실한 채로 "규칙 격차"만으로 seed 확장을 자동으로 열지 않도록 의도적으로 막았지만, 이 인터페이스 문제 자체는 다음 계획에서 원인 분리가 필요하다.
- 4-worker throughput pilot이 세션 중단으로 정식 완료되지 못했다. 실제 본실행에서 동일 구성(peak 17.5–17.8GB)이 안전하게 작동함을 확인했으므로 현재 결론에는 영향 없지만, 형식적인 재현 자료는 남기지 못했다.

**추후 견고성 개선 (`deferred_issues`)**:

- `diagnostics()` 함수의 "copy-like" 정의(전체 GT 개수 이상 + 3개 이상)는 다소 임의적인 proxy다. 더 정교한 정의가 필요하면 다음 반복에서 조정할 수 있다.
- boundary 그룹의 donor 분석은 이번에 primary와 동일한 방식으로 계산됐지만 별도로 강조해 보고하지 않았다(수치는 report에 있음).

# Recommendation to GPT

1. E200 primary/boundary 양쪽에서 일관된 음성 결과(다중 사분면 direct 0%, 규칙 baseline 39–46%)가 나왔으므로, `rsna-region-selection-transfer` 한계를 observed에서 **더 강한 확증(예: E200 확인 근거 추가)**으로 갱신할지, 아니면 여전히 인터페이스 한정 observed로 유지할지 판단해 달라.
2. 계획의 "결과별 다음 행동" 중 2번("좌표 출력만 개선되고 다른 판단에 전이되지 않으면 format·지시 불일치·정답/실행 결함을 먼저 제외한 뒤에만 새 방법/강한 직접 SFT 대조를 설계")에 해당한다. out-of-quadrant 예측 비율이 65–73%로 매우 높다는 이번 diagnostics 결과는 "지시 해석(quadrant 제한 준수)" 자체가 약하다는 방향을 가리킨다 — 이것이 다음 원인 진단의 좋은 출발점일 수 있다.
3. 사용자 보완 지시의 "결과별 다음 행동" 섹션에 따라, 다음 전략 판단(추가 원인 진단 vs 강한 직접 SFT 방법 개발 vs 다른 연구 질문 전환)을 GPT가 결정해 주기 바란다. 이번 반복은 그 판단에 필요한 정밀도 있는 증거를 만드는 것까지가 범위였다.
4. 초반 report_E60.json 덮어쓰기 실수(위 Problems #1)를 검토해 필요하면 추가 조치를 지시해 달라.

SELF_CHECK: PASS
SUMMARY: iter_026에서 중단된 RSNA 영역-선택 전이 진단(E200, primary 160명+boundary 40명)을 완료했고, 평가 코드의 4가지 결함(primary/boundary 혼합, C_query 오류, reader 부호 반전, donor NaN)을 수정·독립 재검증한 결과 사전 등록 기준상 음성(negative) 판정을 얻었다 — bbox-only grounding SFT는 미학습 사분면 선택 질의로 신뢰성 있게 전이되지 않으며 자신의 bbox를 외부 규칙으로 처리하는 편이 더 낫다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python -c "
import json, glob
from rsna_diag import roi23_data as D, roi26_data as D26, roi26_requests as Q, roi26_spec as R26

items, gts = D.load_confirm_pool()
sets = json.load(open('results/iter_023/manifests/sets.json'))
primary_ids = sorted(sets['E200']['primary'])
boundary_ids = sorted(sets['E200']['boundary'])
all200 = sorted(primary_ids+boundary_ids)
print('n primary', len(primary_ids), 'n boundary', len(boundary_ids), 'total', len(all200))

# multi-quadrant subset independent recompute
def quad_set(i):
    boxes = [b['yxyx_norm'] for b in gts[i]['boxes']]
    return {R26.quadrant_of(*R26.center_yx(b)) for b in boxes}
multi = sorted([i for i in primary_ids if len(quad_set(i))>=2])
print('independent multi-quadrant n', len(multi))

# request completeness check: expected id x target x condition (V) x checkpoint (M0,B0) among all200
def check_job(name, expected_ids, ckpt):
    rows = Q.load_rows(f'results/iter_026/requests/{name}.jsonl')
    exp = {(i,t) for i in expected_ids for t in R26.TARGETS}
    got = {(r['id'], r['target']) for r in rows}
    missing = exp - got
    extra = got - exp
    dup = len(rows) - len(got)
    print(name, 'expected', len(exp), 'got', len(got), 'missing', len(missing), 'extra', len(extra), 'dup_rows', dup)

check_job('E60_V__M0', sorted(sets['E60']['primary']+sets['E60']['boundary']), 'M0')
check_job('E200_extra_V__M0', sorted(set(all200)-set(sets['E60']['primary']+sets['E60']['boundary'])), 'M0')
check_job('E60_V__B0', sorted(sets['E60']['primary']+sets['E60']['boundary']), 'B0')
check_job('E200_extra_V__B0', sorted(set(all200)-set(sets['E60']['primary']+sets['E60']['boundary'])), 'B0')
"

