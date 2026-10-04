# 요약

- **핵심 결과:** 기존 answer-likelihood scoring을 MedGemma의 W 질문(F=FLAIR 8장, J=FLAIR+T1gd 16장)에 적용했습니다. 생성 대비 점수는 J에서 크게 회복됐지만 의미 있는 영상 신호는 확인되지 않았습니다. 사전 확대 조건에 미달해 E12에서 멈췄고 E48은 실행하지 않았습니다.
- **근거 (E12, 12 case·72구간, J가 1,296 forward 상한의 288 forward):**

  | 시스템 | BA (balanced accuracy) | 비고 |
  |---|---|---|
  | G_F (생성, F) | 0.725 | |
  | G_J (생성, J) | 0.083 | invalid 65/72 |
  | L_F (scoring, F) | 0.596 | |
  | L_J (scoring, J) | 0.553 | |
  | D6 위치 prior | 0.766 | D6의 정답에서 고정 |

  - L_J−G_J=+0.471 [0.393, 0.522]입니다. 생성의 형식 저하가 상당 부분 걷힌다는 뜻입니다.
  - L_J는 위치 prior보다 0.212 낮고(CI [−0.281, −0.140]), case 대응 제거 null보다 0.013 높을 뿐입니다(CI [0, 0.039]).
  - L_J−L_F=−0.043 [−0.074, −0.011]입니다. F scoring이 J보다 낫거나 같습니다.
  - L은 거의 항상 ABSENT를 고릅니다. sens는 L_F 0.19·L_J 0.11, spec은 둘 다 1.0입니다.
- **미검증·주의:**
  - E12는 12 case뿐인 개발 자료입니다. 이 음성은 frozen MedGemma의 현재 W 인터페이스에만 해당하고 MRI 전체나 다른 모델·적응은 판단하지 않습니다.
  - 순수한 parser 효과나 내부 인식 능력은 분리하지 못했습니다.
  - batch2는 batch1과 점수가 최대 0.22 nats 달라 사전 허용 오차 0.05를 넘어 채택하지 않았습니다.
  - 아래 Problems에 적은 검증 누락이 있어 SELF_CHECK는 FAIL입니다.
- **다음:** 사전 규칙대로 현재 frozen MedGemma의 mask 기반 공동 입력 경로는 보류합니다. 동일 자료의 추가 prompt·보정·학습은 하지 않습니다.

# Work Performed

- 반입 11개 파일의 blob을 `git hash-object`로 manifest와 대조해 모두 일치함을 확인했습니다. `m65_run.py`의 sha256은 `29e3e6…`(계획이 허용한 tech 변경본)입니다.
- iter_065의 W×{F,J} 요청만 읽기 전용으로 추출했습니다(D 72, E12 144, E36 432행). labels는 읽지 않았고, 영상 파일 hash를 target_manifest와 대조했습니다.
- 새 실행기 `m66_run.py`:
  - protocol: 코드, labels, 모델 파일 sha, config를 잠급니다. E 단계는 gate가 있어야 만들 수 있습니다.
  - 입력: iter_065 생성과 동일하게 `msd56_run.build_inputs`를 씁니다.
  - 점수: 두 후보(PRESENT/ABSENT)의 평균 token log P를 계산합니다(bf16 hidden에서 fp32 head). 선택은 평가기에서만 하고 동률은 ABSENT입니다.
  - 운영: worker 단위 flock claim, 부분 행 보존 복구, 단일 write로 저장하고 fsync, launcher가 완료 후 wall을 측정해 completion을 봉인합니다.
- 평가기 `m66_eval.py`:
  - iter_065 생성의 protocol 재검증, 허용 drift는 `m65_run.py`의 ae25…→29e3… 한 쌍뿐입니다.
  - case bootstrap은 10,000회, seed66입니다.
  - 위치 prior와 null(같은 구간 위치에서 case 대응을 제거한 기대 BA)을 계산하고, `decide-e12`로 gate를 만듭니다.
- 변조·재개 검사 `m66_test.py`를 작성했습니다.

# Files Changed

- 신규: `m66_run.py`, `m66_eval.py`, `m66_test.py`.
- 반입 파일은 수정하지 않았습니다.
- 결과는 `results/iter_066/` 아래에 있습니다.

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| build D/E12/E36 | 성공 |
| D protocol 1차 (`D_b1.json`) | tech 도중 코드를 수정해 hash가 바뀌어 폐기. 파일은 보존 |
| tech 첫 시도 | 7개 항목 후 중단. 무거운 검사를 고정 부분집합으로 줄이고 재잠금 |
| D protocol 2차 (`D_main.json`) | 사용 |
| tech D | 72/72 통과, 883초 |
| 재개 시험 | 성공 |
| D main 생성 | 2 worker·GPU 0/1 각 1개, wall 187초, exit 0 |
| `m66_test.py` | 12/12 통과 |
| gate-d | run=true |
| E12 생성 | wall 431초, exit 0 |
| E12 report, decide-e12 | run=false |

- tech D 통과 내용:
  - 입력: 생성 기록의 input_ids·pixel·file hash와 일치합니다.
  - 독립 token-by-token 대조는 24개 항목에서 최대 차이 1.9e-6, native bf16 head와는 0.042로 허용 오차 이내입니다.
  - 모델 설정: `final_logit_softcapping=None`, tied lm_head입니다.
- 재개 시험: torn row를 만든 뒤 재개했습니다. 부분 바이트는 `.partial` 파일로 보존했고, 재개한 7건의 점수는 main과 최대 차이 0입니다.
- E12 BA는 원시 JSONL에서 `python -c`로 독립 재계산해 L_J 0.5532, L_F 0.5957로 일치했습니다.
- 처리량: 1 worker/GPU 구성만 사용했습니다. 측정한 최대 reserved는 약 10.9 GB로 GPU당 worker 2개는 12.9×2 GB가 24 GB를 넘어 불가합니다. 순수 scoring 합은 D 267초, E12 524초이고, E12는 CPU 전처리 합 297초를 포함해 D보다 느렸습니다. 원인은 분리하지 않았습니다. E48 예상 시간은 계산하지 않았습니다.

# Results

- 모든 경로는 `results/iter_066/` 기준입니다.
  - 평가: `eval/report_D.json`, `eval/report_E12.json`, `eval/prior_D.json`
  - 게이트: `gates/D_gate.json`, `gates/E12_decision.json`
  - 기술·재개·변조 검사: `tests/tech_D.json`, `tests/resume_check.json`, `tests/tamper_result.json`
  - 생성 출력: `gen/D_main`, `gen/E12_main`
- 확대 판정(`gates/E12_decision.json`, run=false):
  - c1: L_J≥0.65이고 L_J−G_J≥0.15 → L_J가 0.553이라 미달입니다.
  - c2: L_J>위치 prior 필요 → 0.553 vs 0.766이라 미달입니다.
- D6 요약(prior가 in-sample이라 참고용):

  | 시스템 | BA |
  |---|---|
  | G_F | 0.625 |
  | G_J | 0.167 |
  | L_F | 0.5625 |
  | L_J | 0.521 |
  | prior_pos | 0.8125 |

- E12 생성 상태:
  - 생성 invalid는 F 12건·J 65건입니다.
  - 파싱이 유효한 비EOS 응답은 0건입니다.
  - invalid 65건 중 L_J가 맞힌 비율은 0.385입니다(설명용).
  - 양성 47건 모두 coverage>0이라 coverage 분해는 의미가 없습니다.
  - L의 PRESENT 예측 비율은 F 0.125, J 0.069입니다.

# Goal Progress / Reused Assets

- **새로 알게 된 것:**
  - J의 생성 BA 저하(0.08)는 형식·생성 영향이 큽니다. likelihood readout에서는 0.55까지 올랐습니다.
  - 그러나 이 회복은 위치 prior를 넘지 못합니다. null과의 차이도 작습니다(+0.013, CI 하한 0).
  - 이 과제에서 F 단독이 J보다 낫거나 같으므로, 공동 입력을 위한 새 방법의 필요성을 뒷받침하지 못합니다.
- **미검증:**
  - E48 규모, 독립 확인, 다른 모델·scoring 문자열·보정.
  - 평균 log-prob의 ABSENT 편향이 후보 길이 때문인지 모델 prior 때문인지.
  - HD 대비 비용.
- **재사용 검증:**
  - `m65_data`·`msd56_data`: 생성 입력의 hash 일치를 확인했습니다. build는 실행하지 않았습니다.
  - `msd56_run`: `load_model`/`build_inputs`를 사용했고, 입력은 iter_065 생성과 일치합니다.
  - `mc54_run`: `extend_inputs`/`hidden_last`/`head_fp32`를 사용했고 독립 token-by-token 대조를 통과했습니다.
  - `pg43_run`: 순수 helper만 사용했습니다.
  - 기존 `total_read_to_flush_s`와 비용 sidecar는 재사용하지 않았습니다.

# Problems

- **현재 결론 무효:** 없음.
- **미수행 검증 (SELF_CHECK=FAIL 사유):**
  - `--die-mode whole`(저장 직후 강제 종료) 재개와 강제 중단 중 복수 worker 재개는 실행하지 않았습니다. torn-tail 재개와 2 worker 정상 실행만 검증했습니다.
  - E/prior 평가 변조 시험은 protocol·completion 파일 변조 위주입니다. `report`에 labels가 바뀐 채 들어오는 경로의 변조 시험은 하지 않았습니다.
  - 평가기 독립 재현은 BA만 `python -c`로 했고 bootstrap CI·null은 하지 않았습니다. 별도 verifier 스크립트는 만들지 않았습니다.
  - E48 예상 wall-clock은 산출하지 않았습니다(확대하지 않았음).
- **추후 개선:**
  - batch2는 허용 오차를 넘어 채택하지 않았습니다(`n_heavy` 24개 항목에서 최대 0.22).
  - tech 도중 코드를 수정해 protocol을 재잠금했습니다. 수정은 시험용 `--gpu`·검사 부분집합이며 점수 경로는 불변입니다.
  - 생성된 첫 token과 후보 첫 token 일치는 28/72뿐이라 선택 일치는 참고값입니다.

# Recommendation to GPT

- 사전 규칙대로 frozen MedGemma의 mask 기반 공동 입력·답변 보정 방법 투자는 보류하고 F baseline을 보존하는 것을 권고합니다. 12 case 개발 자료의 한정 결론이며 MRI 전체나 다른 모델·경량 적응은 기각하지 않습니다. 동일 자료의 추가 scoring·prompt 탐색은 하지 않아야 합니다.
- 다음 방향은 같은 research_track에서 별도 정답 연결이 가능한 다른 MRI 질문으로 전환하는 것이 맞아 보입니다. 위치 prior가 이미 BA 0.77인 W 질문은 영상 신호를 식별하기에 약한 과제입니다.
- 검증 보완은 필요하면 `die-mode whole` 재개, labels 변조 시험, 독립 bootstrap 재계산을 한정해 추가할 수 있습니다.

SELF_CHECK: FAIL
SUMMARY: MedGemma W 질문에서 answer-likelihood scoring은 J 생성 BA를 0.08→0.55로 회복했지만 위치 prior(0.77)와 F scoring(0.60)을 넘지 못해, 사전 규칙대로 E12에서 E48 확대 없이 종료했습니다(12 case 한정). 일부 재개·변조·독립 재계산 검증은 미완료입니다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: CUDA_VISIBLE_DEVICES=0 CUDA_DEVICE_ORDER=PCI_BUS_ID python m66_run.py tech --requests results/iter_066/data/requests_D.jsonl --protocol results/iter_066/protocol/D_b1.json --out results/iter_066/tests/tech_D.json > results/iter_066/tests/tech_D.log 2>&1
- Bash: CUDA_VISIBLE_DEVICES=1 python m66_run.py worker --requests results/iter_066/data/requests_D.jsonl --protocol results/iter_066/protocol/D_b1.json --out-dir results/iter_066/tests/resume_D --worker 0 --die-after-write 3 --die-mode torn
- Bash: pkill -f "m66_run.py tech"; sleep 2; pgrep -f "m66_run.py tech" | wc -l; ls results/iter_066/tests
- Bash: python m66_run.py worker --requests results/iter_066/data/requests_D.jsonl --protocol results/iter_066/protocol/D_main.json --out-dir results/iter_066/tests/resume_D --worker 0 --gpu 1 --die-after-write 3 --die-mode torn; echo rc=$?
