# 요약

- **핵심 결과**: E32(환자 32명, 두 모델)에서 사전 확대 조건을 어느 모델도 충족하지 못했다. E96은 실행하지 않았고 R64는 열지 않았다.
- **MedGemma 1.5**: 제안을 그대로 따랐다. lenient 기준으로 올바른 제안(C) 때는 정확도 1.00, 교환된 제안(W) 때는 0.00이다. 제안이 없을 때(N)는 0.547로 우연 수준이다. 영상 없는 N은 0.453이고 N−TextN은 +0.094, CI [−0.016, 0.219]이다. 독립 grounding(PG)은 0.50이다. 기본 연결 능력이 없는 상태이므로 "충분한 인식을 전제로 한 제안 손상"은 주장할 수 없다.
- **CURE**: PG가 32/32(1.00)이고 평균 IoU 0.655이다. 선택 과제 N은 lenient 0.50이고 영상 없는 N과 같다(N−TextN = 0). C는 0.83, W는 0.17이다. 이 선택 인터페이스는 CURE의 학습 형식과 달라 영상 근거 사용이 관찰되지 않는다. 제안 없이 다시 grounding하는 단순 대안이 개발 표본에서 충분하다.
- **근거**: 원시 출력에서 독립 재계산한 56개 수치가 모두 일치한다(`lk105_verify.py`). 처음 만든 간이 verifier는 M15 PG 3건에서 달랐다. 모델이 JSON 뒤에 `]`를 하나 더 붙인 출력을 간이 파서가 처리하지 못한 탓이어서 파서를 고쳐 재실행했다. 두 파일(`verify_E32.json` 실패, `verify_E32_v2.json` 통과)을 모두 보존했다.
- **주의**:
  - CURE 학습에 PadChest-GR가 쓰였으므로 train 환자의 학습 노출을 배제하지 못한다. PG 1.00은 상한에 가까운 값으로 읽어야 한다.
  - 표본은 개발 자료이며 주석 연결 일치만 측정했다. 임상적 진위나 판독 정확성은 평가하지 않았다.
  - 이 결과를 "제안 의존 현상이 없다"로 일반화하지 않는다. 판정 범위는 이 두 모델, 이 선택 인터페이스, 이 32명이다.
- **다음**: 현재 후보는 투자 보류를 권고한다. 재개 조건은 (a) 위치를 올바르게 grounding할 수 있는 모델에서 제안의 영향을 측정하는 설계이거나 (b) 실제 자동 제안의 오류 분포가 확보되는 경우다.

# Work Performed

- 반입 13개 파일의 git blob이 manifest와 일치함을 확인했다.
- 자료: 공식 train에서 단일 box 문장쌍을 가진 254명을 열거해 D4 4명, E32 32명, R64 64명으로 잠갔다. 문장 조각 6쌍은 모델 출력 전에 제외했다. 첫 열거는 254명이 29명으로 줄어 폐기하고 `enumeration_v2.json`으로 교체했으며 원본은 보존했다.
- 시각 점검은 120쌍의 문장 전체와 contact sheet 2장(#0~11, #36~47)이다. box가 의도한 구조에 그려지는 것을 확인했고 전문의 검토는 아니다.
- 구현: spec, runner, eval, verify, tech, test 파일을 새로 작성했다.
- 설계상 차이: plan은 strict parser만 쓰도록 했다. 그러나 D4 smoke 형식이 이를 허용하지 않았다.
  - CURE는 선택지 문장을 그대로 반복한다.
  - MedGemma 1.5는 설명을 쓴다.
  - 그래서 strict(plan 그대로)와 lenient_v1(D4 형식만 보고 E32 전에 잠금)을 병기했고, 확대 규칙은 둘 중 하나라도 충족하면 적용하도록 했다. 리뷰에서 판단해 달라.

# Files Changed

- 코드: `lk105_data.py`, `lk105_spec.py`, `lk105_run.py`, `lk105_eval.py`, `lk105_verify.py`, `lk105_tech.py`, `lk105_test.py`.
- 결과: `results/iter_105/` 아래에 `data/`, `protocol/`, `gen/`, `eval/`, `tests/`.
- `lk105_run.py`는 D4_w1f 생성 후 PEAK_MIB 상수만 바꿨다(10500/12500 → 10000/9100, 실측 9997/9019 MiB). 변경 전 파일은 `protocol/lk105_run_used_for_D4_w1f.py`에 보존했다. 이 변경 때문에 D4_w1f, D4_resume, mutation_D4, tech_*는 변경 전 소스로 실행·검사됐고, D4_w2b와 E32는 현재 소스로 실행됐다.

# Commands / Experiments

- 성공:
  - `lk105_data.py` enumerate/extract/lock.
  - `lk105_run.py lock_weights`.
  - D4_w1f 1 worker/모델 (wall 2184초).
  - D4_w2b 2 worker/모델 (wall 2063초).
  - D4_resume (CURE, `--limit` 20 후 꼬리 12바이트 절단 재개).
  - E32 CURE 2 worker (835초).
  - E32 MedGemma 1.5 4 worker (8000초).
- 실패: D4_w2 첫 시도는 메모리 admission 거부(예약 10500/12500 MiB가 과다)로 중단됐다. 실측 피크로 상수를 고쳐 D4_w2b로 재실행했다.
- 중단: 첫 D4 smoke(D4_w1)는 코드 hash가 바뀌어 중간에 중단했고 부분 산출물을 보존했다.

# Results

- 검사
  - CPU 검사 1922/1922 통과(`tests/cpu_tests_v2.json`).
  - 변조 검사 18/18 거부(`tests/mutation_D4.json`).
  - 공식 경로 대조는 모델별 12/12: input_ids 동일, suffix token 동일, 텍스트 전용 입력에 image token과 pixel_values 없음(`tests/tech_CURE.json`, `tech_M15.json`).
  - 재개: 부분 행을 복구한 뒤 56/56 token이 D4_w1f와 일치했고, 완료 후 재실행해도 파일 hash가 같았다.
  - worker 수 비교: D4 1 worker와 2 worker의 출력이 112/112 요청에서 token 동일했다.
- E32 수치(`eval/report_E32.json`, 환자 bootstrap 10,000회·seed 105017, 95% CI)

| 모델 | parser | N | C | W | 텍스트 N | PG | N−W [CI] |
|---|---|---|---|---|---|---|---|
| CURE | strict | 0.297 | 0.078 | 0.000 | 0.422 | 1.000 | 0.297 [0.219, 0.375] |
| CURE | lenient_v1 | 0.500 | 0.828 | 0.172 | 0.500 | 1.000 | 0.328 [0.250, 0.406] |
| M15 | strict | 0.000 | 0.000 | 0.000 | 0.422 | 0.500 | 0.000 [0, 0] |
| M15 | lenient_v1 | 0.547 | 1.000 | 0.000 | 0.453 | 0.500 | 0.547 [0.500, 0.594] |

  - M15 strict는 영상 조건에서 64/64가 형식 오류라 해석할 수 없다.
  - CURE strict의 N−W 양성은 W가 거의 전부 형식 오류인 데서 오는 것이므로 제안 민감성의 근거로 읽지 않는다.
  - 비용(조건당 요청 평균 생성초): CURE는 선택 3.0초, PG 6.3초(문장 2개)이다. M15는 영상 선택 9.9초, 텍스트 전용 118.3초(thinking 장문)이다.
  - M15 텍스트 전용은 최종 비EOS 16건, cap 재시도 33건이 있었고, M15 PG 평균 IoU는 0.082(문장 IoU≥0.3 비율 4.7%)이다.
  - GPU 점유 최대는 D4_w2b에서 GPU당 약 18.9GB이다.
- 파일: `eval/report_E32.json`, `eval/verify_E32.json`(실패), `eval/verify_E32_v2.json`(통과).

# Goal Progress / Reused Assets

- 이번에 알게 된 것: 이 주석 연결 선택 인터페이스에서는 제안의 영향이 기본 능력 부족과 분리되지 않았다. 제안 없는 독립 grounding이 CURE에서는 사실상 충분하다.
- 미검증: 기본 grounding이 가능한 다른 모델, 실제 자동 제안의 오류 분포, 독립 환자, 자유 판독과의 연결.
- 재사용: `pg39_data.py`는 로더 한정으로 사용했다. `report101_cure.py`와 `pg43_run.py`는 재사용 필수 보완을 새 runner에서 구현했다.
  - 전 shard 정확한 요청 집합 검사와 변조 거부.
  - 자산 digest 잠금.
  - 부분 행을 보존한 재개.
- 현재 필수 검증은 통과했다. 이 코드를 다른 자료에 쓰려면 별도 검증이 필요하다.

# Problems

- 현재 결론 무효: 없음.
- 재사용 전 수정:
  - strict와 lenient 병기는 plan 문구와 다르다.
  - `lk105_run.py` 상수 변경 이후 D4_w1f와 D4_resume은 현재 소스 hash로 재검증되지 않는다.
  - M15 PG 파서의 한 경우(JSON 뒤 추가 `]`)는 production 파서와 독립 파서 사이에 차이가 있었고, 독립 파서를 고쳐 맞췄다.
- 추후 개선: M15 텍스트 전용의 장문 thinking 때문에 비용이 크다.

# Recommendation to GPT

- 현재 선택 인터페이스 후보는 투자 보류를 권고한다. 이유는 CURE에서 독립 PG가 충분하고, M15는 PG와 N이 모두 낮아서 제안 실패를 주장할 근거가 없기 때문이다.
- 다음에 중요한 질문은 두 가지다. (a) 위치를 올바르게 grounding하는 모델에서 같은 연결 질문을 다시 보는 것. 자료 연결은 재사용할 수 있다. (b) 실제 자동 제안의 오류 분포를 확보해서 제안 영향을 측정하는 것.
- 타당한 대안은 이 연결 질문을 접고 기존 위치–판독 관찰(iter_088, 092~094)에서 판독 쪽 질문을 하나 고르는 것이다.

SELF_CHECK: PASS
SUMMARY: 공개 주석 연결 과제에서 E32(두 모델)는 사전 확대 조건을 충족하지 못해 E96은 실행하지 않았다. M15는 기본 grounding과 선택이 모두 낮고, CURE는 독립 grounding이 32/32로 충분해 현재 후보는 보류를 권고한다. strict/lenient 병기와 CURE 학습 노출 미확인은 주의해야 한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python -c "
import json,hashlib
a={json.loads(l)['id']:json.loads(l) for l in open('results/iter_105/gen/D4_w1f/cure/shard0/outputs.jsonl')}
lines=[l for l in open('results/iter_105/gen/D4_resume/cure/shard0/outputs.jsonl')]
b={json.loads(l)['id']:json.loads(l) for l in lines}
print(len(lines),len(b),set(a)==set(b),sum(a[k]['attempts'][-1]['suffix_ids']==b[k]['attempts'][-1]['suffix_ids'] for k in a))
"
H=$(sha256sum results/iter_105/gen/D4_resume/cure/shard0/outputs.jsonl); echo $H
