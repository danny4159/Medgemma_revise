# 요약

- **판정:** CONTINUE / abandon. 실제 비교는 유효하지만 현재 G 설계의 추가 투자는 중단한다.
- **핵심 근거:** full-train V400 양성 200명에서 G−U S_loc은 +0.00125였다. G−C 최종 대 최종은 −0.02583이며 95% CI는 [−0.05800, 0.00450]이다.
- **의미·한계:** 기하 가중의 추가 이득을 입증하지 못했다. GPU 수치 검사 A는 실패 상태이며 전체 기하 supervision의 무효나 신규 contribution을 주장할 수 없다.
- **다음:** 후속 loss 탐색을 자동 연장하지 않는다. 기존 checkpoint 진단과 다른 연구 질문을 포함해 다음 투자 방향을 deep 계획에서 비교한다.

# Assessment

계획한 탐색과 full-train의 실제 학습·생성 비교가 완료됐다. 탐색 C는 iter_013의 호환성 검증된 trajectory를 재사용했고 U/G는 각각 train1200, 225 updates를 실행했다. full C/U/G는 각각 train2400, 450 updates를 실행했다. C_compute와 독립 확인은 미실행이며, full 결과가 진입 기준에 미달했으므로 추가 실행하지 않은 것은 적절하다.

valid_experiment=true는 현재 구현으로 수행한 실제 생성 비교가 해석 가능하다는 뜻이다. 모든 구현 gate 통과나 원 계획과의 완전한 수치 등가성 승인을 뜻하지 않는다. SELF_CHECK: FAIL은 유지한다. 같은 길이의 suffix 교체 검사와 C 환원 검사는 통과했고, 저장 결과의 독립 검산도 일치해 전체 실행을 execution_failed로 분류할 근거는 부족하다.

abandon은 이 후보·학습 조건의 추가 투자에 대한 판단이다. 횟수만으로 결정하지 않았다. 한 번의 확대 이후에도 C/U 대비 목표 효과가 없었고 G의 pilot 학습 시간이 C의 약 3.10배였다는 근거를 함께 고려했다.

# Key Findings

## 원시 결과 검산

리뷰에서 9개 checkpoint의 V400 원시 응답 3,600건을 별도 JSON parser와 최대 cardinality matching으로 재계산했다. checkpoint마다 400개 요청에 누락·중복이 없었고 모두 유효 JSON 및 EOS 종료였다. S_loc·F1@0.5와 환자 bootstrap 10,000회의 비교 CI가 저장 결과와 일치했다.

| 비교 | S_loc 차이 | paired 95% CI |
|---|---:|---:|
| explore G−C, 선택 기준 | +0.00908 | [−0.02042, 0.03975] |
| explore G−C, 최종 대 최종 | −0.01908 | [−0.04292, 0.00500] |
| full G−C, C fallback 기준 | −0.04142 | [−0.07467, −0.00817] |
| full G−C, 최종 대 최종 | −0.02583 | [−0.05800, 0.00450] |
| full G−U, 선택·최종 동일 | +0.00125 | [−0.01608, 0.01825] |

full 최종 S_loc은 C 0.50858, U 0.48150, G 0.48275다. 주된 근거 파일은 `research/results/iter_014/{explore,full}/{report,decision}.json`과 각 trajectory의 `epoch_*/val_gen/gen_worker*.jsonl`, `v400_epoch*/gen_worker*.jsonl`이다.

C fallback은 epoch1이며 V200 선택 적격이 아니다. V400에서도 NoOpacity/NotNormal valid_empty가 B0보다 8 percentage points 낮아 guardrail을 탈락했다. 따라서 −0.04142를 동일 운영 조건에서 확인된 확정적 열등성으로 제시하면 안 된다. 최종 C/U/G는 V400 guardrail을 통과하지만, full C는 V200에서 선택된 checkpoint가 없었다는 사실도 유지해야 한다.

## 입력·코드·학습 연결

리뷰 SHA는 `698c161f51ec098b1263ea8a5acf4d2870930e0b`다. `changes.patch`를 검토했고 변경 소스 14개가 해당 SHA와 일치했다. main protocol에 잠긴 59개 파일의 현재 hash도 모두 일치했다. `reuse_manifest.json`은 요청 파일이 없어 선별 반입 검사가 필요한 경우가 아니다.

현재 train·validation 영상 2,800개의 file/pixel hash 불일치는 0이었다. manifest의 train/validation/기존 confirm 간 환자 ID와 pixel hash 교집합도 0이었다. 새 생성 4,400행의 protocol·adapter metadata·prompt 이름·영상 파일 hash·RGB padding 후 pixel hash·affine 연결에 불일치가 없었다. adapter tensor digest 자체를 리뷰에서 다시 계산한 것은 아니다.

탐색 subset은 양성 600명과 음성 각 300명이며 V200은 양성 100명과 음성 각 50명이다. C/U/G의 각 단계별 batch ID 순서·LR·원래 assistant token 수가 일치했다. 새 학습 5개 trajectory는 총 1,800개의 고유 update와 28,800 patient presentations를 기록했고 loss·gradient norm은 모두 finite였다. 과거 C의 재사용은 `explore/compat_C.json`에 연결돼 있다.

저장 검사는 CPU 수식·span 37/37, 평가 11/11, pilot3 실행기 29/29, 결정적 중간-step 재개 7/7이다. GPU 묶음은 5/6이다. 이 수치는 저장 기록과 구현을 대조한 것이며 리뷰가 테스트나 모델 실험을 재실행한 것은 아니다.

## 자원 사용

두 GPU에서 U/G를 병렬 학습하고, 완료된 GPU에 후속 C 또는 생성을 배정했다. 탐색 pipeline은 약 4시간, full pipeline은 약 8시간 50분 실행됐다. CPU 준비나 작은 동작 확인에서 멈춘 반복이 아니다.

생성 pilot의 48개 요청에서 1 worker는 13.20 req/min, 2 worker는 22.44 req/min이었다. 48/48 greedy token 일치와 각 실행의 48개 고유 요청을 확인했다. 2-worker GPU peak는 17,765 MiB로 기록됐다. 실제 학습 로그의 peak allocated memory는 약 10.22–10.48 GiB다. 저장 GPU 조회와 정상 종료 로그는 현재 실행의 안전성과 완료를 뒷받침한다.

# Problems / Concerns

현재의 제한된 실제 생성 비교를 무효화할 blocking issue는 확인하지 않았다. 다음 문제는 완전한 계획 준수 주장과 재사용 승인을 제한한다.

1. **GPU 사전 gate가 실패했다.** A의 최대 logit 차이는 1.5, NLL 차이는 0.11606으로 허용치 0.05/0.02를 넘었다. 같은 길이에서 suffix를 바꾼 A1은 차이가 0이고 길이만 바꾼 A2도 비슷한 변화를 보였다. 이는 길이에 따른 수치 차이 설명을 지지하지만 gradient 영향이나 학습상 무해성을 증명하지 않는다. 실패 후 추가한 검사를 원래 gate 통과로 바꾸면 안 된다.
2. **실행 규약 변경 기록이 부족하다.** 구현은 bracket과 합쳐진 앞 공백·뒤 쉼표를 span에 포함한다. 명시적으로 검사하므로 조용한 절단은 아니지만 원 계획의 배열 경계 규약과 다르다. `execution_amendment.md`는 없었다.
3. **확대 규칙에 해석 차이가 있다.** explore는 선택 비교가 양수이고 최종 G−C가 음수인데 보완 경로로 확대됐다. Claude는 부호 보류를 일반 확대에만 적용한다고 해석했다. 원 계획에는 그런 제외가 명시적이지 않다. 수치상 보완 조건을 만족한 것은 맞지만 완전한 사전 규칙 준수로 단정하지 않는다. 이미 수행한 full 결과는 보존하고, 다음 자동 확대 전에 적용 범위를 분명히 해야 한다.
4. **판정 표시와 미사용 계산량 설정에 결함이 있다.** full의 `final_opposes_selected=true`는 선택·최종 차이가 모두 음수인데도 표시된다. 또한 C_compute K는 계획의 `ceil(450×max(1,r))` 대신 `450×ceil(max(1,r))`로 구현됐다. C_compute는 실행되지 않아 현재 비교에 영향은 없다.
5. **재사용 시 자원·완전성 검사를 보완해야 한다.** 복수 worker 메모리 검사에는 worker당 여유가 합산되지 않는다. `on_gpu`는 조회 결과가 없을 때 fail-closed가 아니며 `gen_compare`는 중복 ID를 덮어쓴다. 이번 자료에서 중복이나 관련 실행 장애는 확인되지 않았다.
6. **보고서 저장이 불완전하다.** `claude_report.md`는 마지막 대기 알림 답변이다. 전체 보고서는 `claude_stream.jsonl` 3104행에서 확인했다. 마지막 짧은 보고서만으로 승인하지 않았다.

`unpreserved_paths`의 `test_rsna_iter010_gpu.py`와 위 재사용 문제가 있으므로 전체 snapshot은 승인하지 않는다. 사용하지 않는 과거 실행기의 전면 정비를 다음 연구의 선행조건으로 요구하지는 않는다.

# Interpretation

현재 G의 추가 가치가 입증되지 않았다는 결론은 유지된다. G와 U가 동등하다는 증명은 아니며, 최종 G가 C보다 통계적으로 확정된 열등성을 보였다고 말할 수도 없다. 개발 validation의 반복 선택과 single seed 때문에 CI는 checkpoint 선택 불확실성·seed 변동·외부 일반화를 포함하지 않는다.

U도 같은 GIoU-filtered 후보와 GT 질량을 사용한다. 따라서 G−U는 후보 사이 가중 배분의 효과를 비교하며, 모든 기하 정보의 유무를 비교한 것은 아니다. 추가 이득 부재를 내부 표현 병목, 영상 미사용 또는 anatomy 전이 필요성의 증명으로 연결하지 않는다.

iter_009의 정상 사용 검증과 iter_012의 직접 SFT 개선 결론은 바뀌지 않았다. 공식 예제·revision·전처리·출력 규약은 기존 검증 범위를 재사용했고 이번 리뷰에서 공식 GPU 예제를 재실행하지 않았다. reserve 독립 확인은 수행하지 않았다. 따라서 limitation_updates는 비워 둔다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 실제 C/U/G 학습과 생성 비교, 입력 연결 및 독립 점수 검산은 확인됐다. GPU 수치 등가성 gate의 실패는 별도로 남는다.
- **성능 개선:** G의 추가 개선은 확인되지 않았다. guardrail을 탈락한 C fallback 비교와 최종 대 최종 비교를 구분해야 한다.
- **가설 지지:** 현재 후보·LR·학습량에서 기하 가중이 직접 SFT와 동일 후보 U를 함께 넘는다는 가설은 지지되지 않는다. 전체 기하 supervision의 무효를 뜻하지 않는다.
- **신규 기여 가능성:** 선행 loss 이식 자체의 contribution은 확인되지 않았다. 강한 직접 SFT 이후의 실제 능력 변화와 모듈형 대안 대비 가치도 아직 미확인이다.

다음 투자 선택은 세 가지다. 현재 G 개선은 후보·수치 조건을 더 조사할 수 있지만 비용 대비 우선순위가 낮다. 기존 checkpoint의 능력 전이·원인 진단은 새 학습 없이도 좌표 형식 적응과 더 일반적인 시각 능력을 구분할 가능성이 있다. 다른 의료 VLM 질문으로의 전환은 더 높은 중요성·차별성이 확인되면 합리적이다. 이번 리뷰는 G 추가 투자를 중단하고 다음 계획에서 이 셋을 비교하도록 권고한다. 특정 진단이나 faithfulness를 새 최종 목표로 고정하지 않는다.

이번 G 방향에는 후속 탐구를 추천할 긍정적 개선 근거가 없고 다음 전략도 미확정이므로 논문 추천은 보류한다.

# Recommended Next Experiment

첫 작업은 새로운 loss 구현이 아니라 연구 방향 비교다. 기존 base·SFT·추가 SFT의 재사용 가능한 평가 자산을 확인하고, 좌표 출력·의미가 달라진 질문의 영역 선택·근거를 활용한 판단을 구분하는 진단을 우선 후보로 검토한다. 단순 prompt 표현 변경이나 JSON 적응을 시각 능력 전이로 해석하지 않는다.

내부 위치 학습을 계속할 가치가 있다고 판단하면 강한 직접 SFT와 detector+VLM 또는 encoder+head 비교 경로를 포함한다. box에서 파생한 개수·위치 QA에는 검출+규칙 baseline을 고려하고 임상 reasoning의 증명으로 삼지 않는다. 더 가치 있는 다른 질문이 있으면 근거를 남기고 전환할 수 있다.

다음 계획은 중요한 사용 과제, 경쟁 설명, 세 전략의 정보 이득·비용, 양성·음성·불확정 결과별 행동과 중단 조건을 고정해야 한다. 실제 사용할 코드의 결함만 우선 보완하며, 현재 결과를 다시 유리하게 선택하거나 reserve를 개발에 소비하지 않는다.