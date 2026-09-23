보고서와 노트 작성을 마쳤고, 최종 보고서를 정리합니다.

# Work Performed
- iter_003 계획의 "3D 근거 보존 context 안정화" 기전 pilot을 구현하고 끝까지 실행했습니다. 대상은 로컬 BraTS 3 case × T1CE/T2입니다.
- **데이터 구성 (CPU)**
  - 영상과 seg를 `nib.as_closest_canonical`로 같은 RAS 방향으로 변환했습니다. 보간 없이 축만 뒤집습니다.
  - intensity 범위는 case-sequence별 1/99 percentile로 한 번 정해 모든 slice에 같게 적용했습니다.
  - 계획 규칙대로 E·N·R·A·B를 각 2 slice씩 골랐습니다. 제외 이유, source hash, pairwise L1을 manifest에 저장했습니다.
  - 6 case-sequence 모두 적격이어서 제외된 것은 없습니다.
- **CPU 검증**: 영상-mask 정렬, 근거 픽셀 불변, packet 비중복, 조건별 영상 수, P1/P3 multiset 보존, 반복 slice multiplicity, IAF 수동 예제, case 단위 집계와 기권 분모를 확인했고 모두 PASS입니다.
- **Scoring**: `logP("Yes")−logP("No")`를 계산합니다. 두 후보가 모두 단일 token임을 확인했습니다.
  - 독립 teacher-forced 계산과 대조했습니다.
  - `답+\n+<end_of_turn>`까지 포함한 continuation 점수를 보조로 기록했습니다.
  - greedy 생성(최대 8 token)으로 12개 입력을 확인했습니다.
- **비교 방법**: concat, paired 보정(oracle), 독립 slice mean(중복 포함 / unique) 및 max, IAF(MedPruner 본문의 slice filtering만), P1/P3 2-order ensemble, consistency 기권, packet-only(oracle).
- **사후 탐색 (CPU, 사전 기준 아님)**: 비례형 희석 분석.
- 선행 연구 노트와 README 실행법을 추가했습니다.
- 재개 시 이미 끝난 추론·분석은 다시 하지 않았습니다. 남아 있던 사후 분석, 보고서, 노트만 마쳤습니다.

# Files Changed
- 신규: `research/context_pilot/__init__.py`, `research/context_pilot/data.py`
- 신규: `research/build_context_manifest.py`, `research/run_context_pilot.py`, `research/analyze_context_pilot.py`, `research/test_context_pilot.py`
- 신규: `research/notes/related_work_iter003.md`
- 수정: `research/README.md` (iter_003 실행법 추가)
- 결과: `research/results/iter_003/`
  - `config.json`, `manifest.json`, `labels.json`, `requests.jsonl`, `predictions.jsonl`, `metrics.json`
  - `budget.json`, `env_*.json`, `report.md`, `slices/`, `montage/`

# Commands / Experiments (실제 실행한 명령과 성공/실패)
1. `python research/build_context_manifest.py --out research/results/iter_003` — 성공. 6/6 case-sequence 적격, 요청 294개.
2. `python research/run_context_pilot.py --out ... --max-requests 8 --note pilot` — 성공.
   - 예비 실행이며 GPU 1장을 사용했습니다. 로딩 28s, peak 8.7GB, 0.80 device-min.
   - 이후 보조 continuation 정의를 바꾸고 `SCORER_VERSION=2`를 붙였습니다. 그래서 예비 결과 8줄은 분석에서 제외됩니다.
3. `python research/test_context_pilot.py --out ...` — 성공. CPU 검증 5종 모두 PASS.
4. `python research/run_context_pilot.py --out ... --note full` — 성공.
   - 294/294 ok, OOM 0, 4.95 device-min.
   - 누적 5.75 device-min으로 예산 55 이내이며, 축소 규칙은 적용되지 않았습니다.
5. `python research/analyze_context_pilot.py --out ...` — 성공.
6. 사후 비율 분석은 `python -c`로 실행했습니다 — 성공.
7. 재개 확인용 `git status`는 권한 승인이 필요해 실행하지 못했습니다. 대신 `results/` 파일로 진행 상태를 확인했습니다.

# Results (수치와 결과 파일 경로)
분모는 독립 case 3개이고 소표본입니다. 모든 수치는 case 안에서 sequence를 평균한 뒤 case를 평균한 값입니다. label은 annotation 기반 proxy입니다.

**Scoring 검증**
- teacher-forced 계산과 last-logit 계산의 차이는 최대 1.2e-7입니다.
- 생성 12/12가 파싱됐고 scoring 결정과 모두 일치했으며, 잘린 응답은 0개입니다.
- P(Yes)+P(No)는 최소 0.973입니다.
- 동일 입력 반복(24쌍 + 동일 hash 51그룹)의 차이는 모두 0입니다. 단, bf16 logits 양자화 단위가 약 0.125입니다.

**사전 진행 기준**

| 기준 | 판정 | 근거 |
|---|---|---|
| 1 측정 가능성 | PASS | P0 margin이 6/6 case-sequence에서 양수, P0 BA 0.917 |
| 2 불안정성 | PASS | P1↔P3 \|Δm\|≥0.5가 3/3 case(최대 3.5), P1↔P2도 2 case. 같은 길이 조건 간 결정 flip은 0건이고, flip은 P4/P6처럼 긴 context에서만 발생 |
| 3 paired 보정 | **FAIL** | 아래 참조 |

- paired 보정은 drift를 줄이지 못하고 오히려 늘렸습니다.
  - drift: 4.491 → 4.620 (−2.9%, 증가), 감소한 case는 0/3입니다.
  - BA 0.964 → 0.917, worst-context accuracy 0.833 → 0.667로 모두 낮아졌습니다.
  - N의 drift는 46% 줄었지만 E의 drift는 18% 늘었습니다.
  - 원인: empty 후보가 좁은 z 구간에 몰려 있어 R이 N과 인접 slice였습니다. 그래서 R은 N의 변화는 잘 따라가지만 E의 변화는 반영하지 못합니다.

**방법별 비교 (P0–P6)**

| 방법 | oracle | BA | worst-context | drift | 비고 |
|---|---|---|---|---|---|
| concat | no | 0.964 | 0.833 | 4.49 | |
| single mean (unique) | no | 0.988 | 0.917 | 4.37 | 비-oracle 중 최고 |
| single max | no | 0.774 | 0.750 | 0.79 | drift는 낮지만 N 오탐 증가 |
| IAF (γ=0.05) | no | 0.774 | 0.500 | 4.95 | P1–P6 E 입력 36개 중 15개에서 E slice 전부 제거, E 보존율 0.292 |
| packet-only | **yes** | 0.917 | 0.917 | 0 | context 제거 기준 |

- P1/P3의 ensemble과 기권은 결정 불일치가 없어서 concat과 결과가 같았습니다 (BA 1.0, coverage 1.0).

**사후 탐색 (가설 수준)**
- context가 붙으면 E의 log-odds는 평균 0.34배로 줄지만, empty packet은 N 0.76배, R 0.72배로 덜 줄어듭니다. 양성 근거만 선택적으로 희석되는 모양입니다.
- 근거를 앞에 두면 희석이 덜합니다 (α_E: P3 0.60 vs P1 0.44). 반복 context가 붙으면 더 심합니다 (P6 0.21).
- 따라서 가산형이든 비례형이든 R 기반 공통 보정으로는 이 효과를 상쇄할 수 없습니다.

상세는 `research/results/iter_003/report.md`와 `metrics.json`에 있습니다.

# Problems
- 계획은 258개 요청이었지만 실제로는 294개를 실행했습니다. 추가분은 두 가지입니다.
  - P0 IAF 12개: P0에서도 IAF가 E slice 1개를 지워 별도 scoring이 필요했습니다.
  - 반복 오차 측정용 24개.
- empty 후보가 뇌 상·하단의 좁은 구간에 몰려 N/R/A/B가 서로 인접 slice가 됐습니다. 이 때문에 context가 거의 같은 해부 구조의 반복이 됐고, R이 N의 대리값으로 유리하게 작용했습니다. E와 empty slice 사이의 뇌 면적 차이도 큽니다 (montage에서 확인).
- 00005 T2의 N packet(P0)은 모델이 "Yes"로 답했습니다 (m=+1.13). 미주석 이상인지, 오탐인지는 판단할 수 없습니다.
- IAF는 본문에 적힌 규칙만 구현했습니다. 240×240 원본 해상도에서 L1을 비교했고, MedPruner 저자 코드와는 대조하지 못했습니다.
- `git status` / `git diff`는 권한 문제로 실행하지 못했습니다.
- 선행 연구 노트는 GPT 사고 라운드의 내용을 옮긴 것입니다. 이번에 원문을 다시 열어 검증하지는 않았습니다. `agent/PAPERS.md`는 존재하지 않습니다.

# Recommendation to GPT
- 사전 기준 3이 FAIL이므로, 계획에 정한 대로 "GT reference paired 가산 보정" 가설은 포기하는 것이 맞습니다.
- 다만 context가 양성 근거를 선택적으로 희석하고, 근거 위치와 반복 context에 따라 그 정도가 달라지는 신호가 나왔습니다 (사후 관찰). 다음 반복에서 이를 **사전 가설로 등록해 검증**할 것을 권합니다.
  - 예: 근거 위치(앞/뒤)와 empty context 양을 체계적으로 바꾸는 dose-response 설계.
  - 이번처럼 인접 slice로 context를 구성하지 않도록, 서로 다른 해부 수준에서 context를 구성해야 합니다.
- 단순 baseline 중에서는 unique slice 독립 점수 평균이 BA 0.988, worst-context 0.917로 가장 강했습니다. 새 방법은 최소한 이 baseline과 비교해야 합니다.
- MedPruner IAF(γ=0.05)는 뇌 MRI에서 병변 slice를 지우는 실패 사례로 보고할 가치가 있습니다. 저자 코드와 정규화 방식을 확인한 뒤 확정해야 합니다.
- 3 case는 기전 확인 수준입니다. 다음 단계는 두 가지입니다.
  - MRI-GBM-MET 또는 BraTS 추가 subject를 확보하되, 라이선스와 subject 단위 split을 먼저 확인합니다.
  - mask 없이 작동하는 설계(근거 slice 선택 또는 순서 전략)로 넘어갑니다.

SELF_CHECK: FAIL
SUMMARY: BraTS 3 case pilot을 끝까지 실행(294 요청, 5.75 device-min)해 측정 가능성·불안정성 기준은 통과했지만, GT reference paired 보정은 drift를 줄이지 못해(−2.9%, BA·worst 하락) 가설을 기각했고, context가 양성 근거를 선택적으로 희석한다는 사후 신호와 IAF(γ=0.05)의 병변 slice 제거 문제를 발견했다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git -C /SSD1_1TB/home/milab/daniel/08_medgemma/research status --short
