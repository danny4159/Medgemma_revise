# 요약

- **이번에 할 일:** 기존 D8 82건을 보존하고 남은 생성·평가 경로를 연결해 원 E96 비교를 완료한다.
- **필요한 이유:** CURE 로딩은 해결됐지만 전체 비교가 없어 누락 회복과 언급 성향을 구분하지 못했다.
- **확인할 기준:** 원 8조건·표본 규칙·metric·E192 확대 및 종료 기준을 유지한다.
- **주의·다음:** 개발 자료의 assistant 의미 평가다. 실행 완료와 가설 지지를 구분하고 full review로 다음 투자를 판단한다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray PadChest-GR
- 모델: MedGemma 1.5와 기존 RSNA adapter, MedGemma 1과 공개 CURE adapter; 신규 학습 없음
- 과제: 흉부 X-ray에서 판독문과 영역별 설명을 생성한다
- 가설: 증가한 언급은 정답 회복 또는 불확실·잘못된 언급 증가일 수 있다
- 질문: 더 많이 말하는 것이 더 정확히 읽는 것인가?
- 변경: 실행 복구
- 연결: iter_085에서 CURE 로딩과 D8 일부 출력을 확보했으나 본평가는 미실행이다
- 작업: 부분 출력의 재개와 의미 평가를 연결해 원 비교를 끝내고 후속 방법의 필요성을 판단한다

# Current Understanding

이 계획은 동일 실험의 실행 보완이다. 필수 기준 문서는 `agent/runs/iter_085/plan.md`(SHA256 `5663189557a03e3e30b620dbb2202fd86b754ca9b2eebbe6eeb6fadffc962f2f`)와 상속된 `agent/runs/iter_084/plan.md`(SHA256 `42334bc910f7abbb26e27f60696b59b5d2a974d6143fbe2aed153e08c315fefd`)다. 구현 담당은 두 원문과 iter_085 review.json을 읽는다.

**유지:** 연구 질문, 8조건, prompt, 모델·정밀도, 표본 선택, 정답 의미, metric, 생성 길이, 확대·종료 기준, 기존 결과와 캐시 보존.

**이번 변경:** 새 산출물을 `research/results/iter_086/`에 저장한다. 구버전 출력 검증, 원본을 건드리지 않는 결과 계승, source/GPU 변경의 명시적 연결, 캐시 격리, E 표본·평가·완료 경로를 구현한다. 현재 구현 담당은 Claude다. 과거 문서의 Codex 표기는 당시 실행 기록으로 보존한다.

**미완료:** D8 남은 206회, 공식 hybrid 결합, CURE 중단 재개, 수동 token 회귀, 처리량·메모리 배치 선택, 최종 자료 적합성과 학습 노출 확인, 의미 평가 잠금, E96 및 조건부 E192, 독립 수치 재계산.

iter_085의 execution_failed와 valid_experiment=false는 유지한다. 82건의 EOS 종료나 로딩 성공을 판독 성능 근거로 바꾸지 않는다.

# Strategy Check / 연구 방향 판단

iter_084의 전략 판단과 iter_085의 실행 복구 권고를 유지한다. **위치 SFT의 grounding 개선과 불확정 자유 판독 변화 → 확정 회복·불확실 표현·언급 성향·단순 prompt 효과·CURE 충분성 → 같은 base–adapter 및 전체/영역 결합 비교 → 기존 방식 채택 또는 구체적인 최소 개입 검토**로 연결한다.

이번은 같은 현상의 탐구를 위한 실행 복구이며 새 후보 탐색이 아니다. 새 학습은 판독 실패 근거가 아직 없고, 다른 modality 전환은 확보한 실행 경로를 버리는 비용이 있다. 따라서 원 비교 완료를 선택한다. MRI 복구·TOF·문헌 discovery는 보류 상태를 유지한다.

현재 track의 두 반복은 유효 실험 두 회가 아니다. 직전까지의 주요 재작업은 환경·재개·캐시 경계였고, 정확한 누적 비용 비율은 기록되지 않았다. 이번에는 그 경로를 한정 수정한 뒤 실제 출력·평가에 투자한다. 새로운 전략 조사나 불변 검증의 전수 반복은 하지 않는다.

# Hypothesis

원 H_recovery/H_propensity/H_prompt/H_existing/H_residual을 유지한다. 확정 소견 회복, 불확실·모순 언급 증가, 체계적 prompt 효과, CURE의 충분성, 영역 출력과 결합 결과의 잔여 충돌을 구분한다. checkpoint 비교만으로 내부 인식 개선이나 위치 supervision만의 인과 효과를 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

세 limitation ID는 기존 grounding 성과와 QA·인터페이스 해석 경계를 연결한다. iter_012/016/017 원 리뷰의 evidence·usage_checks·remaining_questions를 계승한다. 자유 판독의 검증된 한계를 대신하지 않으므로 diagnostic·method_stage=none이다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, adapter `results/iter_012/train/lr2e-4_s17/epoch_05`, state digest `e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11`를 유지한다.

CURE source `9365333856c0534af0cb05cb4291ce48dd95bb1d`, MedGemma 1 base `290cda5eeccbee130f987c4ad74a59ae6f196408`, adapter `4bb5dc5a5025a854d1f25e475769949915b08b44`를 유지한다. 1.5에 CURE를 로드하지 않는다. 기존 strict PEFT key·shape·값·저장 모듈과 첫 공식 출력 검증은 자산·코드·설정이 불변이면 재사용한다. 바뀐 입력·실행 경로만 추가 검증한다.

모델 정답률 100%는 실행 gate가 아니다. ID·tensor·token·정답 연결 오류와 내용 오답을 구분한다. bbox 파싱 실패로 읽을 수 있는 판독 문장을 삭제하지 않는다.

# Contribution Path / Baselines / Reuse

문헌 판단은 iter_084 원문을 계승한다. CURE의 알려진 recall–precision trade-off를 재현하는 것만으로 새 기여를 주장하지 않는다. PadChest에서 hybrid를 사용하는 것은 확장 검증이며 논문 benchmark 재현과 구분한다. MAIRA-2·가까운 grounding/reporting 연구의 미확인 조건은 신규성 주장 전에 확인할 사항으로 남긴다.

고정 비교는 M15-R/M15-S/B0-R/B0-S/M1-R/M1-G/C-G/C-H다. 앞 네 조건은 1.5 base/RSNA adapter × 중립/체계적 prompt다. M1-R은 bf16 일반 판독, M1-G와 C-G는 동일 NF4 GRG, C-H는 공식 AGRG-29와 C-G의 결합이다. 환자당 36회 생성으로 8조건을 얻고 C-G를 중복 생성하지 않는다. pristine base를 사용하며 adapter disable로 대체하지 않는다. 29개 위치는 GT와 무관하게 모두 사용한다.

현재 branch와 HEAD `1fad82e7d39c3468ffbbe27a5f94eaf6d32e0415`를 이어간다. 작업 트리는 확인 당시 깨끗했고 필요한 파일이 존재한다. reuse_iteration=0, reuse_assets=[]이며 전체 snapshot 승인을 뜻하지 않는다.

- `report85_cure_check.py`, `report84_preflight.py`: 고정 자산의 제한된 CURE 로딩·첫 출력 검사 승인 범위를 재사용한다.
- `report85_d8.py`: 기존 로딩·생성 경로를 유지하면서 입력 manifest·stage·새 결과 경로와 버전별 검증을 연결한다.
- `report85_launch.py`, `test_report85.py`: 실제 자식 캐시, 새 경로, 장치 매핑·메모리·재개 검사를 보완한다.
- `pg39_data.py`: 승인된 metadata reader를 사용한다. `pg43_run.py`와 기존 rsna_diag helper는 실제 사용하는 claim·입력·adapter 경로만 검증한다. 기존 bbox evaluator를 문장 평가기로 전용하지 않는다.

기존 모델 파일·격리 환경·공식 source는 출처 확인 후 재사용한다. 수동 원본과 iter_084/085 산출물은 수정하지 않는다.

# Proposed Experiment

## 1. 출력 계승과 실행 복구

기존 M15 16·B0 16·M1 8건은 해당 실행 버전·protocol·completion 파일 봉인으로 검증한다. record_digest를 원본에 소급 삽입하지 않는다. M1G 8건과 CURE 34건은 행 digest·요청 ID·입력·protocol을 확인한다. CURE에는 전체 completion이 없으므로 부분 결과로만 계승한다.

iter_086에 원본 경로·파일 hash·행 ID·원 protocol·실행 버전·검증 결과를 연결하는 계승 manifest를 만든다. 새 요청 집합에서 검증된 완료 ID만 제외한다. 새 protocol digest로 원본 행을 덮어쓰거나 모든 구버전을 무조건 허용하지 않는다. 근거가 부족한 행은 보존한 채 격리하고 영향받은 요청만 별도 재생성한다.

과학적 설정과 실행 이력을 구분한다. 모델·processor·영상 tensor·prompt/token·정밀도·adapter·seed·cap은 동일해야 한다. GPU·source 경로가 바뀌면 이전/새 protocol 및 수정 내용을 연결하고 필요한 D8 동등성 검사를 한다. source/GPU 검사를 삭제해 무조건 재개하지 않는다. 가능하면 모델 로딩 전에 불일치를 검출한다.

자식 시작 전 보조 캐시를 iter_086 아래로 격리한다. HF_HOME/HF_HUB_CACHE/HF_XET_CACHE, XDG·Torch·Triton·CUDA·pip·임시 경로를 실제 자식 환경에서 확인한다. 기존 hf_cache의 모델은 명시적 로컬 경로로 읽고 새 쓰기는 하지 않는다. 인증 값은 읽어 출력하지 않는다. 기존 캐시 사건 기록은 보존한다.

`results/environments/cure085/bin/python`과 기존 실행의 실제 Python을 확인한다. environment_final.json의 오래된 2.5.1 기록과 recovery/validation·최종 protocol의 2.7.1 기록을 구분해 현재 실행 환경을 기록한다. 불필요한 재설치는 하지 않는다. 설치가 필요하면 먼저 알리고 승인된 격리 환경에서만 수행한다.

## 2. 자료 적합성 및 동작 확인

원 PadChest-GR metadata·보호 manifest를 사용한다. 보고서 접근 전에 H192/F120/test와 보호 환자·study·영상 ID를 제외한다. 기존 D8과 E도 분리한다. 실제 frontal 연결·pixel 중복·CURE 학습 노출을 확인한다. 확인된 train 노출은 주분석에서 제외한다. 미확인 노출을 독립 test로 표현하지 않는다.

환자당 대표 영상은 원 `sha256(84017|PatientID|ImageID)` 순서를 유지한다. abnormal flag만으로 현재 양성 사실을 만들지 않는다. 시간 변화와 현재 소견을 분리하고, generic 정상·미표기·메타 문구를 질환별 음성으로 확장하지 않는다. 영어·스페인어 불일치와 모호한 사실은 표시한다.

남은 D8 206회를 완료해 총 288개의 기본 요청을 확보한다. greedy·seed17·cap1024를 유지하고 비EOS cap 도달만 2048→4096으로 재생성한다. 모든 시도와 비용을 남기며 최종 비EOS도 평가에 포함한다.

공식 고정 source에서 hybrid 결합 방식을 확인하고 29개 영역과 GRG의 출처를 보존한다. 사후 유리한 문장 제거·LLM 재요약을 하지 않는다. 중복 사실은 평가에서 한 번 세고 반대 극성은 유지한다.

CURE의 고정 D8 요청 일부로 통제된 중단·재개와 uninterrupted suffix token을 비교한다. 기존 M15 16/16 재개·복수 worker 일치 증거는 불변 조건에서 재사용한다. 수동 원본 token 회귀도 원 입력·설정과 연결해 완료한다. 차이가 있으면 경로 변경 원인을 확인하며 유리한 출력을 선택하지 않는다.

## 3. 의미 평가 잠금과 E96

D8에서 definite/possible/negated/unmentioned, supported/contradicted/unverifiable, 위치·속성·내부 모순의 규약과 fixture를 확정한다. 모델명을 숨긴 출력 ID, reference 사실 ID, 생성·정답 근거 span, 모호성 사유를 보존한다. assistant 판정은 전문의 판독이 아니다.

E 생성 전에 표본·reference 사실·prompt·모델 설정·평가기·규약을 hash로 잠근다. E96은 평가 가능한 현재 비정상 소견 포함 48명과 비정상 표기 없는 48명을 목표로 하며 다음 48+48명도 사전 잠근다. 한 층이 부족하면 원 규칙대로 적격 인원을 사용하고 생성 전에 범위·분모를 기록한다. 새 표본원을 임의로 섞지 않는다.

E96 전체 8조건·3,456회를 실행한다. 평가자는 모든 출력에 같은 규약을 적용한다. 새 유료 API나 별도 judge 호출을 추가하지 않는다. 정확히 동일한 반복 문장만 묶을 수 있으며 문장별 출처를 잃지 않는다. 고정 hash 24명의 모든 조건, 모호한 사례, 투자 판단을 좌우하는 회복·모순을 재점검한다.

## 4. 조건부 확대·독립 확인

기술·평가가 유효하고 불리한 모호성 처리에도 차이 방향이 유지되며 환자 변동만 결정을 막으면 E192로 확대한다. 추가 3,456회 전에 현재 CI·예상 정밀도·실측 비용과 바뀔 판단을 기록한다. 한 환자 의존이나 정답 의미·학습 노출이 지배하면 확대하지 않고 관련 근거만 한정 검토한다.

이번에는 신규 학습·추가 seed·보호 test 개방을 하지 않는다. E192도 개발 탐색이다. 독립 확인과 method pilot은 실제 결과의 full review 이후 별도 계획으로 판단한다.

## 자원·시간·재개

각 실행 직전 nvidia-smi로 허용 GPU 0,1의 실제 여유와 다른 프로세스를 확인한다. 여유가 큰 장치부터 독립 모델·shard를 배정한다. 물리/논리 index 대응을 기록하고 상속된 허용 집합 밖으로 나가지 않는다.

D8에서 GPU당 1 worker와 유망한 batch 확대 또는 GPU당 2 worker를 비교한다. 기존 M15 출력 일치 증거를 활용하되 전체 처리량·긴 출력 p95·peak VRAM·OOM·CPU/RAM/I/O 경합을 함께 측정한다. 동시 worker peak 합계와 worker당 최소 2 GiB 여유 및 다른 점유량이 실제 용량 이내인 구성을 선택한다. iter_085의 M15 8.27/B0 8.35/CURE 9.43 GiB는 부분 관측값이며 장시간 상한이 아니다. 일률적인 12 GiB free 검사만으로 동시 실행을 승인하지 않는다.

원 E96 산술 참고는 7.1–10.1 worker-hours, 두 worker의 이상적 wall 3.5–5.0시간이다. CURE 실측·로딩·평가를 포함하지 않으므로 D8 후 과제별 요청 수/전체 처리량으로 갱신한다. 임의 시간 상한은 두지 않는다. 의미 평가 시간과 기술 검사·중단·재시도 비용을 별도로 기록하고 미측정 중단 비용을 0으로 처리하지 않는다.

worker 수와 GPU 수를 분리한다. 요청 고유 ID·원자적 claim·worker별 파일·중복/누락 검사로 재개한다. 이전 큐나 원본 partial 파일을 정리 명목으로 변경하지 않는다. 이번 실행의 부분 행 복구도 원본 bytes를 보존한다. 학습 checkpoint는 없고 추론 완료 목록·protocol·코드 checkpoint를 보존한다.

# Implementation Tasks for Claude

1. 기준 문서 SHA와 현재 source·기존 출력 계승 manifest를 기록한다. iter_084/085와 수동 원본은 읽기 전용으로 유지한다.
2. report85_d8.py/report85_launch.py의 D8·iter_085 고정 경로를 필요한 manifest/stage/output 인자로 연결한다. 기존 모델·prompt·변환은 유지한다. 무관한 범용 리팩터링은 하지 않는다.
3. 구버전 40건의 파일 봉인 검증, 신버전 행 digest 검증, 부분 CURE 계승, source/GPU 변경 연결을 구현한다. 변조·누락·중복·다른 protocol의 잘못된 재사용을 거부하는 회귀 검사를 수행한다.
4. 실제 사용할 Python별 캐시 격리와 환경 상태를 확인한다. 검증 완료 CURE strict 로딩 근거는 불변이면 재사용하고 변경된 경로만 확인한다.
5. 남은 D8·hybrid·CURE 재개·수동 token 회귀·처리량 선택을 완료한다. 자료 사실과 평가 fixture를 잠그고 E96을 실행한다.
6. 원 조건을 만족하는 E192만 추가한다. 원시 판정표에서 주수치·분모·환자 bootstrap을 별도 계산 경로로 재계산한다.
7. 완료 검사는 모든 예상 요청 ID와 8조건 판독 산출물, C-H의 30개 원출력 연결, 평가 coverage, metric·비용·실행 종료를 확인한다. 구현 미완료 자체를 이유로 정상 진행 중인 작업을 임의 종료하지 않는다. 실제 장애 시 소유 작업만 안전하게 처리하고 재개 위치를 남긴다.
8. `SELF_CHECK: PASS/FAIL`, `SUMMARY:`와 full review용 보고서를 작성한다. 모델 로딩·생성 완료·의미 평가 완료·가설 판정을 별개로 기록한다. branch·commit은 orchestrator가 관리한다.

# Evaluation (성공/실패 기준 포함)

원 주평가를 유지한다. 확정 reference 사실이 있는 환자별 확정 소견 recall을 평균하고 위치·명시 속성까지 맞는 엄격 recall도 보고한다. 명시적 모순 환자 비율/건수, definite/possible/negated/unmentioned, 미판정 추가 주장, 내부 모순, 형식 실패·비EOS와 비용을 분리한다. 미표기를 FP로 세지 않는다.

supported/contradicted/unverifiable 비율과 unverifiable을 모두 맞음/틀림으로 둔 precision 범위를 제시한다. 이는 임상 precision이 아니다. 명시적 양성·음성이 정의되는 부분집합에서 가능한 운영점만 비교하고 같은 FP 수준을 구성할 수 없으면 matched-FP 결론을 보류한다.

주 paired 비교는 B0-R−M15-R, M15-S−M15-R, B0-S−M15-S, C-G−M1-G, C-H−C-G다. 환자 bootstrap 10,000회·seed84017의 95% CI, 두 층별 결과·원시 분모·coverage를 보고한다. 29개 영역을 독립 환자로 세지 않는다. 순차 확대 CI는 탐색적이다. bbox는 의미 대응·공식 box가 있는 사실의 보조 평가이며 판독 통과 조건이 아니다.

원 투자 기준은 확정 소견 recall 10 pp 증가와 모순 환자 비율 증가 5 pp 이내다. CI·평가 민감도·여러 환자에 걸친 효과를 함께 검토한다. 새로운 유의성 문턱이나 사후 성공 규칙을 추가하지 않는다.

- **양성:** 회복을 보인 baseline을 보존한다. 단순 prompt나 CURE로 충분하면 해당 신규 방법 투자를 보류한다. 단순 대안 이후 여러 환자·소견군의 구체적 충돌이 남으면 full review에서 최소 method pilot을 검토한다. 알려진 trade-off 재현만으로는 방법 개발을 승인하지 않는다.
- **음성:** 확정 회복 없이 possible·모순·미판정만 늘면 현재 adapter 판독 개선 경로를 보류한다. grounding 성과나 의료 VLM 전체를 기각하지 않는다.
- **불확정:** 사전 E192 조건 또는 관련 원문 의미 재검토만 수행한다. 이후에도 판단이 남으면 현재 방법 투자를 보류하고 재개에 필요한 증거를 특정한다.
- **실행 실패:** 오류와 영향 범위를 남기고 모델 가설은 미판정으로 유지한다. 준비 성공을 유효 실험으로 바꾸지 않는다.

# Risks / Checks

가장 큰 위험은 구버전 출력의 무검증 수용, protocol 비교의 무력화, 후보 flag를 정답으로 사용하는 것, 불완전한 reference로 FP를 과대 계산하는 것이다. 필수 회귀 검사는 이 경로와 실제 재개·hybrid·평가 분모에 집중한다.

PadChest 학습·선택 노출, 불완전한 reference, 단일 seed·prompt, assistant 의미 평가의 한계를 유지한다. 이번 결과는 임상 검증·독립 일반화·위치 학습의 인과 효과·신규 contribution을 확정하지 않는다. 기본 환경·기존 hf_cache·다른 사용자 프로세스는 변경하지 않는다.

## 대규모 GPU 필요 후보

동일 영상·문장 노출량의 report-only/box-only/joint/curriculum을 여러 모델·기관에서 비교하는 factorial 학습은 장기 후보로 보존한다. 현재는 기존 checkpoint의 실제 비교를 완료해 필요한 경량 개입을 좁힌다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 사실

- `agent/GOAL.md`, iter_084/085 plan.md, iter_085 review.json·claude_report.md, 관련 LIMITATIONS/CODE_ASSETS 항목과 iter_012/016/017 review.json의 원 근거를 읽었다.
- 기준 SHA256을 직접 확인했다: iter_084 `42334bc910f7abbb26e27f60696b59b5d2a974d6143fbe2aed153e08c315fefd`, iter_085 `5663189557a03e3e30b620dbb2202fd86b754ca9b2eebbe6eeb6fadffc962f2f`.
- 현재 research HEAD는 `1fad82e7d39c3468ffbbe27a5f94eaf6d32e0415`다. `git status --short`와 `git diff --stat` 출력은 비어 있었다. 필요한 report 실행 파일은 현재 브랜치에 있어 재반입이 필요 없다.
- iter_085 review와 handoff_final.json은 D8 82/288건, E 0건을 기록한다. M15 16·B0 16·M1 8의 초기 40건에는 record_digest가 없고 파일 봉인이 있다. M1G 8·CURE 34건에는 record_digest가 있다. CURE 34/240건에는 완료 봉인이 없다. 이는 이번 계획에서 새로 독립 재집계한 수치가 아니라 원 리뷰와 인계 파일에서 확인한 수치다.
- `report85_d8.py`를 직접 읽었다. 결과·입력 경로가 iter_085/D8에 고정돼 있고, protocol에 GPU·Python·source hash가 포함된다. 최신 read 경로는 모든 행에 record_digest를 요구한다. 따라서 원본 수정이나 protocol 비교 제거 대신 버전별 검증과 명시적 계승 연결이 필요하다.
- `report85_launch.py`는 보조 캐시 격리를 제공하지만 iter_085에 고정돼 있다. GPU 메모리 검사도 일률적 12,288 MiB 기준이므로 이번 장시간·동시 실행의 실측 peak 합산으로 연결해야 한다.
- `reference_review_notes.json`은 abnormal 표기와 평가 가능한 현재 양성 사실이 일치하지 않는 사례, 시간 변화의 분리, 임상 부재로 사용할 수 없는 문장을 기록한다. E 표본·정답은 아직 잠기지 않았다.
- `environment_final.json`에는 과거 torch 2.5.1 상태가 남아 있으나 최종 보고서는 2.7.1 복구를 기록한다. 파일명만으로 최종 환경을 판단하지 말고 recovery/validation·실제 실행 protocol과 연결해야 한다. 이는 새 환경 재설치 사유가 아니라 실제 사용할 Python의 버전 확인 사항이다.

## 의미와 선택

직전 리뷰의 한정 실행 복구 권고를 유지한다. 현재 설명을 줄이지 못한 이유는 표본 불확실성이 아니라 실행·평가 미완료다. 기존 로딩을 전부 반복하거나 새 모델·modality로 옮기는 것보다 남은 비교를 완료하는 정보 가치가 높다. 새 문헌 주장·방법 설계는 추가하지 않았고 iter_084의 문헌 원문 및 한계를 계승한다.

파일 수정·환경 구성·모델 실행은 수행하지 않았다.
