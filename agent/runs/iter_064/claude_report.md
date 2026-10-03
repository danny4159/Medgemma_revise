# 요약

- **핵심 결과:** D6과 E48 전체를 두 모델(Qwen2.5-VL-7B, MedGemma 1.5)로 실행했다. 사전 기본 신호 기준을 두 모델 모두 엄밀히는 충족하지 못했다. 기준은 S BA≥0.75, sens≥0.65, spec≥0.65다.
  - Qwen: S BA 0.719.
  - MedGemma: S BA 0.802지만 spec 0.625.
- **추가 영상 영향:** MedGemma의 C는 R보다 크게 나쁘다.
  - C의 spec은 0.021이고, 두 영상 중 하나라도 병변이면 대부분 PRESENT로 답했다.
  - 질문이 가리킨 영상에 대한 판정이 아니라 영상 묶음 전체에 대한 판정이다.
- **Qwen:** C가 R보다 낮지 않다 (L_content −0.052).
- **주의:** 표본은 E48(48 case × 10요청)이며 반복 사용된 개발 자료다. 정답은 mask 기준이고, 임상적 판독 충분성이나 정상은 아니다. 결합 능력, 임상 성능, 새 방법 우위는 어느 쪽도 입증하지 않는다.
- **다음:** 명시적 target 질문에는 routing(질문의 index가 가리키는 영상만 전달)을 채택한다. S 입력과 동일하므로 별도 생성은 없다. 두 모델의 기본 신호가 기준에 못 미치므로 이 경로의 큰 방법 투자는 보류한다.

# Work Performed

- `msd56_data.py`는 출처 SHA `da6e755`에서 반입된 파일을 읽기·render 용도로만 사용했다.
  - blob hash는 `142c67d…`로 reuse_manifest와 일치한다.
  - 원본 select/extract/build는 실행하지 않았다.
- 새 모듈을 작성했다.
  - `s64_data.py`: target 선택과 요청 생성.
  - `s64_run.py`: runner. q63 대비 JSONL 복구·경합, 비용 저장, protocol의 모델 파일 hash를 수정했다.
  - `s64_eval.py`: 평가기.
  - `s64_checkdata.py`: 자료 검사.
  - `s64_test.py`: 합성·재개 검사.
  - `s64_verify_eval.py`: 독립 재계산.
- 자료 검사 결과:
  - P/N 선택 규칙을 결과 전에 고정했다.
  - D6·E48 54 case가 모두 적격이었고 대체 case는 없다.
  - raw image/label hash가 `cases.json`·`case_order.json`과 일치했다.
- 모델 입력 검사 (D 60 / E 480 요청, 두 모델 모두 fails 0):
  - 공식 호출과 tensor가 동일하다.
  - target 영상의 처리 tensor가 S/R/C에서 동일하다.
  - R은 복제본이다.
  - C의 비-target 영상이 다른 target과 동일하다.
  - GT 누출이 없다.
  - routing 영상이 S 영상과 동일하다.
- 실행 규모:
  - D는 60요청×2모델이다.
  - E는 480요청×2모델이다.
  - 학습·추가 prompt·추가 모델·표본 추가는 없다.

# Files Changed

- 신규: `msd56_data.py`(반입), `s64_data.py`, `s64_run.py`, `s64_eval.py`, `s64_checkdata.py`, `s64_test.py`, `s64_verify_eval.py`.
- 결과 경로: `results/iter_064/{data,D,E,tests}`.
- 기존 파일 수정·삭제는 없다.

# Commands / Experiments

- `python s64_data.py build D|E`: 성공.
- `python s64_checkdata.py`: 1463/1463 통과.
- `python s64_test.py cpu`: 18/18 통과.
- `python s64_test.py runtime 1`:
  - 첫 시도는 테스트 코드 버그(gpu를 문자열로 전달)로 4/12 실패. 그 시도의 `runtime_tests.json`과 `gen_resume_medgemma`는 보존했다.
  - 수정 후 `runtime_tests_v2.json`은 12/12 통과.
  - 통과 항목: 저장 후 강제 종료, torn tail 보존, 2 worker 재개, 변조·중간 손상 거부. 재개 후 token은 중단 없는 실행과 불일치 0.
- `lock` / `tech`:
  - D protocol v1에서 MedGemma tech가 60/60 실패했다. 원인은 `s64_run.py`의 tech 코드가 image placeholder id를 잘못 조회한 것이다.
  - 모델 오답이 아니라 코드 문제였다. `<image_soft_token>`(262144)로 수정하고 `_v2` protocol을 새로 잠가 재실행해 통과했다. v1 파일은 보존했다.
- `launch` / `verify`:
  - D: Qwen GPU0, MedGemma GPU1, 각 1 worker. wall 64초, peak 16.3GB / 8.9GB.
  - E: Qwen GPU0 1 worker, MedGemma GPU1 2 worker. wall 198초, peak 16.3GB / 17.8GB.
  - 모든 exit code는 0이다.
  - 두 모델 모두 `verify.json`이 480/480, problems 0이다.
- `s64_eval.py`와 `s64_verify_eval.py E`: 독립 재계산의 점추정 최대 차이 0.

# Results

결과 파일은 `results/iter_064/E/report_{qwen,medgemma}.json`이고 독립 재계산은 `independent_verify.json`이다. E48, invalid는 오답으로 계산했다. CI는 case paired bootstrap, seed64, 10,000회다.

| 모델 | S BA (sens/spec) | R BA | C BA (sens/spec) |
|---|---|---|---|
| Qwen | 0.719 (0.688/0.750) | 0.719 | 0.771 (0.677/0.865) |
| MedGemma | 0.802 (0.979/0.625) | 0.771 | 0.500 (0.979/0.021) |

| 차이 | Qwen [95% CI] | MedGemma [95% CI] |
|---|---|---|
| L_count (S−R) | 0.000 [−0.026, 0.021] | 0.031 [−0.010, 0.073] |
| L_content (R−C) | −0.052 [−0.115, 0.005] | 0.271 [0.203, 0.339] |
| L_total (S−C) | −0.052 [−0.115, 0.010] | 0.302 [0.229, 0.375] |

- **MedGemma의 위치별 L_content:** pos1 0.281, pos2 0.260으로 두 위치 모두 양수다.
  - C가 R보다 나쁜 case는 27개, 좋은 case는 0개다.
  - 추가 영상 영향 후보 기준(기본 신호 + L_content≥0.10 + 5개 이상 case + 두 위치 양수)은 기본 신호 조건 때문에 형식상 충족하지 못한다. S spec 0.625가 0.65에 못 미친다.
- **Qwen의 위치별 L_content:** pos2는 −0.094 [−0.177, −0.021]이다. pos2 쪽 C가 R보다 높고, 두 위치 방향이 일치하지 않는다.
- **형식:** invalid, 비EOS, 2048 재시도가 모두 0이다.
- **S 정답 target에서 C가 틀리는 비율 (보조):** Qwen 4.3%, MedGemma 37.7%.
- **측정 비용:** 요청당 평균 입력 token은 S 대비 C가 Qwen 157→240, MedGemma 320→579다.

# Goal Progress / Reused Assets

- **진전:**
  - 인식·선택 중 선택 쪽의 현상을 하나 얻었다. 정답이 target 단독으로 정의된 질문에서 MedGemma는 영상이 2장이면 "이 영상" 지시를 따르지 않았다.
  - 이는 입력 정보 손실인지, 지시 따르기 문제인지, 근거 선택 문제인지는 이번 대조로 구분되지 않는다.
- **미검증:**
  - 결합 능력.
  - 임상적 판독 충분성.
  - FLAIR 단독에서 annotation이 항상 보이는지.
  - 환자 독립성과 사전학습 노출.
  - 다른 prompt에서의 재현.
  - E48은 반복 사용된 개발 자료다.
  - P/N slice의 해부학 위치 차이(N은 두개저 쪽이 많음)가 shortcut이 될 수 있다. overlay 육안 확인으로 확인했다.
- **재사용:**
  - `msd56_data.py`: required_checks 4개 중 3개를 수행했다.
    - blob 대조.
    - raw hash 대조.
    - 독립 NIfTI→PNG·affine·index 비교(nibabel orientation 변환 경로, 1463건 통과).
    - 신규 산출물은 `results/iter_064`에만 저장.
  - `msd56_run.py`: MedGemma 로딩, env_info, parse_answer를 사용했다.
  - D6 overlay를 실제로 열어 표시했고 mask가 병변과 맞았다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정/주의:**
  - 처리량 비교(batch/worker)를 별도로 하지 않았다. 전체가 약 3분이라 절약 폭이 비교 비용보다 작다고 판단했다.
    - MedGemma 2 worker는 재개 검사와 E 본실행으로 간접 확인했다. peak는 GPU1 17.8GB다.
  - Qwen은 단일 worker로만 실행했다.
  - 모델 파일 검증은 lock과 verify에서 전체 hash, worker에서는 크기·mtime 일치와 변경 시 재hash다.
  - `s64_run.py`의 변경 후 lock 이전 protocol은 재사용할 수 없다.
- **추후 개선:** bootstrap CI는 독립 구현이 난수 체계가 달라 근사 일치만 확인했다(최대 gap 0.005).

# Recommendation to GPT

- 기본 신호 기준 미달이므로, 사전 규칙상 현재 입력·경로의 큰 투자는 보류한다. 명시적 index 질문은 routing으로 처리한다.
- MedGemma의 C 실패가 지시 해석인지 영상 사용인지는 같은 자료에서 구분하지 못했다. 이 구분이 투자 결정을 바꾸는지 먼저 판단해야 한다.
- 점수 개선만을 이유로 새 loss나 학습을 이어가지 않기를 권한다.

SELF_CHECK: PASS
SUMMARY: MSD E48에서 두 모델 모두 사전 기본 신호 기준(S BA≥0.75, sens/spec≥0.65)은 형식상 미달(Qwen BA 0.72, MedGemma spec 0.625)이다. 대신 MedGemma는 두 영상 입력의 C에서 R 대비 BA가 0.271 하락했다(spec 0.021, 지시 해석인지 근거 사용인지는 미분리). Qwen은 하락이 없었다. 결합 능력·임상 성능은 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: mkdir -p results/iter_064/D && for m in qwen medgemma; do python s64_run.py lock --model $m --requests results/iter_064/data/requests_D.jsonl --labels results/iter_064/data/labels_D.json --target-manifest results/iter_064/data/target_manifest_D.json --out results/iter_064/D/protocol_$m.json; done
