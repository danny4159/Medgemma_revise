# Work Performed
- iter_004 계획을 끝까지 구현하고 실행했습니다. 수식 C = D − 다른 질문들의 D 평균을 그대로 썼고, blur를 주방법으로, mean-fill을 독립 적용으로 돌렸습니다.
  - 대상: 로컬 VinDr 10영상 × 질문 6개 × 입력 28종(원본 1, crop 9, blur 9, mean-fill 9)
- iter_003 소스 파일이 저장소에 남아 있지 않았습니다(`context_pilot/`에는 `__pycache__`만 있음). 그래서 리뷰에서 지적된 결함을 반영해 `research/qes/` 모듈로 새로 작성했습니다.
  - 예산 축소: 실행 목록을 미리 한 번에 만드는 방식(`plan_queue`)으로 바꿨습니다. 실행 중 목록을 재할당하지 않습니다.
  - import 부작용 제거: torch는 `Scorer.load()` 안에서만 import합니다.
  - 캐시 검증: 원본 파일 hash, 실제 RGB pixel hash, 입력별 pixel hash, 요청 hash, config hash(model/processor revision 포함), scorer version을 모두 대조합니다. 재개와 집계가 같은 `validate_predictions`를 씁니다.
  - 중복·누락: 서로 다른 값의 중복 결과는 채택하지 않습니다. 누락이나 error가 하나라도 있으면 `incomplete`로 판정합니다.
  - 사용량 기록: 요청마다 `Ledger`에 저장합니다. 비정상 종료로 닫히지 않은 세션에는 2 device-min을 보수적으로 추가 계상합니다.
  - 순서 분리: selector는 label 없이 선택 결과를 먼저 `selections.json`에 고정합니다. evaluator는 그 뒤에 annotation을 읽습니다.
- 모델을 돌리기 전에 calibration 24건과 verification 12건을 고정했습니다. 평가 층도 GT geometry로 계획과 일치하는지 확인했습니다: 20조합/9영상, distinct 쌍 13쌍/6영상.
- 관련 연구 노트를 작성했습니다(C의 대수적 동치, CASE와의 차이, CSGR의 gold answer 의존). 단순 baseline을 선행 방법의 재현으로 표기하지 않았습니다.

# Files Changed
- 신규: `research/qes/{__init__,data,store,scorer,selection,evaluation}.py`
- 신규: `research/build_qes_manifest.py`, `run_qes.py`, `select_qes.py`, `evaluate_qes.py`, `test_qes.py`
- 신규: `research/notes/related_work_iter004.md`
- 수정: `research/README.md` (iter_004 실행법)
- 결과: `research/results/iter_004/` 전체 (iter_003 산출물은 건드리지 않음)

# Commands / Experiments (실제 실행한 명령과 성공/실패)
1. `python research/test_qes.py --out research/results/iter_004` — 성공, CPU 검증 42/42 PASS.
   - 포함 항목: 실제 이미지·config·prompt·scorer version이 바뀌면 캐시 거부, 값이 다른 중복, 누락/error 판정, 명시적 queue 축소, 미종료 세션 penalty, GT 변경이 후보와 선택에 영향 없음, bbox union·pair S·image/question swap·uniform·location prior 수작업 예제, C = contrastive attribution, ΣC=0.
2. `python research/build_qes_manifest.py --out ...` — 성공, 1,680 요청.
3. `nvidia-smi` — GPU0 24,039MiB, GPU1 24,112MiB 여유. 한 GPU(1번), 한 프로세스로 실행했습니다.
4. `run_qes.py --phase calib` — 성공, 24건.
   - 요청당 중앙값 0.51s, 예상 총량 18.8 device-min으로 기준 40 이하라 계속 진행했습니다.
5. `run_qes.py --phase full` — 성공, 1,656건 ok, OOM 0.
   - 도구 타임아웃(600s)으로 백그라운드로 넘어갔지만 exit 0으로 정상 완료됐습니다.
6. `run_qes.py --phase verify` — 성공. 반복 scoring 12회, teacher-forced 24 forward, greedy 생성 12회(96 forward, 9.7s).
7. `select_qes.py` — 성공, complete 판정.
8. `evaluate_qes.py` — 성공.
9. `python -c`로 CPU processor 확인 — image soft token 256개와 boi token 1개를 확인했습니다.

# Results (수치와 결과 파일 경로)
누적 GPU 사용량은 **11.28 device-min**입니다(`budget.json`). 수치는 모두 9영상 macro 평균이고, 개발용 소표본입니다.

| method | macro U | IoU | image-swap U | S distinct |
|---|---:|---:|---:|---:|
| **C_blur (주방법)** | 0.511 | 0.084 | 0.388 | 0.201 |
| D_blur | 0.499 | 0.085 | 0.339 | 0.104 |
| C_mean | 0.518 | 0.085 | 0.424 | 0.251 |
| D_mean | 0.466 | 0.070 | 0.316 | 0.142 |
| crop_conf | 0.502 | 0.075 | 0.321 | 0.088 |
| uniform | 0.197 | 0.030 | – | – |
| location prior (GT) | **0.615** | 0.113 | – | – |

oracle IoU는 0.146입니다. question-swap U는 C_blur 0.280, D_blur 0.308입니다(18조합).

**사전 진행 기준**

| 기준 | 판정 | 근거 |
|---|---|---|
| 1 | **FAIL** | C_blur U 0.511이 위치 prior 0.615 + 0.05에 못 미침. IoU도 0.084로 D_blur 0.085보다 낮음 |
| 2 | **FAIL** | D보다 U가 개선된 영상이 1/9. self − image-swap = 0.123은 조건 충족 |
| 3 | **FAIL** | S 0.201이 기준 0.204에 0.003 모자람 (D·crop 중 높은 쪽보다 0.097 높음, 요구는 0.10) |
| 4 | PASS | C_mean 0.518 ≥ D_mean 0.466, crop 0.502 |

**해석**
- C와 D는 20조합 중 17개에서 같은 tile을 골랐습니다. 공통 반응을 빼도 선택이 거의 바뀌지 않았습니다.
- 바뀐 3건은 개선 1건(06 Atelectasis), 악화 1건(04 Pulmonary fibrosis), 둘 다 U=0인 1건입니다.
- fp32-head 민감도 분석에서도 기준 1–3은 FAIL로 같습니다.
- 다른 질문 하나를 뺀 C_blur의 U는 0.447–0.572 범위입니다. 주결과는 교체하지 않았습니다.

**측정 검증**
- teacher-forced와 fast scoring의 차이는 최대 7.3e-7로 1e-3 기준을 통과했습니다. 반복 scoring 차이는 0입니다.
- 입력은 모두 896×896이고 prompt 잘림은 없습니다.

결과 파일: `research/results/iter_004/report.md`, `metrics.json`, `eval_table.md`, `selections.json`, `predictions.jsonl`, `verification.jsonl`, `overlays/`(20장), `cpu_tests.json`

# Problems
- **Greedy 생성과 제한된 Yes/No scoring이 다릅니다.**
  - 생성 12개 중 8개가 "Based on the ... chest X-ray"로 시작했습니다. 이 중 m>0인 경우가 2개 있습니다.
  - 전체 1,680 요청의 top-1 token은 "Based" 1,242, "Yes" 429, "No" 9입니다.
  - P(Yes)+P(No)의 중앙값은 0.163이고, 74%의 요청에서 0.5 미만입니다.
  - 따라서 이 prompt에서 margin은 모델의 실제 답변이 아니라, 두 후보 token 사이의 조건부 선호입니다. 측정 타당성에 대한 우려로 기록합니다.
- **`n_image_tokens` 필드가 잘못 기록됐습니다.** 저장값 1은 `proc.image_token_id`가 가리키는 boi token(255999)을 센 것입니다.
  - 실제 soft token 256개는 CPU processor로 따로 확인했습니다.
  - scorer 코드는 고쳤지만 이번 predictions의 해당 필드는 그대로 남아 있습니다. margin 값에는 영향이 없습니다.
- bf16 logits 양자화 때문에 argmax 동점이 11건 있었습니다(D·crop 계열, 가장 작은 tile ID 선택 규칙 적용). fp32 head로 계산하면 0건입니다.
- 계획 대비 추가 요청은 없습니다. 기존 iter_003 코드는 저장소에 없어 새로 작성했습니다.
- CPU 검증용 합성 이미지와 `budget_test.json`이 `results/iter_004/cpu_test/`에 남아 있습니다(`rm` 권한 없음).
- git status는 실행하지 않았습니다.

# Recommendation to GPT
- 사전 기준 1–3이 FAIL이므로, 계획대로 질문 간 contrastive occlusion 선택(C)의 조정을 멈추십시오. 결과가 C와 D의 선택 17/20 일치여서 계수나 질문 bank를 바꿔도 이득이 작을 것으로 봅니다. 이는 추정입니다.
- 모든 방법이 GT 위치 prior(0.615)보다 낮았습니다. MedGemma 1.5의 제거 반응이 담는 영역 정보는 이 자료에서 해부학적 위치 prior를 넘지 못합니다. 이를 "모든 질문 조건부 grounding의 불가능성"으로 일반화하지는 마십시오.
- 더 근본적인 관찰은 생성과 scoring의 불일치입니다. 이 CXR prompt에서 모델은 대부분 Yes/No 대신 설명문으로 시작하고, 후보 token 확률 질량이 작습니다.
  - 후속 과제 후보 1: prompt 형식이 margin의 신뢰도에 주는 영향을 측정합니다.
  - 후속 과제 후보 2: answer-mass 조건부 분석, 즉 P(Yes)+P(No)가 큰 요청만으로 선택 품질이 달라지는지 봅니다. 이 경우 사후 분석임을 명시해야 합니다.
- 다음 방향에서도 고정 3×3 tile의 oracle IoU(0.146) 한계를 고려해야 합니다. CheXlocalize 등 독립 자료는 방향을 다시 정한 뒤 취득 조건을 확인하십시오.

SELF_CHECK: FAIL
SUMMARY: VinDr 10영상 1,680요청(11.3 device-min)을 끝까지 실행했고 scoring 검증(teacher-forced 차이 7e-7, 반복 0)도 통과했지만, contrastive 선택 C_blur(U 0.511)는 raw-D(0.499)와 선택이 17/20 같고 GT 위치 prior(0.615)보다 낮아 사전 기준 1–3이 FAIL이다. 또한 greedy 생성이 8/12에서 Yes/No가 아닌 설명문으로 시작해 margin의 타당성에 우려가 있다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git -C /SSD1_1TB/home/milab/daniel/08_medgemma/research ls-files
