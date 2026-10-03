# 요약

- **이번에 할 일:** MARIO 판독 가능성 diagnostic의 자동 실행을 보류하고 임상 검증 자원의 가용 여부를 확인한다.
- **필요한 이유:** 공개 code와 원 주석의 대응, 환자·방문 연결을 확정하지 못했다. 이를 추정하면 판독 불가능과 복합 변화를 잘못 채점할 수 있다.
- **확인할 기준:** 원 주석 식별, 환자 단위 분리, 입력과 정답 근거의 범위, 강한 품질·pair 대조의 실행 가능성이다.
- **주의·다음:** 새로운 한계나 방법 효과는 관찰하지 않았다. `decision=ask_human`이며 아래 내용은 실행 보류 계획이다. 질문에 답하기 전 Claude 구현을 시작하지 않는다.

# Current Understanding

iter_054의 보정 후보 보류와 iter_055 앞선 라운드의 grounding 추가 학습 보류를 유지한다. 원 리뷰의 유효 관찰과 새 방법 투자 가치는 별개다.

이번에 확인한 TrajRAG 본문은 판독 불가능 사례를 제외한 3-class 평가다. 따라서 제안한 질문과 범위는 다르다. 그러나 공개 MARIO annotation에서 필요한 정답을 실제로 분리할 수 있는지는 미확인이다. 공개 loader의 필드 존재만으로 이 조건을 충족했다고 볼 수 없다.

# Strategy Check / 연구 방향 판단

중요한 능력은 시간 비교의 근거 부족을 실제 불변으로 잘못 확정하지 않는 것이다. 기존 적응 방법 개선은 중요한 잔여 실패의 근거가 부족하고, 기존 주변 진단 반복은 정보 이득이 약해 보류한다.

시간 비교 후보는 질문의 의미가 있으나 실행에 필요한 정답 연결을 확보하지 못했다. 이 상태에서 자료 감사만 별도 구현 반복으로 넘기지 않는다는 round_03 종료 조건을 적용한다. 이는 자료의 부재나 연구 가치 부재를 입증한 판단이 아니다.

다음 선택을 바꾸는 정보는 임상 판독 검증 자원의 가용 여부다. 없으면 공개 annotation만으로 정답이 완결되는 과제를 우선한다. 가능하면 구체적 전문과·검증 범위에 맞는 후보를 검토한다. 새로운 협력·주석 수집을 이미 승인된 것으로 취급하지 않는다.

# Hypothesis

후보 가설은 판독 불가능–불변 혼동이다. 영상 품질, 영상 간 대응, class prior와 label 통합이 경쟁 설명이다. 현재 실제 모델 출력으로 검증하지 않았다.

# Limitation Evidence / Correct Usage Checks

이 후보에 연결할 현재 목표의 observed/validated limitation은 없다. `limitation_ids=[]`를 유지한다. 기존 RSNA grounding 한계를 이 후보의 method 진입 근거로 사용하지 않는다.

재개에는 정확한 label mapping, Other의 원 주석 분리, 환자·eye·방문 연결, 판독자와 모델의 입력 범위 일치가 필요하다. 0~3 code의 의미를 빈도나 문헌 표현만으로 추정하지 않는다. 모델 confidence를 판독 불가능의 정답으로 사용하지 않는다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. TrajRAG의 calibration·abstention, MARIO 전용 pair classifier, OCT 품질 평가를 가까운 대안으로 둔다. 후속 방법은 직접 SFT·거부 supervision과 같은 annotation·입력 조건에서 비교해야 한다.

실행 경로를 선택하지 않았으므로 재사용 파일을 지정하지 않는다. 현재 코드와 이전 checkpoint·결과는 보존한다. iter_054의 gate·비용 집계 결함을 고치기 위한 별도 정비 반복도 발주하지 않는다.

# Proposed Experiment

이번에는 실험을 발주하지 않는다. 동작 확인·가능성 탐색·규모 확대·독립 확인 모두 미실행이며, 표본·seed·요청량을 임의로 채우지 않는다.

재개 조건은 정답과 독립 분석 단위가 확인되고, 강한 단순 대안과 구별할 한정 질문이 성립하는 것이다. 조건이 갖춰지면 별도 계획에서 표본·개입·metric·운영점·최소 가치 있는 차이·결과별 종료 행동을 고정한다. 자료 확보만으로 학습이나 본실험을 자동 시작하지 않는다.

# Implementation Tasks for Claude

현재 구현 발주 없음. `decision=ask_human`을 유지하고 다운로드·새 환경 구성·코드 수정·GPU 생성·학습을 시작하지 않는다. GOAL, 기존 계획·리뷰, limitation 상태를 수정하지 않는다. 완료된 iter_050 인계·감사를 반복하지 않는다.

# Evaluation (성공/실패 기준 포함)

- **진입 가능:** 원 주석과 환자 연결 및 필요한 입력 범위를 확인하고 공정한 대조를 구성할 수 있다. 별도 diagnostic 계획을 작성할 근거이며 연구 성공은 아니다.
- **진입 불가:** 원 주석 분리 또는 정답–입력 연결이 불가능하다는 근거가 확인된다. 해당 MARIO 설계만 보류한다.
- **현재 상태:** 필요한 공개 세부 정보를 확인하지 못한 불확정이다. 자료 부재·모델 실패·대안 충분성으로 바꾸지 않는다.

현재 결과로 확대나 방법 학습을 승인하지 않는다. 사람의 답변은 연구 자원과 다음 탐색 범위를 정하며 과학적 gate를 면제하지 않는다.

# Risks / Checks

이번 계획의 GPU 사용량은 0이며 이유는 실행 설계 미확정이다. GPU 최소 사용을 연구 목표로 삼지 않는다. 후속 실험에서는 OCT pair의 실제 peak 메모리와 처리량을 측정하고 두 GPU의 batch 확대 또는 복수 worker를 비교한다. 현재 미측정 비용을 다른 과제의 처리량으로 대신 계산하지 않는다.

공개 archive를 확인하지 못한 것을 비공개·권한 부족으로 단정하지 않는다. 임상 협력자를 확보할 수 있다는 답변도 annotation·자료 접근·독립 평가가 확보됐다는 뜻은 아니다.

대규모 GPU 필요 후보는 다기관 longitudinal volume과 판독 가능성 supervision의 공동 적응이다. 현재 필요성과 효과는 미검증이며 기존 자산과 조사 기록만 보존한다.

# 계획의 근거 (GPT 조사 노트)

# 이번 판단

MARIO 판독 가능성 diagnostic은 현재 실행하지 않는다. 마지막 라운드에서 가까운 선행의 평가 범위와 공개 loader는 더 확인했지만, 원 주석 분리와 환자별 연결을 확정하지 못했다. 자료에 해당 정보가 없다고 입증한 것은 아니다. 확인하지 못한 내용을 구현 담당의 추측으로 채우게 하지 않겠다는 판단이다.

# 직전 질문에 대한 답

## 1. CSV code와 원 주석의 대응

공식 Task 1 제출 문서는 여전히 prediction 0~3만 규정하며 의미 대응을 제공하지 않는다. 원 논문의 simplified label은 Reduced=0, Stable=1, Worsened=2, Other=−1이다. Other에는 Uninterpretable 2,303쌍과 Appeared and Eliminated 9쌍이 함께 들어간다. 따라서 공개 code 3을 곧바로 순수한 판독 불가능 정답으로 사용할 수 없다. [공식 제출 규약](https://raw.githubusercontent.com/YouvenZ/MARIO-Challenge-MICCAI-2024/main/Task%201/README.md), [MARIO 논문 §4](https://arxiv.org/html/2506.02976v1)

DF41의 실제 loader는 `label`, `case`, `image_at_ti`, `image_at_ti+1`을 사용한다. 이 파일에서는 label의 의미 변환이나 원 주석 분리 경로가 확인되지 않았다. 이는 전체 배포에 원 주석이 없다는 증거는 아니다. [공개 loader](https://raw.githubusercontent.com/pzhangwj/mario_challenge_code/master/utils/dataset.py)

## 2. 환자·eye·방문·판독자 연결

TrajRAG §3은 MARIO patient/eye identifier를 사용하고, non-evaluable 제외 후 68명·13,201쌍에서 patient-disjoint 분할을 구성했다고 명시한다. 식별자가 활용된 선행 근거는 확보했지만 이번에 공개 archive의 실제 필드와 연결 규칙을 검증한 것은 아니다. 원 논문에서 확인한 판독자의 인접 B-scan 탐색과 단일 pair 입력의 근거 범위 차이도 남는다. 공개 annotator별 label 보존 여부는 확인하지 못했다. [TrajRAG 본문](https://papers.miccai.org/miccai-2026-sat/paper/MedAgent_010.pdf)

공식 Zenodo는 Task 1의 train/val/test CSV와 archive 내부 readme를 안내한다. Task 1은 14개 multipart 파일이며 약 14 GB다. 이번에는 archive 내부를 읽지 못했다. GitHub directory/API 일부 조회도 실패했다. 이를 비공개 자료 또는 설치 불가능으로 해석하지 않는다. [공식 배포](https://zenodo.org/records/15270469)

## 3. 가까운 선행이 질문을 이미 해결했는가?

이번에는 이전에 열리지 않았던 TrajRAG PDF 본문을 읽었다. non-evaluable 사례를 제외하고 regressed/stable/progressed를 평가한다. 따라서 해당 논문은 원래 판독 불가능인 사례를 Stable로 확정하는 오류를 직접 평가한 근거가 아니다. 다만 calibration과 prompt-vote abstention은 이미 포함하므로 confidence 또는 prompt ensemble을 추가하는 것 자체는 차별성이 없다. 이 범위 차이가 새로운 방법의 필요성을 증명하지도 않는다. [TrajRAG §2–4](https://papers.miccai.org/miccai-2026-sat/paper/MedAgent_010.pdf)

DF41 저장소는 4-class fusion CNN과 실행 코드를 제공하지만 checkpoint는 포함하지 않는다고 명시한다. 이번에 실제 config와 loader를 확인했다. 미설치 때문이 아니라 label 의미와 현재 평가 정의의 연결이 미완료라 비교 실행을 발주하지 않는다. [공식 구현](https://github.com/pzhangwj/mario_challenge_code)

추가로 ROQUS의 원 논문 검색 결과에서 MARIO의 판독 불가능 subset에 대한 OCT 품질 평가를 확인했다. 이는 개별 영상 품질을 약한 자체 prompt만으로 대조해서는 안 된다는 근거다. 본문 직접 열기는 접근 검사로 실패했고, 코드·checkpoint·원 주석 ID 공개 여부는 확인하지 못했으므로 실행 가능한 baseline으로 확정하지 않았다. [ROQUS 원 논문](https://pmc.ncbi.nlm.nih.gov/articles/PMC12265595/)

# 기존 기록과 보존

`agent/runs/iter_055/think/round_03.json` 원문, round_01의 인계·자산 확인 기록, `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/runs/iter_054/review.md`를 확인했다. 이전 라운드에서 읽은 적응 원 리뷰의 판단은 유지한다. `research/`의 현재 `git status --short`는 비어 있다. 새 재사용 경로가 없어 파일 반입이나 checkpoint 승인을 요청하지 않는다.

기존 validated RSNA grounding 한계를 OCT 판독 가능성의 근거로 전용하지 않는다. 새 limitation을 등록하지 않는다. iter_050의 완료된 인계·감사도 반복하지 않는다. 파일 수정·생성·실험은 수행하지 않았다.

# 남은 결정

이번 후보를 바로 실행할 근거는 부족하며, 현재 탐색에서 실행 가능한 다음 실험을 확정하지 못했다. 모든 의료 VLM 연구 대안이 소진됐다는 뜻은 아니다. 마지막 라운드 지시에 따라 불완전한 구현 계획을 강행하는 대신, 임상 검증 자원의 가용 여부를 묻고 다음 탐색 범위를 정한다. 공개 데이터 조회나 격리 환경 구성의 재승인을 요청하는 것은 아니다.

# 대규모 GPU 필요 후보

다기관 longitudinal volume과 판독 가능성 supervision을 함께 사용하는 encoder–projector–decoder 적응은 장기 후보로 보존한다. 현재 그 필요성이나 우위는 미검증이며, 두 RTX 3090에서 가능한 직접 SFT·pair head·품질 gate보다 우선하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_055/think/
