# 요약

- **판정:** CONTINUE / success. 실제 detector 비교 진단은 유효하다. 전체 코드 재사용은 보류한다.
- **핵심 근거:** 양성400명에서 detector17−B0의 F1@0.3은 −0.0491, F1@0.5는 +0.0669였다. IoU0.3에서 detector만 검출한 GT는 71개, SFT만 검출한 GT는 77개였다.
- **의미·한계:** 빠진 전용 detector 비교군을 확보했다. 전반적 detector 우위, VLM 고유 능력, 외부 일반화와 새 contribution은 입증하지 않았다.
- **다음:** VinDr 승인 대기를 유지하며 연구 방향을 재검토한다. confidence·위치 오차·미검출을 구분하는 최소 진단의 정보 가치를 먼저 판단한다.

# Assessment

`plan.md`, `plan.json`, 보고서, amendment, 변경 diff와 리뷰 SHA `615c61ec51cfe9d84d564bfcaab434a3a5c78cb1`을 검토했다. 변경 파일의 현재 bytes는 해당 SHA와 모두 일치했고 working-tree status/diff는 비어 있었다. reuse_manifest는 빈 요청이었다.

이번은 실험 미실행이 아니다. seed17은 기존 update706에서 이어 총7,800 update, seed29는 연장 포함11,400 update를 완료했다. 각 canonical 로그의 update 연속성, 유한 loss, completion digest와 checkpoint hash를 독립 확인했다. 실제 LR은 update4800에서 0.005→0.0005, update6600에서 0.0005→0.00005로 바뀌었다. 최종 호스트 기록에는 detector 작업이 남아 있지 않았고 GPU 메모리는 87/15MiB였다.

연장 launch의 마지막 result.json은 재실행으로 덮어써져 all_ok=false다. 그러나 append 로그의 11,400-update 완료, 전체 학습 로그, checkpoint와 완료 marker가 일치한다. 이를 학습 미완료로 해석하지 않는다. 동시에 원본 launch 보존 문제는 수정 대상이다.

# Key Findings

## 1. 주수치 독립 검증

원시 detector 예측과 저장 SFT suffix를 읽고 별도 좌표 변환·matching·환자 bootstrap으로 재계산했다. parser는 기존 strict parser를 사용했다. 저장된 independent_verify의 PASS만으로 승인하지 않았다.

| 비교 | F1@0.3 차이와 97.5% CI | F1@0.5 차이와 97.5% CI |
|---|---|---|
| detector17−B0 | −0.049107 [−0.100001, 0.001752] | +0.066881 [0.012211, 0.121965] |
| detector29−B0 | −0.056833 [−0.107667, −0.005750] | +0.057750 [0.001166, 0.114084] |

주비교의 실제 점수는 detector17 0.581643/0.415548, B0 0.630750/0.348667이다. FP/환자 차이는 +0.02625, 95% CI [−0.01375, 0.06875]로 재현됐다. 따라서 두 F1의 CI 하한>0 및 FP 증가 CI 상한≤0.05를 요구한 전반적 우위 기준은 충족하지 않는다.

IoU0.3의 detector-only/SFT-only는 589개 GT 중 71/77개이며 63/70명에 분포한다. 비율 CI는 각각 [9.31%, 14.86%], [10.20%, 16.03%]다. IoU0.5에서도 119/67개의 양방향 차이가 있다. 사전 상보성 기준을 충족하지만 GT 합집합 recall은 실용 ensemble 성능이 아니다. detector FP budget1.0에서 SFT-only가 3.9%로 줄어드는 점은 상보성이 confidence 선택에도 의존함을 보여준다.

## 2. 선택·입력·학습 연결

LOCK에 연결된 파일 hash가 모두 일치한다. V400 저장 후보에 선택 규칙을 독립 적용해 seed17 epoch18/threshold0.70, seed29 epoch26/threshold0.60을 재현했다. 두 confirm 출력의 checkpoint·raw·shard hash와 source digest도 현재 보존 소스와 일치했다. 선택 잠금 시각은 confirm 실행보다 앞선다.

전체3,600명 감사는 file/pixel hash 불일치와 분할 중복0을 기록한다. SOP 연결과 사전학습 노출까지 검증한 것은 아니다. 기존 정상 사용 검증과 SFT 출력 출처를 재사용했고, 새 독립 환자를 열지 않았다.

결정적 재개 검사에서는 k2/k6/k15, 실제 SIGTERM/SIGKILL 이후 control·loss·parameter·optimizer 일치가 기록됐다. CLI20건과 추론13건도 통과했다. 다만 이 검사의 범위가 아래 모든 재사용 결함을 덮지는 않는다.

## 3. 자원과 비용

두 GPU에 학습·평가를 병렬 배치했다. 추론 pilot의 batch1 worker2는 worker1과 출력이 같고 처리량이 7.4→8.0 images/s였다. batch4는 후보 수와 score가 달라 채택하지 않았다. 학습 reserved peak는 약8GB, 추론 worker당 약766MiB로 기록됐다.

동일 GPU L64×3의 원시192건씩을 재집계했다. 평균 end-to-end는 detector 0.061785초, B0 4.299653초로 69.59배 차이다. 각각 p95는 0.065407초와 11.933731초다. FP32 detector와 bf16 autoregressive VLM의 현재 구현 비용이며 보편적인 구조 효율 비율은 아니다.

초기 latency JSON의 공식 tensor 불일치는 BOS 중복 검사기 문제였다. 수정 검사 결과64/64 입력 일치와 원래 측정의 저장 suffix64/64×3 재현을 함께 확인했다. 재측정 없이 현재 시간 비교를 유지할 근거는 있지만, 검사 실패에도 정상 종료하는 코드 경로는 보완해야 한다.

## 4. iter_031 잔여 분석

보완 코드가 추가 box와 원래 누락 GT identity를 비교하고 실제 중복 box 제거 후 재매칭하도록 수정됐다. 저장 결과의 IoU0.5 회복은 C201 4/20, E402 7/27이다. E402 dedup 후 F1@0.3은 0.48462로 원래 O의 0.62761보다 여전히 낮다. continuation 추가 투자 종료를 되돌릴 근거가 아니다. 이번 리뷰에서 이 보완 분석 전체를 tokenizer부터 독립 재실행하지는 않았다.

# Problems / Concerns

현재 제한된 비교 결론을 무효화하는 문제는 발견하지 못했다. 다음은 재사용 전에 해결해야 한다.

1. `det_jobs.py`의 추가 인자 무시와 result 덮어쓰기는 실제 사고로 확인됐다. 고유 launch 기록과 소유권 보호가 필요하다.
2. `det_train.py`는 연장 중 갱신되는 checkpoint와 이전 complete.json을 함께 유지한다. 연장 중단 후 재개가 이전 completion 검증에서 차단될 수 있다. 이번 연장은 완료됐으므로 현재 수치에는 영향이 없다.
3. `det_eval.py`의 완료 재사용은 현재 source/input/batch를 확인하지 않고 동일 out_dir 소유권 lock도 없다. 이번 파일은 별도로 대조했지만 코드 자체의 일반적 안전성을 승인할 수 없다.
4. 선택·분석 CLI에서 LOCK·cap·선행 완료 gate를 강제하지 않는다. latency 검사 실패도 실패 종료로 연결되지 않는다.

seed29의 38 epoch 수렴 판단에는 계획에 없던 0.01 기준이 사용됐다. utility는 epoch26/32/38에서 0.747/0.73867/0.748, F1@0.5는 0.396/0.40267/0.39133이다. 강한 계속 상승 신호는 보이지 않지만 '완전 수렴' 표현은 피한다. seed29 선행 시작도 절차상 이탈이나, trigger가 충족됐고 개발800 이전에 seed 집합을 잠가 선택 편향의 직접 증거는 없다.

보고서의 '+4.8초 추가 비용'은 F−O 차이다. E402의 F 호출 자체 평균은12.015초다. 실제 추가 호출 비용과 대체 실행 시간 차이를 혼동하지 않아야 한다.

# Interpretation

빠른 detector가 더 엄격한 IoU에서 높은 점수를 얻지만, 현재 선택점에서는 SFT가 검출하고 detector가 놓치는 GT도 남는다. 이 관찰만으로 SFT의 의미 이해나 작은 병변 발견 능력이 우수하다고 말할 수 없다. confidence, box 크기와 경계, annotation 의미가 경쟁 설명이다. 층별 결과는 탐색적이다.

개발800은 이전 후속 분석에 사용된 집단이다. 이번 CI는 이 집단의 환자 변동을 표현하며 독립 외부 확인을 대체하지 않는다. 두 detector seed의 같은 방향도 모델 계열 전체의 결론이나 신규 contribution이 아니다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 학습·선택·개발 비교·비용 측정과 독립 재계산을 완료했다. 재사용 결함은 현재 결과와 분리한다.
- **성능 개선:** detector의 F1@0.5 및 latency 이점을 확인했다. 전반적 우위는 미충족이고 새 post-training 방법의 개선은 없다.
- **가설 지지:** 정확도 trade-off와 선택점별 오류 상보성이 존재한다는 진단 가설을 지지한다. 원인과 실용적 결합 이득은 미확인이다.
- **신규 기여 가능성:** 강한 baseline 확보는 진전이지만 contribution 자체는 아니다. 잔여 차이가 단순 confidence·위치 보정으로 설명되는지 먼저 구분해야 한다.

다음 투자에서는 세 선택을 비교해야 한다. 현 bbox 방법 개선은 강한 detector 대비 잔여 가치가 먼저 필요하다. 저장 출력의 원인 진단은 비용이 작고 이를 구분할 정보 이득이 크다. 언어·근거가 필요한 과제로의 전환은 VLM 효용을 직접 검증할 수 있지만 유효한 정답과 강한 모듈형 대안이 선행돼야 한다. 따라서 최소 원인 진단을 우선 후보로 권고하되 새 최종 주제로 고정하지 않는다. VinDr 승인 대기를 이유로 연구 루프 전체를 정지하거나 새 loss를 시작하지 않는다.

검출 오류 분해를 설계하는 데 직접 도움이 되는 [TIDE 원문](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123480562.pdf)을 추천한다. §2.2의 오류 구분과 §2.3의 순차 oracle 보정 편향을 참고할 수 있다. 현재 단일 소견·confidence 없는 SFT에 AP 분석을 그대로 적용하는 것은 별도 검토가 필요하다.

# Recommended Next Experiment

다음 계획은 deep 전략 검토로 시작한다. 기존 출력으로 detector의 confidence 선택, IoU0.3~0.5 위치 오차, 후보 자체의 부재를 구분했을 때 어떤 연구 선택이 달라지는지 명시한다. 기존 선택 threshold를 사후 최적화하지 말고 GT 사용 분석은 원인 분리용으로 표시한다. 임상적으로 의미 있는 실패 조건이나 일반적인 학습 원리를 구별할 수 없다면 단순 bbox 후속 투자를 줄인다.

실제로 사용할 코드 경로만 보완하고 완료된 학습·평가를 반복하지 않는다. VinDr 승인 통지 후 권한·파일·target 차이를 확인해 외부 계획을 재검토한다. 새 loss·ensemble·continuation·MRI F139·reserve 평가를 자동으로 추가하지 않는다.