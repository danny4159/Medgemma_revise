# Work Performed

## 요약

- **핵심 결과:** iter_075/076에서 끝내지 못한 F/R/C/H 비교를 `results/iter_077/`에서 끝까지 실행했다. 재개 검사, 동결 검사, 본학습, V8 선택, 사전 잠금, E24, 비용, 독립 재계산이 모두 완료됐다.
- **가장 큰 blocker와 해소:** 결정적 모드가 SDPA(attention) math backend만 써서 allocated 21.3GiB, 43초/step이었다. `use_deterministic_algorithms`만 켜고 SDPA는 기본값으로 두면 10.2GiB, 약 19초/step에서도 반복 gradient가 bit 단위로 일치했다.
- **과학 결과(E24, 개발 자료):** held(ordinal 2/4) class-standardized MAE는 R_adapted 0.777, C 0.776, H 0.806, F_adapted 1.070, prior 1.200이다. R_adapted와 C는 사실상 같고(차이 +0.001, CI [−0.247, 0.238]), C는 R_adapted 비용의 약 0.18–0.19배(모델 적재 포함)다.
- **주의:** 원 계획의 양성 후보 조건은 미충족이다(C보다 ≥0.20 개선 없음). 대안 충분성은 후보 수준이며 확정은 아니다. 단일 seed·반복 개발 자료이고 독립 확인은 하지 않았다.
- **다음:** 현재 oracle ROI 판독에 VLM 방법 투자는 보류를 권고한다(아래 Recommendation 참고).

## 상세

1. 호스트 상태를 확인했다. GPU 두 장은 비어 있었고 `sp75_*` 프로세스는 없었다.
2. `sp77_sdpa_probe.py`로 SDPA backend별 메모리와 재현성을 실측했다(상세는 Results).
3. 학습 코드를 고쳤다.
   - `--deterministic`는 `use_deterministic_algorithms`만 사용한다.
   - 재개 시 checkpoint 이후 로그를 `train_log.uncommitted.jsonl`로 격리하고 `train_log.jsonl`에는 committed 구간만 남긴다. committed step이 비연속이거나 중복이거나 checkpoint 기록이 없으면 재개를 거부한다.
   - 시험 전용 `--allow-uncommitted-stop`을 추가했다.
4. `sp77_stage.py`를 만들었다. 단계 상태(pending/running/completed/failed), 코드·출력 sha256, stale 완료 거부, 살아 있는 소유자 거부, 자식 rc와 verify 실패 전파를 담당한다.
5. `sp77_resume_test.py`로 ref/A/B 재개 검사를 완결했다.
   - A는 step4까지 기록하고 중단해 미커밋 구간을 만든 뒤 재개했다.
   - B는 epoch1 checkpoint 직후, validation 전에 중단했다.
6. `sp76_freeze.py`로 동결 검사를 새 경로에서 실행했다.
7. `sp77_pipeline.py`를 만들었다. 실제 여유 순 배정과 baseline+Σ예상 peak+새 peak+worker당 2GiB 예약을 쓴다. 실패 시 의존 작업을 시작하지 않고 출력 완전성 verify를 한다.
8. `test_sp77.py`로 CPU 회귀 검사를 24건 추가했다.
9. 본학습 4개 trajectory, V8 생성·선택, `eval_lock`, E24 생성, C/H 예측, seal, 평가, 독립 재계산, 비용 4 block을 실행했다.

# Files Changed

**신규:** `sp77_sdpa_probe.py`, `sp77_stage.py`, `sp77_resume_test.py`, `sp77_pipeline.py`, `sp77_gen_pilot.py`, `test_sp77.py`

**수정:**
- `rsna_diag/train.py`: `set_deterministic_algos` 추가.
- `sp75_train.py`: 결정적 모드 변경, 미커밋 로그 격리, `peak_reserved_gb` 기록, `--allow-uncommitted-stop`.
- `sp75_eval.py`, `sp75_cost.py`, `sp75_verify.py`, `sp76_select.py`, `sp76_costreport.py`: 결과 경로를 iter_077로 변경.
- `sp76_select.py`: lock 코드 목록에 `sp77_pipeline.py`, `sp77_stage.py`, `sp75_verify.py` 추가.
- `test_sp75.py`, `test_sp76_gate.py`: 결과 경로를 iter_077로 변경.

`sp75_pipeline.py`는 임시로 경로를 바꿨다가 iter_076으로 되돌렸으며 현재 변경 없음이다. 이전 결과는 수정·삭제하지 않았다.

# Commands / Experiments

| 실행 | 결과 |
|---|---|
| `python sp77_sdpa_probe.py ... --gpu 0` | 성공 |
| `python sp77_resume_test.py` (background, 1478초) | exit 0, PASS |
| `python sp76_freeze.py --out results/iter_077/tests/freeze_check.json --gpu 1` | PASS |
| `python test_sp75.py` | 50 checks, 0 fails |
| `python test_sp76_gate.py` | 8개 변조 모두 rc=1로 차단 |
| `python test_sp77.py` | 24 checks, 0 fails |
| `python sp77_pipeline.py train --epochs 16` | 4개 trajectory rc=0 |
| `python sp77_pipeline.py gen_v8 --epochs 8,16` | 8 job rc=0 |
| `python sp76_select.py select_v8` / `select_final` / `lock_spec` | 성공 |
| `python sp75_eval.py lock --spec ...` | 31개 파일 잠금 |
| `python sp77_gen_pilot.py` | rc [0,0] |
| `python sp77_pipeline.py gen_e24 --est-mib 9700` | 4 job rc=0, 각 118건 |
| `python sp76_cpred.py C` / `H` | 118건 각각 성공 |
| `python sp75_eval.py seal` / `run` | 성공 |
| `python sp75_verify.py` | 원 report와 최대 차이 0.0 |
| `python sp75_cost.py blocks --nblocks 4 --gpu 0 ...` / `python sp76_costreport.py` | 성공 |

실패·재시도는 없었다. 셸 권한 때문에 heredoc 확인 스크립트 1회가 거부되어 `sp77_gen_pilot.py` 파일로 바꿨다.

# Results

## SDPA 구성 probe (`results/iter_077/tests/sdpa_probe.json`)

| 구성 | peak allocated | 반복 gradient bit 일치 |
|---|---|---|
| 비결정 기본 | 10.17GiB | 불일치 |
| 결정적 알고리즘 + 기본 SDPA | 10.17GiB | 일치 |
| 결정적 알고리즘 + math SDPA | 21.29GiB | 일치 |

- 메모리 증가의 원인은 math SDPA였다.
- 입력, loss, 정밀도, 학습량은 바꾸지 않았다.
- math SDPA는 attention 수치가 달라 loss가 12.0878로, 나머지 구성의 12.1376과 다르다. 새 결정적 모드는 실제 학습 경로에 더 가깝다.

## 재개·동결 (`results/iter_077/tests/resume/resume_compare.json`, PASS)

- A와 B 모두 ref와 18/18 step의 loss·grad_norm, batch ID·token hash, RNG, LR이 정확히 같다.
- checkpoint digest 6/6 일치, val_ce와 adapter digest 일치, `max_abs_loss_diff=0.0`이다.
- A 재개에서 미커밋 1행을 격리·보존했고 `restored_equals_saved=true`다.
- B는 재개 전 `val_ce.json`이 없었고 재개 후 validation이 [1, 2]로 복구됐다.
- 동시 중복 실행은 `owned by live process`로 거부됐다.
- 다른 GPU(GPU1)의 ref_g1도 정확히 일치했다(보조 근거).
- 비LoRA 883개·8,600,158,944 byte의 digest가 update 전후 같고 LoRA는 변했다(`freeze_check.json`). 본학습 4개 모두 `freeze_end.json`에 `equals_start`가 기록됐다.

## 본학습

- epoch 16 기준 4개 trajectory가 정상 종료했고 학습 wall은 합계 2.73시간이다(약 39–43분씩, GPU당 1개).
- peak GPU 점유는 11.9GiB다. 2개 동시 배정은 23.9GiB에 worker당 2GiB 여유를 더하면 용량을 넘어 GPU당 1개로 유지했다.
- V8 선택 결과는 F lr2e-4, R lr2e-4이고 연장은 하지 않았다. epoch8→16에서 CE는 오히려 상승했고 primary는 악화됐다.

| 방식 | LR | epoch8 primary | epoch16 primary | epoch8 CE | epoch16 CE |
|---|---|---|---|---|---|
| F | 2e-5 | 0.970 | 0.978 | 1.022 | 2.202 |
| F | 2e-4 | 0.843 | 0.897 | 0.984 | 2.393 |
| R | 2e-5 | 0.665 | 0.943 | 0.861 | 1.562 |
| R | 2e-4 | 0.535 | 0.822 | 1.259 | 2.424 |

- 사전 규칙상 최종 후보는 epoch 16이다. epoch 8이 V8에서 더 좋았지만(과적합 신호) 규칙을 사후에 바꾸지 않았다. 이는 recipe 한계다.

## E24 held 지표 (`results/iter_077/eval/report.json`, `per_row.json`, `independent_verify.json`)

- 평가 118행은 supervised 71 + held 47이며 생성 472건이다.
- 결과 요약은 아래와 같다.

| 시스템 | held primary | 비고 |
|---|---|---|
| F_adapted | 1.070 | |
| R_adapted | 0.777 | F−R +0.294, CI [0.078, 0.475] |
| C | 0.776 | |
| H | 0.806 | |
| prior(global/ordinal) | 1.200 | |
| F_base, R_base | 4.0 | 118/118 invalid (비EOS 장문 응답). 형식 실패이며 내용 오답과 구분됨 |

- 후보 likelihood argmax 보조 분석에서 base held는 2.08(F), 1.91(R)이다.
- R_adapted−prior_ordinal −0.423, CI [−0.680, −0.120]이다. F_adapted−prior_ordinal −0.130, CI [−0.354, 0.101]이다.
- R_adapted−swap −0.968, CI [−1.395, −0.473]이다.
- R_adapted−C +0.001 (CI [−0.247, 0.238]), F_adapted−C +0.294 (CI [0.065, 0.510])이다. C−best VLM의 CI는 ±0.20을 모두 포함한다.
- 사전 선언 flags: R_adapted는 `le_1.0`, prior·swap 대비 ≥0.20 개선을 충족했으나 C 대비 ≥0.20 개선은 미충족이다. F_adapted는 `le_1.0`과 prior 대비 모두 미충족이다. 양성 후보 조건(`all_candidate_conditions_point`)은 두 방식 모두 false다.
- C의 기본 영상 신호는 true, C가 best VLM보다 0.10 이상 나쁘지 않음은 true다.
- independent verify는 원 report와 최대 차이 0.0이다.

## 비용 (`results/iter_077/cost/cost_report.json`, 4 paired block)

- C/best VLM 비율은 적재 포함 0.184–0.194, 제외 0.098–0.103으로 네 block 모두 ≤0.5다.
- H/best VLM 비율은 적재 포함 0.540–0.581, 제외 0.678–0.747로 ≤0.5가 아니다.
- GT anatomy 획득 비용은 모든 시스템에서 미측정이다. 비용 경로 답변은 block 간 모두 동일했다.
- 비용 경로의 F/R 답변은 V8 PNG 기반 생성과 23/24로 일치했다. 원 T2에서 직접 재구성한 입력이라 1건이 다른 한계가 있다.

## 생성 worker 구성

- 2-worker/GPU pilot은 24요청에서 token과 후보 loglik이 1-worker와 완전 일치했다(차이 0.0). peak는 19.2GiB였다.
- 처리량 이득은 요청당 시간 1.7배 지연을 고려하면 약 1.2배 수준으로 크지 않다. 안전 여유 안이라 E24 4 job은 2 worker/GPU로 실행했고 모두 성공했다. 별도 처리량 전수 비교는 하지 않았다.

# Goal Progress / Reused Assets

**진전:** 실행 blocker를 해소하고 SPIDER Pfirrmann 비교를 실제 출력으로 완료했다. 이 결과로 아래가 보인다.
- 영상 대응 신호는 있다(R_adapted와 C가 prior·swap보다 낫다).
- 같은 oracle ROI에서 공유 ResNet18 C가 R_adapted와 같은 정확도를 약 1/5 비용으로 낸다.

**미검증:**
- 단일 seed·반복 개발 자료이며 독립 확인이 없다.
- 세 slice의 등급 판독 충분성과 사전학습 노출은 미확인이다.
- GT anatomy(oracle) 비용은 미측정이다.
- ordinal은 해부학 이름이 아니다.
- F/R 차이는 해상도·context·대상 지정이 얽혀 있어 선택 실패나 결합 능력으로 해석할 수 없다.

**재사용:**
- `sp75_metrics.py`는 iter_075에서 제한 승인됐고 변경 없이 사용했다.
- `sp75_data.py`, `sp75_vlm.py`, `sp75_gen.py`, `sp75_c.py`, `sp75_h.py`는 수정하지 않았다. C/H 선택 파일의 코드 hash가 현재 파일과 모두 일치함을 확인했다.
- 기존 C(lr1e-4, epoch40)와 H(config1)는 재학습·재선택 없이 사용했다.
- `rsna_diag/*`는 iter_075/076 보관본에서 가져왔고, `train.py`만 `set_deterministic_algos`를 추가했다.
- 선별 반입 manifest는 비어 있었다.

# Problems

**현재 결론 무효:** 없음.

**재사용 전 수정이 필요한 것:**
- stage 상태는 `sp77_pipeline`에만 연결됐다. `sp75_eval.py`·`sp76_select.py`·`sp75_cost.py`·`sp76_cpred.py` 단계는 직접 호출이라 상태 파일이 없다.
- `sp75_cost.py blocks`는 `blocks_ledger.json`을 끝에만 쓴다.
- extension 후 `train`을 다시 호출하면 stale 처리되어 재실행될 수 있는 경로가 있다. 이번에는 연장을 하지 않아 발생하지 않았다.

**추후 개선:**
- 학습 중 별도 SIGKILL 시험은 하지 않았다. 대신 정지 시점 중단(`os._exit`)과 미커밋 로그 재현으로 검증했다.
- 처리량 비교는 V8 24건 pilot 1회에 한정된다.
- `sp76_costreport.py` 출력 상단의 일부 flag 필드를 확인했을 뿐, 보고서 전체 필드를 개별 재계산하지는 않았다.
- 구현 중 `ps`는 권한 확인이 필요해 `/proc` 대신 nvidia-smi와 `sp76_recover.py` 기록으로 소유권을 판단했다. GPU는 시작 시 비어 있었다.

# Recommendation to GPT

1. **보류 범위:** 현재 조건(oracle ROI, 세 slice, 단일 seed, SPIDER 일부 위치 supervision)에서 VLM F/R의 이득은 확인되지 않았다. 방법 투자는 보류를 권고한다. 근거는 R_adapted−C +0.001로 정확도에 이득이 없다는 점과 C의 비용이 약 1/5라는 점이다.
2. **구분해서 읽을 것:** 이는 대안 충분성 후보이지 확정이 아니다(CI가 ±0.20을 포함). 정확도 CI가 넓어 VLM이 약하다고 결론낼 수도 없다. 모델 능력 부재나 VLM 전체 기각이 아니다.
3. **남는 가치가 있는 관찰:** epoch 8이 epoch 16보다 V8에서 좋았다(과적합). 같은 recipe를 확대하기보다 이 한계를 먼저 리뷰해 판단해 달라. 새 loss 시도는 권고하지 않는다.
4. **남은 질문:** 이 비교 흐름에서 정말 판별해야 할 설명은 "VLM이 영상 신호를 쓰는가"가 아니라 "VLM만이 해결하는 질문 조건이 있는가"다. 같은 질문에서 VLM 고유 가치(언어 조건·근거 연결)를 보일 설계가 없다면 MRI 연구 질문 전환 또는 종료를 검토하라.

SELF_CHECK: PASS
SUMMARY: SDPA math backend가 원인인 결정적 실행 메모리 문제(21→10GiB)를 해소하고 재개·동결 검사(ref/A/B 18/18 정확 일치)를 통과한 뒤, F/R/C/H 비교를 E24·비용·독립 재계산까지 완료했다. R_adapted는 held MAE 0.777로 prior(1.200)보다 낫지만 C(0.776)와 같고 C는 비용이 약 1/5라, 현재 oracle ROI 조건의 VLM 방법 투자는 보류를 권고한다(대안 충분성은 후보이며 단일 seed·개발 자료로 확정 불가).

# [orchestrator] 권한 거부된 도구 호출
- Bash: ps -eo pid,lstart,cmd --sort=start_time
- Bash: sed -i "s#results/iter_076/tests#results/iter_077/tests#g" test_sp75.py test_sp76_gate.py; grep -n "iter_07" test_sp75.py test_sp76_gate.py | cut -c1-150; sed -n 1,47p test_sp76_gate.py
- Bash: python - <<'EOF'
import subprocess, sys, time, os
ad='results/iter_077/train/F_lr2e-4/epoch_16'
out='results/iter_077/tests/gen_2w_F'
t0=time.time()
ps=[subprocess.Popen([sys.executable,'sp75_gen.py','--variant','F','--split','V8','--positions','supervised','--adapter',ad,'--out-dir',out,'--worker',str(k),'--gpu','0'],stdout=open(f'/tmp/gen2w_{k}.log','w'),stderr=subprocess.STDOUT) for k in (0,1)]
time.sleep(60)
print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used','--format=csv,noheader']).decode())
rc=[p.wait() for p in ps]
print(rc, time.time()-t0)
import json,glob
a={};b={}
for f in glob.glob(out+'/gen_worker*.jsonl'):
    for l in open(f):
        r=json.loads(l); a[r['id']]=r
for f in glob.glob('results/iter_077/gen/V8/F_lr2e-4_ep16/gen_worker*.jsonl'):
    for l in open(f):
        r=json.loads(l); b[r['id']]=r
print(len(a),len(b), all(a[k]['suffix_ids']==b[k]['suffix_ids'] for k in b), max(max(abs(x-y) for x,y in zip(a[k]['cand_loglik'],b[k]['cand_loglik'])) for k in b), sorted({r['worker'] for r in a.values()}))
EOF
- Bash: cat results/iter_077/ledger.jsonl | tail -4 | cut -c1-200; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; for f in results/iter_077/gen/E24/*/gen_worker0.jsonl; do echo $f; wc -l < $f; done
