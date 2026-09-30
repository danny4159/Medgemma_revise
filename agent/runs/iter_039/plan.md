# 요약

- **이번에 할 일:** PadChest-GR 실제 영상에서 두 소견의 개별 grounding과 공동 grounding을 비교한다.
- **필요한 이유:** annotation 조합이 서로 다르다는 사실만으로 실제 문장–영역 대응의 성공을 판단할 수 없다. 개별 성공이 공동 요청에서 보존되는지 확인한다.
- **확인할 기준:** 형식·좌표·출력 길이를 통제한 뒤에도 남는 손실, 문맥과 공동 출력의 차이, 독립 처리의 정확도·비용을 측정한다.
- **주의·다음:** 새로운 기여는 미확정이다. 탐색 기준을 통과할 때만 확대·별도 환자 확인을 진행한다. 새 학습은 이번 범위에 없다.

# Current Understanding

기준 원문은 `agent/runs/iter_038/plan.md`, `review.md`, `data_access_handoff.md`와 `agent/runs/iter_037/review.md`다. iter_038 plan SHA256은 `1e922c0c3014fdf4b72594ebcc5ee0aa3d3fb88f9ffa5d1c4e83505933e2c5c9`다. 이번은 같은 실험의 실행 복구가 아니라 새 실제 출력 가설이므로 과거 setup의 성공 기준을 바꾸지 않는다.

**유지:** GOAL, MedGemma 1.5, RSNA SFT·detector 성과와 checkpoint, VinDr 승인 대기, continuation 추가 투자 종료, MRI F139·CheXpert F105·기존 reserve 보존.

**종료:** exact label+location 이후에도 동일한 annotation 조합이 남아야 한다는 H_data의 자동 확대. train 다중 소견 1,163영상에서 잔여 후보 0개라는 결과를 유지한다.

**이번 변경:** 동일 영상·원문 두 문장에 대해 개별 요청과 공동 요청의 실제 grounding을 비교한다. broad category 공유 213영상만 선택하지 않는다. annotation의 유일성과 모델 출력의 정확성은 다른 문제다.

**미완료:** 본 영상 확보·영상 좌표 연결, 새 과제의 정상 사용 검증, 실제 모델 성능, 비용 및 별도 환자 재현이다.

PadChest-GR 인계는 본 영상 약38.5GB의 조건부 다운로드까지 허용한다. 이번 실제 출력 질문에는 영상이 필요하므로 해당 범위에서 확보한다. 과거 검사 영상 약9GB는 받지 않는다. 인계 자체를 새 학습 승인으로 해석하지 않으며 이번에는 추론 진단만 수행한다.

# Strategy Check / 연구 방향 판단

중요한 사용 과제는 여러 소견의 근거를 한 화면에서 검토할 때, 함께 요청했다는 이유로 근거가 사라지거나 다른 문장에 붙지 않는 것이다. 이번에는 두 소견으로 제한해 이 문제를 식별한다. 전체 보고서 생성·임상 진단 능력으로 일반화하지 않는다.

확인된 사실은 RSNA의 위치·FP trade-off, 이전 QA의 큰 형식 효과, PadChest annotation 조합의 유일성이다. 미확인 설명은 개별 grounding 부족, 문맥 간섭, 공동 출력의 누락·배정 오류와 출력 형식 실패다.

- **현재 방법 개선:** RSNA 추가 loss·calibration은 새 정보 이득이 작고 학습 비용이 든다. 외부 결과가 설명을 바꾸기 전까지 보류한다.
- **능력·원인 진단:** 같은 영상·문장의 개별 성공과 공동 실패를 직접 비교하면 위 경쟁 설명을 분리할 수 있다. 이번 우선순위다.
- **다른 질문 전환:** 보고서 사실성 등은 후보지만 정답 보장·선행 대비 차이를 새로 확보해야 한다. 이번 최소 진단이 음성 또는 구조적으로 불확정이면 다시 비교한다.

단순 분리 처리가 정확도를 보존하고 비용도 충분히 낮다면 공동 처리를 위한 새 post-training의 우선순위를 낮춘다. 공동 처리 손실을 발견하는 것과 이를 해결할 신규 방법의 가치는 별도로 판단한다.

# Hypothesis

**H_joint:** 동일 소견을 개별적으로 grounding할 수 있는 경우에도 두 소견을 공동 요청하면 문장별 grounding 성능이 실질적으로 낮아진다.

**H_context:** 두 문장을 보여 주되 하나만 답하게 해도 손실이 생긴다면, 공동 출력만의 문제가 아니라 입력 문맥의 영향이 포함된다.

**H_binding:** 공동 출력의 영역 집합은 남아 있지만 문장 ID 사이의 재배정으로 점수가 회복된다면 배정 오류와 일치하는 관찰이다. 이는 내부 attention 원인의 증명이 아니다.

경쟁 설명은 개별 grounding 자체의 부족, parser·ID 형식, 짧은 출력 한도, 문장 순서, 주석 중첩·경계 차이, 시간 비교 문구다.

# Limitation Evidence / Correct Usage Checks

연결할 기존 id는 `qa-format-compliance-after-grounding-sft`와 `rsna-evidence-interface-sensitivity`다. 둘 다 observed이며 새 PadChest 한계가 validated라는 뜻이 아니다. RSNA의 validated grounding 주장을 새 자료·공동 요청에 전용하지 않는다.

iter_016에서 strict 차이가 semantic 처리 후 크게 줄었고, iter_017에서는 좌표 추가의 이득이 관찰되지 않았다. 따라서 parser 실패를 내용 손실로 계산한 총점만으로 H_joint를 지지하지 않는다. iter_025처럼 해석되지 않는 좌표 oracle을 통과 조건으로 반복 사용하지 않는다.

모델은 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16, greedy로 고정한다. processor·chat template·라이브러리 버전·generation config를 기록한다. 공식 notebook 보존본은 `results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb`, SHA256 `d2e12122867e3de5c8b13903dcf4859a63810d8b38e30c1bfae85a634f39a52f`다. 이번 웹 재조회는 실패했으므로 보존본과 과거 정상 사용 검증을 출처로 삼는다.

원본 PNG의 dtype·범위·방향·크기를 먼저 확인한다. uint8은 값 보존, grayscale은 채널 복제, 중앙 square padding을 사용한다. uint16이면 제공자 또는 공식 변환의 명시적 규약을 확인한 뒤 고정한다. 임의 per-image min–max, contrast 개선, 반전·좌우 flip을 성능에 맞춰 선택하지 않는다. 규약을 해결하지 못하면 GPU 평가를 보류한다.

GT의 normalized xyxy를 원본 W/H로 복원한 뒤 padding canvas의 yxyx/0–1000으로 변환한다. affine 전체 top·left·side, 원본·변환 pixel hash를 보존한다. 비정사각·홀수 padding·모서리 box fixture와 실제 overlay를 확인한다. 영상 미확보나 좌표 blocker가 남으면 CPU 준비만으로 유효한 모델 진단이라 보고하지 않는다.

# Contribution Path / Baselines / Reuse

[MedGrounder](https://arxiv.org/html/2512.01085v1)는 문장별 복수 영역과 모듈형 grounded report를 이미 다룬다. [uMedGround](https://github.com/Cocofeat/uMedGround) 역시 보고서 grounding의 가까운 선행 방법이다. 이번 차별 후보는 과제 형식이 아니라 개별 grounding이 공동 요청에서 보존되는 조건과 실패 분해다. 신규성은 아직 확인되지 않았다.

**이번 실용 baseline:** 문장별 독립 M0 출력 두 개를 ID로 결합한다. 원본 영상·문장을 제한하지 않고, 병렬 독립 처리의 실제 비용을 측정한다. 동일 문맥에서 하나씩 답하는 조건은 문맥과 공동 출력의 영향을 분리한다.

**진단용 oracle:** 공동 출력의 두 ID 그룹을 GT 기준으로 최적으로 교환했을 때의 점수다. 실용적인 수정 방법이나 detector 성능으로 보고하지 않는다. GT label/location도 실용 입력으로 사용하지 않는다.

**후속 방법의 필수 baseline:** 동일 annotation budget의 과제별 직접 SFT, 독립 SFT 출력 결합, MedGrounder 같은 문장 조건부 detector와 필요시 VLM의 모듈형 구성이다. 원본 영상·crop·도구 사용을 허용하고 학습 자료·학습량·사전학습 노출·추론 비용 차이를 기록해야 한다. 이번은 그 투자 여부를 결정하므로 학습을 먼저 하지 않는다. RSNA SFT와 opacity detector는 이 과제의 언어·category 범위를 충족하는 비교군이 아니다.

현재 브랜치의 `padchest_audit038.py`는 needs_fix다. loader·schema 검사·좌표 순수 함수가 실제 필요한 범위에서만 보완한다. duplicate key, 결측·허용 split, ImageID의 환자·study 연결을 drop_duplicates 이전에 검사하고 오류를 차단한다. 과거 감사 main을 다시 실행해 기존 결과를 덮어쓰지 않는다.

선별 반입 여섯 파일의 SHA·범위는 reuse_assets를 따른다. geometry·parse·metrics의 승인은 기존 RSNA 조건에 한정된다. generate의 저수준 함수만 사용하고 기존 CLI·queue·완료 판정은 호출하지 않는다. 과거 detector·학습 실행기의 결함은 이번 해결 대상으로 삼지 않는다.

# Proposed Experiment

## 1. 자료와 사전 고정

원본 metadata 두 파일의 hash는 iter_038 handoff와 대조한다. 비공개 접근 위치는 `research/results/datasets/padchest_gr/ACCESS_PRIVATE.md`에서만 확인하고 링크를 로그·Git·보고서로 복사하지 않는다. 본 영상 다운로드는 객체 크기·ETag 등 재개 근거를 기록하고, 안전한 압축 해제·파일 충돌·누락·hash 검사를 한다. 현재 확인한 디스크 여유는 약353GB지만 실행 직전에 다시 확인한다.

표본 단위는 환자다. 환자당 영상 하나, 영상당 원문 finding 두 개를 선택한다. 대상은 abnormal=true이며 official box가 있는 현재 영상 소견이다. 시간 비교나 이전 영상의 지시 대상이 필요한 문장은 사전 규칙과 출력에 눈가림한 검토로 제외·계수한다. 희귀 category, 작은 box, 복수 box, 겹치는 영역을 편의상 제외하지 않는다. box 없는 양성과 음성 문장은 이번 가설 밖으로 별도 계수한다.

train에서 D24와 E288을 환자 비중복으로 추출하고 E96을 E288의 고정 첫 단계로 둔다. seed는 20260930이다. eligible patient 목록을 만든 뒤 category 공유 여부·복수 box 여부를 층으로 삼아 비례 배분하고, 층 안에서 hash 순서로 환자·영상·문장 쌍을 고른다. 희소 층도 유지하고 선택 확률과 실제 수를 기록한다. broad category 공유213만으로 모집단을 만들지 않는다. 두 소견을 고르는 규칙은 모델 출력을 보기 전에 잠근다.

별도 F120은 공식 validation에서 같은 규칙으로 확보한다. D/E와 환자·원본 및 decoded pixel hash 중복을 차단한다. 이 집단은 이번 M0 설정 선택에서 보존하며 독립 기관·사전학습 미노출을 뜻하지 않는다. 적격 환자가120명 미만이면 모든 적격 환자를 사전에 잠그고, 목표 정밀도 미달을 명시한다. test는 사용하지 않는다. iter_038에 노출된 test 사례는 비공개 exclusion/provenance로 남기고 원문을 재전파하지 않는다.

표본·층·제외 이유·문장 ID·prompt·생성 설정·metric·확대 규칙을 실행 전 manifest/config에 잠근다. GT·labels·locations는 평가 경로에만 둔다.

## 2. 요청 조건

각 환자의 두 문장을 qA/qB에 무작위 배정한다. ID는 좌표·category·원문 순서와 독립이며 모든 조건에서 대응을 유지한다. 원문 문장을 고치거나 합성 병변을 만들지 않는다.

환자당 총9개 요청이다.

1. **I-long, 2건:** 문장 하나씩 독립 grounding.
2. **J-long, 1건:** 두 문장을 함께 grounding.
3. **J-reverse, 1건:** J-long의 문장 제시 순서만 반전. ID 대응은 유지.
4. **C-long, 2건:** 두 문장을 모두 제시하되 지정한 하나의 근거만 출력.
5. **I-short, 2건:** 간결한 지시문으로 독립 grounding.
6. **J-short, 1건:** 같은 간결한 지시문으로 공동 grounding.

long은 공식 좌표·좌우·reasoning·Final Answer 규약을 유지하며 대상과 ID 지시만 과제에 맞춘다. short는 같은 좌표·대상·ID 규약으로 JSON만 요청한다. 두 template family는 D에서 고정하고 E 결과로 선택하지 않는다.

출력은 공통 평탄 JSON 목록 `[{"box_2d":[y0,x0,y1,x1],"label":"qA"}, ...]`이다. 문장당 여러 box를 허용한다. 알려진 ID의 box가 없으면 그 문장의 빈 예측이며 임상적 정상 판정으로 해석하지 않는다. 미지 ID·중복 key·모호한 복수 답·비유한 좌표는 별도 invalid다. 출력 label의 대소문자·공백 정규화 등 허용 범위를 D에서 고정하며 GT 기반 fuzzy matching은 금지한다.

I/C의 token cap은1000→2000→4000, J는2000→4000→8000이다. EOS 없는 cap 도달에만 동일 요청을 연장 재생성하고 모든 시도를 보존한다. 모델 context 한도와 긴 출력 메모리를 먼저 검사한다. 최종 truncation은 삭제하지 않고 실패 유형으로 보고한다.

## 3. 동작 확인 — D24

24명×9=216개 요청으로 입력·좌표·parser·출력 길이·실행 보호를 확인한다. 대표 실제 영상12개에서 original/padded overlay를 비공개로 검토한다. 합성 좌표·ID 복사 검사는 구현 검증이며 시각 grounding 성공 근거로 사용하지 않는다.

본평가 진입 조건은 모든 데이터·좌표·입력 검증 통과, 각 template family에서 좌표/JSON 유효율90% 이상, 해결되지 않은 truncation이 전체 요청의2% 이하인 것이다. D에서 형식만을 위한 명확한 수정1회는 허용하며 전후 원문과 이유를 보존한다. D 점수로 유리한 문장·환자를 선택하지 않는다. 형식 gate가 계속 실패하면 현재 인터페이스가 부적격하다고 보고하고 E를 열지 않는다.

## 4. 가능성 탐색 — E96

96명×9=864개 요청을 수행한다. 새 학습은 없고 greedy 생성 seed는0이다. E는 개발 자료다. 동작 확인 통과만으로 E288/F를 자동 실행하지 않는다.

개별 능력 기준은 I-long의 환자 평균 F1@0.3이0.40 이상이고, 적어도24명의 환자에서 한 문장 이상의 I-long F1@0.3이1인 것이다. 이는 연구 투자용 기준이며 임상적 적합성 기준이 아니다.

E288 확대는 다음 중 하나일 때 한다.

- 개별 능력 기준을 충족하고 long의 I−J 차이가0.10 이상이며 short 차이도 양수다.
- 형식·길이 문제 없이 결과가 불확정이고, 개별 능력 또는 I−J의 CI가 위 기준을 가로지르며, E288에서 예상 CI 반폭이0.06 이하가 되어 판단을 바꿀 가능성이 있다. 예상치는 E96의 paired 분산으로 산출한다.

I 성능의95% CI 상한이0.40 미만이거나, 두 family 모두 I−J의95% CI 상한이0.10 미만이면 현재 공동 처리 가설의 확대를 보류한다. 작은 표본의 단순 무개선만으로 전체 의료 grounding을 기각하지 않는다.

## 5. 규모 확대 — E288

조건을 충족하면 추가192명×9=1,728건을 수행해 총288명·2,592건으로 만든다. E96 결과·설정은 그대로 보존한다. 평가 시점은 E96과 E288 두 번이며 각 소규모 batch 결과로 조건을 바꾸지 않는다.

표본 규모는 10pp 수준의 차이를 판단하려는 것이다. 예를 들어 binary discordance0.25라면 N288의 paired 차이95% 반폭은 약6pp다. 실제 연속 F1의 정밀도는 관측 분산으로 보고하고 이 근사치를 power 보장으로 표현하지 않는다.

## 6. 별도 환자 확인 — F120

E288에서 개별 능력 기준을 유지하고, long I−J 점추정치≥0.10 및97.5% CI 하한>0, short 차이>0이고, 형식·truncation만으로 설명되지 않는 내용 손실이 남을 때만 F를 실행한다. 판정 artifact를 먼저 저장하고 F 요청을 생성한다.

F120은1,080건이다. prompt·parser·전처리·metric을 고정한 채 한 번 평가한다. F 이후 설정을 바꾸면 F는 개발 자료가 되며 새로운 독립 확인이 필요하다. 이번에는 다중 학습 seed·추가 모델 계열·외부 기관 확인을 하지 않는다.

## 7. GPU·예상 비용·재개

실행 직전 nvidia-smi로 허용GPU0,1의 여유와 논리/물리 대응을 확인한다. 초기에는 GPU별1 worker, 독립 요청 shard를 사용한다. D의 같은48개 요청으로 총2 worker와 가능한 경우 총4 worker를 비교한다. J의 긴 입력·출력을 포함한다. 모델 로딩 포함/제외 wall-clock, 전체 req/min, GPU별 실제 peak, worker별 reserved peak, p95 지연, 오류·CPU/RAM/I/O 경합을 기록한다.

동시 worker peak 합계와 다른 프로세스 점유에 worker당2GiB 여유를 더해24GB 안에 들어야 한다. 긴 J 출력 때문에4 worker가 불가능하면 메모리 근거를 남기고2 worker를 유지한다. 유망하면 batch 확대를 대안으로 비교하되 두 축을 전수 탐색하지 않는다. 처리량이 개선되고 공통 요청의 token·parser 결과가 유지되는 구성을 선택한다. 차이가 생기면 원인을 확인하고 검증된 구성을 사용한다.

추론은 모델당8–10GiB가 초기 참고값이며 긴 출력 peak는 미측정이다. D+E288+F120의 최대 기본 요청은3,888건이다. 전체 처리량10–25req/min을 가정하면 생성만 약2.6–6.5시간이며, 이는 추정치다. token cap 재시도·로딩·검증·다운로드는 별도다. 본 영상38.5GB 전송은20–100MB/s일 때 약6–32분의 순수 전송 시간이지만 서버 제한에 따라 길어질 수 있다. D 실측 후 남은 요청 수/처리량으로 ETA를 갱신한다. 임의 GPU 시간 상한을 두지 않는다.

worker 수와 GPU 수를 분리한다. 고유 request ID, 실행 소유권, worker별 결과 파일, 입력·config·소스·결과 digest를 사용한다. 요청 단위 저장 후 중단·재개하며 live claim을 지우지 않는다. 완료 판정은 예상 요청 집합 일치·결과 내용 검증·worker 종료·집계 완료까지 lock을 유지한다. 기존 결과는 덮어쓰지 않고 불일치 시 새 attempt 경로 또는 명시적 중단으로 처리한다.

# Implementation Tasks for Claude

1. 접근 인계와 이번 계획을 읽고 진행 중인 작업·잠금을 확인한다. 현재 브랜치와 기존 결과를 보존한다.
2. padchest_audit038의 실제 사용할 loader·schema 검사만 보완한다. 새 자료 manifest와 결과는 `results/iter_039/`에 저장한다. 전체 metadata 재집계를 반복의 주성과로 삼지 않는다.
3. 승인된 본 영상 확보·검증과 사전 환자/문장 선택을 완료한다. private 링크·원문·식별 metadata가 공개 로그나 Git에 들어가지 않게 한다.
4. reuse_assets의 함수만 연결하고 새 문장 ID grouping·요청 manifest·평가기·실행 보호를 구현한다. 반입 코드가 있다는 이유로 과거 runner 전체를 승인하지 않는다.
5. 정상 입력 tensor 대조, 좌표 fixture, parser 경계 사례, 요청 중복·누락, 입력 및 결과 변조 거부, 실제 중단·재개를 검사한다. 현재 결론과 무관한 과거 pipeline 정비는 하지 않는다.
6. D와 처리량 비교를 끝낸 뒤 protocol을 잠근다. E96→조건부E288→조건부F120 순서와 decision artifact를 강제한다.
7. 독립 구현으로 주요 matching·환자 점수·paired CI를 재계산하고, 현재 도달 단계·미실행 단계·실측 비용·투자 권고를 보고한다. 소스 checkpoint와 브랜치 관리는 orchestrator에 맡긴다.

# Evaluation (성공/실패 기준 포함)

## 지표

주지표는 각 문장의 maximum-cardinality one-to-one box matching F1@IoU0.3이다. 환자 안의 두 문장을 평균하고 환자 간 평균한다. 주차이는 Δ_long=I-long−J-long이다. short의 동일 차이는 문구 강건성 대조다. IoU0.5, 문장별 union IoU, box recall·FP, 빈 예측, 좌표·형식 invalid, 최종 truncation을 함께 보고한다.

invalid 요청은 주점수0으로 포함하되 내용 오류와 별도 집계한다. long/short I·J가 모두 유효하고 EOS로 끝난 동일 환자 subset의 민감도 분석도 보고한다. 이 subset은 사후 조건부 분석이며 전체 모집단 효과로 대체하지 않는다.

기전 대조는 I-long−C-long, C-long−J-long, J-long−J-reverse다. 독립 처리에서 완전 성공한 문장이 공동 처리에서 실패하는 비율과 반대 방향 회복률을 함께 보고한다. 독립 성공 사례만 골라 평균 손실의 주분모로 쓰지 않는다.

배정 오류는 공동 출력의 qA/qB 전체 box 그룹을 교환했을 때 얻는 최대 점수와 원래 점수 차이로 측정한다. box를 GT에 맞춰 새로 분할하지 않는다. 두 GT 집합 사이 모든 cross-IoU<0.1인 사전 정의 subset에서는 해석력이 더 높으므로 별도 보고한다. 겹치는 소견은 주평가에 남기되 교환만으로 원인을 확정하지 않는다. extra annotation이 있는 동일 subset에서도 방향을 확인한다.

환자 paired bootstrap10,000회, seed20260930을 사용한다. Δ_long·Δ_short는 각각97.5% CI를 보고하고 다른 대조는 탐색적95% CI로 표시한다. 관찰0건·모든 paired 차이0은 exact/Wilson 또는 보수적 유한표본 구간을 덧붙여 bootstrap[0,0]을 모집단 영점으로 해석하지 않는다.

비용은 두 문장을 모두 처리하는 환자 단위로 비교한다. 독립 요청의 병렬 처리를 허용하고 요청 수·token·wall-clock·GPU-seconds·peak를 함께 기록한다. vision/prefix caching을 실제 구현·검증하지 않았다면 가능한 절감량은 추정 또는 미측정으로 명시하며 공동 처리의 필수 속도 우위를 주장하지 않는다.

## 결과별 판단

**양성:** F에서도 Δ_long 점추정치≥0.10 및97.5% CI 하한>0이고 short 차이의 방향이 양수이며, 내용상 실패가 형식·truncation만으로 설명되지 않는다. 이는 고정된 두 소견 과제의 공동 처리 손실을 지지한다. C와 그룹 교환 분석으로 입력 문맥·공동 출력·배정 오류의 설명 범위를 좁힌다. 내부 원인·일반 의료 VLM 결함·새 방법의 효과는 미확인이다.

**음성:** 충분한 개별 grounding 능력에서 두 family 모두 중요한 손실0.10을 CI 상한으로 배제하거나 공동 처리가 유지·개선된다. 이 공동 처리 실패 후보의 투자를 종료한다. 손실이 형식 보정만으로 해소되면 내용상 결합 한계 주장을 하지 않는다. 독립 처리가 손실을 해결하고 실측 비용도 경쟁력이 있으면 그 경로를 baseline으로 보존하고 새 결합 loss 투자를 보류한다.

**불확정:** 개별 능력 부족, 주석·영상 규약 미해결, 효과의 넓은 CI, prompt 간 방향 불일치 또는 F 부족이다. E96에서만 사전 정밀도 기준에 따른 E288 확대를 허용한다. E288/F 이후 같은 표본·prompt를 반복 탐색하지 않고, 어떤 추가 자료·직접 SFT 비교가 실제 판단을 바꿀지 다음 리뷰에서 결정한다. 개별 grounding 부족을 공동 결합 능력의 실패로 해석하지 않는다.

**방법 투자 조건:** 양성 진단만으로 새 학습을 자동 시작하지 않는다. 독립 처리의 비용과 MedGrounder·과제별 직접 SFT 대비 남을 개선 목표가 구체적일 때만 별도 method 계획을 세운다. 새 validated 한계가 필요하며, 단순 분리·순서 교환·혼합 SFT 자체는 contribution으로 삼지 않는다.

**실행 유효성:** 정상 입력·좌표·예상 요청 집합·provenance가 검증되고 실제 가설 비교가 완료됐을 때만 valid_experiment=true다. 다운로드·테스트 통과만이면 false다. 유효한 음성 결과와 연구 목표 달성은 별개다.

# Risks / Checks

- 두 문장 subset의 결과를 전체 보고서·진단·임상 reasoning으로 일반화하지 않는다.
- label/location oracle의 유일성을 실제 detector 성공으로 해석하지 않는다. 문장별 복수 box를 하나로 합치지 않는다.
- 시간 비교 문구, 번역, annotation 경계·중첩은 사전 규칙과 민감도 분석으로 범위를 제한한다. 다른 문장의 영역이라는 이유만으로 확정 음성을 만들지 않는다.
- PadChest 사전학습 노출 가능성과 기관 단일성은 남는다. F는 이번 선택으로부터 보존한 환자 집단이지 모델 사전학습 미노출의 증거가 아니다.
- 재사용 metrics.match는 작은 집합의 열거 방식이다. 실제 box 수에서 계산량을 확인하고, 큰 집합에 효율적 matching이 필요하면 동일 cardinality·IoU 우선순위를 독립 fixture로 검증한다. 임의 box cap으로 평가를 바꾸지 않는다.
- iter_038 test 노출 원문은 보존하되 재출력·공유하지 않는다. 노출 사례의 식별은 비공개 provenance에만 둔다.
- VinDr 승인 전 다운로드·평가·반복 질문을 하지 않는다. 이번 자료 권한과 혼동하지 않는다.

## 대규모 GPU 필요 후보

문장·영역·보고서 공동 post-training에서 개별 질의 능력을 보존하도록 vision encoder와 언어 모델을 함께 적응하는 후보를 남긴다. 현재 필요성은 미입증이다. 두GPU에서 가능한 직접 LoRA·독립 처리·모듈형 baseline 이후에도 재현되는 중요한 잔여 문제가 있을 때 대규모 학습의 비용과 정보 이득을 비교한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

- `agent/GOAL.md`, GPT·보고 표현 정책, INDEX, LIMITATIONS 관련 항목, iter_037·038 리뷰와 iter_038 계획·접근 인계를 읽었다. iter_016·017·025의 형식·인터페이스 결과와 관련 code_assets 원문도 확인했다.
- iter_038의 exact label+location 중복 0건은 좁은 자료 가설의 음성 근거다. 실제 grounding 성공이나 공동 요청의 안정성을 측정한 결과는 아니다. 이를 뒤집거나 broad category 공유 213영상을 새 benchmark로 자동 승격하지 않는다.
- `data_access_handoff.md`에는 PadChest-GR 접근 승인이 확보됐으며, 실제 영상 확인이 필요할 때 본 영상 약38.5GB 다운로드·안전한 압축 해제까지 승인됐다고 명시돼 있다. 과거 검사 영상은 제외된다. 이번 질문은 실제 출력 비교가 필요하므로 영상 확보의 정보 가치가 있다. VinDr 권한과는 별개다.
- 현재 research HEAD는 `1c295feb3a2ed3bac76a95fe7ff1566ccfe71955`이며 status/diff는 깨끗했다. 현재 파일 목록에는 padchest_audit038.py가 있고 rsna_diag 모듈은 없다. 보존 SHA `755ec06e17606936422f1595f7bf62dc53085e59`에서 필요한 여섯 파일과 사용 함수·의존성을 확인했다.
- 보존된 공식 notebook의 SHA256은 `d2e1212286767e3de5c8b13903dcf4859a63810d8b38e30c1bfae85a634f39a52f`가 아니라 `d2e12122867e3de5c8b13903dcf4859a63810d8b38e30c1bfae85a634f39a52f`이다. 실제 파일에서 좌표 yxyx/0–1000, reasoning과 Final Answer 지시, square padding을 확인했다. 최신 웹 재조회는 실패했으므로 최신 원문과 동일하다고 주장하지 않는다. uint8에서 추가 ×255를 적용하는 문제는 과거 검증된 값 보존 경로를 유지한다.

## 선행연구와 의미

[MedGrounder 원논문](https://arxiv.org/html/2512.01085v1)은 문장별 0개·1개·여러 영역과 보고서 생성기에 결합하는 모듈형 경로를 이미 다룬다. [공식 구현](https://github.com/Claire1217/GMPG)은 Chest ImaGenome 사전학습 및 MS-CXR/PadChest-GR 적응 checkpoint를 구분한다. 따라서 공동 grounding 또는 문장 분리 자체는 기여가 아니다. 이번에는 실제 개별 성공을 기준으로 공동 처리의 손실과 원인을 구분하고, 단순 분리 경로로 충분하면 투자를 종료한다.

[PadChest-GR 원논문](https://arxiv.org/html/2411.05085v2)은 환자 단위 split, 문장별 복수 box, official/extra annotation, 시간 변화 문구 및 주석 변동성을 설명한다. 이번에는 현재 영상에서 직접 grounding 가능한 원문 두 문장을 사용하고, 시간 비교가 필요한 문장은 별도로 제외·계수한다. 빈 box를 임상적 음성으로 바꾸지 않는다.

## 결정과 미확인 범위

동일 annotation 조합 이후의 잔여 사례를 찾는 기존 H_data는 종료한다. 같은 소견 문장–영상 근거 접근법 안에서 실제 출력 가설을 새로 고정한다. 단순 bbox 개선이나 기존 oracle 질의 반복보다 다음 투자 판단을 바꿀 가능성이 높고, 새 학습 없이 두 GPU에서 실행 가능하다. 공동 처리 손실의 존재·빈도·원인과 독립 처리의 실측 비용은 아직 미확인이다.

이번 조사는 읽기 전용이었다. 영상 다운로드, 모델 실행, 파일 변경은 하지 않았다. 문헌은 조사 근거이며 이번 방향의 실제 양성 실험이 없으므로 논문 추천으로 처리하지 않는다.
