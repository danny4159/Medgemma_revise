# 요약

- **이번에 할 일:** 같은 C checkpoint에서 공동 직접 SFT와 추가 독립 SFT를 비교한다.
- **필요한 이유:** 공동 요청에서 약20 pp의 F1 손실은 확인됐지만 공동 형식을 학습하지 않은 영향은 아직 분리되지 않았다.
- **확인할 기준:** 공동 성능의 선택적 회복, 독립 성능 보존, 적응 MedGrounder 대비 정확도와 실제 비용이다.
- **주의·다음:** 직접 SFT는 기존 baseline이다. 한정 대조 후 최소 방법 시험 검토 또는 해당 공동 grounding 투자 보류로 종료한다.

# Current Understanding

iter_041에서 C의 독립/공동 AB/BA F1@0.3은 0.577951/0.381076/0.354167이었다. 모든 출력은 valid·EOS였고 정확도 비교는 유효하다. 비용 점추정치는 있으나 request latency CI를 device 시간 기준에 연결한 원 blocker는 남아 있다.

iter_046에서 같은 T305 annotation으로 적응한 MedGrounder A의 F1@0.3은0.594444였다. 비열등성 확증은 없지만 C의 문장별 정확도 우위를 추가 내부 방법의 근거로 삼기 어려워졌다. 공동 요청 손실은 이 비교로 설명되지 않았다.

iter_047은 E96을 실행하지 못했다. 교정 후보의 자료·oracle·지시문 문제를 이번에 고치거나 E를 축소하지 않는다. GOAL, RSNA 자산, VinDr 승인 대기와 H192/F120/test/MRI reserve를 유지한다.

이번은 이전 실험의 amendment가 아니다. 별도 결과 경로 `research/results/iter_048/`를 사용한다. 기준 원문은 iter_040 학습 계획·리뷰, iter_041 공동 비교 리뷰, iter_046 MG 선택·리뷰다. 과거 판정과 blocker를 수정하지 않는다.

# Strategy Check / 연구 방향 판단

**중요한 능력:** 여러 소견의 근거를 한 번에 요청할 때 문장별로 확보한 정확도를 보존하는 능력이다. 단일 VLM 호출 자체보다 정확도·추론 비용의 trade-off가 연구 가치의 기준이다.

**확인된 것:** 독립 SFT의 개선, 현재 공동 인터페이스의 큰 손실, 적응 MG의 강한 문장별 성능이다. **미확인:** 직접 공동 학습으로 손실이 회복되는지, 추가 독립 학습만으로 비슷하게 회복되는지, 강한 대안보다 필요한 효용이 남는지다.

선택을 비교하면 문장별 새 loss는 적응 설명 이후의 정보 가치가 낮다. 공동 손실의 비용만 재측정해도 학습 형식 설명은 풀리지 않는다. 다른 중요한 질문으로의 전환은 가능하지만, RSNA 위험 관리에는 이미 강한 entropy baseline이 있고 현재 교정 후보는 평가 성립부터 다시 필요하다. 이번에는 확보된 동일 자료의 두 직접 학습 대조를 우선한다.

이 선택은 새로운 공동 학습 효과가 관찰됐다는 판단이 아니다. 학습 개입, 공정한 추가 CE 대조, 적응 MG, 결과별 종료를 함께 고정하여 아직 빠진 경쟁 설명에 답할 수 있게 한 투자다. MG를 제외하거나 단일 모델 사용을 강제해 공동 처리를 유리하게 만들지 않는다.

같은 `language-conditioned-grounding` track의 iter_038~047 이력을 이어받는다. 준비·진단·실행 복구를 유효 실험 수와 혼동하지 않는다. 기존 비용은 iter_040 학습 약2.54 GPU-hours, iter_041 일부 실행 약1.123 GPU-hours 등 포함 범위가 달라 총합으로 만들지 않는다. 이번에는 학습·생성·timing·실패 시도의 비용을 분리해 기록한다.

종료 후 직접 SFT가 해결하면 별도 공동 loss 투자를 종료한다. 잔여 공동 손실과 모듈형 대비 실용적 정확도 이점이 함께 있을 때만 최소 방법 시험을 검토한다. 그 외에는 현재 두 양성 문장 공동 grounding 투자를 보류한다. 전체 의료 VLM이나 근거 기반 답변의 가치 판정으로 확대하지 않는다.

# Hypothesis

H1: 공동 prompt와 공동 정답 목록을 직접 학습하면 같은 annotation 노출량의 추가 독립 SFT보다 공동 출력이 더 개선된다.

경쟁 설명은 추가 학습량, 독립 능력 훼손에 따른 격차 축소, 형식/EOS 개선, 공동 형식 학습 이후에도 남는 영역·ID 결합 오류다. 학습 조건 변경은 prompt·정답 직렬화·영상 반복 횟수를 묶어서 바꾸므로 순수한 syntax 효과나 내부 인과 기전으로 해석하지 않는다.

# Limitation Evidence / Correct Usage Checks

대상은 observed인 `padchest-sentence-grounding-and-joint-retention`이다. LIMITATIONS.md와 iter_041·046의 원 리뷰를 확인했다. iter_041의 정확도 관찰과 비용 blocker를 분리한다.

이번은 기존 baseline의 학습 조건을 바꾸어 경쟁 설명을 시험하는 `diagnostic`, `method_stage=none`이다. 새 loss·attention 구조·학습 방법은 제안하지 않는다. 이 분류로 method gate를 통과했다고 간주하지 않으며, 새 방법 시험은 후속 별도 계획과 근거 gate를 거쳐야 한다.

MedGemma 1.5 revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, bf16 frozen base, 공식 chat template, 기존 값 보존 전처리·square padding·yxyx/0–1000 좌표를 유지한다. `pg39_spec.prompt_I_short`, `prompt_J_short`를 그대로 사용한다. J_AB/J_BA에서 문장 순서만 바꾸고 qA/qB의 의미는 유지한다.

학습 prefix·assistant mask·GT 직렬화와 새 입력 processor tensor를 직접 검사한다. 생성 cap은 기존 I의1000→2000→4000, J의2000→4000→8000을 유지한다. 마지막 비EOS·invalid도 평가 분모에 남긴다. 의미가 틀렸다는 이유로 재생성하지 않는다.

# Contribution Path / Baselines / Reuse

[MedGrounder](https://arxiv.org/html/2512.01085v1)는 문장별 다중 영역 출력과 생성 보고서에 대한 모듈형 적용을 이미 다룬다. [공식 구현](https://github.com/aehrc/MedGrounder)의 검증된 자산을 사용한다. 공동 결과 JSON은 독립 출력을 결합해도 만들 수 있으므로 기능 명칭 자체는 기여가 아니다.

비교 시스템은 다음과 같다.

- **C:** 기존 `results/iter_040/train2/C_s17/epoch_03/adapter.pt`. 검증된 I/J 출력은 provenance를 확인해 재사용한다.
- **E:** C에서 추가 독립 CE. 환자당 두 I-short 학습 예제를 사용한다.
- **J:** 같은 C에서 직접 공동 CE. 환자당 두 소견을 하나의 J-short 예제로 학습한다.
- **A:** iter_046의 `A_U_e5`, threshold0.8. `results/iter_046/train/U/weights_e5.pth`, SHA256 `b9c2bccd04dde8b7445aa5f60e082a0c93f1f2412af8a583a4ca5ee207c8718a`다. 재학습·threshold 재선택을 하지 않는다.

E/J는 동일 환자·annotation·초기 상태·update 수를 공유한다. E는 영상과 prompt를 더 많이 forward하고 J는 더 긴 sequence를 사용한다. 따라서 연산까지 동일하다고 주장하지 않는다. A에도 원본 영상과 각 문장 전체를 제공하고 batch 처리를 허용한다. 사전학습·해상도·학습 연산·선택량 차이를 보고한다.

새 branch 기반은 iter_006의 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`다. 반입 파일과 의존성은 JSON의 reuse_assets가 기준이다. 해당 파일들이 새 기반에 없음을 확인했다. 현재 branch에 있는 동일 파일을 새 기반에도 있다고 가정하지 않는다.

iter_040 학습기의 validation 경계 복구, iter_045/046 timing의 config·배타성·실패 처리 문제를 실제 사용할 경로에서만 고친다. `pg43_eval`은 순수 좌표 변환 helper만 사용하며 기존 평가 CLI·verify_import는 사용하지 않는다. rr47, MG 학습기, 과거 RSNA CLI는 정비 대상이 아니다.

# Proposed Experiment

## 1. 자료와 초기 상태 고정

`results/iter_043/data/manifest_private.json`의 T305/D24/V96과 iter_040 train manifest를 연결한다. T305는305명·610문장·765개 box다. D24는24명, V96은96명·192문장이다. 기존 환자·문장·GT를 재선택하지 않는다.

환자·study·영상·pixel 분리, manifest 및 원본 변환 연결을 확인한다. 과거 검증은 source·입력 불변성을 확인한 범위에서 재사용한다. 현재 학습·평가 이미지의 file/pixel hash를 검사하고 불일치하면 실행을 막는다. 보호 reserve는 열지 않는다.

D24는 선택 자료다. V96은 이미 여러 번 사용된 개발 비교이며 C 초기 checkpoint도 과거 개발 선택을 거쳤다. 새로운 독립 확인이라고 부르지 않는다.

## 2. 동작 확인

T305에서 기존 층을 포함하는8명과 긴 문장·최대 box 사례를 고정해 입력·target·CE·gradient·저장·재개를 검사한다. J target은 요청 순서대로 두 ID의 전체 GT box를 연결하고 각 ID 내부 정렬은 기존 규칙을 따른다. 빈 목록·중복 ID·좌표 경계·한 문장의 여러 box를 fixture로 검사한다.

E/J 모두 초기 adapter가 C와 동일해야 한다. base 동결, assistant JSON+EOS만의 학습, accumulation과 마지막 불완전 batch 정규화를 실제 모델에서 확인한다. overfit은 구현 검사일 뿐 일반화 근거가 아니다.

D8에서 공식 processor 입력, I/J parser, A의 기존 출력 회귀를 확인한다. 실제 checkpoint 중간-step 재개와 validation 직전·직후 중단을 시험한다. 기술 gate는 입력·수치·출처·재개의 정확성을 검사하며 낮은 grounding 점수 자체를 실행 무효로 처리하지 않는다.

## 3. 가능성 탐색과 한정 학습

E/J 두 trajectory를 seed17로 시작한다. 언어층 LoRA rank16/alpha32/dropout0.05, AdamW LR1e-5 상수, weight_decay0.01, betas0.9/0.999, eps1e-8, clip1을 사용한다. C에서 adapter만 초기화하고 optimizer는 두 조건에서 동일하게 새로 만든다.

환자 순서와 effective batch8환자를 공유한다. E는 batch당 최대16개 독립 sequence, J는8개 공동 sequence다. 각 조건의 CE는 해당 logical batch 전체 assistant token 합으로 정규화한다. JSON 구조 token 수 차이를 기록한다. 환자별 각 annotation은 epoch마다 한 번 노출된다. J의 AB/BA는 환자 hash와 epoch parity로 균형화하며 정답 ID는 바꾸지 않는다.

기본5 epoch, trajectory당195 updates다. epoch2·5에만 D24의 I_A/I_B/J_AB/J_BA를 생성한다. epoch마다 전체 validation을 하지 않는다. 초기 C의 같은 D24 조건은 호환되는 출력이 없을 때만 최대96건 생성한다.

D24에서 E_I 또는 J_J의 epoch5−epoch2 F1@0.3이0.02 이상이거나, 각 조건의 해당 형식 teacher-forced CE가5% 이상 감소하면 두 trajectory를 함께8 epoch까지 한 번 연장한다. CE만으로 유망성을 선언하지 않으며 연장은 수렴 부족의 한정 확인이다. 조건이 없으면5 epoch에서 끝낸다.

공통 epoch는 후보2/5/(실행했다면8) 중 D24의 `(E_I F1@0.3 + J_J F1@0.3)/2`가 가장 높은 시점으로 선택한다. J_J는 AB/BA 평균이다. 동률은 두 점수의 최솟값이 큰 시점, 그다음 이른 epoch다. E/J를 서로 다른 epoch에서 골라 학습량을 바꾸지 않는다.

## 4. 고정 개발 비교

선택을 잠근 뒤 E/J 각각 V96의 I_A/I_B/J_AB/J_BA를 생성한다. 총768요청이다. C의 기존384요청과 A의 기존192문장 출력은 원 request·protocol·adapter·영상·parser 연결을 검증해 재사용한다. 누락 자산을 임의 다른 checkpoint나 조건으로 대체하지 않는다.

학습 효과·형식 유효성·실용 비교를 모두 보고한다. 선택된 endpoint뿐 아니라 D24 학습 추세와 마지막 checkpoint 추세도 남긴다. endpoint 선택이 수렴 증명이 되지는 않는다.

## 5. 비용 비교

E의 독립 처리, J의 공동 처리, A의 문장별 처리에 대해6개 block을 측정한다. 각 block은 같은 V96 환자 전체를 사용한다. 세 시스템의 실행 순서는 가능한6개 순열을 한 번씩 사용한다. J는 block별 AB/BA를3회씩 고정 배정한다. 시스템끼리는 동시에 실행하지 않는다.

block당 E192·J96·A192개 forward/generation 항목, 전체2,880건이다. 독립 결과는 두 문장을 결합해 환자 결과가 완성되는 시점까지 측정한다. 모든 시스템에서 입력 읽기·전처리·출력 parsing·원본 좌표 변환·환자 결과 결합을 포함한다. warm-up과 loading은 별도 비용이다.

GPU별 요청 처리 구간의 합집합을 합한 device-seconds, barrier 이후 전체 workload wall에 따른 환자/분, 환자 첫 dispatch부터 결과 완성까지의 p95 service latency를 저장한다. 여러 worker의 겹친 시간을 단순 합산하지 않는다. loading 포함 비용과 재개 attempt 전체 비용도 별도 장부에 보존한다.

비용 CI는 block별 paired log-ratio의 t(5) 95% CI다. 환자 latency bootstrap을 device 시간 CI로 대체하지 않는다. 기술 실패 block은 원본을 보존하고 전체 세 시스템을 새 attempt에서 재측정한다. 느리다는 이유로 제외하지 않는다. timing 출력은 고정 정확도 출력과 비교하며 불일치를 무시하지 않는다.

## 6. GPU·시간·확대 경계

실행 직전 nvidia-smi로 허용 GPU와 실제 여유를 확인한다. CUDA_VISIBLE_DEVICES의 논리/물리 대응을 기록한다. 두 학습 trajectory를 두 GPU에 병렬 배치한다. 학습 microbatch는1과2 중 유망 구성을 먼저 측정하고 실제 처리량으로 선택한다. 과거 allocated9.783GiB는 reserved·전체 점유의 보장이 아니다.

추론은 GPU당1/2 worker를 D 입력에서 비교한다. MG는 기존 w2b4와 batch 확대를 우선 비교하되 동일 조건의 최근 실측을 재사용할 수 있으면 이유를 남긴다. worker당 실제 peak와 최소2GiB 여유, 다른 점유를 포함해 안전한 구성을 선택한다. token/box 정합성·긴 출력 지연·OOM·CPU/RAM/I/O 경합을 함께 본다. 구성은 V96 결과 전에 잠근다.

과거 step 실측을 단순 적용하면 두5-epoch trajectory는 약1.3–1.4 GPU-hours,8-epoch는 약2.0–2.2 GPU-hours다. 새 J의 실제 시간은 동작 확인에서 다시 산출한다. 생성·timing·loading을 포함한 전체 참고 wall은 약2–4시간이며 임의 중단 상한이 아니다.

checkpoint에는 adapter·optimizer·RNG·data position·precision·source/config digest를 저장한다. epoch 경계와 중간 step에 저장하고 validation 이후 RNG를 복원한다. 원자적 request claim과 worker별 파일을 사용한다. 실행 중인 다른 작업과 claim은 건드리지 않는다.

이번은 가능성 탐색의 종료점이다. 다중 seed·추가 환자·새 LR·새 방법·독립 확인으로 자동 확대하지 않는다.

# Implementation Tasks for Claude

1. 세 출처의 반입 blob과 의존성, C/A checkpoint 및 기존 manifest·출력 연결을 확인한다. 새 결과는 iter_048 경로에만 쓴다.
2. pg40_train의 CE·checkpoint 경로를 재사용해 E/J 입력 구성을 추가한다. 기존 RSNA CLI와 문장 대조 loss를 호출하지 않는다. 동일 annotation·step·초기 상태 검사를 자동화한다.
3. 학습2/5/(8), D24 선택, V96 진입을 하나의 고정 protocol과 decision digest로 연결한다. completion 존재만으로 학습·평가를 건너뛰지 않는다.
4. pg43_run으로 정확도 생성을 수행한다. 환자×모델×조건 행렬을 강제하고 공식 processor tensor·cap·adapter 연결을 검사한다.
5. 기존 timing 구현을 새 adapter/request에 연결한다. MG launcher의 config·동시 실행·barrier 실패 처리와 C timing의 재개 보호를 보완한다. 기존 source를 수정하면 원본과 amendment hash를 연결한다.
6. 평가와 독립 verifier에서 label·좌표·matching·모든 metric·CI·판정 분기를 검사한다. 불일치 시스템을 검증 대상에서 제외하지 않는다.
7. 실제 중단·재개와 변조·중복·누락·wrong config·child 실패 fixture를 수행한다. 최종 raw/report/selection/training/timing/source/verifier digest를 묶어 마지막에 completion을 확정한다.
8. 계획 대비 실제 학습·요청·비용·미완료와 판정 범위를 보고한다. 학습·평가 프로세스 종료와 결과 완결성을 확인하기 전에 최종 보고서를 내지 않는다.

# Evaluation (성공/실패 기준 포함)

## 지표와 불확실성

기존 문장별 최대 일대일 matching의 F1@0.3/0.5, recall, FP/문장, invalid·EOS를 사용한다. 환자 점수는 두 문장 평균이며 공동 점수 J_J/E_J는 AB/BA 평균이다. 순서별 결과도 별도로 남긴다. GT·metric을 변경하지 않는다.

환자 paired bootstrap10,000회, seed4801로 같은 환자의 모든 조건을 함께 resample한다. 주비교 두 개에는 각각97.5% CI를 사용한다.

- 공동 학습의 추가 회복: `J_J − E_J`.
- 공동 손실의 감소: `(E_I − E_J) − (J_I − J_J)`.

valid 공통 subset은 보조 분석이며 전체 분모의 주결과를 대체하지 않는다. 형식 개선만으로 box 대응 개선을 주장하지 않는다.

## 학습 형식 설명

두 주비교가 각각0.10 이상이고97.5% CI 하한>0이며, `J_I−E_I`의95% CI 하한≥−0.03일 때 큰 손실의 선택적 회복을 지지한다. 0.10은 기존 약0.20 손실의 절반 수준을 설명할 개입을 구분하기 위한 이번 기준이다.

직접 공동 SFT의 충분성은 J_AB와 J_BA 각각의 E_I 대비 F1@0.3 차이97.5% CI 하한≥−0.03, F1@0.5 차이95% CI 하한≥−0.03, FP 차이95% CI 상한≤0.10을 모두 요구한다. 3 pp 허용 손실은 기존 독립 능력을 거의 유지한다는 사용 목적의 기준이며 임상 안전 기준이 아니다.

반대로 `J_I−J_J`가0.05 이상이고95% CI 하한>0이면 현재 학습 이후의 잔여 공동 손실로 기록한다. 계속 상승하는 학습 추세가 있으면 수렴한 baseline의 한계로 표현하지 않는다.

## 실용 가치와 다음 투자

모듈형 대비 필요한 정확도 이점은 해당 VLM 운영점의 A 대비 F1@0.3 차이≥0.05와97.5% CI 하한>0이다. 동시에 F1@0.5 차이95% CI 하한≥−0.03, FP 차이95% CI 상한≤0.10을 요구한다. 이는 빠른 A에 비해 추가 VLM 비용을 검토할 최소 개발 근거이며 보편적인 효용 함수는 아니다.

공동 처리의 비용 기회는 J/E의 device-seconds 비율95% CI 상한≤0.80, throughput 비율95% CI 하한≥1.25, p95 latency 비율95% CI 상한≤1.20을 모두 요구한다. A와의 실제 비용 비율도 같은 block에서 보고한다. J가 E보다 싸다는 사실을 A보다 싸다는 주장으로 바꾸지 않는다.

결과별 행동은 다음과 같다.

- **직접 SFT로 회복·보존:** 학습 형식 설명을 보존하고 별도 공동 loss 투자는 종료한다. J가 A 대비 정확도 이점과 비용 기회까지 충족할 때만 후속 독립 확인·기여 가능성을 검토한다. 직접 SFT 자체는 신규 방법이 아니다.
- **잔여 공동 손실:** E_I가 A 대비 필요한 정확도 이점을 보이고 J의 비용 기회도 확인된 경우에만, 그 능력을 공동 처리에서 보존하는 최소 방법 pilot의 가치를 다음 리뷰에서 판단한다. 구체적 개입·신규성·method gate는 별도 계획 사항이다.
- **MG 대비 필요한 이점 미확보:** 현재 두 양성 문장 공동 grounding의 추가 방법 투자를 보류한다. 충분성이 입증된 경우와 CI·수렴 부족인 경우를 구분한다.
- **불확정:** 사전8-epoch 보완 이후 표본·seed·prompt·timing을 늘리지 않는다. 관찰을 보존하고 이 비교를 종료한다.
- **실행 결함:** 원 결과를 보존하고 현재 결론을 제한한다. 기존 출력의 한정 재채점으로 가능한 수정과 새로운 GPU 실행이 필요한 수정을 구분한다. 자동으로 다음 복구 반복이나 새 진단을 붙이지 않는다.

# Risks / Checks

- 공동 SFT는 prompt·직렬화·영상 반복을 함께 바꾼다. 하나의 내부 원인을 완전히 분리한 실험으로 표현하지 않는다.
- T305, 단일 seed, 두 양성 문장에 한정된다. 부재 거부·보고서 생성·임상 reasoning·외부 일반화는 미검증이다.
- D24와 V96은 개발 자료다. 보호 reserve와 VinDr는 사용하지 않는다.
- 적응 MG의5-query 구조 제한과 기존 checkpoint의 학습 출처를 그대로 공개하고 어려운 사례를 제외하지 않는다.
- 독립 처리 baseline은 두 GPU와 batch를 사용할 수 있다. 공동 처리의 비용 이점을 만들기 위해 비교군을 직렬·저배치로 강제하지 않는다.
- 교차 판본 helper·새 mask·긴 J sequence는 실제 회귀 검사 대상이다. 과거 전체 스냅샷을 승인된 것으로 취급하지 않는다.
- iter_041 비용 blocker는 원 기록에 남긴다. 이번 신규 block 측정은 별도 근거이며 과거 단회 비용을 소급 확증하지 않는다.

## 대규모 GPU 필요 후보

여러 기관의 영상–문장–영역 자료로 독립·공동·부재 조건을 함께 학습하고 vision encoder까지 적응하는 방향을 장기 후보로 보존한다. 더 큰 activation·optimizer 메모리와 다중 seed 비용이 필요할 수 있다. 현재 강한 단순 대조 이후의 잔여 가치가 확인되기 전에는 실행하거나 새로운 기여로 가정하지 않는다.

# 계획의 근거 (GPT 조사 노트)

### 확인한 사실

- GOAL, GPT_USAGE_POLICY, REPORTING_STYLE, INDEX, 관련 LIMITATIONS·CODE_ASSETS와 iter_029·040·041·046·047의 원 계획·리뷰 및 관련 code_assets를 읽었다. iter_047의 이전 조사 노트와 legacy 문서의 중대 정정도 확인했다.
- iter_041의 정확도 손실은 독립 재계산된 유효 관찰이다. C의 I/AB/BA F1@0.3은 0.577951/0.381076/0.354167이다. 모든 정확도 출력이 valid·EOS였으므로 단순 parser·truncation 설명은 약해졌다. 공동 직접 SFT는 미실행이다.
- iter_046의 저장 report에서 A@sel F1@0.3=0.594444, F1@0.5=0.394097을 확인했다. 최종 선택은 U epoch5, threshold0.8이며 checkpoint는 results/iter_046/train/U/weights_e5.pth, SHA256 b9c2bccd04dde8b7445aa5f60e082a0c93f1f2412af8a583a4ca5ee207c8718a다. 이번 계획 단계에서 원시 출력 전체를 재채점한 것은 아니다.
- iter_047 E96은 자료 부족과 oracle 실패 때문에 미실행이다. 해당 실패를 공동 grounding이나 전체 교정 능력의 기각으로 해석하지 않는다.
- iter_029에서는 entropy AUROC0.8225로 단순 위험 baseline이 강했다. 같은 RSNA confidence 질문으로 이동할 새로운 실패 조건은 이번 조사에서 확보하지 못했다.
- 현재 HEAD는 5d34c5cd69de08603b7ad02fbb43a78691c6e7c7이며 status와 diff는 비어 있었다. 핵심 11개 파일이 iter_043 blob과 동일함을 확인했다. 선택한 반입 파일은 실제 Git object에 존재하며 iter_006 기반과 경로 충돌이 없다. 학습 및 timing의 import 의존성도 확인했다.
- 기존 C의 초기 후보는 results/iter_040/train2/C_s17/epoch_03/adapter.pt다. 기존 C 학습 설정은 rank16/alpha32/dropout0.05, LR1e-5, effective batch8환자다. 실제 로그의 B/C 평균 step 시간은11.752/12.579초이고 최대 allocated 메모리는 약9.783GiB였다. 이는 새 공동 학습의 실측값이 아니다.

### 선택의 의미

공동 직접 SFT는 새 방법이 아니라 학습 분포 불일치라는 경쟁 설명을 검증하는 강한 단순 대조다. 문장별 MG 출력을 합치는 방식도 공동 결과를 제공할 수 있으므로, 단일 호출 자체를 VLM의 고유 효용으로 삼지 않는다. 기존 비용 CI 결함의 재분석만으로는 학습 개입의 효과를 알 수 없고, 새 질문의 자료·정답 구축보다 이번 대조의 실행 범위가 구체적이다. 다만 교정 후보가 막혔다는 사실만으로 재개하는 것은 아니며, 적응 MG 대비 이득과 종료 행동을 이번 계획의 필수 판정으로 둔다.

### 선행 확인

[MedGrounder 원논문](https://arxiv.org/html/2512.01085v1)과 [공식 저장소](https://github.com/aehrc/MedGrounder)를 확인했다. 문장별 zero-or-more grounding과 보고서 생성기와의 모듈형 결합이 이미 제안돼 있다. 따라서 공동 출력·box 결합 자체는 차별성이 아니다. 기준 모델의 버전은 [MedGemma 1.5 Technical Report](https://arxiv.org/abs/2604.05081)와 기존 고정 revision을 따른다. 이번 조회는 신규성 확정이나 사용자 논문 추천이 아니다.

### 보존과 미확인

iter_041 원 plan SHA256은 e9786ff168532ae432a03be8aa9d64e84308bc69ff08d8cd03e3002fd28eb87f, iter_046은 0cbe18162cc5c1b81a75601ba4ac5d01cda0bb8050f14f77a50f841cead3baf6다. 이번은 원 계획의 수정 재실행이 아니라 별도 학습 개입이다. 과거 blocker·판정·출력은 유지한다. 새 학습 메모리·처리량, 현재 GPU 가용성, 교차 판본 helper 호환성은 구현 단계의 실제 검사 대상으로 남는다. 파일 생성·수정이나 실험은 수행하지 않았다.
