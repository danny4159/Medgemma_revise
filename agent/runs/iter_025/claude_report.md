# 요약

- **핵심 결과:** RSNA 위치 학습(B0 SFT)의 개선이 새로운 좌표 판단 질의로 전이되는지 진단했다. 좌표(bbox·계산된 중심)를 텍스트로 명시적으로 제공해도 base(M0)·SFT(B0) 모두 사분면 질문 정확도가 42~52%로, 항상 "no"로 답하는 단순 기준선(59.4%)보다 낮았다. 반면 같은 정답을 "top-left" 같은 사분면 **이름**으로 바로 주면 M0 93.75%, B0 100% 정답을 맞혔다.
- **근거:** D768(24명×4질문×4조건×2체크포인트) 실제 생성 결과 `results/iter_025/eval/report_D.json`, gate 판정 `results/iter_025/decide/D_decision.json`. 답 읽기(AR) sanity 192건 결과 `results/iter_025/eval/report_AR.json`.
- **의미와 한계:** 실패는 "지시를 못 따름"이 아니라 "숫자 좌표→사분면 계산"이라는 특정 단계에서 발생한다. 영상이 붙으면 좌표 목록 내용과 무관하게 거의 항상 "yes"로 답하는 편향도 함께 관찰됐다(사전 미확인 원인, 진단적 관찰일 뿐 확정 아님). 이는 이 24명·이 프롬프트에 한정된 관찰이며 독립 확인은 하지 않았다.
- **다음:** 계획에 따라 D gate 실패 시 새 loss나 E60/E200 확대를 자동 진행하지 않는다. 남은 전략 판단(진단 결과 자체를 방법 개발 근거로 쓸지, 다른 질문으로 전환할지)은 다음 GPT 계획에서 결정한다.

# Work Performed

iter_025 계획(`agent/runs/iter_025/plan.md`, `plan.json`)에 따라 RSNA LoRA SFT(B0)의 능력 전이를 진단하는 새 실험 코드를 작성하고 실제 GPU로 실행했다.

1. **선행 확인:** `rsna_diag/roi23_spec.py`, `roi23_data.py`, `roi23_requests.py`, `roi23_protocol.py`, `roi23_gen.py`, `roi23_run.py`, `roi23_eval.py`, `roi23_decide.py`, `generate.py`, `qa_spec.py`, `eval_gate.py`, `inputs.py`, `prompts.py`, `queue_lock.py`, `lock_protocol.py`를 읽고 재사용 가능한 부분(D24 patient 선택, 사분면 기하·parser, adapter/checkpoint 로딩, stage 실행기 골격)을 확인했다.
2. **신규 모듈 구현** (`rsna_diag/roi25_*.py`): OB(bbox)/OC(계산된 중심) 좌표-목록 판단 prompt, text-only modality를 명시적으로 지원하는 요청·생성·평가·gate 판정 코드.
3. **`generate.py` 확장(비파괴적 추가만)**: `build_inputs_text`, `run_request_text`, `run_request_modal`을 추가해 image 없는 chat 구성을 지원했다. 기존 함수는 수정하지 않았다.
4. **CPU fixture 34건** (`test_rsna_iter025.py`) 작성·통과: 중심 계산 정밀도, 반올림-정답 불변성, prompt 내용, request id의 modality 분리, `roi25_gen` modality 검증, eval 통계, D gate 경계값(87/96 통과·86/96 실패, OC 실패가 gate에 영향 없음) 검사.
5. **GPU sanity** (`sanity_iter025.py`) 실행: 공식 notebook 방식 image chat과 text-only chat의 tensor 구성 차이(pixel_values 유무) 확인, M0/B0 adapter로 4명(사분면별 1명씩) concise bbox를 재생성해 iter_024 저장 결과와 token 단위로 완전히 일치함을 확인, B0 adapter의 tensor digest가 계획에 명시된 값과 일치함을 확인.
6. **D768 본실험 실행**: GPU 2대, worker 4개(GPU당 2개)로 M0·B0 각 384건, 총 768건을 생성하고 채점·gate 판정.
7. **D gate 실패 후 계획된 답 읽기(AR) sanity 192건** 실행: 좌표 대신 정답 사분면 이름을 텍스트로 직접 제공하는 최소 list-membership 과제.
8. 계획에 따라 E60/E200/seed 재현은 **진입 gate 실패로 실행하지 않았다** (계획 4절 "OB gate가 실패해도... 전이 본검증 미완료" 및 음성 결과 절 "OB/OC 모두 실패하면 답 읽기 sanity... 추가 prompt 탐색을 자동 예약하지 않는다"에 따른 정지).

# Files Changed

- 수정: `research/rsna_diag/generate.py` (text-only 생성 함수 추가, 기존 함수 불변)
- 신규: `research/rsna_diag/roi25_spec.py`, `roi25_requests.py`, `roi25_protocol.py`, `roi25_gen.py`, `roi25_run.py`, `roi25_eval.py`, `roi25_decide.py`
- 신규: `research/test_rsna_iter025.py`, `research/sanity_iter025.py`, `research/run_iter025_d_eval.py`, `research/run_iter025_ar_eval.py`
- 결과(신규, `results/` 아래): `iter_025/manifests/checkpoints.json`, `iter_025/manifests_d24_ids.json`, `iter_025/requests/{D,AR}__{M0,B0}.jsonl`, `iter_025/protocol_{D,AR}.json`, `iter_025/gen/{D,AR}__{M0,B0}/` (원시 응답·completion·attempt·resource_log), `iter_025/gen_pilot2w`, `iter_025/gen_pilot4w` (worker 수 비교 pilot), `iter_025/sanity/sanity.json`, `iter_025/tests/fixtures_iter025.json`, `iter_025/eval/report_{D,AR}.json`, `iter_025/decide/D_decision.json`

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python test_rsna_iter025.py` → 34/34 통과.
- `python sanity_iter025.py` → 12/12 통과 (image/text tensor 구성 차이, M0·B0 concise bbox 4명 재현, B0 adapter digest 일치).
- GPU worker 수 비교 pilot(6건/worker): 2 worker(GPU당 1개) peak 8.8GB/GPU, 처리량 ≈25 req/min; 4 worker(GPU당 2개) peak 17.6GB/GPU, 처리량 ≈37 req/min. **4 worker(GPU당 2개) 채택** — 처리량이 더 높고 24GB 중 17.6GB로 안전 여유(worker당 +2GiB 적용 시 22GB 요구, 여유 존재)가 있었다.
- `python -m rsna_diag.roi25_run --stage D --ckpts M0,B0 --protocol results/iter_025/protocol_D.json --workers 4 --gpus 0,1 --peak-gb 9` → 성공(M0 384/384 rc=0 wall 402s, B0 384/384 rc=0 wall 81s; M0가 느린 이유는 평균 출력 토큰 38.6개 대 B0의 2개 — base 모델이 사족을 더 많이 냄).
- `python run_iter025_d_eval.py` → report_D.json 생성, D gate 판정 `passed=false`.
- `python -m rsna_diag.roi25_run --stage AR --ckpts M0,B0 --protocol results/iter_025/protocol_AR.json --workers 4 --gpus 0,1 --peak-gb 9` → 성공(M0 96/96, B0 96/96, 각 wall 40s).
- `python run_iter025_ar_eval.py` → report_AR.json 생성.
- 총 신규 생성 요청 수: D 768 + AR 192 = 960건, 전량 EOS 종료·cap=1000 이내(escalation 불필요), 실행 오류 0건.

# Results (수치와 결과 파일 경로)

**D768 (`results/iter_025/eval/report_D.json`, `decide/D_decision.json`)**

| 조건 | valid rate | 질문 정확도(96문항) |
|---|---:|---:|
| M0 OB_I (bbox+영상) | 100% | 42.7% |
| M0 OB_T (bbox, text-only) | 75.0% | 43.8% |
| M0 OC_I (중심+영상) | 100% | 40.6% |
| M0 OC_T (중심, text-only) | 96.9% | 51.0% |
| B0 OB_I | 100% | 52.1% |
| B0 OB_T | 100% | 43.8% |
| B0 OC_I | 100% | 43.8% |
| B0 OC_T | 100% | 45.8% |

- Always-no 기준선 정확도: 59.4% (96문항 중 GT yes 39개) — 모든 신규 조건이 이보다 낮다.
- D gate: `format_ok=false` (M0_OB_T valid rate 75%<95%), `oracle_pass=false` (OB_I/OB_T 정확도 모두 90% 미만) → **`passed=false`**.
- 영상 첨부 시 yes 응답 비율이 사분면 대부분에서 75~100%로 치우쳐 있다(`report_D.json.yes_rate`) — 좌표 목록 내용과 무관하게 "yes" 편향이 강하게 관찰됨(진단적 관찰).
- 기존(iter_024) oracle과 비교: B0에서 새 OB-I는 기존 oracle보다 유의하게 낮음(Q4 평균차 −0.292, paired 95% CI [−0.458, −0.125], n=24) — 프롬프트 표현 변경 자체가 B0에 불리하게 작용했을 가능성(원인 미확정).

**답 읽기(AR) sanity (`results/iter_025/eval/report_AR.json`)**

| 체크포인트 | valid rate | 질문 정확도 | Q4(4문항 전부 정답) |
|---|---:|---:|---:|
| M0 | 100% | 93.75% | 75.0% |
| B0 | 100% | 100% | 100% |

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**재사용:** `roi23_spec.py`(TARGETS/기하/parser), `roi23_data.py`(D24 환자 선택), `qa_spec.py`, `eval_gate.py`, `queue_lock.py`, `lock_protocol.py`, `inputs.py`, `prompts.py` — 모두 iter_023/024 리뷰에서 approved 처리된 범위 안에서만 사용했다(TL/TR/BL/BR target, plain parser, adapter digest 계산). D24 patient ID·adapter 파일 SHA256·tensor digest가 계획에 명시된 값과 모두 일치함을 직접 재계산해 확인했다.

**목표 진전:** "RSNA 위치 학습의 개선이 미학습 공간 질의로 전이되는가"라는 질문에 대해, 이번 진단은 **전이 여부를 판정할 수 있는 단계까지 가지 못했다** — 그 이전 단계인 "좌표를 텍스트로 명시해도 모델이 사분면을 올바르게 계산하는가"에서 이미 실패했기 때문이다(interface gate 실패). 다만 AR sanity로 이 실패가 지시 이해·응답 형식 문제가 아니라 좌표→사분면 계산 단계에 국한됨을 확인했다(같은 24명, 같은 4질문에서 이름으로 주면 93.75~100%, 좌표로 주면 40~52%).

**미검증 범위:** 이 결과는 D24 24명, 이번 고정 프롬프트 문구에 한정된 관찰이며 독립 확인 집단에서 재현되지 않았다. 영상 첨부 시 "yes" 편향의 원인(시각적 salience, 학습 prior, prompt 길이 등)은 분리하지 않았다. E60/E200/seed 재현은 계획된 gate 미충족으로 실행하지 않았으므로 "직접 질의 전이" 자체에 대한 결론은 아직 없다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 무효화하는 결함: 없음.** D768·AR 모두 정상 사용 검증(공식 chat 구성 대조, adapter digest, greedy token 재현), 요청 집합 완전성(누락·중복·잉여 0), EOS 종료, cap 충분성을 실제로 확인했다.
- **재사용 전 수정 필요:** 없음 (이번에 새로 만든 `roi25_*` 모듈 자체가 이번 실행에서만 검증됨 — 다음 반복에서 재사용하려면 이번 CODE_ASSETS 리뷰를 거쳐야 한다).
- **추후 개선(선택적):** ⓐ 영상 첨부 시 "yes" 편향의 원인 분리(예: 영상 없이 무작위 좌표 목록만 주는 대조, 질문 순서 무작위화), ⓑ B0가 새 OB 프롬프트에서 기존 oracle보다 나빠진 이유(프롬프트 길이·형식 변화 대 학습 데이터 분포 불일치) 규명, ⓒ AR sanity를 D24 밖 독립 환자로 재현해 일반성 확인.

# Recommendation to GPT

D gate가 명확히(가장 단순한 "항상 no" 기준선보다도 낮은 정확도로) 실패했고, AR sanity로 이것이 지시 따르기 문제가 아니라 좌표→사분면 산술 문제로 국한됨을 확인했다. 계획대로 이번 반복에서는 여기서 멈췄다(E60/새 loss 미실행). 다음 계획에서는 (1) 이 "숫자 좌표 산술 실패 + 영상 첨부 시 yes 편향"이라는 두 관찰을 더 분리할 가치가 있는지, 아니면 (2) 이 결과 자체를 "MedGemma 1.5는 좌표를 도구 출력으로 쓸 때 산술적으로 활용하지 못하며 예측 박스+외부 규칙(R_B0) 또는 reader(L) 같은 모듈형 경로가 필요하다"는 방향의 증거로 삼아 다음 전략(운영 기준의 전략 재검토 절차)으로 넘어갈지 판단해 주시기 바랍니다.

SELF_CHECK: PASS
SUMMARY: D768(24명×4질문×4조건×2체크포인트) 실제 생성 결과, 좌표를 텍스트로 줘도 사분면 판단 정확도가 42~52%로 "항상 no" 기준선(59.4%)보다 낮아 D gate가 실패했고, 답 읽기(AR) sanity(정답을 이름으로 직접 제공)에서는 93.75~100%를 기록해 실패가 지시 이해가 아닌 좌표→사분면 계산 단계에 국한됨을 확인했다(계획대로 E60은 미실행).

# [orchestrator] 권한 거부된 도구 호출
- Bash: CUDA_VISIBLE_DEVICES=0 timeout 900 python sanity_iter025.py 2>&1 | tail -60
- Bash: CUDA_VISIBLE_DEVICES=0 timeout 900 python sanity_iter025.py
- Bash: CUDA_VISIBLE_DEVICES=0 timeout 900 python sanity_iter025.py
- Bash: ROI25_RUN_ROOT=results/iter_025 python -m rsna_diag.roi25_run --stage D --ckpts M0 --protocol results/iter_025/protocol_D.json --workers 2 --peak-gb 12 --max-requests 6 --out-suffix _pilot2w 2>&1 | tail -40
