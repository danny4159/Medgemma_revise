# 요약

- **핵심 결과:** 재개 결함(재개 첫 update가 warmup 첫 LR로 적용되던 문제 등)을 고치고 모든 gate를 통과한 뒤 비교를 완료했습니다. detector seed17(26 epoch)과 조건부 seed29(38 epoch)를 학습했고, 잠긴 validation 선택으로 개발800에서 저장된 LoRA SFT와 비교했습니다. 결과는 한쪽의 우위가 아니라 **trade-off와 상보성**입니다.
  - IoU0.3 기준 F1은 SFT 쪽이 점추정상 높습니다. detector17−B0 = −0.049, 97.5% CI [−0.100, +0.002]로 0을 포함합니다.
  - IoU0.5 기준 F1은 detector가 유리합니다. +0.067, 97.5% CI [+0.012, +0.122]입니다.
  - 한쪽만 검출한 GT가 양방향 모두 12~13%이고, 63명·70명에 분포합니다.
- **근거:** 주수치와 CI는 독립 구현으로 재계산해 일치했습니다. 기존 SFT seed별 F1@0.3(0.6308/0.6359/0.6528)도 그대로 재현됐습니다. detector seed29와 SFT seed29/43에서도 같은 방향이 나왔습니다. 단독 latency는 detector 0.062s, B0 4.30s(약 70배)입니다.
- **미검증·주의:** 개발800은 이미 사용된 개발 집단이므로 독립 확인이 아닙니다. 사전 기준상 "detector 우위"는 성립하지 않았습니다(F1@0.3 CI가 0 포함, FP 증가 95% CI 상한 0.069 > 0.05). 세션이 한 번 끊겼고, 제 명령 실수로 spec 한 개가 재실행됐습니다. 상태 변화는 없었으며 상세 내용은 Problems에 적었습니다.
- **다음:** 단순 bbox 개선의 우선순위를 판단하려면 "SFT가 느슨한 IoU에서 더 찾는 병변(단일·작은/중간 병변)"과 "detector의 위치 정밀도"를 가르는 조건이 핵심입니다. VinDr 승인 후에는 이 두 경향을 외부 확인 후보로 삼는 것을 권합니다.

# Work Performed

1. **호스트·원본 확인:** GPU 두 장은 idle이었고 detector 프로세스는 없었습니다. 기준 계획 hash(iter_034 `255b526c…`, iter_033 `9476060…`)가 일치했습니다. iter_034 checkpoint(update 706, SIGTERM 경계 저장)와 로그 706행은 원본을 보존했습니다.
2. **소스 편입·수정:** results/의 원본 소스를 `rsna_diag/`·`tests_det/`로 편입했습니다. 원본 경로와 SHA256은 `results/iter_035/amendment.md`에 기록했습니다.
3. **학습기 수정(`det_train.py`):**
   - scheduler를 먼저 만든 뒤 optimizer→scheduler 순으로 state를 복원하고, 실제 group lr을 검사합니다.
   - `lr_applied`는 `opt.step()` 직전의 실제 값으로 기록합니다.
   - format2 checkpoint에 permutation·cursor·dataset RNG·config/input/source digest·학습 장치 index를 저장합니다.
   - 비유한 loss/gradient는 step 전에 중단합니다.
   - 로그를 segment로 나누고 canonical log·orphan을 분리하며, `complete.json`과 `verify`를 추가했습니다.
   - 기존 경로의 fresh 실행을 거부하고, lock에 소유 metadata를 남기며, `--init_from`/`--migration`을 지원합니다.
4. **이관:** 구 checkpoint를 15개 검사로 감사했고 모두 통과했습니다. 기록 전체에 대해 sample·flip·dataset RNG를 결정적 함수로 재생해 일치를 확인했습니다. 이어서 두 독립 process로 update 706을 검증했고, update 706부터 이어서 학습했습니다.
5. **Gate 검사:**
   - 결정적 모드: 동일 checkpoint의 연속 실행 대 새 process 재개가 bit 단위로 일치했습니다(경계 2/6/15, 실제 SIGTERM, SIGKILL과 orphan 분리).
   - production 모드: 반복 변동을 먼저 기록해 허용오차를 고정한 뒤 비교했습니다.
   - CLI 거부 20건, 추론 D24 재개·변조 13건을 검사했습니다.
6. **데이터 감사:** 3,600명 전체를 재감사했습니다.
7. **추론 구성 pilot:** batch1/4와 worker 1/2를 비교했습니다.
8. **학습·선택:**
   - seed17: 26 epoch, 연장 조건 불충족. V400 선택 결과 epoch18·threshold 0.70.
   - seed29: 규칙 충족으로 실행(판정 전 선행 시작). 연장 규칙 충족으로 38 epoch까지 학습. 선택 결과 epoch26·threshold 0.60.
   - seed43: 조건 불충족.
   - 선택을 잠근 뒤(`select/LOCK.json`) 개발800 추론을 실행했습니다.
9. **비교 분석:** 개발800 비교와 독립 재계산, 동일 GPU 교차 latency와 공식 tensor 대조, iter_031 잔여 분석을 수행했습니다.

# Files Changed

- **수정:** `rsna_diag/det_train.py`, `rsna_diag/det_lib.py`
- **신규(추적 경로):** `det_jobs.py`, `rsna_diag/det_eval.py`, `det_select.py`, `det_compare.py`, `det_audit.py`, `det_latency.py`, `det_migrate.py`, `det_evalwatch.py`, `iter031_supp.py`
- **신규 검사:** `tests_det/test_det_resume.py`, `test_det_cli.py`, `test_det_migration_next.py`, `test_det_infer.py`, `test_match_identity.py`, `verify_compare_independent.py`
- **결과:** `results/iter_035/` 전체(아래 경로 참조). 원본 results/iter_033·034는 수정하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

detector 전용 환경은 모두 `python det_jobs.py results/iter_035/jobs/<spec>.json`으로 실행했습니다(고정 스크립트, 상속 GPU 집합 안에서만 배정).

- **migrate_audit:** 1차 실패(구 checkpoint pickle의 `cmd_train` 참조) → 수정 후 성공.
- **gates:** 세션 종료로 중단. 결정적 검사는 A2 단계에서 rc −15, production 검사는 통과.
- **gates2:** 결정적 검사와 CLI 20/20은 통과. migration은 실패했습니다(CUDA RNG가 GPU 2장 분으로 저장된 상태에서 1장만 보는 process에 복원하려다 IndexError).
- **infer_gate:** 12/13 통과. 부모가 SIGTERM을 반복 전달한 결함 때문이었고, 수정 후 **infer_gate2 13/13**.
- **gates3(최종 소스):** 결정적 재개, production 재개, CLI 20/20, migration 모두 성공.
- **infer_pilot:** 성공. 학습 spec(train17, train29, train29_ext): 학습은 모두 rc 0.
  - 감시기 결함: 연장 시작 시 이전 완료 marker를 보고 즉시 오류 종료(rc 1) → 수정.
  - 제 명령 실수: `det_jobs.py … --help`로 spec이 한 번 더 실행됐습니다. 학습은 "already complete"로 거부됐고(상태 변화 없음), 감시기가 epoch 32/38 평가를 수행했습니다.
- **추가 평가·선택:** `v400_e18_s17`, `confirm800` 성공. `det_select` v100/extend/v400/seed 성공. `det_train verify` seed17·seed29 성공.
- **기본 env에서 직접 실행:**
  - `python rsna_diag/iter031_supp.py`: 1차 실패(offline 설정 누락으로 gated repo 접근 시도) → 수정 후 성공.
  - `det_audit.py`, `det_compare.py`, `tests_det/test_match_identity.py`(2회), `verify_compare_independent.py`, `det_latency.py run`, `det_latency.py tensorcheck`: 모두 성공.
- **권한 거부:** `sed -i`, `ps`, detector 전용 Python 직접 실행. 우회하지 않고 다른 허용 경로를 사용했습니다.

# Results (수치와 결과 파일 경로)

## Gate

| 검사 | 결과 | 파일 |
|---|---|---|
| 결정적 재개 | 모두 bit 단위 일치(k=2/6/15, SIGTERM·SIGKILL, orphan 2건 분리) | `sanity/resume_det_v3/resume_result.json` |
| production 재개 | 첫 재개 update loss 차이 0, 이후 차이는 반복 변동 범위(k15: 0.0039 대 0.00395) | `sanity/resume_prod_v2/` |
| CLI 거부 | 20/20 | `sanity/cli_v2/` |
| 추론 재개·변조 | 13/13 | `sanity/infer_d24_v2/` |
| migration | 통과 | `migration/migration_seed17.json`, `migration/next_v2/` |
| matching identity | 6,812건 `metrics.match`가 독립 exhaustive와 identity까지 일치. DP는 69건에서 identity만 달라 분석에 쓰지 않음 | `sanity/match_identity_with_det.json` |
| 데이터 감사 | 3,600명 hash 불일치 0, 분할 중복 0, manifest 6종 모두 단일 분할의 부분집합 | `data/data_audit_full_3600.json` |

## 추론 구성

batch1·worker 2를 채택했습니다(`pilot/infer_config_decision.json`).

- batch4는 출력이 달라졌습니다(최대 score 차이 0.099, 5/100 영상의 후보 수 차이).
- 처리량(V100): b1w1 7.4, b1w2 8.0, b4w2 9.1 img/s. b1w2는 b1w1과 bit 단위로 같았습니다.

## 학습

- **seed17:** update 706부터 7,800까지, 5,979초, 9.49 img/s, peak reserved 7,952MiB, orphan 0.
  - V100 utility: e6 0.723, e12 0.681, e18 0.745, e22 0.718, e26 0.700 → 연장하지 않음.
  - V400 선택: epoch18·threshold 0.70. utility 0.711, F1@0.3 0.603, F1@0.5 0.407, FP/환자 0.278.
- **seed29:**
  - 기본 26 epoch: 6,928초. 연장 12 epoch: 3,080초.
  - V100 utility: e26 0.747, e32 0.739, e38 0.748(32→38 변화 < 0.01, 정체로 판단).
  - V400 선택: epoch26·threshold 0.60.
- 결과: `train/seed{17,29}`, `select/`
- 참고로 기존 SFT seed17 학습 로그의 `elapsed_s` 최댓값은 17,237초입니다(validation 포함 여부 미확인). 750 step, eff batch 16, peak 9.8GB였습니다.

## 개발800 비교

파일: `confirm800/analysis.json`, 독립 검증 `confirm800/independent_verify.json`(모두 일치).

| 모델 | F1@0.3 | F1@0.5 | FP/환자(800) | lesion recall@0.3 / @0.5 |
|---|---|---|---|---|
| detector17 | 0.582 | 0.416 | 0.295 | 0.637 / 0.455 |
| detector29 | 0.574 | 0.406 | 0.274 | — |
| B0 (SFT17) | 0.631 | 0.349 | 0.269 | 0.647 / 0.367 |
| SFT29 | 0.636 | 0.313 | — | — |
| SFT43 | 0.653 | 0.364 | — | — |
| base official_long | 0.165 | 0.021 | — | — |
| base concise | 0.081 | 0.006 | — | — |

- **다른 seed 쌍:** detector29−B0는 F1@0.3 −0.057, F1@0.5 +0.058(두 CI 모두 0 제외)로 detector17과 같은 방향입니다.
- **층별 차이(detector−B0):**
  - GT 1개(223명): F1@0.3 −0.086, 95% CI [−0.149, −0.023]
  - GT 2개(166명): F1@0.5 +0.085, CI [0.020, 0.153]
  - union 면적 중간(133명): F1@0.3 −0.106
  - union 면적 큰 층(151명): F1@0.5 +0.127, CI [0.058, 0.200]
  - 개별 GT 면적 소형: lesion recall@0.3이 detector 0.347, B0 0.420
- **상보성(IoU0.3):** detector-only 12.1% [9.3, 14.9], SFT-only 13.1% [10.2, 16.0], 둘 다 미검출 23.3%, 두 방식의 GT 합집합 recall 0.767(진단용 상한). 동점 규칙 반대·best-IoU cover·다른 seed에서도 유지됐습니다.
- **상보성(IoU0.5):** detector-only 20.2%, SFT-only 11.4%.
- **FP budget(threshold는 validation에서 고정):** 0.5 budget에서 detector F1@0.3 0.622, lesion recall 0.725, FP 0.451입니다. 1.0 budget에서는 SFT-only가 3.9%로 줄었습니다.

## Latency

파일: `latency/latency_summary.json`. 같은 GPU0, 모델별 단독 resident 3회×64건, 순서 교차.

- detector: end-to-end 0.062s(p95 0.065), 모델 구간 0.035s, peak reserved 766MiB, 로드 약 2.3s.
- B0: end-to-end 4.30s(p95 11.9), 모델 구간 4.22s, peak reserved 8,550MiB, 로드 9–12s.
- 속도비는 end-to-end 70배, 모델 구간 122배입니다.
- B0 저장 suffix는 3회 모두 64/64 재현됐습니다. 긴 출력 stress 4건도 token이 일치했습니다.
- 공식 tensor 대조는 수정한 검사기로 64/64 일치했습니다(`latency_tensorcheck_L64.json`).

## iter_031 보완

파일: `analysis_iter031/supplement.json`. 저장 보고서의 수치가 먼저 그대로 재현됐습니다.

- IoU0.3 회복은 기존과 같이 8/20·11/27입니다.
- IoU0.5 회복은 4/20·7/27, 중심 포함 기준 회복은 9/20·11/27입니다.
- 중복 box를 실제로 제거하고 재매칭해도 E402의 F1@0.3은 0.474→0.485, FP/환자는 1.572→1.507로 조금만 바뀝니다.
- F 호출의 O 대비 추가 비용은 약 +4.8s, +36 token입니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **진전:** 빠진 강한 비교군(실제 전용 detector)을 충분히 학습된 상태로 확보했습니다. 수렴 규칙과 2개 seed를 적용했습니다. 그 결과 기존 LoRA SFT의 위치 개선이 전용 detector 대비 "느슨한 IoU에서의 검출률"은 비슷하거나 약간 높지만, "위치 정밀도(IoU0.5)"는 낮다는 것을 확인했습니다. 오류는 상당 부분 상보적입니다. 이는 성공적인 진단 결과이지 새 방법의 기여가 아닙니다.
- **미검증:**
  - 독립 환자(개발800은 이미 사용된 집단)와 외부 데이터(VinDr 승인 대기) 확인.
  - detector 쪽 다른 architecture와 해상도 조건.
  - 결합(ensemble) 방법의 실제 성능. GT 합집합은 상한일 뿐입니다.
  - 언어·근거 과제에 미치는 영향.
- **재사용 검증:**
  - geometry·parse·metrics·sft_eval: 기존 SFT 주수치를 정확히 재현했고, matching identity를 exhaustive로 검증했습니다.
  - generate·lora: 저장 input_ids·suffix를 64/64 재현했고, 공식 tensor 대조에서 64/64 일치했습니다.
  - risk30_eval의 H2 정의: iter_031 재현에 사용했습니다.
- **반입 manifest:** 비어 있었습니다(요청 없음).

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 무효화하는 결함:** 발견하지 못했습니다.
- **실행 중 수정한 결함(재사용 전 필수 수정에 해당, 이미 반영):**
  - CUDA RNG 장치 매핑.
  - SIGTERM 반복 전달.
  - 공식 tensor 검사기의 BOS 중복. 첫 latency JSON 3개의 `official_tensor_all_equal=false`는 이 검사기 결함의 기록입니다.
  - 감시기의 연장 조건.
- **사고:**
  - 세션이 1회 끊겨 gate를 재실행했습니다.
  - `det_jobs.py … --help` 오사용으로 연장 spec이 재실행됐습니다. 이 때문에 `train/launch29_ext/result.json`이 두 번째 실행 결과로 덮어써졌습니다. 첫 실행 기록은 같은 디렉터리의 append 로그에 있습니다.
- **판정상 주의:**
  - seed29는 규칙 판정 전에 미리 시작했습니다. 사용 여부는 사전 규칙으로만 결정했습니다.
  - seed29의 38 epoch "상승 중" 판단에는 연장 규칙과 같은 0.01 기준을 적용했습니다. 계획에는 명시돼 있지 않았습니다.
- **추후 개선:**
  - `det_jobs.py`에 인자 검증(알 수 없는 인자 거부)을 추가해야 합니다.
  - batch4 추론의 padding 효과는 문서화만 했습니다.
  - SFT 학습 시간의 정확한 wall 구성은 미확인입니다.

# Recommendation to GPT

- 사전 기준으로는 "detector 우위"가 아니라 "조건부 trade-off와 상보성"입니다. 단순 bbox 개선을 전면 중단할 근거도, 계속할 근거도 이 결과만으로는 부족합니다.
- 다음 판단의 핵심은 두 가지입니다.
  - SFT가 IoU0.3에서 더 찾는 병변(단일 GT, 작은·중간 면적)이 실제 병변 발견인지, 느슨한 위치 매칭 효과인지.
  - detector의 위치 정밀도 이점이 외부에서 유지되는지.
- VinDr 승인 후 같은 층별 비교를 외부 확인 후보로 두기를 권합니다. 그 전에는 새 loss나 결합 방법을 자동으로 시작하지 않는 것이 맞다고 봅니다.

SELF_CHECK: PASS
SUMMARY: 재개 결함을 고쳐 모든 gate를 통과한 뒤 detector(seed17/29)를 학습하고 잠긴 validation 선택으로 개발800에서 LoRA SFT와 비교했습니다. detector는 F1@0.5에서 유리하고(+0.067, 97.5% CI>0), F1@0.3에서는 SFT가 점추정상 높으며(−0.049, CI가 0 포함), 오류는 양방향 12~13%로 상보적이고 단독 latency는 약 70배 빠릅니다. 개발 집단이므로 독립 확인은 아닙니다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: sed -i 's#sanity/infer_d24"#sanity/infer_d24_v2"#' results/iter_035/jobs/infer_gate.json
