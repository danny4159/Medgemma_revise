# 요약

- **이번에 할 일:** 기존 254 case·896장의 누출 감사를 마치고, 통과한 집단에서 직접 답변·소견 압축·원본 재접근·추가 공동 판독을 비교한다.
- **필요한 이유:** 자료 확보는 끝났지만 실제 모델 한계는 미검증이다. 생성 소견의 손실과 단순 대안의 충분성을 구분해야 한다.
- **확인할 기준:** 동일 case의 답변 정확도 차이·불확실성, 영상 기여, 실제 추론 비용을 함께 본다.
- **주의·다음:** 기존 grounding 투자는 보류한다. 새 contribution은 미확정이며, 자료 gate 실패나 불확정 결과를 같은 setup의 자동 연장으로 연결하지 않는다.

# Current Understanding

iter_049는 공식 train 7,347행에서 전체 X-ray·비longitudinal 후보 254 case·896장을 확보했다. 원 리뷰는 파일·pixel hash와 집계를 확인했지만 이력의 의미상 정답 정보, 영상 주석과 figure 감사가 끝나지 않아 `valid_experiment=false`로 판정했다. 이 판정과 blocker를 보존한다.

기준 문서는 `agent/runs/iter_049/plan.md`, SHA256 `2da819e987874bd57f260d5cbcfb560d866df152f327bec1b92fdd76658018bd`, 그리고 해당 review.md/review.json이다. 이번은 단순 setup 재실행이 아니라 진입 gate를 갖춘 새 diagnostic이다.

- **유지:** 전체 X-ray, 비longitudinal, 고유 영상 둘 이상, 원본 전체 영상 보존, 원래 A–E 선택지와 정답, 공식 train만 사용.
- **변경:** 누출·figure 처리 규칙, 추론용 물리적 manifest 분리, D/E 분리, 실제 생성 조건과 투자 기준을 이번에 고정한다.
- **미완료:** 의미상 누출 감사, 공식 processor 연결, 실제 출력·비용 측정.
- **회귀 검증:** 기존 254/896 기준 manifest의 출처·정합성, decoder, 입력 필드 allowlist, code/rule/output digest와 완료 판정 연결.

Plain radiograph·fluoroscopy·angiography·mammography가 섞인 자료다. chest X-ray 연구 또는 환자 단위 독립 평가라고 표현하지 않는다. 공식 train에서 새로 분리하는 E도 탐색용 개발 평가이며 외부 독립 확인이 아니다.

# Strategy Check / 연구 방향 판단

iter_048·049의 전략 판단을 유지한다. 직접 공동 SFT의 회복과 적응 MedGrounder 비교 이후 현재 두 양성 문장 grounding의 추가 투자는 보류됐다. 이번 자료의 결과는 그 관찰을 소급 설명하거나 기각하지 않는다.

중요한 사용 문제는 여러 영상을 중간 소견으로 요약하는 의료 VLM workflow에서 답변에 필요한 근거가 유지되는가다. 해결된 질문은 자료 확보 가능성이다. 남은 질문은 생성 텍스트로의 대체와 생성 텍스트의 간섭을 구분할 수 있는가다.

현재 방법 개선은 실제 잔여 실패가 없어 이르다. 한정 진단은 기존 자산으로 서로 다른 입력 경로를 비교할 수 있어 우선한다. 다른 질문 전환은 감사 실패·정밀도 부족·단순 대안 충분성 때 선택한다. 진단/setup의 누적 체류를 새 track으로 초기화하지 않는다. iter_049의 확보 비용은 영상 다운로드 약157.6초·65.8MB, GPU 0이며 전체 track의 누적 비용을 이 수치로 대체하지 않는다.

가장 가까운 선행인 [MedThinkVQA](https://arxiv.org/html/2604.16506v1)는 생성 중간 소견의 불안정성을 이미 다룬다. 이번 관찰만으로 차별성이 성립하지 않는다. 새 방법의 필요성은 기존 직접·단계별 대안 이후에 남는 실제 문제와 비용 기회가 있어야 검토한다.

# Hypothesis

H1: 생성 소견·요약만으로 답하는 C는 원본 전체 영상에 직접 답하는 D보다 정보를 잃을 수 있다.

H2: 같은 생성 요약에 원본을 다시 제공한 R이 C보다 회복되면 영상 재접근의 효과를 지지한다. R이 D보다 나쁘면 원본이 있어도 생성 텍스트가 판단을 방해하거나 입력 길이·판독 경로가 영향을 준다는 경쟁 설명이 남는다.

X는 전체 영상을 공동으로 읽어 생성한 중간 소견과 원본을 사용하는 추가 계산 대조다. R과 X 차이는 판독 분해 방식의 차이를 포함하며 순수 내부 기전으로 해석하지 않는다. T는 이력·선택지만으로 얻는 성능을 확인한다. 이 설계만으로 모든 영상이 필요함이나 순수 다중 영상 결합 능력을 입증하지 않는다.

# Limitation Evidence / Correct Usage Checks

새 모집단에서 검증된 출력 한계가 없으므로 `limitation_ids=[]`, `experiment_role=diagnostic`, `method_stage=none`이다. 기존 PadChest observed 한계를 새 자료에 옮기지 않는다.

## 자료 진입 gate

기존 `results/iter_049/audit_v2/eligible_cases.jsonl`, `image_manifest.json`, 원본 metadata와 영상을 읽고 새 산출물은 `results/iter_050/`에 저장한다. 이미 검증된 자료를 재다운로드하거나 과거 결과를 덮어쓰지 않는다.

모델 출력 확인 전에 254개 이력·선택지와 896장 모두에 case/image별 감사 기록을 만든다. 영상은 contact sheet로 전체를 확인하되 주석·세부내용이 불명확하면 원본 크기로 확대한다. OCR·문자열 검사는 보조이며 육안 확인을 대신하지 않는다. case별로 이력 정보 유형, 영상 주석, figure 구성, 해부 부위, subtype, 제외 사유와 근거를 기록한다.

1. 임상 이력에서 현재 정답 진단을 확정 사실로 직접 서술하거나 명백한 동의어로 알려주는 사례는 제외한다. 감별진단·의심·과거 병력·증상·검사 결과는 자동 제외하지 않고 의미와 시점을 기록한다. 판단이 모호한 사례는 primary에서 제외한다. 이력을 삭제·재작성해 적격 사례를 만들지 않는다.
2. 영상에 정답 진단명, 판독 설명, 병변을 가리키는 교육용 화살표·outline, 답변을 알려주는 도식이 있으면 case 전체를 primary에서 제외한다. 통상적 laterality·view·장비 표시와 단순 panel 문자는 유지한다. montage 자체는 제외 사유가 아니며 전체 영상을 원형대로 제공한다.
3. 정답/선택지의 중복·불일치와 명백히 상충하는 자료는 제외한다. iter_049의 duplicate-option 제외 규칙을 유지한다. 어려운 진단·희귀 subtype이라는 이유로 제외하지 않는다. 에이전트 감사를 임상 전문가의 gold 재판정으로 표현하지 않는다.
4. 동일 pixel 외 perceptual near-duplicate, 같은 이력·선택지 및 알려진 동일 case 출처를 확인해 연결된 component를 중복 cluster로 묶는다. split은 cluster 단위다. 원본 전체 영상은 유지하며 case 내 중복 영상도 삭제하지 않는다. 환자 독립성·사전학습 오염 부재를 주장하지 않는다.

추론 manifest는 이력·A–E options·순서 있는 영상 경로와 hash만 허용한다. case ID는 실행 추적에만 쓰고 prompt에는 넣지 않는다. `_eval`, `_audit`, caption, findings, discussion, ICD, title과 정답은 별도 파일에 둔다. 하위 필드도 allowlist로 제한하고 worker는 평가 파일을 읽지 않는다.

## 정상 입력 gate

고정 MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, eval, adapter 없음, greedy를 사용한다. [공식 model card](https://huggingface.co/google/medgemma-1.5-4b-it)의 processor/chat-template 경로를 기준으로 각 단계를 독립 single-turn 요청으로 만든다.

Pillow 12.3.0을 포함한 실제 환경을 고정하고 RGB 변환·alpha 검사와 파일/pixel hash를 남긴다. 기존 영상은 480×480이지만 추가 crop·padding·영상 선택을 하지 않는다. 영상 순서·image token 수·실제 tensor·전체 입력 token을 검사한다. options를 포함한 실제 processor 길이를 사용한다. 한 영상, text-only, 2장 및 최대 영상 수 요청에서 공식 직접 구성과 wrapper의 tensor key/shape/dtype/value를 대조한다.

# Contribution Path / Baselines / Reuse

현재 브랜치의 `mt49_audit.py`, `mt49_fetch.py`, `mt49_images.py`, `mt49_report.py`, `test_mt49.py`는 needs_fix다. 실제 재사용 경로에서 다음을 수정한다.

- 완료 재사용에 원본·코드·규칙·입력·산출물 digest를 모두 연결한다.
- 기존 파일과 경합 경로의 size/hash 재검증, symlink·경로 이탈 거부를 강제한다.
- 영상 manifest에 공식 객체 식별자, 원본 revision, decoder, 입력 manifest digest를 연결한다.
- 보고서의 token 추정 오류를 정정하고 실제 processor 길이와 구분한다.

다운로드가 필요 없는 경로는 재실행하지 않는다. 미사용 과거 파이프라인 정비도 하지 않는다.

`reuse_assets`의 iter_043 helper 다섯 파일은 원본 code_assets와 blob을 확인했다. 모델 로더·잠금 및 import 의존성만 반입한다. iter_021의 MRI 전용 multi-image runner는 protocol·padding·gate 의존성이 있어 사용하지 않는다. 새 adapter는 공식 processor로 현재 과제의 이미지 목록을 구성한다. 새 실행기는 MCQ 및 단계 간 생성물 연결에 필요한 범위로 한정한다.

직접 답변 D가 가장 중요한 단순 baseline이다. 생성 요약 C/R과 공동 소견 X는 기존 방식의 대안이다. oracle caption은 사용하지 않는다. 학습이나 신규 방법을 실행하지 않으며 후속 method를 택할 때 동일 annotation 직접 SFT 비교를 별도로 설계한다.

# Proposed Experiment

## 1. 분할과 규모

감사 통과 cluster를 subtype와 영상 수 2–3/4장 이상으로 층화하고 seed=5001로 D24를 고정한다. D에는 subtype·영상 수 범위를 포함하며 가장 긴 입력 case를 포함한다. 연결된 cluster는 전부 D로 이동시키고 실제 D 크기 증가를 기록한다. 나머지 전체를 E로 고정한다. annotation 여부·정답성 이력 감사 결과도 분포표에 남긴다.

E에 독립 중복 cluster가 156개 이상이면 실행한다. 이 기준은 discordance q=0.25일 때 4개 대비의 98.75% CI 반폭을 약10 pp로 예상하는 계획용 근사다. q=0.10/0.25/0.40의 정밀도와 unequal cluster size 영향을 함께 계산하며 검정력 보장으로 쓰지 않는다. 부족하면 현재 자료 범위의 진단 투자를 보류한다. 다른 modality·test·longitudinal로 자동 확대하지 않는다.

## 2. 비교 조건

모든 최종 답변은 동일 이력·원래 선택지와 공통 지시를 사용한다. 기본 최종 지시는 제공된 정보로 가장 타당한 진단을 고르고 짧은 근거 뒤 마지막 줄에 `Answer: <A-E>`를 출력하도록 한다. 조건 차이는 제공하는 영상과 중간 소견으로만 만든다.

- **T:** 이력·선택지. D에서 image content만 제거하며 별도의 추측 지시를 추가하지 않는다.
- **D:** 이력·선택지·원본 전체 영상에서 직접 답한다.
- **F→U→C:** 각 영상 F에 이력·선택지와 해당 영상 하나를 제공해 진단 선택 없이 관찰 소견·불확실성을 생성한다. 원래 영상 index로 묶어 U가 통합 요약을 생성한다. C는 이력·선택지·U로 최종 답한다.
- **R:** C와 완전히 같은 U bytes 및 원본 전체 영상으로 답한다.
- **H→X:** 전체 영상에서 H가 공동 소견을 생성하고, X가 H와 원본 전체 영상으로 답한다. 추가 판독·출력 예산의 단순 대조다.

F는 영상당 최대512 tokens, U는 최대1024, 최종 T/D/C/R/X는 최대1024를 시작값으로 한다. H는 해당 case의 `영상 수×512+1024` 상한으로 두어 F+U의 허용 중간 token 총량과 맞춘다. 상한 일치가 실제 비용 일치가 아님을 명시한다. D에서 비EOS·잘림이 나오면 해당 단계의 cap을 한 번 두 배로 늘려 전체 조건에 일관되게 고정한다. 그 후에도 정상 출력 경로가 확보되지 않으면 E 진입을 보류한다. E 결과를 보고 cap을 바꾸지 않는다.

중간 생성은 문자열 그대로 사용하고 답변 내용에 따른 선택·교정·재생성을 하지 않는다. U는 F와 hash로, C/R은 U와 hash로, X는 H와 hash로 연결한다. 각 단계는 새 대화다. 추가 임상 정답 정보를 prompt에 넣지 않는다.

## 3. 동작 확인 → 가능성 탐색 → 본진단

D24 중 subtype·긴 입력을 포괄하는 최소 8 case로 입력·parser·EOS·메모리·재개를 검사한다. D24 전체로 조건별 실제 생성과 처리량을 확인한다. 이 과정의 정확도로 유리한 prompt나 조건을 선택하지 않는다. 기술적 형식 수정이 필요하면 변경 전후와 근거를 기록하고 D를 다시 확인한 후 E protocol을 잠근다.

E 확대 조건은 자료·입력·출력·재개 gate 통과와 위 정밀도 기준이다. D의 우연한 정확도 차이를 확대 기준으로 삼지 않는다. E는 고정된 한 번의 탐색 평가로 모두 실행하며 중간 정확도를 열어 표본을 줄이거나 늘리지 않는다. 이번에는 학습·다중 seed·독립 확인 단계로 확대하지 않는다.

본 요청 수는 F의 S건, U/H 각 N건, T/D/C/R/X 각 N건으로 `S+7N`이다. 전체 후보 상한은 896+7×254=2,674건이며 실제 D/E·감사 제외 후 수치를 먼저 기록한다. 동작·처리량·재개 검사 호출은 별도 장부에 남긴다.

## 4. GPU·시간·checkpoint

시작 직전 nvidia-smi로 허용 GPU 0/1의 실제 여유를 확인한다. 양 GPU에 독립 case 또는 단계별 준비된 요청을 배치한다. 논리/물리 장치 대응을 기록한다.

D 입력에서 1 worker/GPU와 2 worker/GPU를 먼저 비교하되 동시 peak 합계+외부 점유+worker당 2GB 여유가 들어갈 때만 후자를 실행한다. 복수 worker가 불가능하면 작은 batch 확대와 비교한다. 가장 긴 영상 입력·H 출력 cap을 포함해 requests/min, case throughput, peak VRAM, 긴 요청 지연, OOM·CPU/RAM/I/O 경합 및 답변 정합성을 확인한다. 안전하고 처리량이 높은 구성을 선택하며 1 worker 유지 시 실측 이유를 남긴다.

D 실측 전에는 시간 숫자를 확정하지 않는다. 단계별 요청 수/처리량과 dependency critical path로 E의 예상 wall-clock을 산출해 실행 전에 기록한다. 두 GPU를 활용해도 F/U/H의 의존 순서는 유지한다. 수 시간 소요 자체는 중단 사유가 아니다.

request ID는 split·case·condition·prompt·ordered image hash·model/config·상위 생성물 digest로 만든다. 원자적 claim, worker별 결과, flush/fsync, attempt별 비용 장부, source/config 잠금과 완료 seal을 둔다. worker 수 변경 재개에서도 기존 결과의 provenance와 중복·누락을 검사한다. 살아 있는 claim을 지우지 않는다. OOM은 동시성/batch를 낮추고 동일 요청을 복구하며 표본·영상·cap을 축소하지 않는다.

# Implementation Tasks for Claude

1. 기준 plan/review와 현재 파일을 확인하고 필요한 helper만 manifest대로 반입한다.
2. 기존 원본을 검증해 재사용하고, 누출·figure·subtype·중복 감사를 case/image별로 완결한다. 불확실한 판단과 제외 사유를 기록한다.
3. 입력/정답 manifest를 물리적으로 분리하고 D/E 및 정밀도 gate를 생성한다. 실패하면 보류 보고서로 종료한다.
4. 공식 processor 기반 다중 영상 adapter와 단계별 요청 그래프를 구성한다. F/U/H 의존물은 raw output digest로 연결한다.
5. D에서 입력 tensor, cap, parser, 2/4 worker 또는 batch, 중단·재개·변조 거부를 검사한다. E protocol과 예상 비용을 잠근다.
6. E를 실행하고 accuracy·paired CI·오류/회복 흐름·subtype·비용을 산출한다. 평가자는 generation worker와 분리한다.
7. 독립 verifier로 요청 행렬, 정답 대응, parser, case 벡터, 모든 투자 기준과 비용을 재계산한다. 최종 report와 verifier가 같은 raw/source/config digest를 검사했는지 강제한다.
8. 새 결과는 iter_050에 보존하고 원 결과·blocker·보호 reserve를 변경하지 않는다. 소스 checkpoint/commit은 orchestrator 절차에 맡긴다.

# Evaluation (성공/실패 기준 포함)

## 지표와 판정

주지표는 case 단위 MCQ accuracy다. parser는 마지막 비어 있지 않은 줄의 `Answer: A`부터 `Answer: E`까지를 허용한다. 답이 여러 개이거나 마지막 줄이 불명확하면 invalid·오답으로 분모에 유지한다. 문자열 포함으로 정답을 추측하지 않는다. 비EOS·기술 실패·invalid를 별도로 보고하며 동일 생성의 strict/형식 정규화 수치는 보조 분석으로만 남긴다.

paired 대비 D−C, R−C, D−R, D−X 네 개에 각각 98.75% two-sided cluster bootstrap CI를 사용한다. seed=5002, 20,000회, case 평균을 estimand로 유지하고 중복 cluster를 함께 resample한다. 작은 cluster 수·퇴화 bootstrap에서는 paired discordance와 exact 보조 구간도 보고한다. T와 subtype 분석은 설명용이며 별도 확증으로 부르지 않는다.

최소 가치 있는 차이는 10 accuracy pp로 정한다. 현재 작은 공개 개발 모집단과 다단계 추론 비용에서 새 학습 투자를 정당화할 정도의 효과를 찾기 위한 기준이며 임상 허용오차가 아니다. 큰 오류율만으로 새 방법의 필요성을 인정하지 않는다.

- **압축 손실 지지:** D−C 점추정 ≥0.10, CI 하한>0.
- **원본 재접근 회복 지지:** R−C 점추정 ≥0.10, CI 하한>0.
- **원본이 있어도 남는 생성 중간물 문제:** D−R 및 D−X가 각각 점추정 ≥0.10, CI 하한>0이면 현재 고정된 두 중간물 경로의 유해성을 지지한다. 내부 원인 확정은 아니다.
- **영상 관련 해석의 전제:** D−T와 영상 조건의 이득·오류 교환을 함께 확인한다. D−T의 95% CI 하한이 0을 넘지 못하면 영상 관련 한계의 해석을 제한하고 이를 method 진입 근거로 쓰지 않는다.

정확도뿐 아니라 D/C/R/X의 유효 요청 처리량, input/output token, warm device-seconds, case end-to-end latency, peak VRAM을 측정한다. C와 R의 F/U 생성 비용은 각 배포 경로 비용에 각각 포함하며 전체 실험 장부에서는 공유 실행을 한 번만 센다. loading·실패·재시도는 별도 총비용에도 포함한다. 동시 worker 시간 합을 GPU busy union이나 latency로 부르지 않는다.

비용·비열등성 주장을 하려면 paired 정확도 CI 하한 −0.03 이상과 device-seconds 최소20% 감소를 함께 요구한다. 이번 단회 실행의 비용은 기술적 측정값이며 반복 timing 없이 모집단 비용 CI를 만들어내지 않는다. 이 기준의 통계적 비용 확증은 이번에 주장하지 않는다.

## 결과별 다음 행동

**양성:** 압축 손실과 재접근 회복이 관찰돼도 R 또는 D라는 기존 대안으로 충분하면 해당 baseline을 보존하고 새 방법 투자를 보류한다. D/R/X 모두를 고려한 중요한 잔여 문제와 영상 기여가 확인될 때만 full review가 최소 method pilot을 검토한다. 그때도 현재 결과는 observed 후보 근거이며 신규성·외부 일반화·full 개발을 승인하지 않는다.

**음성:** 관련 차이의 CI 상한이 0.10 미만이면 이 자료·조건에서 큰 효과를 전제로 한 투자를 보류한다. 단순 대안이 충분하다는 근거와 특정 효과가 작다는 근거를 구분한다.

**불확정:** CI가 무효과와 중요한 효과를 함께 포함하면 정밀도 부족으로 표시하고 현재 자료 범위를 보류한다. E의 결과를 보고 추가 sample·prompt·seed·loss를 붙이지 않는다. 자료 gate 실패는 모델 가설 기각이 아니라 진입 실패다.

독립 확인은 이번에 하지 않는다. test split·MRI F139·기존 reserve를 열지 않고 VinDr 승인 통지 전 접근·다운로드를 하지 않는다.

# Risks / Checks

- 영상 annotation 및 임상 이력 감사는 정답 누출 부재의 완전한 증명이 아니다. 애매한 사례를 보수적으로 제외하고 제외 전후 모집단을 보고한다.
- 강한 이력 정보는 정당한 임상 정보일 수 있다. T의 정답 여부로 사례를 사후 제거하지 않는다.
- 여러 영상이 존재한다는 것과 여러 영상의 결합이 정답에 필요하다는 것은 다르다. 이번 결과를 순수 결합 능력의 인과 증거로 확대하지 않는다.
- 요약 내용의 오류와 압축에 의한 누락은 최종 accuracy만으로 완전히 분리되지 않는다. 틀린 중간물을 내부 병목으로 단정하지 않는다.
- 기본 MedGemma 4B 외 모델, 직접 SFT, 다른 기관 및 임상 결과 일반화는 미검증이다.
- 최소 회귀 검사는 평가 필드 혼입, 하위 unknown key, symlink, 원본/산출물 변조, 영상 누락·순서 교환, 잘못된 단계 digest, 중복 request, torn output, worker 수 변경 재개, 잘못된 정답 letter 및 비용 중복 집계를 포함한다.
- 현재 파일이 검증됐다는 사실과 범용 재사용 승인은 다르다. 과거 blocker를 지우지 않는다.
- **대규모 GPU 필요 후보:** 다중 영상 encoder와 언어 decoder를 공동 적응해 근거 보존을 학습하는 방향은 보존한다. 현재 그 필요성과 차별성은 미확정이며 이번에는 실행하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 확인한 사실

- GOAL, GPT_USAGE_POLICY, iter_049 plan/review/review.json, iter_048 review, LIMITATIONS의 관련 grounding 항목, CODE_ASSETS의 관련 항목을 확인했다.
- 현재 research HEAD는 `05bd6b0b543ae786a7e250f7502b70db7a6dc7f8`이고 작업 트리는 깨끗했다. 현재 브랜치에는 mt49 파일이 있으며 rsna_diag 실행 자산은 없다.
- iter_049 원 계획 SHA256은 `2da819e987874bd57f260d5cbcfb560d866df152f327bec1b92fdd76658018bd`다. 이번은 기존 setup의 성공 판정 수정이 아니라 실제 출력 진단을 추가하는 별도 계획이다.
- 직전 리뷰는 254 case·896장의 연결과 hash를 독립 확인했지만 누출·figure 감사를 blocker로 남겼다. 실제 코드에서 infer_view와 달리 저장 manifest에는 `_eval`·`_audit`가 있고 하위 영상 필드 allowlist가 불완전함을 확인했다. audit_done 재사용도 raw hash만 검사한다.
- feasibility.json의 모든 영상은 480×480이고 최대 case는 14장이다. token 추정에는 options가 빠져 있으므로 기존 3.6k 추정으로 메모리를 승인하지 않는다. Pillow 12.3.0과 다른 decoder에서 pixel hash가 달랐다는 원 리뷰를 유지한다.
- 실제 임상 이력에는 정답을 직접 명시한 사례뿐 아니라 질병 계열·검사 결과가 강한 단서인 사례도 있다. 문자열 탐지 14건만 제외하는 것으로 충분하지 않다. 반대로 진단에 유용한 정당한 이력 정보를 모두 누출로 분류해서도 안 된다.

## 선행과 정상 사용

[MedThinkVQA 논문](https://arxiv.org/html/2604.16506v1)은 생성 중간 소견의 불안정성을 이미 비교한다. 따라서 같은 경향의 재현이나 원본 재접근만으로 신규 기여를 주장할 수 없다. 이번에는 같은 생성 요약을 고정한 영상 재접근 대비와 추가 공동 판독 대조를 사용한다.

[MedGemma 공식 model card](https://huggingface.co/google/medgemma-1.5-4b-it)는 공식 processor의 chat template와 greedy 생성 예제를 제공하며 multi-turn 용도로 최적화되지 않았다고 명시한다. 이번 각 단계는 독립 single-turn 요청으로 구성한다. 논문의 정확한 MedGemma 평가 prompt/parser가 확보되지 않았으므로 공개 점수 재현으로 부르지 않는다.

## 자산 판단

iter_021 원본 code_assets와 mi19_gen을 확인했다. MRI 전용 request/protocol·padding 및 미해결 gate 의존성이 있어 전체 실행기를 반입하지 않는다. iter_043의 승인 helper 다섯 파일과 iter_048의 동일 blob을 확인하여 모델 로더·잠금만 재사용한다. 신규 코드는 현재 과제의 다중 영상 입력, 단계 간 생성물 연결 및 MCQ 평가에 한정한다.

## 다음 투자 판단

현재 공동 grounding 보류는 유지한다. 확보한 자료의 한정 진단은 새 학습보다 정보 가치가 높지만, 단순 대안이 충분하거나 남은 표본으로 정밀도가 부족하면 종료한다. 새로운 limitation은 실제 출력과 사용 검증을 리뷰한 뒤에만 등록할 수 있다.
