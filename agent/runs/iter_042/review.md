# 요약

- **판정:** CONTINUE / inconclusive. 실제 비교는 유효하며 현재 방법 투자를 보류한다.
- **핵심 근거:** presence gate는 음성 false-box를 39/40에서 1/40로 줄였지만, 양성 F1 차이의 CI가 허용 손실 −0.05를 넘어서지 못했다.
- **의미·한계:** 중립 grounding의 잔여 오류는 확인했다. 단순 gate 이후에도 새 방법이 필요한지는 입증하지 못했다.
- **다음:** 고정 후보 전수 진단을 종료한다. 같은 진단을 확대하지 않고 다음 연구 투자 방향을 선택한다.

# Assessment

검토 SHA는 `e7ee15464cf404a44a877997661b9f50dd8c3096`이다. 대상 소스 21개와 현재 작업 파일이 일치했고, 선별 반입 12개 파일의 blob도 원본과 일치했다. `unpreserved_paths`는 비어 있다. 계획·plan.json·보고서·diff·reuse_manifest·관련 소스·원시 출력·검사 기록과 의심 구간의 실행 로그를 확인했다. execution_amendment는 없다.

원 계획은 처음부터 PadChest였다. 보고서의 ‘RSNA 대신’은 계획 변경이 아닌 오기다. E 양성 29명·음성 40명은 사전 최소 24/32를 충족한다. M0/C 각 207건, 총 414건의 본생성을 완료했고 worker 종료 코드는 모두 0이다. 학습과 독립 확인은 미실행이다.

`SELF_CHECK: FAIL`은 엄격 보조 parser와 기존 parser의 차이를 반영한다. 기존 평가 규칙을 사후 변경한 것은 아니며, 리뷰의 독립 재계산으로 현재 수치를 확인했으므로 실행 실패로 판정하지 않는다.

# Key Findings

## 실제 출력과 독립 재계산

| 시스템 | 양성 F1@0.3, n=29 | 음성 nonempty / empty / invalid, n=40 |
|---|---:|---|
| M0_short | 0.01724 | 40 / 0 / 0 |
| M0_neutral | 0.12874 | 7 / 33 / 0 |
| C_short | 0.40805 | 39 / 0 / 1 |
| C_neutral | 0.38506 | 20 / 0 / 20 |
| P0 gate | 0.38506 | 1 / 39 / 0 |
| PC gate | 0.36782 | 1 / 39 / 0 |

원시 JSON을 별도로 해석하고 GT를 canvas로 변환한 뒤 최대 matching으로 F1@0.3·0.5를 재계산했다. 저장 환자별 점수·음성 집계와 일치했다. seed20261001, 환자 paired bootstrap 10,000회로 모든 저장 비교 CI도 재현했다.

P0/PC gate의 C_short 대비 양성 F1 차이는 각각 −0.02299와 −0.04023이다. 95% CI는 [−0.13218, 0.07471], [−0.15517, 0.06322]다. 두 gate 모두 음성 false-box 감소는 0.95이고 감소 CI 하한은 0.875다. 잔여 1/40의 Wilson 상한은 0.12881이다. 음성 개선은 크지만 사전 양성 보존 기준을 충족하지 못했다.

C_neutral 대비 P0 gate의 양성 환자별 F1은 모두 동일했다. PC gate의 평균 손실은 0.01724였다. 따라서 단순 gate 이후 큰 양성 손실 또는 큰 음성 오류라는 pilot 조건도 충족하지 않는다. C_neutral 자체도 F1 0.38506<0.40, invalid 21/69>5%로 core gate를 통과하지 못한다. `inconclusive_or_negative_hold`는 계획과 일치한다.

presence sensitivity는 M0 28/29, C 26/29이며 specificity는 모두 39/40이다. 사전 민감도 분석에서 명시적 pleural 음성 21명의 P0 gate false-box는 0건이었다. 이 부분집단으로 원래 판정 기준을 교체하지 않는다.

## 입력·출처·사용법

원본 metadata에서 후보 양성 30·음성 41건을 재현했다. 최종 E의 환자·study·영상·문장·GT 연결을 확인했고 기존 제외 manifest와 환자·영상·원본 pixel 중복은 없었다. 출력 전 의미 검토 기록과 음성 영어·스페인어 문장을 확인했다. 양성 1건의 과거 보고 언급과 음성 1건의 부분 부재 진술 제외는 기록돼 있다. 양성 hedge 8건과 bare effusion 음성 19건의 해석 범위는 유지한다.

D/E 원본 ZIP 영상 75개에서 raw PNG, uint16 pixel, uint8 변환, padding 후 요청 pixel hash를 검증했다. 대표 GT overlay도 확인했다. 이는 임상 재판독이나 annotation 완결성의 독립 증명은 아니다.

450개 고유 D/E 요청의 prompt·target·caps를 명세와 대조했다. 본실험 414건의 record·요청·protocol·config·adapter 및 worker file digest가 일치했다. 공식 template·값 보존 전처리는 iter_039의 검증과 동일 소스 범위에서 재사용했다. 각 모델 G_short 1건은 1000/2000/4000 재시도 후에도 비EOS였으며 invalid로 포함됐다.

## 자원과 완료

D의 2 worker와 4 worker wall 합은 135.61초와 90.47초였다. 공통 36건의 token은 모두 같아 약 1.50배 처리량 개선을 확인했다. E는 두 GPU에 각 2 worker를 배치했다. 관측 peak는 M0 17,674/17,537 MiB, C 17,836/17,829 MiB로 이번 조건에서는 worker당 2 GiB 여유를 확보했다.

E 두 큐의 wall 합은 1,702.92초다. D 비교·재개 완료 큐와 부분 실행을 포함한 기록된 launcher wall 합은 약 2,034.47초, 33.9분이다. 준비·CPU 검사 시간과 구분한다. E의 loading 포함 GPU 점유 구간 합은 약 0.648 GPU-hours이며 실제 조건부 gate 서비스 latency는 아니다.

# Problems / Concerns

현재 수치와 투자 보류 결론을 무효화하는 문제는 발견하지 못했다. 다음 해석과 재사용 문제는 남는다.

- C_neutral의 음성 20건은 unknown label 때문에 invalid지만 label을 무시하면 box가 있다. valid false-box 0.50을 부재 거부 성공률 0.50으로 읽으면 안 된다. 보수적 실패율은 40/40이다.
- 보고서의 ‘SFT가 만든 악화가 아니다’는 G_short에 한정해야 한다. G_neutral에서는 C−M0 false-box +0.325, 97.5% CI [0.150, 0.500]로 사전 악화 관찰 기준을 충족했다. 다만 형식·질의 적응과 내부 능력 손상을 구분해야 한다.
- 엄격 verifier는 M0의 여분 닫기 괄호를 invalid로 처리했다. 기존 parser는 완결 목록을 추출한다. 현재 불일치는 설명됐지만 tolerant verifier가 뒤의 상충 JSON까지 무시할 수 있으므로 일반 재사용 전 보완이 필요하다.
- 평가 소스와 일부 의존성은 실행 전 protocol에 잠기지 않았다. 현재 digest·GT·원시 수치는 리뷰에서 확인했으나, required_checks 전체 완료로 표현할 수 없다.
- report와 per_patient의 묶음 완료 보호, build 중단 복구, worker당 메모리 기준 및 GPU 여유 순 배정은 재사용 전 수정한다. CPU/RAM/I/O 계측은 미완료다.

# Interpretation

존재 전제 질의에서 M0/C가 거의 항상 box를 반환한다는 관찰은 유효하다. 중립 질의만으로 M0의 부재 거부는 크게 바뀌지만 C의 정상 빈 출력은 회복되지 않았다. 이는 현재 인터페이스와 적응 조건의 차이다. 일반적인 시각적 forgetting 또는 모든 소견 판별 능력 상실은 증명하지 않는다.

presence gate의 음성 개선은 실제 관찰이다. 그러나 작은 양성 표본에서 허용 손실 이내라는 근거가 부족하므로 검증된 해법으로 부르지 않는다. 반대로 넓은 CI를 단순 baseline의 실패로 간주해 새 loss 투자를 정당화해서도 안 된다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 본생성·입력·출처·독립 수치 검증을 완료했다. valid_experiment=true다.
- **성능 개선:** 추가 학습 없는 gate의 음성 오류 감소를 확인했다. 정확도 보존과 실제 비용까지 포함한 실용 개선은 불확정이다.
- **가설 지지:** 현재 grounding 질의의 부재 거부 문제는 관찰됐다. 적응 악화는 prompt에 따라 다르며, 두 gate 이후 큰 잔여 문제는 입증되지 않았다.
- **신규 기여 가능성:** 직접 negative CE와 presence gate, 계획에서 확인한 MedGrounder류 zero/multiple-box 방법을 넘어설 근거는 없다. 이번 결과는 새 방법이나 full 확대를 승인하지 않는다.

`language-conditioned-grounding` track의 iter_038 준비, iter_039 진단, iter_040 방법 pilot, iter_041 공동 요청 진단과 이번 결과를 연결한다. 직접 SFT의 양성 grounding 개선과 공동 요청 손실은 이미 확인된 질문이다. 이번에는 실제 부재 영상의 반응과 단순 gate의 작동 범위를 추가로 확인했다. 남은 핵심은 강한 단순 대안 이후에도 중요한 정확도·비용 문제가 있는지다.

과거 기록의 약 4.21시간 생성 wall, 약 2.54 GPU-hours 학습, 일부 큐 약 1.123 GPU-hours와 이번 비용은 집계 범위가 달라 단일 누적 GPU 비용으로 합치지 않는다. 준비·복구를 유효 실험 횟수로 세지 않지만, 이미 여러 차례 진단을 수행했다는 기회비용은 다음 선택에 반영한다.

현재 개선 연장은 pilot gate 미달이고, 같은 진단의 정밀도 확대는 원 decision_contract가 보류하도록 정했다. 따라서 다른 연구 질문으로의 전환 검토가 우선이다. 이는 모든 presence 방법을 기각한다는 뜻이 아니다. 향후 새로운 유효 근거가 단순 대안의 구체적인 부족함을 보여줄 때만 별도 최소 방법 시험을 재검토한다.

이번 방향의 방법 투자 판정이 불확정이고 양성 보존까지 확인된 해법이 없으므로 논문 추천은 보류한다.

# Recommended Next Experiment

현재 부재 거부 설계 투자를 보류하고 다음 deep 계획에서 연구 질문 하나를 선택한다. 같은 E의 prompt 수정·추가 환자·질환·seed 또는 negative SFT를 자동 실행하지 않는다.

실행 가능한 문장 조건부 모듈형 비교와 GOAL 안의 다른 후보를 기존 유효 근거, 강한 baseline, 실제 사용 가치 및 비용으로 비교한다. 최소 방법 시험을 선택하려면 연결할 한계, 단순 대안의 부족함, 구분할 경쟁 설명과 종료 조건을 구체화한다. 이 조건이 없으면 다른 질문으로 전환하고 같은 진단의 연장으로 결정을 미루지 않는다.

실제 사용할 코드 경로만 보완한다. 기존 RSNA·PadChest 결과와 checkpoint, continuation 투자 종료, VinDr 승인 대기 및 H192/F120/test/MRI reserve 보존은 유지한다.