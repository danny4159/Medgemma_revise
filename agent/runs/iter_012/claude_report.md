# 요약

- **핵심 결과:** 재개 결함을 GPU 비결정성과 분리해서 확인했습니다. 결정적 kernel에서는 무중단 학습과 5회 중단·재개 학습이 bitwise로 같았습니다(GPU 검사 59/59). 이 검증된 코드로 원래 규모의 실험을 끝까지 실행했습니다. 확인 집단(양성 400명)에서 직접 LoRA SFT가 가장 강한 단순 비교군(`prior_set`)보다 F1@0.3이 **+0.216 (95% CI 0.172–0.259)** 높았고, 사전 기준 5개를 모두 충족했습니다.
- **근거:**
  - seed별 F1@0.3은 0.631, 0.636, 0.653입니다. 비교군과의 차이는 +0.207, +0.212, +0.229로 모두 양수입니다.
  - 전체 유효 출력률은 100%입니다. 음성 층의 valid_empty율은 concise base보다 낮아지지 않았습니다(Normal 0.765 → 0.975–0.98, NoOpacity/NotNormal 0.195 → 0.665–0.72).
  - 모든 선택·comparator·연장 판정은 최종 평가 시점에 원시 요청에서 다시 계산해 파일과 일치함을 확인했습니다.
- **미검증·주의:**
  - 이 결과는 직접 적응 baseline의 확립입니다. 새 방법론의 기여나 다른 데이터셋에서의 재현은 아닙니다.
  - 세 seed 모두 마지막 epoch(5)가 선택됐습니다. 사전 규칙으로는 연장하지 않았지만 학습이 부족했을 가능성은 남습니다.
  - base validation은 `generate.py`의 기존 결함 때문에 부모 record를 재사용하지 못하고 새로 생성했습니다.
  - 잔여 오류가 큽니다: F1@0.5는 약 0.31–0.36, 양성인데 빈 응답이 15–18%, 작은 병변 F1은 약 0.42–0.44입니다.
- **다음:** 잔여 오류(위치 정밀도, 양성 미검출, 작은 병변)를 겨냥한 방법을 이 SFT baseline과 비교합니다. 두 번째 데이터셋 재현도 필요합니다.

# Work Performed

1. **실행 상태·부모 결과 감사** (`results/iter_012/recovery/parent_audit.json`)
   - iter_011 학습 PID 3786218/3786219는 종료된 상태였고 train.lock도 풀려 있었습니다(읽기 전용 flock probe로 확인). 시작 시점에 GPU compute 프로세스는 없었습니다.
   - 두 run 모두 step 300까지 진행됐습니다. epoch 2 validation은 29/4건만 남은 미완료 상태였습니다.
   - **LR 정정:** 원시 응답에서 다시 계산하면 lr1e-4는 F1@0.3 0.4740 / utility 0.5895, lr2e-4는 0.4932 / 0.5991입니다. iter_011 STATUS.md는 두 LR의 수치를 뒤바꿔 적었습니다.
   - **부모 궤적은 재사용하지 않았습니다.** 부모 checkpoint에는 저장 상태 digest가 없어 복원이 정확했는지 사후 검증할 수 없습니다. step 0–100 구간은 iter_010 코드로 학습됐고, 로그에 batch ID·RNG 기록도 없습니다. 그래서 seed17 두 LR을 step 0부터 다시 학습했습니다(추가 비용 약 2시간). 점수를 보고 고른 결정이 아닙니다. iter_011 결과 파일은 그대로 보존했습니다.
2. **재개 관측과 수정** (`train.py`, `sft_data.py`)
   - step마다 실제 batch ID(DataLoader가 반환한 위치에서 역산), token/mask digest, step 전 RNG 4종 digest, optimizer step, train mode를 기록합니다. 계획된 batch와 다르면 즉시 중단합니다.
   - checkpoint에 adapter·optimizer·RNG digest를 저장하고, 복원 직후 live 상태와 정확히 같은지 대조합니다.
   - validation 전후로 학습 상태가 바뀌지 않았는지 검사합니다.
   - DataLoader에 epoch별 전용 generator를 줬습니다. 효과는 CPU 통제 검사로 먼저 확인했습니다: generator가 없으면 iterator 생성이 전역 CPU RNG를 소비하고, 있으면 소비하지 않습니다.
   - 기존 val_metrics는 존재만으로 믿지 않습니다. 점수를 원시 응답에서 다시 계산해 기록값과 비교합니다.
   - pilot 전용 옵션 `--deterministic`, `--stop-after-step`을 추가했습니다.
3. **선택·완료 gate** (`select.py`, `final_eval.py`, `run_shards.py`, `launch.py`, `pipeline.py`, `lock_protocol.py`)
   - 선택 파일에 다음 provenance를 기록합니다: protocol 내용 digest, 선택 규칙, 예정 epoch, 입력 digest, 근거 파일의 sha256. 파일을 쓸 때와 최종 평가할 때 모두 원시 근거에서 다시 계산해 파일과 완전히 같아야 통과합니다.
   - confirm 평가는 comparator, 연장 판정, 세 seed의 선택을 모두 다시 계산해 검증합니다.
   - run_shards는 시도(attempt)별 상태를 따로 기록합니다. 새 시도가 시작되면 이전 completion은 삭제하지 않고 `attempts/`로 옮겨, 현재 성공 근거로 쓰이지 않게 합니다. completion은 원자적으로 씁니다.
   - launch는 살아 있는 child를 returncode null이 아니라 `running` 상태로 명시합니다.
   - pipeline은 단일 소유 lock을 쓰고, 건너뛰기는 파일 존재가 아니라 근거 검증을 통과할 때만 합니다. pipeline.py도 protocol 잠금 목록에 넣었습니다.
4. **본실험**
   - seed17 두 LR 5 epochs → 연장 판정 → LR 선택 → seed29/43 → 생성 경로 점검 → base validation → comparator → confirm 생성 4,000요청 → 최종 평가까지 실행했습니다.
   - `generate.py` 부모 재사용 분기의 NameError(iter_010부터 있던 결함) 때문에 원래 pipeline이 6단계에서 멈췄습니다. 이후는 잠긴 pipeline 함수를 같은 순서로 호출하는 `run_iter012_rest.py`로 진행했고, base validation은 800요청 전부 새로 생성했습니다.

# Files Changed

- 수정한 코드: `rsna_diag/train.py`, `rsna_diag/sft_data.py`, `rsna_diag/select.py`, `rsna_diag/final_eval.py`, `rsna_diag/run_shards.py`, `rsna_diag/launch.py`, `rsna_diag/pipeline.py`(iter_012용으로 재작성), `rsna_diag/lock_protocol.py`(잠금 목록에 pipeline.py 추가)
- 새로 만든 파일: `test_rsna_iter012.py`, `test_rsna_iter012_gpu.py`, `run_iter012_rest.py`
- 건드리지 않음:
  - `generate.py`: 결함은 확인했지만 잠긴 protocol을 유지하려고 수정하지 않았습니다.
  - `test_rsna_iter010_gpu.py`: 미추적 파일입니다. iter_011 commit.json에서 "비밀정보 패턴 감지"로 자동 커밋에서 제외된 파일이라 원본 그대로 두었습니다.
- 결과: `results/iter_012/` 아래 새 파일만 만들었습니다. 부모 결과는 수정하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python test_rsna_iter012.py results/iter_012/tests`: **36/36 PASS**. 첫 실행에서는 launch 검사 1건이 실패했는데, json.tool의 종료 코드를 1로 잘못 가정한 테스트 쪽 오류였습니다(실제 코드는 2를 반환). 기대값을 고친 뒤 통과했습니다.
- `python test_rsna_iter009.py results/iter_012/tests`: 59/59 PASS
- `python test_rsna_iter010.py results/iter_012/tests`: 70/70 PASS
- `python test_rsna_iter011.py results/iter_012/tests`: **42개 PASS 후 중단(exit 1)**. iter_011의 select fixture에는 protocol digest와 재계산 가능한 점수 필드가 없어서, 강화된 gate가 의도대로 거부했습니다. 그 뒤의 migration 검사 등은 실행되지 않았습니다. 대신 연장 규칙과 epoch 선택 규칙의 수계산 검사는 iter_012 테스트에 옮겨 통과시켰습니다.
- `python test_rsna_iter012_gpu.py`: **59/59 PASS**. 실행 시간 약 1시간 10분, LR별로 GPU 한 장씩 사용했습니다.
- `python -m rsna_diag.lock_protocol ...`: pilot protocol과 main protocol의 digest가 같습니다(797ae707…). 모든 실행이 끝난 뒤 다시 검증해도 일치했습니다.
- `python -m rsna_diag.pipeline`: seed17과 seed29/43 학습, 선택, gen_check까지 성공했습니다. base_val 단계에서 worker NameError로 **실패**했습니다(`results/iter_012/base_val/`에 기록 0건).
- `python run_iter012_rest.py`: 성공했습니다. 선택 파일 5개를 다시 계산해 기존 파일과 같음을 확인한 뒤 나머지 단계를 끝까지 실행했습니다.

# Results (수치와 결과 파일 경로)

**재개 검사** (`results/iter_012/tests/fixtures_iter012_gpu.json`, 판정 기준은 실행 전에 `gpu_gate_config.json`에 고정)

| 모드 | 비교 | 결과 |
|---|---|---|
| D: 결정적 kernel, pilot | U1 vs U2, U1 vs R(5회 중단, 중간 step 2회 포함) | 12 step loss·adapter·validation 출력이 bitwise 일치 |
| M: 결정적 kernel, 본학습 설정(2400/eff16/mb2/workers3) | U1 vs U2 vs R(step 2에서 중단) | 4 step loss가 bitwise 일치, 최종 digest 일치 |
| N: 기본 kernel, pilot | U1 vs U2 / U1 vs R (lr1e-4) | loss 상대차 최대 0.80% / 1.01% |

- D·M 모두 batch ID, token, LR, RNG, optimizer 상태가 정확히 일치했고, 복원 직후 상태는 저장 상태와 같았습니다. validation은 학습 상태를 바꾸지 않았습니다.
- 중단된 epoch의 validation은 epoch 1·3에서 8건 전체, epoch 2에서 남은 5건만 복구됐습니다.
- N 모드에서는 부동소수 궤적만 다르고 batch·RNG 등 비부동소수 상태는 정확히 일치했습니다.
- **해석:** iter_011의 A·C 계열 FAIL 5건은 상태 복원 오류가 아니라 kernel 비결정성으로 설명됩니다. C 계열(부모 이관)은 부모 궤적을 쓰지 않는 것으로 해소했습니다.
- 결정적 모드는 step당 약 31초로 기본 kernel(약 11.4초)보다 약 2.7배 느립니다. 그래서 본학습은 원래 설정대로 기본 kernel을 유지했습니다.

**학습과 선택** (`results/iter_012/select/`)

- validation utility, epoch 1→5:
  - lr1e-4 s17: 0.597 → 0.700
  - lr2e-4 s17: 0.619 → 0.728
- 연장하지 않았습니다. lr2e-4는 utility가 +0.017 올랐지만 val loss가 0.6105에서 0.6289로 늘어 loss 조건을 충족하지 못했습니다.
- LR 2e-4를 선택했습니다. seed29와 seed43의 epoch 5 utility는 0.703, 0.717이며, 세 seed 모두 epoch 5가 선택됐습니다.

**생성 경로 점검** (`gen_check/decision.json`)

- 4 worker를 채택했습니다.
- iter_010 결과와 48/48 요청의 출력 token이 같았습니다.
- GPU별 전체 점유 최대는 17.9GB로, 기준 20,480MiB(worker당 2GiB 여유) 이내였습니다.

**Comparator** (`final/comparator.json`, validation 양성 F1@0.3 기준)

- `prior_set` 0.380으로 선택했습니다.
- 나머지: official_long 0.113, official_long 보정 0.288, concise 0.082, concise 보정 0.149, prior_single 0.276

**Confirm** (`final/confirm_result.json`, 양성 400명)

| 비교군 | F1@0.3 | F1@0.5 | 유효 출력률 | Normal 빈 응답률 | NoOpacity/NotNormal 빈 응답률 |
|---|---:|---:|---:|---:|---:|
| official_long | 0.165 | 0.021 | 100% | 0 | 0 |
| official_long 보정 | 0.268 | 0.090 | 100% | 0 | 0 |
| concise | 0.081 | 0.006 | 97.25% (잘림 22건) | 0.765 | 0.195 |
| prior_set (주 비교군) | 0.424 | 0.162 | 100% | 0 | 0 |
| SFT s17 / s29 / s43 | 0.631 / 0.636 / 0.653 | 0.349 / 0.313 / 0.364 | 100% | 0.975–0.98 | 0.665–0.72 |

- SFT 평균과 `prior_set`의 차이는 **+0.2156 (CI 0.1715–0.2591)**입니다. 이 CI는 환자 단위 bootstrap이라 학습 seed 불확실성을 충분히 반영하지 않습니다.
- 다른 비교군과의 차이: prior_single +0.316, official_long 보정 +0.372, concise +0.559
- **잔여 오류 (SFT):**
  - 양성인데 빈 응답: 15–18%
  - GT 개수별 F1@0.3: 단일 GT 약 0.57, 복수 GT 0.70–0.75
  - GT 면적별 F1@0.3: 작은 병변 0.42–0.44, 큰 병변 0.74–0.78
  - 예측 box 수 / GT box 수: 약 1.25 / 1.47로 과소 예측 경향

**자원과 처리량**

- 학습: seed17 5.39시간, seed29/43 5.26시간. GPU별 최대 점유는 약 12.2GB이고, GPU당 학습 프로세스는 하나였습니다.
- 생성 wall-clock: base validation 96분, confirm base 212분, SFT 각 15분

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **도달 단계:** 계획한 독립 확인 단계까지 완료했습니다. 실행 규모는 원래 계획 그대로이며, iter_010 계획의 연속이라 단계별 규모 정책은 소급 적용하지 않았습니다.
- **이번에 알게 된 것:**
  - validated된 `lesion-grounding-generalization` 한계에 대해, 언어층 rank16 LoRA 직접 SFT가 같은 RSNA 확인 집단에서 실제 생성 grounding을 크게 개선했습니다.
  - 그래도 F1@0.5 약 0.34, 양성 미검출 약 17%, 작은 병변의 낮은 성능이 남습니다.
- **아직 검증하지 못한 것:**
  - 다른 데이터셋에서의 재현. Kvasir-SEG는 iter_010의 준비 상태 그대로이며 이번에 사용하지 않았습니다.
  - 새 방법론의 기여. 이번 결과는 baseline입니다.
  - 8 epochs 이상 학습했을 때의 추세.
  - 세 seed를 넘는 재현성.
- **재사용한 자산:**
  - 승인된 모듈 geometry, parse, metrics, sft_eval, lora는 회귀 검사로 재확인했습니다.
  - iter_010의 manifest, split, baselines.json은 protocol에 잠그고 hash로 확인했습니다.
  - iter_011의 val8_ids는 GPU 검사 fixture에만 썼습니다.
  - iter_010의 thr_w4 출력은 출력 일치 대조에만 썼습니다.
  - iter_010의 base_val 부모 record는 사용하지 않았습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 무효로 만드는 문제:** 확인한 것은 없습니다.
- **재사용 전에 고쳐야 할 것:**
  - `generate.py`의 `run_worker`가 `lock_protocol`을 import하지 않아 `--parent-dir` 경로가 NameError로 실패합니다. 다음 protocol 버전에서 고쳐야 합니다.
  - 남은 단계는 `run_iter012_rest.py`가 실행했는데, 이 파일은 protocol 잠금 목록 밖입니다. 다만 잠긴 pipeline 함수와 잠긴 CLI gate만 호출합니다.
  - `test_rsna_iter011.py`의 select·migration fixture는 새 gate에 맞게 갱신해야 합니다.
- **추후 개선:**
  - 결정적 모드가 약 2.7배 느리다는 점은 기록만 해두었습니다.
  - 세 seed 모두 마지막 epoch가 최고였으므로 학습량을 다시 살펴볼 여지가 있습니다.
  - 음성 층 기준(빈 응답률이 5%p 넘게 악화되지 않을 것)은 정식 비열등성 검정이 아닙니다.
  - RSNA bbox 주석 경계의 모호성과 사전학습 노출 여부는 여전히 불확실합니다.

# Recommendation to GPT

- SFT를 "검증된 직접 적응 baseline"으로 등록하세요(단일 데이터셋, 5 epochs, 3 seeds).
- 다음 method 단계는 이 baseline의 잔여 오류에 직접 대응하는 방법이어야 합니다. 대상은 F1@0.5로 드러나는 위치 정밀도, 양성인데 빈 응답을 내는 문제, 작은 병변입니다. 같은 확인 규칙으로 SFT와 비교하되, 이번 confirm 집단은 이미 본 자료이므로 새 확인 집단이나 두 번째 데이터셋을 확보하세요.
- `generate.py` 결함 수정과 새 protocol 버전 작성을 다음 계획의 준비 작업에 넣으세요.

SELF_CHECK: FAIL
SUMMARY: 결정적 kernel에서 재개 상태가 bitwise로 정확함을 확인(GPU 59/59, CPU 36/36)한 뒤, 원래 규모의 LoRA SFT(두 LR, 3 seeds, confirm 800명)를 끝까지 실행했다. 사전 기준 5개를 모두 충족했다(prior_set 대비 F1@0.3 +0.216, CI 0.172–0.259). 다만 generate.py 부모 경로 결함 때문에 잠금 밖 실행기로 우회했고 test_rsna_iter011 fixture가 중단됐으며, 결과는 단일 데이터셋의 baseline 확립이라 FAIL로 표시해 검토를 요청한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: ps -eo pid,lstart,etime,user,args --sort=start_time
- Bash: timeout 590 bash -c 'until grep -qE "pass$|Traceback" results/iter_012/tests/gpu_test.log; do sleep 30; done'; ls results/iter_012/pilot | tr '\n' ' '
- Bash: timeout 590 bash -c 'until grep -qE "pass$|Traceback" results/iter_012/tests/gpu_test.log; do sleep 30; done'
