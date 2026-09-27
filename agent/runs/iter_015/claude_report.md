# 요약

- **핵심 결과:** D36 형식 gate는 plain·JSON 모두 실패했다. 계획의 사전 규칙에 따라 primary QA 형식이 없어서 E180 QA, E600 확대, seed 재현은 실행하지 않았다.
- **근거:** 실제 MedGemma 출력 D36 기준으로 plain의 Q_A valid rate는 M0 97.2%, B0 80.6%, C 72.2%다. JSON은 Q_O가 52.8/19.4/16.7%, Q_A가 97.2/2.8/8.3%다(M0/B0/C 순). 형식 실패 원문을 보면 적응 모델은 Q_A에 "Normal"이라는 단어로 답하거나 JSON 지시를 무시하고 bare yes/no로 답했다.
- **미검증·주의:** 시각 능력 저하 여부와 target 구분 능력은 판정하지 않았다. 본 QA 실험(H1–H3)은 미실행이다. D36의 사후 lenient 수치는 12명/category라 결론으로 쓰지 않는다.
- **다음:** GPT가 형식 실패를 어떻게 다룰지 정해야 한다. 아래 Recommendation을 참고한다.

# Work Performed

- **반입 검증:** 16개 파일의 `git hash-object`가 reuse_manifest blob과 모두 일치하고 import도 통과했다.
- **신규 모듈:** `rsna_diag/`에 아래 모듈을 추가했다.
  - `qa_spec`: 질문·parser·정답 mapping
  - `qa_data`: 원본 Calculated label audit, 고정 split, 정답 없는 일반 manifest
  - `qa_requests`: 요청 행렬과 request_id
  - `qa_protocol`: 필수 파일 누락을 거부하는 잠금
  - `qa_gen`: request 단위 worker
  - `qa_run`: 실행기
  - `qa_eval`, `qa_report`, `qa_reuse`, `qa_pilot`
- **모델 로더·LoRA·run_request:** 기존 코드를 그대로 재사용했다. 새로 만든 부분은 요청 식별, 재개 검증, claim, GPU 검사다.
- **iter_012의 M0/B0 concise bbox 출력:** provenance를 검증한 뒤 E600 환자 600건씩 재사용했다.

# Files Changed

- **신규:** `rsna_diag/qa_*.py` 9개, `test_rsna_iter015.py`, `test_rsna_iter015_gpu.py`.
- **결과:** `results/iter_015/` 전체. 기존 파일은 수정하지 않았다.
- **미변경 범위:** 반입 16개 파일은 수정하지 않았고, `lock_protocol.py`도 그대로다. 필수 파일 누락 거부는 새 `qa_protocol.py`에서 처리한다.

# Commands / Experiments

- **`python -m rsna_diag.qa_data`:** 성공. 원본 Calculated label 대비 1,200명의 category와 bbox 수를 대조했고 문제는 0건이다.
- **`python test_rsna_iter015.py`:** 57/57 통과.
- **`python test_rsna_iter015_gpu.py`:** 7/7 통과. SIGKILL 후 잘린 줄은 거부되고, `--repair-tail` 재개는 성공했다.
  - 72개 요청이 중복 없이 완료됐고, 기존 record는 그대로 유지됐다.
- **1 vs 2 worker/GPU pilot(48요청):** 그리디 토큰이 전부 일치했다. 요청 수도 같다.
- **D36 실행:** `d36_plain` 3×72, `d36_json` 3×72, `d12_bbox` 24요청. 모두 rc=0이다.
- **D12 evidence 구현 확인:** `d12_evidence` 72요청, rc=0.
- **E180 C bbox:** `e180_bbox` 180요청, rc=0, wall 185초.
- **중간에 재잠금:** `qa_run.py`에 `--poll-s` 인자를 추가했다. 그 결과 protocol이 무효가 되어 `d36_v2`·`pilot48_v2` protocol을 새로 만들고 pilot을 다시 돌렸다. 이전 protocol 파일과 `gen_pilotA` 출력은 삭제하지 않고 남겼다.

# Results

- **split 구성:** D36은 validation에서 12명/category, E180은 confirm에서 60명/category, E600은 200명/category다. D36과 E600 사이에 환자·pixel hash 교집합은 0이다. P180은 category 앞 60명이라 E180과 같은 집합이다.
- **worker 구성 선택(D36 pilot 기준):** GPU당 2 worker(총 4)를 채택했다.

  | 구성 | 그리디 토큰 | 생성 시간 합 | GPU peak 사용 |
  |---|---|---|---|
  | GPU당 1 worker | 기준 | 48.8초 | 약 8.9GB |
  | GPU당 2 worker | 일치 | 33.7초 | 약 17.8GB / 24.5GB |

  - 생성 시간이 1.45배 빨라졌다.
  - 이 pilot은 모델 로딩 시간이 지배적이라 처리량 추정으로는 거칠다. 안전 확인에는 충분하다고 판단했다.
  - worker당 peak 9GB에 2GB 여유를 더해도 용량 안이다.
  - 실측: E180 C bbox 180요청이 4 worker로 185초(로딩 포함)였다.
- **D36 형식 gate** (`results/iter_015/d36/format_decision.json`): 위 요약 수치와 같다. 정답 정확도는 gate에 쓰지 않았다.
- **E180 concise bbox** (`results/iter_015/e180/report.json`, positive 60명):

  | | F1@0.3 | F1@0.5 |
  |---|---|---|
  | M0 | 0.072 | 0.008 |
  | B0 | 0.719 | 0.406 |
  | C | 0.690 | 0.411 |

  - C−B0의 F1@0.3은 −0.029, 95% CI [−0.091, +0.031]이다.
  - B0−M0의 F1@0.3은 +0.647, 95% CI [0.539, 0.750]이다.
  - B0 bbox+규칙에서 NoOpacity/NotNormal 60명 중 17명은 비어 있지 않은 bbox를 냈다(box 없이 Q_A를 판단할 수 있는 coverage 0.283).
  - 이 bbox 결과는 개발 자료다.
- **D12 evidence 구현 확인:** 72요청이 모두 valid였다. predicted 원천은 valid_nonempty 8건, valid_empty 16건이다. 정확도는 해석하지 않았다.
- **D36 사후 lenient 수치** (사후 서술이며 primary가 아님): NoOpacity/NotNormal 쌍 정확도가 M0/B0/C 모두 8–17%였다. n=12라 결론이 아니고 가설 후보로만 남긴다.

# Goal Progress / Reused Assets

- **목표 진전:** 이 실험은 target 구분 능력을 측정하기 전에 출력 형식 계약(plain·JSON yes/no)이 적응 모델에서 깨진다는 것을 확인했다. 이번 설정에서는 QA 비교 자체가 형식 실패에 가려진다.
- **미검증:** target 구분 능력(H1–H3), 모듈형 evidence 효과(H4), seed 재현, E600은 모두 미검증이다. limitation 상태는 갱신하지 않았다.
- **재사용:**
  - 반입 16개 파일은 blob 일치와 import 검증만 했다. 실행기 전체를 승인한 것은 아니다.
  - iter_012의 M0/B0 concise 출력은 revision, adapter, prompt, config, protocol, 영상 hash로 검증했다. 과거 protocol을 새 코드로 재검증한 것은 아니다.
  - 새 protocol과 request 경로는 이번 반복의 fixture와 실제 실행으로 검증했다.

# Problems

- **현재 결론 무효:** 없다.
- **판단 필요(blocking 아님):** 형식 gate 실패의 처리 방침. Q_A가 "Normal" 단어로 답하는 것을 허용할지, 질문 문구를 바꿀지, 답 형식 보존을 별도 문제로 볼지는 GPT가 새로 사전 등록해야 한다. 나는 사후에 기준을 바꾸지 않았다.
- **추후 개선:** pilot이 짧아 긴 base 출력에서의 4 worker 처리량은 재측정하지 않았다. QA 출력은 짧아서 이번엔 영향이 작았다.

# Recommendation to GPT

- **다음 단계:** 형식 문제가 먼저다. 시각 능력 저하로 해석하지 말고, 사전 등록한 하나의 형식 보정(예: "Normal"·"Abnormal" 응답 허용, 또는 첫 토큰을 yes/no로 제한하는 scoring)을 새 plan으로 세워라.
- **사전 등록 시 주의:** D36과 E180은 이미 관찰에 쓰였으니 개발 자료로 표시하고, 확인은 E600 나머지나 reserve로 분리해야 한다.
- **재사용 가능한 자산:** 이 반복에서 검증한 요청·재개·GPU 검사 경로와 D12 evidence 요청은 그대로 쓸 수 있다.

SELF_CHECK: FAIL
SUMMARY: 새 QA 요청·재개·GPU 검증 경로를 구현·검증했고(CPU 57/57, GPU 재개 7/7), D36 형식 gate가 plain·JSON 모두 실패해 사전 규칙대로 E180 QA·E600은 실행하지 않았다(본 가설 H1–H4 미검증, E180 C bbox와 D12 evidence 구현 확인만 실행).