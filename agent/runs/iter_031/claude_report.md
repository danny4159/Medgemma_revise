# 요약

- **핵심 결과:** iter_030에서 미완료였던 RSNA 부분 누락 위험 진단(C201/E402)을 실행 결함·평가 결함을 수정한 뒤 처음부터 끝까지 완료했다. H2(닫기 선택을 한 번 continue로 바꾸면 완전히 놓친 병변의 후보를 회복하는가)는 **positive**(C201 8/20=40.0%, E402 11/27=40.7%, 두 표본 모두 사전 기준 충족), H1(그 분기의 margin Q가 단순 baseline보다 위험을 더 잘 구분하는가)은 **inconclusive**(Q와 최고 baseline의 AUROC가 사실상 동률).
- **근거:** C201(201명, 402요청)·E402(402명, 804요청) = 합계 1,206요청, 계획서 상한과 정확히 일치. 모두 완료·중복 0·O suffix 재현 100%·F prefix 보존 100%. GPU당 2 worker(총 4)로 peak 8.3~8.4GiB/process, GPU당 약 16.8GiB 사용(6.8~7.2GiB 여유), OOM 없음. 공식 chat_template 구성과 실행 wrapper의 전체 tensor가 완전히 일치함을 확인했고, 실제 SIGKILL 후 재개도 중복·손실 없이 완료됨을 실측했다.
- **미검증·주의:** 이 개입은 전체 모집단 F1을 크게 악화시킨다(E402 F1@0.3 0.628→0.474, 평균 extra FP/환자 ≈1.04). "무조건 이어쓰기"는 실용적 개선이 아니다. C/E는 여전히 개발 자료이며 독립 확인·다른 데이터셋 재현은 이번 범위에 없다. 사건 수(C 20, E 27)는 작다.
- **다음:** 사용자 보완 지시(능력 전이 진단)는 다음 재계획에서 다룬다. 이번 결과는 "예측 박스 개수/모델 자신의 분기 확신도가 이미 강한 신호(AUROC~0.78-0.81)이며, 추가로 설계한 margin Q는 그 이상의 이득이 없다"는 것과 "무조건적 재생성 완화는 recall을 살짝 올리지만 precision을 크게 해친다"는 것을 확정 진단으로 제공한다.

# Work Performed

iter_030 리뷰의 blocking/needs_fix 항목(실행 lock·protocol 강제 누락, 평가 CI 수준·Capture 반올림·퇴화 bootstrap·한 박스 층 diff 누락·전체 비용 집계 누락)을 수정하고, D24 재개 검사를 실제로 완료한 뒤 원래 계획대로 C201 본진단과 조건부 E402를 실행·평가·판정까지 마쳤다.

# Files Changed

- `rsna_diag/risk30.py`: `validate_existing`에 protocol_digest/request_id 검증 추가, `require_full_protocol`/`verify_c_gate` 신설, `read_records`의 마지막 줄 손상 허용(재개 복구), `load_all` 중복 거부, `main()`의 `--protocol` 필수화·`--decide-c`/`--accept-protocol` 추가.
- `rsna_diag/risk30_eval.py`: `capture_at_k_ceil`, `bootstrap_idx_nondegenerate`/`auroc_ci_safe`/`diff_auroc_ci_safe`, split-aware `h1_report`(C 95%/E 97.5% CI, 한 박스 층 diff 추가), `population_cost_report` 신설.
- 신규: `run_iter031_launch.py`, `run_iter031_eval.py`, `run_iter031_decide_c.py`, `run_iter031_decide_e.py`, `sanity_iter031.py`, `resume_test_iter031.py`, `test_rsna_iter031.py`.
- 결과: `results/iter_031/` 전체(protocol_v1/v2, D24/attempt1, D24/resume_test, C201/attempt1+report+decide, E402/attempt1+report, decide_e.json, sanity, tests, FINAL_REPORT.md). `results/iter_030/*`는 변경하지 않았다(재실행 검증 후 바이트 동일 확인).

# Commands / Experiments (실제 실행한 명령과 성공/실패)

1. `python test_rsna_iter031.py` → 32/32 PASS.
2. `python test_rsna_iter030.py` (재실행, 검증 목적) → 28/28 PASS, 결과 파일 기존과 바이트 동일.
3. `python -m rsna_diag.lock_protocol --extra ... --out results/iter_031/protocol_v1.json` → 성공. read_records 수정 후 `protocol_v2.json` 재잠금 → 성공.
4. `sanity_iter031.py 0` (GPU0) → 성공: tensor 완전 일치(6/6), adapter 재현(2/2).
5. `run_iter031_launch.py --split D24 ...` (2 worker) → 성공, 48/48, wall 254.6s.
6. `resume_test_iter031.py` → 성공: SIGKILL 후 재개, 12/12 완료, 중복 0.
7. `run_iter031_launch.py --split C ... --ids remaining_ids.json --accept-protocol protocol_v1.json` (4 worker, D24 48건 재사용) → 성공, 402/402, wall 935.2s(신규분).
8. `run_iter031_eval.py --split C` → 성공. `run_iter031_decide_c.py` → `enter_E=true`.
9. `run_iter031_launch.py --split E --decide-c decide_c.json` (4 worker) → 성공, 804/804, wall 2006.4s.
10. `run_iter031_eval.py --split E --decide-c decide_c.json` → 성공. `run_iter031_decide_e.py` → H1 inconclusive, H2 positive.

실패한 명령 없음. 모든 GPU job은 exit code 0, 프로세스·lock 잔존 없음(최종 확인).

# Results (수치와 결과 파일 경로)

- `results/iter_031/C201/report.json`: n=201, events=20, bstar=branch_chosen_token_nll(AUROC .780), diff_Q_minus_Bstar point −0.0037 CI[−0.0093,0.0014], one-box Q AUROC .711 CI[.555,.847], recovery 8/20=0.40 Wilson[.219,.613].
- `results/iter_031/decide_c.json`: point_criterion=false, recovery_criterion=true → **enter_E=true**.
- `results/iter_031/E402/report.json`: n=402, events=27, diff point −0.0011 CI(97.5%)[−0.0052,0.0026], one-box Q AUROC .642 CI[.515,.763], recovery 11/27=0.407 Wilson[.245,.593]. population_cost: F1@0.3 O .628→F .474(diff −.154), F1@0.5 O .347→F .266(diff −.081), recall +.019, extra FP/환자 1.037, 중복률 6.5%, invalid 0%.
- `results/iter_031/decide_e.json`: **H1=inconclusive, H2=positive**.
- `results/iter_031/FINAL_REPORT.md`: 전체 요약.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

`rsna_diag/{geometry,parse,metrics,__init__}.py`는 기존 승인 범위(iter_009~030) 그대로 재사용. `risk30*.py`/`risk28*.py`는 iter_030 needs_fix를 본 반복에서 수정·검증했다(위 코드 변경 참조). `results/iter_030/source_manifest.json`·`source_audit.json`은 read-only로 재사용(protocol에 잠가 hash 대조 완료). D24 24명분 O/F(48건)는 protocol_v1 digest를 명시적으로 accept하여 C201에 재사용, 중복 없음을 확인했다. iter_029 correction은 재실행하지 않고 그대로 재사용(결론 불변).

목표 진전: "부분 누락 시 continue 강제가 실제 놓친 병변을 회복하는가"는 이제 두 독립 표본(C201/E402)에서 일관되게 positive로 확인됐고, "그 결정을 언제 내릴지 판단하는 margin Q가 단순 baseline보다 나은가"는 inconclusive로 확정됐다(추가 표본이 이 결론을 바꿀지는 낮은 우선순위). 독립 확인(별도 데이터셋/기관)은 미실행.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- 현재 결론을 무효화하는 결함: 없음. 모든 필수 검증(protocol 강제, request_id, O 재현, F prefix, dedup, 재개, tensor 동등성)이 실측으로 통과했다.
- 재사용 전 수정 필요: 없음(이번 반복에서 iter_030의 needs_fix를 모두 이 실행 경로에 한해 해결). 다만 `run_iter031_*` 스크립트들은 "이번 호출 경로"만 검증됐고, 과거 iter_030 스크립트(`run_iter030_*`)는 여전히 needs_fix 상태로 남아있다(별도로 승인하지 않았다).
- 추후 개선: 다른 seed/기관 데이터에서의 재현, 독립 확인 집단 설계, 그리고 사용자 보완 지시(능력 전이 진단)로의 전환 판단.

# Recommendation to GPT

H1 inconclusive / H2 positive-but-costly라는 결과는 "이 특정 continuation 완화 설계"에 대한 명확한 정보를 제공했다고 본다. 부분 누락 진단 라인은 이 정도로 충분히 판별력 있는 실험을 완료했으므로, 다음 계획에서는 (a) 이 결과를 바탕으로 한 정교화(gate 있는 continuation 등)를 시도할지, 아니면 (b) 사용자가 이전에 승인한 능력 전이 진단(전략 재검토)으로 전환할지를 판단해 주기 바란다. 개인적으로는 H1이 단순 baseline을 못 이긴 점, 그리고 population 전체 F1 악화가 크다는 점에서 이 방향에 추가 정교화 투자를 곧바로 확대하기보다 전략 재검토 쪽에 무게가 있다고 본다.

SELF_CHECK: PASS
SUMMARY: iter_030 실행/평가 결함을 수정해 C201(402건)·E402(804건, 합계 계획 상한 1,206건과 일치)를 완료했고, H2(누락 회복)는 positive(약 40%)이나 H1(margin Q의 추가 판별력)은 inconclusive, 전체 F1은 오히려 악화되어 단순 continuation 완화는 실용적 개선이 아니다.