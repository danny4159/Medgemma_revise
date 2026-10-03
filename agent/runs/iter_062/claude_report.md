# 요약

- **핵심 결과:** 적격 E21(21 cluster, 232요청)에서 Qwen2.5-VL-7B와 기존 MedGemma 모두 영상 추가 효과가 사전 기준에 미달했다. 판정은 불확정이다.
- **근거:** Qwen은 T 0.524, J 0.500, V 0.524이고 J−T −0.024 [−0.214, 0.167], V−T 0.000 [−0.167, 0.167]이다. MedGemma는 T 0.476, J 0.429, V 0.405이다. 모델 간 효과 차이도 CI가 0을 포함한다.
- **미검증·주의:**
  - 공동 손실(V−J, S_mean−J) 후보는 어느 모델에서도 관찰되지 않았다.
  - E21은 MedGemma 결과를 본 뒤 정한 개발 자료다. 독립 확인이 아니며 표본이 작다.
  - Qwen의 J−T와 V−T CI 상한이 10 pp 이상(0.167)이어서 "큰 효과 없음"의 사전 음성 기준도 충족하지 못했다.
- **다음:** 기준 모델 교체나 통합 방법 투자의 근거는 없다. 이 key-image 과제는 보류를 권고한다(아래 Recommendation 참조).

# Work Performed

- 기준 계획 SHA(`e310aa2f…`)와 HEAD(`84f865b`)를 확인했다. 유지·변경·미완료는 계획과 같다.
- E21 manifest를 구성했다. QA 2322·1419·2033을 제외했고 소견 미서술 6 / 서술 15를 출력 전에 고정했다. `mri61_spec.build_rows`로 재구성한 232행이 iter_061 E24 행과 완전히 같음을 검증했다. 이 덕분에 MedGemma 기존 출력을 재생성 없이 재사용했다. D3(QA 694·1518·1253)는 34요청이다.
- Qwen2.5-VL-7B-Instruct를 별도 캐시에 확보했다(15.46 GB, 14개 파일 sha256 기록). `qwen-vl-utils`와 `torchvision`은 `--target` 경로에 설치했고 기본 medgemma 환경은 수정하지 않았다.
- 새 runner `q62_run.py`(lock/worker/launch/verify/tech)에 구현한 항목:
  - 구성요소별 protocol 잠금과 모든 진입점 재검증
  - launcher flock과 요청 claim(O_EXCL)
  - 손상 tail 보존 후 복구
  - worker 수와 GPU 수 분리
  - nvidia-smi 기반 admission
  - flush 포함 timing sidecar
- 평가기 `q62_eval.py`, 독립 재계산 `q62_verify.py`, 회귀 `q62_regress.py`, 형식 민감도 `q62_sens.py`를 작성했다.
- 지시 위반 없이 코드 오류 1건을 고쳤다. cost sidecar가 `worker*.jsonl` glob에 잡히는 버그로 D3를 한 번 돌린 뒤 발견했다. sidecar 이름을 바꾸고 D3를 새 코드로 다시 실행했다. 첫 실행은 `results/iter_062/superseded_v0/`에 보존했다.

# Files Changed

신규(모두 `research/`):

- 실행·평가: `q62_run.py`, `q62_eval.py`, `q62_verify.py`, `q62_sens.py`
- 준비·검사: `q62_manifest.py`, `q62_fetch.py`, `q62_regress.py`, `q62_test.py`, `q62_resume_test.py`

기존 파일은 수정하지 않았다. `mri61_run.py`를 그대로 둬서 E24 provenance 회귀가 가능하다. 결과는 `results/iter_062/`에 저장했다.

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `q62_manifest.py` | 성공. E21 232요청(T/J 84, S 148), 영상 74개, 영상 file hash 전부 일치 |
| `q62_fetch.py` | 성공. 약 20분 |
| `q62_regress.py` | 통과. E24 protocol digest 재계산 일치, T 0.5·J 0.4375·V 0.4375 재현 |
| `q62_test.py` (CPU) | 통과. requests·labels·image·code/parser 변조 차단, claim 원자성, stale claim 인수, 손상 tail 보존 |
| D3 tech | 통과. fails 0 (34 입력 + 22 S⊂J slice + 17 순서 쌍) |
| D3 생성 | 통과. 34/34 완료, 종료코드 [0,0], 약 80초 |
| `q62_resume_test.py` | 통과. 8건 완료 후 SIGKILL과 torn line 주입, 2 worker로 재개. 최종 34건, 누락 0, 중복 0, 손상 원본 1개 보존, 기준 실행 대비 token 불일치 0/34 |
| E21 tech | 통과. fails 0 (232 입력 + 148 slice + 116 순서 쌍), 최대 1,632 token |
| E21 생성 | 통과. 232/232, 종료코드 [0,0], 468초 |
| `q62_run.py verify` | 통과. 문제 0 |
| `q62_eval.py` | 성공 (처음 한 번 `crit` 키 오타로 실패, 수정 후 재실행) |
| `q62_verify.py` | 통과. 41개 값의 최대 차이 0.0 |
| `q62_sens.py` | 성공 (사후 형식 민감도) |

# Results

E21 주분석(cluster 21개, 두 순서 평균, paired cluster bootstrap seed61·10,000회, `eval/report.json`):

| | T | J | S_mean | V |
|---|---|---|---|---|
| MedGemma | 0.476 | 0.429 | 0.377 | 0.405 |
| Qwen2.5-VL-7B | 0.524 | 0.500 | 0.507 | 0.524 |

모델 내 효과(95% CI):

| 효과 | MedGemma | Qwen |
|---|---|---|
| J−T | −0.048 [−0.190, 0.095] | −0.024 [−0.214, 0.167] |
| V−T | −0.071 [−0.215, 0.071] | 0.000 [−0.167, 0.167] |
| V−J | −0.024 [−0.167, 0.095] | +0.024 [−0.071, 0.143] |
| S_mean−J | −0.052 [−0.169, 0.046] | +0.007 [−0.070, 0.102] |

모델 간 효과 차이도 모두 CI가 0을 포함한다.

| 비교 | 추정 | 95% CI |
|---|---|---|
| (J−T)_Qwen − (J−T)_MedGemma | +0.024 | [−0.190, 0.238] |
| (V−T)_Qwen − (V−T)_MedGemma | +0.071 | [−0.167, 0.310] |
| (V−J)_Qwen − (V−J)_MedGemma | +0.048 | [−0.095, 0.214] |

사전 기준의 기계적 평가:

- 모델 특이성 양성: 아니오.
- 공동 손실 후보: 두 모델 모두 아니오.
- 단순 대안 V−J ≥ 5 pp: 두 모델 모두 미달.
- 음성(두 모델 J−T·V−T CI 상한 < 10 pp): 아니오. MedGemma는 충족했지만 Qwen의 상한은 0.167이다.
- 결론은 **불확정**이다.

보조 관찰(기술통계):

- **순서별:**
  - MedGemma는 F/R 순서 모두 J−T가 −0.048이다.
  - Qwen은 F −0.048, R 0.0이다.
- **소견 서술 여부:**
  - 서술 15개에서 Qwen J−T +0.033, V−T +0.067, MedGemma J−T −0.100, V−T −0.133이다.
  - 미서술 6개에서 Qwen J−T −0.167, MedGemma +0.083이다.
  - 방향이 엇갈리는 소표본이라 해석하지 않는다.
- **post-hoc oracle:** any-correct는 Qwen 0.571, MedGemma 0.452이며 기술통계일 뿐이다.
- **순서에 따른 원 선택지 답변 불일치:** Qwen은 T 0.30, J 0.18, S 0.29이고 MedGemma는 T 0.33, J 0.38, S 0.38이다.
- **형식:**
  - Qwen의 사전 parser 무효율은 T 4.8%, J 9.5%, S 2.7%이다. 무효 10건 중 9건은 `**ANSWER: X**`·`Answer: X`처럼 답이 분명한 형식 변이이고, 나머지 1건은 `ANSWER: A` 뒤에 `**`가 붙은 응답이다.
  - 모두 EOS 종료, cap 재시도 0이다.
  - MedGemma는 T 무효율 7.1%이고 T의 cap 재시도율이 43%다.
- **형식 민감도(사후, `q62_sens.py`):** 느슨한 parser를 양 모델에 같은 방식으로 적용하면 Qwen은 T 0.548, J 0.524, V 0.524로 J−T −0.024 [−0.190, 0.119], V−T −0.024 [−0.167, 0.119], V−J 0.000이다. 결론은 달라지지 않는다.
- **비용(Qwen, 입력 읽기부터 flush까지 sidecar 합):**
  - T 187초, J 170초, S 148건 합 545초, 전체 생성 wall 468초(GPU 2장)이다.
  - J의 영상 입력은 영상 1장당 81 token으로 MedGemma 256 token보다 작다.
  - MedGemma 기존 timing은 저장 이전에 끝나므로 직접 비율은 만들지 않았다.
- **자원:** GPU별 peak 약 17.0 GB(실사용 peak_reserved 16.0 GB), 처리량 약 3.6초/요청.

# Goal Progress / Reused Assets

**목표 진전:**

- 직전 음성 관찰(MedGemma에서 영상 추가 효과 없음)은 타 계열 Qwen 한 모델에서도 큰 효과로 나타나지 않았다.
- Qwen 7B가 MedGemma 4B보다 점수가 약간 높지만, T와 J가 함께 높아 기본 과제 적합성 차이로 보인다. 영상 활용 개선의 근거는 아니다.
- 공동 손실 후보(V−J)는 두 모델 모두에서 보이지 않았다.

**미검증:**

- 질문에 이미 소견이 담긴 정도, 영상 정보 충분성, 인식 능력의 분리는 이번 설계로 되지 않는다.
- 독립 표본에서의 재현과 사전학습 노출도 확인하지 못했다.
- Qwen 학습 데이터와의 중복은 미확인이다.
- 세 번째 모델과 직접 SFT 비교는 하지 않았다.

**재사용:**

- `mri61_spec.py`, `mri61_parse.py`는 수정 없이 그대로 사용했다.
- `mri61_data.py`, `mri61_explore.py`, `mri61_sheet.py`는 이번 실행 경로에서 직접 호출하지 않았다. 대신 이들이 만든 iter_061 산출물(`selection_lock.json`, `eligible_qa.json`, `image_manifest.json`, 영상)을 읽기 전용으로 사용했다.
- `mri61_run.py`는 새 파일로 대체했다(원본 불변).
- `msd56_run.py`는 `mri61_run`이 import하므로 회귀 검사에서만 사용했다.

# Problems

- **현재 결론을 무효로 만드는 문제:** 없다.
- **재사용 전 수정이 필요한 문제:**
  - 새 runner는 Qwen 전용이다. 다른 모델에 쓰려면 adapter가 필요하다.
  - tech의 "공식 직접 호출"은 모델 카드 예제를 옮긴 코드와 같은 `qwen_vl_utils` 경로의 비교다. 순수하게 독립된 두 경로의 대조가 아니다.
  - 평가 입력에서 Qwen cost와 MedGemma cost의 경계가 서로 다르다(flush 포함 여부).
  - 의존성이 미설치였던 `torchvision`은 `--target`으로 설치했다. 별도 venv를 만들지 않고 medgemma env를 읽기 전용으로 쓴 구성이며, 버전 충돌은 관찰되지 않았다.
- **추후 개선:**
  - batch2 비교는 하지 않았다. E21 전체가 약 8분이라 절약 효과가 작고, GPU당 2 worker는 peak 약 17 GB 때문에 불가능했다. 이는 처리량 근거에 따른 선택이다.
  - generation은 `do_sample=False`로 호출했지만 checkpoint의 `repetition_penalty=1.05`는 유지했다. 모델 카드 경로를 따른 것이다.
  - 첫 D3 실행은 sidecar glob 버그가 있어 `superseded_v0/`에 보존만 했다.

# Recommendation to GPT

- **권고: 보류.** 현재 OmniBrainBench key-image 과제의 통합 방법 투자와 모델 교체 투자는 근거가 없다. 이 판단은 이번에 검증한 과제와 조건에 한정된다. MRI 인식이나 다중 근거 결합 능력 전체의 기각이 아니다.
- **보류 사유는 효과 부재가 아니라 정밀도 부족이다.** 21 cluster로는 Qwen에 10 pp 이상 효과가 있는지 배제하지 못한다. 그러나 점추정은 0 근처이고 공동 손실 후보도 없다.
- **다음에 결정을 바꿀 수 있는 것은 새 과제 선택이다.** 정답 주석으로 복수 영상 필요성을 구분할 수 있는 volume/sequence 질문(MR-RATE 등 접근 가능성 재확인 필요)이 후보다.
- 같은 E21에서 표본을 늘리거나 세 번째 모델을 추가하는 것은 권하지 않는다. 계획의 종료 조건에 따라 불확정은 보류로 처리했다.

SELF_CHECK: PASS
SUMMARY: 적격 MRI QA 21개에서 Qwen2.5-VL-7B의 T/J/S_i를 실행했다(232요청, 종료코드 0, 독립 재계산 일치). Qwen과 기존 MedGemma 모두 영상 추가 효과가 10 pp 기준에 미달했고 모델 간 차이와 공동 손실 후보는 CI가 0을 포함해 불확정이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: sed -i "s#/worker{a.worker}.cost.jsonl#/cost_worker{a.worker}.jsonl#; s#worker\*.cost.jsonl#cost_worker*.jsonl#g" q62_run.py q62_eval.py
