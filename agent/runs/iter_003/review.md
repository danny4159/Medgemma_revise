# Assessment

**CONTINUE / abandon.** 실험은 실제 실행됐으며 핵심 부정적 결과는 신뢰할 수 있다. 다만 실패 범위는 이번 reference 구성과 계수 1의 가산 보정이다. 3D context 안정화 전체가 불가능하다는 결론은 아니다.

계획, 변경된 소스, 실행 로그, manifest, 원시 predictions, metrics, budget 및 montage를 직접 확인했다. 파일 수정이나 실험 재실행 없이 저장된 결과를 읽어 핵심 지표를 독립적으로 재집계했다. `changes.patch`에는 README 변경만 있어 신규 Python 파일은 직접 열어 검토했다.

# Key Findings

- **실행 완료:** predictions는 예비 8행과 `scorer_version=2` 본실행 294행으로 구성되며 모두 `ok`다. 본실행의 요청 ID·입력 hash·config hash가 현재 요청 및 설정과 일치한다. 저장된 PNG 60개의 pixel hash도 manifest와 일치한다. 로그와 budget의 누적 시간은 5.747 device-minutes로 일치한다.
- **측정 검증:** 실행 로그에 CPU 검사 5종 PASS가 있다. 저장 결과에서 teacher-forced 대조 24건의 최대 차이는 1.23e-7, 생성 확인은 12/12 파싱·scoring 일치, 잘림 0건이다. 반복 입력 24쌍의 점수 차이도 0이다.
- **사전 기준 1·2 통과:** P0 E–N margin은 6/6 case-sequence에서 양수이고 BA는 0.917이다. 같은 길이의 P1/P3에서 3/3 case가 log-odds 차이 기준을 충족한다. 해당 비교의 decision flip은 0건이다.
- **사전 기준 3 실패:** 아래 수치를 원시 예측에서 재확인했다. 독립 단위는 3 case이며 84개 응답이나 12개 packet을 독립 환자로 해석하면 안 된다.

| 지표 | concat | paired |
|---|---:|---:|
| P0 대비 평균 drift | 4.491 | 4.620 |
| P0–P6 annotation-proxy BA | 0.964 | 0.917 |
| 모든 조건에서 맞힌 packet 비율 | 0.833 | 0.667 |
| drift가 감소한 case | — | 0/3 |

paired의 drift는 2.9% 증가했고, 정답 응답은 81/84에서 77/84로 감소했다. N drift 감소 46.0%와 E drift 증가 17.7%도 저장 결과와 일치한다.

- **baseline:** unique-slice mean의 BA 0.988, worst-context 0.917은 유효한 비교 기준이다. IAF는 E 입력 36개 중 15개에서 E slice를 모두 제거했고 보존율은 0.292였다. 이는 현재 전처리·threshold에서 구현한 IAF ablation의 결과다.

# Problems / Concerns

1. **baseline의 drift 기준을 구분해야 한다.** [집계 코드](/SSD1_1TB/home/milab/daniel/08_medgemma/research/analyze_context_pilot.py:83)는 방법 자체의 P0 대비 `drift_own`과 공통 concat P0 대비 `drift_vs_packet`을 모두 계산하지만 보고서는 전자를 중심으로 비교한다. unique mean은 각각 4.369와 4.614다. 따라서 concat의 4.491보다 원래 packet 점수를 더 잘 복원했다고 주장할 수 없다. paired의 실패 판정은 두 기준이 같아서 영향을 받지 않는다.

2. **flip 설명이 부정확하다.** P0 대비 flip이 P4/P6에만 있다는 설명은 양성 packet의 오답 전환에 한정해야 한다. `00005/t2w/N`은 P0에서 +1.125였지만 P1–P6에서는 모두 음수가 되어 정답으로 바뀐다. context가 오류를 유발한 경우와 기존 오류를 교정한 경우를 분리해야 한다. P1/P2/P3 상호 간 flip이 없다는 설명은 맞다.

3. **reference 실패의 원인은 확정되지 않았다.** N/R/A/B가 인접 해부 수준에 몰린 것은 manifest와 montage에서 확인된다. 특히 `00002`의 empty slice 비영점 면적은 E의 약 31–48%다. 그러나 reference 인접성·뇌 면적·해부학적 위치를 각각 조작하지 않았으므로 이를 실패의 확정 원인으로 쓰면 안 된다. annotation-empty는 임상적으로 정상이라는 뜻도 아니다.

4. **사후 비례 분석은 기전 증명이 아니다.** 일부 평균에서 `00005/t2w`를 제외했고 log-odds 비율은 기준 점수와 부호에 민감하다. E/N/R의 평균 비율 차이는 추가 가설의 근거일 뿐, 선택적 희석의 원인이나 모든 비례형 reference 보정의 불가능성을 입증하지 않는다.

5. **예산 축소 구현에 실제 버그가 있다.** [추론 코드](/SSD1_1TB/home/milab/daniel/08_medgemma/research/run_context_pilot.py:210)의 `for ... in enumerate(todo)` 실행 중 `todo`를 새 목록으로 재할당해도 기존 iterator는 원래 목록을 계속 순회한다. 따라서 T1CE 축소를 기록하고도 T2 요청을 실행할 수 있다. 이번에는 축소 조건이 발동하지 않아 본 결과에는 영향이 없다. budget도 정상 종료 때만 저장되어 비정상 종료 후 사용량이 누락될 수 있다.

6. **재개·집계의 동일 입력 보장이 불완전하다.** [집계의 load](/SSD1_1TB/home/milab/daniel/08_medgemma/research/analyze_context_pilot.py:28)는 version/status만 확인하고 ID별 마지막 결과를 채택한다. config·요청 hash 대조가 없으며, runner도 실제 PNG를 다시 hash하지 않고 요청에 저장된 hash를 신뢰한다. 현재 산출물은 직접 대조해 일치를 확인했지만 재사용 전에 수정해야 한다. 일부 요청 누락 시 case-sequence를 제외하고 진행 기준을 계산하는 동작도 명시적인 미완료 판정으로 바꿔야 한다.

7. **범위와 leakage:** prompt에 GT나 packet 역할이 직접 들어가는 경로는 확인되지 않았다. 다만 E/N/R/context 구성 자체가 segmentation 기반이며 paired와 packet-only는 oracle이다. 모든 방법이 GT로 구성한 pilot 입력에서 평가됐으므로 배포 성능으로 해석할 수 없다. 독립 환자는 3명이고 최종 평가용 holdout은 없다.

8. **계획 이탈과 비교 한계:** 요청 수는 계획 258개보다 36개 많았다. P0 IAF 12개와 반복 측정 24개라는 설명은 파일과 일치하고 시간 예산은 지켰다. IAF 저자 구현 대조와 선행 연구 원문 재검증은 이번 실행에서 수행되지 않았으므로 전체 MedPruner의 실패나 신규 contribution을 주장할 근거는 없다.

# Interpretation

H1의 context 민감성 부분은 지지되지만, 정확도와 안정성을 회복할 만큼 유용한 공통 가산 성분은 확인되지 않았다. H2는 이번 사전 기준에서 실패했다.

같은 context에서 E와 N에 동일한 reference 항을 빼므로 `m_corrected(E,C)−m_corrected(N,C)=m(E,C)−m(N,C)`다. 이 보정은 결정 threshold에 대한 위치를 바꿀 수 있지만 E–N 분리 자체를 복원하지 못한다. 보고서에서 concat과 paired의 margin이 동일한 것은 이 수식의 필연적 결과다.

또한 context 추가 후 concat BA가 packet-only보다 높다는 점은 P0 복원이 항상 정확도 개선과 같은 목표가 아님을 보여준다. 향후에는 유해한 context 효과와 유익한 정보 통합을 구분해야 한다.

이번 결과의 가치는 저비용 pilot으로 한 방법 가설을 반증하고 강한 단순 baseline을 확보한 데 있다. 논문 수준의 해결책이나 일반화는 아직 확보하지 못했다. 접근법 abandon 및 재사용 코드의 결함 때문에 이번 변경은 커밋 대상으로 승인하지 않는다.

# Recommended Next Experiment

1. paired 계수나 reference를 현재 3 case 결과에 맞춰 조정하지 않는다. 남은 후보인 질문 조건부 2D 근거 선택으로 전환하고, 기존 선택·집계 방법과 구별되는 가설을 먼저 명시한다.
2. 재사용 코드의 예산 축소, 종료 시 사용량 기록, config·실제 입력 hash 확인, 누락 결과 판정을 보완한다. 기존 산출물로 지표 정의와 flip 설명도 정정한다.
3. 새 선택 규칙은 GT 없이 작동하도록 고정하고 concat, unique mean, max 및 동일 비용의 단순 선택 baseline과 비교한다. GT packet-only는 oracle 상한 참고로만 둔다.
4. 근거 보존과 근거 제거 대조군을 함께 두고, context의 해부학적 수준·면적·중복량·위치를 가능한 범위에서 분리한다. 적절한 음성 proxy를 만들 수 없으면 해당 비교를 제외한다.
5. 현재 3 case는 개발용으로만 사용한다. 확장 데이터의 사용 조건과 subject 대응을 확인한 뒤 독립 subject에서 정확도·공통 기준 drift·방법 자체 drift·worst-context·전체 추론 비용을 함께 평가하는 소규모 계획을 세운다.