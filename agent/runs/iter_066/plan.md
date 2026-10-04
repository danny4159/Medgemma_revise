# 요약

- **이번에 할 일:** 기존 MRI W 질문에서 FLAIR 단독 F와 공동 입력 J를 고정하고, 두 답변의 likelihood를 비교하는 기존 baseline을 실행한다.
- **필요한 이유:** 공동 입력의 낮은 생성 점수에는 큰 형식 오류가 섞였다. 새 selector를 만들기 전에 영상 판별 신호가 실제로 부족한지 구분해야 한다.
- **확인할 기준:** 생성 대비 회복, F scoring 대비 성능, 위치 prior 및 case 대응 제거 대조를 넘는 영상별 신호를 확인한다.
- **주의·다음:** scoring은 기존 방법이다. 결과에 따라 baseline을 보존하거나 현재 경로를 종료하며, 학습·추가 prompt 탐색으로 자동 이어가지 않는다.

# Current Understanding

iter_065의 고정 정책 이득은 사전 기준 미달이었다. 현재 mask 기반 selector 투자의 종료와 HD subtype·전체 비용 비교의 미완결 판정을 유지한다.

동시에 MedGemma의 E48 W BA는 F 0.72872, J 0.13035였고, 두 질문을 합친 J invalid는 329/576이었다. 원시 출력에는 비EOS 반복 생성과 서술 뒤 명시 답변이 함께 존재한다. 계획 단계의 사후 점검에서 마지막 명시 답까지 읽으면 J의 W BA는 0.35955로 높아졌다. 이는 원 평가를 교체하는 수치가 아니라 인터페이스 혼입의 근거다.

iter_064의 명시적 target context 관찰은 다른 조건에서 얻은 것으로 유지한다. 이번 실험으로 해당 관찰의 원인이나 충분한 인식 이후의 선택 실패를 확정하지 않는다.

원 계획 `agent/runs/iter_065/plan.md`, SHA256 `5147dbce11958feef582f0d0c2587f8e3988ef3d48bf979df561134d4243af13`을 보존한다. 이번은 새로운 진단이며 원 gate·지표·판정을 수정하지 않는다.

# Strategy Check / 연구 방향 판단

**상위 질문:** 여러 관측에서 질문에 필요한 근거를 사용하는 능력이다. 현재 확인된 것은 생성 인터페이스의 큰 영향이며, 충분한 인식 이후의 선택·결합 실패는 아니다.

**관찰 → 경쟁 설명 → 최소 비교:** W/J의 큰 오류가 생성 형식에 주로 묶여 있는지, closed-answer scoring에서도 영상별 판별이 부족한지 비교한다. 같은 prompt와 영상에서 답변 readout만 바꾸고 위치 prior를 통제한다.

**세 선택:** selector·형식 학습은 기존 대안 이후의 부족함이 없어 보류한다. 즉시 다른 MRI 질문으로 이동하는 것은 가능하지만 현재 큰 오류를 설명하지 않은 채 기본 능력 부족으로 취급할 위험이 있다. 새 자료 없이 기존 scoring으로 한 번 확인하는 비교를 우선한다.

**타 계열 비교:** iter_062·064·065에서 Qwen 비교를 이미 수행했다. 이번 현상은 MedGemma의 큰 형식 실패에 초점을 맞춘다. Qwen의 동일 scoring을 추가해 모델 순위표를 만드는 것은 현재 결정에 필수적이지 않아 보류한다. 기존 Qwen W/F/J 생성 결과는 참고값으로만 보존한다.

**이번 결과가 바꿀 결정:** frozen MedGemma의 공동 MRI 입력을 기존 closed-answer baseline으로 유지할 가치가 있는가. 양성이어도 새 방법 필요성은 별도다. F가 충분하면 공동 입력 방법 투자를 종료한다.

**비용과 종료:** iter_065의 MedGemma E12/E36 생성 wall-clock은 약 6,319/17,355초였다. 이번에는 긴 생성 재실행 없이 최대 1,296 candidate forward로 한정한다. 구현·감사의 전체 누적 비용 비율은 측정되지 않았으므로 만들지 않는다. 동일 자료의 다음 parser·prompt·보정 탐색은 예정하지 않는다.

# Hypothesis

H1: 기존 answer likelihood baseline은 W/J의 생성 점수 저하를 상당 부분 줄인다.

H2: 회복된 점수가 위치 prior와 case 대응 제거 대조를 넘지 못하면, 형식 회복만으로 영상 활용이나 후속 방법 투자 가치를 주장할 수 없다.

H3: 영상별 신호가 남더라도 F scoring이 J와 비슷하거나 더 좋으면 이 과제에서 공동 입력을 위한 새 방법이 필요하다는 근거는 부족하다.

Likelihood 선택은 생성 정책과 평가 인터페이스를 함께 바꾸므로 순수한 parser 효과나 내부 인식 능력의 직접 측정으로 해석하지 않는다.

# Limitation Evidence / Correct Usage Checks

이번 직접 대상은 iter_065의 W/F/J 생성 관찰이다. 해당 리뷰는 VLM 비교를 유효하다고 판단했지만 전체 복합 결론에는 blocker가 있다. 이를 blocking 없는 method 근거로 승계하지 않는다. 따라서 `experiment_role=diagnostic`, `method_stage=none`, `limitation_ids=[]`로 둔다. 새로운 한계 등록 여부는 이번 full review에서 판단한다.

기존 `mri-explicit-target-context-effect`는 계보상 관련 관찰이며 현재 과제의 validated 근거로 대체하지 않는다.

필수 사용법 검사는 다음과 같다.

- 기존 W 정답, 구간, 등간격 z, F/J PNG와 표시 순서·정규화를 유지한다. W는 mask의 비배경 voxel 유무이며 임상 정상 여부가 아니다.
- 같은 chat template·processor·model revision을 사용하고 scoring prefix의 input_ids와 영상 tensor를 원 생성 입력에 연결한다.
- 후보 문자열은 정확히 `PRESENT`, `ABSENT` 두 개다. 추가 assistant 설명·답변 접두어·few-shot을 넣지 않는다.
- 전체 다중 영상 prefix와 후보 문자열의 token 경계, causal shift, padding 및 token_type_ids를 검증한다.
- teacher forcing에 넣는 후보는 양쪽 모두 동일하게 열거한다. 정답은 평가기만 읽는다.
- 기존 생성의 invalid와 최종 비EOS는 원 규칙대로 오답이다. scoring 결과로 원 생성 결과를 덮어쓰지 않는다.
- 모델의 정답률이나 100% oracle 정답을 기술 gate로 요구하지 않는다.

# Contribution Path / Baselines / Reuse

[ReForm-Eval](https://arxiv.org/html/2310.02569v2)은 생성과 답변 likelihood 평가를 이미 구분한다. iter_054에서도 같은 계열의 PS scoring을 검증했다. 따라서 이번 구현·점수 회복은 새로운 contribution이 아니다. 이 진단의 가치는 알려진 대안으로 설명되는 오류에 새 학습을 투자하지 않도록 하는 데 있다.

[MedGemma 1.5 공식 입력 방식](https://huggingface.co/google/medgemma-1.5-4b-it)을 유지한다. 향후 방법 투자가 필요해지면 강한 직접 SFT와 전문 대안 이후의 부족함을 별도 계획에서 확인해야 한다.

필수 baseline은 기존 strict 생성 G_F/G_J, 신규 scoring L_F/L_J, D6 전체 다수 class, D6 구간 위치별 다수 class다. prior 동률은 ABSENT로 고정한다. E 결과로 prior 규칙을 바꾸지 않는다.

영상별 신호는 같은 구간 위치에서 case 대응을 제거한 null과 비교한다. W/F 또는 W/J 안에서 모든 case의 prompt가 byte-identical한지 먼저 확인한다. 동일하다면 다른 case의 저장 score를 대응시키는 것이 그 donor 영상으로 새로 추론하는 것과 같은 입력 조건이므로 신규 모델 호출 없이 대조를 계산할 수 있다. 이 대조는 실제 사용할 예측기가 아니다.

HD의 iter_059 전체 병변 비교는 강한 전문 대안이 존재한다는 전략 근거로 유지한다. 이번에는 HD를 재실행하거나 iter_065의 미완결 subtype·비용 비율을 사용하지 않는다. 따라서 HD 대비 실용 우위는 이번 결론 범위 밖이다.

새 브랜치는 iter_006 기반으로 요청한다. `reuse_assets`에 현재 MRI 파일과 iter_054 scoring의 실제 import 의존성을 모두 명시했다. 반입은 재사용 승인이 아니다.

- `m65_data.py`, `msd56_data.py`: 승인된 기존 자료 연결 범위만 사용한다. build를 다시 실행해 원 PNG를 덮어쓰지 않는다.
- `m65_run.py`, `msd56_run.py`: 모델 로딩·공식 입력·hash·I/O helper를 재사용한다. 과거 worker의 비용 sidecar와 완료 판정은 그대로 사용하지 않는다.
- `mc54_run.py`: `extend_inputs`, `hidden_last`, `head_fp32` 등 확인한 scoring 계산을 재사용한다. 단일 영상용 prefix 및 MediConfusion CLI는 호출하지 않는다.
- 나머지 반입 파일은 위 함수의 import 의존성이다. 미사용 CLI의 전면 수정은 하지 않는다.

# Proposed Experiment

## 1. 자료·조건 고정

기존 D6와 E48, case당 여섯 구간을 유지한다. E12/E36 구분도 iter_065의 고정 순서를 재사용한다. 이번에는 W 질문의 F/J만 실행한다. E 질문·T 단독은 현재 형식 혼입 대조에 불필요하므로 제외한다.

추론 모델은 기존 MedGemma revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b` 하나다. F는 8장, J는 같은 z의 FLAIR/T1gd 16장이다. 입력 영상·질문·정답·case는 바꾸지 않는다.

## 2. 고정 scoring

후보 y의 score는 답변 token 위치의 평균 log-probability다. prefix와 EOS의 확률은 포함하지 않는다. 두 후보 중 score가 높은 답을 선택하고 정확한 동률은 ABSENT로 처리한다. threshold 학습·prior 차감·후보 문구 탐색은 없다.

기존 iter_054와 같이 bf16 hidden state에서 fp32 lm_head/log_softmax를 계산하되 현재 checkpoint의 head·softcapping 설정이 맞는지 검사한다. 후보별 token ID·token log-probability·합·평균을 모두 저장한다. 합계 score는 재현용이며 성능을 보고 주지표를 합계 방식으로 바꾸지 않는다.

## 3. 동작 확인: D6

36구간×F/J 2조건=72개 scoring 항목, 후보별로 총 144 forward를 수행한다. D6은 자료·수치·메모리·처리량·재개 검증과 prior 고정에 사용한다.

두 조건의 실제 입력에서 독립 token-by-token 계산과 score를 대조한다. 공식 입력 tensor, 후보 경계, 모델 output head 대응, candidate 교환 시 동일 score 복원, 정답·영상·설정 변경 거부를 검사한다. 허용 오차는 구현 전에 계산 정밀도에 맞춰 고정하고 초과 시 원인을 해결한다.

## 4. 가능성 탐색: E12

72구간×2조건×2후보=288 forward다. 기존 G_F/G_J와 새로운 L_F/L_J, prior 및 case 대응 제거 결과를 모두 보고한다.

다음 중 하나이면 E48까지 확대한다.

- L_J BA≥0.65이고 L_J−G_J≥0.15다. 큰 생성 오류 중 실질적으로 회복 가능한 부분을 확인하는 탐색 조건이다.
- L_J≥L_F−0.10이고 L_J가 위치 prior보다 높으며, case 대응 제거 null보다 BA가 0.03 이상 높다.

이는 확증·기본 능력 인증 기준이 아니다. 기존 약 60 pp의 W F−J 생성 격차에 대해 판별력 있는 회복 또는 공동 입력의 잔여 신호가 있는지 보는 조건이다. 모두 미달하면 E12에서 현재 경로를 보류하고, 작은 표본 결과를 MRI 전체의 음성 결론으로 확대하지 않는다.

E12에서 BA의 class 분모가 정의되지 않으면 성능 문턱 대신 자료 상태를 보고하고, E48의 두 class 존재 여부만 확인한다. E48에서 정의 가능하면 고정 잔여 case를 완료하고, 불가능하면 해당 지표를 미정의로 종료한다.

## 5. 조건부 개발 확대와 독립 확인 경계

E48 전체는 288구간×2조건=576개 scoring 항목, 1,152 candidate forward다. E12 결과를 재사용하며 중복 생성하지 않는다. D 포함 최대 1,296 forward다.

E48은 반복 개발 자료이며 이번에도 독립 확인이 아니다. 신규 환자·reserve·다중 seed·학습을 추가하지 않는다. 별도 독립 확인은 이번 리뷰에서 충분한 가치가 확인될 때만 새 계획으로 판단한다.

## 6. 자원·시간·재개

실행 직전 nvidia-smi와 상속 GPU 범위를 확인하고 허용된 장치 중 여유가 큰 순서로 배정한다. 기본 후보는 GPU 두 장에 MedGemma worker를 하나씩 배치해 독립 shard를 처리하는 구성이다.

D에서 batch1과 후보 두 개를 묶는 batch2를 우선 비교한다. 후보 batching은 같은 원 영상·prompt·score 정의를 유지해야 한다. batch 이득이 없고 측정 peak가 허용하면 GPU당 두 worker도 검토한다. 동시 worker peak 합계와 다른 점유에 worker당 2 GiB 여유를 더해 용량 안에 들어가야 한다.

iter_065에서 관측된 reserved memory 약 10.85 GiB는 현재 scoring의 admission 근거가 아니다. 이 값을 그대로 적용하면 두 worker와 각 2 GiB 여유가 24 GiB를 넘으므로 실측 없이 두 개를 올리지 않는다.

E36의 과거 W/F·W/J processor 평균은 약 0.690/1.521초다. 같은 전처리를 항목당 한 번 수행한다고 단순 환산하면 E48 전처리 합계만 약 637초다. 이는 scoring·loading·I/O를 제외한 참고치다. 전체 예상 wall-clock은 D의 조건별 실측 완료 항목/분과 두 GPU 배치로 계산해 E 시작 전에 기록한다. 임의 시간 상한은 두지 않는다.

score·후보 token·요청 ID·protocol digest·추론 구간 timing은 같은 결과 행에 저장한다. 전체 wall-clock은 부모 실행기가 worker 종료와 마지막 fsync 완료 후 측정한다. 저장 전 시간을 전체 비용으로 부르지 않는다. 이번에는 과거 생성이나 HD 대비 end-to-end 비용 비율을 주장하지 않는다.

고정 shard 배정 manifest와 worker lock으로 중복 소유를 막는다. 완결 행을 checkpoint로 재사용하며 중간 JSONL 손상은 거부하고 마지막 불완전 행만 원본을 보존해 복구한다. worker 수를 변경할 때는 완료 요청을 재검증한 뒤 미완료 요청의 배정을 새 manifest로 기록한다. 기존 claim·결과 파일은 변경하지 않는다.

# Implementation Tasks for Claude

1. 지정 SHA의 파일과 실제 반입·import 의존성을 확인한다. 누락을 새 구현으로 대체하지 않는다.
2. 기존 W/F/J 요청과 결과를 읽기 전용으로 연결하고 `results/iter_066/`에 새 protocol을 만든다. 모델·processor·코드·source·labels·PNG·scoring 규칙·prior를 잠근다.
3. 기존 scoring helper 위에 다중 영상 wrapper를 추가한다. 두 후보를 모두 계산하고 원 입력 tensor를 유지한다.
4. 별도 평가 진입점에서 protocol·요청·정답·모델·출력 seal과 중복·누락을 검증한다. D/E12의 과거 runner 차이는 명시한 hash 쌍만 허용한다.
5. 신규 경로의 저장 전후 강제 중단·재개와 복수 worker 결과 정합성을 시험한다. 비용 기록이 빠진 출력을 비용 비교 완료로 처리하지 않는다.
6. D 검증·처리량 비교·비용 예측 후 E12와 조건부 E48을 실행한다.
7. 원시 candidate 점수에서 별도 계산으로 예측·confusion counts·BA·주차이를 재현한다. 원 생성의 strict/비EOS 판정을 그대로 유지한다.
8. 계획 대비 실제 단계·요청량·확대 이유와 최종 투자 결정을 보고한다. HD 및 미사용 과거 실행기는 정비하지 않는다.

# Evaluation (성공/실패 기준 포함)

**주지표:** W의 pooled sensitivity, specificity, BA다. case가 분석 단위이며 여섯 구간을 독립 환자로 세지 않는다. case bootstrap 10,000회, seed66의 95% CI로 L_J−G_J, L_F−G_F, L_J−L_F와 prior 차이를 보고한다. class가 사라지는 replicate는 제외 수와 조건부 해석을 명시한다.

**생성 격차의 변화:** R=(BA(L_J)−BA(L_F))−(BA(G_J)−BA(G_F))를 보고한다. R>0은 scoring 아래 공동 입력의 상대 손실이 줄었다는 뜻이다. 순수 형식 원인이나 내부 기전을 확정하지 않는다.

**영상별 신호:** 같은 구간 위치에서 case 단위 예측 벡터를 재배열한 null의 기대 BA를 계산한다. 모든 case를 donor로 균등 사용하는 기대값을 사용하며 자기 case가 포함될 확률 1/n을 명시한다. bootstrap에서는 case를 재표집한 뒤 null 기대값도 다시 계산한다. 이는 case 연관성에 대한 대조이며 병변의 시각적 충분성이나 임상 인식 정확도의 직접 증명이 아니다.

**기존 출력의 재사용 확인:** G_F/G_J의 원 BA와 invalid/비EOS 수를 재현한다. 사후 마지막 줄 parser는 조사 노트의 민감도 결과로만 남기고 새 주분석으로 사용하지 않는다. invalid-only 하위집단은 설명용이며 전체 성능을 대체하지 않는다.

**양성 및 다음 행동:** L_J가 위치 prior와 null을 각각 5 pp 이상 넘고 L_J≥L_F−3 pp이면, 생성 인터페이스를 통제한 제한적 영상 신호와 기존 baseline의 가치를 보존한다. 5 pp는 prior 수준의 답변에 다시 연구 투자를 하지 않기 위한 개발 단계의 최소 여유이며, 3 pp는 두 배 영상 입력을 유지할 때 허용할 최대 성능 손실이다. 임상 허용 오차나 확증된 동등성 문턱이 아니다. L_J−L_F≥3 pp까지 확인될 때만 독립 확인 계획의 가치를 검토한다. 새 selector·형식 loss는 승인하지 않는다.

**음성 및 다음 행동:** scoring 후에도 prior/null 대비 신호가 부족하면 현재 frozen MedGemma mask 기반 경로를 종료한다. F가 J보다 충분히 좋으면 F baseline을 보존하고 공동 입력 방법 투자를 종료한다. 형식 회복은 크지만 F·prior 이후의 가치가 없을 때도 동일하다.

**불확정 및 다음 행동:** E48에서 점추정과 CI가 다른 결정을 허용하면 제한된 관찰을 보존하고 보류한다. CI 상한이나 format-valid 100%만으로 확대하지 않는다. 동일 자료의 다른 scoring 문자열·보정·prompt·세 번째 모델·학습을 자동 추가하지 않는다.

**기술 실패:** token 경계, causal shift, 입력·정답 연결, 수치 검증 실패는 모델 능력의 음성 결과가 아니다. 영향을 받는 경로를 한정 복구한 뒤 같은 기준으로 재검증한다. 복구하지 못하면 실행 미완료로 종료한다.

# Risks / Checks

- 평균 token likelihood는 문자열 길이·tokenization·답변 prior의 영향을 받는다. 하나의 고정 기존 baseline으로 해석하며 성능에 따라 score 정의를 바꾸지 않는다.
- F/J는 영상 수와 정보량이 다르다. J의 회복이나 우위도 상보적 결합의 필수성을 증명하지 않는다.
- 구간 전체 GT와 제공된 희소 slice의 범위가 다르다. 기존 coverage를 함께 보고하되 coverage>0을 시각적 충분성으로 바꾸지 않는다.
- case 대응 제거 null은 위치 prior를 보존하지만 모든 해부학·촬영 차이를 통제하지 않는다.
- E48의 반복 노출과 환자 독립성·사전학습 노출의 미확인을 유지한다.
- 현재 연구 질문에서 비용 우위·전문 모델 우위·신규 contribution은 미검증이다. 단순 scoring의 성공으로 이를 승인하지 않는다.
- 과거 결과·코드·판정과 상위 관리 저장소의 사용자 변경은 보존한다.

## 대규모 GPU 필요 후보

다중 sequence 표현과 언어 답변을 함께 적응하는 3D VLM post-training은 장기 후보로 남긴다. 현재는 기존 readout과 전문 대안 이후의 중요한 부족함이 확보되지 않았으므로 대규모 학습의 필요성이나 우위를 주장하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- GOAL, INDEX, iter_061~065 원 리뷰, iter_065 원 계획·review.json/code_assets, 관련 LIMITATIONS·CODE_ASSETS를 확인했다. iter_054의 생성/likelihood 비교도 원 리뷰와 scoring 소스로 확인했다.
- iter_065 E48 MedGemma의 W BA는 F 0.72872, J 0.13035다. W/E macro BA의 J는 0.35641이며 invalid는 J 329/576이다. Qwen은 형식 invalid 0이지만 같은 과제에서 강한 기본 성능을 확보하지 못했다.
- 저장 출력만 읽어 사후 민감도 계산을 수행했다. EOS로 끝난 응답의 마지막 줄이 명시적인 PRESENT/ABSENT 또는 'The answer is …'일 때만 추가 해석하면 MedGemma J macro BA는 0.52360, W BA는 0.35955다. J invalid는 329→214건이다. 원 parser·판정의 정정이나 독립 증거가 아니며 신규 주분석 parser로 채택하지 않는다.
- E48의 J 최종 비EOS는 156/576건이다. 원문에는 반복되는 소견 서술과 서술 후 명시 답변이 모두 존재한다. 따라서 단순 형식 오류와 내용 오류를 하나의 원인으로 묶을 수 없다.
- 모든 invalid를 정답으로 치환한 비실용 상한에서 J macro BA는 0.92103이다. 이 값은 실제 회복 가능 성능이 아니지만 기존 출력만으로 기본 인식 부족을 확정할 수 없음을 보여준다.
- 기존 E36의 W/F·W/J 평균 processor 시간은 약 0.690/1.521초, 기록된 최대 reserved memory는 약 10.85 GiB다. 이는 신규 likelihood forward의 시간·peak 측정이 아니다.

## 선행과 의미

[ReForm-Eval §3.3·§4.3.4](https://arxiv.org/html/2310.02569v2)는 생성과 답변 likelihood 평가를 구분한다. 따라서 이번 scoring은 기존 대안이며 신규성 주장이 아니다. [MedGemma 1.5 공식 model card](https://huggingface.co/google/medgemma-1.5-4b-it)의 chat-template 기반 입력을 유지한다.

iter_054에서는 scoring이 형식 문제를 줄여도 새로운 보정 방법의 투자 기준은 충족하지 못했다. 그 실패 범위와 교훈을 유지한다. 이번에는 평가 쌍의 상대 정답을 사용하지 않고, 이미 확보한 MRI 출력의 해석을 정리하는 데만 scoring을 사용한다.

## 선택 이유

새 selector 학습은 prior 대비 이득과 단순 대안 이후의 부족함이 확보되지 않아 제외한다. 다른 MRI 질문으로 즉시 이동하는 선택보다, 새 데이터 없이 최대 1,296 candidate forward로 큰 인터페이스 혼입을 분리하는 비교의 정보 가치가 높다고 판단한다. 이 비교 후에도 같은 자료의 주변 진단을 이어가지 않는다.

## 재사용

현재 HEAD는 ce5f5991ee7274806e9b6ffbfbefa26d7189df62다. 신규 브랜치의 자동 기반이 현재 HEAD와 다를 수 있음을 orchestrator 코드로 확인해, legacy 재사용 기준을 충족하는 iter_006 기반과 필요한 파일의 선별 반입을 명시했다. 원 iter_065 계획 SHA256은 5147dbce11958feef582f0d0c2587f8e3988ef3d48bf979df561134d4243af13이다. 이번 계획은 해당 계획의 소급 수정이 아닌 별도 진단이다.

이번 라운드에서는 파일 수정·신규 모델 추론·학습을 실행하지 않았다.
