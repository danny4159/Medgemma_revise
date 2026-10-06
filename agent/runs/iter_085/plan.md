# 요약

- **이번에 할 일:** 인증이 연결된 CURE의 공식 로딩과 D8 검사를 마치고 PadChest-GR의 원 8조건 비교를 실행한다.
- **필요한 이유:** iter_084는 신규 출력 0건으로, 누락 회복과 언급 성향을 아직 구분하지 못했다.
- **확인할 기준:** 원 계획의 표본·비교군·metric·확대·종료 조건을 유지한다.
- **주의·다음:** 인증 성공은 실험 성공이 아니다. 새 결과는 iter_085에 보존하고 full review로 후속 투자를 판단한다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray PadChest-GR
- 모델: MedGemma 1.5와 기존 RSNA adapter, MedGemma 1과 공개 CURE adapter; 신규 학습 없음
- 과제: 흉부 X-ray에서 판독문과 영역별 설명을 생성한다
- 가설: 증가한 언급은 정답 회복 또는 불확실·잘못된 언급 증가일 수 있다
- 질문: 더 많이 말하는 것이 더 정확히 읽는 것인가?
- 변경: 실행 복구
- 연결: iter_084의 인증 차단이 사용자 제공 인증으로 해소됐으며 과학적 질문은 그대로다
- 작업: 공식 로딩·D8 검사를 마친 뒤 실제 비교로 기존 방식의 충분성과 잔여 문제를 판단한다

# Current Understanding

이 계획은 `agent/runs/iter_084/plan.md`의 실행 보완이다. 직접 확인한 SHA256은 `42334bc910f7abbb26e27f60696b59b5d2a974d6143fbe2aed153e08c315fefd`다. 구현 담당은 이 원문과 iter_084 review.json·reuse_manifest.json을 함께 읽는다. 아래에서 명시한 인증·결과 경로·상태 기록 변경 외 과학적 조건은 원문을 따른다.

**유지:** 가설, 8조건, prompt, 모델·정밀도, 표본 규칙, metric, 평가 규약 잠금, E192 확대 조건, 종료 및 보존 기준.

**이번 변경:** HF_TOKEN_PATH의 표준 인증 사용, 새 모델 저장 위치와 결과를 `research/results/iter_085/`로 지정, preflight의 고정 경로·상태 문구 수정.

**미완료:** 모델 다운로드·공식 로딩, 실제 frontal 영상 연결과 정답 적합성, D8 입력·adapter·재개·처리량 검사, 의미 평가 규약 고정, E96 및 조건부 E192.

사용자는 정확한 base revision의 config와 두 safetensors 파일 접근 성공을 확인했다. 이는 다운로드와 로딩 성공의 증거는 아니다. iter_084의 execution_failed 판정과 모든 원본은 보존한다.

# Strategy Check / 연구 방향 판단

iter_084의 전략 판단을 유지한다. 위치 출력의 SFT 개선과 자유 판독의 불확정 언급 변화 → 확정 회복·불확실 표현·언급 성향이라는 경쟁 설명 → 동일 base–adapter 및 단순 prompt·CURE 영역 결합 비교 → 기존 방식 채택 또는 구체적인 잔여 문제의 최소 개입 검토로 연결한다.

직전 반복은 과학적 설명을 줄이지 못했지만 현재는 인증 조건이 달라졌다. 따라서 같은 현상의 탐구를 이어가며 새 후보 탐색으로 전환하지 않는다. 직전 리뷰의 실행 복구 권고를 그대로 따른다. 새 학습은 근거가 없고, CURE 제외는 필요한 비교를 약화하므로 선택하지 않는다. MRI 복구·TOF·문헌 discovery는 재개하지 않는다.

준비 검증은 불변 근거를 재사용한다. 앞으로의 지배 비용은 영역별 생성과 의미 평가로 예상되지만 실측 전 비용 절감률을 주장하지 않는다.

# Hypothesis

원 H_recovery/H_propensity/H_prompt/H_existing/H_residual을 유지한다. 확정 소견 회복, 불확실·모순 언급, 간단한 체계적 prompt 효과, CURE의 충분성, 영역 출력과 결합 결과의 잔여 충돌을 구분한다. 내부 시각 인식 개선이나 위치 supervision만의 인과 효과는 이번 checkpoint 비교로 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

기존 세 limitation ID는 자산의 성과와 해석 경계를 연결하며 새 판독 한계의 검증을 대신하지 않는다. diagnostic, method_stage=none을 유지한다. iter_084의 사용법 검사 미완료 항목을 통과하기 전 method pilot 근거로 승격하지 않는다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`와 `results/iter_012/train/lr2e-4_s17/epoch_05`를 유지한다. adapter state digest는 `e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11`다.

CURE 공식 source `9365333856c0534af0cb05cb4291ce48dd95bb1d`, base `290cda5eeccbee130f987c4ad74a59ae6f196408`, adapter `4bb5dc5a5025a854d1f25e475769949915b08b44`를 기존 확보 자료와 연결한다. 정확한 base는 google/medgemma-4b-it이며 1.5로 대체하지 않는다. processor·라이선스·config 및 modules_to_save 연결을 확인한다.

상속된 HF_TOKEN_PATH를 huggingface_hub 표준 인증으로 사용한다. 토큰 파일을 직접 읽어 출력하거나 값·인증 헤더를 로그·명령 인자·프롬프트·프로젝트에 복사하지 않는다. 새 캐시 위치를 지정해도 인증 경로 상속이 유지되도록 한다. 접근·다운로드·로딩·D8·전체 비교의 상태를 각각 기록한다.

# Contribution Path / Baselines / Reuse

가까운 CURE·MAIRA-2와의 관계 및 신규성 미확인은 원 계획을 계승한다. CURE의 알려진 recall–precision trade-off만 재현되면 새 기여로 삼지 않는다. PadChest의 CURE hybrid는 확장 검증이며 원 benchmark 재현 실패로 해석하지 않는다.

원 8조건은 M15-R, M15-S, B0-R, B0-S, M1-R, M1-G, C-G, C-H다. 앞 네 조건은 base/RSNA adapter × 중립/체계적 prompt, M1-R은 bf16 일반 판독, M1-G/C-G는 동일 NF4 GRG, C-H는 공식 AGRG-29와 C-G의 결합이다. 환자당 36회 생성이며 C-G를 다시 생성하지 않는다. pristine base를 사용하고 adapter disable로 대체하지 않는다. 공식 위치 29개는 GT와 무관하게 전부 사용한다.

현재 `approach/grounding-report-transfer`와 HEAD `7748fdcffdc0e5f44bf090a6563f6e6dd3490274`를 이어간다. 새 브랜치 기반이나 재반입은 필요 없어 reuse_iteration=0, reuse_assets=[]다. 이는 전체 snapshot 승인이라는 뜻이 아니다.

현재 파일 중 report84_preflight.py는 제한된 준비 기록, pg39_data.py는 metadata reader 범위만 승인됐다. pg43_run.py, pg39_spec.py와 rsna_diag의 __init__.py/generate.py/geometry.py/metrics.py/parse.py/prompts.py/lora.py/queue_lock.py는 원 manifest의 출처를 유지하면서 실제 새 연결 검사를 마친다. 기존 grounding 표본 선택·평가 CLI를 판독 평가에 그대로 쓰지 않는다. 수동 실험 파일은 읽기 전용 참고다.

# Proposed Experiment

## 1. 실행 복구와 자료 적합성

설치가 필요하면 먼저 알리고 승인된 격리 환경을 구성한다. 기본 환경과 hf_cache는 변경하지 않는다. 환경 Python 절대경로, package/version, CUDA 호환성, 설치·오류 기록을 보존한다. 추가 모델은 `results/iter_085/` 아래 별도 경로에 받는다.

기존 metadata·출처 검증은 연결된 hash가 불변이면 재사용한다. 327영상·323환자는 후보 수이지 적격 표본이 아니다. 보고서 의미 검토 전에 H192/F120/test와 보호 환자·study·영상 ID를 제외한다. frontal 연결, pixel 중복, 현재 상태의 문장 의미, CURE train 노출을 확인한다. 확인된 train 노출 환자는 원 계획대로 주분석에서 제외한다.

환자당 대표 영상은 `sha256(84017|PatientID|ImageID)` 순으로 선택한다. 현재 상태를 평가할 수 없는 시간 비교 문장은 제외하고 분리 가능한 현재 사실은 남긴다. generic 정상 문구나 미표기를 질환별 음성으로 만들지 않는다.

## 2. 동작 확인 D8

기존 D24의 고정 hash 순 D8에서 8조건·288회 생성한다. 공식 입력과 wrapper의 tensor·token, ID–영상 연결, strict adapter key/shape 및 eval 상태, CURE PEFT와 저장 모듈, EOS·cap, 중단 재개를 확인한다. 모델 정답률 100%를 gate로 요구하지 않는다.

greedy·seed17, 최초 cap1024를 유지한다. EOS 없이 cap 도달 시에만 동일 입력을 2048→4096으로 재생성하고 모든 시도·비용을 보존한다. 최종 비EOS도 평가에 남긴다.

모델명을 숨긴 출력 ID, 원문 근거 span·reference ID, definite/possible/negated/unmentioned 및 supported/contradicted/unverifiable 규약과 fixture를 D8에서 확정한다. E 출력 전에 prompt·GT·평가기·규약·모델 설정을 hash로 잠근다.

## 3. 가능성 탐색 E96

평가 가능한 비정상 소견 포함 48명과 비정상 표기 없는 48명을 목표로 사전 고정한다. 한 층이 부족하면 원 계획대로 적격 인원을 사용하고 생성 전에 범위와 한계를 기록한다. 비정상 표기 부재를 정상 gold로 해석하지 않는다. 조건부 다음 48+48명도 미리 잠근다.

E96에 8조건·3,456회 생성을 수행한다. 원문의 중립·체계적 prompt, CURE 448×448·deterministic CLAHE 및 공식 결합 규칙을 유지한다. 중복 사실은 평가에서 한 번만 세고 반대 극성은 삭제하지 않는다. 전체 출력에 동일 의미 판정을 적용하며 신규 유료 API·별도 judge 모델 호출은 추가하지 않는다. 고정 hash 표본 24명의 모든 조건과 모호하거나 결정을 좌우하는 사례를 재점검한다.

## 4. 조건부 확대와 독립 확인

기술·평가 경로가 유효하고 불리한 모호성 처리에도 차이 방향이 유지되며 환자 변동만 결정을 막을 때 E192로 확대한다. 추가 3,456회 생성 전에 현재 CI·예상 정밀도·실측 비용과 판단 변화를 기록한다. 한 환자 의존, 정답 의미 또는 학습 노출이 지배하면 확대하지 않는다.

이번에는 신규 학습·다중 seed·독립 test를 실행하지 않는다. 이후 방법 개발과 독립 확인은 실제 결과의 full review를 거쳐 별도로 판단한다.

## 자원·시간·재개

시작 직전 nvidia-smi로 허용 GPU 0,1의 여유를 확인하고 여유가 큰 장치부터 배정한다. 독립 모델·shard를 두 GPU에 배치한다. D8에서 GPU당 1 worker와 유망한 batch 확대 또는 GPU당 2 worker 구성을 비교한다. 처리량·peak VRAM·긴 출력 p95·오류·CPU/RAM/I/O 경합·출력 정합성으로 선택한다. 동시 worker peak와 worker당 2 GiB 여유, 다른 점유량을 합산한다. 논리/물리 장치 대응과 device_map 범위를 확인한다.

MedGemma bf16 8–10 GiB는 참고값이며 NF4·긴 출력 메모리는 실측한다. E96 원 산술 참고는 7.1–10.1 worker-hours, 두 worker 이상적 wall 3.5–5.0시간이다. 실제 CURE 처리량·로딩·평가는 포함하지 않은 추정이므로 D8 후 과제별 요청 수/실측 처리량으로 갱신한다. 임의 시간 상한은 두지 않는다.

요청별 고유 ID·원자적 claim·worker별 출력·protocol digest로 재개한다. 부분 행 원본, 모든 재시도와 비용을 보존하며 중복·누락을 검사한다. 학습 checkpoint는 없고 코드 checkpoint는 orchestrator가 관리한다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex이며 섹션명만 호환 형식이다.

1. 기준 plan SHA와 현재 source provenance를 기록하고 이번 amendment를 results/iter_085에 남긴다. 기존 iter_084·수동 결과를 덮어쓰지 않는다.
2. report84_preflight.py의 iter_084 전용 출력 제한·plan 연결·고정 설치 보류/후속 문구를 이번 실행에 맞게 한정 수정한다. 출력 경로 보호는 유지하며 asset_access_ready와 experiment_complete를 분리한다.
3. 기존 공식 source/config 산출물을 재사용하고 표준 인증으로 정확한 가중치를 새 경로에 확보한다. 공식 로딩·import·GPU·작은 실제 입력을 확인한다.
4. 승인 reader와 runner helper를 연결해 표본·요청·평가 잠금을 구현한다. 원 reuse_manifest의 미완료 required_checks를 실제 경로에서 수행한다.
5. D8 이후 E96과 원 조건에 맞는 E192만 진행한다. 새 출력·판정표·비용·completion을 이번 경로에 저장한다.
6. 원시 판정표에서 주요 수치와 bootstrap을 별도로 재계산하고 full review용 근거를 남긴다. 프로세스 종료·완료 검증 전에 완료 보고서를 작성하지 않는다.

필수 회귀 검사는 기존 결과 덮어쓰기 거부, 현재 plan/source hash 연결, 성공·실패에 따른 실제 상태 기록, tensor/token 대응, strict adapter 연결, GT 비노출, GPU 매핑, claim·중단 재개·중복/누락 거부다. 불변 출처 검증은 재사용하고 무관한 범용 정비는 하지 않는다.

# Evaluation (성공/실패 기준 포함)

원 주지표를 유지한다. 확정 reference 사실이 있는 환자의 평균 확정 소견 recall과 위치·속성까지 맞는 엄격 recall, 명시적 모순 환자 비율/건수, 불확실·미판정 추가 주장, 내부 모순 및 비용을 각각 보고한다. 미표기를 FP로 세지 않는다. unverifiable을 모두 맞음/틀림으로 둔 precision 범위를 제시하되 임상 precision이라 부르지 않는다. 같은 FP 운영점을 구성할 수 없으면 matched-FP 결론을 보류한다.

주 paired 비교는 B0-R−M15-R, M15-S−M15-R, B0-S−M15-S, C-G−M1-G, C-H−C-G다. 환자 bootstrap 10,000회·seed84017의 95% CI와 두 층별 결과를 보고한다. 29개 영역을 독립 환자로 세지 않는다. 순차 확대 CI는 탐색적이다. bbox는 의미 대응·공식 box가 있는 사실의 보조 평가이며 판독 통과 조건이 아니다.

원 투자 기준은 확정 소견 recall 10 pp 증가와 모순 환자 비율 증가 5 pp 이내다. CI·원시 수·coverage·민감도를 함께 판단하고 점추정치만으로 승인하지 않는다.

- **양성:** 유효한 회복을 보이는 baseline을 보존한다. 체계적 prompt 또는 CURE로 충분하면 해당 신규 방법 투자를 보류한다. 여러 환자·소견군의 구체적 잔여 충돌이 단순 대안 이후에도 남으면 full review에서 최소 method pilot의 가치를 검토한다.
- **음성:** 확정 회복 없이 possible·모순·미판정만 증가하면 현재 adapter 판독 개선 경로를 보류한다. 기존 grounding 성과는 유지한다.
- **불확정:** 원 E192 조건 또는 한정 의미 재검토만 허용한다. 이후에도 남으면 방법 투자를 보류하고 필요한 독립 정답·노출 근거·강한 대조를 명시한다.
- **실행 실패:** 자료·입력·로딩·평가 결함의 범위를 기록한다. 인증이나 구현 실패를 모델 가설의 음성 결과로 바꾸지 않는다.

완료 조건은 기술적으로 유효한 전체 대조와 근거 있는 투자 판단이다. SELF_CHECK: PASS/FAIL 및 SUMMARY: 형식을 유지한다.

# Risks / Checks

PadChest reference의 불완전성, 단일 seed/prompt, assistant 의미 판정, 모델 학습·validation 노출을 원 계획대로 명시한다. 임상 검증·독립 test·위치 학습의 인과 효과를 주장하지 않는다. 새 인증이 실패하면 실제 오류와 인증 상속 여부를 특정하고 동일 무인증 요청을 반복하지 않는다. 새로운 사용자 권한이 실제로 필요할 때만 질문한다.

## 대규모 GPU 필요 후보

동일 영상·문장 노출량의 report-only/box-only/joint/curriculum을 여러 모델·기관에서 비교하는 factorial 학습은 장기 후보로 유지한다. 이번에는 기존 checkpoint 비교로 필요한 경량 개입의 근거부터 확보한다.

# 계획의 근거 (GPT 조사 노트)

이번은 전략 재선정이 아니라 인증 복구 후 동일 실험의 실행 보완이다.

- `agent/GOAL.md`, iter_084의 plan.md·review.json·claude_report.md, 관련 LIMITATIONS/CODE_ASSETS 항목 및 reuse_manifest를 확인했다.
- 기준 plan SHA256은 `42334bc910f7abbb26e27f60696b59b5d2a974d6143fbe2aed153e08c315fefd`로 직접 확인했다. 현재 research HEAD는 `7748fdcffdc0e5f44bf090a6563f6e6dd3490274`이며 작업 트리는 깨끗하다.
- 직전 리뷰는 metadata 후보 327영상·323환자, 반입 파일 출처, adapter digest 등 준비 범위만 확인했다. 신규 생성은 0건이며 tensor·strict adapter·재개·평가 규약 검사는 미완료다.
- `report84_preflight.py`는 결과 경로를 iter_084로 제한하고 plan.json 경로·설치 보류 이유·다음 안내를 고정한다. 이번 경로와 실제 상태를 반영하도록 한정 수정해야 한다. 접근 성공을 실험 완료로 연결하면 안 된다.
- CURE source revision `9365333856c0534af0cb05cb4291ce48dd95bb1d`, base revision `290cda5eeccbee130f987c4ad74a59ae6f196408`, adapter revision `4bb5dc5a5025a854d1f25e475769949915b08b44`가 기존 preflight에 고정돼 있다. 원 source·config 산출물을 재사용하고 실제 로딩으로 확인한다.
- 사용자 지시가 인증 연결 및 세 파일의 접근 성공 근거다. 이번 계획 호출에서는 인증 저장소를 읽거나 접근 요청을 반복하지 않았다. 다운로드·공식 로딩 완료는 아직 확인되지 않았다.
- pg43_run.py의 claim·재개·완료 helper, pg39_data.py의 reader, rsna_diag/lora.py의 실제 경로를 확인했다. 기존 LoRA 파일의 오래된 설치 금지 주석은 현재 사용자 정책을 대체하지 않는다. CURE에는 공식 PEFT를 사용한다.
- 문헌·전략 판단은 iter_084의 고정 계획과 조사 노트를 계승한다. 새로운 문헌 주장이나 모델 성능 근거는 추가하지 않았다. 파일 수정·설치·실험은 수행하지 않았다.
