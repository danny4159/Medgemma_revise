# 요약

- **이번에 할 일:** MediConfusion에서 MedGemma 1.5의 단일 영상 생성과 likelihood scoring, 선택지 순서·text-only prior 보정을 비교한다.
- **필요한 이유:** 낮은 답변 정확도만으로 시각 판별 실패와 답변 선택 문제를 구분할 수 없다. 강한 단순 대안 이후 남는 격차가 다음 투자 대상이다.
- **확인할 기준:** 영상별 상대 점수의 판별 신호, 실제 단일 영상 선택의 잔여 오류, 자료 의존성과 정답 모호성을 함께 평가한다.
- **주의·다음:** 전체 benchmark는 개발 자료다. 상대 평가 영상을 쓰는 점수 분석은 실용 해법이 아니며, 양성 결과도 학습이나 contribution을 자동 승인하지 않는다.

# Current Understanding

판단의 기준은 `agent/runs/iter_054/think/round_01.json`과 이번 조사 노트다. iter_053의 oracle 183/192 실패와 E/F 미실행 판정은 유지한다. iter_048의 공동 형식 학습 효과와 모듈형 대안 이후 투자 보류, iter_052의 CT 자료·기술 gate 실패도 유지한다. iter_050 담당 전환의 일회성 인계는 후속 반복에서 처리됐으므로 반복하지 않는다. 현재 구현 담당은 Claude다.

MediConfusion은 176쌍의 같은 질문·선택지와 서로 다른 정답을 제공한다. 공식 metadata에서 영상 재사용과 PMC 문서 공유를 확인했다. 고유 영상·문서·연결 성분 수는 출력 전에 정확히 집계한다. 환자 ID는 확인되지 않았으므로 환자 독립성을 주장하지 않는다.

# Strategy Check / 연구 방향 판단

round_01에서 기존 방법 개선, 교정·CT 보완, 자연 영상쌍 진단을 비교했다. 이번에는 그 선택을 유지하며 광범위한 전략 조사를 반복하지 않는다.

중요한 능력은 동일 질문에서도 실제 영상에 따라 답을 바꾸는 능력이다. 기존 grounding에서는 직접 SFT와 모듈형 적응이 큰 차이를 설명했으며, 현재 새 loss의 필요성은 약하다. 새 후보는 실제 답변에서 영상 신호와 선택의 관계를 저비용으로 검사할 수 있다.

같은 `language-conditioned-grounding` track의 누적 이력을 유지한다. iter_040~053의 유효 비교와 준비·실행 실패를 구분하며, 이번 질문이 다른 benchmark라는 이유로 체류 비용을 초기화하지 않는다. 해결된 것은 기존 일부 형식·적응 차이의 설명이다. 남은 질문은 단일 영상의 단순 선택 규칙 이후에도 활용 가능한 판별 신호가 남는가다.

MediConfusion 점수 재현이나 prior 보정의 적용만으로 새 기여를 주장하지 않는다. 가까운 DoubleTake는 외부 reference와 두 평가 영상을 사용하는 단계가 있다. 이번에는 상대 평가 영상 없이 작동하는 조건을 평가하고, pair 정보의 이점은 별도 진단으로 표시한다. 단순 대안이 충분하거나 상대 순서 신호가 약하면 이 후보의 투자를 종료한다.

# Hypothesis

H1: 영상별 A/B margin의 상대 순서는 정답 방향과 일치하지만 단일 영상의 선택 문턱은 두 영상에 같은 답을 내도록 할 수 있다.

경쟁 설명은 선택지 위치 편향, text-only 답변 prior, 생성 형식 오류, 상대 순서 자체의 실패, benchmark 정답 모호성이다. GD·PS·순서 평균·prior 차감은 기존 단순 대조군이다. 상대 순서가 맞아도 내부 표현이 충분하다거나 단일 영상에서 같은 개선을 얻을 수 있다고 결론 내리지 않는다.

# Limitation Evidence / Correct Usage Checks

현재 이 과제의 로컬 observed/validated 한계는 없다. `limitation_ids=[]`, `experiment_role=diagnostic`, `method_stage=none`을 유지한다. 다른 데이터의 validated grounding 한계를 이번 학습 진입 근거로 빌리지 않는다.

MedGemma는 기존 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, eval, greedy로 고정한다. 공식 processor의 단일 영상 chat template를 사용한다. 모델·processor revision, package version, template hash, image processor 설정을 보존한다.

원본 영상을 RGB로 처리해 공식 processor에 전달한다. grounding용 square padding, bbox overlay, 임의 crop은 적용하지 않는다. 원본 mode·크기·file/pixel hash를 기록한다. 비표준 mode는 출력 전에 명시적으로 처리·검증하며 조용한 정규화를 하지 않는다. text-only는 텍스트가 동일하고 영상 content만 제거하며 image token·pixel tensor가 없어야 한다.

형식 invalid는 오류로 보존한다. MC가 완벽히 정답을 복사해야 한다는 oracle gate를 만들지 않는다. 기술 gate는 입력·scoring·완료 무결성에 적용하며 내용상 오답은 연구 관찰이다.

# Contribution Path / Baselines / Reuse

가장 가까운 자료·평가는 [MediConfusion](https://github.com/MShahabSepehri/MediConfusion), 추가 입력을 쓰는 가까운 방법은 [DoubleTake](https://arxiv.org/html/2602.02894v1)다. 이번에 DoubleTake의 미실행을 성능 열세로 표현하지 않는다. 외부 bank·caption 기반 retrieval·pair adjudicator가 없는 입력 범위의 진단이다.

후속 방법을 검토하려면 이번 유효 리뷰 외에도 평가 자료와 분리된 학습 자료, 강한 직접 SFT, 동일 비용의 단순 보정, 외부 확인 계획이 필요하다. 새로운 loss·reference bank·encoder 학습은 이번 범위 밖이다.

새 브랜치는 자동 승인 기반을 사용한다. 필요한 여섯 파일은 `reuse_assets`의 실제 SHA에서 반입한다. 현재 작업 파일과 해당 blob의 일치를 확인했다. 사용 범위는 `generate.load_model/build_inputs/build_inputs_text/generate/env_info`, `pg43_run`의 순수 digest·record I/O·부분 행 보존 함수, `queue_lock`의 lock 기능이다. `generate`의 기존 CLI, `load_image`, adapter 경로와 `pg43_run`의 기존 protocol/worker/launcher는 실행하지 않는다. 따라서 해당 미사용 경로의 lazy dependency와 PadChest 설정은 추가 반입하지 않는다.

새 scoring 작업을 처리할 `mc54_*` 모듈에서 기존 저수준 기능을 호출하고, 이번 자료·요청·stage에 맞는 검증을 구현한다. 기존 파일을 전역 monkeypatch하거나 과거 실행기의 의미를 바꾸지 않는다. iter_053의 gate·재개 비용·평가 봉인 문제는 새 실제 실행 경로에서 해결한다.

# Proposed Experiment

## 1. 자료 고정

공식 `data/dataset.json`, `data/image_dict.json`, `configs/prompts/answering.json`, 평가 소스의 revision과 digest를 보존한다. 공식 176 pair ID와 `question/option_A/option_B/im_*_correct`를 사용한다. AI_*로 바꾸지 않는다.

영상 확보는 PMC 원천 archive의 해당 figure member만 안전하게 추출한다. 공식 download.py의 디렉터리 삭제 동작은 사용하지 않는다. 기존 자산을 먼저 검색하고 정확한 출처·hash가 같으면 재사용한다. 외부 다운로드·환경은 results 전용 경로를 사용하며 hf_cache를 수정하지 않는다. 자료의 이용 조건과 원천 연결을 기록한다.

pair→영상→PMC 대응, 중복 key, ID 충돌, 동일 pixel, 공유 문서, 동일 질문·선택지의 반복을 검사한다. 같은 영상·PMC·정확 pixel을 공유하는 pair를 연결하여 dependency component를 만든다. 크기 분포와 최대 component 비중을 보존한다.

caption·정답·AI_*·category·pair 위치·파일명 의미는 모델 입력에 넣지 않는다. 추론 manifest에는 불투명 request ID, 대상 영상, 질문·선택지만 전달한다. pair 연결과 정답은 평가 manifest에만 둔다.

출력 전에 전체 metadata의 명백한 caption–선택지 모순 의심을 기록한다. 이는 임상 재판독이 아니다. 의심 항목을 원 점수에서 조용히 제거하거나 정답을 바꾸지 않는다. 전체 공식 집합과 사전 의심 항목 제외 민감도를 함께 보고한다. 실제 영상을 확인하지 않고 시각 감사 완료로 쓰지 않는다.

## 2. 동작 확인

seed 54의 ID hash 순서로 category를 가능한 한 포함하는 12쌍을 기술 표본으로 정한다. 12쌍은 두 영상·두 순서·text-only·두 scoring 경로 및 실행 재개를 검사하기 위한 표본이며 효과 탐색의 통계 표본이 아니다. 원본 크기가 가장 큰 영상과 답변 token이 가장 긴 항목은 자원 검사에 추가 포함한다.

이 표본에서 원본 영상이 실제 rendering되는지, 공식 processor와 입력 tensor가 일치하는지 확인한다. parser·token 경계·batch·worker 설정만 검증하며 정확도에 따라 prompt나 scoring 규칙을 선택하지 않는다. 같은 조건으로 생성된 기술 표본 출력은 본집계에 재사용하고 독립 test라고 부르지 않는다.

## 3. 고정 비교 조건

MC와 GD의 공통 텍스트는 다음 형식이다.

`Based on the image, choose the correct option for the following question.\nQuestion: {question}\nA: {option_A}\nB: {option_B}\nAnswer with the option's letter from the given choices directly. Your answer should be just one letter.\nAnswer:`

각 pair에서 두 영상 각각에 원래 순서와 교환 순서를 적용한다. 동일 질문의 text-only는 순서별 한 번만 실행하고 두 영상의 독립 관측으로 중복 계산하지 않는다.

- **MC:** 자유 greedy 생성. cap 128→512→2048은 비EOS일 때만 동일 입력으로 재시도한다. 원시 token·EOS·각 attempt를 보존한다. 공식 manual parser 결과와 whole-string A/B parser 결과를 함께 기록한다. whole-string parser는 공백·고정 wrapper·문장부호만 허용하고 설명 속 문자를 찾아 정답으로 만들지 않는다.
- **GD:** 공통 prompt 다음 A/B의 log probability 차이. 실제 tokenizer에서 두 문자가 단일 token인지 검증한다. 단일 token이 아니면 전체 문자 continuation의 합 log likelihood를 사용하고 공식 GD와의 차이를 명시한다. canonical option_A 기준으로 교환 순서의 부호를 되돌린다.
- **GD-avg:** 두 canonical margin의 산술평균으로 독립 선택한다.
- **GD-cal:** 순서별 image margin에서 동일 text-only margin을 계수 1로 뺀 뒤 평균한다. 계수·문턱은 학습하지 않는다.
- **PS:** 질문만 있는 user turn 다음에 각 원문 option을 assistant continuation으로 넣고, 답변 내용 token의 평균 log likelihood를 비교한다. 질문·template·EOS token은 평균에서 제외한다. PS는 선택지 순서를 prompt에 넣지 않으므로 중복 실행하지 않는다.
- **PS-cal:** PS의 canonical score 차이에서 동일 질문의 text-only 차이를 계수 1로 뺀다.

MC/GD의 원래·교환 순서, GD-avg, GD-cal, PS, PS-cal이 사전 고정 비교 집합이다. scoring의 정확한 동점은 abstain으로 처리한다. 수치 허용오차 안의 거의 같은 점수는 별도로 표시하고 작은 수치 차이를 강한 판별 신호로 해석하지 않는다.

## 4. 상대 순서 진단

추론 완료 후 평가 코드만 두 영상의 GD-avg margin을 연결한다. 정답 A 영상의 margin이 정답 B 영상보다 높으면 orientation=1, 낮으면 0, 동점이면 0.5로 정의한다. 평균을 O라 한다. 이 값은 두 영상의 점수와 서로 다른 정답이라는 구조를 이용한 진단이다. 무작위 방향의 기준은 0.5이며 독립 무작위 답변의 set accuracy 0.25와 혼동하지 않는다.

PS의 orientation은 보조 분석이다. GD-cal은 pair 공통 text margin을 빼므로 orientation이 GD-avg와 같아야 한다. 이 불변성은 구현 회귀 검사다. 영상 없는 같은 질문의 orientation은 정확히 0.5여야 한다.

## 5. 가능성 탐색과 규모

작은 효과 표본의 결과에 따라 나머지 자료를 선택하지 않는다. 전체 공식 176쌍이 작고 반복 영상으로 독립 표본은 더 작으므로, 기술 검사를 통과하면 고정 조건의 전체 개발 평가를 한 번 수행한다. 학습률·seed·prompt 후보 탐색은 없다.

영상 누락·손상은 대체 pair로 채우지 않는다. 확보된 부분 결과는 보존하되 미확보 pair의 가능한 결과를 포함한 최악/최선 범위를 보고한다. 완전 자료 또는 그 범위에서도 동일한 투자 판단이 유지되는 경우에만 양성 기준을 검토한다. 독립 확인과 학습 확대는 이번에 실행하지 않는다.

# Implementation Tasks for Claude

1. `results/iter_054/`에 source, data, protocol, tests, raw, eval, resource 산출물을 분리한다. 원본 source·영상·이전 결과를 덮어쓰지 않는다.
2. metadata와 안전한 figure 확보·연결 검사를 구현한다. inference/evaluation manifest를 분리하고 모든 요청을 잠긴 source에서 재구성해 대조한다.
3. 기존 모델·chat·생성 함수를 재사용하고 GD/PS scoring을 추가한다. token 경계는 실제 chat 문자열과 tokenizer 결과로 검증한다. 공식 PS의 문자열 token 검색·첫 token 제거를 복사하지 않는다.
4. 동일 입력에서 teacher-forced 계산과 token-by-token autoregressive log probability를 비교한다. 질문에 답변 문자열이 이미 등장하는 fixture, 여러 token 답변, punctuation, A/B 교환, text-only, EOS 제외를 검사한다.
5. 실제 launch가 필수 자료·기술 근거와 hash를 검증하도록 한다. generic run=true나 completion 존재만으로 진행하지 않는다. 새로운 파일은 protocol 잠금 전에 준비한다.
6. lock·요청별 claim·worker별 파일을 재사용해 생성과 scoring을 저장한다. worker mapping을 바꾼 실제 중단·재개 및 동일 요청의 중복 방지를 검사한다. 완료 요청도 현재 입력·코드와 대조한다.
7. raw에서 별도 구현으로 metric·orientation·bootstrap을 재계산한다. raw/code/protocol digest에 연결된 report·verifier·decision을 원자적으로 봉인한다.
8. 보고서에 실제 자료 수, 고유 영상·문서·component 수, 불완전 자료, 정답 의심, 실제 요청/forward/재시도 수, 비용과 투자 판정을 구분한다.

## GPU 배치·시간·재개

실행 직전 `nvidia-smi`와 상속된 허용 장치를 확인한다. 여유가 큰 GPU부터 사용하고 논리/물리 index와 UUID를 기록한다. 우선 두 GPU에 worker 하나씩 배치한다. 기술 표본에서 GPU당 두 worker 또는 scoring batch 확대 중 유망한 하나를 비교한다. 전체 요청/분, 긴 답변 PS 지연, GPU별 실제 peak, CPU/RAM/I/O, 오류와 출력 정합성을 기록한다.

모델 bf16 8–10GB는 참고값이다. processor가 만든 실제 image token과 PS full-sequence logits 메모리를 포함해 측정한다. 같은 GPU의 모든 worker peak와 다른 프로세스 점유에 worker당 2GB 여유를 더해 용량 이내일 때만 증설한다. scoring logits는 필요한 위치를 중심으로 저장하고 전체 vocabulary tensor를 결과에 기록하지 않는다.

최대 기본 작업량은 MC 1,056건, GD 1,056건, PS 후보 forward 1,056건이다. MC 첫 단계 logits 재사용은 별도 forward와 일치 검증 후에만 허용한다. 조건별 성능을 보기 전에 실행 구성을 확정한다.

iter_053의 448건/437초를 MC에 단순 적용하면 약17분이다. 이는 영상 크기·출력 길이가 다른 참고 환산이다. 본실행 전 실제 MC/GD/PS 처리량으로 `남은 작업량/측정 처리량 + loading`을 계산하고 자료 확보·검증 비용을 별도 기록한다. 이 수치를 timeout으로 사용하지 않는다.

각 요청의 완료를 저장하고 launch attempt별 시작·loading·종료·GPU 구간을 append한다. generation 구간 합집합과 loading 포함 점유 구간은 동일 attempt 범위에서 비교한다. 비정상 종료의 관측 비용은 하한으로 표시한다. OOM은 batch/worker를 낮춰 재개하며 과학적 조건을 바꾸지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표와 불확실성

각 고정 baseline의 individual accuracy, set accuracy S, invalid/abstention, image coverage, valid-pair coverage, 전체 pair 분모 same-answer 비율, 공식 valid-pair 조건부 confusion을 보고한다. invalid는 전체 정확도의 오답이다. accuracy와 비용은 함께 보고하되 단회 비용으로 CI를 만들지 않는다.

일차 진단은 GD-avg orientation O와 `G = O − max_b S_b`다. max는 사전 고정한 전체 baseline 집합에 대해 계산한다. 선택된 최고 baseline을 독립 검증된 방법이라고 부르지 않는다. bootstrap마다 max를 다시 계산하여 선택을 반영한다. pair 재사용으로 인한 의존성은 공유 영상·PMC·pixel의 연결 성분 단위 bootstrap 10,000회, seed 54로 반영한다. pair 가중 평균을 유지한다.

component 수·최대 비중과 leave-one-component-out 결과를 함께 제시한다. component가 20개 미만이거나 하나가 pair의 20%를 넘으면 bootstrap CI는 탐색적 보조로만 제시하고 이를 근거로 방법 투자 양성을 선언하지 않는다. 이는 실행 gate가 아니라 추론 범위 제한이다. 전체 176개가 독립이라는 이상적 경우에도 단일 비율의 최악 표준오차는 약3.8 pp이며, 실제 의존성은 정밀도를 더 낮출 수 있다.

## 양성: 다음 최소 방법 시험의 검토 가치

다음 조건을 모두 요구한다.

- 기술·자료·평가 무결성이 유효하다.
- O≥0.70이고 cluster 95% CI 하한이 0.50보다 크다.
- G≥0.15이고 cluster 95% CI 하한이 0.05보다 크다.
- GD-avg의 individual accuracy가 같은 text-only 순서 평균보다 최소5 pp 높고 차이의 CI 하한이 0보다 크다.
- 사전 정답 의심 항목 제외와 leave-one-component-out에서 효과 방향이 유지되며, 위 component 추론 제한에 걸리지 않는다.

15 pp의 격차는 176쌍에서 약26쌍 규모다. 좁은 점수 변화가 아니라 새로운 학습 투자를 검토할 만큼 큰 잔여 기회를 요구하는 탐색 기준이며 임상 성능 기준은 아니다. 양성이어도 pair 정보 없이 같은 개선을 얻는 방법은 아직 없다. 다음 리뷰는 별도 학습 자료와 직접 SFT를 대조하는 최소 방법 설계의 가치만 판단한다.

## 단순 대안으로 설명되는 결과

어떤 고정 단일 영상 baseline이 원래 순서 MC보다 set accuracy를 10 pp 이상 개선하고 paired 차이의 CI 하한이 0보다 크며, O와의 잔여 차이 점추정이 5 pp 이내이면 단순 대안이 이번 격차를 상당 부분 설명한다고 기록한다. 이 효과는 약18쌍 규모에 해당한다. 새 보정 방법의 투자를 종료하고 baseline을 보존한다. 다른 임상 과제의 충분성을 주장하지 않는다.

## 음성·불확정·실행 실패

O의 CI 상한이 0.70 미만이거나 G의 CI 상한이 0.15 미만이면 현재 큰 상대 신호–선택 격차 가설에 필요한 근거가 부족하다고 판단하고 해당 보정 후보를 보류한다. 낮은 scoring 점수는 encoder 병목의 증명이 아니다.

나머지는 불확정이다. 전체 자료를 이미 사용했으므로 prompt·seed·pair 추가로 자동 연장하지 않는다. 정답 모호성이나 component 의존성이 남아도 별도 자료 감사 반복을 자동 발주하지 않는다. 새 외부 근거가 생길 때만 별도 계획으로 재개한다.

scoring alignment·입력·자료 대응·완료 연결 오류가 있으면 실행 실패로 구분한다. 명확한 구현 오류의 영향을 받는 요청만 고쳐 재측정하며 기존 출력과 수정 전 코드를 보존한다. 통계 결과를 보고 문턱이나 표본을 바꾸지 않는다.

# Risks / Checks

- benchmark label은 독립 임상 gold가 아니다. 낮은 점수를 일반 의료 판독 결함으로 확대하지 않는다.
- 반복 영상·문서와 공개 자료의 사전학습 노출을 통제했다고 주장하지 않는다. ROCO의 원 train/test 이름은 이번 독립 분할을 의미하지 않는다.
- 전체 집합은 개발용이다. 기술 표본을 포함한 결과를 독립 확인이라고 부르지 않는다.
- pair ranking은 두 평가 입력의 점수를 사용한다. 이를 단일 영상 정확도 개선이나 실용 비용 우위로 보고하지 않는다.
- prefix 점수는 답변 길이 정규화와 template에 민감하다. 평균·합 log likelihood를 모두 저장하되 합 점수는 보조 분석이며 결과에 따라 주지표를 교체하지 않는다.
- parser가 모호한 설명에서 A/B를 추출해 가짜 개선을 만들지 않도록 공식 parser와 엄격 parser의 차이를 보고한다.
- scoring 수치 차이와 batch 차이는 실제 token 정합성·독립 계산으로 검증한다. threshold 근처 항목은 수치 민감도를 표시한다.

## 대규모 GPU 필요 후보

다양한 modality의 판별 영상–질문 자료로 visual encoder·projector·decoder를 공동 적응하는 방향은 장기 후보로 보존한다. 현재 encoder 원인이나 공동 적응 필요성은 확인되지 않았다. 이번 단일 영상 진단과 강한 단순 대안의 결과가 먼저다.

# 계획의 근거 (GPT 조사 노트)

# 새로 확인한 것

`agent/runs/iter_054/think/round_01.json` 원문을 읽고 남은 네 질문에 집중했다. GOAL·GPT_USAGE_POLICY·LIMITATIONS 관련 내용과 iter_053 원본 리뷰를 대조했다. 기존 전략 보류를 바꿀 근거는 발견하지 않았다.

## 1. 자료 구조와 분석 단위

공식 `dataset.json`에는 `im_1/im_2`, local ID, question, option_A/B, 정답, caption, category, AI_* 필드가 있다. 공식 evaluator는 AI_*가 아닌 question/option_A/B를 사용한다. 같은 ROCO 영상이 여러 pair에 반복되는 것을 실제 항목에서 확인했다. 따라서 176쌍·352항목을 352개 독립 영상 또는 환자로 부르면 안 된다. `image_dict.json`은 ROCO 경로를 local ID·PMC archive·figure member에 연결하며 동일 PMC의 여러 figure도 존재한다. 전체 고유 영상 수와 연결 성분 수는 이번 조회에서 정확히 집계하지 않았고 구현의 출력 전 manifest 검사로 확정한다. [공식 metadata](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/data/dataset.json), [영상 출처 대응](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/data/image_dict.json)

metadata에는 caption과 질문·선택지의 대응이 명확하지 않은 항목도 보인다. 예를 들어 10022는 caption의 병변 소실 서술과 선택지의 enhancing lesion 사이에 해석 문제가 있다. 이를 영상 정답 오류로 확정하지 않는다. 원 정답은 유지하고 출력 전 의심 항목을 기록하며 민감도 분석으로 분리한다. 이번 자료를 독립 임상 gold로 취급하지 않는다.

공식 다운로드 스크립트는 save_path가 존재하면 삭제한다. 그대로 실행하지 않고 PMC 원천 자산을 새 결과 경로에 안전하게 확보해야 한다. shell의 읽기 전용 원격 조회는 DNS 오류였지만 web 조회로 metadata와 소스 원문을 확인했다. 실제 영상 다운로드 성공 여부는 아직 미검증이다. [다운로드 원문](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/scripts/download.py)

## 2. 공식 scoring의 의미

공식 MC는 생성 답변의 문자를 parser로 읽는다. GD는 마지막 위치의 A/B 점수를 비교한다. 확인한 LLaVA PS 구현은 답변 token 확률의 기하평균을 비교한다. MedGemma에는 모델별 template와 token 경계 검증이 필요하며 기존 구현의 token slicing을 복사하면 안 된다. 이번 PS는 같은 수학적 점수를 평균 log likelihood로 계산하는 MedGemma 이식이다. [모델별 scoring](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/Models/llava.py)

공식 confusion은 둘 다 valid인 pair를 분모로 사용한다. invalid 증가가 confusion 감소로 보이지 않도록 전체 pair 분모의 same-answer 비율, valid-pair 조건부 confusion, coverage를 함께 보고한다. MC와 GD의 prompt를 같게 맞춘 비교는 공식 leaderboard의 완전한 재현이 아니라 통제된 이식으로 명시한다. [공식 evaluator](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/utils/answering.py), [공식 prompts](https://raw.githubusercontent.com/MShahabSepehri/MediConfusion/main/configs/prompts/answering.json)

## 3. DoubleTake와의 경계

DoubleTake의 pair adjudicator는 두 평가 영상과 각 evidence를 함께 받고, 서로 다른 답을 강제하지는 않는다. 따라서 선행을 강제 정답 배정 규칙이라고 설명하면 부정확하다. 그러나 단일 영상 조건보다 많은 정보를 받는다는 차이는 남는다. 이번에는 retrieval bank나 DoubleTake 전체를 재현하지 않으며 우월성을 주장하지 않는다. 단일 영상의 단순 scoring 이후에도 문제가 남는지 먼저 판단한다. [DoubleTake §3.3](https://arxiv.org/html/2602.02894v1)

## 4. 실행과 재사용 판단

현재 HEAD는 `7217b7045f48f95d8dc9b750544634e1c28d4f5c`이며 clean status다. 선택한 여섯 파일의 blob과 현재 파일을 byte 비교해 일치 확인했다. `generate.load_image`는 square padding을 수행하므로 이번에는 호출하지 않는다. 모델 로딩·chat 구성과 검증 가능한 파일/lock 함수만 사용한다. 공식 MedGemma 사용 예제의 단일 영상 chat 구조를 기준으로 새 입력 경로를 대조한다. [MedGemma 공식 카드](https://huggingface.co/google/medgemma-1.5-4b-it)

iter_053의 재개 비용·gate 연결·평가 봉인 결함은 실제 선택한 실행 경로에서만 해결한다. 교정 parser나 E/F 평가기를 정비하지 않는다. 새 소스·결과는 이번 반복 경로에 저장하며 과거 결과를 수정하지 않는다.

# 결론

고정 benchmark를 개발용으로 한 번 평가하는 diagnostic을 실행한다. 낮은 set accuracy를 확인하는 데 그치지 않고, 단순 baseline 이후의 상대 순서 신호와 실제 선택 간 격차를 판정한다. 전체 자료의 반복 의존성이나 정답 불확실성이 결정을 막으면 후보를 보류한다. 새 학습·자료 확대·추가 사고 라운드는 이번에 승인하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_054/think/
