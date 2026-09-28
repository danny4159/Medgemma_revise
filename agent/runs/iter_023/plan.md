# 요약

- **이번에 할 일:** RSNA bbox SFT의 개선이, 지정 사분면에 opacity bbox의 중심이 있는지 묻는 새 질문에도 이어지는지 확인한다.
- **필요한 이유:** 기존 실험은 bbox 출력과 영상 전체의 Q_O/Q_A를 평가했다. 위치가 실제로 답을 바꾸는 질문의 전이는 아직 확인하지 않았다.
- **확인할 기준:** 동일 입력의 base/SFT 직접 답변, 예측 bbox+규칙, bbox reader를 비교한다. 형식과 지시 해석을 먼저 확인하고 환자 단위 paired 불확실성을 보고한다.
- **주의·다음:** 이번은 개발 자료의 기하 질의 진단이다. 새 학습·임상 reasoning 주장·reserve 개방은 포함하지 않는다. 결과에 따라 전이 재현, 구체적 활용 단절의 후속 진단, 외부 연결로 충분한지 중 하나를 판단한다.

# Current Understanding

iter_012의 직접 LoRA SFT는 유효한 출발점이다. 확인 양성 400명의 F1@0.3은 base official 0.1650, SFT 세 seed 0.6308–0.6528, prior_set 0.4243이었다. 이는 한 데이터셋의 bbox 개선이며 일반적 공간 이해의 증명은 아니다.

이미 답한 질문은 다음과 같다. iter_013–014에서는 특정 추가 loss의 이득이 입증되지 않았다. iter_015–016에서는 큰 QA 저하의 상당 부분이 형식 효과였다. iter_017에서는 전역 질문에 좌표를 추가해도 개수 전달보다 정답 쌍이 개선되지 않았다. 당시 질문에는 위치가 필수적이지 않았다.

이번에 새로 확인할 것은 **같은 영상·같은 소견에서 질문 영역이 달라질 때 기존 SFT가 올바른 답을 직접 생성하는가**이다. 예측 bbox를 외부 규칙으로 사용하면 좋아지는데 직접 답변은 좋아지지 않는 경우와, 두 경로 모두 좋아지는 경우를 구분한다.

사용자 보완에 따라 GOAL·기준 모델·기존 성과와 자산을 유지한다. iter_022 longitudinal 계획, MRI F139, 기존 reserve, 새 loss·추가 학습은 보류한다. iter_022는 사용자 재계획으로 보존된 기록이며 실패가 아니다. 기존 confirm은 후속 개발에 사용됐으므로 이번에도 개발 자료로 취급한다.

# Strategy Check / 연구 방향 판단

중요한 능력은 위치 supervision으로 얻은 정보를 새로운 판단에 재사용하는 능력이다. 이 결과는 의료 VLM post-training에서 supervision을 어떻게 구성할지와 내부 학습의 추가 가치에 연결된다.

1. 현재 grounding 개선은 추가 bbox 점수를 얻을 수 있지만, 사용자가 우선한 미확인 전이를 설명하지 못한다.
2. 기존 checkpoint 진단은 이미 개선된 localizer와 원시 출력이 있어 추가 학습 없이 직접·외부 활용을 비교할 수 있다. 현재 정보 이득이 가장 크다.
3. 다른 의료 질문은 자료·소견·입력 구성을 동시에 바꾼다. 현재 우선순위를 대체할 근거가 없어 보류한다.

이번 선택은 사용자 보완과 iter_023 사고 라운드 01의 전략 판단을 구체화한 것이다. 영역 QA가 이미 알려진 과제라는 점을 인정한다. 유효한 정답을 만들 수 없거나 형식·지시 문제만 측정하면 전이 실패로 결론 내리지 않는다. 단순 규칙이 충분히 잘 작동하는 결과도 후속 내부 학습의 필요성을 판단하는 진전이다.

# Hypothesis

- H_transfer: bbox-only 직접 SFT B0는 미학습 사분면 질문에서도 M0보다 환자별 네 답의 정확도를 높인다.
- H_external: B0 bbox를 외부 규칙으로 사용하면 M0 bbox보다 질문 정확도가 높아진다. 이는 이번 기하 질문에 필요한 위치 정보가 개선됐는지를 확인한다.
- 경쟁 설명: 직접 답변의 차이는 형식 순응, 사분면 지시 해석, 답변 prior, 숫자 해석 또는 실제 위치 정보 활용의 차이일 수 있다.

H_external이 지지되더라도 H_transfer를 자동 지지하지 않는다. 두 가설의 불일치도 내부 표현의 정보 소실이나 임상 reasoning 결함을 바로 뜻하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`의 validated 범위와 iter_009·012 원본 리뷰를 사용한다. 새 질문의 전이 실패는 아직 관찰되지 않았다. 기존 QA 형식 및 evidence interface 주장은 observed 범위로 유지한다.

모델은 `google/medgemma-1.5-4b-it`, revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`로 고정한다. bf16·greedy·공식 chat template·값 보존 전처리를 유지한다. 보존된 공식 notebook `results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb`의 messages 구조와 실제 D 입력의 input_ids·pixel_values를 대조한다. 공식 원문 출처와 로컬 hash를 기록한다.

출력 길이는 기존 1000→2000→4000 EOS ladder를 유지한다. 짧은 답을 요구해도 cap을 임의 축소하지 않는다. 최종 비EOS는 invalid이며 no로 처리하지 않는다.

새 parser는 전체 yes/no 또는 유일한 answer 키의 JSON yes/no만 허용하는 의미 동등 규칙을 고정한다. 기존 Q_A 전용 Normal/Abnormal mapping을 적용하지 않는다. 공식 형식의 완결된 thinking prefix `<unused94>…<unused95>` 제거는 별도로 기록하고, 이후 전체 답 문자열에 같은 규칙을 적용한다. 불완전 marker, 설명문, 모순, bbox·빈 목록을 yes/no로 구제하지 않는다. 원문 strict 결과와 의미 동등 처리 결과를 모두 보존한다.

# Contribution Path / Baselines / Reuse

## 기여 경로와 가까운 방법

[Targeted Visual Prompting](https://arxiv.org/html/2408.03043v1)은 영역 표시·crop과 영역 QA 학습을 이미 다룬다. Ferret 등의 영역 입력·grounding 학습도 가까운 선행이다. 이번은 그런 학습을 새로 도입하는 방법 개발이 아니라, 기존 bbox-only 학습의 전이 범위를 확인하는 진단이다.

후속 방법은 단순 답변+bbox 다과제 SFT와 구별되는 실패 조건·개선 원리가 있어야 한다. 강한 직접 질의 SFT와 같은 train 자료를 사용하는 detector/encoder+head 대안을 포함하기 전에는 내부 VLM 학습의 우월성을 주장하지 않는다.

## 고정 checkpoint

- M0: 원본 MedGemma 1.5.
- B0: `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`, SHA256 `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`.
- 조건부 B29: `results/iter_012/train/lr2e-4_s29/epoch_05/adapter.pt`, SHA256 `d4db2f2ab10d134b4352c7f57cc0ca5c497da3bce388d9cc91751ec9ca6d1fc9`.
- 조건부 B43: `results/iter_012/train/lr2e-4_s43/epoch_05/adapter.pt`, SHA256 `e6e4730add1d942c81fb89aabd5477a779668d2f0f8ef01cc21af33032584f4a`.

선택 출처는 `results/iter_012/select/pick_seed{17,29,43}.json`이다. 실행 전 파일 hash와 tensor digest, rank16/alpha32, epoch·학습 출처를 대조한다. C 추가 SFT는 보존하며 이번 핵심 비교에 추가하지 않는다. C까지 넣기 전에 B0의 직접·외부 활용 차이를 먼저 판단할 수 있기 때문이다.

## 비교 조건

각 환자의 TL/TR/BL/BR 질문은 독립 대화로 실행한다.

| 조건 | 입력과 역할 |
|---|---|
| D_M0 | 원본 영상+질문, base 직접 답변 |
| D_B0 | 같은 영상+같은 질문, SFT 직접 답변 |
| R_M0 | 저장된 M0 official_long bbox에서 규칙 답변; concise도 별도 보고 |
| R_B0 | 저장된 B0 concise bbox에서 같은 규칙 답변 |
| L | 원본 영상+B0 예측 bbox+질문을 받는 M0 reader |
| U | L과 동일 안내문에서 bbox 값만 unavailable로 바꾼 M0 reader |
| O_M0/O_B0 | 원본 영상+GT bbox+질문; 지시·수치 해석용 oracle |

L과 U는 공통으로 별도 localization proposal이 있을 수 있고 틀릴 수 있다는 안내를 사용한다. 빈 예측 목록과 출처 실패 unavailable을 구분한다. oracle에서는 제공 좌표를 정답 reference로 사용하도록 명시한다. Oracle은 실용 비교군이 아니다.

보조 baseline은 항상 yes/no, D24에서 고정한 사분면별 다수 답 및 가장 흔한 네 답 패턴이다. E에서 가능한 16개 고정 패턴의 최댓값은 사후 위치 prior의 상한으로만 보고하며 배포 가능한 baseline으로 부르지 않는다. M0/B0 각각 동일 회색 영상과 네 질문을 한 번씩 실행한다. 회색 영상은 정보 제거 대조이며 정상 환자로 해석하지 않는다.

모든 조건은 원본 영상을 자유롭게 사용한다. 규칙 baseline의 입력만 bbox인 것은 그 대안의 정의다. bbox 생성 비용과 reader 호출 비용을 포함한 실제 배포 비용 및 이번 저장 출력 재사용 비용을 나눠 보고한다.

## 코드와 결과 재사용

새 브랜치는 승인 iter_006을 기반으로 하며, reuse_assets에 명시한 iter_018의 16개 파일을 선별 반입한다. 실제 모델 로더·LoRA·worker·잠금 구현을 다시 만들지 않는다. qa_protocol에는 이번 실행의 필수 자료와 코드만 요구하는 명시적 profile을 추가한다. 단순히 REQUIRED_CODE 검사를 끄거나 없는 파일을 무시하지 않는다.

원본 bbox는 `results/iter_012/confirm_base/gen_worker*.jsonl`, `confirm_sft_seed17/gen_worker*.jsonl`과 조건부 seed29/43의 출력에서 연결한다. 모델·prompt·adapter·입력 hash·EOS·원본 completion 및 protocol 출처를 확인한다. 파생 `iter_015/reuse/bbox_*`만으로 provenance를 대신하지 않는다. 과거 protocol을 수정하거나 현재 코드 hash로 덮어쓰지 않는다. 이번의 읽기 전용 source manifest에 기존 SHA와 호환 범위를 기록한다.

# Proposed Experiment

## 1. 정답과 고정 query

과제는 **주석된 opacity bbox 중 중심이 지정 사분면에 있는 것이 하나 이상인가**이다. 영상의 중앙 가로선·세로선으로 TL/TR/BL/BR를 정하고, 좌우는 환자가 아니라 표시된 영상 기준이다. bbox `[y_min,x_min,y_max,x_max]`의 중심은 두 끝점의 산술평균이다. 500 경계는 lower/right에 배정하고 전체 0–1000 범위를 명시한다.

직접 질문은 숫자 ROI 해석을 요구하지 않는다. 고정 영문 template은 다음 의미를 유지한다: `For this task, the location of a pulmonary opacity suspicious for pneumonia is the center of its enclosing bounding box. Divide the displayed image into four equal quadrants at its horizontal and vertical midlines. Left and right refer to the displayed image, not the patient's sides. Is at least one such opacity centered in the {quadrant} quadrant? Answer only yes or no.`

모든 환자에게 네 질문을 전부 제시하며 GT로 query를 선택하지 않는다. 환자 ID·category·정답·bbox 개수는 direct prompt에 넣지 않는다. 각 조건의 question 원문은 동일하다. GT bbox는 oracle에서만 전달한다.

정답 no는 해당 사분면에 주석 bbox의 중심이 없다는 뜻이다. 병변 픽셀의 부재나 임상적 정상 여부를 뜻하지 않는다. 모든 평가 환자는 opacity 양성이며 정상 환자 specificity를 주장하지 않는다.

주평가는 모든 GT bbox 중심이 두 중앙선 각각에서 25 이상 떨어진 환자다. 이는 원본 1024 영상에서 약 25.6 pixels다. 경계 환자도 같은 네 질문을 생성하고 exact annotation 기준의 보조 결과로 보존한다. 주평가에서 제외한 이유·coverage·box 크기·개수 분포를 보고한다. 모델 출력으로 제외 여부를 바꾸지 않는다.

## 2. 동작 확인: D24

기존 iter_010 validation ID와 GT에서 opacity이면서 중앙선 margin을 통과한 환자를 사용한다. 가장 큰 GT bbox의 중심 사분면으로 네 층을 만들고, 면적 동률은 ann_id로 정렬한다. 각 층에서 `SHA256('iter023-D24-v1|'+id)` 순서의 6명을 선택한다. 후보 수는 28/19/58/53으로 확인됐다. 선택은 개발용 coverage 확보이며 성능 추정 표본이 아니다.

D24의 bbox 개수는 1개 10명·2개 12명·3개 2명, 사분면별 yes는 8/7/11/13이다. 이 수치와 선택 ID를 재생성해 일치시킨다. train/E 환자·pixel hash와의 중복을 검사한다. 기존 reserve 파일을 열어 신규 표본을 뽑지 않는다.

- 원본·중앙선·GT box·중심을 표시한 최소 8개 개발 overlay를 확인한다. 단일·다중 box, 네 사분면, 경계 인접 사례를 포함한다.
- CPU fixture로 center 계산, half-open 경계, bbox 순서 불변성, invalid bbox, 빈 목록, strict/semantic parser를 독립 기준과 대조한다.
- M0 official/B0 concise bbox를 D24에서 필요한 만큼 생성하고, 이 중 저장 결과가 있는 고정 8명에서는 adapter 로드와 기존 출력 연결을 비교한다. 불일치를 조용히 허용하지 말고 환경·입력·token 차이를 확인한다. 완료된 본실험은 재실행하지 않는다.
- 여섯 생성 조건 D_M0/D_B0/L/U/O_M0/O_B0의 24×4×6=576개 고유 QA 요청을 수행한다. 학습 update는 0이다.
- plain이 checkpoint·조건별 semantic valid 95%를 충족하지 못하면 사전에 정한 JSON 출력 지시만으로 D24 전체를 한 번 더 실행한다. 의미 parser는 두 형식을 동등하게 처리한다. common format 선택은 정답률이나 B0−M0 차이가 아니라 전체 조건의 형식 통과 여부로 한다. 둘 다 통과하면 plain을 쓴다.
- O_M0/O_B0 각각의 전체 질문 정확도 90% 이상을 지시·좌표 해석 gate로 사용한다. oracle 결과는 질의 이해를 보조하지만 직접 시각 능력의 증거는 아니다.
- 형식 또는 oracle gate가 해결되지 않으면 E로 확대하지 않는다. 결과는 형식·지시 해석에 제한된 진단으로 보고하며 전이 부재로 결론 내리지 않는다. 추가 prompt 탐색·새 학습은 자동 실행하지 않는다.

## 3. 실행 경로와 GPU 구성 확인

D에서 24개 요청의 정상 실행과 중단·재개를 비교한다. 자기 worker 또는 자기 pipeline을 중단했을 때 자식 종료·claim 소유권·tail 격리·재개 후 고유 요청 집합·greedy suffix가 일치해야 한다. 완료된 결과의 source·query·adapter를 변조한 fixture가 재사용을 거부하는지도 확인한다.

실행 직전 nvidia-smi로 허용 GPU 0,1의 UUID·여유 메모리를 확인한다. 여유가 큰 GPU부터 배정한다. 현재 다른 사용자 프로세스는 건드리지 않는다.

대표 D 요청 48개를 고정해 총 2 worker와, 메모리가 허용하면 총 4 worker를 비교한다. 모델·oracle/reader 길이·출력 형식을 포함하고 M0/B0 각각에서 정합성을 확인한다. 별도의 최장 prompt·4000-token KV 상한 메모리 stress를 수행해 생성 결과와 구분해 기록한다. batch 확대를 추가로 전수 탐색하지 않는다.

GPU별 다른 점유량에 각 worker의 측정 peak와 2GiB를 더한 합이 용량 이내여야 한다. 4 worker가 이 조건을 만족하지 않으면 2 worker를 사용한다. 모델당 8–10GiB는 초기 참고값일 뿐 배치 근거가 아니다. 전체 요청/분, 모델 로딩 포함 wall, 긴 출력 지연, peak allocated/reserved 및 장치 전체 점유, CPU·I/O 경합, 오류를 기록한다. greedy 출력과 요청 수가 같고 총 완료시간이 실제 줄어드는 구성을 채택한다. 두 구성이 측정 잡음 범위에서 같으면 단순한 2 worker를 선택하고 근거를 남긴다.

## 4. 가능성 탐색: E60

기존 `iter_015/manifests/sets.json`의 E180 opacity 60명 전원을 사용한다. 이 중 중앙선 margin 주평가 대상은 48명이고 나머지 12명도 경계 보조 집단으로 유지한다. 여섯 생성 조건의 60×4×6=1,440요청을 실행한다. M0/B0의 bbox 규칙 결과는 검증한 기존 출력에서 계산한다.

M0/B0 회색 영상 대조는 각각 네 고유 요청이다. 동일 입력을 60회 반복 생성해 표본 수를 부풀리지 않는다.

이 단계는 기존 개발 자료의 새 과제 탐색이다. 프롬프트·parser·사분면·margin·주지표·확대 규칙을 E 출력 전에 잠근다. 정답을 본 뒤 유리한 환자·query·checkpoint를 고르지 않는다.

## 5. 조건부 규모 확대: E200

자료·실행·형식 gate가 통과하고 아래 중 하나를 만족하면, 같은 Claude 호출에서 기존 E600 opacity 200명까지 확대한다. E60 결과를 재사용하고 추가 140명의 3,360요청만 생성한다. 주평가 160명, 경계 보조 40명이다.

- 직접 전이 차이 또는 외부 규칙 개선의 점추정이 0.10 이상이다.
- 외부 규칙 R_B0 또는 reader L의 성능이 직접 B0보다 0.10 이상 높아, 직접 활용의 차이를 더 정확히 볼 가치가 있다.
- 관련 paired CI가 0.10의 실질 차이를 포함해 불확정이며, discordance 비율의 Wilson 상한으로 계산한 N=160 예상 반폭 `1.96×sqrt(q_upper/160)`이 0.12 이하이다.

마지막 조건은 확대의 정보 이득을 추정하는 보수적 근사이며 검정력 보장으로 부르지 않는다. 0.10은 후속 투자 판단의 사전 기준이지 임상적 중요도 기준이 아니다. 확대하지 않으면 어떤 효과와 정밀도가 부족했는지 보고한다. 작은 표본의 불확정을 접근법 전체의 실패로 바꾸지 않는다.

## 6. 조건부 기존 seed 재현

E200에서 아래 Evaluation의 신뢰할 만한 직접 전이 또는 해석 가능한 직접·외부 활용 차이가 확인되면 기존 B29/B43의 직접 질문을 같은 E200에서 실행한다. 추가 200×4×2=1,600요청이며 학습은 없다. 각 seed의 D24 oracle 96요청과 adapter sanity를 먼저 확인한다. 그 seed의 저장 bbox에 같은 규칙을 적용한다.

최고 seed를 고르지 않는다. seed별 효과·범위·환자 paired CI를 나란히 보고하고, 환자 bootstrap에서 seed를 독립 환자로 세지 않는다. D24 gate가 실패한 seed는 의미 능력 기각 대신 형식·해석 문제로 별도 보고한다.

## 7. 독립 확인과 비용

이번에는 새로운 독립 확인 집단을 평가하지 않는다. E200 확대와 seed 재현도 개발 진단이다. MRI F139와 기존 reserve는 그대로 보존한다. 결과가 유망하면 다음 계획에서 같은 소견을 평가할 다른 원천 자료 또는 적절한 미사용 환자 집단의 독립 확인을 설계한다. reserve 사용은 이번 계획에 포함하지 않는다.

최대 기본 생성량은 E200 여섯 조건 4,800건, 추가 두 seed 직접 질의 1,600건, D24 약 576건 및 seed oracle·sanity·처리량/재개 검사다. JSON fallback이 필요하면 D 요청이 추가된다. E60을 E200과 중복 계산하지 않는다.

새 질문의 처리량은 미측정이다. 준비 추정은 전체 20–60 requests/min일 때 주요 약 7천 요청에 2–6시간, 로딩·검사·긴 출력까지 포함해 대략 2–8시간이다. 이는 상한이나 보장값이 아니다. D 실측 후 남은 요청 수/총 처리량과 준비·재개 비용으로 wall-clock을 다시 산출한다. 임의 시간 상한을 넣지 않는다.

# Implementation Tasks for Claude

1. 시작 시 기존 자기 작업의 PID/starttime·lock·종료 상태를 확인하고 살아 있는 작업을 중복 실행하지 않는다. 반입 manifest와 16개 파일의 의존성을 확인한다.
2. `rsna_diag/roi23_spec.py`, `roi23_data.py`, `roi23_eval.py`, `roi23_pipeline.py` 등 이번 과제에 필요한 모듈을 추가한다. 실제 이름은 바꿀 수 있으나 기존 로더·LoRA·worker를 중복 구현하지 않는다. 새 산출물은 전부 `results/iter_023/` 아래에 둔다.
3. qa 요청/실행 경로에 명시적 run-root와 protocol profile을 연결한다. 환자·query·형식·조건·checkpoint·영상·bbox 출처·생성 설정을 request ID와 protocol에 연결한다. optional extra가 빠져도 실행되는 구조를 이번 경로에 남기지 않는다.
4. 기존 manifest와 원시 bbox에서 필요한 환자만 읽어 source manifest를 만든다. label/query 생성은 inference 요청 구성과 분리하고 direct 요청에 GT가 섞이지 않음을 검사한다. 기존 split 이름 confirm은 provenance로 보존하되 이번 사용 역할은 development로 별도 표시한다.
5. 데이터·parser·규칙·완료 검증 fixture, 공식 입력 대조, adapter sanity, 재개 검사, 처리량 비교를 수행한다. 필수 source 누락·불일치는 새 구현이나 조용한 재생성으로 대체하지 않는다.
6. D→E60→조건부 E200→조건부 seed 단계를 실행기에 강제한다. 직접 stage 진입과 완료 건너뛰기에서도 앞 단계 decision·현재 hash·요청 집합을 재검증한다. 모든 자식 종료 코드를 수집하고 성공일 때만 completion을 원자적으로 기록한다.
7. 환자별 원시 네 답, strict/semantic 결과, 규칙 답, CI, exclusion·형식 실패·bbox invalid·oracle 실패를 보존한다. 독립 계산으로 주지표와 규칙 답을 재확인한다.
8. 보고서 첫머리에 기존 RSNA 성과와의 연결, 이미 알려진 것, 새 실제 결과, 실행·미실행 범위, 다음 투자 결정을 적는다. checkpoint·원본 결과·과거 protocol·hf_cache를 수정하지 않는다. 소스 커밋과 브랜치 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

## 지표

주지표 Q4는 중앙선 margin을 통과한 환자에서 네 사분면의 답이 모두 맞은 비율이다. invalid 하나라도 있으면 해당 환자의 Q4는 실패다. 같은 환자의 네 질문을 네 독립 표본으로 계산하지 않는다.

주 비교는 `Δ_direct=Q4(D_B0)−Q4(D_M0)`이다. 위치 정보 개선의 보조 비교는 `G=Q4(R_B0)−Q4(R_M0_official)`이며 M0 concise도 함께 보고한다. reader 효과 `Q4(L)−Q4(U)`, 직접 활용 차이 `Q4(R_B0)−Q4(D_B0)`, `Q4(L)−Q4(D_B0)`를 보고한다.

보조 지표는 사분면별 sensitivity/specificity·balanced accuracy, 환자 평균 질문 정확도, strict/semantic valid, bbox invalid/empty, oracle 정확도, 1/2/3개 box별 결과와 경계 집단 결과다. bbox invalid는 규칙 baseline의 정답 no로 바꾸지 않는다. 주평가에선 실패로 세고 coverage를 따로 보고한다.

환자 단위 paired bootstrap 10,000회, 고정 seed 23023으로 95% CI를 계산한다. 평균만이 아니라 paired 개선·악화·동일 환자 수도 보고한다. 모든 paired 차이가 같아 bootstrap이 퇴화하면 개선/악화 확률 각각의 Bonferroni 보정 Clopper–Pearson 구간으로 보수적 차이 구간을 계산해 판단에 사용한다. [0,0]을 모집단 동등성으로 해석하지 않는다.

원본 응답 벡터를 환자 간 10,000회 permutation한 연관성 분석을 수행한다. 환자의 네 답을 함께 옮기며 사분면 위치는 바꾸지 않는다. 이는 위치 prior와 영상별 답의 연결을 보는 보조 근거다. gray 대조의 실패만으로 영상 이해를 증명하지 않는다.

## 양성 결과

E200에서 Δ_direct≥0.10이고 paired CI 하한>0이며, B0가 고정 prior·gray 대조보다 우수하고 영상별 응답 연결도 지지되면 가까운 공간 질의 전이를 지지한다. E의 semantic valid도 조건별 95% 이상이어야 한다. 기존 seed 재현 조건으로 진입한다.

다음 행동은 같은 소견의 다른 원천 자료에서 같은 원리가 재현되는지 검토하는 것이다. 이번 진단만으로 신방법이나 일반적 공간 이해를 주장하지 않는다. 내부 직접 답변과 외부 규칙의 성능·호출 비용 차이가 후속 질문을 정한다.

## 직접 활용 차이가 남는 결과

G의 CI 하한>0이고 R_B0−D_B0≥0.10 및 그 CI 하한>0인데, Δ_direct CI 상한이 0.10 미만이면 외부로 사용할 수 있는 위치 개선에 비해 직접 질의의 개선이 제한적이라는 근거다. O_M0/O_B0 정확도 90% 이상, semantic valid 95% 이상, 실행·정답 검증 통과를 함께 요구한다.

작지만 양의 전이가 있으면 그대로 보고한다. 이를 전이 전무나 forgetting으로 바꾸지 않는다. 다음에는 지시·형식 영향과 활용 단절의 재현 범위를 확인한 뒤에만 방법 개발과 강한 직접 질의 SFT 비교를 설계한다. 이번 반복에서는 새 학습을 시작하지 않는다.

## 음성 또는 외부 연결로 충분한 결과

직접 전이와 외부 규칙 개선 모두 작고 CI가 0.10의 효과를 배제하면, 현재 과제에서 기대한 추가 전이 근거가 부족하다고 판단한다. RSNA bbox SFT 전체의 실패로 일반화하지 않는다.

R_B0 또는 L이 충분히 정확하고 직접 내부 학습의 추가 이점을 확인하지 못하면 이를 유효한 baseline으로 보존한다. 내부 학습이 더 필요한 실제 사용 조건이 있는지 판단하고 복잡한 loss를 자동 추가하지 않는다.

## 불확정·실행 실패

CI가 중요한 양·음 효과를 함께 포함하면 사전 확대 기준으로 E200까지 진행할지 정한다. 확대 후에도 불확정이면 효과·정밀도·미해결 설명을 기록하고 추가 환자가 판단을 바꿀지 다음 계획에서 평가한다. reserve를 자동 개방하지 않는다.

형식·oracle gate 실패는 의미 능력 실패와 분리한다. source 불일치·좌표 오류·누락 출력·잘못된 adapter 등은 실행 유효성 문제로 처리한다. 단순 준비 성공을 유효한 전이 실험이나 목표 달성으로 보고하지 않는다.

# Risks / Checks

- bbox 중심은 annotation geometry다. 실제 병변 중심·segmentation·임상적 음성을 보장하지 않는다. 직접 질문과 보고서에 이 범위를 명시한다.
- 중앙선 margin은 과제를 쉽게 만들 수 있다. 전체 200명 중 160명이라는 coverage와 제외 40명의 보조 결과를 함께 보고하고, 드문 3개 box 환자를 임의 제외하지 않는다.
- 모든 환자가 opacity 양성이므로 전역 검출 prior가 생긴다. 네 질문 전체와 고정 답 패턴·회색 영상·permutation 대조로 이를 점검한다.
- D24는 층화된 지시 확인 자료다. D의 균형이나 성공을 E의 대표성·일반화로 해석하지 않는다.
- 환자·영상의 비중복은 모델 사전학습 미노출의 증거가 아니다. 기존 E600은 개발 자료이며 독립 확인으로 재명명하지 않는다.
- GT oracle이 답의 기하 정보를 제공한다는 사실을 숨기지 않는다. oracle 통과만으로 직접 시각적 지시 이해가 완전히 통제됐다고 단정하지 않는다.
- 재사용 bbox 출처가 실패하면 unavailable과 empty를 구분한다. 성능에 유리한 fallback이나 중복 덮어쓰기를 허용하지 않는다.
- OOM·진행 정체 시 자기 작업을 안전하게 중단하고 원인을 확인해 batch/동시성을 낮춘다. 결과·claim·이전 protocol을 삭제해 재개 문제를 우회하지 않는다.
- 사용하지 않는 MRI downloader, 과거 GIoU 수치 검사, 학습 실행기 전체 정비는 이번 범위가 아니다.

## 대규모 GPU 필요 후보

다양한 영역 질문·grounding·일반 QA를 함께 학습하는 vision encoder–언어 모델 공동 post-training을 보존한다. 현재 필요성은 미확정이다. 이번 진단에서 확인한 직접 활용의 실패 조건과 강한 외부 연결 baseline을 기준으로 투자 가치를 다시 판단한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

이번 라운드는 파일·소스·저장 주석의 읽기와 집계, 선행연구 본문 확인만 수행했다. 파일 생성·수정, 모델 로딩, 테스트·GPU 실행은 하지 않았다. 새 영역 질문의 모델 성능은 아직 없다.

### 1. 영역 과제의 정답과 coverage

`research/results/iter_015/manifests/labels.json`, `sets.json`의 기존 개발 opacity 주석을 집계했다. 환자와 무관한 영상 중앙선으로 사분면을 정의하고, 주석 bbox 중심이 중앙선에서 정규화 좌표 25 이상 떨어진 환자를 주평가 대상으로 삼으면 다음과 같다.

- 기존 D36의 opacity 12명 중 10명.
- 기존 E180의 opacity 60명 중 48명.
- 기존 E600의 opacity 200명 중 160명.
- E600의 주평가 160명 모두 네 질문에 yes와 no가 함께 존재한다. 전체 opacity 유무나 개수만으로 네 답을 정할 수 없다.
- 160명의 사분면별 yes 수는 TL/TR/BL/BR=45/37/81/67이다. bbox 개수는 1개 94명, 2개 62명, 3개 4명이다.
- 가장 흔한 정답 벡터도 39/160명이다. 사분면별 불균형과 고정 패턴 prior를 반드시 보고해야 한다.

비교한 bbox 겹침안에서는 E600의 네 사분면 모두에 명확한 답을 줄 수 있는 환자가 145명이고, 그중 질문에 따라 답이 바뀌는 환자는 99명이었다. 이 집계의 yes는 bbox 면적의 10% 이상 겹침, no는 모든 box와 ROI 사이 25 이상의 간격이었다. 이는 후보 비교용 집계이며 최종 과제 규칙으로 사용하지 않는다. bbox 중심안이 정답 정의가 더 단순하고 경계 제외 후의 식별 가능한 환자가 많아 선택했다. 중심 위치는 주석 사각형의 기하이며 실제 병변 segmentation의 중심이나 임상적 정상 여부가 아니다.

기존 D12에는 TR 양성이 없어 그대로 지시 해석 gate로 쓰기에는 부족하다. `iter_010/manifests/validation_ids.json`과 `gt_manifest.json`에서 중앙선 margin을 통과한 opacity validation 환자를 확인했다. 가장 큰 bbox의 중심 사분면별 후보 수는 28/19/58/53명이다. 각 층에서 `SHA256('iter023-D24-v1|'+id)` 순서의 6명을 선택하면 D24를 만들 수 있다. 모든 bbox를 기준으로 한 TL/TR/BL/BR yes 수는 8/7/11/13, bbox 개수 구성은 1개 10명·2개 12명·3개 2명이다. D24는 형식·연결 확인 자료이며 성능 추정 집단이 아니다.

### 2. 기존 실험과 이번 질문의 차이

iter_012–018의 원본 plan.json과 review.json, 관련 review.md를 다시 대조했다. 재확인 목적은 사용자 보완에 맞춰 비교군과 미해결 질문을 확정하는 것이었다.

- iter_012는 직접 SFT의 bbox 개선을 확인했다. iter_013–014의 추가 loss 결과가 이를 기각하지 않는다.
- iter_015–016은 Q_O/Q_A의 전역 판단과 형식 효과를 구분했다.
- iter_017은 동일 전역 질문에서 검출·개수·좌표 전달을 비교했다. 그 질문들은 좌표가 반드시 필요한 구조가 아니었다.
- 이번 질문은 같은 영상의 서로 다른 고정 영역에서 정답이 달라진다. 따라서 Q_O/Q_A나 U/B/K/L의 단순 반복이 아니다.
- iter_022 계획과 superseded.json을 읽었다. longitudinal 계획은 보존하며 실행 대상으로 삼지 않는다.

### 3. 최소 대조의 결정

직접 질의에는 숫자 ROI 대신 영상 기준 사분면과 중앙선 정의를 사용한다. 환자 좌우와 영상 좌우를 명시적으로 구분한다. 숫자 bbox의 해석은 예측 reader·GT oracle에서 별도로 확인한다. GT oracle은 원본 영상을 그대로 유지하고 두 checkpoint 모두 평가한다. 동일 문구의 predicted/unavailable reader를 두어 인터페이스 효과를 구분한다.

모든 환자에게 네 고정 질문을 전부 제시한다. GT에서 양성 ROI만 골라 제시하지 않는다. 회색 영상 대조는 환자별로 같은 입력을 반복할 필요가 없어 checkpoint당 네 고유 요청으로 충분하다. 원본 영상 응답의 환자 연결을 permutation하는 분석도 추가 GPU 생성 없이 가능하다. 이는 영상 의존성의 보조 분석이며 실제 영상 교체 실험이나 인과적 증명으로 부르지 않는다.

### 4. 선행연구의 추가 확인

[Targeted Visual Prompting 본문 §2–3](https://arxiv.org/html/2408.03043v1)을 다시 확인한 이유는 영역 표시 대조와 학습 범위가 이번 계획과 어떻게 다른지 확인하기 위해서다. 이 연구는 영역을 표시한 context와 crop을 결합하고, region-in-text·draw-region 등의 baseline을 비교한다. 평가 모델은 영역 QA를 포함해 학습한다. 따라서 영역 QA나 시각적 표시 자체는 신규 기여가 아니다. 이번에는 bbox-only SFT 이후 추가 QA 학습 없이 나타나는 전이 범위를 진단한다. 첫 라운드의 Ferret·Localization-Grounded Supervision 조사도 유지하되 광범위한 문헌 조사는 추가하지 않았다.

### 5. 실제 재사용 경로

research의 현재 HEAD는 iter_021이며 작업 트리 변경은 없다. 새 기반 iter_006의 전체 SHA는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`이고 rsna_diag가 없음을 확인했다. iter_018 SHA의 16개 파일을 실제 읽어 blob 존재와 import 의존성을 대조했다. qa_protocol의 기존 REQUIRED_CODE는 이번에 사용하지 않을 ev17/cx18 등을 포함한다. 새 profile을 명시적으로 추가하는 수정이 필요하며, 누락된 과거 과제 전체를 반입할 필요는 없다.

원본 bbox는 요약본만 믿지 않고 `iter_012/confirm_base`, `confirm_sft_seed17`, 조건부 `confirm_sft_seed29/43`의 원시 worker 출력과 연결해야 한다. `iter_015/reuse/bbox_*`는 suffix_ids와 완전한 입력 연결을 생략한 파생 자료임을 확인했다. `iter_015/reuse/reuse_report.json`은 출처 연결의 참고로 사용한다.

B0/B29/B43 adapter 파일은 각각 119,369,709 bytes로 존재한다. 첫 라운드에서 계산한 SHA256과 선택 epoch 근거를 실행 전 재검증하도록 계획에 넣는다. 이번에는 tensor 로드·GPU 검사를 하지 않았다.

## 의미와 남은 한계

정답·coverage·재사용 경로가 확인돼 실행 계획으로 넘어갈 수 있다. 이번 결과는 기존 개발 양성 환자의 가까운 기하 질의 전이만 설명한다. 외부 기관, 정상 환자의 specificity, 사전학습 미노출, 임상 reasoning, 새 방법의 contribution은 확인하지 않는다. 기존 reserve와 MRI F139는 열지 않았다.

## 대규모 GPU 필요 후보

다양한 공간 질의·grounding·일반 QA를 결합한 vision encoder–언어 모델 공동 post-training을 후보로 보존한다. 현재 필요성은 미확정이며, 이번 직접 활용과 외부 연결의 비교 결과를 먼저 확인한다.

이전 사고 라운드 노트: agent/runs/iter_023/think/
