# Assessment

계획한 실험은 실제로 실행됐다. 실행 로그에서 160장 feature 추출, 24개 학습, CPU 검사 8건의 통과를 확인했다. 원시 prediction으로 주지표와 paired bootstrap CI를 독립 재계산했고 보고서와 일치했다. 실험 재실행이나 파일 수정은 하지 않았다.

이번 결과는 사전 정의한 coarse pooling 가설을 지지하지 않는다. 이 접근법은 abandon으로 종료하되, 결론은 현재 데이터·head·학습 규약에 한정한다. 연구 최종 목표인 새로운 방법론과 다중 데이터셋 contribution 증명에는 아직 도달하지 않았다.

# Key Findings

- MLP coarse soft-IoU는 Z **0.257395**, U(P(Z)) **0.257092**다. 차이 **+0.000304**, 95% CI **[−0.001012, +0.001611]**로, 최소 차이 0.03과 CI 하한 양수 조건을 모두 충족하지 못했다.
- Z는 train 위치 prior보다 **+0.082343**, 같은 클래스 image-swap보다 **+0.099087** 높다. 두 조건 모두 영상별 위치 정보를 읽어내지만 pooling 전 feature의 추가 이득은 관찰되지 않았다.
- linear 대조군의 coarse macro 차이는 **2.31e−10**이다. 동일 초기화·batch 순서·coarse loss, unknown mask 제외, validation 공통 LR 선택, patient별 seed 평균 후 bootstrap 구현은 계획에 부합한다.
- train/validation/test는 **80/32/48명**, 전체 고유 patient는 **160명**이다. test 클래스별 관측 양성은 **13/13/12/12개**다. 확인한 코드에서 test label을 학습이나 LR 선택에 사용하는 경로는 발견하지 못했다.
- 저장 산출물 **28개**, Z와 P_model cache, 공식 다운로드 **5개**의 hash를 확인했다. 현재 target 파일도 cache에 기록된 target hash와 일치한다. 추출 검사에는 공간 정렬·token 순서·pooling 일치가 모두 통과로 기록돼 있다.
- strict readiness는 false, canvas는 assumed로 유지됐다. 탐색 실행은 이번 계획에서 명시적으로 허용한 범위다.

# Problems / Concerns

1. **완료 판정 결함:** `run_pooling_probe_iter007.py:281`의 complete는 정렬·pooling·linear 검사를 모두 요구하지 않는다. 실패한 실험도 eval_complete=true가 될 수 있다. 이번 저장 결과에서는 해당 검사가 모두 통과했으므로 현재 수치를 무효화할 사유는 아니지만, 재사용 전에 반드시 수정해야 한다.
2. **provenance 검증 누락:** `pooling_probe/features.py:94`의 verify_cache는 ID·patient·Z shape·Z hash만 검사한다. 기록된 targets_sha256, split, 모델·processor digest와 현재 입력의 연결을 강제하지 않고, gate·검사 산출물도 해당 실행 입력과 연결하지 않는다. 동일 ID의 target이나 split이 변경돼도 통과할 수 있다. 이번 target hash는 리뷰에서 별도로 일치함을 확인했다.
3. **GPU 가시성 덮어쓰기:** 추출·학습 스크립트가 CUDA_VISIBLE_DEVICES를 자체 설정한다. orchestrator가 제한한 GPU 집합과 논리 index를 존중하도록 바꿔야 한다. 이번 실행의 GPU 충돌 증거는 없지만 재사용 시 잘못된 장치를 선택할 수 있다.
4. **예산 제한이 완전하지 않음:** 추출 코드에 실행 중 상한 검사가 없고, 학습 코드는 추출 비용을 수동 인자로 받으며 run 사이에서만 검사한다. 이번 실행은 기록상 약 1.87 device-min으로 충분히 짧았으나, 45 device-min 상한을 일반적으로 보장하는 구현은 아니다.
5. **음성 결과의 범위:** 두 head 모두 LR 후보 상단을 선택했고 200 update 후에도 loss가 감소한다. 최적 readout 성능이나 일반적인 pooling 무손실을 입증하지 않는다. 실제 UPZ는 bf16 Z를 float32로 평균한 값이며, 실제 bf16 projector 출력과는 반올림 차이가 있다. 이는 계획한 head float32 비교와 양립하지만 실제 projector 출력 전체와의 동등성 주장은 피해야 한다.
6. **confound와 평가 한계:** 양성 bbox만 평가하므로 병변 존재 판별이나 false positive 성능은 알 수 없다. image-swap 대비 이득은 영상 의존성을 보여주지만 해부학적 위치·크기·촬영 조건을 이용한 효과를 배제하지 않는다. 좌표 canvas 가정, 미러 영상 원본 동일성 미확인, 사전학습 노출 미확인도 남아 있다.
7. `changes.patch`는 0바이트라 diff 자체는 검토 근거가 되지 못했다. 대신 신규 소스 파일과 실행 기록을 직접 읽었다.

# Interpretation

현재 coarse target과 제한된 비선형 readout에서는 pooling 이전 표현을 사용해도 의미 있는 추가 이득이 없었다. 따라서 이 결과를 근거로 pooling 보존형 adapter 개발에 진입하지 않는 판단은 타당하다.

fine 차이 **−0.018708**, CI **[−0.027680, −0.010164]** 역시 fine supervision 없는 부차 분석이다. 이를 fine 정보의 부재나 pooling의 우월성으로 해석해서는 안 된다. 마찬가지로 feature probe가 prior를 이겼다는 사실만으로 LLM/decoder가 병목이라고 결론 내릴 수 없다. 이번 실험은 decoder를 직접 비교하지 않았다.

# Recommended Next Experiment

현재 접근법의 test 결과를 본 뒤 학습량이나 loss를 바꾸며 반복 최적화하지 말고, 남은 anatomy→lesion grounding 전이 후보의 최소 반증 실험을 설계한다. 윤곽선·정답 표시 없는 anatomy 입력 확보 가능성과 선행 방법 대비 차별성을 먼저 확인한다.

직접 병변 학습과 anatomy 사전 적응 후 병변 학습을 동일 backbone·head·병변 label budget으로 비교하고, 학습량 차이를 분리할 대조군과 patient 독립 평가를 사전 고정한다. 현재 NIH split은 개발 자료로 취급하며 최종 확인에는 독립 자료가 필요하다. decoder 병목 후보를 선택한다면 실제 decoder grounding 결과와 probe를 공통 target·metric에서 비교하는 별도 실험부터 필요하다.

재사용 전에는 위 완료 판정과 provenance 검증을 수정하고, 실패 입력에서 complete가 남지 않는 검사를 추가한다.