# 요약

- **이번에 할 일:** base·직접 SFT·추가 SFT가 특정 finding의 음성과 Normal 판정을 구분하는지 실제 생성으로 검사한다.
- **필요한 이유:** bbox 개선은 확인됐지만 질문 target이 달라졌을 때의 능력과 모듈형 활용 가치는 미확인이다.
- **확인할 기준:** 180명 탐색에서 형식·target별 답변·bbox를 분리하고, 판단에 필요한 경우 고정된 600명으로 확대한다.
- **주의·다음:** 이번은 진단이다. 임상 reasoning·새 방법·외부 일반화를 주장하지 않으며 reserve와 기존 결과를 보존한다.

# Current Understanding

iter_009의 정상 사용 grounding 한계와 iter_012의 직접 LoRA SFT 개선은 유지된다. iter_014의 G는 full-train에서도 추가 이득을 입증하지 못해 투자를 중단했다. 추가 SFT C의 최종 checkpoint는 진단 자산으로 사용하지만 V200 선택 기준을 통과한 최적 모델은 아니다.

이번에 중요한 구분은 ‘폐렴 의심 opacity 없음’과 ‘Normal’이다. RSNA의 NoOpacity/NotNormal은 다른 opacity나 이상을 포함할 수 있다. Normal에도 치유된 늑골 골절만 있는 경우가 포함될 수 있다. 질문과 결론은 이 판독 규약으로 제한한다. [RSNA 원 논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC8017407/)

iter_008 보완의 정상 사용 진단 요구는 iter_009에서 충족됐다. 과거 공식 sanity를 반복하지 않고 새 질문·parser·입력 연결을 검증한다. anatomy 전이와 새 loss 학습은 보류한다.

# Strategy Check / 연구 방향 판단

강한 직접 SFT를 확보했고 두 추가 loss의 투자 근거가 부족하므로 연구 방향을 재검토한다.

중요한 능력은 전문 과제에 적응하면서도 질문이 요구하는 판단 범위를 구분하는 것이다. 단일 finding 검출기의 빈 출력이 다른 이상까지 없다는 뜻은 아니다. 현재 자료에서 이 능력이 손상됐는지는 미확인이다.

세 선택을 비교했다.

1. **기존 checkpoint 진단:** 정답·checkpoint·생성 결과가 있어 추가 학습 없이 형식 저하, target별 능력 변화, 모듈형 활용을 구분할 수 있다. 이번 선택이다.
2. **다른 질문으로 전환:** 영상–언어 충돌과 의료 부정 이해는 중요하지만 가까운 선행과 유효한 개입 정답을 확보해야 한다. 이번 진단이 실질적 차이를 배제하면 우선순위를 높인다.
3. **현재 grounding 개선:** 새로운 원인이나 효율 근거 없이 loss를 추가할 정보 이득이 낮다. localization 연구 전체를 기각하지는 않는다.

[Grounding/QA 진단 연구](https://arxiv.org/html/2604.27720v2), [LobA](https://arxiv.org/html/2505.00744v1), [NAST](https://arxiv.org/html/2602.12498v2)가 이미 관련 현상과 방법을 다룬다. 이번 결과만으로 novelty를 확정하지 않는다. 방향을 바꾸는 조건은 Evaluation에 고정한다.

# Hypothesis

주가설은 단일 opacity grounding 적응의 효과가 질문 target에 따라 달라질 수 있다는 것이다.

- H1: bbox와 동일 finding의 존재 판단은 개선되지만, NoOpacity/NotNormal을 Normal로 답하는 오류가 증가한다.
- H2: 겉보기 저하는 답변 형식 변화로 설명된다.
- H3: 두 target을 구분하는 능력이 유지되거나 함께 개선된다.
- H4: 적응된 localizer의 출력과 base reader를 결합하면 직접 적응의 이득·손실과 다른 결과가 나온다.

관찰만으로 빈 목록 학습이 원인이라고 확정하지 않는다. H1이 재현돼도 일반 forgetting, 답변 prior, task-specific supervision을 분리하는 학습 대조는 후속 과제다.

# Limitation Evidence / Correct Usage Checks

대상 limitation은 validated인 `lesion-grounding-generalization`이다. 검증 범위는 특정 RSNA 조건의 실제 bbox 오류와 직접 적응 효과다. 새 target 구분 오류는 아직 validated가 아니다.

유지할 사용 조건:

- MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, 기존 processor/chat template, bf16, greedy.
- 값 보존 RGB 변환과 square padding, bbox yxyx 0–1000 규약.
- 1000→2000→4000 생성 cap과 EOS 기록. 짧은 QA라는 이유로 출력 길이를 임의 축소하지 않는다.
- 원본 Calculated annotation과 category를 대조한다. NIH 자동 finding label로 정답을 대체하지 않는다.
- 현재 환자·영상 hash·adapter digest와 과거 출력 provenance를 검증한다.

새 QA는 두 target을 별도 대화로 실행한다. 다음 의미를 고정한다.

- Q_O: `Is there a pulmonary opacity suspicious for pneumonia in this chest radiograph?` 확진 폐렴이나 모든 opacity를 묻지 않는다.
- Q_A: `Under the RSNA chest-radiograph labeling convention, is this image abnormal rather than Normal? An abnormal image need not contain an opacity suspicious for pneumonia. A healed rib fracture alone counts as Normal.`

출력 지시는 두 가지다.

- plain: `Answer only yes or no.`
- JSON: `Return only {"answer":"yes"} or {"answer":"no"}.`

정답 쌍 `(Q_O,Q_A)`는 opacity=(yes,yes), Normal=(no,no), NoOpacity/NotNormal=(no,yes)다. 어떤 영상에도 다른 이상 위치의 정답 bbox를 새로 만들지 않는다.

plain parser는 앞뒤 공백·대소문자·단일 문장부호만 정규화한다. JSON은 단일 answer 키와 yes/no 값만 허용한다. bbox 목록·모순된 답·설명만 있는 답·truncation은 별도 실패다. `[]`를 no로 바꾸지 않는다.

# Contribution Path / Baselines / Reuse

## 비교 자산

- M0: 미적응 base.
- B0: `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`.
- C: `results/iter_014/full/C_lr2e-05/epoch_03/adapter.pt`.
- 조건부 seed 재현: iter_012의 같은 LR·epoch에 저장된 seed29·43.

새 학습은 없다. C는 B0에서 추가 SFT된 trajectory이므로 독립 seed처럼 집계하지 않는다. 각 checkpoint의 학습 환자·presentations·선택 이력을 표에 남긴다.

## 비교군

1. M0/B0/C의 원본 영상 직접 답변.
2. B0 bbox+규칙: 비어 있지 않은 유효 bbox이면 Q_O=yes. 빈 유효 bbox이면 Q_O=no. Q_A는 양성 검출 시 yes, 빈 목록이면 판단 불가로 두고 coverage와 전체 오류를 함께 보고한다.
3. M0+원본 영상+B0 예측 bbox. 좌표·검출 target을 명시하고, 빈 proposal이 Normal을 뜻하지 않는다는 동일 안내를 제공한다.
4. M0+원본 영상+proposal unavailable. 3과 같은 안내·질문을 사용해 설명문 자체의 효과를 구분한다.
5. M0+원본 영상+GT bbox. 진단용 oracle이다. Q_O 답의 일부가 입력으로 제공되므로 실용 성능이나 reasoning 증거로 사용하지 않는다.
6. category에 무관한 고정 답 쌍 baseline. 질문 prior만으로 얻는 성능을 표시한다.

모듈형 비교는 full image를 유지한다. 실제 추론 비용에는 localizer와 reader 호출을 모두 포함하고, 저장 bbox 재사용의 이번 실행 비용은 별도로 표시한다. 이번에 새로운 detector를 학습하지 않는 이유는 최고 검출기와의 성능 경쟁이 아니라 동일 localizer 자산의 사용 방식을 진단하기 때문이다. 내부 위치 학습의 새 방법을 주장할 후속 실험에는 matched-data detector/encoder+head와 강한 직접 SFT가 필요하다.

## 코드 재사용

새 브랜치는 승인 기반 iter_006을 요청한다. `reuse_assets`의 16개 파일을 SHA `698c161f51ec098b1263ea8a5acf4d2870930e0b`에서 반입한다. 현재 파일과 해당 blob 일치를 확인했다. 승인된 전처리·metric·LoRA 범위와 미승인 실행기 범위를 구분한다.

기존 생성·claim·완전성 검사에 새 request manifest 경로를 연결한다. 각 환자마다 evidence prompt가 달라지므로 기존 전역 prompt 이름만으로 요청을 식별하지 않는다. 모델 로더나 LoRA를 재구현하지 않는다. 기존 protocol과 새 protocol의 schema/version을 구분하고 과거 결과를 새 실행 결과로 위장하지 않는다.

`adapt_geo`, `geo_pipeline`, `gen_compare`, 과거 학습 pipeline은 사용하지 않는다. 해당 코드의 수치 검사나 미사용 계산량 문제를 이번 반복에서 수리하지 않는다. untracked `test_rsna_iter010_gpu.py`는 반입 대상이 아니다.

# Proposed Experiment

## 1. 분할과 고정

모든 새 결과는 `results/iter_015/`에 저장한다.

- D36: 기존 validation에서 category별 12명. 질문·parser·형식·실행 구성 개발용이다.
- E180: 기존 confirm에서 category별 60명.
- E600: 같은 풀에서 category별 200명. E180을 포함한다.
- P60: E180에서 category별 20명인 형식·evidence 대조 panel.
- P180: E600에서 category별 60명인 확대 panel. P60을 포함한다.

순서는 `sha256(scope-v1|20260927|category|patient)`로 고정한다. manifest·순서·요청 행렬·분석 규칙을 E180 출력 전에 잠근다. 기존 confirm은 이미 개발 자료이며 이번에도 독립 test라고 부르지 않는다. D36과 E 집단의 환자·pixel 교집합을 금지한다. reserve는 읽어 평가 대상으로 확장하지 않는다.

환자당 한 영상이다. 임상 category별 결과와 균등 가중 요약을 함께 보고한다. 유효한 어려운 영상이나 오답을 사후 제외하지 않는다. 입력 오류·중복은 전체 실행 전에 검출하고 제외 사유와 정해진 순서의 대체 ID를 기록한다.

## 2. 동작 확인

D36에서 M0/B0/C의 두 질문·두 출력 형식을 실행한다. 각 모델·target별 valid rate를 평가해 모든 조합에서 95% 이상이면 plain을 primary로 쓴다. plain이 실패하고 JSON이 이 조건을 만족하면 JSON을 primary로 쓴다. 이는 정답 정확도가 아니라 형식 준수만으로 결정하며 E180 전에 고정한다.

둘 다 실패하면 형식 문제가 먼저라는 결과를 기록한다. target 의미 손실을 판정하거나 E600으로 확대하지 않는다. 무제한 prompt 탐색이나 형식 보정 학습을 추가하지 않는다.

D36 안의 12명에서 C bbox와 세 evidence 조건을 검사한다. 최대 516개 고유 development 요청이며 처리량 비교의 반복 요청은 별도로 센다. 원본과 square-padded 입력, 정답 mapping, adapter 재로드, 기존 생성 함수 연결을 확인한다. 이 단계의 accuracy는 일반화 근거로 사용하지 않는다.

## 3. 가능성 탐색

E180에서:

- primary QA: 3 checkpoint × 2 target × 180명 = 1,080요청.
- C concise bbox: 180요청. M0/B0의 기존 concise bbox는 provenance 검증 후 재사용한다. M0 official_long bbox는 기존 sanity 비교로 별도 보고한다.
- P60 alternate 형식: 3 checkpoint × 2 target × 60명 = 360요청.
- P60 evidence: predicted/unavailable/oracle × 2 target × 60명 = 360요청.

합계 신규 1,980요청이다. checkpoint·환자별 요청 실패와 모든 원시 출력을 보존한다. 실행 완료 후 한 번 분석하며 중간 정확도로 표본·prompt를 조정하지 않는다.

## 4. 규모 확대

입력·형식 gate를 통과한 경우 다음 중 하나면 같은 설정으로 E600/P180까지 확대한다.

- B0−M0 또는 C−B0의 S_scope 차이 절댓값이 0.10 이상이다.
- NoOpacity/NotNormal의 정답 쌍 정확도 차이 절댓값이 0.15 이상이다.
- predicted evidence−unavailable의 panel S_scope 차이 절댓값이 0.10 이상이다.
- 위 효과 크기를 CI가 포함해 판단이 남아 있고, 관측 paired 변동으로 계산한 필요 표본이 현재 E600 범위 안이며 S_scope CI 반폭 0.075 또는 핵심 category CI 반폭 0.10에 도달할 것으로 예상된다.

확대 시 신규 요청 총량은 누적 기준 primary 3,600 + C bbox 600 + alternate 1,080 + evidence 1,080 = 6,360이다. 기존 완료 요청을 다시 생성하지 않는다.

형식 차이가 주된 설명이거나 정답 정의에 문제가 있으면 표본 확대보다 해당 해석을 보류한다. 효과가 작고 CI도 실질적 차이 범위 안에 있으면 확대하지 않는다. E600으로도 필요한 정밀도를 얻지 못할 것으로 예상되면 이유를 기록하고 불확정으로 남긴다. reserve를 자동 소비하지 않는다.

## 5. seed 재현과 독립 확인

도달한 E 집단에서 B0−M0의 사전 중요 효과가 CI와 함께 확인되고 다음 투자 방향을 바꿀 때, 기존 seed29·43 checkpoint로 같은 primary QA를 실행한다. 같은 panel의 alternate 형식도 실행한다. 추가 요청은 `4N+4P`이며 E600/P180에서는 3,120개다. 새 학습이나 유리한 seed 선택은 없다.

이 단계는 학습 seed 재현이며 독립 환자 확인이 아니다. C만의 차이는 single-trajectory 결과로 남긴다. 진정한 독립 확인은 이번 반복에서 수행하지 않는다. 후속 방법과 비교군을 확정한 뒤 보존 reserve 및 적절한 추가 데이터에서 새 계획으로 수행한다.

## 6. GPU·비용·재개

실행 직전 `nvidia-smi`로 허용 GPU 0,1의 UUID·전체 점유·남은 메모리를 확인하고 여유가 큰 장치부터 배정한다. 조회 실패 시 실행하지 않는다.

D36의 대표 요청 48개에 base와 adapter, QA와 긴 출력 가능 조건을 포함해 GPU당 1 worker와 2 worker를 비교한다. 기존 두 worker 근거를 참고하되 새 prompt에서 안전성을 확인한다. 동일 greedy token·parser 결과·요청 수가 유지되고 처리량이 개선될 때 채택한다. batch 확대를 추가 전수 탐색하지 않는다.

추론 프로세스당 약 8–10GiB는 초기 추정이다. 실제 KV cache·출력 길이·allocator와 전체 GPU 점유를 포함해 측정한다. GPU당 두 worker는 각 peak와 각각 2GiB 여유, 다른 프로세스 점유의 합이 용량 안에 들어올 때만 배치한다. 1 worker 유지 시 메모리 또는 처리량 근거를 기록한다.

두 GPU에 독립 checkpoint·shard를 배정한다. GPU당 최대 두 worker는 후보이며 고정 정책이 아니다. 논리 CUDA index와 물리 UUID 대응을 기록한다. 다른 사용자의 프로세스는 변경하지 않는다.

예상 시간은 `요청 유형별 남은 수/실측 처리량 + 모델 로딩·검증 시간`으로 계산한다. 전체 유효 처리량이 10–40 req/min이면 E180 신규 요청은 약 0.8–3.3시간, E600 누적은 약 2.7–10.6시간이다. 이는 가정이며 base가 과거 긴 생성처럼 느리면 더 길어진다. pilot 후 유형별 비용과 일정 추정치를 기록하고 진행한다. 임의 GPU 시간 상한은 없다.

원자적 request claim, worker별 JSONL, run lock, PID/starttime, 요청별 fsync와 attempt별 완료 상태를 유지한다. 재개 시 완료 요청까지 현재 입력·prompt·evidence·adapter와 대조한다. OOM은 동시성 또는 batch를 낮춰 복구하며 표본·생성 cap·metric을 바꾸지 않는다. 오래된 completion의 존재만으로 건너뛰지 않는다.

# Implementation Tasks for Claude

1. 선별 반입과 의존성을 검증한다. 기존 자산·원본 결과를 보존하고 사용 모듈의 결함만 수정한다.
2. 원본 Calculated annotation, manifest, 현재 영상 hash와 checkpoint tensor digest를 연결한 audit를 만든다. 정답 mapping·split·중복을 확인한다.
3. D36/E180/E600 및 panel 목록, 질문 원문, parser, 확대 규칙을 고정한다. 일반 inference manifest에 category·정답을 넣지 않는다. oracle 요청은 별도로 생성한다.
4. 기존 생성 함수·LoRA·claim을 재사용해 요청별 prompt/evidence를 지원한다. 요청 ID에는 모델 revision, adapter digest, image identity, target, 형식, 실제 prompt와 evidence digest를 포함한다. protocol 필수 파일 누락을 거부한다.
5. 기존 bbox 출력 재사용 목록을 만든다. 원본 protocol·adapter·prompt·영상 hash를 확인하고 subset 추출의 출처를 기록한다. 기존 protocol을 새 코드로 통과했다고 소급 표시하지 않는다.
6. QA parser·paired metric·bootstrap을 구현한다. duplicate key와 []의 잘못된 no 변환, 환자 내 반복을 독립 표본으로 세는 오류를 fixture로 검사한다.
7. GPU 허용 범위·조회 실패·worker별 여유·자식 종료 코드와 완료 검사를 보완한다. 작은 실제 중단·재개와 1/2 worker 정합성을 확인한다.
8. 고정된 단계와 확대 규칙대로 실행한다. 실행 전 필요한 규모 변경은 이유와 새 경로를 기록하며 결과를 본 뒤 성공 기준을 바꾸지 않는다.
9. `claude_report.md`에 실제 실행량, 단계별 결정, 미실행 조건, 원시 결과 경로, 비용, SELF_CHECK를 완전하게 남긴다. 보고서를 단순 대기 알림으로 끝내지 않는다. 커밋·브랜치 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

## 지표

주지표 S_scope는 각 환자에서 두 target을 모두 맞힌 비율을 category별로 계산한 뒤 세 category를 균등 평균한 값이다. invalid·truncation은 전체 분모에서 실패로 센다. 주 비교는 B0−M0와 C−B0다.

함께 보고할 항목:

- Q_O/Q_A 각각의 balanced accuracy, category별 accuracy와 답 쌍 confusion.
- NoOpacity/NotNormal에서 `(no,yes)` 정답률과 `(no,no)` 오류율.
- 형식별 valid rate, EOS·truncation, 두 형식 답변 일치율.
- bbox F1@0.3/F1@0.5, 음성 두 category의 valid_empty, GT 2개 이상을 포함하는 multi 결과.
- evidence 조건의 S_scope·category별 차이와 detector+규칙 coverage.
- 환자 전체 평가와 형식이 양쪽 모두 유효한 집단의 보조 분석. 후자만으로 결론내리지 않는다.

category 내 환자를 재표집하는 paired bootstrap 10,000회, seed 20260927을 사용한다. 한 환자의 질문·형식·조건은 함께 재표집한다. 두 주 비교는 각각 97.5% CI를 사용해 가족 단위 오류를 보수적으로 관리하고 나머지는 95% 탐색 CI로 표시한다. 여러 seed를 평가하면 seed별 결과와 환자별 seed 평균을 모두 보고하며 3N명으로 세지 않는다. 순차 확대 결과는 개발 진단 CI이며 confirmatory 유의성으로 부르지 않는다.

## 결과별 의미와 다음 행동

**양성: target 구분 유지·전이 근거.** S_scope의 중요 개선 0.10 이상과 양의 CI, 두 형식의 일관성, Q_A 저하 부재가 함께 있으면 해당 RSNA target 범위의 활용 가능성을 지지한다. 기존 bbox 개선만으로 이 판정을 내리지 않는다. 내부 적응을 계속할 후보 근거는 되지만 신규 기여는 아니다. 다음에는 강한 다과제 SFT·모듈형 baseline과 다른 target 자료의 비교를 설계한다.

**음성: target별 저하 근거.** bbox/동일 finding 이득과 함께 NoOpacity/NotNormal의 Normal 오판 증가가 관찰되고, S_scope 또는 해당 category의 사전 중요 차이가 음의 CI와 두 형식에서 재현되면 target 범위 보존 문제를 지지한다. 추가 기하 loss 투자는 낮추고 일반 replay·명시적 target supervision·모듈형 reader가 설명하는 범위를 다음 질문으로 삼는다. 원인으로 빈 목록 학습을 확정하지 않는다.

**형식 설명.** QA invalid 차이가 크거나 alternate 형식에서 효과가 사라지면 시각 능력 저하 가설을 보류한다. 사용 가능한 출력 형식의 보존 문제로 범위를 제한한다. 이 경우 target 의미를 위한 새 loss 학습을 시작하지 않는다.

**실질적 차이 없음.** 두 주 비교의 CI가 모두 [−0.10,+0.10] 안에 있고 핵심 category 차이도 [−0.15,+0.15] 안에 있으며 모듈형 중요 효과가 없으면 이번 진단에서 추가 투자 근거가 약하다고 판단한다. 다른 의료 VLM 질문으로 우선순위를 옮긴다. localization 자체의 가치나 모든 전이를 기각하지 않는다.

**불확정.** CI가 의사결정 경계를 가로지르면 정밀도 계산에 따라 E600까지 보완한다. 정답 의미·형식·표본 범위가 blocker면 표본만 늘리지 않는다. E600 이후에도 불확정이면 현재 범위와 필요한 추가 근거를 적고 새 학습은 보류한다.

**모듈형 효과.** predicted evidence가 unavailable보다 개선되고 직접 B0의 저하를 피하면 분리된 localizer/reader를 후속 후보로 올린다. oracle만 개선되면 proposal 품질과 인터페이스를 구분할 필요가 남는다. 둘 다 개선되지 않아도 모든 도구 활용의 실패로 일반화하지 않는다.

실행 무결성과 연구 해석을 분리한다. 요청·정답·provenance가 잘못되면 execution_failed다. 유효한 비교에서 차이가 작거나 CI가 넓으면 inconclusive 또는 유효한 음성 진단이다. 진단 성공은 연구 목표 달성이 아니다.

# Risks / Checks

- RSNA Normal을 모든 이상·질환의 부재로 확대하지 않는다. Q_A는 dataset convention의 분류이며 임상 triage 성능이 아니다.
- 예측/GT bbox는 opacity 존재 정보를 제공한다. 이를 새로운 공간 reasoning이나 인과적 evidence 사용으로 주장하지 않는다.
- 다른 질환의 영역 선택, 외부 기관 일반화, 사전학습 비노출은 미검증이다. 새 한계 상태 갱신은 이번 실제 출력의 범위만 대상으로 한다.
- 기존 confirm의 역사적 독립 확인 결과는 유지하지만 이번 사용은 개발 진단이다. reserve는 보존한다.
- C의 선택 부재를 숨기지 않는다. C의 single trajectory로 학습량의 일반적 인과 효과를 주장하지 않는다.
- 성능을 본 후 parser·질문 의미·표본·확대 기준을 고치지 않는다. 개발 형식 결정과 과학적 결과 선택을 구분한다.
- 이번 결과에 필요한 결함만 수정한다. 미사용 기하 학습 경로의 실패한 수치 gate를 소급 통과 처리하지 않는다.

## 대규모 GPU 필요 후보

다양한 finding·modality·질문을 함께 학습하는 encoder–language 공동 post-training은 보존 후보로 남긴다. 단일 target의 음성 의미 보존과 폭넓은 적응의 관계를 비교할 수 있지만, 먼저 현재 진단과 강한 경량·모듈형 baseline으로 필요성을 확인해야 한다.

# 계획의 근거 (GPT 조사 노트)

## 핵심

기존 checkpoint 진단을 선택하되 질문을 좁혔다. 이번에는 병변 grounding의 일반적인 QA 전이를 주장하지 않고, **특정 finding의 음성과 더 넓은 Normal 판정의 구분이 적응 후 유지되는지** 확인한다. 이 구분에는 기존 RSNA의 세 category가 유용하다. 다른 질환의 영역 선택은 이번 자료로 충분히 검증할 수 없어 별도 미측정 축으로 남긴다.

이번 라운드는 파일·저장 결과·Git blob·공개 문헌을 읽었다. 코드 수정, 파일 생성, 모델 로딩, 실험 실행은 하지 않았다.

## 질문 1: 정답을 보장할 최소 자료

### RSNA의 정답 의미를 더 정확히 확인했다

원 논문은 No Opacity/Not Normal에 다른 opacity가 있을 수 있다고 설명한다. 또한 치유된 늑골 골절만 있는 영상은 Normal로 분류한 판독 예시가 있다. 따라서 ‘모든 opacity 부재’나 ‘어떤 이상도 전혀 없음’을 정답으로 만들면 오류다. 이번 target은 기존 prompt의 pulmonary opacity suspicious for pneumonia와 **RSNA 판독 규약에 따른 Normal 대 abnormal**로 제한한다. 임상적으로 확진된 폐렴이나 환자의 전반적인 건강 상태를 묻지 않는다. [RSNA 원 논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC8017407/)

`rsna_diag/prompts.py`의 기존 target은 이미 pulmonary opacity suspicious for pneumonia이므로 과거 정상 사용 검증과 충돌하지 않는다. `rsna_diag/rsna_data.py`는 Calculated 그룹의 세 category를 사용한다. `results/iter_010/manifests/gt_manifest.json`에서 기존 confirm은 opacity 400명, Normal 200명, NoOpacity/NotNormal 200명이다. 이를 후속 개발 자료로 전환한 기존 결정을 유지하며, 각 category 200명으로 구성한 최대 600명 진단을 만들 수 있다. 별도 validation 400명에서 개발용 36명을 분리할 수 있다.

### 다른 자료의 범위

- NIH 160명은 bbox가 없는 finding을 음성으로 쓸 수 없다. RSNA와 원천 자료가 겹치므로 외부 기관 평가도 아니다.
- 로컬 VinDr 10영상은 여러 finding의 bbox가 있지만 충분한 독립 평가 규모가 아니다. 공식 전체 자료는 credential·교육·DUA 조건이 있어 현재 접근 권한을 추정하지 않는다. [VinDr 공식 배포](https://physionet.org/content/vindr-cxr/1.0.0/)
- SCR manifest는 247 case지만 `results/iter_005/readiness.json`에 burned annotation과 mask 의미 미확정이 기록돼 있다. 영상 수가 충분하다는 이유로 anatomy 평가에 사용하지 않는다.
- SLAKE는 공식 사이트에서 저자 HF 저장소로 연결된다. 저장소에는 212MB imgs.zip, mask.txt와 train/validation/test JSON이 있다. 따라서 접근 가능한 의미별 영역 평가 후보는 존재한다. 다만 archive 내부의 실제 mask·질문 대응, 환자 식별과 MedGemma 사전학습 노출을 아직 검증하지 않았다. CT/MRI까지 섞으면 이번 단일 CXR 적응 진단에 도메인 변화가 추가된다. 이번에는 도입하지 않는다. [SLAKE 공식 안내](https://www.med-vqa.com/slake/), [저자 배포 파일](https://huggingface.co/datasets/BoKelvin/SLAKE/tree/main)

## 질문 2: 최소 요청 행렬과 해석

두 질문의 정답 쌍을 Q_O=폐렴 의심 opacity 존재, Q_A=RSNA 규약상 abnormal 여부로 정의하면 opacity=(yes, yes), Normal=(no, no), NoOpacity/NotNormal=(no, yes)다. 질문은 각각 독립 대화로 실행한다. 동일 영상의 질문 target이 달라지므로 단순 paraphrase 비교와 구별된다.

- 좌표 출력: 기존 base·B0 bbox와 C의 실제 bbox를 같은 metric으로 비교한다.
- 질문 target 구분: 세 checkpoint의 Q_O/Q_A 실제 생성으로 측정한다.
- 다른 target의 영역 선택: 이번에는 측정하지 않는다. abnormal의 위치 정답이 없으므로 bbox를 만들어내지 않는다.
- 제공된 근거 활용: 원본 영상을 유지한 base에 B0 예측 bbox 또는 GT bbox를 제공한다. 이 조건은 인터페이스와 task scope의 검사다. bbox가 존재한다는 정보만으로 opacity 답을 얻을 수 있어 공간 reasoning 증거로 해석하지 않는다.

plain yes/no와 JSON answer 형식을 개발 자료에서 점검하고, 고정 subset에서는 두 형식을 모두 비교한다. 형식 실패가 checkpoint 차이를 설명하면 시각 능력 손실로 해석하지 않는다. bbox []를 QA의 no로 파싱하지 않는다.

## 질문 3: 선행 연구·비교군·투자 결정

[Why Does Grounding Hurt Medical VQA? v2](https://arxiv.org/html/2604.27720v2)의 형식 rehearsal 및 crop 대조는 이전 조사에서 확인했다. 이번 재조회는 단일 target의 음성 의미 보존이라는 질문과의 차이를 확인하기 위해 수행했다. 단순 grounding/QA 점수 차이나 형식 분리는 이미 연구된 범위다.

이전 라운드에서 본문을 확보하지 못했던 [Localizing Before Answering](https://arxiv.org/html/2505.00744v1)의 데이터 생성 부분을 확인했다. HEAL-MedVQA는 VinDr bbox와 MIMIC에 적용한 detector 결과, anatomy mask의 관계에서 QA를 만든다. 따라서 모든 질환·영역 정답을 직접 판독한 자료로 일괄 취급할 수 없다. 이번에 큰 benchmark를 먼저 가져올 이유가 줄었다.

새로 확인한 [NAST v2](https://arxiv.org/html/2602.12498v2)는 contrastive medical VLM의 부정·긍정 문장 선택과 선택적 학습을 다룬다. 따라서 ‘의료 부정 이해’ 자체를 신규 주제로 주장할 수 없다. 이번 질문은 생성형 모델의 단일 target 적응 전후에 다른 target의 답변이 어떻게 달라지는지다. 그 차이가 새로운 방법으로 이어질지는 미확정이다.

모듈형 비교에는 기존 B0를 localizer로 사용하고 base reader에 원본 영상과 예측 bbox를 함께 준다. 이 비교는 동일 localizer 정보를 내부 적응과 외부 도구로 사용하는 선택을 진단한다. 강한 detector보다 우수하다는 주장을 하지 않으므로 이번 단계에서 detector를 새로 학습할 필요는 없다. 내부 grounding 방법 개발을 계속한다면 후속 계획에서는 같은 학습 자료의 detector/encoder+head 비교가 필요하다.

결과가 target별 능력 저하를 재현하면 일반 replay·다과제 SFT·모듈형 구성이 해결하는 범위를 다음 방법 질문으로 삼는다. 단순 형식 저하만 있으면 의미 보존 방법을 개발하지 않는다. 차이가 실질적으로 작으면 해당 가설의 투자를 보류하고 다른 의료 VLM 질문을 비교한다. 모든 결과를 다음 loss 탐색으로 연결하지 않는다.

## 질문 4: 코드·표본·실행 비용

`git status --short`는 기존 untracked `test_rsna_iter010_gpu.py`만 보였고 tracked diff는 없었다. HEAD는 `698c161f51ec098b1263ea8a5acf4d2870930e0b`다. 반입할 16개 파일 모두 해당 SHA의 blob과 현재 내용이 일치했다. 상대 import 의존성도 확인했다. 새 브랜치 기반 iter_006의 전체 SHA는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`이며 rsna_diag가 없다. 따라서 선별 반입 목록을 명시했다.

B0 seed17·29·43의 `results/iter_012/train/lr2e-4_s{seed}/epoch_05/adapter.pt`와 C의 `results/iter_014/full/C_lr2e-05/epoch_03/adapter.pt`는 각각 119,369,709 bytes로 존재한다. tensor digest 재검증과 실제 재로드는 Claude의 실행 조건이다. 기존 confirm_base에는 official_long/concise 각각 800요청, confirm_sft_seed17에는 concise 출력이 있다. 과거 결과를 새 protocol에서 생성한 것처럼 표시하지 않고 별도 provenance로 재사용해야 한다.

필수 수정은 동적 요청·evidence digest, 명시적 필수 파일 잠금, GPU 조회 실패 시 중단, worker당 여유 합산 및 완료 검사다. `generate.py`의 과거 lock_protocol NameError는 현재 수정돼 있다. 사용하지 않는 adapt_geo 수치 검사를 이번 진단의 선행조건으로 삼지 않는다.

180명 탐색에서 시작해 필요하면 600명으로 확대한다. 중요 category는 60→200명이다. paired 이진 차이의 discordance가 0.25라면 category 차이의 대략적인 95% CI 반폭은 12.7→6.9 percentage points다. 이는 설계용 근사이며 실제 환자 bootstrap으로 판단한다.

처리량은 새 질문에서 측정해야 한다. iter_014 짧은 생성의 GPU당 2 worker는 22.44 req/min이었지만 iter_012의 긴 base 출력은 4 worker 전체에서도 2.376 req/min이었다. 따라서 새 QA를 전자의 속도로 단정하지 않는다. 요청 유형별 pilot 실측으로 단계별 wall-clock을 계산하며 임의 시간 상한을 두지 않는다.

## 유지·보류

iter_009 한계 검증, iter_012 직접 SFT 개선, iter_014 현재 G 투자 중단을 유지한다. anatomy 전이·새 loss·reserve 사용은 보류한다. 이번 진단은 새 접근법이며 G 재시도가 아니다. 문헌은 조사 근거이며 아직 사용자 추천 대상은 아니다.

## 대규모 GPU 필요 후보

여러 finding·modality·질문을 함께 학습하면서 단일 target의 음성 의미를 보존하는 공동 post-training을 보존 후보로 둔다. 다만 이번 진단에서 문제와 단순 baseline의 범위를 확인하기 전에는 대규모 학습의 필요성을 주장하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_015/think/
