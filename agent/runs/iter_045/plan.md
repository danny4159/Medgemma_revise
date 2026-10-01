# 요약

- **이번에 할 일:** 관리 경로에서 실행 권한을 정합화한 뒤 iter_044의 MedGrounder 비교를 완료한다.
- **필요한 이유:** 이전 실패는 명령 권한 차단이며 모델 성능을 평가하지 못했다.
- **확인할 기준:** 원래 D24/V96·두 checkpoint·정확도 문턱·6개 paired timing block을 유지한다.
- **주의·다음:** 현재 연구 Claude는 agent/ 설정을 수정할 수 없다. 관리 변경과 회귀 검증이 끝나기 전 재호출하지 않는다. 과학적 결과에 따른 종료 기준도 유지한다.

# Current Understanding

이 계획은 새 과학적 설계가 아니라 iter_044의 실행 복구 amendment다. 기준 문서는 `agent/runs/iter_044/plan.md`, SHA256 `e59714854fbe60c50e2135181592ea8d0868fd8e3af54b278a68a06f779312af`다. 원문 전체를 실행 명세로 상속하며 아래 명시한 경로·선행 관리 작업만 변경한다. 누락된 조건을 선택적으로 생략하는 요약으로 사용하지 않는다.

**유지:** 가설, GOAL, MedGemma revision·C adapter, T305/D24/V96, 두 MG checkpoint, prompt·생성 길이, 전처리·좌표·matching, threshold 후보·선택 순서, bootstrap, timing block, 가치 기준과 종료 행동을 유지한다. RSNA 자산, VinDr 승인 대기, H192/F120/test/MRI reserve도 유지한다.

**이번 변경:** 연구 실행 전에 관리 담당 실행의 권한 정합화와 실제 적용 검증을 선행한다. 신규 실험 결과는 `research/results/iter_045/`, 외부 자산은 그 아래 `external/`, 격리 환경은 `research/results/environments/medgrounder_iter045/`를 사용한다. 원 계획·기록·세션·Git 이력은 덮어쓰지 않는다.

**미완료:** 환경 구성, required_checks, D8, D24 선택, V96, timing, iter_041 정정 모두 미실행이다. 현재 결과 디렉터리 부재도 확인했다.

# Strategy Check / 연구 방향 판단

iter_044의 Strategy Check를 유지한다. 그 계획은 joint 정정·SFT, 강한 모듈형 비교, track 전환을 비교해 모듈형 비교를 우선했다. iter_044의 execution_failed는 이 선택을 뒤집는 과학적 근거가 아니다.

해결된 질문은 직접 SFT의 개선, 현재 공동 형식에서의 정확도 손실, 단순 retrieval 대비 C의 성능이다. 남은 핵심은 강한 모듈형 대안 대비 실용적 가치다. 현재까지의 setup·diagnostic 체류와 iter_044 운영 실패를 같은 track에 연결하며 유효 실험 횟수와 구분한다.

이번에는 새 문헌·loss·주변 진단을 추가하지 않는다. 고정 비교 후 동일 T305 적응 baseline 검토 또는 track 보류 중 하나를 선택한다.

# Hypothesis

원 계획의 H_modular, H_residual, H_budget을 유지한다. 모듈형 모델이 C의 정확도를 보존하며 비용을 줄일 수 있다. C가 우세하더라도 target 적응 차이가 경쟁 설명으로 남는다. 권한 복구는 어느 가설도 지지하지 않는다.

# Limitation Evidence / Correct Usage Checks

대상은 `padchest-sentence-grounding-and-joint-retention`의 observed 주장이다. iter_041 원 리뷰에서 C 독립 F1@0.3=0.57795와 공동 AB/BA=0.38108/0.35417의 관찰은 유효하지만 비용 결합 판정에는 blocker가 남는다. 이번은 diagnostic이며 method gate를 우회하지 않는다.

C의 공식 template·greedy·I-short·caps 1000/2000/4000, adapter digest와 기존 protocol 연결을 유지한다. MG는 공식 evaluation 전처리, uint16 변환 근거, 실제 resize/padding affine, cxcywh·confidence·WBF 순서를 검증한다. random initialization fallback, sample drop, 공식 test loader 호출을 허용하지 않는다. checkpoint 출처·학습 자료·중복·이용 조건 확인도 상속한다.

# Contribution Path / Baselines / Reuse

가장 가까운 방법은 MedGrounder다. C, MG-P, MG-MS와 D24에서 고른 MG-selected를 원 계획대로 비교한다. target 적응·사전학습·입력 해상도·annotation budget 차이를 보고하며 oracle 비교나 동일-budget 비교로 부르지 않는다. contribution은 미확정이다.

현재 `approach/modular-grounding-comparison`과 HEAD `e908c7d9ccf65e8db0b499d74bbd7fa042f6fce9`를 유지한다. 14개 파일은 현재 기반에 있으므로 재반입하지 않는다. 출처 `b50aa230a86c6d5b6c6b280fe718170ce4ecf220`와 실제 바이트 일치를 이번 계획에서 확인했다.

재사용 파일은 `pg43_run.py`, `pg43_eval.py`, `pg43_retrieval.py`, `pg39_spec.py`, `pg39_data.py`, `pg41_verify.py`, `rsna_diag/{__init__,generate,geometry,metrics,parse,prompts,lora,queue_lock}.py`다. 이는 경로 설명이며 reuse manifest의 glob 지정이 아니다. 원 manifest의 개별 파일과 required_checks를 따른다.

runner·순수 helper의 제한 승인을 유지한다. pg43_eval의 import 검증과 평가 완료 연결은 needs_fix다. pg41_verify는 C 순수 JSON 보조 채점에만 사용한다. 미사용 과거 CLI를 실행하거나 전수 정비하지 않는다.

# Proposed Experiment

## 0. 관리 실행 선행 조건

현재 GPT 계획 역할은 파일을 수정하지 않는다. 연구 Claude에도 자기 권한 변경을 지시하지 않는다. 관리 권한이 있는 별도 실행이 다음을 적용해야 한다.

1. 현재 main 관리 코드와 실제 Claude 실행에 적용되는 설정을 확인한다. 별도 worktree가 필요하면 관리 실행이 생성하며 실행 중인 상위 작업 폴더의 브랜치를 바꾸지 않는다.
2. 공식 저장소 revision 조회, 필요한 공개 코드·checkpoint·package의 격리 다운로드와 설치, 읽기 전용 blob 검사를 허용하는 최소 변경안을 적용한다. `git hash-object`는 객체를 쓰는 `-w`를 포함한 광범위 허용으로 바꾸지 않는다. 다운로드 대상·출력 경로 제한은 실제 권한 문법과 적용 결과로 확인한다.
3. `agent/`, `legacy/`, `hf_cache/`, 상위 관리 파일·연구 Git metadata 보호, 파괴적 Git·sudo·push 제한은 유지한다. 전역 권한 해제나 다른 실행기를 통한 deny 우회를 사용하지 않는다.
4. 허용 회귀 검사는 이전에 거부된 공식 SHA 조회, 공식 requirements 조회, 14개 파일의 읽기 전용 blob 확인과 전용 환경의 Python 실행을 포함한다. 거부 회귀 검사는 보호 경로 수정·파괴적 명령에 대한 정책 판정을 검사하며 실제 파괴적 명령을 실행하지 않는다.
5. `tests/test_convergence_policy.py`의 관련 검사를 보완하고 영향을 받는 실행 인자·권한 테스트를 수행한다. 실제 연구 호출에 변경 설정이 적용된 근거와 관리 commit·설정 digest를 남긴다. 관리 변경은 연구 기록 자동 커밋과 분리한다.

이 선행 작업이 완료됐다는 근거가 없으면 연구 Claude 호출을 보류한다. 단순 사용자 진행 응답을 설정 적용의 증거로 취급하지 않는다.

## 1. 동작 확인

권한 적용 후 원 계획 전체를 읽고 격리 환경·공식 revision·두 checkpoint를 확보한다. 기존 medgemma와 hf_cache는 변경하지 않는다. 디스크·CUDA/PyTorch 호환성, import, GPU 가용성과 D8 실제 입력을 검사한다. 다운로드·설치 실패는 명령 권한 거부와 구분해 기록한다.

기존 manifest의 D24 48문장과 V96 192문장, T305 출처와 비중복을 확인한다. C completion→원본 protocol→record config→adapter→현재 영상·prompt·GT 연결을 검증한다. MG 공식 함수와 wrapper의 실제 tensor·출력, 좌표 왕복, empty·복수 box·비정상 box fixture 및 재개 검사를 완료한다.

## 2. 가능성 탐색과 선택 잠금

D24에서 MG-P와 MG-MS의 raw logits·5개 query box를 저장한다. threshold 0.2/0.4/0.6/0.8, WBF true·IoU 0.1·skip 0.0·NMS false를 유지한다. checkpoint별 F1@0.3 최대, 동률이면 F1@0.5·낮은 FP·높은 threshold 순으로 선택하고 checkpoint까지 완전 동률이면 MG-MS를 선택한다. 공식 threshold 0.8도 보조 보고한다.

C는 총 2/4 worker, MG-selected는 GPU당 1 worker에서 batch1/4를 비교한다. batch4가 안전하지 않으면 batch2를 사용한다. batch 확대의 이득이 없고 메모리가 허용할 때만 GPU당 2 worker를 추가 비교한다. 품질·출력 정합성을 유지하며 처리량이 좋은 구성을 잠근다.

## 3. 고정 비교 본실행

기술 gate 통과 후 두 MG checkpoint의 V96 384문장 출력을 모두 생성한다. 낮은 성능을 이유로 정상 모델을 제외하지 않는다. C 주정확도는 기존 192건을 재사용한다.

선택 시스템과 C에 대해 각각 V96 96환자×2문장의 작업을 6개 paired timing block에서 측정한다. 선행 순서는 C/MG/C/MG/C/MG다. 두 시스템은 순차 실행하고 각 시스템이 허용된 두 GPU를 사용한다. end-to-end wall, 장치 구간의 합인 device-seconds, 실제 환자 dispatch부터 두 문장 완료까지 latency, model-only·cold loading·메모리를 구분한다. worker overlap을 device 시간에 중복 합산하지 않는다.

비용 비율은 block별 log 비율의 평균±t(5)로 95% CI를 산출한다. 원시 비율도 보고한다. 요청 단위 bootstrap을 장치 비용의 반복 구간으로 대신하지 않는다.

## 4. 독립 확인과 규모 경계

이번 V96는 개발 자료이며 독립 확인은 없다. 새 환자·학습·seed·reserve를 추가하지 않는다. 학습 및 epoch별 validation은 해당하지 않는다. 다음 동일 T305 적응 비교도 별도 리뷰·계획 사항이다.

기본 요청량 2976건, 조건부 MG 구성 48건 및 warm-up·재개·재시도 별도 집계를 유지한다. 원 계획의 C 16.75환자/분에 따른 C timing 본체 약 34분과 전체 GPU 약 1–3시간은 추정이다. 설치 시간은 미확정이며 D 실측으로 ETA를 갱신한다.

실행 직전 nvidia-smi와 물리/논리 장치 대응을 확인한다. GPU별 동시 peak와 타 프로세스 점유에 worker당 2GiB 여유를 더해 안전성을 판정한다. CPU/RAM/I/O 경합도 기록한다. 다른 사용자 프로세스는 변경하지 않는다.

# Implementation Tasks for Claude

관리 선행 조건이 확인된 뒤 수행한다.

1. 원 계획·이번 amendment·iter_044 review와 reuse_manifest를 읽고 상속 조건과 변경된 결과 경로를 기록한다.
2. 기존 14개 파일의 import closure와 실제 호출 경로를 검사하고 required_checks를 완료한다.
3. `pg43_eval.verify_import`의 protocol→completion 및 record config 연결을 보완한다. 과거 protocol의 source는 원본 SHA와 비교한다.
4. 평가 소스·metrics 의존성과 입력을 출력 평가 전에 잠근다. report·per_item·timing·decision을 digest로 연결하고 마지막에 completion을 확정한다.
5. 공식 MG wrapper, D8 검사, D24 잠금, V96·6개 paired timing을 실행한다. 중복·누락·비정상 child 종료·부분 결과와 동시 작성 검사를 포함한다.
6. C의 F1@0.3=0.5779513889, F1@0.5=0.2911458333을 독립 matching으로 재현한다. 불일치 시스템을 제외하고 PASS를 만드는 검증기는 허용하지 않는다.
7. `results/iter_045/legacy041_correction/`에 iter_041 원 plan·review·report·timing hash를 연결한다. 정확도와 비용 점추정을 보존하고 유효한 반복 비용 CI는 unavailable, 결합 판정은 unresolved로 기록한다. 원 blocker는 지우지 않는다.
8. 신규 결과·실측 비용·실패·종료 판단을 보고한다. 기존 세션은 삭제하지 않고 재개 가능 여부를 확인한다. 세션 연결 방식 자체를 연구 조건 변경으로 삼지 않는다.

# Evaluation (성공/실패 기준 포함)

원 계획 Evaluation 전체를 유지한다. 주지표는 최대 cardinality 일대일 matching으로 계산한 문장 F1@0.3의 환자 내·환자 간 평균이다. F1@0.5, recall, FP/문장, empty·invalid·EOS·truncation과 기존 층별 결과를 함께 보고한다. 정확도·FP는 paired patient bootstrap 10000회, seed4401, 97.5% CI다.

**모듈형 대안 지지:** MG−C의 F1@0.3 및 0.5 CI 하한 모두 ≥−0.03, FP 차이 CI 상한 ≤0.10, MG/C device 비율 CI 상한 ≤0.50, throughput 비율 CI 하한 ≥2.0, p95 latency 비율 CI 상한 ≤1.20을 모두 충족한다. 현재 내부 grounding 투자를 보류하고 track 전환을 권고한다.

**C 잔여 이점 지지:** C−MG F1@0.3 점차이 ≥0.05 및 CI 하한 >0, F1@0.5 CI 하한 ≥−0.03, FP 차이 CI 상한 ≤0.10, C/MG device와 p95 latency 비율 CI 상한 각각 ≤2.0을 모두 충족한다. 두 checkpoint의 정상 실행까지 완료됐을 때만 동일 T305 적응 baseline을 검토한다.

**과학적 불확정:** 어느 기준도 완결되지 않으면 track을 보류한다. 추가 표본·threshold·prompt·seed·timing 반복으로 연장하지 않는다.

**실행 실패:** 권한·checkpoint·입력·좌표·provenance·정합성 문제로 비교가 무효면 해당 범위를 execution_failed로 기록한다. 모델 가설을 기각하지 않는다. 관리 준비나 테스트 통과만으로 valid_experiment=true를 부여하지 않는다.

**필수 회귀:** C 기존 수치 불변, 동일 입력의 timing token 정합성, 모든 시스템의 독립 수치 대조, config/protocol 변조 거부, 요청 wall 합과 device interval union의 구분, 비용 CI 부재 시 양성 결합 판정 금지, 기존 결과·부분 파일 보존을 확인한다.

# Risks / Checks

- 이번 계획만 저장해도 실제 권한 설정은 바뀌지 않는다. 관리 적용 증거가 연구 실행의 선행 조건이다.
- 권한 복구 후에도 실제 네트워크·dependency·checkpoint 문제가 남을 수 있다. 성공을 미리 단정하지 않는다.
- V96 반복 사용과 target 적응 차이는 그대로 남는다. CI가 선택 편향을 해소하지 않는다.
- 기술 실패 timing block은 원본을 보존하고 원인이 확인된 경우에만 paired block 전체를 새 attempt로 재측정한다. 느리거나 불리한 block을 제외하지 않는다.
- 관리 변경, 연구 코드 checkpoint, 실험 유효성, 방법론 기여를 구분한다. 원본 판정과 자산을 보존한다.

## 대규모 GPU 필요 후보

원 계획의 다기관 공동 grounding·비groundable 거부 multi-task post-training 후보를 보존한다. 이번 비교에서 중요한 잔여 가치가 확인되기 전 대규모 학습 투자를 우선하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/REPORTING_STYLE.md`, 최근 INDEX 기록, iter_044 plan/review/report와 review.json의 code_assets, reuse_manifest, 관련 LIMITATIONS·CODE_ASSETS 원문을 확인했다.
- 기준 `agent/runs/iter_044/plan.md`의 SHA256은 실제 계산으로 `e59714854fbe60c50e2135181592ea8d0868fd8e3af54b278a68a06f779312af`와 일치했다.
- `orchestrator.py:717–726`은 연구 Claude에 `acceptEdits`, `agent/prompts/claude_engineer.md`, `agent/claude_settings.json`을 전달한다. 현재 설정은 curl·wget을 명시적으로 거부하고 git ls-remote·git hash-object를 허용 목록에 넣지 않는다.
- `agent/prompts/claude_engineer.md:50–51`은 코드를 research/ 안에서만 수정하고 agent/는 읽기만 하도록 정한다. 설정에도 agent/ Edit·Write 거부가 있다. 따라서 연구 Claude에게 자기 권한 설정 수정을 맡기는 복구 계획은 실행 가능하지 않다. 현재 GPT 계획 환경도 read-only이며 승인 상승 경로가 없다.
- research HEAD는 `e908c7d9ccf65e8db0b499d74bbd7fa042f6fce9`이고 status·diff는 비어 있다. 반입된 14개 파일 모두를 실제 파일 바이트와 출처 `b50aa230a86c6d5b6c6b280fe718170ce4ecf220`의 Git blob으로 대조해 일치를 확인했다. 현재 기반에 있으므로 중복 reuse_assets는 필요 없다.
- `research/results/iter_044`, `research/results/iter_045`, `research/results/environments`는 아직 없다. 신규 비교 결과나 환경 구성이 완료됐다는 근거는 없다.
- iter_041 review.json 원문에서 정확도 관찰은 유효하지만 request-wall CI를 device-seconds 판정에 연결한 blocker가 남아 있음을 확인했다. 이를 방법 진입 근거로 사용하지 않는다.
- `pg43_eval.py`, `pg43_run.py`, `pg41_verify.py`의 관련 경로를 읽었다. 원본 protocol/config 연결, 평가 의존성 잠금, 모든 시스템을 포함하는 독립 검증은 여전히 필수다.

## 의미와 선택

과학적 전략은 iter_044에서 이미 비교·선택했으며 뒤집을 새 결과가 없다. 이번에는 문헌 조사나 새 진단을 늘리지 않는다. 관리 실행이 적용할 권한 복구와 연구 Claude가 수행할 원 실험을 분리한다. 연구 실행을 막는 설정은 그대로인 채 proceed로 넘기지 않는다.

## 남은 실행 조건

관리 권한이 있는 별도 실행에서 최소 설정 변경과 회귀 검사를 적용해야 한다. 이는 설치나 GPU 사용의 재승인 요청이 아니라 현재 역할 밖의 설정 적용 요청이다. 실제 다운로드·dependency·checkpoint·GPU 호환성은 그 뒤 검증하며 권한 복구만으로 성공을 예상하지 않는다.
