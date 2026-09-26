# 요약

- **판정:** CONTINUE / inconclusive. 실제 가설 비교는 완료했으므로 valid_experiment=true다. 현 설정의 제한적 음성 결과를 보존한다.
- **핵심 근거:** V400 양성 200명에서 최종 S_loc은 C 0.5221, H 0.5204, D 0.5253이다. 독립 재계산한 D−C는 +0.0032, 95% CI [−0.0136, +0.0203]이다.
- **의미·한계:** 자리별 거리 항의 추가 가치는 이번 설정에서 약하다. D는 V200 선택 조건을 통과하지 못했지만 최종 V400 유지 조건은 통과했다. 방법 전체의 실패나 수렴 완료를 뜻하지 않는다.
- **다음:** 자동 확대는 보류한다. 오류 분해·선택 상태 표시와 실행기 재사용 결함을 보완하고, 다음 방법 후보를 비교한다.

# Assessment

계획한 가능성 탐색은 실제 수행됐다. 공통 B0에서 C/H/D 각각 train 1,200명, effective batch16, seed17, LR 2e-5, 3 epochs·225 updates를 학습했다. 조건별 3,600 presentations이며 225개 step의 batch ID·token digest·LR·assistant token 수가 조건 간 일치했다.

V200 milestone 9개에서 총 1,800개 요청의 ID 완전성을 확인했다. C/H의 선택 epoch1과 세 조건의 최종 epoch3에 대해 V400을 평가했다. 확대·추가 seed·새 독립 확인·Kvasir-SEG는 미실행이다. 사전 진입 조건을 충족하지 못했으므로 이 보류는 적절하다.

SELF_CHECK: FAIL은 GPU 검사 묶음의 미완전한 통과 기록을 반영한다. 이를 본학습 미실행 또는 가설 검증 전체 실패로 바꾸지 않는다.

# Key Findings

## 실제 결과와 독립 검산

| 조건 | 최종 F1@0.3 | 최종 F1@0.5 | 최종 S_loc | V200 선택 |
|---|---:|---:|---:|---|
| B0 | 0.6405 | 0.3550 | 0.49775 | 시작점 |
| C | 0.6575 | 0.38667 | 0.52208 | epoch1 |
| H | 0.6625 | 0.37833 | 0.52042 | epoch1 |
| D | 0.6705 | 0.38000 | 0.52525 | 없음 |

리뷰에서 별도 JSON parser와 재귀적 최대 cardinality matching으로 5개 V400 checkpoint의 점수를 재계산했다. 환자 단위 bootstrap 10,000회로 D−C와 D−H의 CI도 저장 결과와 일치했다. D−H는 +0.00483, 95% CI [−0.01325, +0.02250]이다. 각 V400 평가의 400개 ID에 누락·중복이 없었다.

주요 근거는 `research/results/iter_013/explore/report.json`, `decision.json`, 각 trajectory의 `epoch_*/val_gen/gen_worker*.jsonl`과 `v400_epoch*/gen_worker*.jsonl`이다. 독립 검산은 저장 결과의 읽기 전용 재계산이며 모델 실험을 추가 실행하지 않았다.

## 코드·입력·실행 연결

`commit.json`의 리뷰 SHA는 `d68840e0f9317700a8b585bcf6edbb8ef73703a0`이다. 구현 전후 diff를 확인했고 현재 tracked 파일은 해당 SHA와 모두 일치했다. main protocol에 잠긴 49개 파일의 현재 SHA256도 모두 일치했다.

새 원시 응답 2,800행의 protocol·prompt digest 불일치는 0이었다. 9개 epoch와 5개 V400 결과의 adapter digest metadata 연결 및 V400 자식 종료 코드 0을 확인했다. 학습 3개 작업도 pipeline 로그에서 rc=0이다.

저장 CPU 검사 43건은 좌표 tokenization, loss 수치, mask·shift, subset·입력 연결과 평가 검사를 포함한다. 실제 모델의 loss 성분과 독립 float64 기준 계산도 일치했다. 결정적 D 재개 검사에서는 batch·LR·RNG·optimizer step·loss 및 최종 adapter digest 일치가 기록돼 있다.

리뷰 환경의 `python`에는 torch가 없어 기존 `eval_gate.verify_gen` 직접 호출은 import 단계에서 실패했다. 따라서 이번 리뷰가 adapter tensor digest와 전체 gate를 재실행했다고 주장하지 않는다. 파일 hash, 원시 metadata, 별도 metric 검산 및 Claude의 저장 검증 기록을 대조했다.

## 표본·자원 정책

train1200은 양성 600명과 음성 각 300명, V200은 양성 100명과 음성 각 50명이다. train/validation ID 교집합은 0이고, 저장 검사에는 환자·pixel 중복 및 실제 입력 hash 검증이 있다. subset의 3·4개 병변 환자도 포함됐다. V200/V400은 개발 자료이며 독립 확인으로 취급하지 않았다.

두 GPU에서 C/D를 병렬 학습하고 H를 후속 실행했다. 빈 GPU에는 완료된 checkpoint의 추론을 배정했다. 학습·평가 구간 wall-clock은 약 3.4시간이다. microbatch2/4를 비교했고, 추론은 GPU당 2 worker가 12.70→21.08 req/min으로 빨라지며 48/48 출력 token이 일치해 채택했다. CPU 준비나 동작 pilot에서 멈춘 반복이 아니다.

# Problems / Concerns

현재의 제한된 비교 결론을 무효화할 blocking issue는 발견하지 않았다. 다음은 해석 정정 또는 재사용 문제다.

1. **V200 선택 탈락과 V400 성능을 구분해야 한다.** D는 V200의 NoOpacity/NotNormal valid_empty가 B0 31/50에서 29/50으로 낮아져 4 percentage points 감소했다. 허용치는 3 points이므로 모든 milestone이 탈락했다. 반면 최종 V400에서는 세 조건 모두 B0 대비 해당 감소가 3 points여서 guardrail을 통과했다. `decision.json`의 `D_guardrail_v400_ok=false`는 실제 final V400 실패가 아니라 선택 후보 부재에서 나온 값이다.
2. **비교 checkpoint가 섞인 값을 선택 결과로 읽으면 안 된다.** `D_selected_S_loc`은 D final 값이고 C는 선택 epoch1이다. 이때 차이는 +0.03133이나 D가 선택 적격이 아니므로 확대 근거가 아니다. 보고서의 '어느 해석으로도 0.03 미만'이라는 표현은 과도하다. 최종 대 최종 비교 CI 상한이 0.03 미만이라는 사실로 한정해야 한다.
3. **오류 분해에서 환자가 누락된다.** `adapt_eval.detail`의 multi는 `ng == 2`로 구현돼 3개 이상 병변을 가진 V400 양성 7명을 제외한다. 전체 주지표에는 포함되므로 S_loc 결론은 유지되지만 오류 유형 분석은 수정해야 한다.
4. **실행기 재사용 안전성이 부족하다.** GPU 허용 집합을 검증하지 않고 환경 변수를 재설정하며, train.lock 파일이 있으면 메모리 확인을 생략한다. 완료 검사도 요청 stage·loss·LR과 기존 완료 근거를 충분히 대조하지 않는다. 이번 0,1 실행의 관측 결과를 무효화하지는 않지만 다음 실행 전에 보완해야 한다.
5. **GPU 검사 기록을 정확히 해석해야 한다.** 전체 묶음은 27/29였고 E 단독 보완이 뒤따랐다. 동일 함수 반복 gradient 차이는 상대 L2 1.15%, C/H/D와 기존 CE 차이는 1.34–1.37%였다. 이 측정은 엄격한 절대 기준 실패를 설명하지만 bitwise 등가 증명은 아니다. pilot의 전체 GPU peak 23,807 MiB에는 E OOM 구간이 포함되므로 정상 동시 worker 안전 여유의 근거로 쓰면 안 된다.

`unpreserved_paths`와 이전 미사용 실행 경로의 결함도 남아 있어 전체 스냅샷 재사용은 승인하지 않는다. 파일 읽기만으로 모듈을 승인하지 않았으며, code_assets의 승인은 실제 저장 검사·실행 근거가 있는 범위로 제한했다.

# Interpretation

D의 최종 대 최종 추가 이득은 C와 H 모두에 대해 작다. 이 설정을 곧바로 전체 train·여러 LR·다중 seed로 확대할 근거는 얻지 못했다. 동시에 D의 V200 S_loc은 마지막 구간에 0.0245 상승했고 선택 gate는 음성 50명에서 환자 두 명 차이로 탈락했다. 따라서 수렴이나 더 넓은 방법 계열의 무효를 선언할 수 없다.

기존 정상 사용 조건의 한계 검증과 직접 LoRA SFT 개선 결론은 바뀌지 않는다. 이번 결과는 새로운 독립 한계 재현도 아니므로 limitation_updates는 비워 둔다. 공식 sanity 전체를 반복하지 않고 검증된 규약 위에서 실제 생성 비교를 진행한 점은 사용자 보완 지시와 일치한다.

# Recommended Next Experiment

현재 결과와 baseline을 보존한다. 우선 3개 이상 병변의 오류 분해를 복원하고, 위치 정밀도·작은 병변·빈 응답 중 다음 방법이 해결할 대상을 정한다. 이를 근거로 자리별 loss의 추가 탐색과 box 기하 supervision 후보의 정보 이득·기여 가능성을 비교한다.

현재 결과를 보고 guardrail을 완화하거나 D final을 사후 선택해 확대하지 않는다. 후속 실험은 새로운 계획과 결과 경로에서 강한 직접 SFT·관련 방법 baseline, 동일 선택 예산, 실제 생성 지표 및 확대 기준을 고정한다. reserve는 방법·설정이 확정될 때까지 보존한다.