# 요약

- **이번에 할 일:** 저장된 RSNA detector–SFT 출력을 이용해 상보성을 confidence 선택·GT 대응 경쟁·위치 오차·후보 부재로 분해한다.
- **필요한 이유:** detector는 높은 IoU와 속도에서 유리하지만, 현재 상보성이 VLM의 추가 능력을 뜻하는지는 확인되지 않았다.
- **확인할 기준:** 기존 비교 수치 재현, 동일 GT별 오류 분류, FP 비용, seed·matching 민감도와 잔여 차이의 크기를 확인한다.
- **주의·다음:** 개발800은 독립 확인이 아니다. 후처리의 영향이 투자 판단을 바꿀 때만 GPU 중간 후보 추적을 실행한다. VinDr 승인 대기는 유지하며 새 contribution은 미확정으로 둔다.

# Current Understanding

iter_035는 완료된 유효한 비교다. 양성400명에서 detector17의 F1@0.3/0.5는 0.581643/0.415548, SFT17은 0.630750/0.348667이었다. IoU0.3에서 detector-only/SFT-only GT는 589개 중 71/77개였다. detector의 단독 평균 추론은 현재 구현에서 약70배 빨랐다.

하지만 validation FP budget1.0에서 SFT-only 비율이 3.9%로 줄어드는 관찰은 선택 threshold가 상보성에 관여함을 보여준다. 같은 operating point의 개발800 FP/환자는 1.0075이고 양성 F1@0.3은 0.58443이다. 낮은 점수 후보의 존재만으로 실용적인 detector 우위를 선언할 수 없다.

기준 비교 문서는 `agent/runs/iter_035/plan.md`이며 SHA256은 `463b95001116ec77bc64c8a95fa33cf7c948ca3e582f498732a8290ea1cacd15`다. 이번은 새로운 오류 분해 질문을 추가하는 정식 diagnostic이다. 기준 문서의 완료된 학습·선택·성공 판정을 수정하거나 그 실행 명령을 반복하지 않는다.

사용자 보완 `20260929_131450_4dda5b89`의 GOAL·MedGemma 1.5·기존 checkpoint·분할·VinDr 대기 방침을 유지한다. iter_031의 보완 분석은 완료된 범위로 보존하고 다시 수행하지 않는다. MRI F139와 reserve는 열지 않는다.

# Strategy Check / 연구 방향 판단

**재검토 이유:** 빠졌던 강한 detector baseline을 확보했다. 이제 정확도 차이를 넘어 어떤 실패 조건이 새 post-training의 필요성을 만드는지 판단해야 한다. 현재 접근법의 유효 실험은 1회이며 반복 횟수 때문에 계속하거나 포기하는 판단이 아니다.

**중요한 능력:** 의료 영상에서 병변을 빠뜨리지 않으면서 불필요한 후보와 위치 오차를 억제하는 능력이다. VLM 내부 적응의 가치는 강한 검출 대안과 실제 비용을 함께 비교해야 한다.

**세 선택 비교:**

1. 현재 방법 개선은 실제 출력 개선으로 이어질 수 있지만, threshold나 위치 경계가 설명하는 차이에 새 loss를 도입할 위험이 있다.
2. 원인 후보 진단은 이미 확보한 원시 출력으로 가능하며, 표현 학습·confidence 선택·언어 과제 전환 중 어디에 투자할지 구분한다. 이번 우선순위다.
3. 언어·근거 과제로의 전환은 VLM의 필요성을 직접 묻지만, 유효한 정답과 detector+VLM 또는 검출+규칙 대안이 선행돼야 한다. iter_017·018의 제한된 결과를 그 근거로 과장하지 않는다.

**방향을 바꿀 조건:** 선택·후처리를 통제하면 차이가 작아지는 경우 새 시각 표현 학습의 우선순위를 낮춘다. 충분한 잔여 차이가 남으면 외부 재현 후보와 구체적인 실패 조건을 보존한다. 이번 한 번의 분해 후 같은 개발 자료의 세부 층을 계속 늘리지 않는다. 어떤 결과에서도 loss·ensemble을 자동 시작하지 않는다.

# Hypothesis

H_selection: 현재 SFT-only GT의 상당 부분은 detector에 대응 후보가 있으나 선택 threshold 아래에 있는 경우다. 이 경우 상보성의 일부는 후보 발견보다 선택의 차이다.

H_geometry: IoU0.3에서는 대응하지만 0.5에서는 대응하지 않는 출력이 두 모델의 위치 정밀도 차이를 설명한다. 중심 이동·크기 차이와 GT 대응 변경을 구분한다.

H_residual: 낮은 점수의 저장 후보와 필요한 후처리 추적을 고려해도 SFT가 검출하고 detector 후보가 충분히 대응하지 않는 GT 집단이 남는다. 이는 현재 모델·자료의 제한된 잔여 차이이며 VLM 고유 의미 이해나 내부 시각 정보의 부재를 입증하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`은 iter_009·012의 정상 사용·독립 출력 검증 범위에서 validated다. 이번 직접 대상인 `rsna-detector-sft-localization-tradeoff`는 iter_035의 observed 주장이다. 저장 출력 분석만으로 내부 원인이나 외부 일반화를 validated로 승격하지 않는다.

MedGemma revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, 기존 adapter·prompt·processor·EOS·strict parser를 유지한다. 원본 영상 pixel xyxy와 padded yxyx 0–1000 좌표 연결도 유지한다. 모델 입력이나 생성 길이를 바꾸지 않는다.

기존 출력 재사용은 원본 commit의 source digest와 비교한다. 수정된 분석 코드의 hash를 과거 생성 소스와 같아야 한다고 요구하거나 원본 metadata를 새 hash로 덮어쓰지 않는다. 현재 입력·GT·manifest·checkpoint·adapter·protocol·completion과 원시 shard 연결을 확인한다. 사용 이력상 개발800이며 사전학습 노출과 SOP 수준 독립성은 미확인이다.

# Contribution Path / Baselines / Reuse

## 기여와 비교군

가까운 선행 진단은 [TIDE](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123480562.pdf)다. 오류를 구분하고 순차 oracle 보정의 점수 차이를 독립적인 원인 기여처럼 더하지 않는 원칙을 참고한다. 이번은 TIDE의 AP 분석을 그대로 재현하지 않으며 새로운 진단 방법이라고 주장하지 않는다.

주비교는 detector17 epoch18/threshold0.70 대 SFT17이다. detector29 epoch26/threshold0.60은 detector seed 민감도, SFT29·43은 SFT seed 민감도다. seed를 환자 표본으로 합치지 않는다. 기존 validation FP budget0.25/0.5/1.0에서 잠긴 threshold도 사용하되, 개발 집단의 실제 FP와 검출 성능을 함께 제시한다. budget 값 자체를 동일 FP 비교라고 부르지 않는다.

동일 annotation budget은 유지되지만 detector의 전체 backbone 적응과 VLM의 rank16 LoRA는 사전학습·학습량·추론 비용이 다르다. 기존 비용 표를 연결한다. 원본 영상과 검출 영역을 이용하는 모듈형 대안의 접근을 제한하지 않는다. 이번에 언어 출력 효용까지 평가했다고 주장하지 않는다.

## 재사용 범위

현재 `approach/rsna-detector-comparison`, HEAD `615c61ec51cfe9d84d564bfcaab434a3a5c78cb1`을 잇는다. 필요한 파일이 모두 있으므로 `reuse_iteration=0`, `reuse_assets=[]`다. 전체 snapshot 승인이라는 뜻은 아니다.

- 승인된 `rsna_diag/__init__.py`, `geometry.py`, `parse.py`, `metrics.py`, `sft_eval.py`와 `det_lib.py`의 현재 RSNA 데이터·좌표·모델 보조 범위를 사용한다.
- `det_compare.py`의 저장 SFT 로더와 집계 함수, `det_eval.py`의 저장 detector 로더는 선택 LOCK·원본 source·현재 input·batch·completion 연결을 보완한 범위에서 사용한다.
- `tests_det/test_match_identity.py`, `verify_compare_independent.py`는 기존 규약과 독립 검증의 출발점이다. 고정 결과 경로를 덮어쓰지 않도록 새 out 경로를 강제한다.
- `det_match.bounded_match`의 GT identity는 승인되지 않았다. GT별 오류 분류는 승인된 `metrics.match` 또는 그 identity까지 독립 대조한 구현을 사용한다. 많은 후보의 단순 coverage 계산에는 matching이 필요 없다.
- 조건부 GPU 추적에 들어갈 때만 `det_eval.py`의 소유권·완료 재사용·worker 종료·재개 경로를 보완한다. `det_jobs.py`, 학습 연장, latency 실행기와 과거 continuation 실행기는 이번에 사용하지 않는다.

# Proposed Experiment

## 1. 동작 확인과 provenance 고정

모든 새 산출물은 `research/results/iter_036/` 아래 고유 attempt에 저장한다. 분석 config에는 입력 파일 hash, 원본 코드 SHA, 선택 LOCK, parser·metric·분류 규칙, bootstrap seed와 확대 조건을 잠근다. 누락·중복·비유한 좌표·box/score/label 길이 불일치·선택 연결 오류는 해당 분석을 중단한다.

기존 V400에서 category와 GT 개수로 고정한 D24를 구성한다. 출력 성능으로 고르지 않고 category별 8명, 양성 내 GT 개수 층을 가능한 범위에서 포함하며 hash 순서로 결정한다. 정규화 왕복과 GT identity, IoU 경계0.1/0.3/0.5, threshold 경계, 동일 box·겹친 GT·한 후보가 여러 GT에 대응하는 fixture를 검사한다.

실제 저장 출력에서는 detector17/29와 SFT17의 기존 F1 두 값, 589개 GT 분모, detector-only/SFT-only 및 FP를 재현한다. 허용 오차는 수치 연산의 1e-8 수준이며 불일치에 맞춰 완화하지 않는다. 과거 검사 전체를 다시 돌리지 않고 변경된 loader와 새 분류 경로를 검사한다.

## 2. 가능성 탐색: V400에서 분해 규칙 검증

학습은 0 update다. 먼저 V400의 선택된 detector17/29와 SFT17 저장 출력을 사용한다. 기존 threshold와 checkpoint를 다시 선택하지 않는다. 이 단계는 분석 가능성·후보 수·cap·실행 비용과 분모 검증이다. 효과가 유리한지를 근거로 개발800 분석 여부를 고르지 않는다.

각 GT에 대해 모델별 선택 출력의 일대일 대응 여부, 선택 출력의 최대 IoU, detector 저장 전체 후보의 최대 IoU, IoU0.3/0.5 이상인 후보의 최고 score를 기록한다. 후보가 없으면 명시적인 결측/부재 값으로 저장한다. 원래 candidate index를 유지한다.

선택점의 SFT-only GT를 다음 네 범주로 나눈다. 기준은 IoU0.3이며 같은 분석을 0.5에서도 보조적으로 제시한다.

1. **대응 경쟁:** 선택 detector 출력에 IoU 기준을 넘는 후보가 있지만 일대일 matching에서는 해당 GT가 배정되지 않았다.
2. **threshold 제외:** 선택 출력에는 대응 후보가 없지만 저장 전체 후보에는 있다. 해당 후보 score와 잠긴 threshold를 연결한다.
3. **인접 위치 오차:** 저장 전체 후보의 최대 IoU가 0.1 이상이며 기준 미만이다. 0.1은 탐색적 인접 기준이며 병변 인식의 증명이 아니다.
4. **저장 후보 coverage 부재:** 최대 IoU가 0.1 미만이거나 후보가 없다. 저장 파일은 후처리 이후 결과이므로 내부의 실제 미검출이라고 부르지 않는다.

범주가 배타적이고 합이 원래 SFT-only 수와 일치해야 한다. cap100 도달은 별도 censoring 표시로 유지한다. 선택점에서 cap 문제가 없었다는 과거 검사는 score floor까지의 완전성을 보장하지 않는다.

## 3. 저장 출력 본분석: 개발800 전체

V400에서 구현·무결성 gate를 통과하면 고정 개발800 전체를 분석한다. 양성400명·GT589개, Normal200명·NoOpacity/NotNormal200명의 구성을 유지한다. 새 환자 추출은 없다. 저장 detector 2×800건과 SFT 3×800건을 재사용한다. 충분한 기존 표본과 완료 출력이 있으므로 작은 성능 탐색 표본으로 다시 축소하지 않는다.

주분해는 detector17 대 SFT17이다. detector29 대 SFT17을 동일하게 분석한 뒤, 두 detector 각각에 SFT29·43을 적용한 민감도 표를 만든다. 유리한 seed만 보고하지 않는다.

핵심 잔여량 R은 `SFT가 IoU0.3 일대일 matching으로 검출했지만 detector 저장 전체 후보 중 IoU0.3 이상 후보가 없는 GT 수 / 전체 GT 수`다. 원래 선택점 SFT-only 중 R이 차지하는 비율과 해당 환자 수도 함께 보고한다. coverage는 여러 GT가 한 후보를 공유할 수 있으므로 검출 recall과 분리한다.

기존 FP budget 세 operating point마다 F1@0.3/0.5, lesion recall, 전체800 및 category별 FP/환자, 상보성, R을 보고한다. 낮은 threshold에서 후보가 회복되더라도 FP 비용을 숨기지 않는다. E800 결과로 threshold를 새로 최적화하지 않는다.

위치 정밀도는 각 모델의 IoU0.3 대응에서 출발해 IoU0.5 대응 여부를 표시한다. 같은 GT에 대한 중심 거리/GT 대각선, 예측/GT 면적비, 폭·높이 비를 기록한다. 두 IoU에서 독립적으로 재매칭한 결과와 원래 대응쌍의 IoU 변화는 다른 표로 제시한다. GT 순서 또는 matching 변경을 위치 개선으로 오해하지 않는다.

양쪽 모델의 FP는 중복 후보, 어떤 GT와도 IoU0.1 미만, 0.1 이상이지만 해당 평가 threshold 미만, 대응 경쟁으로 분리해 함께 보고한다. 이는 정답 주석 기준의 분류이며 임상적 정상/비정상을 새로 부여하지 않는다.

분류 오류를 확인할 overlay는 각 비어 있지 않은 범주에서 hash 순서로 최대6명씩 고정 추출한다. 그림을 보고 GT·환자·분류 규칙을 바꾸지 않는다. 주석 모호성이 의심되면 별도 주의 항목으로만 기록한다.

## 4. 조건부 GPU 확대: 후처리 전 후보 추적

기본 blocker는 저장된 post-NMS 후보만으로 후보 부재와 후처리 제거를 구분할 수 없다는 점이다. 다음 중 하나를 만족하고, 그 구분이 후속 투자 판단을 바꿀 때만 GPU 단계에 진입한다.

- detector17 또는29 대 SFT17의 R에 대해 영향 환자가20명 이상이고 97.5% CI 상한이 전체 GT의5% 이상이다.
- cap에 의해 관측되지 않은 후보를 모두 회복 가능/불가능으로 두는 양극단 분석에서 5% 투자 기준의 판단이 달라진다.

5%와20명은 직전 비교의 의미 있는 상보성 기준과 연결한 투자 기준이며 임상적 중요성이나 모집단 효과의 증명 기준은 아니다. 확대 판단을 `decision.json`에 저장하고 이후 trace 요청과 hash로 연결한다. 조건 미충족이면 CPU 결과로 이번 진단을 끝내고 GPU 단계 미실행 이유를 기록한다.

진입 시 기존 두 detector의 선택 checkpoint를 그대로 사용한다. 설치된 torchvision 0.21.0의 실제 `roi_heads.postprocess_detections`를 기준으로 ROI class-specific decode 뒤의 box·score와 score filtering, small-box 제거, NMS, cap 단계의 생존 index를 추적한다. 원래 반환 경로의 threshold·NMS·cap은 변경하지 않는다. ROI 입력 proposal이 이미 RPN 선택을 거친다는 한계를 유지한다.

GT는 추론 입력이나 후보 선택에 전달하지 않고 추적 완료 후 분석에만 사용한다. resized 좌표와 원본 pixel 좌표의 변환을 저장하고 기존 geometry로 정규화한다. score floor의 공식 조건 `score>0.001`과 사용자 operating threshold의 `score>=threshold`를 혼동하지 않는다.

D24에서 trace on/off의 최종 box·score·label·순서가 같고 기존 저장 결과와 일치해야 한다. 불일치는 계측 gate 실패다. batch1과 동일 입력의 반복 대조에서 발생한 차이를 조사하며, 결과를 보고 허용 오차를 확대하지 않는다. score threshold 바로 전후·small box·NMS 동점·cap fixture도 검사한다.

그 다음 V400 내 고정 V100에서 계측 처리량과 재개를 확인한다. gate 통과 후 두 seed의 V400+개발800, 최대2,400개의 고유 image×checkpoint 요청을 추적한다. D24/V100 요청은 동일 provenance일 때 재사용한다. 기존 최종 검출 비교를 다시 선택하는 실험이 아니라, 저장돼 있지 않던 중간 후보를 얻는 계측이다.

후처리로 사라진 GT coverage, ROI decode 단계에도 남는 낮은 IoU, 대응 경쟁을 구분한다. 단계를 통과하며 coverage가 사라지는 양상은 그 파이프라인의 경로 설명이다. 각 단계의 수치를 독립적인 인과 기여로 더하지 않는다. pre-NMS 저점수 후보가 GT와 겹친다는 사실도 실제 검출이나 시각 이해의 증거로 해석하지 않는다.

## 5. 독립 확인과 자원

이번 독립 확인 단계는 미실행이다. 전체 결과는 개발 자료의 진단이며 seed 민감도도 환자·기관 독립성을 대신하지 않는다. VinDr 승인 통지 후 target 차이와 자료 접근을 확인하고 별도 계획에서 재현 질문을 정한다.

GPU 확대 직전 nvidia-smi로 허용 장치0,1의 UUID·실제 여유와 논리 index 대응을 확인한다. 여유가 큰 장치부터 배정하며 타인 프로세스는 건드리지 않는다. detector17/29와 독립 shard를 두 GPU에 배치한다.

iter_035는 batch1 worker1/2에서 출력 동일, 처리량7.4/8.0 images/s, worker당 reserved peak 약766MiB를 기록했다. batch4는 출력이 달라 채택하지 않는다. 새 trace의 메모리·I/O 비용은 달라지므로 D24/V100에서 GPU당1 worker와2 worker의 유효 요청/초·peak·오류·출력 정합성을 비교한다. 전체 점유와 동시 peak에 worker당2GiB 여유를 더한 조건에서 총4 worker도 허용한다. 1 worker를 유지하면 실측 이득 없음·메모리·작업량 근거를 남긴다.

GPU가 필요한 경우 원시 추론량은 기존 처리량으로 수분 규모지만, trace 검증·모델 로드·I/O를 포함한 실행 wall-clock은 약10–30분으로 추정한다. CPU 분석은 matching·bootstrap 구현에 따라 약10–40분으로 추정한다. 둘 다 상한이 아니며 실제 처리량으로 ETA를 갱신한다. 새로운 학습 시간은0이다.

요청 ID는 patient×checkpoint×trace-config로 고정하고, 고정 shard 또는 원자적 claim으로 중복 할당을 막는다. worker별 append 결과와 완료 metadata를 분리한다. 레코드 단위 재개, 원본을 보존한 손상 tail 처리, source/input/checkpoint 변조 거부, 부모 종료와 child 회수를 D 단계에서 확인한다. 모든 worker 종료와 정확한 요청 집합을 확인한 뒤에만 완료로 보고한다.

# Implementation Tasks for Claude

1. 원본 비교 계획 hash, HEAD, 필요한 자산과 저장 입력의 provenance를 확인한다. 실행 중인 같은 작업이 있으면 중복 실행하지 않는다.
2. 실제 사용하는 loader에 선택 LOCK·원본 source·현재 입력·완료 연결 검사를 추가한다. 새 분석은 추적 경로 `rsna_diag/det_error_audit.py` 등에 두고 원본 평가 함수를 재사용한다.
3. 새 분류·GT identity·coverage·위치 전이·FP 비용·bootstrap을 구현한다. 독립 검사 코드는 별도 IoU/분류 계산으로 원시 출력에서 주수를 재현한다.
4. V400에서 분석 gate를 확인한 뒤 개발800 전체와 저장 seed 민감도를 완료한다. 결과를 본 뒤 범주·판정 기준을 수정하지 않는다.
5. 명시한 확대 조건을 만족할 때만 계측 모듈과 추론 실행 경로를 보완하고 D→V100→전체 추적을 수행한다. 미사용 학습·latency·continuation 경로는 정비하지 않는다.
6. 보고서에 새로 설명된 차이, 남은 경쟁 설명, 실제 GPU 진입 여부, 실행량·비용, 후속 투자 권고와 미검증 범위를 기록한다. `SELF_CHECK: PASS/FAIL`, `SUMMARY:`를 유지한다. Git 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

## 통계와 무결성

기존 주 F1 차이의 97.5% paired CI와 전체 FP 차이의95% CI를 유지한다. 새 R 및 threshold 제외 비율은 detector17/29 각각97.5% 환자 cluster bootstrap CI, 10,000회, seed20260929로 계산한다. 두 detector 결과는 같은 환자에 의존하며 독립 반복 두 번으로 세지 않는다. 비율은 resample마다 분자·분모를 재계산한다. 분모0은 결측으로 표시하고 관찰0건의 퇴화 bootstrap 구간을 정확한 모집단 영점으로 해석하지 않는다. 해당 경우 환자 사건의 Wilson 구간도 제시하고 확정적인 동등성 판정을 보류한다.

층별 GT 개수와 면적은 기존 train 기준을 재사용한다. 추가 층과 seed 분석은 탐색적이며 다중 비교를 거친 확증으로 표현하지 않는다. matching 순서 민감도와 best-IoU coverage를 구분한다. 많은 후보에서 계산을 가속하면 기존 identity 규약까지 검증한 범위만 사용한다.

## 양성: 의미 있는 잔여 차이

두 detector seed 각각에서 SFT17의 잔여 R 하한이5%를 넘고20명 이상에 분포하며, 필요한 추적 이후에도 남고 SFT29·43 민감도에서 소수 사례에만 의존하지 않으면 제한된 잔여 차이를 지지한다. 이는 외부 확인과 해당 실패 조건에 대한 방법 후보 비교의 근거다. 새로운 방법의 성공이나 detector 전체보다 우수하다는 판정은 아니다.

다음은 VinDr 승인 후 같은 조건의 재현 후보를 보존하고, 승인 전에는 이 실패 조건을 해결하는 기존 직접 SFT·표준 선택/보정 대안과 구별할 수 있는 원리를 검토하는 것이다. 학습은 별도 계획에서 정한다.

## 음성: 후보 발견 설명의 약화

두 detector seed에서 R의 CI 상한이5% 미만이고 cap 불확실성이 결론을 바꾸지 않으면 큰 후보 coverage 차이라는 설명을 약화한다. threshold 제외가 원래 SFT-only의 과반이며 그 비율 CI 하한도0.5를 넘으면 선택 효과가 주된 설명이라는 제한된 결론을 내린다. 그렇지 않으면 위치·대응 경쟁 등의 실제 분해 결과대로 보고한다.

이 경우 새 시각 표현 loss와 단순 ensemble에 대한 추가 투자를 낮춘다. 다만 낮은 score 후보 회복이 FP를 늘린다면 실용 검출 차이는 남으므로 detector 우위나 confidence 문제가 해결됐다고 주장하지 않는다. 후속 방향은 표준 calibration/선택으로 설명 가능한지 또는 언어·근거가 필요한 과제로 옮길지 비교하되 자동 방법 학습으로 연결하지 않는다.

## 불확정

5% 기준을 가로지르는 CI, seed 반전, cap·후처리 영향 또는 대응 규칙 민감도가 판단을 바꾸면 불확정이다. 저장 후보와 중간 후보의 차이가 원인일 때만 승인된 조건부 GPU 추적을 수행한다. 추적 후에도 표본·기관 일반화가 병목이면 같은800명의 분석 종류를 늘리거나 새 seed를 학습하지 않는다. 외부 확인에 필요한 정밀도와 어떤 결과가 결정을 바꿀지를 적고 해당 주장을 보류한다.

## 진단 완료와 실행 실패

진단 완료는 잠긴 입력, 재현된 기준 수치, 배타적 분류와 분모, 비용·seed·matching 민감도, 조건부 확대 판정 및 독립 수치 대조가 모두 있을 때다. 양성 가설 지지가 없어도 투자 판단을 구분했다면 유효한 진단일 수 있다.

원시 입력 연결 실패, GT identity 오류, 계측이 원래 출력을 바꾸는 문제, 미완료 worker 또는 요청 누락은 해당 경로의 실행 실패다. 이를 가설 기각으로 바꾸지 않는다. GPU 단계가 실패해도 이미 검증된 저장 출력 분석은 보존하되 추적에 의존하는 결론은 보류한다.

# Risks / Checks

저장 후보 coverage는 검출 recall이 아니며 저점수 후보의 GT 중첩은 oracle 정보다. ROI 이전 RPN의 후보 선택, 사전학습 노출, annotation 경계와 임상적 중요성은 이번 분해만으로 해결되지 않는다. GT bbox 제거나 crop으로 임상적 정상 label을 만들지 않는다.

과거 결과와 새 코드의 source digest 차이를 명시적으로 연결한다. 원본 선택 파일·prediction·completion·로그를 고치거나 덮어쓰지 않는다. 기존 소스 보존본을 못 찾으면 새 구현으로 대체하지 말고 해당 경로를 중단한다.

이번에 필요한 재사용 보완과 현재 결론에 무관한 운영 개선을 분리한다. CPU로 종료하더라도 단순 코드 정비 완료가 아니라 실제 저장 출력의 과학적 진단과 GPU 미진입 근거를 보고한다. 기존 결과로 답할 수 있는 질문에 GPU를 채우기 위한 추가 실험을 만들지 않는다.

## 대규모 GPU 필요 후보

다기관·다소견에서 vision encoder와 언어 decoder를 공동 적응하며 후보 coverage·위치 정밀도·언어 조건 선택을 함께 학습하는 post-training을 장기 후보로 보존한다. 큰 모델과 여러 기관의 충분한 대조 학습에는 현재 두3090을 넘는 자원이 필요할 수 있다. 현재 결과는 그 필요성을 입증하지 않으므로 이번에는 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- GOAL, GPT_USAGE_POLICY, REPORTING_STYLE, INDEX, 관련 LIMITATIONS/CODE_ASSETS와 iter_009·012·017·018·031·035의 관련 원문을 확인했다. 이번은 iter_035의 실행 복구가 아니라 완료된 비교의 원인을 구분하는 후속 diagnostic이다.
- 현재 research HEAD는 `615c61ec51cfe9d84d564bfcaab434a3a5c78cb1`이며 status와 diff는 비어 있다. 필요한 parser·geometry·metric·detector 평가 모듈은 현재 브랜치에 있다. 다른 commit의 파일 반입은 필요하지 않다.
- iter_035 리뷰에서 detector17−SFT17의 양성400명 F1@0.5 차이는 +0.066881, 97.5% CI [0.012211, 0.121965]다. F1@0.3 차이는 −0.049107로 불확정이다. IoU0.3의 detector-only/SFT-only는 71/77개였다.
- 저장 `confirm800/analysis.json`에서 validation FP budget1.0 operating point는 개발800에서 FP/환자 1.0075, 양성 F1@0.3 0.58443이다. 후보 coverage 증가를 실용적 성능 개선으로 해석할 수 없다.
- `det_lib.build_model`은 score floor0.001, NMS0.5, cap100이다. `raw_preds.json`에는 box·score·label·원본 영상 크기가 있어 threshold 영향을 재학습 없이 분석할 수 있다. 하지만 이 파일은 ROI score filtering·small-box 제거·NMS·cap 이후 출력이다.
- 설치된 torchvision 0.21.0의 `roi_heads.py` 원문에서 class-specific box decode → clipping → background 제거 → score>0.001 → small-box 제거 → NMS → cap 순서를 확인했다. 저장 후보 부재는 내부 시각 정보 부재를 뜻하지 않는다.
- `tests_det/test_match_identity.py`는 `metrics.match`의 GT identity를 독립 exhaustive 방식으로 검사한다. 반면 `det_match.bounded_match`는 cardinality·총 IoU만 비교하고 identity 차이를 따로 센다. 따라서 빠른 DP의 GT identity를 후속 상보성 분석에 그대로 쓰면 안 된다.
- iter_035 code_assets는 geometry·strict parser·현재 metric·SFT 평가와 detector 데이터/모델 보조 범위를 승인했다. 평가 loader의 source/input/batch 검증, 선택 LOCK 강제, 실행 소유권은 needs_fix다. 학습 연장과 latency 실행기는 이번에 사용하지 않으므로 정비 대상에서 제외한다.

## 문헌과 의미

[TIDE 원문](https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123480562.pdf)의 §2.2–2.3을 확인했다. 오류 유형을 구분하고, 여러 oracle 보정을 순차 적용한 점수 차이를 독립적인 원인 기여처럼 해석하지 말아야 한다는 원칙을 적용한다. 이번 분석은 단일 소견·환자 F1·confidence 없는 SFT에 맞춘 제한된 진단이며 TIDE 재현이나 신규 방법이 아니다. 해당 논문은 직전 리뷰에서 이미 추천됐다.

## 전략 판단

새 loss나 ensemble 학습은 상보성의 원인을 모르는 상태에서 투자를 늘린다. 언어·근거 과제로의 즉시 전환도 현재 확보한 정답과 강한 모듈형 대안이 부족하며, iter_017·018은 기존 인터페이스 개선의 일반화를 지지하지 않았다. 따라서 저장 출력으로 선택·위치·후보 부재를 한 번 구분하는 것이 현재 정보 이득이 가장 높다. 후처리 때문에 판단이 달라질 만큼 큰 잔여 집단이 있을 때만 기존 detector checkpoint의 중간 후보를 GPU로 추적한다.

## 원본 연결

기준 비교 계획은 `agent/runs/iter_035/plan.md`, SHA256 `463b95001116ec77bc64c8a95fa33cf7c948ca3e582f498732a8290ea1cacd15`다. 원 계획의 학습·선택·완료 판정을 변경하지 않는다. 이번 계획 단계에서는 파일 수정·생성이나 실험 실행을 하지 않았다.
