# 요약

- **이번에 할 일:** iter_050을 Codex로 인계해 무효·미확인 영상 감사를 보완하고 남은 진단을 수행한다.
- **필요한 이유:** 이전 감사 일부는 이미지가 보이지 않은 상태에서 작성됐다. 모델 비교 완료 근거는 없다.
- **확인할 기준:** 실제 이미지 확인 근거와 원래 자료·입력·정밀도 gate, 동일 정확도·비용 기준을 적용한다.
- **주의·다음:** 유효 중간물은 재사용한다. gate 실패 시 현재 자료 범위를 보류하며 새 방법의 효과를 미리 주장하지 않는다.

# Current Understanding

이번은 사용자 보완 `20261003_025112_c5bc1c2e`에 따른 인계다. iter_050의 실패 판정이나 새로운 과학적 설계가 아니다.

기준 문서는 `agent/runs/iter_050/plan.md`이며 SHA256은 `6e9a5010785840182c20e13456bc0051d73b1a827ee4e19eebba229bc7ffc041`이다. 함께 읽을 plan.json의 SHA256은 `32e82ceac78888799067eae50d6e36a87e0286dcb33a20c58f658e7afd478813`이다. 구현 시작 시 일치를 확인한다. 본 amendment는 담당·감사 근거 승계·새 결과 경로만 보완하며 나머지는 기준 계획 전체를 따른다.

- **유지:** 연구 질문, 전체 X-ray·비longitudinal·고유 영상 둘 이상 조건, 모든 원본 영상, 이력·A–E options, T/D/C/R/X, split seed, metric, 문턱과 종료 조건.
- **변경:** 구현 담당은 Codex, 새 산출물은 `research/results/iter_051/`. iter_049/050은 읽기용 출처로 보존한다. 무효 감사의 자동 승계를 차단한다.
- **미완료:** 시각적 감사의 유효 근거 연결, 의미상 이력 감사 정합성, 중복 cluster와 split, processor 검증, 생성 실행기·평가 및 실제 비교.
- **회귀 검증:** 원본·코드·규칙·산출물 digest, 정정문 적용, 입력 allowlist, 정상 입력, 재개와 최종 완료 판정.

현재 브랜치와 HEAD `fbaea4c557e151fa39d5cdf0e9da1c4f8de7c106`을 이어간다. checkpoint는 interrupted/unreviewed이며 승인본이 아니다. 04:30 KST 복귀 예약은 orchestrator가 관리한다. 이미 시작한 iter_051 담당을 시각 때문에 바꾸거나 종료하지 않는다.

# Strategy Check / 연구 방향 판단

iter_050의 Strategy Check를 유지한다. 새로운 모델 결과나 방향 전환 요청이 없어 전략·문헌조사를 다시 시작하지 않는다. 현재 방법 개선보다 원래 한정 진단을 마치는 것이 우선이며 자료 gate 실패 때는 이 후보를 보류한다.

기존 공동 grounding 투자의 보류와 관찰은 유지한다. 이번 감사 문제는 모델 가설을 설명하거나 반박하지 않는다. 같은 research_track에 iter_050을 연결하며 진단 체류를 초기화하지 않는다. 해결된 것은 자료 확보와 코드 보존이고, 남은 것은 유효 감사 및 실제 출력 비교다.

# Hypothesis

기준 계획의 H1/H2를 그대로 유지한다. D−C는 생성 소견 대체 경로의 손실, R−C는 동일 요약에 원본을 추가한 효과를 평가한다. D−R 및 D−X는 원본이 있어도 남는 중간 생성물 경로의 문제를 비교한다. T는 영상 관련 해석의 대조군이다. 순수 내부 원인이나 모든 영상의 필요성을 확정하지 않는다.

# Limitation Evidence / Correct Usage Checks

새 모집단의 실제 출력 한계는 아직 없으므로 `limitation_ids=[]`, diagnostic/none을 유지한다. iter_049의 누출 감사 blocker는 해소 증거가 검증되기 전까지 유지한다.

먼저 `research/results/iter_050/audit/decisions/RETRACTION_image_part1_to_14.md`와 `RETRACTION_image_redo_01_to_25.md`를 읽는다. 후자가 이전의 redo 유효 주장을 정정한다.

- `image_part*.json` 전체, `image_redo_01.json`부터 `image_redo_25.json` 전체, redo26의 c620/c621은 제외·유지 판정 모두 무효다. 암묵적 기본 keep에도 사용하지 않는다.
- redo26의 c623/c625/c627/c6369/c6378/c6456, redo27–30과 valid31은 유효 후보다. 원 세션의 해당 이미지 도구 응답과 실제 렌더링, sheet와 원본 영상의 연결을 확인한 항목만 승계한다. 확인 불가 항목은 미확인으로 두고 실제 이미지를 본다.
- 파일 glob이나 viewed_from/through 범위만으로 case 전체를 승인하지 않는다. case별 ordered image 목록과 각 영상의 확인 근거를 명시한다. 최신 정정문이 앞선 판정보다 우선한다.
- 무효·미확인 사례는 실제 렌더링된 contact sheet를 확인한다. 흐리거나 주석 여부가 모호하면 원본 크기로 확인한다. 도구가 이미지를 반환하지 않으면 pending으로 기록하며 소견을 만들지 않는다. 정상 렌더링 경로를 확보하지 못하면 gate 실패로 종료한다.
- 기존 sheet의 생성 index 표시는 원본 annotation과 구분한다. sheet hash·원본 hash·순서·생성 코드의 연결을 검사한다. 검증된 sheet를 일괄 재생성하지 않는다.

254개 이력·선택지와 896장 전체에 원 계획의 감사 범위를 유지한다. history_part1–4의 출처와 case coverage를 연결하고 원 규칙과 충돌하거나 누락된 항목만 재검토한다. 강한 검사 결과·증상만으로 정답 직접 공개와 동일시하지 않는다. 실제 정답 진단의 명시·동의어, 모호한 공개, 교육용 화살표·outline·진단 설명 및 원 계획의 중복·불일치 제외 조건을 적용한다. 무효 영상 판정을 참조한 파생 집계·split·완료 표시는 모두 재사용하지 않는다.

# Contribution Path / Baselines / Reuse

새 기여는 미확정이다. 가장 가까운 선행과 직접·단계별 대안에 대한 판단은 기준 계획을 계승한다. 이번 수정은 평가의 타당성을 복구하는 작업이다.

현재 기반에 `mt50_common.py`, `mt50_prep.py`와 `rsna_diag/__init__.py`, `generate.py`, `geometry.py`, `prompts.py`, `queue_lock.py`가 있다. helper 다섯 파일은 iter_043 SHA `b50aa230a86c6d5b6c6b280fe718170ce4ecf220`의 blob과 일치한다. 추가 반입 없이 기존 파일을 재사용하며 iter_050/reuse_manifest.json의 required_checks를 완료한다. 과거 단일 영상 padding·CLI·cap ladder를 새 과제에 사용하지 않는다.

필수 수정은 다음으로 한정한다.

- OUT을 새 결과 경로로 명시적으로 지정하고 이전 경로 쓰기·덮어쓰기를 거부한다.
- 원본 hash/size/pixel 불일치가 있으면 bad를 기록하는 데 그치지 않고 이후 gate를 차단한다.
- 허용 입력 경로의 모든 관련 symlink·경로 이탈과 기존 sheet의 불일치를 거부한다.
- 재사용 완료 판정에 원본·규칙·코드·출력 digest와 decoder 버전을 연결한다. 기존 v2 검사는 시각적 감사 완료로 취급하지 않는다.
- 현재 입력 검증 경로로 iter_049의 재사용 결함을 해결하되 사용하지 않는 download CLI나 주변 코드를 정비하지 않는다.

원본 파일·검증된 중간물은 재다운로드·중복 생성하지 않는다. `research/results/iter_051/`에 인계 manifest로 출처 SHA, 파일 hash, 승계 여부, 정정 사유와 남은 검사를 연결한다.

# Proposed Experiment

## 자료와 단계

원 계획대로 감사 통과 cluster를 subtype와 영상 수 2–3/4장 이상으로 층화한다. seed5001로 D24를 고정하고 가장 긴 입력 및 연결 cluster를 포함하며 실제 D 증가를 기록한다. 나머지 전체 E의 중복 cluster가 최소156개일 때만 실행한다. q=0.10/0.25/0.40과 unequal cluster size의 예상 정밀도를 보고한다. gate를 맞추기 위해 제외 규칙·모집단을 바꾸지 않는다.

동작 확인은 D 중 최소8 case, 가능성 탐색은 D24 전체의 기술적 검증과 처리량 측정이다. D 정확도로 조건을 고르지 않는다. 자료·정밀도·입력·출력·재개 gate 통과 후 E 전체를 한 번 실행한다. 학습·다중 seed·독립 확인은 이번 범위가 아니다.

## 요청과 입력

T는 이력·선택지, D는 여기에 전체 원본 영상을 제공한다. 영상별 F를 U로 통합한 뒤 C가 답하며, R은 동일 U bytes와 전체 영상을 사용한다. H는 전체 영상 공동 소견, X는 H와 전체 영상으로 답한다. 최종 지시는 동일하며 각 단계는 새 single-turn 요청이다.

F cap512, U 및 최종 T/D/C/R/X cap1024, H cap은 영상 수×512+1024를 유지한다. 개발 집단에서 비EOS·잘림이 있으면 원 계획대로 해당 단계 cap을 한 번 두 배로 조정하고 고정한다. 이후에도 정상 출력이 확보되지 않으면 E를 보류한다. E 결과로 cap을 수정하지 않는다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, eval, adapter 없음, greedy를 유지한다. 공식 processor 경로와 wrapper를 text-only·1장·2장·최대 영상 입력에서 tensor 단위로 비교한다. RGB·alpha·Pillow12.3.0 및 실제 환경, 영상 순서와 options 포함 token 수를 기록한다. 추가 crop·padding·영상 선택을 하지 않는다.

추론 manifest는 이력·A–E options·ordered image path/hash만 허용한다. 추적 ID는 prompt에서 제외한다. 평가 정답·caption·audit·findings·discussion 등은 별도 파일에 두고 worker 입력의 하위 key까지 allowlist를 검사한다.

## 자원·비용·재개

요청 수는 S+7N으로 전체 후보 기준 최대2674건이다. 감사 후 실제 규모를 고정하고 기술 검사·재시도 비용은 별도 집계한다. 시작 직전 nvidia-smi와 논리/물리 GPU 대응을 확인한다.

D에서 두 GPU의 1 worker/GPU와 안전할 때 2 worker/GPU를 비교한다. 복수 worker가 불가능하면 작은 batch 확대를 검토한다. 최대 영상 입력·긴 H 출력을 포함한 peak 합계와 외부 점유에 worker당2GB 여유를 확보한다. 처리량·긴 요청 지연·OOM·정합성·CPU/RAM/I/O 경합으로 배치를 정한다. 1 worker를 유지하면 실측 이유를 남긴다.

wall-clock은 단계별 실측 처리량과 의존 경로로 계산해 E 실행 전에 기록한다. 임의 시간 상한은 두지 않는다. 원자적 claim, worker별 결과, attempt 비용, 원본·config·상위 생성물 digest 및 완료 seal을 적용한다. U/F, C/R/U, X/H 연결을 검증한다. OOM은 동시성·batch를 줄여 동일 요청을 복구하며 영상·표본·출력 기준을 줄이지 않는다.

# Implementation Tasks for Claude

호환용 제목이며 실제 담당은 Codex다.

1. 기준 계획 hash, intervention, checkpoint, 정정문과 원본 helper 승인 범위를 확인한다. 기존 실행·claim의 상태를 확인하고 중복 작업을 시작하지 않는다.
2. 새 결과 경로와 인계 manifest를 만들고 감사 파일을 valid-candidate/invalid/unverified로 명시적으로 구분한다. 유효 출처가 확인된 작업만 승계한다.
3. 무효·미확인 시각적 감사와 필요한 이력 판정 보완을 수행한다. 전체 coverage·중복 cluster·정밀도 gate를 독립 점검한다. 실패하면 범위와 이유를 보고하고 종료한다.
4. 입력·평가 manifest 분리, 필요한 경로·digest 보완, 공식 processor 및 요청 그래프를 구현한다. 원 계획의 D 기술 gate와 E protocol 잠금을 완료한다.
5. gate 통과 시 두 GPU로 실제 비교를 실행한다. 기준 계획의 평가·비용·독립 verifier를 완결한다.
6. 새 보고서에 유지/변경/승계/무효/미완료를 구분한다. 과거 원본은 보존하며 소스 checkpoint는 orchestrator 절차에 맡긴다.

# Evaluation (성공/실패 기준 포함)

원 metric·문턱을 유지한다. case MCQ accuracy를 사용하며 마지막 비어 있지 않은 줄의 `Answer: A`–`Answer: E`를 엄격하게 파싱한다. 여러 답·불명확한 최종 답은 invalid 및 오답으로 분모에 유지한다. 비EOS·기술 실패를 별도 보고한다.

D−C, R−C, D−R, D−X 각각에 98.75% two-sided cluster bootstrap CI, seed5002, 20000회를 적용한다. case 평균 estimand를 유지하고 cluster를 함께 resample한다. 원 계획의 discordance·exact 보조 분석도 유지한다.

- 압축 손실: D−C≥0.10이며 CI 하한>0.
- 재접근 회복: R−C≥0.10이며 CI 하한>0.
- 원본 이후 중간물 문제: D−R과 D−X 각각≥0.10이며 CI 하한>0.
- 영상 관련 해석: D−T의95% CI 하한>0이 아니면 영상 한계 해석과 method 진입 근거를 제한한다.
- 비용·비열등성: 정확도 paired CI 하한≥−0.03과 device-seconds 최소20% 감소를 함께 요구한다. 단회 timing으로 모집단 비용 CI를 만들지 않는다.

C/R 각 배포 경로에 F/U 비용을 포함하되 실제 공유 실행 장부에는 한 번만 센다. loading·실패·재시도를 따로 기록하고 동시 worker 시간 합을 GPU busy union 또는 latency로 표현하지 않는다.

양성이라도 D/R 등 단순 대안으로 충분하면 새 방법은 보류한다. 중요한 잔여 문제와 영상 기여가 함께 남을 때만 full review에서 method pilot을 검토한다. 관련 차이의 CI 상한이0.10 미만이면 현재 큰 효과 가설의 투자를 보류한다. 무효과와 중요한 효과를 함께 포함하면 정밀도 부족으로 현재 자료 범위를 보류한다. gate 실패는 모델 가설 기각이 아니다. 결과에 따라 추가 sample·prompt·seed·loss를 붙이지 않는다.

# Risks / Checks

필수 회귀 검사는 무효 감사 자동 유입, 누락 case의 암묵적 keep, 정정 전 파생물 승계, sheet/원본 불일치, 이전 결과 경로 쓰기, 평가 필드·unknown 하위 key 혼입, symlink, 원본·산출물 변조, 영상 누락·순서 교환, 단계 digest 오류, 중복 요청·torn output·worker 수 변경 재개, 정답 letter 오류와 비용 이중 집계다. 최종 verifier가 실제 보고 대상 raw/source/config digest를 검사했는지 확인한다.

기존 감사 유효 후보도 파일명만으로 승인하지 않는다. 이번 계획은 영상 내용을 확인한 임상 판정이 아니다. 에이전트 감사는 전문가 gold 검증이 아니며 공개 train의 E는 탐색용 개발 평가다. 환자 독립성·사전학습 오염 부재·순수 다중 영상 결합 결함을 주장하지 않는다.

공식 test, MRI F139와 기존 reserve를 열지 않는다. VinDr 승인 대기를 유지한다. 새로운 limitation 승격이나 과거 blocker 삭제는 full review의 근거 없이 하지 않는다.

**대규모 GPU 필요 후보:** 다중 영상 encoder와 언어 decoder의 공동 적응을 통한 근거 보존 학습 후보는 기준 계획대로 보존한다. 현재 필요성·차별성은 미확정이며 이번에는 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

이번 라운드는 같은 실험의 인계이므로 문헌·전략을 다시 탐색하지 않았다.

- 기준 plan.md 전체와 plan.json을 확인했다. SHA256은 각각 `6e9a5010785840182c20e13456bc0051d73b1a827ee4e19eebba229bc7ffc041`, `32e82ceac78888799067eae50d6e36a87e0286dcb33a20c58f658e7afd478813`이다.
- 현재 research HEAD는 `fbaea4c557e151fa39d5cdf0e9da1c4f8de7c106`이고 작업 트리는 깨끗하다. checkpoint.json은 interrupted/unreviewed이며 unpreserved_paths는 없다. 이는 재사용 승인이 아니다.
- 두 최종 정정문을 읽었다. image_part 전체, redo01–25와 redo26의 c620/c621은 무효다. redo26의 명시된 여섯 사례 및 redo27–30·valid31은 출처 확인 후 재사용할 후보다. 이번 계획 단계에서 해당 이미지의 관찰 내용을 검증했다고 주장하지 않는다.
- regression_source_check_v2.json은 254 case·896장, bad=[], RGBA364/RGB532, alpha_min=255를 기록한다. 이는 파일·decoder 검사 기록이며 시각적 주석 감사의 완료 근거가 아니다.
- mt50_common.py와 mt50_prep.py를 확인했다. OUT이 iter_050으로 고정되어 있고 prep은 bad를 모아 기록하지만 실패 종료를 강제하지 않는다. 기존 sheet 존재 시 내용 일치를 검증하지 않는다. 경로 검사는 모든 조상 symlink를 검사하지 않는다. 현재 실행 경로에서 보완해야 한다.
- history_part1–4는 보존돼 있으나 범위 요약을 case별 근거로 연결해야 한다. 일부 제외 설명은 진단을 직접 명시한 경우와 강한 검사·증상 단서를 혼동할 여지가 있으므로 원 규칙과 충돌하는 항목만 원문으로 재검토한다.
- iter_043 원본 review.json/code_assets와 iter_049의 needs_fix 항목, CODE_ASSETS 및 LIMITATIONS 관련 항목을 확인했다. 현재 rsna_diag helper 다섯 파일은 iter_043 원본 blob과 모두 같다. 이미 현재 기반에 있으므로 추가 반입은 불필요하다. 모델 로더·잠금의 제한적 재사용과 새 입력 검증 의무를 유지한다.
- 소스 수정·파일 생성·실험 실행은 하지 않았다. 다음 구현에서 출처 확인, 필요한 감사 보완, 원 gate에 따른 실행 또는 보류를 수행한다.
