# 요약

- **이번에 할 일:** E48 정확도 결과를 보존하고 D6에서 원본 NIfTI→여섯 답변 저장의 전체 비용을 재측정한다.
- **필요한 이유:** HD-GLIO의 BA 이득은 확인됐지만 기존 비용에는 channel 분리·OR·답변 저장이 빠졌다.
- **확인할 기준:** 기존 정확도 세 조건과 HD/U8 전체 비용≤1을 유지한다.
- **주의·다음:** 네 sequence 개발 조건의 대안 채택 여부만 결정한다. 비용 증가·불확정이면 해당 복합 기준 미충족으로 종료하며 추가 timing 탐색을 하지 않는다.

# Current Understanding

기준 문서는 `agent/runs/iter_058/plan.md`이며 SHA256는 `9781574f0b3c413653cbe2db27fafd4ad2ab376bd386bc45f948d10e84c40b51`이다. `agent/runs/iter_058/review.md`와 review.json의 수정 요구를 함께 적용한다. 원 계획 전체를 다시 실행하는 지시가 아니다.

**유지:** D6/E48, 여섯 구간, 정답, U8 prompt·parser·caps·model revision, HD checkpoint·fold·TTA·전처리·foreground OR, 정확도 기준과 개발 평가 해석을 유지한다. E48 BA는 U8 0.768639, HD 0.950457이며 차이의 95% CI는 [0.115776, 0.247666]이다. sensitivity는 양쪽 176/189다.

**이번 변경:** 전체 비용 경계와 직접 계측, 해당 실행 경로의 provenance·admission·실패/재개 검사를 보완한다. 결과는 `research/results/iter_059/`에 저장한다.

**미완료:** 올바른 전체 비용과 전문 대안 충분성 판정이다. E 재생성·새 학습·독립 확인은 이번 범위가 아니다.

**회귀 검증:** 고정 E 원시 결과·입력·checkpoint 불변성을 확인하고 기존 수치가 유지되는지 검증한다. 과거 원본 기록·판정은 수정하지 않는다.

# Strategy Check / 연구 방향 판단

iter_058 review의 방향 판단을 유지한다. 관찰은 전문 대안의 BA +18.18 pp와 FP 39→3 감소다. 남은 질문은 누락된 처리 단계를 포함해도 비용 이점이 유지되는지다. 전문 표현·추가 sequence·전체 관측 범위의 기여는 이번에 분해하지 않는다.

직접 SFT 개선은 전문 대안 대비 가치가 아직 불명확하다. 새 MRI 질문으로의 전환은 가능하지만 현재 질문을 작은 보완으로 종료할 수 있다. 따라서 D6 비용 복구가 우선이다. 세 유효 반복을 정보 축적으로 연결하며, 횟수 자체를 포기 사유로 삼지 않는다.

지배적인 새 비용은 계측·검증 구현과 D6 재실행이다. 기존 환경과 E 결과를 재사용한다. 정확한 구현/GPU 비용 비율은 로그 없이 추정하지 않는다. 이번 종료 후 구체적 사용 가치가 없는 timing·prompt 탐색은 보류한다.

# Hypothesis

누락 단계를 포함해도 HD-GLIO+OR가 U8 이하의 전체 비용을 유지할 수 있다. 반대로 전처리·저장 비용 또는 loading 조건이 기존 비용 우위를 뒤집을 수 있다. 이는 기존 전문 대안의 충분성 진단이며 새 방법 효과 검증이 아니다.

# Limitation Evidence / Correct Usage Checks

`limitation_ids=[]`, `experiment_role=diagnostic`, `method_stage=none`을 유지한다. MRI 구간에 등록된 observed/validated id가 없는 상태에서 다른 MRI 한계를 전용하지 않는다.

iter_058의 정상 사용·공식 checkpoint·sequence mapping·native grid·E 평가 검증은 불변 SHA와 입력에 한해 재사용한다. 변경된 timing 경로는 새로 검사한다. 기존 비용 blocker는 이번 새 결과에서만 해소 여부를 판단하며 과거 review에서 삭제하지 않는다.

# Contribution Path / Baselines / Reuse

가장 가까운 방법은 기존 HD-GLIO segmentation+OR다. 이번 기여는 새로운 알고리즘이 아니라 후속 투자 판단을 끝내는 근거다. HD는 네 sequence 전체 volume과 전문 supervision, U8는 FLAIR 구간당 8장을 사용한다. 동일 annotation·입력 예산 비교 또는 언어 추론 우위로 해석하지 않는다.

현재 `approach/mri-slab-evidence`, HEAD `e203cbd0b4c7d8e6c1f75fbd37625a82b14c232d`를 유지한다. 필요한 파일이 이미 있으므로 `reuse_assets=[]`다.

- `hdglio58_pred.py`: 검증된 단회 segmentation adapter 승인 범위를 재사용한다. 기존 overwrite·부분 출력 처리는 새 실행 경로에서 차단한다.
- `hdglio58_timing.py`, `hdglio58_u8.py`: 전체 경계·직접 steady-state·허용 GPU 매핑을 수정한다. U8 내부 case timer도 최종 답변 저장 후 종료한다.
- `hdglio58_prep.py`, `msd56_data.py`: 실제 channel voxel·affine 대응을 확인하고 매 timing 실행의 새 경로에서 channel 분리 비용을 포함한다.
- `hdglio58_eval.py`, `hdglio58_verify.py`, `msd57_analysis.py`, `test_hdglio58.py`: 사용하는 검증 경로의 GT 중복·case/split·protocol 내부 연결과 실패 종료를 보완한다.
- `msd56_run.py`: 필요한 로딩·생성·parser 경로와 그 의존성만 사용한다. 실제 sanity를 호출하면 관련 미해결 검사를 먼저 고친다.

환경은 기존 `results/environments/hdglio58/`의 Python 절대경로를 사용한다. 사용하지 않는 Qwen·breakdown·범용 launcher 정비는 하지 않는다. 모듈 전체 재사용 승인을 임의로 선언하지 않는다.

# Proposed Experiment

## 1. 동작 확인과 고정 입력

실행 전 원 plan hash, 기존 E 예측·U8 출력·D/E manifest·원본 영상·checkpoint·공식 source/config digest를 잠근다. 기존 protocol은 당시 보존 코드에 연결하고 새 코드 digest로 덮어쓰지 않는다. 사용 경로에서 GT 중복 key, case/split 누락·교환, 요청 집합 누락·변조를 거부한다.

첫 D block인 BRATS_053/BRATS_199를 기술 검사에 사용한다. 원본 4D 영상의 HD channel 순서 T1←1, T1c←2, T2←3, FLAIR←0, voxel·affine·shape·유한값을 확인한다. GT를 inference 경로에 전달하지 않는다. 새 instrumentation이 공식 추론 인자나 U8 tensor·prompt·생성 설정을 바꾸지 않았는지 대조한다. U8의 기존 D 답변과 EOS를 비교하고, HD의 공간 대응·여섯 OR 답변을 확인한다. 정상 오답은 기술 실패로 취급하지 않는다. HD의 알려진 미세 voxel 변동은 기록하며 byte 동일성 자체를 보편적 gate로 요구하지 않는다.

## 2. 직접 비용 측정

공통 시작은 원본 NIfTI가 디스크에 있고 모델별 파생 입력은 아직 없는 상태다. 공통 끝은 여섯 구간 답변 파일의 원자적 저장 완료다. 파일 close/rename 완료를 기준으로 하며 durable fsync 비용을 포함할 경우 양쪽에 동일 적용한다.

HD는 원본 읽기, channel 분리·쓰기, 공식 전처리·추론·출력, native-grid 복원, foreground OR, 답변 저장을 포함한다. U8는 원본 읽기, FLAIR 정규화·렌더, processor, 여섯 생성, parsing·답변 저장을 포함한다. OS page cache를 강제 삭제하지 않고 실행 순서로 균형을 잡는다. 기존 분리 channel이나 segmentation cache로 계산을 건너뛰지 않는다.

각 실행에서 monotonic clock으로 외부 subprocess 전체 wall과 내부 단계 event를 직접 기록한다. 모델 loading 구간과 모델이 준비된 뒤 원본 읽기부터 답변 저장까지의 steady-state 구간을 직접 계측한다. 다른 실행 시간끼리 빼서 steady-state를 만들지 않는다. 공식 함수가 loading을 내부에서 수행하면 고정 설치 소스의 해당 경계에 최소 계측을 추가하고 patch·source digest를 보존한다. 계산·fold·TTA·수치 설정은 그대로 둔다. GPU 비동기 경계는 synchronize한다. 겹치는 단계 시간을 단순 합산해 전체 wall로 대체하지 않는다.

## 3. 고정 본측정

block은 기존대로 `[BRATS_053, BRATS_199]`, `[BRATS_368, BRATS_380]`, `[BRATS_037, BRATS_455]`다. 각 block에 U8→HD와 HD→U8 두 순서를 적용한다. 한 paired block의 두 모델은 같은 GPU에서 순차 실행한다. 두 허용 GPU에 block/order를 균형 배정하되 실험끼리 CPU/I/O 경합을 새로 만들지 않도록 측정 block은 순차 진행한다. 이는 처리량 본실험이 아니라 비교 가능한 latency 측정이다.

총 HD 12 volume, U8 72구간 요청이다. loading 포함 총비용 비율은 동일 여섯 실행의 HD wall 합/U8 wall 합으로 계산하고, 각 block/order 비율과 case 비용도 공개한다. steady-state 비율은 동일 실행에서 직접 측정한 구간 합으로 별도 계산한다. loading 포함 결과를 주 결과로 두고 steady-state가 반대 방향이면 조건별 결과로 보고해 보편적 비용 충분성을 선언하지 않는다. 작은 D6 비용 CI를 확증 gate로 추가하지 않는다.

## 4. 자원·예산·재개

시작 직전 `nvidia-smi`와 상속된 허용 장치를 대조해 UUID·논리/물리 mapping을 기록한다. 자식 장치는 허용 집합 내부에서만 배정한다. 실제 전체 점유에 예상 worker peak와 worker당 2GiB 여유를 더해 admission한다. 초기 peak는 보존된 실행 자료를 확인하고 기술 block에서 갱신한다. 다른 사용자의 프로세스를 변경하지 않는다.

기존 2 GPU×1 worker 21.282초, 2 GPU×2 worker 23.206초의 처리량 근거를 재사용한다. 이번에는 대규모 생산 큐가 없어 새로운 동시성 탐색의 절약 가치가 작고 paired timing의 경합을 통제해야 하므로 각 측정 장치에서 1 worker를 사용한다. GPU 0/1은 균형 배정으로 모두 활용한다.

과거 누락 경계의 12 subprocess 합은 약307초다. 새 전체 비용 예산은 기술 2-case block에서 측정한 HD/U8 wall을 사용해 `6×paired 2-case 비용+필수 검증·복구 비용`으로 실행 전에 갱신한다. 시간 상한을 만들지 않는다. 학습·E 생성은 0이며 기술 검사는 HD 2 volume·U8 12요청을 별도 집계한다.

실행 ID·block/order·입력·source/checkpoint/config digest와 완료 파일을 연결한다. 기존 run 덮어쓰기를 거부하고 부분 출력은 완료로 읽지 않는다. 중단된 timing pair는 부분 시간을 이어 붙이지 않고 해당 pair 전체를 새 attempt에서 다시 측정한다. 실패 attempt 비용도 보존한다. 완료 pair는 digest 검증 후 재사용한다.

## 5. 규모 확대와 독립 확인

이번은 고정 D6 비용 보완으로 종료한다. E48 재생성·추가 case·seed·모델·prompt·학습·reserve 사용은 없다. 기존 E48은 개발 자료이며 독립 확인으로 부르지 않는다. 후속 MRI 질문은 이번 결과와 사용 가치에 근거한 별도 계획에서 판단한다.

# Implementation Tasks for Claude

1. 기준 plan/review와 위 재사용 범위를 읽고 변경 전 입력·출력·source digest를 보존한다.
2. 새 결과 경로를 받도록 timing 관련 코드를 최소 수정하고 원본→최종 답변의 전체 경계를 구현한다.
3. loading과 steady-state를 동일 실행에서 직접 계측하고 stage event·외부 wall의 연결을 검증한다.
4. source/checkpoint/config mismatch, 기존 run 충돌, 부분 출력, GT 중복·case 교환, protocol 요청 변조, worker 실패·중단 재개, 허용 GPU mapping·메모리 부족 fixture를 사용 경로에 연결한다. fixture 실패는 nonzero exit로 종료한다.
5. D 첫 block 기술 검사 후 고정 6 paired block을 실행한다. 실행 수·attempt·자원 peak·비용을 기록하고 누락·중복을 검사한다.
6. 기존 E 결과를 불변성 확인 후 재사용해 정확도 조건을 재현한다. 기존 리뷰의 정정값인 FN 13개 중 600 voxel 미만 11개, 단일 worker D6 launch wall 29.296초를 이번 보고서에 출처와 함께 적되 과거 보고서는 수정하지 않는다.
7. 원 정확도 관찰, 수정된 비용, 복합 판정, 다음 투자 보류 범위를 분리해 보고한다.

# Evaluation (성공/실패 기준 포함)

정확도 기준은 HD−U8 BA≥0.05, case-cluster paired bootstrap 10,000회·seed58의 95% CI 하한>0, sensitivity 차이≥−0.05다. 기존 E 원시 결과로 유지 여부를 확인하며 변경된 값을 유리하게 선택하지 않는다.

**양성:** 정확도 세 조건과 loading 포함 전체 비용 비율≤1을 충족하고 block별 방향이 안정적이며 steady-state도 반대 결론을 주지 않으면 현재 네 sequence 개발 조건의 전문 대안을 채택한다. VLM 구간 적응 투자는 보류한다. 이는 독립 일반화·임상 성능·신규 기여의 확증이 아니다.

**음성:** 전체 비용 비율>1이면 비용 기준 미달을 명시한다. BA 이득을 지우거나 전문 모델 전체를 기각하지 않는다. 이번 과제의 복합 대안 충분성은 충족하지 못한 것으로 종료하며 자동으로 VLM 학습에 진입하지 않는다.

**불확정:** block별 비용 방향이 엇갈리거나 loading 조건에 따라 결론이 달라지면 조건별 수치와 범위를 공개하고 불확정으로 종료한다. 결과를 본 뒤 유리한 loading 조건·block·집계법을 선택하지 않는다. 같은 D timing의 정밀도 확대는 하지 않는다.

**기술 실패:** 누락 단계, provenance 불일치, 잘못된 GPU 배정, 불완전 출력 또는 계측 불가능성이 남으면 비용 결론만 보류한다. 원인 수정 후 기술적으로 무효인 pair의 한정 복구는 허용하되 유효 결과의 방향을 바꾸기 위한 재측정은 금지한다.

# Risks / Checks

- HD와 U8의 입력·학습 정보 차이는 유지되므로 동일 정보 우위를 주장하지 않는다.
- HD/MSD foreground 의미와 환자 단위 학습 중복 불확실성은 기존 범위로 남긴다.
- 파일 저장 전 종료되는 내부 timer, 사전 channel cache, 다른 실행 차분, 실패 attempt 누락이 재발하지 않도록 실제 event와 코드를 함께 검증한다.
- 검사에 필요한 일회성 hash/fixture 비용과 실제 inference pipeline 비용을 분리해 양쪽 경계를 일관되게 적용한다.
- 기존 정확도 SHA·입력 불변성 실패 시 자동 재생성으로 덮지 말고 영향을 먼저 특정한다.
- 이전 미사용 모듈의 reuse 문제는 해제하지 않는다. branch·commit 관리는 orchestrator에 맡긴다.

## 대규모 GPU 필요 후보

3D multi-sequence encoder–언어모델 공동 적응과 대규모 MRI instruction tuning은 장기 후보로 보존한다. 이번 비용 비교는 그 필요성이나 신규성을 입증하지 않으며 실행 범위에 포함하지 않는다.

# 계획의 근거 (GPT 조사 노트)

직전 plan/review 원문, review.json의 code_assets, GOAL·GPT_USAGE_POLICY, CODE_ASSETS 관련 항목과 LIMITATIONS를 확인했다. 현재 HEAD는 e203cbd0b4c7d8e6c1f75fbd37625a82b14c232d이며 git status와 diff는 비어 있다. 필요한 파일은 현재 브랜치에 있다.

기준 plan은 agent/runs/iter_058/plan.md, SHA256 9781574f0b3c413653cbe2db27fafd4ad2ab376bd386bc45f948d10e84c40b51이다. 리뷰는 E48 BA 0.768639→0.950457, 차이 0.181818 및 95% CI [0.115776, 0.247666], sensitivity 동일을 독립 재현했다.

실제 hdglio58_timing.py는 HD 입력으로 이미 분리된 input_D를 전달하고 hdglio58_pred.py는 segmentation 저장에서 끝난다. 따라서 channel 분리·OR·최종 답변 저장이 빠졌다는 지적을 코드로 확인했다. U8의 t_case_s도 답변 파일 저장 전에 종료되므로 내부 steady-state 계측을 함께 바로잡아야 한다. hdglio58_prep.py는 기존 channel 파일 존재만으로 재사용하고 pred.py는 overwrite_existing=True다. 수정 범위는 실제 비용 실행·검증 경로로 한정한다.

기존 blocks.json은 세 block×두 순서의 12 subprocess가 모두 rc=0이며 합계 약307초다. 이는 누락 단계가 있는 과거 실측이지 이번 전체 비용 예측이 아니다. 기존 처리량 비교는 2 GPU×1 worker 21.282초, 2 GPU×2 worker 23.206초로 직전 리뷰에 검증돼 있다. 작은 보완에서 같은 동시성 탐색을 반복할 필요가 없다.

이번은 문헌·모델 재선정이 아니라 고정된 실행 경계의 보완이다. 새 외부 문헌 조사나 실험은 수행하지 않았다.
