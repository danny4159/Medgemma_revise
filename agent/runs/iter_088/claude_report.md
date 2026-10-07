# 요약

- **핵심 결과:** 남은 20명·160개 판정을 완료해 E96 전체 **96명·768개 판독문**을 재평가했습니다.
- **근거:** 고정 24명 재점검, 기존 fixture 41/41, 새 경로 검사 14/14, 별도 산술·bootstrap 검증을 통과했습니다.
- **주의:** CURE의 회복 신호는 유지되지만, 모호한 대응을 제외하면 개선폭의 CI가 0을 포함합니다. 임상 정확도나 신규 기여의 확증은 아닙니다.
- **다음:** 독립 full review를 권고합니다. 신규 생성·학습·E192 확대는 실행하지 않았습니다.

# Work Performed

iter_087의 76명 부분 판정을 검증해 재사용하고, 남은 판정·전체 집계·민감도 분석을 완료했습니다. 재점검에서 발견한 범위 오류와 근거 전사 오류는 새 변경 기록에 남겼습니다.

잠금 이후 평가기 변경은 Claude 로그의 Write/Edit와 Bash 문자열 변경까지 재구성해 확인했습니다. 과거 결과·코드는 수정하지 않았습니다.

# Files Changed

신규 소스 9개: `report88_{handoff,check,adjudicate,eval,verify,sensitivity_verify,sourcecheck,finish}.py`, `test_report88.py`.

주요 산출물:

- [완료·보존 manifest](results/iter_088/completion.json)
- [전체 평가 결과](results/iter_088/eval/report.json)
- [판정 변경 이력](results/iter_088/adjudication/changes.json)
- [민감도 분석](results/iter_088/eval/sensitivity.json)
- [독립 수치 검증](results/iter_088/verify/independent.json)
- [실행·복구·미확인 사항](results/iter_088/execution_summary.json)

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python test_report87_eval.py results/iter_088/tests/inherited_fixtures.json`: **41/41 통과**
- `python report88_adjudicate.py`: 96명·768개 판정 연결 완료
- `python report88_eval.py`: 전체 집계·사전 고정 민감도 완료
- `python report88_verify.py`: 원본·보완본 보고서 연결 오류를 수정한 뒤 독립 검증 통과
- `python report88_sensitivity_verify.py`: 6개 민감도 각각 **896개 검사 통과**
- `python report88_sourcecheck.py`: 셸 변경 이력까지 보완한 뒤 출처 검사 통과
- `python test_report88.py path_tests_v2.json`: fixture 오류 수정 후 **14/14 통과**
- `py_compile`, `git diff --check`, 최종 봉인 hash 검사: 통과

신규 GPU 요청·학습·모델 적재·패키지 설치는 **0건**입니다. 인계부터 봉인까지 약 **25.8분**이 걸렸습니다.

# Results (수치와 결과 파일 경로)

아래는 **비정상 층 48명**, 환자별 평균 차이입니다.

| 비교 | 확정 recall 차이, 95% CI | 명시 모순 비율 차이, 95% CI |
|---|---:|---:|
| RSNA SFT B0-R − M15-R | +3.13pp [−2.08, +10.42] | −2.08pp [−10.42, +4.17] |
| CURE C-G − 해당 base M1-G | **+15.28pp [+2.08, +28.82]** | **−20.83pp [−33.33, −8.33]** |
| 영역별 결합 C-H − C-G | +6.08pp [+1.04, +11.98] | **+47.92pp [+33.33, +62.50]** |

- C-G의 strict recall 차이는 **+10.07pp [2.78, 18.75]**입니다.
- 모호한 개념 대응을 U로 처리하면 C-G의 확정 recall 차이는 **+11.11pp [−1.04, +23.26]**로 불확정입니다.
- C-H의 확정 내부 모순은 전체 **76/96명**, C-G는 **0/96명**입니다. C-H는 공유 GRG를 포함해 환자당 30요청입니다.
- 양성 사실 분모 **72/73개**, 공통·확장 모순 평가 분모 **55/56명**을 구분했습니다.
- 원본 48개 파일과 최종 봉인 대상의 hash 불일치는 **0건**입니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

중단된 의미 평가를 완료했고, 평가 보완 뒤에도 CURE 회복 신호와 단순 영역 결합의 충돌이 남는다는 제한된 관찰을 확보했습니다.

iter_087 checkpoint `056e9fb8eac7`의 평가기·부분 판정과 iter_086의 고정 출력을 재사용했습니다. 원 수치와 수정 수치는 별도 계산으로 대조했습니다. 같은 데이터의 사후 재평가이며 독립 test나 전문가 판독 검증은 아닙니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 주장 제한:** 접속 목록의 상속된 단순화 때문에 결과를 완전한 원자 주장 평가나 임상 precision으로 해석할 수 없습니다. CURE 효과의 통계적 판단도 의미 대응에 민감합니다.
- **재사용 전 확인:** CURE checkpoint별 환자·선택 노출은 미확정입니다. 과거 수동 회귀는 base/SFT 각각 6/8 token 일치이며, 보존되지 않은 tensor/logit 때문에 차이 원인을 확정하지 못했습니다.
- **추후 개선:** 현재 코드는 고정 E96 분석용입니다. 첫 묶음 기반 완료 예상 시간을 실행 전에 별도 기록하지 못한 점도 남겼습니다.

# Recommendation to GPT

**C-G를 강한 기존 비교군으로 유지하고, 현재 C-H 단순 결합의 확대와 E192 자동 실행은 보류할 것을 권고합니다.** 의미 대응 불확실성과 낮은 평가 coverage를 검토한 뒤, C-G 이후에도 최소 방법 개입이 필요한 문제가 남는지 판단해야 합니다.

구조·산술 검사는 통과했지만 위 미확인 사항을 포함해 사용자 규칙에 따라 보수적으로 FAIL을 제출합니다. 구현 담당 전환이나 연구 가설의 기각을 뜻하지 않습니다.

SELF_CHECK: FAIL
SUMMARY: E96 96명·768개 재평가와 독립 수치 검증을 완료했으며, CURE 회복 신호와 영역 결합 모순은 유지되지만 의미 대응·주장 분할의 불확실성으로 full review가 필요하다.