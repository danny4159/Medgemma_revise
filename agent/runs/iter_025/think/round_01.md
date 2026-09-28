# 사고 라운드 1

## 새로 확인한 것

이번 라운드는 파일·소스·문헌 조회와 저장된 출력의 메모리 내 재집계만 수행했다. 파일 생성·수정, 모델 로딩, 테스트·GPU 실험은 하지 않았다.

### 1. 기존 성과와 미해결 질문

`agent/GOAL.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`, iter_009·024 리뷰, iter_023 계획과 관련 코드·결과를 확인했다. iter_012–018의 원본 계획·리뷰 요약도 대조했다. 이전에 확인한 사실을 새 미확인 사항으로 되돌리지 않는다.

- 이미 확인: iter_012의 직접 SFT bbox 개선은 유효하다. iter_015–016은 QA 형식 효과를, iter_017은 전역 질문에서 검출·개수·좌표 전달의 차이를 다뤘다. iter_013–014의 특정 loss 결과는 SFT 전체의 실패가 아니다.
- 아직 미확인: 위치가 답을 바꾸는 미학습 질문에서 SFT가 영상의 공간 정보를 활용하는가. iter_024의 D24 oracle 실패로 이 전이 본검증은 진행되지 않았다.
- 유지: 사용자 보완의 RSNA checkpoint 진단 우선순위, 기존 성과·분할·원시 결과.
- 보류: 새 학습·loss, MRI F139, reserve, longitudinal 전환. E60도 기존 gate를 낮춰 바로 열지 않는다.

### 2. 실제 oracle 요청은 계획한 통제와 차이가 있다

`agent/runs/iter_023/plan.md`는 oracle에서 제공 좌표를 정답 reference로 사용하도록 명시한다고 설명했다. 그러나 `rsna_diag/qa_spec.py`의 `EVIDENCE_HEAD`·`oracle_nonempty`, `roi23_spec.py`, `roi23_requests.py` 및 `results/iter_024/requests/D24__O_M0.jsonl`의 실제 요청은 reference annotation boxes를 제시한 뒤 영상에서 opacity의 중심을 묻는다. 제공 목록만을 기준으로 계산하고 영상에서 재검출하지 말라는 명시적 지시는 없다. 중심 계산식도 실제 prompt에는 없다.

이 차이는 다음 대조를 설계할 근거다. 다만 문구 차이가 오류의 원인이라고 입증된 것은 아니다. bbox의 yxyx·0–1000 규약은 요청에 들어 있으며, 직전 리뷰는 반올림 좌표에서도 정답 사분면이 유지됨을 확인했다. 좌표 데이터 오류와 지시 범위의 모호함을 혼동하지 않는다.

### 3. 원시 응답은 단순 축 혼동보다 넓은 문제를 시사한다

`results/iter_024/gen/D24__{D_M0,D_B0,L,U,O_M0,O_B0}/gen_worker*.jsonl`을 별도로 읽었다. 각 조건은 24명×4질문=96건이며, 전체 yes/no 응답을 정규화해 집계했다.

| 조건 | 중심 규칙 정답/96 | yes/96 | 환자 내 네 답이 모두 같은 환자/24 |
|---|---:|---:|---:|
| D_M0 | 40 | 93 | 22 |
| D_B0 | 60 | 41 | 9 |
| L | 45 | 72 | 24 |
| U | 54 | 21 | 12 |
| O_M0 | 41 | 90 | 20 |
| O_B0 | 65 | 42 | 9 |

특히 L은 18명에게 네 질문 모두 yes, 6명에게 모두 no를 답했다. 현재 D24 reader가 질문 영역에 따라 답을 달리하지 않았다는 제한된 관찰이다. 영상 무사용이나 일반적인 공간 능력 부재를 뜻하지 않는다.

GT bbox 제공 전후 답변 일치는 M0 89/96, B0 87/96이다. 높은 일치만으로 evidence를 무시했다고 단정할 수 없으나, oracle 제공 자체가 문제를 해결하지 않았음을 보여준다.

경쟁 해석을 탐색하기 위해 저장 답변을 다른 기하 규칙과도 대조했다. O_M0의 일치 수는 중심 41, x/y 교환 45, 좌우 반전 43, bbox와 사분면의 양의 면적 겹침 61이었다. O_B0는 각각 65/59/59/65였다. 이는 사후 진단이며 정답·metric 변경이 아니다. 특히 M0는 거의 항상 yes여서 겹침 규칙과 더 많이 일치하는 현상을 실제 겹침 이해의 증거로 해석할 수 없다. 기존 중심 규칙과 gate 실패 판정은 그대로 보존한다.

### 4. 코드와 checkpoint는 현재 브랜치에 존재한다

`research/`의 HEAD는 `d60460f8be761e11e1dbce306aa571173e4229db`이고 `git status --short`, `git diff`는 비어 있었다. `git ls-files`에서 `roi23_*`, `qa_spec.py`, `qa_requests.py`, `generate.py`, `lora.py`, `geometry.py`, `inputs.py`, `eval_gate.py`, 잠금 모듈과 iter_023·024 테스트를 확인했다. 같은 접근법을 잇는다면 별도 선별 반입이 필요하지 않다. 현재 기반의 파일을 중복해서 reuse_assets에 넣지 않는다.

실제 adapter 파일 SHA256을 다시 계산해 기존 기록과 일치함을 확인했다.

- B0: `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt` — `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`.
- B29: `results/iter_012/train/lr2e-4_s29/epoch_05/adapter.pt` — `d4db2f2ab10d134b4352c7f57cc0ca5c497da3bce388d9cc91751ec9ca6d1fc9`.
- B43: `results/iter_012/train/lr2e-4_s43/epoch_05/adapter.pt` — `e6e4730add1d942c81fb89aabd5477a779668d2f0f8ef01cc21af33032584f4a`.

현재 checkpoint manifest의 B0 tensor digest는 `e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11`이다. 이번에 tensor digest 재계산·실제 adapter 로드를 수행한 것은 아니다.

`generate.build_inputs`는 image→text 순서의 user content와 `apply_chat_template(..., add_generation_prompt=True)`를 사용한다. 보존된 공식 notebook도 존재한다. 소스 구조 확인을 실제 D 입력의 tensor 대조 완료로 간주하지 않는다.

재사용 전 필요한 보완은 직전 리뷰의 범위를 유지한다. 선택한 경로의 필수 source·bbox 출처 잠금, manifest 기준 요청 완전성, completion·선행 decision 재검증, 직접 실행의 gate 우회 차단, 실제 중단·재개 검사가 필요하다. E 확대를 채택한다면 discordance 기반 정밀도 계산과 형식·oracle gate 연결도 수정해야 한다. 미사용 MRI·과거 학습 코드는 보완 대상이 아니다.

### 5. 가까운 문헌과 구별할 범위

[Targeted Visual Prompting 원문](https://arxiv.org/html/2408.03043v1)의 §2–3을 다시 확인했다. 재확인 이유는 영역 표시·crop 대안을 현재의 bbox-only 전이 진단과 구별하기 위해서다. 이 논문은 영역을 표시한 context와 crop을 함께 제공하며, Region in text·Draw region 등의 baseline 및 QA 학습을 다룬다. 따라서 영역 입력이나 표시 방식 자체는 신규 기여가 아니다. 이번의 가능한 정보 이득은 추가 QA 학습 전의 직접 활용과 외부 활용을 구분하는 데 있다. 문헌은 조사 근거이며 이번 결과만으로 사용자 논문 추천을 하지 않는다.

## 의미와 전략 판단

현재 방법 개선 / 기존 checkpoint의 원인·능력 전이 진단 / 다른 질문 전환을 비교했다. 추가 grounding loss는 현재 oracle 실패의 설명을 구분하지 못한다. 다른 임상 질문으로 즉시 이동할 새 근거도 없다. 기존 checkpoint의 최소 진단을 우선하되, 전체 E 평가를 예약하기 전에 대조의 식별성을 한 라운드 더 확정하는 것이 타당하다.

우선 검토할 대조는 제공 목록만을 기준으로 하는 명시적 좌표 판단에서 영상 유무를 맞춰 비교하고, 필요하면 bbox를 계산된 중심으로 바꿔 산술 부담을 분리하는 것이다. 중심 제공도 시각적 전이 증거가 아니며, 정답 사분면 제공은 답 읽기 sanity에만 해당한다. 여러 prompt를 시도해 가장 높은 점수를 선택하는 설계는 피한다.

지정 범위 bbox 선택은 yes/no 출력의 영향을 줄이는 가까운 대안이다. 그러나 전체 bbox를 그대로 복사해도 높은 점수가 나오는지, 영역별 선택이 실제로 필요하도록 정답을 구성할 수 있는지 확인해야 한다. 이 비교가 끝나기 전 구현 계획을 확정하지 않는다.

## 다음 라운드에서 확정할 것

추가 조사는 광범위한 문헌 검색이 아니라 대조 행렬·정답 타당성·진입 조건에 집중한다. D24와 기존 주석으로 선택 과제의 식별 가능성을 확인하고, 좌표 판단 대조와 비교해 하나의 실행 설계를 고른다. 양성·음성·불확정에 따라 E 탐색, 가까운 과제 전환, 현재 인터페이스 진단 종료를 구분해야 한다.

두 GPU 사용 권한과 단계별 확대 정책은 유지한다. 구현 계획에는 실제 D 요청의 2/4 worker 또는 batch 비교, worker당 측정 peak+2GiB 여유, 긴 출력 정합성, 전체 처리량을 포함한다. 이번에는 새 처리량을 측정하지 않았으며 임의의 시간 상한을 만들지 않는다.

## 대규모 GPU 필요 후보

영역 질의·grounding·일반 QA를 결합한 encoder–언어 모델 공동 post-training은 후보로 보존한다. 현재 필요성과 새 기여는 미확정이다. 기존 checkpoint 진단과 강한 외부 규칙 baseline이 보여주는 구체적 단절을 먼저 확인해야 투자 근거가 생긴다.

## 다음에 파고들 질문
- 명시적 제공 목록 기반 판단에서 bbox/계산된 중심과 영상 유무를 어떻게 최소한으로 조합해야 산술 부담과 영상·evidence 관계를 구분할 수 있는가? 각 대조가 통과하거나 실패했을 때 전이 평가에 허용되는 결론은 무엇인가?
- 기존 D24 및 개발 주석에서 지정 범위 bbox 선택은 전체 목록 복사·위치 prior와 구별되는가? 영역별 선택이 필요한 환자 수와 부분집합 분포를 확인했을 때 사분면 yes/no 보정보다 정보 이득이 큰가?
- 선택한 진단의 D gate, E 진입·조건부 확대·보류 기준을 어떻게 고정할 것인가? 답 읽기 sanity만 통과한 상태에서 공간 전이를 주장하지 않으면서, 다시 준비 단계만 반복하지 않도록 어떤 실제 GPU 비교까지 완료해야 하는가?
