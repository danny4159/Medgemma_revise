# 요약

- **이번에 할 일:** 기존 M0와 RSNA SFT B0에 네 영역별 bbox 선택을 요청한다. 학습한 bbox 출력 형식을 유지하면서 요구하는 대상만 바꾼다.
- **필요한 이유:** SFT의 bbox 개선은 유효하지만 미학습 질의 전이는 미확인이다. 저장 bbox+규칙은 E200 진부분집합 환자 26/66명에서 네 질의를 모두 맞힌다.
- **확인할 기준:** 직접 성능, 네 질의 전체 정답, 동일 출력의 질의 배정 대조와 환자 영상 대응 대조를 함께 본다. B0−M0 차이만으로 선택 능력을 선언하지 않는다.
- **주의·다음:** 이번은 개발 진단이다. oracle 실패는 전이 실패와 구분한다. D→E60→조건부 E200·기존 seed 재현을 진행하며 새 학습·reserve·MRI F139는 열지 않는다.

# Current Understanding

iter_012의 RSNA 직접 LoRA SFT 개선은 유효하다. 확인 양성 400명에서 base official F1@0.3은 0.1650, SFT 세 seed는 0.6308–0.6528이었다. iter_013–014의 추가 loss 결과는 이 성과를 기각하지 않는다.

이미 답한 질문은 전역 QA의 형식 효과와 검출·개수·좌표 packet의 영향이다. iter_015–018의 Q_O/Q_A 및 evidence 실험을 반복하지 않는다. 아직 답하지 못한 질문은 같은 소견·같은 영상에서 요청 영역이 바뀌면 SFT가 관련 병변만 반환하는가이다.

iter_025의 yes/no 좌표 oracle과 현재 prompt 탐색은 종료한다. 기존 출력의 thinking marker 보정 분석은 별도 경로에 남기되 원점수·gate를 바꾸지 않는다. AR 성공은 답 읽기 sanity다.

이번은 같은 RSNA 전이 접근법의 후속 진단이므로 현재 branch를 유지한다. 새로운 bbox 선택 spec과 결과는 `results/iter_026/`에 분리한다. 사용자 보완의 기존 성과·checkpoint·분할 보존과 RSNA 진단 우선순위를 유지한다.

# Strategy Check / 연구 방향 판단

중요한 능력은 의료 영상에서 학습한 위치 정보를 새로운 선택 요청에 사용하는 것이다. 임상 reasoning이나 모든 공간 이해를 평가하는 과제는 아니다.

1. **현재 grounding 방법 개선:** 새 loss는 검출 개선과 질의 활용의 차이를 답하지 못한다. 지금 투자하지 않는다.
2. **기존 checkpoint 진단:** bbox 형식을 유지하면 기존 yes/no 형식과 다른 관찰을 얻는다. 강한 규칙 baseline, 복사 대조와 진부분집합 환자가 있어 다음 선택을 구분할 수 있다. 이를 선택한다.
3. **다른 연구 질문:** 큰 목표 안에서 가능하지만, 현재 사용자 우선 질문을 해결할 가까운 대조가 남아 있다. 지금 전환할 근거는 부족하다.

판단의 새 근거는 라운드 1의 복사 confound와 라운드 2의 Q4_select 재집계다. E200 진부분집합에서 B0 규칙은 26/66명, M0 official 규칙은 0/66명이다. 직접 선택과 외부 계산의 차이를 확인할 가치가 있다.

새 bbox 형식도 해석 가능한 출력을 만들지 못하거나 E200 후 남은 불확실성을 현재 자산으로 줄일 가치가 없으면 이 인터페이스의 투자를 종료한다. loss나 다른 임상 과제를 자동 예약하지 않고 미해결 범위와 대안을 보고한다.

# Hypothesis

주가설은 B0가 M0보다 미학습 영역 선택을 잘 수행하며, 그 성과에 질의에 맞춘 선택과 환자 영상의 기여가 포함된다는 것이다.

경쟁 설명은 다음과 같다.

- B0는 전체 bbox를 반복하지만 검출 성능이 높아 영역 점수도 높다.
- 영역 이름에 따른 위치 prior만 출력한다.
- 직접 생성은 불안정하지만 bbox+규칙 또는 bbox+영상 reader로 충분하다.
- 형식·지시 해석의 문제가 남아 시각 전이에 관한 결론을 내릴 수 없다.

양성 결과의 명칭은 '미학습 질의에 대한 기능적 전이'다. 기존 선택 정책에 좋은 검출이 결합된 경우와 새로운 선택 정책 획득을 완전히 분리하지 못하므로 내부 원인을 단정하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`의 validated 범위는 정상 사용 조건의 RSNA 위치 오류와 직접 SFT 개선이다. `rsna-quadrant-oracle-interface`는 D24의 observed 현상이다. 이번은 새 방법 개발이 아닌 diagnostic이며, 후자를 일반적 공간 능력 결함으로 승격하지 않는다.

모델은 `google/medgemma-1.5-4b-it`, revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`로 고정한다. bf16, greedy, 값 보존 RGB·padding, 공식 chat template과 1000→2000→4000 EOS ladder를 유지한다. 최종 비EOS는 invalid다.

보존 공식 출처는 `results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb`다. 원문은 [공식 anatomy notebook](https://raw.githubusercontent.com/Google-Health/medgemma/main/notebooks/cxr_anatomy_localization_with_hugging_face.ipynb)에 연결한다. 로컬 notebook·processor·template·generation config hash를 기록한다.

실제 D 영상과 이번 prompt에서 공식 messages를 독립적으로 구성하고 공식 pipeline 전처리 경로와 실제 worker 입력의 `input_ids`, `attention_mask`, `pixel_values`, `token_type_ids` 등 존재하는 tensor를 대조한다. 동일 helper를 두 번 호출하는 검사는 독립 대조로 인정하지 않는다. text-only 대조는 공식 text-only 구성과 비교한다.

B0 adapter 파일 hash·tensor digest·LoRA 대상과 실제 로드를 확인한다. 저장 D bbox 중 사전 hash로 고른 M0/B0 각 4건을 재생성해 기존 token과 비교한다. 불일치하면 원인을 확인한 뒤 진행하며 기존 본실험을 전수 재실행하지 않는다.

# Contribution Path / Baselines / Reuse

## 기여와 비교 범위

[Targeted Visual Prompting](https://arxiv.org/html/2408.03043v1)은 영역 입력과 위치 prior 문제를 이미 다룬다. [CURE](https://arxiv.org/html/2601.15408v1)는 grounding 관련 과제들을 명시적으로 학습한다. 영역 표시나 다중 과제 SFT 자체를 신규 기여로 주장하지 않는다. 현재의 차이는 bbox-only 적응 후 미학습 선택 요청에 대한 기능적 전이 여부다.

실용 비교군은 다음과 같다.

| 조건 | 입력과 역할 |
|---|---|
| V_M0, V_B0 | 같은 원본 영상과 영역 선택 prompt의 직접 생성 |
| R_M0_official, R_M0_concise, R_B0 | 저장된 전체 bbox를 중심 사분면으로 규칙 필터 |
| Copy_M0, Copy_B0 | 저장된 전체 bbox를 네 질의에 그대로 반환 |
| Empty | 네 질의 모두 빈 목록 |
| Reader_M0 | 원본 영상+B0 예측 bbox+영역 요청; 영상 기반 수정·재검출 허용 |
| O_M0, O_B0 | D 전용 GT 목록+원본 영상; 제공 목록만 선택하는 oracle |

reader는 전용 detector+VLM이라고 부르지 않는다. B0는 RSNA SFT VLM이다. reader가 원본 영상과 proposal을 사용하도록 허용해 비교군을 약하게 만들지 않는다. reader와 direct의 문구가 다르므로 두 조건의 차이를 bbox packet만의 인과 효과로 해석하지 않는다.

직접 경로는 환자당 4회 생성, 규칙 경로는 전체 bbox 1회 생성 후 네 계산, reader는 전체 bbox 1회와 reader 4회다. 재사용 출력도 원래 생성 비용을 구분해 보고한다. 학습량은 각 기존 checkpoint의 기록을 그대로 제시한다. 후속 방법의 가치 주장에는 직접 질의 SFT와 적절한 detector/encoder+head 비교가 별도로 필요하다.

## 재사용

현재 HEAD `89b2975a679c6eed3d9a356d2c01d85b7950a1bf`의 현재 branch를 유지한다. 필요한 파일이 존재하므로 `reuse_assets=[]`다.

- 기하·parser·metric·adapter: `rsna_diag/{__init__,geometry,parse,metrics,lora}.py`.
- 모델 입력·출처·소유권: `rsna_diag/{generate,prompts,inputs,eval_gate,queue_lock,lock_protocol}.py`.
- 분할·주석·기존 bbox 연결: `rsna_diag/roi23_data.py`, `roi23_spec.py`.
- 현재 실행 패턴: `rsna_diag/{roi25_requests,roi25_protocol,roi25_gen,roi25_run}.py`, `sanity_iter025.py`.

전체 runner는 승인본이 아니다. 아래 Implementation Tasks의 공식 입력·재개·필수 provenance·평가 완전성 결함을 해결한 경로만 사용한다. 기존 실행기를 재사용하면서 새 spec·평가·단계 정책을 연결한다. 사본 runner를 불필요하게 늘리거나 MRI·학습 실행기를 정비하지 않는다.

B0는 `results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt`이며 SHA256은 `5f542af96df705e567bf4cfb000398b09313db2456c577e772bd76481799cf29`다. 조건부 B29/B43은 같은 경로 패턴의 s29/s43 epoch_05를 사용한다. 각각 SHA256은 `d4db2f2ab10d134b4352c7f57cc0ca5c497da3bce388d9cc91751ec9ca6d1fc9`, `e6e4730add1d942c81fb89aabd5477a779668d2f0f8ef01cc21af33032584f4a`다.

# Proposed Experiment

## 1. 데이터와 요청 고정

`results/iter_023/manifests/{sets,labels}.json`의 D24, E60, E200을 유지한다. E60은 E200의 부분집합이며 E200은 primary 160명과 boundary 40명이다. 원본 주석·manifest와 연결하고 환자 ID 및 decoded pixel 중복을 검사한다. 이들은 기존 결과로 선택·분석한 개발 자료이며 새 독립 확인이 아니다.

primary는 기존 모든 GT 중심의 midline margin≥25 규칙을 유지한다. boundary를 삭제하지 않고 별도로 평가한다. 여러 사분면에 GT가 있는 진부분집합 환자는 E60 primary 22명, E200 primary 66명이다. 각 집단은 출력 확인 전에 고정한다.

모든 환자에게 TL/TR/BL/BR 네 질의를 모두 요청한다. 영역 위치·크기는 GT나 예측을 보고 고르지 않는다. 위치는 표시 영상 기준이며 해부학적 좌우가 아니다. bbox 중심으로 배정하고 500 경계는 lower/right다. GT는 기존 float 좌표를 유지한다.

직접 prompt는 다음 한 종류로 고정한다. `{quadrant}`와 `{condition}`만 네 영역에 맞춰 치환한다.

`Localize all pulmonary opacities suspicious for pneumonia whose bounding-box centers are in the {quadrant} quadrant of this chest radiograph. Divide the displayed image at its horizontal and vertical midlines. Left and right refer to the displayed image, not the patient's sides. For a box [y_min, x_min, y_max, x_max], its center is cy=(y_min+y_max)/2 and cx=(x_min+x_max)/2. The requested quadrant satisfies {condition}. Return only a JSON list. Each entry must contain "box_2d": [y_min, x_min, y_max, x_max] and a nonempty "label" string. Coordinates must be between 0 and 1000 relative to the entire square-padded image, with y before x. Return the full enclosing boxes; do not clip boxes to the quadrant. Exclude opacities centered in other quadrants. Return [] if no such opacity is visible in the requested quadrant.`

조건은 각각 `cy<500 and cx<500`, `cy<500 and cx>=500`, `cy>=500 and cx<500`, `cy>=500 and cx>=500`이다. 예시 정답·정답 사분면·환자별 GT 정보는 direct에 넣지 않는다.

oracle은 D의 GT를 기존 schema 목록으로 제공하고 '제공 목록만 선택하며 좌표를 수정하거나 재검출하지 말라'는 공통 prefix를 사용한다. reader는 B0 예측을 불완전할 수 있는 proposal로 명시하고 원본 영상에 근거한 추가·수정을 허용한다. 각 prefix는 첫 실행 전에 spec에 고정한다. reader에 unavailable source가 있으면 이를 명시하고 별도 분류하며 빈 목록으로 위장하지 않는다.

parser는 기존 `parse.py`를 사용한다. 모순된 여러 목록, 잘린 출력, 잘못된 좌표를 임의 구제하지 않는다. 예측 box를 평가 전에 요청 영역으로 자동 필터하거나 clip하지 않는다. 반복 box도 FP 분모에 남긴다.

## 2. 동작 확인: D24

D24에서 다음을 실행한다.

- M0/B0 직접 선택: 24×4×2=192요청.
- M0/B0 GT 목록 oracle: 192요청.
- M0 reader: 96요청.
- M0/B0 text-only 직접 prompt: 환자 정보를 넣지 않은 네 prompt씩 총 8요청. 반복된 동일 prompt를 환자별 독립 생성으로 세지 않는다.

정식 D 합계는 488요청이다. text-only 출력은 위치·문구 prior의 참고 대조이며 임상 음성을 뜻하지 않는다.

E60 진입은 다음 모두를 요구한다.

1. 공식 입력·adapter·기하·source 연결 검증 통과.
2. 실제 중단·재개, 완료 재사용 및 변조 거부 검증 통과.
3. 독립 예상 행렬과 완료 출력의 누락·중복·잉여 0, 모든 worker 종료 코드 0.
4. 직접 M0와 B0 각각 96요청 중 bbox 형식 valid≥92건. 이는 비교 가능한 출력 확보 기준이며 능력 성공 기준이 아니다.

oracle의 정답률과 reader의 성능은 E 진입 gate에 넣지 않는다. oracle 실패는 원인 해석의 한계로 기록한다. direct gate 실패 시 이번 고정 인터페이스의 본평가를 보류하고 추가 prompt 탐색을 자동 수행하지 않는다. 내용상 빈 목록은 형식 valid로 보되 능력 성공으로 세지 않는다.

## 3. 가능성 탐색: E60

고정 M0/B0와 reader를 E60 전체 60명에 적용한다. 60×4×3=720요청이다. primary 48명과 boundary 12명을 분리하며, primary 진부분집합 22명을 반드시 보고한다.

저장된 M0 official_long/concise 및 B0 concise bbox에서 규칙·복사 baseline을 계산한다. source 누락은 실행 오류이며 모델 invalid와 구분한다. 기존 출력이 유효한 빈 목록인 경우와 parser 실패인 경우를 별도 보고한다.

평가는 E60 완료 시 한 번 수행한다. 부분 결과로 prompt·parser·checkpoint를 바꾸지 않는다.

## 4. 규모 확대: E200

E60의 실행 유효성이 확보되고 직접 각 모델의 형식 valid≥95%일 때 다음 중 하나면 E200으로 확대한다.

- 기능적 차이 후보: primary에서 |S_B0−S_M0|≥0.05이고 적어도 한 모델의 C_query 점추정≥0.05.
- 정밀도 보완: 진부분집합에서 B0 규칙 Q4_select≥0.20이며 직접 B0 Q4_select의 95% exact 구간이 0.10을 포함한다. 22→66명 확대로 현재 인터페이스에서 10% 수준의 전체 선택 가능 여부 판단을 바꿀 수 있다.
- 모듈형 격차 후보: primary에서 규칙 또는 reader가 B0 direct보다 S가 0.10 이상 높고, B0 direct에 C_query>0 또는 진부분집합 Q4_select>0의 실제 선택 사례가 있다. 격차와 부분적 전이를 함께 평가할 가치가 있다.

0/22명이라는 이유만으로 전이 부재를 선언하지 않는다. two-sided 95% exact 상한은 15.44%이며 0/66명에서는 5.44%다. 0.05 F1 차이와 10% 전체 선택은 다음 투자 판단을 위한 사전 기준으로, 임상적 수용 기준이 아니다.

조건을 충족하면 E200의 남은 140명×4×3=1,680요청을 추가한다. E60 출력을 재사용해 총 2,400요청으로 집계한다. primary 160명, boundary 40명, 진부분집합 각각 66명·24명을 보고한다. E60과 E200을 독립 재현 두 번으로 세지 않는다.

확대 조건을 충족하지 않으면 효과·정밀도·형식 중 무엇 때문에 보류했는지 기록한다. 효과 상한이 작지 않으면 전체 접근법 실패로 일반화하지 않는다.

## 5. 조건부 기존 seed 재현

E200에서 아래 Evaluation의 양성 조건을 만족하거나, 형식과 oracle 해석이 확보된 상태에서 규칙 대비 명확한 직접 활용 격차가 확인되면 기존 B29/B43을 평가한다. 명확한 격차는 R_B0−V_B0의 S 차이≥0.10이고 95% paired CI 하한>0인 경우다.

두 seed를 모두 E200 전체에 직접 선택으로 평가한다. 추가 200×4×2=1,600요청이며 해당 seed의 저장 전체 bbox로 규칙·복사 baseline도 계산한다. 유리한 seed만 선택하지 않는다. 환자 수와 seed 수를 곱해 독립 표본 수로 쓰지 않는다.

oracle 실패·형식 문제 때문에 원인 해석이 불가능하거나 환자 표본의 불확실성만 남았다면 seed 추가를 자동 실행하지 않는다. seed 증가는 환자 정밀도 부족을 해결하지 못한다.

## 6. 독립 확인과 학습

이번 학습량은 0이다. M0, seed17 및 조건부 seed29/43의 기존 checkpoint만 사용한다.

이번에는 독립 확인을 실행하지 않는다. 기존 reserve와 MRI F139를 보존한다. 기능적 전이나 재현되는 중요한 단절이 확인되면 같은 소견을 평가할 다른 원천 데이터와 새로운 독립 집단의 접근·주석 타당성·중복을 다음 계획에서 검토한다. 개발 집단의 양성 결과를 최종 contribution으로 보고하지 않는다.

# Implementation Tasks for Claude

1. 실행 호스트에서 기존 PID/starttime·lock·worker 종료 상태를 확인한다. 살아 있는 작업을 중복 실행하거나 claim을 지우지 않는다. 새 산출물은 모두 `results/iter_026/`에 둔다.
2. 현재 파일과 CODE_ASSETS의 승인 범위를 확인하고 기존 실행 경로에 새 spec·요청·평가·decision을 연결한다. 과거 protocol·원시 출력은 수정하지 않는다. iter_025 D protocol의 AR 추가 차이는 검증 가능한 before/after 호환 기록으로만 설명한다.
3. source manifest·GT·sets·이미지 hash·checkpoint 파일/tensor digest·기존 bbox 원시 파일·completion·공식 notebook·실제 호출 코드·spec·parser·평가기·단계 decision을 필수로 잠근다. optional extra 전달에만 의존하지 않는다. stage·checkpoint·condition·split도 request provenance에 포함한다.
4. 평가기는 요청 파일의 관측 ID가 아니라 잠긴 manifest와 실험 spec에서 예상 행렬을 독립 재구성한다. 요청·원시 출력·completion과 현재 provenance를 비교하며 누락·중복·잉여·잘못된 stage를 거부한다. 완료 파일 존재만으로 재사용하지 않는다.
5. D/E60/E200/seed 진입점과 직접 worker 실행 모두 선행 decision을 강제한다. 평가 시에도 선행 decision의 hash·내용을 검증한다. 프로토콜을 잠근 뒤 실행 중 소스를 추가 수정하지 않도록 필요한 조건을 먼저 구현한다.
6. 실제 D 입력의 독립 공식 tensor 대조, adapter 연결과 8건 bbox sanity를 수행한다. 전처리 왕복, 사분면 경계, 순서가 바뀐 목록, 중복 box, 잘린 출력, thinking marker, ambiguity를 검증한다.
7. D의 고정 24요청으로 무중단 기준 실행과 worker 중단·재개 및 부모 종료·재개를 비교한다. M0/B0와 네 영역, 빈·비빈 GT를 포함한다. 완료 요청의 token/provenance 일치, 누락·중복 0, 자식 회수, 원자적 완료 기록을 확인한다. 해당 검사에서 재생성되는 요청 수를 별도 기록한다.
8. source·adapter·request·decision·completion 변조 및 부분 JSONL tail, 살아 있는 다른 worker 소유 파일을 다루는 검사를 수행한다. 완료 요청에도 현재 입력 검증을 적용한다. 복구는 소유권을 확보한 새 attempt에서 원본을 보존하며 수행한다.
9. metric은 별도 작은 기준 구현으로 대조한다. 완벽한 분할은 S=1·Q4_select=1, 완벽한 전체 GT 복사는 S=0.4·Q4_select=0·C_query=0, 빈 목록은 S=0·Q4_select=0·C_query=0이어야 한다. 질의 순열·환자 쌍 교환·invalid 처리와 통계 분모를 검사한다.
10. iter_025의 marker 뒤 최종 yes/no 답과 paired 정확도 분석을 별도 파일로 보완한다. 원래 점수·gate를 고치거나 GPU 출력을 재생성하지 않는다. 이 분석을 새 실험의 진입 조건으로 삼지 않는다.

## GPU 배치와 비용

실행 직전 `nvidia-smi`로 허용 장치 0,1의 실제 여유와 다른 프로세스 점유를 확인한다. 여유가 큰 GPU부터 배정하며 상속된 허용 집합과 논리/물리 매핑을 지킨다.

D에서 같은 48요청을 총 2 worker와 4 worker로 비교한다. 각 비교에는 M0/B0, 네 영역과 직접·목록 조건을 균형 있게 포함한다. 모델별 동일 요청 집합을 유지하며 전체 로딩·종료 시간을 포함해 집계한다. batch 탐색까지 전수 추가하지 않는다.

측정 항목은 전체 req/min, 로딩 포함 wall-clock, 긴 출력 지연, worker별 allocated/reserved peak, 장치 전체 실제 peak, CPU/RAM/I/O 경합, OOM과 greedy token 정합성이다. 4000-token 상한까지의 KV 메모리는 D 기반 별도 stress로 검증하고 성능 결과에 섞지 않는다.

각 GPU에서 동시 worker의 실측 peak 합계+다른 점유+worker당 최소 2GiB 여유가 용량 안에 있어야 한다. 참고 추정은 약 8–10GiB/worker이며 새로운 prompt의 보장은 아니다. 안전성과 token 정합성을 유지하며 총 처리량이 개선되는 구성을 선택한다. 4 worker가 느리거나 안전 여유가 부족하면 두 GPU 각 1 worker를 쓰고 근거를 남긴다.

정식 요청 수는 D 488, E60까지 1,208, E200까지 2,888, 조건부 두 seed까지 최대 4,488이다. 처리량 비교 96건, bbox sanity 8건, 재개 기준·재실행과 stress는 별도 계상한다. D pilot을 정식 D로 편입하려면 요청·코드·protocol 연결이 완전히 동일해야 하며 다른 attempt의 출력을 임의 병합하지 않는다.

과거 iter_025의 로딩 포함 처리량 약 9–12 req/min을 참고하면 최대 정식 생성은 약 6.2–8.3시간이다. 새 bbox prompt의 실측 전 추정이며 준비·검사·긴 출력 비용은 추가된다. D 실측으로 남은 요청/처리량과 로딩 비용을 다시 산출한다. 임의 시간 상한은 두지 않는다.

요청별 append와 stage checkpoint로 재개한다. 진행량·실패·메모리·자식 종료 코드를 기록한다. OOM이나 진행 정체 시 소유 프로세스를 안전하게 회수하고 batch/동시성을 낮춘 새 attempt로 재개한다. 가설·표본·출력 길이·성공 기준은 자원 조정 때문에 바꾸지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표 정의

환자 i의 GT를 중심 사분면으로 G_iq에 나누고 직접 출력 목록을 P_iq로 둔다. IoU≥0.3이며 예측 중심도 요청 사분면에 속하는 쌍만 일대일 최대 cardinality matching한다. tie-break는 총 IoU, 이후 고정 index 순으로 결정한다.

`S_i = 2 × Σq TP_iq / (Σq |P_iq| + Σq |G_iq|)`.

요청 밖 예측도 예측 수 분모에 남긴다. 네 응답 중 하나라도 invalid면 primary S_i=0으로 처리하고 invalid 종류를 별도 보고한다. 모든 대상 환자는 주석 양성이므로 빈 GT 분모 문제는 없다. 환자 평균 S를 사용한다.

`Q4_select_i=1`은 네 응답이 모두 valid이고 각 영역에서 TP=예측 수=GT 수일 때만 성립한다. primary 전체와 사전 고정 진부분집합에서 각각 보고한다. 진부분집합이 선택 능력의 핵심 stress 집단이다.

`C_query_i = S_i(실제 질의 배정) − mean_{π∈24개 순열} S_i(네 출력 목록의 배정 π)`.

재배정에는 예측 목록만 이동시키며 GT와 요청 영역은 고정한다. invalid 환자는 모든 배정 점수와 C_query를 0으로 둔다. 같은 목록을 반복하면 C_query=0이다. 이 대조에는 새 GPU 출력이 없다. C_query의 모델 간 크기 차이 자체는 순수 선택 능력의 인과 효과가 아니다.

추가로 IoU≥0.5, 빈/전체/진부분집합 질의별 정확도, 요청 밖 FP, 복사율, 빈 출력률, 형식·EOS 실패와 영역별 결과를 보고한다. 주지표를 사후 교체하지 않는다.

## 환자 영상 대응 대조

각 단계의 primary와 boundary 안에서 `SHA256('iter026-pair-v1|'+patient_id)` 순으로 정렬하고 인접한 두 환자를 짝짓는다. 쌍 안에서 동일 질의의 네 출력 전체를 교환해 donor 점수를 계산한다. mapping은 생성 결과 확인 전에 고정한다. 이 대조는 prompt에 환자별 GT·ID가 없는 direct에만 적용한다.

원본 영상 대신 다른 실제 영상에 대한 출력을 연결했을 때의 점수 저하를 본다. 영상 인과 메커니즘 전체를 증명하지 않지만 고정 위치 prior 설명을 약화할 수 있다. E60과 E200의 mapping은 각각 사전 고정하며 donor 결과를 독립 표본으로 추가하지 않는다.

## 통계

primary 환자별 paired bootstrap 10,000회, 분석 seed 26026으로 S·C_query·모델 및 baseline 차이의 95% CI를 구한다. Q4_select 성공률에는 exact binomial CI, paired 차이에는 환자 bootstrap과 discordance 수를 함께 보고한다. donor 차이는 교환 쌍을 cluster로 bootstrap한다.

진부분집합·boundary는 별도 분모로 보고한다. 모든 출력이 같아 bootstrap이 [0,0]이면 모집단 효과의 영점으로 해석하지 않는다. 이진 지표에는 exact 구간을 병기하고 연속 지표의 확대 판단을 퇴화 bootstrap만으로 결정하지 않는다. 여러 개발 비교의 CI는 독립 확증이나 다중 비교 보정된 검정으로 제시하지 않는다.

## 양성 결과와 다음 행동

E200 primary에서 다음이 함께 성립하면 기능적 전이의 양성 후보로 판정한다.

- V_B0−V_M0의 S 차이≥0.05이고 paired CI 하한>0.
- V_B0−Copy_B0의 S 차이≥0.05이고 paired CI 하한>0.
- B0 C_query의 CI 하한>0.
- 진부분집합 B0 Q4_select 점추정≥0.10이며 실제 성공 환자가 존재한다.
- B0의 실제 영상 대응 S−donor S의 CI 하한>0.

기존 두 seed 재현 후 같은 소견의 외부 자료와 직접 질의 SFT·모듈형 비교를 다음 계획에서 검토한다. 새 선택 알고리즘 획득·임상 reasoning·top-tier contribution의 증명으로 확대하지 않는다.

## 음성 결과와 다음 행동

형식·실행 검증이 유효하고 E200 진부분집합에서 B0 직접 Q4_select의 exact CI 상한<0.10인데 B0 규칙의 하한>0.20이면 현재 인터페이스의 신뢰할 만한 전체 선택이 제한된다는 근거다. C_query나 부분 F1이 양성이면 부분적 전이는 함께 인정한다.

oracle에서도 목록 선택이 실패하면 지시·좌표 인터페이스 설명이 남는다. 일반적 시각 전이 실패로 결론내리지 않는다. oracle의 형식과 비빈 진부분집합 선택이 잘 되지만 direct가 규칙보다 크게 낮으면 직접 활용의 단절을 후속 원인·방법 후보로 기록한다. oracle을 사후 gate로 사용하지 않는다.

규칙이나 reader가 직접 경로보다 충분히 좋으면 강한 모듈형 baseline으로 보존한다. 더 복잡한 loss를 자동 추가하지 않는다. 내부 활용의 추가 가치가 필요한 사용 조건이 있는지 다음 전략 판단에서 검토한다.

## 불확정 결과와 다음 행동

E60에서 표본 때문에 양성·음성이 갈리면 위 사전 규칙으로 E200을 실행한다. E200에서도 CI가 투자 기준을 가로지르면 표본, seed, 형식 또는 과제 식별성 중 남은 원인을 명시한다. 환자 정밀도만 부족할 때 seed를 늘려 해결한 것처럼 보고하지 않는다.

형식 gate 실패는 현재 인터페이스의 평가 보류다. provenance·재개·입력 연결 실패는 실행 오류이며 복구 후 동일 계획을 이어간다. 두 경우 모두 SFT 전체의 실패가 아니다.

# Risks / Checks

- RSNA 주석의 불완전성과 bbox 경계 모호성은 남는다. 빈 영역 응답을 임상적으로 정상이라는 판단으로 바꾸지 않는다.
- primary만으로 경계 사례의 성능을 숨기지 않는다. boundary와 IoU@0.5를 별도 보고한다.
- GT oracle·직접 입력·reader packet을 구분하고 GT가 direct 요청에 들어가지 않도록 검사한다.
- 전체 복사보다 나은 F1만으로 새로운 선택 능력을 주장하지 않는다. Q4_select·C_query·영상 대응 근거를 함께 유지한다.
- E60/E200은 개발 자료다. 환자·영상 중복 검사와 사전학습 미노출은 다른 주장이다.
- 현재 전체 코드 스냅샷은 재사용 승인본이 아니다. 실제 호출 경로의 필수 결함만 해결하고 근거를 SHA·protocol에 연결한다.
- 이번 완료는 진단 반복의 완료이며 연구 목표 달성이 아니다. 보고서에는 실제 도달 단계, 계획 대비 요청 수·비용, 확대/보류 이유와 독립 확인 미실행을 명시한다.

## 대규모 GPU 필요 후보

vision encoder와 언어 모델을 함께 적응시키는 영역 선택·grounding·일반 QA 공동 post-training을 후보로 보존한다. 대규모 다기관 자료와 충분한 batch·seed 재현에는 더 큰 메모리·처리량이 필요할 수 있다. 이번 진단이 필요성을 지지하는지부터 확인하며 현재 두 GPU에서 가능한 경량 적응을 배제하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 이번 라운드의 결론

영역 선택 진단을 구현할 근거가 확보됐다. 직접 B0−M0 점수만으로 전이를 선언하지 않고, 네 질의 전체 정답·동일 출력의 질의 배정 대조·환자 영상 대응 대조를 함께 사용한다. 목록 oracle 성능은 직접 평가의 진입 gate에서 분리한다.

이번 라운드는 문서·소스·보존 notebook 조회와 저장 결과의 읽기 전용 재집계만 수행했다. 파일 생성·수정, 모델 로딩, 추론·학습·테스트 실행은 하지 않았다.

## 질문 1: 검출 개선과 선택을 어떻게 구분하는가?

라운드 1에서 확인한 B0 전체 복사 점수는 M0 bbox+규칙보다 높다. 따라서 직접 모델 간 영역 F1 차이만으로 질의 이해를 주장할 수 없다.

새 설계는 세 근거를 결합한다.

- 환자별 네 응답을 함께 채점하는 Q4_select: 모든 영역에서 정답 목록과 일대일로 대응하고 잉여 box가 없어야 성공한다. 여러 영역에 GT가 있는 환자에서는 전체 복사와 빈 목록이 모두 실패한다.
- 동일한 네 생성 목록을 24가지 질의 배정으로 재채점한다. 실제 배정의 F1에서 24개 배정 평균을 뺀 C_query를 계산한다. 출력과 검출량은 고정되므로 전체 목록을 반복하는 모델은 검출이 아무리 좋아도 C_query=0이다.
- 모든 환자에게 동일한 네 prompt를 사용하므로, 다른 환자의 동일 질의 출력을 현재 환자 GT와 대조할 수 있다. 사전 고정한 환자 쌍 교환으로 위치 prior만으로 설명되는 정도를 평가한다. 추가 GPU 생성은 필요 없다.

이 조합은 검출 개선과 질의 무시만으로 생기는 양성을 배제하는 데 유용하다. 다만 기존 선택 정책에 더 좋은 검출이 결합된 경우와 새로운 선택 정책을 학습한 경우는 완전히 분리하지 못한다. 양성 결론은 '미학습 질의에 대한 기능적 전이'로 제한한다.

## 질문 2: D gate와 oracle의 역할

현재 `parse.py`는 bbox JSON과 완결 thinking marker를 처리한다. `roi25_spec.py`의 yes/no 형식 문제를 bbox 경로의 동일한 결함으로 취급하지 않는다. 직접 선택은 기존 concise의 target·좌표·JSON schema를 유지하며 영역 제한만 추가한다.

D에서는 직접 영상 선택, GT 목록 선택, 예측 bbox+영상 reader를 분리한다. 직접 비교의 진입 조건은 공식 입력·adapter·provenance·재개 검증 및 충분한 bbox 형식 유효율이다. 이전 yes/no oracle의 90% 정확도 기준은 가져오지 않는다. GT 목록 선택의 정확도는 해석 자료이며 직접 시각 평가를 막는 조건이 아니다. oracle 실패와 직접 실패가 함께 나오면 일반적 공간 전이 부재를 주장할 수 없다.

보존 공식 notebook의 실제 셀을 확인했다. image→text user content, greedy 생성, thinking marker 이후 응답 처리가 명시돼 있다. 현재 `generate.build_inputs`의 구조는 이에 대응하지만 실제 tensor 동등성은 구현 단계에서 독립 경로로 확인해야 한다.

## 질문 3: 22명에서 66명으로 확대할 가치

저장된 iter_012 bbox를 독립 IoU matching으로 재집계했다. 원본 출력 생성이나 기존 점수 수정은 하지 않았다. 아래 수치는 새 직접 선택 결과가 아니라 bbox+규칙의 달성 가능한 비교 성능이다.

| 집단 | M0 official Q4_select@0.3 | B0 규칙 Q4_select@0.3 |
|---|---:|---:|
| E60 primary 전체 48명 | 2/48 | 25/48 |
| E60 진부분집합 22명 | 0/22 | 11/22 |
| E200 primary 전체 160명 | 11/160 | 60/160 |
| E200 진부분집합 66명 | 0/66 | 26/66 |
| E200 boundary 전체 40명 | 1/40 | 19/40 |
| E200 boundary 진부분집합 24명 | 0/24 | 11/24 |

직접 선택이 0/22명이어도 성공률의 two-sided 95% Clopper–Pearson 상한은 15.44%다. 0/66명이면 5.44%다. 따라서 10% 수준의 신뢰할 만한 전체 선택이 가능한지를 판단할 때 확대가 결정을 바꿀 수 있다. 이 계산은 효과 예측이 아니며, 개발 집단을 독립 확인으로 바꾸지도 않는다.

출처: `research/results/iter_023/manifests/{sets,labels}.json`, `research/results/iter_012/confirm_base/gen_worker*.jsonl`, `confirm_sft_seed17/gen_worker*.jsonl`. matching은 IoU≥0.3과 GT·예측 중심 사분면 일치를 요구했다.

## 선행 방법 확인

[Targeted Visual Prompting](https://arxiv.org/html/2408.03043v1)의 §3.1을 재확인한 목적은 영역 위치·크기 prior의 위험을 설계에 반영하기 위해서다. 논문은 영역과 정답의 상관 및 Region in text의 낮은 성능을 논의한다. 이번에는 GT에 맞춰 영역을 고르지 않고 모든 환자에게 네 영역을 묻는다. prior 대조도 포함한다. 영역 지시 자체는 신규 기여가 아니다.

[CURE](https://arxiv.org/html/2601.15408v1)의 명시적 grounding·영역 관련 다중 과제 학습과 모델 표기 차이는 라운드 1의 확인을 유지한다. 같은 내용을 재조사하지 않았다. 두 문헌은 설계 근거이며 이번 단계의 사용자 논문 추천은 아니다.

## 재사용 상태와 범위

`research/` HEAD는 `89b2975a679c6eed3d9a356d2c01d85b7950a1bf`이며 status와 diff는 비어 있다. 현재 브랜치에 `roi23_*`, `roi25_*`, `generate.py`, `parse.py`, `geometry.py`, `lora.py`, `inputs.py`, `eval_gate.py`, `queue_lock.py`, `lock_protocol.py`, `sanity_iter025.py`가 있다. 별도 반입이 필요 없다.

라운드 1에서 검증한 B0/B29/B43 adapter 파일 경로와 SHA256을 유지한다. 이번에는 같은 큰 파일 hash를 다시 계산하지 않았다. 실행 직전 파일·tensor digest와 실제 adapter 연결을 검증한다.

`agent/CODE_ASSETS.md`와 iter_025 리뷰의 공식 tensor 대조, 실제 재개, 필수 source·decision 잠금, 평가 행렬 완전성 결함은 선택한 실행 경로에서 해결한다. 기존 원시 출력·protocol은 보존한다.

## 대규모 GPU 필요 후보

영역 선택·grounding·일반 QA를 결합한 vision encoder–언어 모델 공동 post-training은 후보로 보존한다. 필요성과 신규성은 미확정이며 현재 실험으로 예약하지 않는다. 큰 batch·다기관 자료·여러 seed를 포함한 공동 학습은 현재 두 24GB 장비보다 큰 메모리와 처리량이 필요할 수 있다. 경량 적응 전체가 불가능하다는 뜻은 아니다.

이전 사고 라운드 노트: agent/runs/iter_026/think/
