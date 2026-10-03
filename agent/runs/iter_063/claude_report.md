# 요약

- **핵심 결과:** 소견 문단을 삭제하면 두 모델 모두 텍스트만의 정답률(T)이 0.0까지 떨어졌다. 1차 parser 기준 L은 Qwen 0.65, MedGemma 0.55다.
- **영상 이득(G)은 영상 신호로 읽을 수 없다.** 삭제문에서 영상을 주면(J) 정답률이 Qwen 0.10, MedGemma 0.15였다. 이는 최빈 class prior(0.30)보다 낮다.
- **형식 문제가 결과를 좌우한다.** 삭제문 T에서 MedGemma는 20/20이 "ANSWER: N/A/None"이었고, Qwen은 18/20이 굵은 글씨 `**ANSWER: X**`였다. 둘 다 1차 parser(parse_v2)에서 invalid(오답 처리)다.
- **한계와 다음:** 개발 자료 10개 cluster의 탐색이며 확증이 아니다. 영상 충분성·선택·결합 실패는 판정하지 않았다. 현재 key-image QA를 선택·결합 방법 투자의 출발점으로 삼는 것은 보류를 권고한다.

# Work Performed

- 계획 `plan.md`/`plan.json`을 읽고 기존 `q62_run.py`, `mri61_*.py`, `msd56_run.py`, `q62_eval.py`를 확인했다.
- `q63_manifest.py`로 E10(QA 587, 658, 721, 740, 759, 782, 831, 1120, 1224, 1297)과 D2(QA 694, 1253)의 삭제문 요청을 만들었다.
  - 첫 문장(`).`까지)과 `What is the most likely diagnosis for this participant?`는 원문 그대로 두고 그 사이 소견 문단만 삭제했다.
  - 12개 모두 경계 가정(문장 1회 등장, 끝 위치, 구분 공백)이 성립해 중단은 없었다.
  - 삭제 offset·삭제 문자열·원 annotation hash를 manifest에 잠갔다.
  - 원문 T/J 행이 `E21`/`D3` 기존 요청과 필드 단위로 같고, 삭제 외 prompt 차이가 없음을 대조했다.
  - 영상 44개의 hash를 `image_manifest`와 대조했다.
- QA 587/721/782/1120의 영상을 contact sheet로 직접 열람했다(`results/iter_063/audit/`).
  - 파일–사례·순서 연결은 정상이다.
  - 587은 병변이 뚜렷하다.
  - 721과 782의 제공 slice에서는 병변이 눈에 띄지 않는다. 이는 영상 충분성 임상 주석이 아니다.
- `q63_run.py`를 새로 작성했다(Qwen/MedGemma 공용). 보완 사항:
  - 구성요소별 protocol 잠금과 진입 시 재검증.
  - claim 획득 후 최신 완료 상태 재확인.
  - 손상 tail은 `.corrupt_*`로 보존 후 복구, 그 외 JSONL 읽기는 strict.
  - 답변↔비용 대응(rid, attempt_id, answer_sha)과 `cost_missing` 명시.
  - tech gate와 worker 수/GPU 수를 분리한 launcher.
- `q63_eval.py`로 2×2, L/G/I, seed63 10,000회 cluster bootstrap을 계산했다. `q63_verify.py`는 평가기와 parser를 import하지 않고 독립 재계산한다.
- 기존 `q62_run.py`, `mri61_run.py`, `msd56_run.py`와 iter_061/062 결과·protocol은 수정하지 않았다.

# Files Changed

- 신규 코드: `q63_manifest.py`, `q63_run.py`, `q63_test.py`, `q63_eval.py`, `q63_verify.py`
- 신규 결과: `results/iter_063/`
  - `data/`
  - `D2_*`, `E10_*` protocol·tech·jobs
  - `gen_D2_*`, `gen_E10_*`
  - `tests/run_path_tests.json`
  - `eval/report.json`, `eval/report_sensitivity_lenient_format.json`, `eval/verify.json`, `eval/verify_lenient.json`
  - `audit/`
  - `E10_expected_cost.json`

# Commands / Experiments

- `python q63_manifest.py`: 성공 (E10 40건, D2 8건).
- `q63_run.py lock`/`tech`: 모델 2개 × (D2, E10) 모두 성공. tech 불일치(fail)는 0이며 검사 범위는 D2 8건/E10 40건씩이다. 확인 항목:
  - prompt 차이가 삭제 문자열뿐이다.
  - adapter와 공식 직접 호출의 input_ids/pixel_values/grid가 일치한다.
  - J의 영상 tensor가 원문 J와 같다.
  - T에는 영상 token이 없다.
  - 누출 문자열이 없다.
- D2 동작 확인(`launch`): Qwen GPU0, MedGemma GPU1에 각 1 worker를 배정했다. 두 worker 모두 exit 0이고 wall은 107초다. `verify` 문제 0.
- `python q63_test.py`(실제 진입점, MedGemma D2 사본): 전부 통과.
  - 요청·label·model 변조 거부.
  - 마지막 줄 절단 복구와 corrupt 파일 보존.
  - 죽은 pid claim 회수.
  - 재생성 token 일치.
  - `cost_missing` 1건이 표시되고 verify는 통과.
  - 완료 상태에서 두 번째 worker의 신규 생성이 0.
  - 중간 손상 줄은 strict 읽기에서 예외.
- E10 본실행(`launch`): 두 worker 모두 exit 0, wall 392.05초. `verify` 문제 0, `cost_missing` 0.
- `q63_eval.py`(1차, `--lenient` 보조)와 `q63_verify.py`: 독립 재계산과 report의 최대 차이 0.0.

# Results

**자원·처리량**

- 예상 wall은 Qwen ≈480초, MedGemma ≈380초(D2 실측 환산). 실제는 Qwen 392초, MedGemma 353초다.
- peak VRAM은 GPU0(Qwen) 16,397 MiB, GPU1(MedGemma) 9,161 MiB다.
- batch2는 실행하지 않았다. 요청이 모델당 40건뿐이라 절약이 수 분 이하이고, padding·출력 대응 검증 비용이 더 크다고 판단했다. 근거는 `E10_expected_cost.json`에 있다.
- MedGemma 2 worker는 GPU1에 들어가지만 임계 경로가 Qwen이라 wall 이득이 없어 GPU당 1 worker로 했다.

**정확도**

`results/iter_063/eval/report.json`(1차 parser). 정확도는 cluster 평균이며, CI는 cluster paired bootstrap의 95%다.

| 모델 | O_T | O_J | R_T | R_J | L [CI] | G [CI] | I [CI] |
|---|---|---|---|---|---|---|---|
| Qwen | 0.65 | 0.60 | 0.00 | 0.10 | 0.65 [0.35, 0.90] | 0.10 [0.00, 0.25] | 0.15 [0.00, 0.30] |
| MedGemma | 0.55 | 0.35 | 0.00 | 0.15 | 0.55 [0.25, 0.85] | 0.15 [0.00, 0.30] | 0.35 [0.10, 0.60] |

- **사전 기준 판정**
  - Qwen은 L≥0.15는 충족했지만 G≥0.15는 미달이다(0.10). "텍스트 의존만 관찰"에 해당한다.
  - MedGemma는 모든 기계적 기준을 충족해 탐색 양성으로 판정된다. 아래 이유로 이 양성은 영상 신호의 근거가 아니다.
- **G·I의 형식 의존성 (invalid 비율)**

  | 모델 | 조건 | invalid |
  |---|---|---|
  | MedGemma | R_T | 20/20 |
  | Qwen | R_T | 18/20 |

  - 이 때문에 R_T 정확도 0.0은 "틀린 답"이 아니라 "답하지 않음/형식 위반"이다. 그래서 L과 G의 상당 부분은 형식·거절 효과다.
  - 나머지 조건(O_T, O_J, R_J)의 invalid는 0이다.
  - MedGemma R_T는 20건 모두 invalid라, 유효 응답만으로 L·G를 따로 계산할 수 없다.
- **R_J 답변 분포 (최빈 class prior 0.30)**
  - R_J 정확도는 Qwen 0.10, MedGemma 0.15로 prior보다 낮다. 답이 한 class로 쏠렸다.
  - Qwen은 Infarction 9, Leukoencephalopathy 9로 답했다.
  - MedGemma는 Leukoencephalopathy 13으로 답했다.
- **사전 정의한 형식 민감도** (`--lenient`, 굵은 글씨 `ANSWER`를 허용, iter_062와 동일 정의)

  | 모델 | 결과 |
  |---|---|
  | Qwen | R_T가 0.10으로 올라 G=0.00 [-0.20, 0.20], I=0.05가 된다. 탐색 양성도 아니다. |
  | MedGemma | 변화 없음(문장이 `N/A`/`None`이라 여전히 invalid). |

- 방향성은 안정적이다. L>0 cluster는 Qwen 7, MedGemma 6이고 음수는 0이다. 순서 F/R 각각에서도 L>0이다.
- 원문 T/J 대조: MedGemma는 O_T 0.55 > O_J 0.35로 영상 추가 시 하락했고, Qwen은 0.65와 0.60이다. 이는 iter_062의 "영상 추가 효과 불확정"과 같은 방향이다.
- source별 값은 기술통계(n=2–3)이며 해석하지 않는다.

# Goal Progress / Reused Assets

**목표 진전**

- 질문의 소견 서술은 이 과제의 텍스트 정답률(O_T 0.55~0.65)을 크게 떠받친다(L 0.55~0.65).
- 소견을 지우면 두 모델 모두 영상만으로는 class prior 이하이고, J 답변은 한 class에 쏠린다.
- 이는 "원문의 영상 이득 부재가 텍스트 소견 때문"이라는 설명과 양립하지만, 영상이 정보를 못 줬다는 점(R_J 쏠림)은 그대로 남는다.

**투자 결정 (계획의 종료 규칙 적용)**

- Qwen은 "텍스트 의존만 관찰"이다.
- MedGemma의 기계적 양성은 refusal artifact 때문에 영상 근거 후보로 격상하지 않는다.
- 따라서 현재 key-image QA를 선택·결합 방법 개발의 출발점으로 삼는 투자는 보류를 권고한다.
- 보류 범위는 이 BraTS/ISLES key-image QA에 한정한다. MRI 전체나 모델의 인식 능력을 기각한 것이 아니다.
- 재개 조건은 영상 충분성을 독립적으로 연결하는 새 근거(원천 volume 등)다.

**재사용 자산**

- `mri61_spec.py`와 `mri61_parse.py`는 변경 없이 사용했다. protocol에 hash를 잠갔고 tech에서 prompt·tensor 동일성을 재확인했다.
- `msd56_run.py`의 `load_model`, `env_info`는 MedGemma 경로에서 변경 없이 사용했다.
- Qwen의 입력·로딩은 `q62_run.py`의 경로를 복사해 새 파일에 구현했다. `q62_run.py`는 import하지 않았다.
- 원문 T/J 출력은 iter_062 Qwen과 iter_061 MedGemma E24의 기존 protocol과 verify seal을 검증한 뒤 재사용했다.

# Problems

- **현재 결론 무효:** 없음.
- **해석 제약 (결론의 범위)**
  - 삭제문 T는 사실상 정답 가능한 정보가 없는 조건이다. 모델의 "답하지 않음"은 합리적 반응이며, 이를 능력 저하로 읽으면 안 된다.
  - parser를 사후에 바꾸지 않았다. lenient 결과는 보조이며, MedGemma의 `N/A` 거절은 lenient로도 구제되지 않는다.
  - 10개 cluster는 구조적 선택이고 source와 class가 얽혀 있다. 개발 자료이며 독립 확인이 아니다.
  - 721과 782의 제공 slice에서는 병변이 눈에 띄지 않는다. 소견 삭제 후 영상 충분성이 낮을 가능성이 있다.
- **재사용 전 필요:** `q63_run.py`는 모델별 단회 실행용이다. 이번 실행에서 확인한 범위는 위 `q63_test.py` 항목이다. 이 범위 밖의 stress(다중 worker 경합 등)는 검증하지 않았다.
- **추후 개선(선택):** `q63_eval.py`에 사용하지 않는 `if False` 분기가 남아 있다. 결과에는 영향이 없다.

# Recommendation to GPT

- 이 key-image QA의 선택·결합 방법 투자는 보류를 권고한다. 근거는 (1) 삭제문 영상 정확도가 prior 이하이고, (2) 양성 판정이 형식·거절로 설명되며, (3) 일부 사례의 제공 slice에 병변이 보이지 않는다는 점이다.
- 계속한다면 새 prompt나 표본 확대가 아니라 관측 충분성이 연결된 자료(MR-RATE 일부 study 등, 접근 권한 확인 필요)에서 같은 2×2를 보는 쪽이 판별력이 있다.
- 삭제문에 별도 응답 형식(예: 5개 선택지 강제)을 쓰는 변형은 이번 사전 계획 밖이다. 하려면 새 계획으로 정해야 한다.

SELF_CHECK: PASS
SUMMARY: 소견 삭제 시 두 모델의 텍스트 정답률이 0.0으로 하락(L 0.55~0.65)했으나 이는 대부분 거절·형식 invalid이고, 삭제문 영상 정답률은 prior 이하(Qwen 0.10, MedGemma 0.15)라 영상 이득은 확인되지 않았다. 현재 key-image QA 방법 투자는 보류를 권고한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: CUDA_VISIBLE_DEVICES=1 python q63_test.py 2>&1 | tail -30
