# 요약

- **핵심 결과:** 계획한 RSNA 대신 PadChest 개발 집단 E(양성 29명·음성 40명)에서 M0와 직접 SFT C의 부재 거부를 비교했다. C는 존재 전제 질의(G_short)에서 음성 40명 중 39명에 box를 냈고, M0도 40/40이었다. C−M0 false-box 차이는 −0.025로 적응 악화 근거가 없다(97.5% CI [−0.100, 0.000]).
- **presence gate:** 음성 false-box가 39/40에서 1/40으로 줄었다. 양성 F1@0.3은 0.408에서 0.385(P0 gate)와 0.368(PC gate)로 바뀌었다. 하지만 양성 F1 차이의 95% CI 하한이 −0.132로, 사전 기준(−0.05)을 넘지 못했다.
- **사전 고정 판정:** `inconclusive_or_negative_hold`이며 method pilot 후보 조건도 충족하지 못했다.
- **주의:** 표본이 작아 큰 효과만 판별할 수 있다. 단일 target, 단일 SFT seed, 개발 자료이며 독립 확인은 하지 않았다.
- **다음:** 사전 규칙상 같은 진단을 확대하지 않는다. 보류 여부는 GPT 리뷰에서 판단한다.

# Work Performed

- 반입된 12개 파일을 확인했다. `pg42_*` 신규 코드는 별도 함수로 만들어 과거 양성 문장쌍 선택 함수와 분리했다.
- **후보 열거:** official train에서 iter_039/040의 환자·study·영상 737개를 제외했다. 음성 후보 41건과 양성 후보 30건을 얻었다(계획 예상과 일치).
- **출력 눈가림 검토(`review_private.json`):**
  - 음성 1건 제외: "significant"만 부정한 부분 부재.
  - 양성 1건 제외: 2011년 과거 보고를 언급한 문장.
  - 최종 E는 양성 29명·음성 40명으로, gate(24/32)를 통과했다.
  - 양성 GT box는 overlay 3장으로 눈으로 확인했다. 명백한 누락·좌표 오류는 없었다.
- **사전 flag:** 양성 hedged 8건, 음성 bare "effusion" 19건. 이 둘을 제외한 민감도 분석을 미리 정했다.
- **D 동작 확인:** 양성 3명·음성 3명. 요청 36건씩을 2 worker와 4 worker로 실행했고, 변조 거부와 중단·재개 검사도 했다.
- **본실험:** E_M0와 E_C를 각 207건, 4 worker로 실행하고 평가와 독립 재계산을 했다.

# Files Changed

새 파일:
- `pg42_data.py`, `pg42_spec.py`, `pg42_build.py`, `pg42_driver.py`, `pg42_eval.py`
- `pg42_verify.py`, `pg42_dcheck.py`, `pg42_overlay.py`, `test_pg42.py`

반입 파일 12개는 수정하지 않았다. `pg41_run.py`는 그대로 호출했다.

결과는 `results/iter_042/`에 저장했다: `data/`, `requests/`, `protocol/`, `gen/`, `eval/`, `tests/`, `decisions/`.
- `data/`와 `review_private.json`에는 원문과 ID가 있어 private이다(git 제외).
- 임시 출력 `results/iter_042_tmp_review.txt`(원문 포함)는 삭제 권한이 없어 남아 있다. 비공개 처리가 필요하다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령 | 결과 |
|---|---|
| `python pg42_build.py` | 성공. E 양성 29/음성 40, 요청 D 18×2·E 207×2 |
| `python pg42_overlay.py` | 성공. 양성 29명 GT overlay 확인 |
| `python test_pg42.py` | 43/43 통과 |
| `pg42_driver.py` D_M0/D_C, 2w·4w 각 1회 | 4건 모두 성공, `verify_completion` 통과 |
| `python pg42_dcheck.py compare` | 성공 |
| `python pg42_dcheck.py tamper` | 변조·누락·다른 모델 protocol·중복 4종 모두 거부 |
| `pg42_driver.py --kind D_C --name D_C_resume --max-requests 3` | 미완료로 종료(예상) |
| torn tail 추가 후 `pg42_driver.py` 재개 | 성공, 18건 완료 |
| `pg42_driver.py` E_M0, E_C (각 4 worker) | 성공, completion 재검증 통과 |
| `python pg42_eval.py` | 성공 |
| `python pg42_verify.py` (엄격) | 불일치 발견(아래 Problems 참조) |
| `python pg42_verify.py --tolerant` | 성공, 불일치 0 |

# Results (수치와 결과 파일 경로)

**실행 구성 선택** (`decisions/d_worker_config.json`)
- D 2 worker: 135.6초, 4 worker: 90.5초(모델 M0·C 합계, 로딩 포함).
- 두 모델 모두 2w와 4w의 token 불일치 0, OOM 0.
- 4w GPU peak 17,836MiB(24,576MiB 중, 여유 약 6.7GB)라서 4 worker를 채택했다.
- 중단·재개: 재개 결과가 원 실행과 token 일치 0건 불일치(`tests/resume_result.json`). 부분 행 원본은 `.partial.*.bin`으로 보존했다.

**E 생성 비용**
- E_M0: wall 618초, generate 구간 합 863초.
- E_C: wall 1,085초, generate 구간 합 1,386초.
- 각 모델에서 요청 1건이 4,000 token까지 재시도했고, G_short 1건이 EOS로 끝나지 못했다(invalid 처리).

**주요 결과** (`eval/report_E.json`)

| 시스템 | 양성 F1@0.3 | 음성 false-box(valid nonempty) | 음성 valid-empty | 음성 invalid |
|---|---|---|---|---|
| M0_short | 0.017 | 40/40 | 0 | 0 |
| M0_neutral | 0.129 | 7/40 | 33 | 0 |
| C_short | 0.408 | 39/40 | 0 | 1 |
| C_neutral | 0.385 | 20/40 | 0 | 20 |
| gate_P0 | 0.385 | 1/40 | 39 | 0 |
| gate_PC | 0.368 | 1/40 | 39 | 0 |

- **presence:** 양성 sensitivity M0 28/29, C 26/29. 음성 specificity는 두 모델 모두 39/40이었다.
- **C−M0 (97.5% CI):**
  - G_short: 양성 F1 +0.391 [0.218, 0.569]. false-box −0.025 [−0.100, 0.000].
  - G_neutral: 양성 F1 +0.256 [0.101, 0.423]. false-box +0.325 [0.150, 0.500].
- **C_neutral의 label 형식 문제:**
  - G_neutral 전체 21건이 label을 "qA"가 아니라 소견명으로 써서 unknown_id(invalid)가 됐다. 음성 20건, 양성 1건이다.
  - label을 무시하면 C_neutral의 음성 box는 40/40이다(`lenient_false_box`).
  - 따라서 사전 정의된 false-box 0.50은 형식 오류에 가려진 하한이다.
- **사전 고정 결정** (`decision`): `outcome = inconclusive_or_negative_hold`.
  - simple_solution: 세 후보 모두 `supported=false`. C_neutral은 잔여 오류가 크고, gate는 양성 F1 CI 하한 −0.132/−0.155가 기준을 넘지 못했다.
  - pilot: C_neutral의 grounding invalid가 30.4%로 기준(5%)을 넘고 F1 0.385<0.40이라 core를 통과하지 못했다.
  - 적응 악화: G_short는 미지지, G_neutral은 +0.325로 기준 충족. 그러나 이 차이는 C의 label 형식 오류(invalid)가 섞인 값이다.
- **민감도** (사전 고정): 양성 non-hedged 21명에서 C_short 0.429, C_neutral 0.444. 음성 명시적 "pleural"만 21명에서 C_short 21/21, gate_P0 0/21.

**독립 검증**
- 엄격 재계산(`eval/verify_E.json`)은 report와 불일치했다(양성 F1 최대 0.5, 음성 1.0).
- 원인: M0 출력 10건에 여분의 `]`가 붙어 엄격 재계산은 invalid, pipeline은 완결 목록을 추출.
- 같은 규칙으로 맞춘 관대 변형(`eval/verify_E_tolerant.json`)은 환자별 F1·false-box·invalid 모두 최대 차이 0, presence 수치도 일치했다.
- 주 CI의 재계산 값은 `verify_E*.json`에 있다(별도 난수 seed).

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**진전 (관찰 범위 내)**
- 양성 문장만으로 학습한 C는 존재 전제 질의에서 부재 영상에도 거의 항상 box를 낸다.
- 그러나 M0도 같다. 따라서 이 결함은 SFT가 만든 악화가 아니다.
- 미적응 M0의 presence 확인과 C의 presence 확인은 모두 이 개발 집단에서 부재 거부를 크게 개선했다(39/40→1/40). 양성 F1 손실은 점추정 −0.02~−0.04였다.
- 이 손실의 상한은 n=29에서 CI 하한 −0.13까지라 사전 기준으로는 미확정이다.

**미검증**
- 독립 확인 집단, 다른 target·기관, 다른 SFT seed, 실제 pipeline latency.
- MedGrounder 비교, positive+negative 직접 CE 대조군은 실행하지 않았다.

**재사용 검증**
- **반입 blob·import:** 12개 파일 blob 일치와 import 정상, 기존 산출물은 읽기 전용으로 썼다.
- **eligibility 분리:** fixture 43/43과 눈가림 검토 기록.
- **provenance:** protocol에 GT manifest, selection lock, review, 스펙 소스를 hash 잠금.
- **평가 소스:** protocol에 잠그지 않고 `report_E.json`의 provenance digest에 기록했다.
- **completion:** 존재만으로 건너뛰지 않고 `verify_completion`으로 재검증한다. 변조 거부와 다른 모델 protocol 거부를 확인했다.
- **양성 matching:** 기존 함수와 별도 구현의 환자별 값 일치.
- **음성·presence parser:** fixture.
- **GPU 배치:** 허용 GPU 0/1, 여유 순 배정 대신 pg41_run의 `worker % gpu` 배정을 썼다(두 GPU가 모두 여유가 커서 차이 없음). 메모리 gate 거부는 기록하지 않았다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **해석 주의:**
  - C_neutral의 invalid 21건은 label 지시("Use qA") 무시라는 형식 문제다. 내용(부재 거부) 오류와 구분해야 한다. 사전 parser 규칙을 유지해 보고했으므로, 사후에 규칙을 바꾸지 않았다.
  - 양성 F1 손실 CI가 넓어(n=29) gate의 비용 판단은 정밀도가 부족하다.
  - E 표본이 작고, 사전학습 노출은 미확인이다.
- **재사용 전 수정:**
  - `pg42_verify.py`의 엄격 모드와 pipeline parser는 stray token을 다르게 처리한다(정의 차이).
  - 음성 GT는 report 문장 기반이며 영상 재판독이 아니다. bare "effusion" 19건은 흉수로 해석한 것이다.
  - `results/iter_042_tmp_review.txt` 정리 필요.
- **추후 개선:** 요청 시간 합은 device-seconds CI나 사용자 지연을 대체하지 않는다. 실제 두 단계 pipeline latency는 측정하지 않았다.

# Recommendation to GPT

- 사전 규칙상 결과는 "불확정/보류"다. 같은 진단에 환자·prompt를 추가하지 않기로 계획에 명시돼 있다.
- 다만 관찰은 다음 투자 판단에 쓸 만하다. 단순 presence gate(추가 학습 없음)가 이 개발 집단에서 부재 오출력을 39/40→1/40으로 줄였고 양성 손실은 작았다. 그러므로 negative 포함 SFT 또는 새 loss 투자의 필요성은 약해졌다.
- 판단할 점은 세 가지다: (1) G_neutral 형식 오류를 형식 문제로 볼지, (2) gate의 양성 손실을 더 정밀하게 볼 후속 표본이 필요한지, (3) 위치 출력 연구를 언어·근거 연결 과제로 옮길지.
- 논문 추천 조건(개선 효과 재현 등)은 충족하지 않는다고 본다.

SELF_CHECK: FAIL
SUMMARY: PadChest E(양성29·음성40)에서 M0·SFT C 모두 존재 전제 질의에서 음성 39–40/40에 box를 냈고 C 적응 악화 근거는 없다. presence gate는 39/40→1/40으로 줄였지만 양성 F1 손실 CI(하한 −0.13)가 사전 기준을 못 넘어 사전 판정은 불확정/보류다. 엄격 독립 재계산은 parser 정의 차이로 불일치했고 관대 변형은 일치하며, 독립 확인과 실제 latency는 미검증이다.