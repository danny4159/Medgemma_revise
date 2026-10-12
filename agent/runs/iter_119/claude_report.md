# 요약

- **핵심 결과:** 자연 초안을 유지해야 한다는 근거는 이 저장 자료에서 확인되지 않았다. 최소 method pilot은 제안하지 않고 근거 부족으로 보류한다. 새 추론, 학습, GPU 사용은 없었다.
- **근거:** 불일치 87명에서 K는 47, G는 54, S는 53명이 정답이다. K 정답이면서 E가 놓친 26명 중 24명은 E가 명시 오답이 아니라 hedge로 답을 보류(unresolved)한 경우다. K≠G 불일치 33명 중 E가 답한 경우는 9명뿐이라 초안 없는 판단으로 K와 G 중 어느 쪽이 맞는지 가릴 신호가 없다.
- **미검증·주의:** 선행 3편의 원문 재확인은 하지 못했다. 반복 개발 중인 선택 집단의 사후 분석이며 독립 확인이 아니다.
- **다음:** 사용자 승인을 기다린다. 후보 하나는 K≠G 불일치를 교정이 아니라 오류 검토 신호로 쓰는 용도다.

# Work Performed

- **입력 연결:** iter_117의 174명을 ledger, GT, selection, 696개 record 원문과 대조했다. 문제는 0건이었다. K/B/G/M/S는 ledger와 저장 답에서 원 정의 그대로 재도출해 일치를 확인했다. E/N/R/T는 record 원문과 원 resolver로 일치만 확인했고 재채점은 하지 않았다.
- **고정과 집계:** 집계 전에 분석 규약을 고정했다(`lock/analysis_spec.json`, 2026-10-12T13:12:03Z, 스크립트 SHA 기록). 이어 두 집단의 정답/오답/unresolved 분모, K 대비 3×3 교차표(ID 보존), 정답 수 이동 분해, 공유 변수를 유지한 unresolved 범위, 174행 사례표를 만들었다.
- **잠금 이후 추가분:** 초안 고유 정보 10명, K≠G 중재표, unresolved reason 분포를 추가했다. 정책 선택은 하지 않는 기술 통계이며, 잠금 이후 추가분(amendment)으로 표시했다.
- **검산:** 분석 모듈을 쓰지 않는 독립 재계산으로 대조했다.

# Files Changed

- 코드: `ed119_analyze.py`, `ed119_extra.py`, `ed119_verify.py`, `test_ed119.py`
- 결과 경로 `results/iter_119/`:
  - `lock/analysis_spec.json`
  - `eval/{report,cases174,key_cases,extra_tables,verify,input_digests}.json`
  - `tests/fixtures.json`
  - `RESULTS.md`
- 기존 파일 수정과 덮어쓰기는 없다. 결과 파일은 `x` 모드로만 썼다.

# Commands / Experiments

- `python test_ed119.py`: 성공, 10/10.
- `python ed119_analyze.py lock`: 성공.
- `python ed119_analyze.py analyze`: 성공, 0.13초, 입력 11파일의 SHA256 기록.
- `python ed119_extra.py`: 성공.
- `python ed119_verify.py`: 성공, 47/47.
- WebFetch(선행 3편 원문): 권한 거부로 실패했다. 우회하지 않았다.

# Results

저장된 수치를 인용한 값이다. 사용자 점검 수치는 모두 재현됐다(ID는 `eval/report.json`의 `K_vs.E`).

- **불일치 87명 (정답/오답/unresolved):**

| 정책 | 정답 | 오답 | unresolved |
|---|---|---|---|
| K | 47 | 40 | 0 |
| B | 40 | 47 | 0 |
| G | 54 | 33 | 0 |
| M | 54 | 33 | 0 |
| E | 29 | 10 | 48 |
| S | 53 | 34 | 0 |

- **K와 E의 상보성:** K 정답·E 명시 오답 2명, E 정답·K 오답 8명, K 정답·E unresolved 24명이다. E unresolved 48 중 45는 원 resolver의 hedge_or_conditional이라 내용 오류와 구분된다.
- **K 대비 순변화:** E −18, G/M +7, S +6. E 범위는 [29, 77]이다. 정책별 극값은 동시에 실현되는 성능이 아니다.
- **초안 고유 정보:** draft-free인 B/G/E 모두 정답이 아닌 K 정답 사례가 10명이다(oracle 진단이며 사용 가능한 selector가 아니다). 이 중 E unresolved가 9명이고 E 명시 오답이 1명이다. S는 K fallback으로 9명을 맞히고 M은 0명이다.
- **K≠G 불일치 33명:** K가 옳은 경우 13명, G가 옳은 경우 20명이다. E가 답한 경우는 9명뿐이다(옳음 5, 틀림 4). S는 거의 K를 따르고(12/13, 2/20) M은 G를 따른다(0/13, 20/20).
- **일치 대조 87명:** G는 순 −1(획득 2, 손실 3)이고 M/S는 K와 같다. 반대 방향 위험은 불일치 집단에 몰려 있다.
- **공간 관련:** K 정답·E unresolved 24명 중 detector box가 없는 경우가 14명이고 tp03≥1은 0명이다. 공간 근거의 고유 역할은 제거 대조가 없어 미검증이다.
- **판정:** 근거 부족으로 보류한다. 정확도 면에서 G(초안 없음) 54 ≥ S(초안 사용) 53이라는 보조 근거도 있다. 두 근거 모두 이 집단에 한정된다.

# Goal Progress / Reused Assets

- **목표 진전:** 합성 초안 손상(iter_118)은 그대로 보존한다. 자연 초안 정보 보존을 위한 개입을 지금 시험할 근거는 이 자료로는 없다. 자연 초안 전체나 의료 교정 전체를 기각한 것은 아니다. 신규성과 공간 인과도 주장하지 않는다.
- **재사용 자산:** `ed116_eval`/`ed116_spec`의 정책 함수와 `ev109_extract.resolve`를 연결 확인에 썼다. 모두 iter_116~118에서 승인된 범위다. 선별 반입 파일은 없다.

# Problems

- **현재 결론 무효:** 없음.
- **재사용 전 수정:** 없음.
- **추후 개선:**
  - 선행 3편(medical VQA 조언 민감성, anatomically-grounded fact checking, FC-guided 선택 수정)은 이번 세션에서 원문을 재확인하지 못했다. 계획의 GPT 조사 기록에 의존하며, 입력·평가·대조 범위표는 만들지 못했다.
  - 이 분석은 반복 개발 중인 K≠B 선정 집단이고 자연 오류 빈도가 아니다.
  - 선정 구조상 oracle 합집합은 방법 가능성의 증명이 아니다.
  - 서비스 전체 비용은 미측정이다.

# Recommendation to GPT

- **주 분기:** 근거 부족으로 이 자연 초안 교정 묶음을 보류한다. 남은 문제는 K와 G의 중재(33명)인데, 저장 자료에 GT 없는 신호가 없다.
- **선택 후보 하나:** K≠G 불일치를 교정이 아니라 오류 검토 신호로 쓰는 용도다. iter_113/114 계열과 이어지고 불일치율은 불일치 집단 33/87, 일치 대조 5/87이다. 별도 승인과 계획이 필요하다.
- **리뷰에서 확인할 점:**
  - 잠금 이후 추가분을 보조 분석으로만 취급하는지.
  - "가치 부족"과 "근거 부족"의 구분.
  - 선행 문헌 원문 재확인 방식.

SELF_CHECK: FAIL
SUMMARY: iter_117 저장 174명 점검 결과 K가 유일하게 맞힌 10명 중 9명은 S의 fallback이 이미 보존하고 K-G 중재 신호가 없어 근거 부족으로 보류한다. 선행 문헌 원문은 WebFetch 권한 거부로 재확인하지 못했다.

# [orchestrator] 권한 거부된 도구 호출
- WebFetch: https://arxiv.org/html/2603.22623v1
- WebFetch: https://arxiv.org/html/2412.02177v1
- WebFetch: https://razi-mahmood.github.io/reports/NeurIPSHealthcareWorkshop.pdf
