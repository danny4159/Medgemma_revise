# 요약

- **핵심 결과:** 공동(J) 형식 직접 SFT는 공동 요청의 F1@0.3을 크게 회복했다. V96에서 C 0.368, 추가 독립 SFT(E) 0.333, J 0.523이다. J의 독립 I-short F1은 0.590으로 E의 0.559보다 낮지 않다.
- **실용 판정:** 적응 MedGrounder(A)는 F1@0.3 0.594, F1@0.5 0.394로 E_I 0.559/0.302, J_J 0.523/0.256보다 높거나 같다. A는 요청 처리도 약 30배 싸다. 사전 규칙의 결과는 `residual_joint_loss`이고, 다음 투자는 "공동 grounding 방법 투자 보류"이다.
- **주의:** 단일 seed, 두 양성 문장, 개발 집단 V96에 한정된 결과다. 직접 SFT 자체는 새 방법이 아니고 신규성 판단이 아니다.
- **자원 사용:** GPU 시간은 학습 약 1.8 GPU-hours(epoch 8까지), V96 생성은 E 860초·J 1,673초(wall) 등이다. 외부 프로세스 때문에 첫 timing 시도가 한 번 거부됐고, 이는 아래에 기록했다.
- **다음:** 사전 규칙상 비교를 종료하고 관찰을 보존한다. 방향 판단은 GPT 리뷰에서 한다.

# Work Performed

1. 반입 28개 blob이 manifest와 일치함을 확인했다. C epoch03 adapter digest(419ae81f…)와 기존 C(iter_040/041)·A(iter_046) 출력은 자체 import 검증기로 재검증했다.
   - 기존 점수가 그대로 재현됐다: C I/AB/BA 0.57795/0.38108/0.35417, A@0.8 0.59444/0.39410.
2. 학습기 `pg48_train.py`를 `pg40_train.py` 기반으로 새로 만들었다. 모드는 `ce`(E)와 `joint`(J)다.
   - 학습기 안의 validation은 제거했다. J의 AB/BA는 환자 hash+epoch parity로 균형 배정한다.
   - 초기 adapter는 C의 digest로 강제하고, config·소스·precision을 checkpoint에 묶었다.
3. 동작 확인을 수행했다.
   - 자료 gate: 20/20
   - 공식 processor·mask·EOS 대조: 32/32
   - GPU gate: 8/8
   - 중단-재개: 8개 시나리오 전부 digest 정확 일치
   - 학습 lock
4. E·J를 각 5 epoch(195 updates) 학습했다.
   - D24 선택 규칙(`pg48_dsel.py`)이 연장 조건을 충족해 둘 다 8 epoch(312 updates)까지 한 번 연장했다.
   - D24에서 공통 epoch 8이 선택됐다.
5. V96에서 E/J 각 384요청(총 768)을 생성하고 평가했다.
   - 환자 paired bootstrap은 10,000회, seed 4801이다.
   - 독립 verifier(별도 parser·matching·bootstrap)가 통과했다.
6. 6개 paired timing block을 실행했다. 보고서와 독립 재계산이 모두 일치한다.
7. 사전 판정(`pg48_decide.py`)을 실행하고, 최종 봉인(`pg48_final.py`)으로 `completion.json`을 만들었다.

# Files Changed

새 파일은 모두 `research/` 아래다.

- **학습·gate:** `pg48_train.py`, `pg48_gates.py`, `pg48_resume_check.py`, `pg48_locktest.py`, `pg48_ce.py`
- **요청·생성·평가:** `pg48_requests.py`, `pg48_import.py`, `pg48_eval.py`, `pg48_dsel.py`, `pg48_decide.py`, `pg48_verify.py`, `pg48_gentests.py`
- **실행·timing:** `pg48_jobs.py`, `pg48_seq.py`, `pg48_waitgpu.py`, `pg48_ctime.py`, `pg48_time.py`, `pg48_time_report.py`, `pg48_timing_verify.py`, `pg48_launchtests.py`, `pg48_final.py`
- **수정한 반입 파일:** `mg45_launch.py`(config 불일치 거부, 동시 launcher lock, barrier 전 child 사망 시 자기 child만 종료). 원본 sha256 `02a427fd…`, 수정본 `ff52d4cc…`는 `results/iter_048/protocol/mg45_launch_amendment.json`에 연결했다.
- **그 외 반입 파일:** 수정하지 않았다.
- **결과:** `results/iter_048/` 하위의 `tests/`, `train/`, `gen/`, `eval/`, `timing/`, `timing_pilot/`, `decisions/`, `protocol/`, `requests/`, `completion.json`

# Commands / Experiments

GPU는 `pg48_jobs.py`(상속된 허용 집합 0,1 안에서만 배정)와 `pg43_run.py launch`로 실행했다. 성공/실패는 아래와 같다.

| 항목 | 결과 |
|---|---|
| 자료·입력 gate | data 20/20 PASS. inputs는 첫 시도가 FAIL이었다(원인: 내 gate의 이중 BOS 오류, 원본 `gate_inputs.json` 보존) → `_v2` PASS |
| GPU gate | 첫 실행 FAIL(accumulation 차이 1.18% = 같은 함수 반복 노이즈 1.20%, 사전 허용 2e-3이 비결정 backward를 구분 못 함, `gate_gpu_01.json` 보존). 결정적 모드로 다시 설계해 PASS(반복 노이즈 ≤1e-6, accumulation ≤2e-3) |
| 학습 microbatch | E: mb1 17.8초/step, mb2 12.7초/step. 메모리는 같아 mb2를 선택. J는 환자당 1 sequence |
| E/J 5 epoch | 각 rc=0, 2,422초 wall, peak allocated 9.8GB |
| 8 epoch 연장 | rc=0 |
| 생성 worker 구성 | D8: 2 worker 135초, 4 worker 90초 → 4 worker 채택. peak reserved 8.35GB, 1회 거부는 `peak-gb 10`의 메모리 gate가 `free 24561 < need 24576 MiB`로 작동한 것 |
| D24 J_e5 | 마지막 1요청(반복 출력, cap 8000)에서 세션이 끊겨 95/96에서 중단. 같은 out-dir로 재개했고 `occupancy`의 worker→GPU 매핑 `KeyError`가 나서 4 worker로 재호출해 completion을 만들었다. 이 D24 completion의 비용 필드는 두 attempt가 섞여 의미 없고, 판정에는 쓰지 않았다 |
| timing 첫 시도 | 다른 사용자의 프로세스(`tof_1dcm/run_full_volume.py`)가 GPU1을 12GB 점유해 메모리 gate가 block1 시작을 거부했다(측정 없음, `block1_a1_E` 보존). 그 프로세스는 건드리지 않았다. GPU가 빈 뒤 6개 block 전부 attempt 2로 실행했고, `resource_log`로 외부 부하 없음을 확인했다 |

# Results

**검사 (출처: `tests/`, 단위는 항목 수)**
- 재개: E/J×(epoch 중간, epoch 경계) 모두 loss·grad 차이 0, adapter·optimizer·RNG digest 일치(`tests/resume/resume_compare.json`).
- 생성 경로 D8: 2w/4w/중단-재개 간 token 불일치 0이고, 저장된 iter_041 C 출력과도 32/32 일치했다. 변조·누락·중복·wrong config 8종은 모두 거부됐다(`tests/gen_tests.json`). 한 항목의 expected-branch 라벨 불일치는 내 검사의 문자열 오류이고, 거부 자체는 유지됐다.
- launcher: barrier 전 child 사망, config 불일치, 동시 launcher 3종 모두 통과(`tests/launch_tests.json`).

**D24 선택 단계 (선택 자료, `decisions/`)**
- 연장 규칙: E_I의 e5−e2 F1 변화 −0.037, J_J의 변화 +0.038(≥0.02) → 연장 발동.
- 선택 점수 (E_I+J_J)/2: e2 0.5247, e5 0.5252, e8 0.5330 → 공통 epoch 8.
- D24 teacher-forced CE는 E_I 0.776→0.921, J 0.709→0.739로 held-out에서 증가했다. 생성 F1 추세와 일치하지 않는다.

**V96 정확도 (`eval/report.json`, 96명·192문장, F1@0.3)**

| 시스템 | I | 공동(AB/BA 평균) | 비고 |
|---|---|---|---|
| C | 0.578 | 0.368 | 기존 |
| E | 0.559 | 0.333 | invalid 0 |
| J | 0.590 | 0.523 | I에서 1건 truncated(반복 출력) |
| A | 0.594 (문장별) | — | F1@0.5 0.394 |

- 주비교 M1 J_J−E_J: +0.190 (97.5% CI [0.138, 0.244]).
- 주비교 M2 손실 감소 (E_I−E_J)−(J_I−J_J): +0.159 (CI [0.097, 0.221]).
- 독립 성능: J_I−E_I +0.032 (95% CI [−0.014, 0.079]).
- 충분성: J_AB−E_I −0.037 (97.5% CI 하한 −0.095), FP/문장 차이 95% CI 상한 0.287로 사전 허용을 충족하지 못했다.
- 잔여 공동 손실: J_I−J_J = +0.067 (CI 하한 0.025)가 남았다.
- J_J−A −0.071 [−0.158, 0.016], F1@0.5 −0.138 (CI 하한 −0.202).
- E_I−A −0.036 [−0.123, 0.050], F1@0.5 −0.093 (CI 하한 −0.166).
- 층별(F1@0.3, J_J 기준): 복수 box 문장 0.48 vs A 0.62, 작은 box 0.36 vs A 0.50. 큰 box 0.69는 A 0.69와 비슷하다.

**비용 (6개 paired block, 환자 96명, `timing/timing_report.json`)**
- E / J / A 평균
  - device-seconds: 661 / 636 / 21
  - 환자/분: 17.4 / 18.0 / 510
  - p95 latency: 19.9초 / 21.6초 / 0.64초
- J/E 비율 (95% CI)
  - device-seconds 0.963 [0.922, 1.007]
  - throughput 1.033 [0.990, 1.078]
  - p95 latency 1.075 [0.916, 1.261]
  - 세 지표 모두 비용 기회 기준을 충족하지 못했다.
- A/E device-seconds 비율 0.032.
- timing 출력과 고정 정확도 출력 대조: E/J token 불일치 0, A box 불일치 0.

**사전 판정 (`decisions/final_decision.json`)**
- recovered=true, sufficient=false, residual=true.
- adv_E_I_over_A=false, adv_J_J_over_A=false, cost_opportunity=false.
- outcome=`residual_joint_loss`, next=`hold joint grounding method investment`.

# Goal Progress / Reused Assets

- **새로 확인한 것:** 공동 형식을 직접 학습하면 공동 손실의 큰 부분이 회복된다(약 0.19 F1@0.3). 같은 annotation 노출의 추가 독립 SFT로는 회복되지 않는다. 이전의 "공동 요청 손실은 학습 형식을 학습하지 않은 영향이 아직 분리되지 않았다"는 질문에 대한 답이다.
- **회복은 부분적이다:** 독립 형식 대비 J_J−J_I 잔여 손실 0.067이 남았고, 작은 box·복수 box에서 A가 더 높다.
- **미검증·한계:** 단일 seed, 개발 V96, 두 양성 문장이다.
  - prompt·직렬화·영상 반복을 함께 바꾼 개입이라 순수한 syntax 효과나 내부 원인으로 해석할 수 없다.
  - D24 CE 증가와 생성 F1 상승의 불일치 원인은 확인하지 못했다.
  - 부재 거부·보고서 생성·언어 근거 답변은 평가하지 않았다.
- **재사용 검증:**
  - 승인 모듈(pg43_run·pg39_spec·rsna_diag 등)의 blob 일치와 새 protocol의 소스 잠금을 확인했다.
  - 공식 processor 대조, 요청 행렬 강제, 변조 거부, 2/4 worker 정합성도 수행했다.
  - `pg43_eval`은 순수 좌표 변환 helper만 사용했다. `verify_import`는 쓰지 않았다.
  - 보조 채점기 `pg40_verify`는 호출하지 않았고, 별도 verifier를 새로 만들었다.
  - MG 학습기는 사용하지 않았고, A는 재학습·threshold 재선택 없이 iter_046 출력을 재사용했다.
- **MG 쪽 `required_checks` 중 직접 수행하지 않은 것:** 공식 소스 44개·text encoder 출처 digest, D8에서 A의 공식 입력 tensor 대조. iter_046의 검증 기록에 의존했다.
- **전략 판단 근거:** `padchest-sentence-grounding-and-joint-retention` 관찰은 유지된다. 이번 결과는 그 관찰을 설명하는 근거를 추가하되, 방법 투자의 근거를 만들지는 못했다.

# Problems

- **현재 결론을 무효로 하는 문제:** 발견하지 못했다. 독립 verifier 84개 CI와 환자 벡터가 일치했고, completion은 모든 검사가 통과해야만 작성된다.
- **재사용 전 수정이 필요한 것**
  - `pg43_run` 재개 launcher의 occupancy에 worker→GPU 매핑 `KeyError`가 있다. 이전 attempt의 worker 번호가 현재 매핑에 없으면 completion을 쓰지 못한다.
  - `pg48_ctime.py` timing worker는 재개를 지원하지 않는다(의도). 기술 실패 block은 새 attempt에서 전체 재측정한다.
  - verifier와 timing 검증에서 t(5) 상수와 부트스트랩 방식은 같은 정의라 독립성이 제한적이다.
  - `pg48_gentests`의 한 항목 expected-branch 라벨이 틀렸다.
- **추후 개선**
  - J의 반복 출력(cap 8000까지 이어지는 loop)이 요청 지연을 크게 늘린다. 이 문제를 줄이는 방법은 이번 범위가 아니다.
  - 시스템 prompt·seed·독립 환자 재현은 하지 않았다. 사전 계획대로 가능성 탐색의 종료점이다.

# Recommendation to GPT

- **결과 해석:** 직접 공동 SFT는 학습 형식 설명을 지지한다(M1·M2가 사전 기준 0.10 이상이고 CI 하한 >0). 그러나 독립 형식 보존 충분성과 MedGrounder 대비 정확도 이점은 모두 미달이고 비용 이점도 없다. 사전 규칙의 결론은 현재 공동 grounding 방법 투자 보류다.
- **구분해서 볼 것:** 검증 부족, 가치 부족, 별도 관찰(J의 부분 회복, 작은·복수 box에서의 약점)을 분리해 판단하기를 권한다. 이번 비교는 두 양성 문장 grounding에 한정된다.
- **추가 투자는 보류를 권한다.** 표본·seed·prompt·timing을 늘리거나 별도 loss 탐색을 붙일 근거는 이번 결과에 없다.

SELF_CHECK: PASS
SUMMARY: 같은 C checkpoint에서 직접 공동 SFT(J)와 추가 독립 SFT(E)를 비교해, J가 공동 F1@0.3을 0.333→0.523으로 회복(M1 +0.190 [0.138,0.244])하나 독립 보존 충분성·MedGrounder 대비 이점(J_J−A −0.071)·비용 이점(J/E 0.96)이 모두 미달해 사전 규칙상 공동 grounding 방법 투자 보류(단일 seed·개발 V96·두 양성 문장 한정).

# [orchestrator] 권한 거부된 도구 호출
- Bash: until [ $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1) -lt 1500 ]; do sleep 30; done; echo GPUs free; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
- Bash: until [ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)" ]; do sleep 30; done; echo GPUs free
