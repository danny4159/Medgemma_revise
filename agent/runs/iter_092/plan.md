# 요약

- **이번에 할 일:** R305/G285에서 학습을 재개하고 원 R/G 평가를 끝낸다.
- **필요한 이유:** 직전 실행은 학습 오류가 아니라 구현 응답 조기 종료로 중단됐다.
- **확인할 기준:** 기존 epoch6/12 선택 규칙과 E128 recall·모순 기준을 유지한다.
- **주의·다음:** 완료된57 updates와 G epoch4 validation은 반복하지 않는다. pending이면 같은 구현 세션에서 기다린다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray PadChest-GR
- 모델: MedGemma 1.5의 report-only/위치 보조 LoRA
- 과제: 흉부 X-ray 한 장에서 현재 소견 판독문을 생성한다
- 가설: 같은 판독 supervision에 위치 정답을 추가하면 정확한 소견 회복이 늘거나 언급 성향만 달라질 수 있다
- 질문: 같은 판독문으로 학습해도 위치 정답을 배우면 더 정확하게 읽는가?
- 변경: 실행 복구
- 연결: iter_091에서57 updates와 안전 checkpoint는 보존됐지만 완료 전 세션 종료로 최종 비교가 남았다
- 작업: 완료 대기 연결을 보완하고 남은 학습·E128 평가로 위치 보조 CE의 후속 투자 여부를 판단한다

# Current Understanding

기준은 `agent/runs/iter_091/plan.md` SHA256 `63b843678cf3107a886634609d5547397cd65c9bc369484b79209c20dde70a95`다. 부모 `agent/runs/iter_090/plan.md` SHA256은 `a305c99f6f0473e832560a875d854dafdf9dbe7ace5a330b0abc23a98ce45fb8`다. 두 계획의 과학적 조건을 상속하고 이번 문서는 최신 재개 상태·대기·저장 위치를 갱신한다.

구현자는 `research/results/iter_090/amendment_v2.json`, `recovery/amendment.json`, `recovery/training_gate.json`, `recovery/stage_decision_rules.json`, `recovery/decisions/expand_epoch6.json`, 같은 디렉터리의 `expand_epoch6_semantic_confirmation.json`·`grounding_evidence_check.json`, `semantic/reference_amendment.json`·`semantic/decision_details.json`을 연결한다. 오래된 준비 amendment의 training_authorized=false를 이후 recovery gate와 혼동하지 않는다.

현재 소스는 `41232edf304c85f3e747c9da7dae2fe9f473d2ac`다. 전체 재사용 승인 상태는 아니며 실제 사용하는 경로의 검증이 필요하다. 직전 리뷰상 유효 recovery 누적은846 updates다. 초기 비recovery266 updates는 비교·선택에서 제외하고 비용에만 남긴다.

# Strategy Check / 연구 방향 판단

**이어받는 관찰 → 남은 설명 → 최소 비교 → 결정 변화:** 위치 학습 가능성과 기존 시스템 간 판독 변화는 유지된다 → 위치 보조 학습이 정확한 회복을 늘리는지, 좌표 출력·언급 성향만 바꾸는지는 남는다 → 같은 R/G 통제 비교를 완료한다 → 추가 seed·공간 대응 대조의 한정 확인 또는 현재 보조 CE 투자 보류를 선택한다.

iter_091 리뷰의 권고를 바꾸지 않는다. 같은 현상의 실행 복구이며 새 후보 탐색이 아니다. 현재 방법의 추가 변경이나 다른 연구 질문 전환보다, 보존된 학습을 마치는 정보 가치가 높다. 실행 실패는 인식·선택·결합의 경쟁 설명을 줄이지 못했으므로 이를 과학적 반증으로 사용하지 않는다. 지배 비용은 남은 학습·생성·의미 평가이며 불변 기술 검사를 반복하지 않는다.

# Hypothesis

원 H1–H4를 유지한다. 위치 보조 CE가 정확한 소견·위치·속성 회복을 늘릴 수 있고, 좌표 출력만 개선하거나 언급과 모순을 함께 늘릴 수도 있다. 직접 판독 SFT만으로 충분할 가능성도 있다. R/G 차이는 보조 학습의 총 효과이며 공간 대응의 고유 기전을 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`의 iter_012 validated 근거는 위치 학습 가능성을, `padchest-regional-report-concatenation-conflict`의 iter_088 observed 근거는 C-H 자동 확대를 피할 이유를 제공한다. 어느 것도 이번 R/G 판독 효과를 이미 검증한 근거가 아니다.

공식 MedGemma 1.5 revision·processor/template·전처리·assistant mask·좌표·CE 정규화·생성 cap을 유지한다. recovery gate와 config의 불변 hash를 연결해 기존 수치·resume 검증을 재사용한다. 모델 정답률100%를 새 실행 gate로 만들지 않는다.

# Contribution Path / Baselines / Reuse

기준 계획의 CURE·MAIRA-2 관련 선행 비교를 유지하고 새 문헌조사는 하지 않는다. 이번은 표준 공동 CE의 통제 진단이며 신규 contribution은 미확정이다.

주대조 R과 G는 동일 base·판독 target·입력·환자 순서·update 수·LR 선택 기회를 사용하고 위치 CE만0/1로 다르다. base와 CURE C-G는 참고 시스템이며 학습 자료·모델·노출 차이를 방법 효과로 해석하지 않는다. 강한 모듈형 판독 비교는 향후 실용 주장에 필요하지만 이번 복구 범위에는 추가하지 않는다.

현재 브랜치에 파일이 있으므로 `reuse_assets=[]`다. `report90_recovery_launch.py`, `report90_recovery_train.py`, `report90_train.py`, `report90_stable_v2.py`, `report90_recovery_train_verify.py`를 재사용한다. validation은 `report90_recovery_gen_queue.py`, `report90_recovery_gen.py`, `report90_recovery_ground_eval.py`, `report90_recovery_blind.py`, `report90_semantic_eval.py`, `report90_semantic_verify.py`, `report90_decide.py`, `report90_select.py`를 사용한다. 최종 경로는 `report90_e_prepare.py`, `report90_e_reference.py`, `report90_final_queue.py`, `report90_final_verify.py`, `report90_final_blind.py`, `report90_e_adjudicate.py`, `report90_e_recheck.py`, `report90_effects.py`, `report90_effects_verify.py` 및 기존 CURE wrapper다. 각 config의 의존 파일도 함께 확인한다.

iter_091의 launcher needs_fix는 운영 연결 문제다. 우선 소스 변경 없이 완료 대기를 바로잡는다. 아직 실행하지 않은 평가 경로는 코드 존재만으로 승인하지 않고 실제 입력·reference·checkpoint·출력 provenance를 검사한다.

## 대규모 GPU 필요 후보

여러 모델·기관·학습량에서 report-only/정확한 위치/교란 위치/모듈형 판독을 교차 비교하는 후보를 보존한다. 이번에는 실행하지 않는다.

# Proposed Experiment

## 유지 / 변경 / 미완료

**유지:** GOAL, 데이터·split·target, R/G loss, seed17, LR1e-4/2e-4, rank16/alpha32/dropout0.05, effective batch8·microbatch1, optimizer·수치 경로, 의미 규약, epoch6/12·선택·평가·종료 기준.

**변경:** 최신 checkpoint에서 재개하고 pending 동안 구현 세션을 종료하지 않는다. 새 인계 manifest·집계·보고서는 `research/results/iter_092/`와 `agent/runs/iter_092/`에 저장한다. 기존 recovery의 새로운 attempt/event/checkpoint와 미생성 후속 산출물은 사용자 승인대로 append-only로 남긴다. 과거 파일을 덮어쓰거나 경로 변경만을 위해 config를 수정하지 않는다.

**미완료:** 네 trajectory epoch6, validation·의미 평가·연장 판단, 조건부 epoch12, 최종 선택 잠금, E128 reference·생성·평가·독립 집계.

## 1. 최신 상태에서 재개

실행 직전 실제 소유 프로세스·시작 시각·lock 소유를 확인한다. 살아 있는 supervisor가 있으면 연결해 기다리고 중복 실행하지 않는다. lock 파일 존재만으로 실행 상태를 단정하거나 삭제하지 않는다. `nvidia-smi`와 상속된 GPU0,1의 UUID·논리/물리 대응을 확인한다.

재개 기준은 다음과 같다.

- R LR1e-4: `research/results/iter_090/recovery/train/R_lr0.0001/checkpoint_000305.pt`, SHA256 `071e2ca245e3d7805ca5b8f33f6bee964b7bed85aab5e50d2e4827c5f158ce98`.
- G LR1e-4: `research/results/iter_090/recovery/train/G_lr0.0001/checkpoint_000285.pt`, SHA256 `023d3816956ce9194784a4cbe886e953ce346e293e3180e2e7e699ca124a24ad`.
- LR2e-4 R/G: checkpoint128과 해당 sidecar/config를 확인한다.

R305/G285 모두 pending=null이다. G epoch4 validation은 완료됐으므로 반복하지 않는다. 실행 시 더 최신의 정당한 checkpoint가 있으면 attempt·hash·config 연결을 검증하고 이를 사용하며 오래된 상태로 되돌리지 않는다.

기존 환경의 Python 절대경로와 버전을 기록하고 `research/`에서 `python report90_recovery_launch.py --epochs 6`의 자동 resume를 사용한다. HF_TOKEN_PATH는 상속하되 값을 출력하지 않는다. adapter/optimizer/RNG/다음 batch 복원과 시작 step을 한 번 확인한다. 불변 수치·중간/epoch resume 기술 검사를 다시 학습으로 반복하지 않는다.

## 2. 완료 대기와 종료 처리

학습·생성은 supervisor가 관리한다. 초기 연결 확인 후 `python ../experiment_wait.py --pid <실제 supervisor PID> --timeout 600` 또는 동등한 background completion 대기를 사용한다. 도구가 먼저 반환하면 그 task/session을 계속 기다린다. 상태 변화 없이 update 수를 조회하는 새 명령을 반복하지 않는다.

`experiment_wait.py`는 pending이어도 exit0이므로 반환 코드만으로 완료를 판정하지 않는다. pending이면 **동일 구현 호출을 유지하며 다음 대기**로 이어간다. background task를 만들고 최종 응답으로 턴을 끝내는 방식은 금지한다. 기다림 timeout은 실험 시간 제한이 아니다.

processes_exited일 때 supervisor exit 상태, 자식 결과, pending jobs, 필수 산출물과 verifier를 확인한다. 프로세스 소멸 자체는 성공이 아니다. epoch6 학습 완료도 전체 실험 완료가 아니므로 다음 평가·판단 단계로 진행한다. 오류·사용자 정지는 즉시 처리하고 안전 checkpoint와 실제 종료 상태를 기록한다.

운영 연결 수정이 필요하면 trainer/config digest와 분리한다. 변경 경로에 한해 pending→대기 유지, 정상 종료→검증 진행, 비정상 종료→오류 보존을 작은 제어 작업으로 회귀 확인한다. 불필요한 공통 orchestrator 리팩터링은 하지 않는다.

## 3. 기존 단계와 조건부 확대

동작 확인은 기존 recovery 검증 근거의 불변 연결로 대체한다. 새 변경·불일치가 있을 때만 영향 범위를 재검사한다.

가능성 탐색인 epoch2와 V32 의미 평가는 완료됐다. `expand_epoch6_semantic_confirmation.json`의 pending=false와 grounding evidence를 계승한다.

네 trajectory를 각각384 updates까지 마친다. V64 NLL epoch4/6, V32 실제 판독 epoch6와 고정 보조 grounding 일정을 수행한다. 저장된 유효 validation은 재생성하지 않는다.

조건별 LR은 epoch6 V64 NLL 최소로 선택하고 동률은 낮은 LR이다. 선택 조건 중 하나라도 epoch4→6 NLL이2% 이상 감소하고 V32 strict recall6−2가−5pp 이상이면 선택 R/G 모두 epoch12까지 연장한다. 연장 시 epoch8/12 NLL·V32 생성을 평가한다. 아니면 epoch6에서 끝낸다. 최종 공통 epoch는 선택 R/G의 공통 NLL 평가 checkpoint 중 합 최소, 동률은 이른 epoch다. 저장된 stage_decision_rules가 기준이며 E/CURE 점수를 선택에 쓰지 않는다.

## 4. 설정 잠금 후 E128

선택·prompt·parser·의미 규약을 잠근 뒤 E128을 연다. 원 환자/study/영상/raw·u8 pixel 중복·노출 검사를 적용하고 불가피한 적격성 교체만 원 seed·hash 규칙으로 기록한다. 비정상96명·비정상 표기 없음32명의 원 구성을 유지한다. reference는 모델 출력 전에 작성한다.

R/G/base/CURE C-G 각각128개로 총512개 판독을 생성한다. box 보유 hash 순32명의 R/G grounding64개를 별도로 평가한다. greedy·seed17·cap1024 유지, 비EOS cap 도달에만2048→4096을 적용한다. 오답 때문에 재생성하지 않는다. 누락·중복·source/adapter/protocol digest와 원문 anchor를 검증한다.

E는 target 적응에 쓰지 않은 집단이지만 foundation/CURE 노출이 완전히 배제된 임상 독립 test라고 부르지 않는다. 추가 seed·기관 검증은 별도 투자 판단이다.

## 5. 자원·예상 비용·보존

현재846 updates에서 epoch6까지690 updates가 남는다. 조건부 epoch12는768 updates 추가다. 기존39.57초/update와 두 GPU 병렬의 단순 추정은 학습 약3.8시간, 연장 약4.2시간이다. validation·checkpoint·생성·의미 평가·외부 점유 지연은 별도이며 상한이 아니다. 새 이벤트의 실측으로 갱신한다.

두 GPU에 독립 trajectory를 하나씩 배정한다. 기존 microbatch1/2 비교와 최근 peak reserved13.51GiB를 재사용한다. training worker 두 개의 peak와 worker당2GiB 여유는24GiB를 넘으므로 GPU당1개가 타당하다. 추론도 기존 peak10.61GiB 기준 두 worker와 여유 합이25.22GiB이므로 GPU당1개를 우선 유지한다. 동일 조건의 기존 처리량 증거를 재사용하고 이번 복구를 위해 batch 탐색을 반복하지 않는다. 실제 긴 출력·외부 점유를 실행 전에 다시 확인한다.

32 updates 및 epoch 경계 checkpoint·안전 resume를 유지한다. 다른 사용자 프로세스와 기본 환경·hf_cache는 변경하지 않는다. 환경 구성이 필요하면 먼저 알리고 승인된 격리 경로를 사용한다.

# Implementation Tasks for Claude

1. 기준 plan·amendment·리뷰와 최신 상태를 연결한 iter_092 인계 manifest를 작성한다. iter_091에 없던 보고서를 과거 완료 보고서처럼 소급 생성하지 않는다.
2. 소유 프로세스·lock·checkpoint/config/code digest 확인 후 기존 자동 resume를 사용한다. R277/G256으로 돌아가지 않는다.
3. supervisor가 pending이면 같은 세션에서 완료 대기를 유지한다. 완료·오류·판단 경계에서만 다음 작업을 결정한다.
4. epoch6 검증·V64/V32 의미 평가 후 원 조건에 따라 epoch12를 수행하거나 학습을 종료하고 최종 선택을 잠근다.
5. E128 reference·생성·평가와 별도 metric/bootstrap/민감도 재계산을 마친다. 실제 사용한 미완료 평가 경로의 provenance와 입력 연결을 확인한다.
6. 최종 보고서에 상속/신규 산출물, 유효/제외 updates, 실제 비용, 원 기준 충족 여부와 미실행·미검증 범위를 나눈다. 소스는 orchestrator의 보존 절차에 맡긴다.

# Evaluation (성공/실패 기준 포함)

비정상 층 환자 평균 strict recall은 reference의 확정 소견과 명시 위치·속성이 확정적으로 회복된 경우만 인정한다. possible-only, 위치·속성 누락, 명시 reference 모순, 내부 모순, 판단불가, 형식 실패, grounding F1@0.3/0.5를 분리한다. 미표기 소견을 정상 또는 임상 FP로 만들지 않는다.

모델명을 가린 assistant 평가의 원문 anchor·모호성을 보존한다. 고정 E hash24명의 네 조건과 결정을 좌우하는 사례를 재점검한다. 환자 bootstrap10,000회·seed89017·두 층 별도 재표집, 모호 reference 제외와 모호 대응 불인정 민감도를 유지한다. 전문의 검증으로 표현하지 않는다.

- **양성:** G−R strict recall≥5pp, 명시 모순 증가가 전체·비정상 층 각각≤3pp, 추가 회복≥5명, 한 환자 제거 후 양의 방향 유지, 두 모호성 민감도에서도 양의 방향 유지. CI가0을 포함하면 탐색 신호와 확증을 구분한다. 다음 투자는 추가 seed·공간 대응 대조의 한정 확인 검토다.
- **음성:** R이 작동해도 G 이득이 없거나 모순 비용을 초과하면 현재 위치 보조 CE 투자를 보류한다. bbox 개선은 판독 전이와 분리해 보존한다.
- **불확정:** 허용된 연장 후 수렴·의미 평가·환자 변동을 구분한다. E 결과를 보고 조건을 추가하지 않는다. 의미 불확실성이 지배하면 보류하고 안정된 효과의 표본 변동만 남으면 별도 확대의 정보 가치를 검토한다.
- **실행 문제:** digest·resume·누수·평가 결함은 해당 경로의 blocker다. 사용자 인계 정지와 이번 세션 조기 종료를 구분하며 모델 가설의 음성으로 바꾸지 않는다.

# Risks / Checks

- pending의 exit0, SDK 호출 성공, Git checkpoint를 실험 완료로 취급하지 않는다.
- G epoch4 validation과 완료된57 updates를 반복하지 않는다.
- trainer/config digest를 바꾸거나 검사를 우회해 resume를 강제하지 않는다.
- 기존 recovery 쓰기 예외는 신규 append-only 산출물에만 적용하며 덮어쓰기·삭제를 허용하지 않는다.
- 불변 검증 재사용과 아직 실행하지 않은 E 평가 경로의 승인을 구분한다.
- C-H·E192·새 loss·모델·modality 탐색을 추가하지 않는다. 원 비교 종료 후 full review에서 후속 투자와 실험 판정을 분리한다.

# 계획의 근거 (GPT 조사 노트)

이번 라운드는 read-only로 원 계획·리뷰·실제 소스와 checkpoint를 확인했다. 새 문헌조사·파일 변경·실험은 하지 않았다.

- 기준 `agent/runs/iter_091/plan.md` SHA256은 `63b843678cf3107a886634609d5547397cd65c9bc369484b79209c20dde70a95`, 부모 iter_090은 `a305c99f6f0473e832560a875d854dafdf9dbe7ace5a330b0abc23a98ce45fb8`다.
- 현재 research HEAD는 `41232edf304c85f3e747c9da7dae2fe9f473d2ac`이며 작업 트리는 깨끗하다. 필요한 report90 파일은 현재 브랜치에 있어 반입이 필요 없다.
- R305의 SHA256 `071e2ca245e3d7805ca5b8f33f6bee964b7bed85aab5e50d2e4827c5f158ce98`, G285의 `023d3816956ce9194784a4cbe886e953ce346e293e3180e2e7e699ca124a24ad`를 직접 계산해 sidecar와 대조했다. 둘 다 pending=null이다.
- iter_091 원 리뷰는 R28/G29 updates 추가, G epoch4 validation 완료, 최종 응답 이후 background 작업 killed를 확인했다. 이번 계획은 이전 R277/G256으로 돌아가지 않는다.
- `stage_decision_rules.json`, 확대 결정·semantic confirmation·grounding evidence와 두 amendment를 읽었다. epoch6 확대는 유지되고 semantic_V32_pending=false다. 초기 비recovery266 updates는 계속 제외한다.
- `experiment_wait.py`는 pending에서도 exit0을 반환하며 experiment_success=null이다. 따라서 명령 성공만으로 실험 완료를 판정하면 안 된다. launcher는 종료 시 자식을 정지·회수하므로 구현 세션 종료 전 완료 대기가 핵심이다.
- CODE_ASSETS와 iter_091 원 code_assets는 launcher 운영 연결을 needs_fix로 둔다. 소스 변경이 반드시 필요한 것은 아니며 trainer/config digest를 유지한 실행 연결 보완을 우선한다.
- LIMITATIONS 및 iter_012/088 원 limitation_updates를 확인했다. 위치 학습 가능성과 단순 영역 결합의 모순 관찰을 유지하며, R/G 판독 효과의 검증으로 전용하지 않는다.
