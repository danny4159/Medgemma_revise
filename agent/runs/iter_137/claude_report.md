# 요약

- **핵심**: 설명 요구 제거(B) 대 원문(A)의 E45 본비교 180요청은 **실행하지 않았습니다**. 사전 기술 gate 11개 중 1개가 미달해서입니다.
- **근거**: A의 첫 줄 유효율이 11/12(0.917)로 기준 0.95에 못 미쳤습니다. 원인은 BRATS_053__N1__A 한 건이 상태어 없이 문장으로 시작한 모델의 형식 오류입니다. 나머지 10개 항목은 모두 통과했습니다.
- **미검증·주의**: B 대 A 정확도, BA, 판정(positive/negative/inconclusive)은 아직 없습니다. 이번 결과는 가설에 대한 판단이 아닙니다.
- **다음**: 아래 결정이 필요한 사항 한 가지가 있습니다. 판정 방법은 GPT가 정합니다.

# Work Performed

- 현재 브랜치에 i134/i136 소스가 없었습니다. 보관 커밋 87bb24e에서 `i134_spec.py`와 `msd56_data.py`를 그대로 복원하고 blob SHA 일치를 확인했습니다 (7962f6c9…, 142c67d5…).
- `i136_*` 실행기·잠금·기술검사는 `i137_*`로 파생해 경로와 계약만 바꿨습니다. 단일 영상·A/B 요청, 단일 gate 경로, 중단 시도 비용 합산을 넣었습니다.
- iter_136의 D6/E45 P/N1 PNG를 읽기 전용으로 재연결했습니다. 새 표본 선정이나 재렌더는 없습니다.
  - PNG와 원 NIfTI hash, 면적 계약, D/E 비중복, pixel 중복 0을 확인했습니다.
  - 원 NIfTI는 51개 사례 전부 hash가 일치했습니다.
- 요청은 technical 24건과 main 180건을 만들었고, 평가기(`i137_eval.py`)를 생성 전에 작성했습니다.
- 기술 검사는 CPU 테스트 37/37, boundary, tensor, negative 24/24를 통과했습니다. tensor 검사에서 A/B는 입력 token에서 설명 요구 문장 구간(`' Then give one short sentence of visible evidence.'`) 하나만 차이가 났습니다.
- D24를 GPU에서 w2 → w4 → SIGKILL 후 재개 순으로 실행했습니다. 세 구성의 token이 24/24 동일했고 exit code는 모두 0이었습니다.

# Files Changed

- 신규:
  - `i137_common.py`, `i137_spec.py`, `i137_data.py`, `i137_run.py`
  - `i137_eval.py`, `i137_lock.py`, `i137_tech.py`, `i137_gate.py`
  - `test_i137.py`
  - 복원 파일 `i134_spec.py`, `msd56_data.py`
- 산출물은 `results/iter_137/` 아래에 있습니다.
  - `data/manifest.json`, `requests/`, `tests/`, `jobs/tb1024_{w2,w4,resume}`, `protocol_lock_technical.json`

# Commands / Experiments

- 성공:
  - `i137_data.py`
  - `test_i137.py` (37/37)
  - `i137_tech.py boundary / tensor / neg`
  - `i137_lock.py technical`
  - `i137_tech.py launch technical tb1024_w2 2` / `tb1024_w4 4` / `resume`
  - `i137_tech.py compare`
- 실패 후 분리 처리: `i137_tech.py gate technical`은 `max({}.values())` 오류로 중단했습니다. w4가 빨리 끝나 GPU 사용량 샘플이 비어 있었기 때문입니다.
  - 생성 후 `i137_tech.py`를 고치면 protocol hash가 어긋납니다. 그래서 수정 두 건을 원복해 잠금과 일치함을 다시 확인했습니다.
  - 판정 기준은 그대로 두고 샘플 없음만 기록하는 별도 `i137_gate.py`를 만들어 실행했습니다. 이 파일은 생성 이후 작성했으므로 사전 잠금이 아닙니다.
- 미실행: technical2048, main protocol 잠금, E180 생성. 절단(non-EOS)이 0건이라 2048 재실행 조건에도 해당하지 않았습니다.

# Results

- gate (`results/iter_137/tests/technical_gate_technical.json`): passed=false.
  - 통과한 항목: boundary, tensor, negative, w4 동일, 재개 동일, 요청 수, rc 0, 중단 후 재개, EOS 24/24, 메모리.
  - 실패한 항목: 첫 줄 유효율 인터페이스별 ≥0.95 (A 0.917, B 1.0).
- D24 출력 상태 (accuracy 판단이나 gate 기준 아님, 참고 기록):

| 조건 | PRESENT | invalid |
|---|---|---|
| A, P | 6 | 0 |
| A, N1 | 5 | 1 |
| B, P | 6 | 0 |
| B, N1 | 6 | 0 |

  - B는 12건 모두 상태어 한 단어(2~3 token)만 출력했습니다.
- 처리량(loading 포함):

| 구성 | req/분 | 비고 |
|---|---|---|
| w2 | 41.9 | wall 34.4초 |
| w4 | 29.8 | wall 48.2초 |
| resume | 17.9 | 중단 시도 51.3초 포함 |

  - 이 기준으로 main은 2 worker가 선택됩니다.
  - peak reserved는 8,466 MiB, GPU used는 w2에서 8,877/8,805 MiB였습니다. w4는 사용량 샘플이 비어 torch peak로만 판정했습니다.
- 구성 간 비교는 24건 token 동일, 첫 줄 상태 동일입니다.

# Goal Progress / Reused Assets

- 한 일은 실행 기반 검증입니다. 설명 요구의 효과는 아직 판단하지 못했습니다.
- 재사용:
  - `i134_spec`/`msd56_data`는 SHA 일치 후 그대로 사용했습니다.
  - i136 실행기·gate·평가기는 needs_fix 범위를 계승하되 하드코딩 요청 수와 result 개수 가정을 제거했습니다.
- 계승한 한계: 반복 개발 E45, N1은 임상 정상이 아님, P는 GT 기반 선택, 독립 확인 없음.

# Problems

- 현재 결론을 막는 결함: E180이 미실행입니다. 사전 gate(첫 줄 유효율 ≥95%, D 분모 12)가 A 1건의 형식 오류로 미달했습니다. 분모 12에서는 사실상 100%를 요구하는 기준입니다.
  - 계획의 "정확도 미달은 기술 실패가 아니다"와 "기준을 본실행 후 완화하지 않는다"에 따라 임의로 통과시키지 않았습니다.
  - 모델이나 prompt를 바꾸지도 않았습니다.
- 재사용 전 수정:
  - `i137_tech.gate`는 resources 샘플이 비면 중단합니다. 보정본은 `i137_gate.py`에 있습니다.
  - protocol 잠금 코드와 gate 코드가 같은 파일이라 생성 후 수정이 막힙니다.
- 추후 개선: w4 resources 샘플링은 worker를 순차 기동한 뒤에야 시작해서 짧은 job에서 비는 경우가 있습니다.

# Recommendation to GPT

- 결정이 필요한 사항 하나: D gate의 "조건별 첫 줄 유효율 ≥95%"가 D12 기준에서 A 11/12로 미달했습니다.
  - (a) gate 실패로 두고 execution_failed로 종료할지,
  - (b) 이 gate 항목은 사전 주판정 조건인 "main에서 조건별 ≥95%"로 대체한다는 명시적 보완을 승인할지
  를 정해야 합니다.
- iter_136의 같은 prompt A는 405건 중 2건만 invalid였습니다. E45에서는 A 유효율이 95%를 넘을 가능성이 있지만, 이는 추정이며 실제 측정이 아닙니다.
- 선택된 쪽의 계획을 받으면 main protocol 잠금과 E180(w2, 예상 약 4~5분)을 이어서 실행할 수 있습니다.
- 지금 상태에서는 B가 상태 분포를 바꾼다는 관찰도 아직 확정할 수 없습니다.

SELF_CHECK: FAIL
SUMMARY: 설명 요구 제거 대조의 자료 연결·잠금·기술 검사·D24 w2/w4/재개를 실제 GPU로 실행했으나, A의 첫 줄 유효율 11/12가 사전 gate(≥95%)에 미달해 E180 본비교는 실행하지 않았고 B−A 결과는 없다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: git ls-tree --name-only 87bb24e65b04b7f8c556ababd9035dfa18fafed1
- Bash: git ls-tree 87bb24e65b04b7f8c556ababd9035dfa18fafed1
- Bash: sed -i "s#results/iter_134/jobs/main#results/iter_136/jobs/main#; s#iter_134 저장 출력#iter_136 저장 출력#; s#iter134_stored_status_counts#iter136_stored_status_counts#" i137_tech.py && grep -n "iter_136\|iter136" i137_tech.py
