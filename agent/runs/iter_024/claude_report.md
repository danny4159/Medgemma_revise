Now I have everything needed to write the final report.

# 요약

- **핵심 결과:** iter_023에서 중단됐던 RSNA 사분면 질의 전이 진단을 복구해 D24 동작 확인 단계를 실제 GPU에서 완료했다. 형식(plain yes/no) 준수는 6개 조건 모두 100%(576/576)였지만, 사전에 정한 oracle gate(정답 bbox를 텍스트로 직접 줬을 때 사분면 질문에 90% 이상 정답)는 base M0 42.7%, SFT B0 67.7%로 모두 기준 미달이었다. 계획에 따라 이 gate 실패 시 E60으로 진행하지 않고 형식·지시 문제로 보고하도록 되어 있어, **E60/E200/seed 비교는 실행하지 않았다.**
- **근거:** 오답 패턴을 직접 3건 수기 검산한 결과 좌표·사분면 계산 자체는 정확했고(파이프라인 버그 아님), 대신 base M0가 정답 bbox 좌표를 줘도 "yes"로 답하는 비율이 93.8%(직접 질문 무증거 조건도 96.9%)에 달하는 강한 응답 편향을 보였다. SFT B0는 이 편향이 완화됐지만(43.8%/42.7% yes-rate) oracle 정확도가 여전히 90%에 못 미쳤다. 회색(빈) 대조 영상에서도 M0는 하단 두 사분면에 항상 "yes", B0는 항상 "no"로 답해 내용과 무관한 위치 편향/응답 prior 차이를 보였다.
- **미검증·주의:** D_B0−D_M0(환자 단위 Q4) 점추정 +0.167(CI[0.042,0.333])과 G_official +0.25(CI[0,0.5])는 원자료로 계산했지만, oracle gate 실패로 인해 "학습되지 않은 사분면 질의로의 전이" 증거로 해석할 수 없다. 이 차이는 일반적 응답 편향(yes-prior) 변화로 상당 부분 설명될 수 있어, 계획서의 경쟁 설명("답변 prior") 중 하나가 지지된다.
- **다음:** 이번 gate 실패는 계획이 예견한 정상적 종료 경로다. 새 prompt 탐색이나 재학습을 자동 추가하지 않았다(계획 지시대로). 다음 GPT 계획에서 이 결과를 근거로 (a) 다른 evidence 표현(예: 좌표 대신 사분면 명시적 서술)으로 gate를 다시 시도할지, (b) 이 진단 경로를 여기서 종료하고 다른 정보 이득이 큰 질문으로 전환할지 판단이 필요하다.

# Work Performed

1. **코드 검토 및 수정 (재사용 전 결함 해소, iter_023 리뷰의 needs_fix 대응):**
   - `roi23_pipeline.py`의 `cmd_score`: `oracle_accuracy` 분모가 `status=="valid"`인 질문만 세던 버그를 고쳐, 계획대로 **전체 96개 질문을 분모로** 하는 `acc_over_all_questions`를 추가했다(invalid도 오답으로 분모에 포함).
   - `cmd_score`: fmt를 `"plain"`으로 하드코딩하던 것을 각 조건의 실제 요청 행(`row["fmt"]`)에서 읽어오도록 고쳐, 형식이 바뀌어도(JSON fallback 포함) 정확한 parser가 쓰이게 했다.
   - `cmd_qa_requests_d24`: B0 D24_bbox 원시 결과를 읽을 때 completion.json 검증 없이, 그리고 중복 id를 조용히 덮어쓰던 버그를 고쳐, completion 검증과 중복 시 명시적 예외를 추가했다.
   - `cmd_requests`: E60/E200 요청 생성 전에 이전 stage decision을 **재계산 검증**(파일 존재만으로 통과하지 않음)하도록 `_require_decision`을 추가했다.
   - `roi23_eval.paired_ci`: 계획서 식 `[L_improve−U_worsen, U_improve−L_worsen]`(clip [-1,1])을 `diff_interval_clipped`/`judge_ci_lo/hi`로 구현해 퇴화 CI에서도 판정 가능하게 했다.
   - 신규 `roi23_decide.py`: D24 형식/oracle gate, E stage 확대 gate를 report 원본에서 **재계산**하고, 결정 파일이 가리키는 report가 사후에 바뀌면 `recheck()`가 거부하도록 구현했다(파일 존재나 저장된 boolean만 믿지 않음).
   - `roi23_protocol.py`의 `REQUIRED_CODE`에 `roi23_decide.py` 추가.
2. **테스트:** 기존 `test_rsna_iter023.py`(45개, 전부 통과 유지)를 재실행해 회귀가 없음을 확인했고, 새 `test_rsna_iter024.py`(10개)를 작성해 gate 재계산·중복 거부·변조 거부·pipeline 연결을 CPU에서 검증했다.
3. **실행 범위 결정(재사용 전략):** iter_023의 부분 산출물(M0 bbox 47/48, B0 미실행)은 cross-protocol 호환성 검증이 protocol digest·adapter 재검증 등 상당한 추가 위험/작업을 요구하는 반면, 72건의 bbox 재생성 비용은 낮아(GPU 수 분 수준), **iter_023 원본은 그대로 보존하고 `ROI23_RUN_ROOT=results/iter_024`에서 D24 전체를 처음부터 재생성**하기로 결정했다. iter_023 결과 디렉터리는 이번 작업에서 전혀 수정되지 않았다(재확인 완료).
4. **GPU 실행:** manifests 빌드 → D24 bbox 생성(M0 48건, B0 24건) → D24 QA 6조건(576건) + gray 대조(8건) 생성 → 채점 → gate 판정까지 실제로 완료했다.

# Files Changed

- `research/rsna_diag/roi23_pipeline.py` (oracle 분모 수정, fmt 동적화, dedup/completion 검증 추가, decision gate 연결, fmt CLI 인자)
- `research/rsna_diag/roi23_eval.py` (퇴화 CI의 `diff_interval_clipped`/`judge_ci_lo/hi` 추가)
- `research/rsna_diag/roi23_protocol.py` (REQUIRED_CODE에 roi23_decide.py 추가)
- `research/rsna_diag/roi23_decide.py` (신규: D24/E stage gate 계산 및 recheck)
- `research/test_rsna_iter024.py` (신규: CPU fixture 10건)
- 결과 신규 경로: `research/results/iter_024/{manifests,requests,gen,eval,decide,tests}/*`

# Commands / Experiments (실제 실행한 명령과 성공/실패)

모두 `ROI23_RUN_ROOT=results/iter_024`, model revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, config digest `2d73a46066bf1109b90987ebcf964d10ede293885cc36b24c387b9a77cc5fd57`(iter_023과 동일 = 환경 불변 확인).

1. `python test_rsna_iter023.py` → 45/45 PASS (성공, 회귀 없음)
2. `python test_rsna_iter024.py` → 10/10 PASS (성공)
3. `python -m rsna_diag.roi23_pipeline manifests` → 성공. D24=24, E60=48/12(primary/boundary), E200=160/40 (iter_023 fixture와 동일 수치로 재현됨)
4. `python -m rsna_diag.roi23_pipeline requests --stage D24 --cfg ...` → 성공 (M0 48, B0 24 요청)
5. `python -m rsna_diag.roi23_protocol --out results/iter_024/protocol_D24_bbox.json --extra ...` → 성공, protocol digest `467e3944...`
6. `python -m rsna_diag.roi23_run --stage D24_bbox --ckpts M0,B0 --protocol ... --workers 4 --gpus 0,1 --peak-gb 9` → **성공**. M0 rc=[0,0,0,0] wall=624s 48/48, B0 rc=[0,0,0,0] wall=81s 24/24. GPU peak 관측 17.8/17.7GiB (iter_023 review 기록과 일치하는 구성 재사용, 별도 처리량 비교는 생략 — 근거: 기존 실측이 이미 안전 마진과 이득을 보여줌).
7. `python -m rsna_diag.roi23_pipeline d24-qa-requests --cfg ... --fmt plain` → 성공, D24 6조건×96 + gray 2×4 = 584건 요청 생성
8. `python -m rsna_diag.roi23_protocol --out results/iter_024/protocol_D24_qa.json --extra ...` → 성공, protocol digest `0c8980c4...`
9. `python -m rsna_diag.roi23_run --stage D24 --ckpts D_M0,D_B0,L,U,O_M0,O_B0 --protocol ... --workers 4 --gpus 0,1 --peak-gb 9` → **성공**, 6개 조건 모두 rc=[0,0,0,0], 576/576, wall 40–60초/조건
10. `python -m rsna_diag.roi23_run --stage gray --ckpts D_M0,D_B0 --protocol ... --workers 2 --gpus 0,1 --peak-gb 9` → 성공, 8/8
11. `python -m rsna_diag.roi23_pipeline score --stage D24` → 성공, `results/iter_024/eval/report_D24.json` 생성
12. `python -m rsna_diag.roi23_decide D24` → 성공, `results/iter_024/decide/D24_decision.json`: **passed=false (oracle_pass=false)**

**미실행(의도적, gate 실패에 따른 정지):** E60/E200 요청 생성·생성·채점, B29/B43 seed 비교. `roi23_pipeline.cmd_requests`의 `_require_decision`이 코드 수준에서도 이를 차단한다(D24 decision의 `passed`가 false이므로 E60 요청 생성 시 `RuntimeError`가 발생하도록 구현·검증됨, test #10 참고).

GPU 사용량: 총 wall-clock 약 15분(bbox 624+81s + QA 6×~45s평균 + gray 80s + 로딩/검증), 두 GPU 모두 peak ≈17.8GiB로 24GB 한도 내 안전. 다른 프로세스와 경합 없음(사전/사후 `nvidia-smi` 확인, 실행 전 87MiB/15MiB, 실행 후 87MiB/15MiB로 원복).

# Results (수치와 결과 파일 경로)

전체 report: `research/results/iter_024/eval/report_D24.json`, decision: `research/results/iter_024/decide/D24_decision.json`

**형식(모든 6조건 100% valid, 576/576):**

| 조건 | 설명 | valid rate |
|---|---|---|
| D_M0 | base 직접 질문 | 96/96 |
| D_B0 | SFT 직접 질문 | 96/96 |
| L | base + B0 예측 bbox reader | 96/96 |
| U | base + "정보 없음" | 96/96 |
| O_M0 | base + GT oracle bbox | 96/96 |
| O_B0 | SFT + GT oracle bbox | 96/96 |

**Oracle gate (전체 96질문 분모, 기준 ≥90%): 실패**
- O_M0: 41/96 정답 = **42.7%**
- O_B0: 65/96 정답 = **67.7%**

**질문 단위 정확도 및 "yes" 응답 비율(수기 재계산, 파이프라인과 독립):**

| 조건 | 정확도 | yes 응답 비율 |
|---|---|---|
| D_M0 | 41.7% | 96.9% |
| D_B0 | 62.5% | 42.7% |
| L | 46.9% | 75.0% |
| U | 56.2% | 21.9% |
| O_M0 | 42.7% | 93.8% |
| O_B0 | 67.7% | 43.8% |

**환자 단위 Q4(4문항 전부 정답, n=24, paired bootstrap 10,000회, seed 23023):**
- `delta_direct` (D_B0−D_M0) = +0.1667, 95% CI [0.042, 0.333], 개선 4/악화 0/동일 20
- `G_official` (규칙 기반 B0 bbox − M0 bbox) = +0.25, 95% CI [0, 0.5]

**회색(빈 128 영상) 대조:** M0는 하단 두 사분면(BL,BR)에 항상 "yes", 상단은 항상 "no" (내용과 무관한 고정 위치 편향). B0는 네 사분면 모두 "no" (내용과 무관하게 비어있다고 정확히 답함).

**수기 검산(오답 3건 직접 계산):** `val_00007487`(box center → BR인데 TR 질문에 GT=no, 모델=yes), `val_00012146`, `val_00005416` 모두 좌표→사분면 변환이 코드와 일치함을 확인 — **파이프라인/좌표 버그가 아니라 모델의 실제 응답 편향**으로 판단.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **재사용:** `roi23_spec.py`, `qa_spec.py`(질문·parser, iter_023/이전 승인 범위), `roi23_data.py`/`roi23_requests.py`(전처리·좌표·요청 구성), `roi23_gen.py`/`roi23_run.py`(worker·lock·완료 검증, iter_023 needs_fix였던 항목 중 completion 검증·claim 소유권 로직 그대로 사용하되 이번 실행에서 실제로 재개 없이 단일 attempt로 정상 완료됨 — iter_023이 지적한 "재개 경로 미검증" 자체는 이번에도 발생하지 않아 별도로 검증하지 못했다), `roi23_eval.py`(통계 계산, oracle 버그 수정 후 사용). `B0` adapter는 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`(tensor digest `e13f3c44...`, checkpoints.json에 기록, iter_023 계획의 파일 SHA와 일치 확인).
- **iter_023 대비 진전:** 부분 준비/중단 상태에서 **실제 D24 QA 결과를 얻었다.** 사전 등록한 oracle gate가 실패해 E60/E200으로 진행하지 못했지만, 이는 계획이 정의한 정상적인 "gate 실패" 종료 경로이며 실행 실패가 아니다(전 요청 100% 완료, 형식 100% 정상).
- **미검증 범위:** iter_023 리뷰가 지적한 "실제 중단·재개" 경로는 이번에도 필요하지 않아(단일 attempt로 완료) 검증되지 않았다. E60/E200/seed 비교는 gate 실패로 실행하지 않았으므로 관련 처리량·재개 검증도 없다.
- **한계 기록(LIMITATIONS.md) 업데이트 필요성:** 이번 결과는 `lesion-grounding-generalization`(validated, RSNA bbox 개선 유지)과 별개로, 사분면 질의 전이 진단 자체는 오라클 gate 실패로 판정 보류(inconclusive at gate) 상태다. 새 limitation 항목("quadrant-transfer-oracle-gate-failure" 또는 유사, observed)으로 다음 GPT 리뷰에서 등록을 검토할 필요가 있다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

**현재 결론을 막는 요인 (이번 진단의 핵심 결과):**
- Oracle gate 실패로 `Δ_direct`, `G_official`의 양의 점추정을 "학습되지 않은 사분면 질의로의 전이" 증거로 해석할 수 없다. 계획서가 명시한 경쟁 설명(답변 prior 변화)이 오히려 가장 유력하다: yes-응답 비율이 M0(93.8–96.9%)에서 B0(42.7–43.8%)로 극적으로 이동한 것이, 실제 위치 판단 능력 차이가 아니라 일반적 응답 균형(calibration) 변화를 더 크게 반영할 수 있다.

**재사용 전 수정 필요(다음 반복에서 이 경로를 계속 쓴다면):**
- `roi23_run.py`의 실제 중단·재개 경로는 이번에도 실전 검증되지 않았다(정상 완료만 관측). iter_023 리뷰가 지적한 문제이며 여전히 미해결이다.
- oracle evidence 표현(원시 JSON 좌표)이 "숫자→사분면 변환"이라는 부가 인지 부담을 요구한다는 점이 이번 결과로 뚜렷해졌다. 계획이 금지한 "새 prompt 탐색"을 이번에 하지 않았지만, 다음 계획에서 gate를 재시도할지 판단할 때 이 지점(evidence 표현 방식 자체가 gate 실패의 주 원인일 가능성)을 검토 대상으로 남긴다.

**추후 개선(선택적):**
- `roi23_decide.py`의 E stage discordance 근사(`q_upper`)는 계획식의 정확한 정의를 단순화한 근사이며, 실제 E stage를 실행하지 않아 검증되지 않았다.

# Recommendation to GPT

D24 동작 확인은 완료됐고 결과는 깨끗하다(100% 형식 준수, 100% 요청 완료, 좌표/파이프라인 버그 없음 확인). 그러나 사전 등록한 oracle gate가 두 checkpoint 모두에서 실패해(42.7%, 67.7% < 90%) 계획대로 E60/E200/seed 비교로 진행하지 않았다. 다음 판단이 필요하다: (1) 이 gate 실패를 "이 evidence 표현으로는 사분면 전이를 판별할 수 없다"는 결론으로 확정하고 진단을 종료할지, (2) evidence 표현 방식을 (원시 좌표 대신 예: "top-half/bottom-half/left-half/right-half" 같은 더 단순한 서술로) 바꿔 gate를 한 번 더 시도할 가치가 있는지, 아니면 (3) 이 정보 이득 대비 다른 후보(예: 다른 checkpoint 진단)로 전환할지. 관찰된 강한 yes-bias/응답 prior 이동 패턴은 그 자체로 보고할 가치가 있는 관찰이지만, 이것이 "임상적으로 의미 있는 능력 전이"인지 "형식/calibration 인공물"인지는 이번 데이터만으로 구분되지 않는다.

SELF_CHECK: PASS
SUMMARY: D24 사분면 QA를 실제 GPU에서 완료했으나(형식 100% 정상) 사전 등록한 oracle gate가 base 42.7%/SFT 67.7%로 기준(90%) 미달해 계획대로 E60/E200 확대 없이 gate 실패로 정지·보고했다.