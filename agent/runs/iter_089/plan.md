# 요약

- **이번에 할 일:** 같은 MedGemma 1.5에서 판독문만 학습한 R과 위치 정답도 학습한 G를 비교한다.
- **필요한 이유:** 기존 CURE·RSNA adapter 비교에는 학습 자료·목적·노출 차이가 섞여 있어 위치 supervision의 효과를 분리하지 못했다.
- **확인할 기준:** 확정 소견·위치·속성의 회복과 명시적 모순을 함께 측정한다. 좌표 출력 개선만으로 판독 개선을 주장하지 않는다.
- **주의·다음:** 기존 방법의 통제 진단이다. 양성 결과도 신규 contribution이나 방법 개발 자동 승인이 아니며, C-H·E192 확대는 계속 보류한다.

## 알림 맥락

- 연구: 위치 학습과 판독 정확성
- 데이터: 흉부 X-ray PadChest-GR, 기존 개발 E96 → 별도 학습·validation과 사전 잠근 평가 환자
- 모델: MedGemma 1.5의 report-only/위치 보조 LoRA, 미적응 base와 공개 CURE C-G 참고 비교
- 과제: 흉부 X-ray 한 장에서 현재 소견 판독문을 생성한다
- 가설: 위치 학습은 판독 소견의 회복을 돕거나 좌표 출력·언급 성향만 바꿀 수 있다
- 질문: 같은 판독문으로 학습해도 위치 정답을 배우면 더 정확하게 읽는가?
- 변경: 구체화
- 연결: iter_088의 회복·충돌 관찰은 보존하되 시스템 간 학습 조건 차이를 통제한다
- 작업: 두 학습 조건의 실제 판독을 비교해 위치 보조 학습의 다음 투자 여부를 결정한다

# Current Understanding

iter_088은 유효한 저장 출력 재평가다. C-G의 회복 신호는 남지만 의미 대응에 따른 불확실성이 있다. C-H의 추가 회복은 큰 충돌 증가와 함께 나타나며 단순 C-G 선택으로 상당 부분 피할 수 있다. 이를 새 결합 방법의 필요성으로 연결하지 않는다.

iter_012의 RSNA grounding 개선은 유지한다. iter_016/017의 yes/no·검출 정보 결과는 자유 판독 전체의 결과가 아니다. iter_040/048에서는 직접 SFT와 학습 형식이 큰 설명력을 보였으므로 이번에도 강한 직접 판독 SFT를 먼저 확보한다.

보완 ID `20261007_094428_6873684f`의 담당 전환·부분 평가 인계는 iter_088에서 완료됐다. 이번에는 미완료 평가를 다시 만들지 않는다. iter_087/088 원본, E96 판독문, protocol·판정·checkpoint는 보존한다.

# Strategy Check / 연구 방향 판단

**관찰 → 경쟁 설명 → 최소 비교 → 바뀔 판단:** grounding 개선은 확인됐지만 판독 전이는 불확정이다 → 판독 supervision·학습량·모델 차이와 언급 성향이 남는다 → 동일 base와 판독 target에서 위치 CE의 유무를 비교한다 → 위치 보조 학습의 한정 확인에 투자할지 현재 설계를 보류할지 결정한다.

선택은 같은 현상의 구체화다. 새로운 modality나 benchmark 후보 탐색이 아니다. 현재 C-H 개선은 C-G 이후의 가치가 부족하고, 연구 묶음 전체 보류는 실행 가능한 통제 비교가 주는 정보 가치를 버린다. 따라서 한 번의 명시적인 학습 대조를 선택한다.

이번에는 **기존 다중 과제 CE의 원인 구분을 위한 diagnostic**을 수행한다. 새로운 loss·교정기·선택기를 개발하지 않는다. 학습을 한다는 이유로 새로운 방법이라고 부르지 않으며, observed C-H 충돌을 다른 방법의 진입 근거로 전용하지 않는다.

해결한 질문은 현재 C-H의 복합 투자 기준 미달과 평가 수정 후에도 남는 제한된 관찰이다. 남은 질문은 판독 supervision을 고정해도 위치 학습의 효과가 남는가이다. 인식·선택·결합의 내부 원인은 아직 구분하지 못했다.

지배 비용은 신규 학습과 실제 판독의 의미 평가로 예상한다. 기존 전체 이력 감사나 E96 재평가를 반복하지 않는다. 불변 자산 검증은 원 SHA와 연결해 재사용한다.

# Hypothesis

- **H1:** 동일 판독 supervision에서 위치 CE를 추가하면 확정 소견과 명시된 위치·속성의 회복이 증가한다.
- **H2:** 좌표 출력은 개선되지만 자유 판독은 개선되지 않는다.
- **H3:** 추가 학습 신호가 이상 언급을 늘리고 불확실 표현·명시적 모순도 증가시킨다.
- **H4:** report-only 적응으로 기존 차이의 상당 부분이 해소돼 위치 보조 과제의 추가 가치가 작다.

R/G 차이는 현재 보조 과제의 총 효과다. 양성이라도 공간 대응 자체와 일반적인 보조 supervision·gradient 변화는 후속 대조 없이는 분리하지 않는다.

# Limitation Evidence / Correct Usage Checks

`lesion-grounding-generalization`은 위치 학습이 실제 가능한 자산이라는 근거다. `padchest-regional-report-concatenation-conflict`는 현재 C-H 투자를 피하는 근거다. 두 항목 모두 이번 판독 학습의 미검증 효과를 validated로 대신하지 않는다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`에서 두 LoRA를 새로 시작한다. 기존 RSNA·PadChest adapter로 초기화하지 않는다. CURE는 기존의 정확한 MedGemma 1 base와 adapter revision을 그대로 사용한다.

정상 사용의 불변 근거는 재사용하되 새로운 다중 턴 학습 입력은 별도 검사한다. 이미지 tensor, chat template, assistant-only mask, EOT, 좌표 canvas, 생성 cap, GT 연결을 검증한다. 기술 검사는 모델 정답률 100%를 요구하지 않는다.

# Contribution Path / Baselines / Reuse

가까운 방법은 [CURE](https://arxiv.org/html/2601.15408v1), [MAIRA-2](https://arxiv.org/html/2406.04449v1), [RegionFormer](https://proceedings.mlr.press/v315/aas-alas26a.html)다. 이미 grounding과 판독을 연결하므로 단순 공동 SFT 개선을 새 기여로 삼지 않는다. RegionFormer 공식 코드의 mask 입력 조건은 위치 정답 없이 판독하는 이번 조건과 구분한다. 최종 PDF의 미확인 세부를 선행의 실패로 표현하지 않는다.

주대조는 R이다. 최종 참고군은 미적응 MedGemma 1.5와 CURE C-G다. C-G는 다른 base·자료·학습량·정밀도이므로 시스템 참고군이며 R/G의 통제 효과를 대체하지 않는다. C-H는 실행하지 않는다.

이번에는 detector+reporter를 새로 학습하지 않는다. 현재 질문은 동일 VLM의 위치 supervision 효과다. 향후 실용 우위나 신규 방법을 주장하려면 예측 영역을 사용하는 강한 모듈형 판독 대조가 필요하다. 정답 영역 제공 조건을 실용 비교군으로 사용하지 않는다.

현재 `approach/grounding-report-transfer`, HEAD `faee416633f87d281656c00982b973757c36817b`를 이어간다. `reuse_iteration=0`은 이 브랜치의 초기화를 뜻하지 않는다. `reuse_assets`의 9개 파일만 iter_048 SHA에서 반입한다. 현재 존재하는 의존 파일은 원 blob과 동일함을 확인했다.

재사용 범위는 다음과 같다.

- `pg39_data.py`: metadata 연결, 분할 ZIP 읽기, 좌표 유효성. 과거 두 양성 문장 표본 규칙은 사용하지 않는다.
- `rsna_diag/generate.py`, `lora.py`, `geometry.py`, `queue_lock.py`: 현재 입력·LoRA·좌표·잠금 함수.
- 반입 `pg48_train.py` 및 `rsna_diag/train.py`: CE·checkpoint·optimizer/RNG 보존의 구현 기반. 과거 main과 고정 manifest는 실행하지 않는다.
- `report86_gen.py`, `report86_launch.py`: 필요한 생성 경로를 확장하면서 sibling digest·protocol, 실행 조건 잠금, 외부 점유와 예약 메모리 합산을 수정한다.
- `report87_eval.py`, `report88_eval.py` 등의 집계 구조와 회귀 사례: 참고·함수 단위 재사용. E96 전용 hardcoded 수정과 기존 주장 단위는 새 평가에 적용하지 않는다.

## 대규모 GPU 필요 후보

여러 모델·기관·학습량에서 report-only, 정확한 위치, 교란된 위치, 모듈형 판독을 교차하는 연구는 장기 후보로 보존한다. 이번 결과가 투자 가치를 보여줄 때 검토하며 현재 실행 범위에는 포함하지 않는다.

# Proposed Experiment

## 1. 자료 적합성 및 분할

원 자료는 `results/datasets/padchest_gr/raw/grounded_reports_20240819.json`, `master_table.csv.zip`과 기존 분할 영상 ZIP이다. 원본 hash·접근 조건·환자 연결은 기존 증거와 대조한다.

공식 train의 3,185영상/3,123환자에서 환자별 대표 frontal image를 hash 순으로 선택한다. `seed=89017`, hash key는 `seed|PatientID|ImageID`로 고정한다. 기존 보호 집단과 환자·study·영상 중복을 먼저 제거한다. 위치가 있는 비정상, 비정상이나 위치 없음, 비정상 표기 없음의 세 층을 유지하며 실제 적격 비율에 따라 largest-remainder로 T512/V64를 배정한다. 희귀 층이 있으면 최소 한 환자를 포함하고 실제 비율을 보고한다. D8은 T 안에서 세 층과 긴 판독·복수 box 사례를 포함하는 기술 검사 집단이다.

과거 영상이 필요한 문장은 기존 temporal 규칙과 progression 필드로 표시한다. 현재 영상으로 평가할 수 없는 문장을 target에서 제외하되 그 환자를 정상으로 바꾸지 않는다. 현재 문장이 하나도 남지 않으면 제외한다. 정상·부정 문장, box 없는 문장은 report target에 유지한다. box가 없다는 이유로 `[]`를 정답으로 만들지 않는다. train 일부의 영어·스페인어 및 실제 영상·box를 D8에서 대조하고 제외율·표적 분포 변화를 기록한다.

공식 test의 915영상/893환자에서 E128을 별도로 잠근다. 현재 비정상 사실이 있는 96명과 비정상 표기가 없는 32명을 목표로 한다. 기존 모델 출력·평가·학습에 사용한 로컬 환자, 보호 H192/F120, 중복 pixel, 이번 계획에서 내용을 본 JSON 첫 test 사례를 제외한다. 후자는 `251488034557732338959601580328898734705_wigcpj.png`다. 기존 E96/E192는 열거나 재사용하지 않는다.

E의 ID 선택은 출력과 무관하게 먼저 잠근다. 실제 reference 작성·영상 추출·출력 평가는 학습·선택 설정이 잠긴 뒤 진행한다. 새 reference는 모델 출력을 보기 전에 작성한다. 부족하면 같은 공식 split의 사전 hash 순서로만 보완하며, 적격 환자 전부로도 목표에 못 미치면 실제 수와 정밀도를 보고한다. 작은 표본이라는 이유만으로 기술 실패로 판정하지 않는다.

E는 이번 R/G 적응·선택에 사용하지 않은 평가 집단이다. foundation model의 과거 노출이나 공개 CURE의 benchmark 선택 노출까지 배제한 임상 독립 test라고 부르지 않는다. 선택하지 않은 공식 test 환자는 봉인 상태로 남긴다.

## 2. 통제 학습 조건

공통 첫 turn은 이미지와 기존 중립 판독 prompt, assistant의 현재 소견 판독문이다. 판독 target은 적격 영어 문장을 원 순서로 결합하고 EOT로 끝낸다.

위치 정답이 있는 환자에는 뒤에 두 번째 user turn을 붙인다. 첫 판독문 중 사전에 선택한 한 소견 문장을 인용해 위치를 요청하고, assistant는 해당 문장의 모든 유효 box를 기존 square-padded yxyx 0–1000 JSON 형식으로 출력한다. 문장은 환자·epoch hash로 순환 선택한다. reference의 비정상 문장과 box 연결을 그대로 사용하며 새 언급을 만들지 않는다.

- **R:** 첫 assistant 판독 token의 CE만 학습한다. 뒤 grounding 답변의 가중치는 0이다.
- **G:** 같은 판독 CE에 grounding 답변 CE를 가중치 1로 추가한다.
- 환자별 report token 평균을 낸 뒤 batch 환자 평균을 사용한다. 보조 CE도 환자별 token 평균이며 보조 정답이 없는 환자는 0으로 처리한다. 두 조건의 report 가중치와 분모는 같다.
- 두 조건은 같은 전체 입력·forward shape·assistant logit 계산 범위를 사용한다. R에서 미래 turn의 loss는 완전히 차단한다. dummy 입력 비용을 공정한 실제 report-only 운영 비용으로 포장하지 않고, 같은 출력의 효율적인 R 경로 비용도 별도로 구분한다.
- 두 조건의 LoRA 초기값·dropout seed·환자 순서·update 수는 같고 차이는 보조 loss 가중치다. 최종 판독 생성은 첫 user turn만 사용한다. 정답 문장이나 위치를 판독 입력에 제공하지 않는다.

이는 고정된 표준 CE ablation이다. 공간 loss, contrastive loss, preference 학습, curriculum을 추가하지 않는다.

## 3. 동작 확인

D8에서 mask·좌표·전처리·gradient·checkpoint·생성·메모리를 확인한다. 첫 turn을 단독으로 실행한 경우와 미래 grounding turn을 붙인 경우의 첫 turn logits/loss를 비교한다. dropout을 통제한 R의 gradient/update도 일반 report-only 학습과 일치해야 한다. 불일치하면 causal attention 또는 mask 결함을 해결하기 전 학습하지 않는다.

G에서 보조 CE를 0으로 두면 R과 loss·gradient·update가 일치해야 한다. 실제 보조 CE가 켜지면 해당 token의 gradient가 존재하고 base는 동결돼야 한다. padding·system/user/image token에 loss가 걸리지 않는지 확인한다. 짧은 학습의 암기는 경로 확인일 뿐 일반화의 증거가 아니다.

모델은 bf16 base 동결, 기존 언어층 rank16 LoRA, alpha32, dropout0.05, AdamW·weight decay0.01·gradient clip1, effective batch8을 사용한다. LR 후보는 1e-4와 2e-4다. 실제 적용 값과 optimizer 설정을 config digest에 잠근다. 모델·환경별 Python 경로를 명시하고 기본 환경·hf_cache는 변경하지 않는다.

## 4. 가능성 탐색과 학습 확대

T512에서 R/G×두 LR, seed17의 네 trajectory를 epoch2까지 수행한다. 환자 512명이 유지되면 trajectory당 128 updates다. 512명은 전체 train 일부에서 정상 문장·다양한 소견·복수 box를 함께 학습하기 위한 규모이며 보편적 표본 상한이 아니다.

V64의 report NLL을 epoch1/2/4/6에 측정한다. 실제 판독 생성·의미 평가는 고정 층화 V32에서 epoch2/6에만 수행한다. grounding 보조 능력은 같은 V 안의 box가 있는 고정 16명에서 측정한다. 정답 문장 조건부 bbox 출력임을 명시하며 자유 판독 인식 지표와 혼합하지 않는다.

Epoch2 이후 다음 중 하나면 네 trajectory를 epoch6까지 이어간다: 실제 V32에서 base 대비 올바른 확정 소견 회복이 여러 환자에 나타남, G의 문장 조건부 grounding이 base보다 개선됨, 또는 report NLL이 초기 대비 5% 이상 낮아지면서 실제 생성에서도 올바른 회복과 소실이 혼재해 아직 방향을 판정하기 어려움. loss 감소만 있고 실제 출력의 유용한 변화가 전혀 없으면 자동 확대하지 않는다. 한 LR의 수치 오류는 그 경로의 기술 복구 대상으로 분리한다.

Epoch6에서 각 조건의 LR을 V64 report NLL로 선택한다. 동률은 낮은 LR을 택한다. 어느 한 조건에서 epoch4→6 report NLL이 2% 이상 더 낮아지고 V32 strict recall이 5pp 넘게 악화되지 않았으면, 두 조건의 선택 LR을 동일하게 epoch12까지 연장한다. epoch8/12에서 NLL과 V32 생성을 평가한다. 추가 LR·seed·epoch는 없다.

최종 공통 epoch는 두 선택 LR trajectory가 모두 가진 평가 checkpoint 중 R/G report NLL 합이 가장 작은 것으로 고른다. 동률은 이른 epoch다. R/G의 report 노출과 update 수를 같게 유지하며 두 조건의 개별 최선 결과는 보조 표로만 남긴다. 선택 기준에 E·CURE 성능을 사용하지 않는다.

네 trajectory의 epoch6 비용은 최대 1,536 updates, 선택 두 trajectory의 추가 epoch6은 768 updates다. 총 최대 2,304 updates다. 정상 동작만 확인하고 이 최대량을 자동 실행하지 않는다.

## 5. 잠금 후 평가

학습·checkpoint·prompt·parser·의미 규약을 잠근 뒤 E128에서 R, G, 미적응 MedGemma 1.5, CURE C-G를 각각 한 번 생성한다. 총 512개 판독이다. CURE는 기존 공식 GRG 전처리·prompt·정밀도·revision을 유지한다. 이 비교는 공식 전체 benchmark 재현이 아닌 현재 protocol의 시스템 비교다.

생성은 greedy·seed17이다. 최초 cap1024, 비EOS cap 도달 요청만 동일 입력에서 2048→4096으로 연장한다. 모든 시도·비용을 보존한다. 정답 여부에 따라 재생성하지 않는다. 최종 비EOS·거부·형식 실패는 별도로 보고하며 유리하게 제외하지 않는다.

E의 box 보유 환자 중 hash 순 32명에서는 R/G의 문장 조건부 grounding을 별도 측정한다. 이는 위치 학습이 작동했는지를 확인하는 보조 진단이며, 정답 문장을 이용하므로 판독 recall의 원인 증명이나 실용 detector 비교가 아니다.

## 6. GPU 배치·시간·재개

실행 직전 `nvidia-smi`와 상속된 허용 장치의 논리/물리 대응을 확인한다. 독립 R/G·LR trajectory를 두 GPU에 배정한다. 다른 사용자의 프로세스는 변경하지 않는다.

과거 iter_048의 peak reserved 중앙값은 약 11.2–11.6GiB였다. 이 값에 worker별 2GiB를 더하면 두 training worker의 동시 배치는 이미 24GiB를 넘으므로 초기 training은 GPU당 한 worker로 시작한다. 이는 고정 정책이 아니라 현재 근거다. D8에서 microbatch1→2 등 유망한 batch 확대를 먼저 비교하고 새 실측에 따라 확정한다.

추론에는 GPU당 두 worker도 후보로 둔다. 기존 CURE D8의 두 GPU 처리량은 worker 총2개에서 9.44 requests/min, 총4개에서 14.66 requests/min이었다. 새 긴 출력·R/G 모델에 그대로 적용하지 않고 D8에서 필요한 확인을 한다. 외부 점유 + worker별 예약 peak + worker별 2GiB가 실제 용량 안에 들어야 한다.

보고 항목은 유효 requests/min 또는 updates/hour, GPU별 peak allocated/reserved와 장치 전체 점유, 긴 출력 지연, OOM·오류, CPU/RAM/I/O 경합, token 정합성이다. validation/test 점수로 실행 구성을 고르지 않는다.

초기 추정은 학습 wall-clock 3–10시간, 생성 1–3시간이며 의미 평가 시간은 별도다. 이는 제한이 아니다. 과거 짧은 입력 실측과 새 sequence 길이 차이를 반영한 거친 추정으로, 첫 정상 20 updates 및 D8 생성의 실제 처리량으로 남은 시간·메모리를 갱신한다. 첫 의미 평가 묶음의 실제 소요로 평가 완료 예상도 기록한다.

checkpoint는 32 updates마다 및 epoch 경계에 adapter·optimizer·RNG·다음 batch·protocol digest를 함께 저장한다. 실행 종료와 평가 종료를 분리한다. 요청 ID·worker 결과 파일·원자적 claim·누락/중복 검사를 유지하고 완료 파일을 존재만으로 신뢰하지 않는다. 재개·검증·실패 시도의 비용도 누적한다.

# Implementation Tasks for Claude

현재 구현 담당은 Codex이며 섹션명은 호환 형식이다.

1. 현재 branch·HEAD·선별 반입 파일을 확인한다. 새 소스는 `report89_*`, 결과는 `results/iter_089/`에 두고 기존 결과를 덮어쓰지 않는다.
2. metadata와 D8 실제 영상·문장·좌표를 연결하고 T/V/E manifest·노출 이력·제외 사유를 잠근다. 자료 의미가 성립하지 않으면 대규모 추출 전에 해당 blocker를 보고한다.
3. 기존 trainer 함수를 재사용해 공통 report CE와 선택적 grounding CE를 구현한다. 과거 고정 manifest·init adapter·CLI main을 실행하지 않는다. 실제 LR과 재개 조건을 일치시킨다.
4. 새 생성 전에 sibling 행 provenance·실행 조건 잠금·GPU 예약 합산의 기존 reuse issue를 해당 실행 경로에서 수정한다. 과거 E96를 다시 생성하지 않는다.
5. D8에서 causal 비간섭·loss/gradient·중간 재개·epoch 재개·validation 상태 보존을 검사한다. 완료된 불변 검증을 전수 재실행하지 않는다.
6. 새 의미 규약은 V 사례로 고정한다. reference 사실과 생성 주장을 분리하고 근거 span·불확실성·충돌 상대를 저장한다. E96 전용 판정 수정은 가져오지 않는다.
7. 계획된 학습·validation 분기를 실행하고 선택 근거를 잠근 뒤 E를 한 번 평가한다. base나 CURE의 내용 오답을 기술 blocker로 취급하지 않는다.
8. 별도 집계 구현으로 환자별 점수·차이·bootstrap·민감도를 재계산한다. 결과·학습량·요청량·비용·미실행 범위와 후속 투자 권고를 보고한다. 코드는 orchestrator의 checkpoint 절차로 보존한다.

# Evaluation (성공/실패 기준 포함)

## 평가 단위와 주지표

새 reference는 현재 소견을 소견 종류·극성·확실성·위치·명시 속성으로 분리한다. 접속 문장의 여러 주장을 하나의 C/S/U 우선순위로 축약하지 않는다. 문장 분할이 애매하면 원문과 모호 플래그를 보존한다.

주지표는 비정상 층의 **환자 평균 strict recall**이다. reference의 확정 소견이 확정적으로 회복되고, 명시된 위치·속성이 일치해야 한다. 위치·속성이 없는 reference에는 없는 정답을 요구하지 않는다. 위치 누락, 위치 충돌, 속성 누락·충돌을 별도로 기록한다. 넓은 동의어를 이용한 회복과 모호 대응은 구분한다.

안전성 지표는 **명시적 reference 모순이 하나 이상 있는 환자 비율**과 내부 모순 환자 비율이다. reference에 없는 추가 주장은 미지원/판단불가로 기록하며 모두 임상 FP로 간주하지 않는다. 비정상 표기가 없는 32명도 정상 임상 gold가 아니다.

보조 지표는 소견 종류만의 확정 recall, possible-only 회복, strict/비strict의 차이, 생성 원자 주장 수, reference 지지·반박·판단불가 수, 형식 실패, 보조 grounding F1@0.3/0.5다. 주지표와 bbox 지표를 직접 비교하지 않는다. 완전한 임상 precision–recall 또는 동일 임상 FP 수준의 우위를 주장하지 않는다.

모델명·학습 조건을 가린 출력 ID로 assistant 의미 평가를 수행한다. 원문과 reference anchor를 저장한다. E의 고정 hash 24명에 대해 네 조건을 다시 점검하며 모호 사례와 결정을 좌우하는 회복·모순도 확인한다. 이는 전문의 검증이나 독립 평가자 합의가 아니다.

R/G paired 차이와 95% CI는 환자 bootstrap 10,000회·seed89017로 계산한다. E의 두 층은 따로 재표집한다. 임의의 유병률로 합친 임상 성능은 보고하지 않는다. reference의 모호한 사실을 전체 제외하는 분석과 모호한 출력 대응을 회복으로 인정하지 않는 분석을 사전 민감도로 함께 계산한다. 유리한 기준을 선택하지 않는다.

## 양성

G−R strict recall이 5pp 이상이고 명시 모순 환자 비율 증가는 전체 및 비정상 층에서 각각 3pp 이내여야 한다. 추가 회복은 최소 5명의 환자에 분산되고, 한 환자 제거로 차이의 부호가 바뀌지 않으며, 모호 대응 민감도에서도 양의 방향이 유지돼야 한다.

5pp는 100개 reference 사실당 약 5개의 정확한 회복을 구분하려는 탐색상 최소 가치다. 3pp는 그 회복을 적은 수의 추가 명시 모순으로 맞바꾸는 조건을 걸러내는 운영 기준이며 임상적으로 검증된 허용 한도가 아니다. CI가 0을 포함하면 양의 탐색 신호와 효과 확증을 구분한다.

양성이면 표준 공동 SFT 자산을 보존하고, 추가 seed·공간 대응 대조가 위치 supervision의 고유 기여를 구분할 한정 확인 계획을 권고한다. 즉시 새 loss를 개발하거나 method/full로 확대하지 않는다.

## 음성

R이 실제 판독을 학습했는데 G가 개선하지 못하거나 모순 비용이 기준을 넘으면 현재 위치 보조 CE 투자를 보류한다. G의 bbox만 개선되면 위치 출력과 판독 전이의 분리를 보존한다. 단순 R이나 C-G가 충분한 대안이면 해당 범위에서 신규 방법 투자를 종료한다.

두 조건 모두 학습·기본 판독 신호가 부족하면 위치 supervision 일반 가설의 반증이 아니다. 현재 recipe·표본의 적합성 부족으로 한정하고 무조건 다른 모델·modality 실험을 붙이지 않는다.

## 불확정과 종료

표본 변화만 남는지, 의미 대응이 결론을 바꾸는지, baseline이 아직 상승하는지 구분한다. 허용된 epoch12 이후에는 E를 보고 학습을 늘리지 않는다. 의미 불확실성이 핵심이면 추가 생성 없이 보류한다. 평가가 안정되고 여러 환자의 일관된 효과가 있으나 CI만 넓으면 추가 표본이 줄일 불확실성과 비용을 보고해 별도 한정 확대를 판단한다. 이번에는 남은 test를 열지 않는다.

현재 E128 평가는 신규 적응·선택과 분리되지만 단일 seed·assistant 평가다. 논문 수준의 독립 확인이나 임상 검증 완료로 부르지 않는다.

# Risks / Checks

- 미래 grounding turn이나 정답 문장이 첫 판독 loss·추론 입력에 새지 않아야 한다. 실제 logits·gradient 검사가 필수다.
- 보조 loss 추가에는 gradient 규모·최적화 변화도 포함된다. 공간 대응의 고유 효과를 주장하지 않는다.
- temporal 문장 제거로 비정상 환자가 정상 층으로 바뀌지 않게 원 보고서 상태와 retained-target 상태를 모두 기록한다.
- box 없는 문장과 미표기 소견을 음성 정답으로 만들지 않는다. 좌표 변환은 원 영상→square padding→0–1000 순서를 검사한다.
- R/G에 같은 report 노출과 선택 기회를 제공한다. 낮은 report loss만으로 판독 개선을 선언하지 않는다.
- CURE의 공개 test·선택 노출과 foundation pretraining 중복은 미확정이다. 시스템 순위를 위치 supervision 효과로 해석하지 않는다.
- 참조문서의 불완전성과 assistant 평가 오차를 보존한다. 현재 평가를 임상 gold·precision으로 부르지 않는다.
- 추가 환경이 필요하면 먼저 알리고 승인된 격리 경로에만 구성한다. `HF_TOKEN_PATH`는 경로로만 사용하고 토큰 내용은 출력하지 않는다.
- 기존 기본 환경·hf_cache·다른 사용자 프로세스·과거 결과는 변경하지 않는다. 무관한 공통 코드 정비나 전수 감사로 실험을 확장하지 않는다.

# 계획의 근거 (GPT 조사 노트)

새로 확인한 핵심은 통제 학습 자료와 재사용 경로가 존재한다는 점이다. 이번 계획 단계에서는 파일 읽기·메타데이터 집계·문헌 조회만 수행했으며 코드 수정·학습·추론은 하지 않았다.

- `agent/GOAL.md`, iter_084 계획, iter_085/086 관련 계획·리뷰, iter_088 review 원문과 code_assets, 관련 LIMITATIONS/CODE_ASSETS, iter_012/040/048 review의 근거·재사용 문제를 확인했다. iter_087의 인계는 iter_088에서 완료됐으므로 다시 발주하지 않는다.
- iter_088: C-G의 base 대비 확정 recall 차이는 +15.28pp이나 모호 대응 민감도에서는 CI가 0을 포함한다. C-H는 C-G 대비 recall +6.08pp와 명시 모순 +47.92pp다. 현재 결합 방식의 투자 보류를 유지한다.
- 로컬 `grounded_reports_20240819.json`과 `master_table.csv.zip`에는 train 3,185영상/3,123환자, validation 455영상/443환자, test 915영상/893환자가 연결된다. 현재 문장만 남기는 기존 temporal 규칙의 한정 집계에서 train 보고서 3,050개가 남고, 그중 box 있는 비정상 문장 포함 1,895개, 비정상이나 box 없음 47개, 남은 문장에 비정상 표기가 없음 1,108개였다. 마지막 집단은 정상 환자라는 뜻이 아니다. 환자 대표 선택·영상 검증 전의 후보 수다.
- 영상 폴더는 개별 PNG가 아니라 `PadChest_GR.zip.001–.037` 분할 archive다. `pg39_data.py`의 기존 ConcatFile·ZIP reader를 재사용할 수 있다. 새 대규모 다운로드는 필요 근거가 없다.
- 현재 research HEAD는 `faee416633f87d281656c00982b973757c36817b`, 작업 트리는 깨끗했다. 현재 생성기에는 sibling provenance 및 GPU 예약 합산 문제가 남는다. 새 생성에 필요한 경로만 고친다.
- iter_048 학습 원시 로그를 집계하면 E/J의 step 시간 중앙값은 11.899/9.313초, peak reserved 중앙값은 11.576/11.172GiB다. 이는 짧은 grounding 입력의 실측으로 새 판독 학습의 처리량·메모리 보장이 아니다.
- CURE는 여러 위치·판독 과제와 curriculum을 함께 사용한다. 공개 시스템의 이득을 위치 supervision 하나의 효과로 분해할 수 없다. [CURE 원문](https://arxiv.org/html/2601.15408v1)
- MAIRA-2는 소견 생성, 위치 출력, 다양한 판독 context를 함께 다룬다. 따라서 단순 공동 학습이나 grounding 점수 개선은 새 기여가 아니다. [MAIRA-2 원문](https://arxiv.org/html/2406.04449v1)
- RegionFormer의 공식 초록은 영상·grounding mask 조건의 판독 개선을 보고한다. 공식 코드에서 mask embedding을 입력 prefix에 결합하는 경로를 확인했다. 이는 추론에서 정답 위치 없이 위치 supervision의 학습 효과를 보는 이번 조건과 구분된다. 최종 PDF는 content-type 오류, OpenReview 판본은 browser challenge로 상세 표를 확인하지 못했다. 논문 전체의 한계를 단정하지 않는다. [논문](https://proceedings.mlr.press/v315/aas-alas26a.html), [공식 입력·생성 코드](https://raw.githubusercontent.com/LightVED-prhlt/RegionFormer/main/train_one_epoch_and_validate_region.py)
- Phrase-grounded APO의 공식 초록은 fact-checking과 교정으로 만든 preference 및 위치 loss를 사용한다. 현재 관찰만으로 그 방법을 다시 제안할 근거는 없다. [공식 논문 페이지](https://openaccess.thecvf.com/content/CVPR2026/html/Mahmood_Phrase-grounded_APO_for_Improving_Chest_X-ray_Report_Generation_CVPR_2026_paper.html)

전략 선택은 동일 연구의 구체화다. C-H 개선은 단순 C-G 선택 이후의 잔여 가치가 부족해 보류하고, modality 전환은 현재의 학습 조건 혼입을 해소하지 못하므로 선택하지 않는다. 표준 CE의 R/G 대조를 통해 다음 방법 투자 여부를 판단한다. 대규모 GPU 후보는 여러 모델·기관·학습량에서 report/grounding 및 공간 대응 대조를 교차하는 학습 연구이며, 이번에는 실행하지 않는다.
