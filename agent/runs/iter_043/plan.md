# 요약

- **이번에 할 일:** 직접 SFT의 문장 grounding 개선을 환자별 영상 기여와 문장 위치 prior로 분리한다.
- **필요한 이유:** V96의 192문장 중 91개가 학습 문장과 겹친다. 높은 점수만으로 영상 정보 사용 증가를 확정할 수 없다.
- **확인할 기준:** 문장 retrieval의 경쟁력, 동일 문장 환자쌍의 영상 교환 반응, M0/C 차이를 함께 본다.
- **주의·다음:** 개발96명·고정21쌍으로 종료한다. 중요한 잔여 문제가 확인되면 최소 방법 pilot 후보를 선정하고, 불확정이면 추가 진단·학습을 보류한다.

# Current Understanding

iter_040에서 동일 I-short의 F1@0.3은 M0 0.09844에서 C 0.57795로 개선됐다. C의 F1@0.5는 0.29115다. 문장 대조의 추가 효과, baseline 수렴, 모듈형 대비 가치와 독립 재현은 미확인이다.

iter_041의 공동 요청 손실과 iter_042의 grounding 부재 거부 문제는 유효한 관찰이다. 그러나 공동 요청의 비용 gate는 미완결이고 presence gate 이후 중요한 잔여 문제도 입증되지 않았다. 해당 방법 투자는 보류한다.

이번은 새로운 진단 질문이다. 과거 계획의 수정·복구나 판정 기준 변경이 아니다. 유지할 것은 GOAL, MedGemma 1.5, 기존 결과·checkpoint·분할, VinDr 승인 대기, continuation 투자 종료와 H192/F120/test/MRI reserve 보존이다. 기존 SFT 재학습과 새 loss는 실행하지 않는다.

# Strategy Check / 연구 방향 판단

중요한 능력은 같은 소견 문장이 성립하더라도 환자마다 다른 영상 위치를 올바르게 반환하는 것이다. 문장에 흔히 연결되는 위치를 잘 출력하는 것과 환자의 실제 영역을 구별하는 것은 다른 능력이다.

현재 방법 개선은 직전 세 반복의 보류 근거 때문에 우선순위가 낮다. 실제 문장 조건부 모듈형 비교는 가치가 높지만 MedGrounder의 공식 실행 경로가 현 환경에서 준비되지 않았다. 이 환경 정비만으로 반복을 소비하지 않는다. 새 보고서·시간 변화 과제는 정답과 baseline 확보 비용이 크고 현재 사용자 지시의 보호 경계를 유지해야 한다.

이번 자료 확인에서 정규화된 학습 문장 일치가 91/192였고, 원문 동일 문장의 환자 비중복 21쌍을 구성할 수 있었다. 이는 문장 prior와 영상 기여를 분리할 구체적인 새 근거다. 따라서 한정된 원인·능력 진단을 선택한다. 낮은 GPU 비용 자체가 선택 이유는 아니다.

`language-conditioned-grounding` track을 유지한다. iter_038 준비, iter_039 진단, iter_040 방법 pilot, iter_041·042 진단을 연결한다. 해결된 질문은 직접 SFT의 양성 grounding 개선, 공동 요청 손실과 단순 presence gate의 작동 범위다. 남은 핵심은 직접 SFT의 개선 중 환자별 영상 구별이 차지하는 부분이다.

과거 약4.21시간 생성 wall, 약2.54 GPU-hours 학습, 일부 큐 약1.123 GPU-hours 및 iter_042 약33.9분 launcher wall은 포함 범위가 달라 단순 합산하지 않는다. 여러 준비·진단을 수행한 기회비용을 반영해 이번 비교 이후 같은 질문을 자동 확대하지 않는다.

가장 가까운 선행은 MedGrounder의 문장별 grounding과 의료 VLM의 image-intervention audit다. 영상 교환·text-only 비교 자체는 새로운 기여가 아니다. 현재 부족한 것은 동일 문장 조건에서 SFT가 환자별 위치 차이를 얼마나 반영하는지에 대한 실제 출력 근거다.

# Hypothesis

**H_prior:** 직접 SFT의 높은 문장 grounding 점수 일부는 문장별 위치 prior로 설명되며, 문장이 같은 환자들의 실제 위치 차이를 반영하는 데 중요한 잔여 문제가 있을 수 있다.

**경쟁 설명:** C가 실제 시각 정보를 활용해 위치를 개선했거나, 단순 좌표 형식 적응이 주효했거나, 관찰된 문장 반복과 무관하게 공간적으로 고정된 소견이 많은 자료 특성으로 설명될 수 있다.

문장 중복은 환자 누수의 증거가 아니다. text-only의 실패도 이미지 활용의 증명은 아니다. 세 비교를 함께 해석한다.

1. 실제 영상 C 대 train-only 문장 retrieval: 간단한 위치 prior의 설명 범위.
2. 실제 영상 대 text-only의 M0/C 차이: 영상 입력 제거에 대한 행동 변화.
3. 원문 동일 문장 환자쌍의 영상 교환: 해당 문장이 양쪽 영상에서 실제로 성립할 때 환자별 위치 변화에 대한 반응.

# Limitation Evidence / Correct Usage Checks

연결하는 한계는 `padchest-sentence-grounding-and-joint-retention`이다. 그중 정상 입력에서의 문장별 grounding과 직접 SFT 성과를 출발점으로 사용한다. 기존 observed 상태를 영상 무사용 또는 shortcut 한계의 검증 상태로 옮기지 않는다. 이번 역할은 diagnostic, method_stage=none이다.

iter_039·040·042의 유효한 리뷰, 공식 template와 값 보존 전처리 검사를 동일 revision·소스·입력 경로에서 재사용한다. 기준 모델 revision은 `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`다. dtype, processor, template, package, adapter digest를 다시 연결한다.

C는 `results/iter_040/train2/C_s17/epoch_03`을 고정한다. protocol의 adapter digest와 파일 SHA256은 research_notes에 기록했다. M0에서는 adapter가 비활성임을 검사한다.

영상 교환은 병변 제거 실험이 아니다. 원문이 완전히 같은 양성 문장이 양쪽 영상에 주석된 경우만 사용한다. 교환 영상에 대해 원래 환자의 GT를 정답이라고 주장하지 않는다. 실제 donor GT에 대한 성능과 recipient GT와의 우연한 일치를 별도로 계산한다.

# Contribution Path / Baselines / Reuse

## 비교군

- **M0, C 실제 영상:** 기존 I-short 출력과 protocol을 재사용한다. C의 iter_041 Icost 재실행은 기존 출력과 token이 같았으므로 출처 검증 후 사용할 수 있다. 모델별 원본 경로를 새 manifest에 고정한다.
- **문장 retrieval P:** T305의 610문장과 공식 전체 box 집합만 사용한다. 평가 labels·locations·GT는 검색 특징으로 사용하지 않는다.
- **M0/C text-only:** 동일 I-short 텍스트를 공식 text-only 입력으로 전달한다. 영상 token·pixel·cached feature는 없다. 이 조건은 modality ablation이며 별도 학습된 최선의 text-only baseline이 아니다.
- **동일 문장 영상 교환:** 실제 영상만 바꾸고 해당 recipient의 prompt·ID·생성 조건을 유지한다.
- **GT 교차 기준:** 두 환자의 GT가 얼마나 구별되는지 보여주는 진단용 기준이다. 실용 모델이나 달성 가능한 성능 상한으로 부르지 않는다.

retrieval은 word unigram/bigram과 character 3–5 gram TF-IDF, 각각 k=1/5의 네 설정만 비교한다. IDF와 vocabulary는 T305에서만 만든다. k=1은 최상위 문장의 전체 box 집합, k=5는 이웃의 전체 box 집합 중 평균 pairwise set-F1@0.3이 가장 높은 medoid를 반환한다. 빈 similarity와 동률은 고정 hash 순서로 처리한다. D24의 환자 평균 F1@0.3으로 선택하고 동률은 k=1, word 설정 순으로 정한다. 이후 V96을 보고 설정을 바꾸지 않는다. 새 package 설치 없이 기존 환경에서 구현한다.

retrieval box는 원본 normalized 좌표로 저장하고 대상 영상의 알려진 크기·padding으로 변환한다. 모델에 제공되지 않는 GT나 소견 metadata는 입력으로 사용하지 않는다. 같은 문장은 같은 normalized box 집합을 반환하므로 환자별 영역 구별에 대한 단순 기준이 된다.

MedGrounder는 가까운 시각적 모듈형 baseline이지만 이번에 실행하지 않는다. [공식 구현](https://github.com/aehrc/MedGrounder)과 [논문](https://arxiv.org/html/2512.01085v1)을 출처로 기록한다. 현 환경 blocker를 성능 열세로 해석하지 않으며, PadChest 적응 공개 checkpoint를 비누수 비교군으로 사용하지 않는다. [의료 VLM 영상 개입 연구](https://arxiv.org/html/2606.17710v1)와 구별되는 새 방법은 아직 없다.

## 코드 재사용

새 브랜치는 승인 iter_006을 기반으로 하고 reuse_assets의 12개 파일을 반입한다. 원본 SHA와 현재 파일 일치는 계획 단계에서 확인했다. pg39_data/spec의 제한 승인과 pg41_verify의 순수 좌표·matching 기능을 재사용한다.

pg41_run은 text-only의 명시적 입력 규약, 현재 요청과 protocol 일치, GPU 여유 순 배정과 worker별 메모리 여유를 보완한다. pg41_verify CLI나 tolerant parser를 무검증으로 호출하지 않는다. 기존 parser의 의미를 유지하고 새 평가기의 독립 수치 검사에 순수 함수를 활용한다. 과거 비용 판정기·학습기·사용하지 않는 build/driver는 반입하거나 정비하지 않는다.

# Proposed Experiment

## 1. 동작 확인

새 결과는 `results/iter_043/`에만 기록한다. 원본 metadata·T305/D24/V96·selection lock·기존 출력·adapter·소스와 새 설정을 잠근다. H192/F120/test/MRI reserve는 입력 목록에서 차단한다.

T305/D24/V96의 환자·study·영상 비중복과 현재 영상 hash를 확인한다. text-only의 의미는 이미지 없이 같은 prompt를 사용하는 것이다. 임의의 검은 영상이나 위치 설명 추가로 바꾸지 않는다.

D24에서 기존 stratum을 반영한 hash 순서 D8을 고정한다. 각 환자의 두 문장에 대해 M0/C × 실제 영상/text-only를 실행해 64요청을 확인한다. C의 32요청을 2-worker와 4-worker에서 공통 실행하므로 추가 32요청이 발생한다. 실제 영상의 기존 출력 재현, text-only tensor에서 영상 경로 부재, parser·ID·EOS·길이 ladder, adapter 연결을 검증한다.

환자와 donor가 같을 때 원래 요청과 동일한 입력·출력이 되는 교환 경로 회귀검사를 포함한다. 서로 다른 영상의 raw/padded hash가 실제로 바뀌는지도 검사한다. GT fixture로 좌표 왕복·집합 matching·교차 점수의 부호를 검증한다.

동작 확인은 성능 후보 선택 단계가 아니다. prompt 변경은 하지 않는다. 명백한 구현 오류를 수정하면 protocol 버전을 새로 만들고 실패 산출물을 보존한다.

## 2. 가능성 탐색

retrieval 네 설정을 T305→D24에서 비교하고 하나를 잠근다. 학습은 없고 annotation budget은 C와 같은 T305다. 선택에 사용한 D24는 개발 자료로 명시한다.

V96 192개 문장의 exact train match 여부는 사전 기술 층으로 기록한다. 정규화 규칙은 lower-case와 공백 정리뿐이다. 전체 V96를 주분석으로 유지하며 일치/비일치 집단 중 유리한 집단을 선택하지 않는다.

환자쌍은 원문 문자열이 완전히 같은 문장끼리만 만든다. 각 가능한 edge의 두 endpoint `(PatientID, qID)`를 정렬하고 `sha256('4301|'+sentence+'|'+str(endpoint_a)+'|'+str(endpoint_b))` 순으로 처리한다. 이미 사용한 환자가 있는 edge는 건너뛴다. 계획 시 확인한 결과는 21쌍·42명·17문장 cluster다. count나 원본 hash가 다르면 자료 연결을 확인한 뒤 진행하며 임의 표본 대체는 하지 않는다.

GT만으로 확인한 평균 `1−cross-F1`은 IoU0.3에서 0.30952, IoU0.5에서 0.54762다. 이 값으로 출력이 좋은 쌍을 선택하지 않는다. 21쌍 전체를 유지한다.

## 3. 고정 본비교

동작·출처 gate 통과 후 같은 호출 안에서 수행한다. 새로운 대규모 확대가 아니다.

- 실제 영상 M0/C의 V96 384요청은 재사용한다.
- V96 text-only는 M0/C × 192문장으로 384요청이다.
- 21쌍 양방향 교환은 M0/C × 42질의로 84요청이다.
- 신규 본생성 총 468요청, D 비교를 포함한 기본 총 564요청이다.

greedy 생성, 기존 I-short, caps 1000/2000/4000을 유지한다. 길이 재시도·비EOS·invalid를 모두 보존하고 비용을 별도 집계한다. 새 epoch·training seed·학습률 탐색은 없다.

## 4. 독립 확인과 종료

이번에는 독립 확인을 실행하지 않는다. V96은 기존 checkpoint 선택에 사용된 개발 자료이며 21쌍도 그 부분집합이다. 이번 결과로 validated 승격이나 외부 일반화를 자동 선언하지 않는다.

Evaluation에 따라 최소 방법 pilot 후보 또는 투자 보류를 결정하고 종료한다. H192·F120을 불확정 해소용으로 열지 않는다.

## 자원·시간·재개

실행 직전 nvidia-smi로 허용된 두 GPU의 실제 여유를 확인한다. 논리/물리 index 대응을 보존한다. D에서 총2-worker와 GPU당2개인 총4-worker를 비교하고 token 정합성·전체 처리량·p95 지연·peak VRAM·OOM·CPU/RAM/I/O 경합으로 선택한다.

과거 관측의 프로세스당 약8–10GB와 두 worker 약17.5–17.8GiB는 참고값이다. 실제 peak 합과 다른 프로세스 점유에 worker당 최소2GiB 여유를 더해 용량 이내인 구성만 사용한다. text-only와 긴 출력의 peak를 따로 확인한다. 여유 부족이나 실측 처리량 저하가 있으면 worker 수를 줄이고 근거를 기록한다.

과거 iter_042의 414요청 wall 약1,703초를 참고하면 이번 GPU 실행은 대략0.5–2시간으로 추정한다. text-only 속도와 출력 길이가 달라 D 실측으로 예상 시간을 갱신한다. 이는 시간 상한이 아니다.

request별 원자적 claim, worker별 JSONL, source/config digest와 completion 재검증을 유지한다. 중간 행은 별도 보존하고 재개한다. 평가 report·per-patient·pair 결과는 고유 임시 경로에서 작성하고 digest가 연결된 completion을 마지막에 확정한다. 기존 결과는 덮어쓰지 않는다.

# Implementation Tasks for Claude

1. 선별 반입 파일·의존성·원본 리뷰의 승인 범위를 확인하고 이번 실행 경로의 reuse_issues만 수정한다.
2. T305/D24/V96, 원시 출력과 adapter 출처를 연결한 iter_043 manifest를 만든다. 환자쌍 선정과 retrieval 설정을 출력 생성 전에 잠근다.
3. text-only modality를 runner에 명시하고 image·donor·recipient provenance를 분리한다. 모델 입력에는 문장과 해당 조건의 영상만 전달한다.
4. retrieval 네 설정의 D24 선택, 기존 출력 import 검증, D8 GPU 동작·처리량 검사를 수행한다.
5. 고정468건을 생성하고 요청 수·중복·누락·종료·재시도·자원을 기록한다.
6. 아래 지표와 CI를 계산하고 독립 좌표·matching 구현으로 재계산한다. prior·영상 교환·text-only를 하나의 인과 주장으로 합치지 않는다.
7. 양성/음성/불확정 종료 결정을 보고한다. 코드 완료, 유효 실험, 가설 지지, 신규 기여를 구분하고 원본과 실패 attempt를 보존한다.

# Evaluation (성공/실패 기준 포함)

## 지표

전체 V96는 기존 환자 평균 F1@0.3을 주지표로 유지하고 F1@0.5, FP/문장, empty, invalid, EOS를 함께 보고한다. M0/C/P를 같은 환자로 비교한다. text-only 차이는 별도 ablation 수치다.

동일 문장 쌍의 위치 구별은 F1@0.5를 주지표로 한다. 이는 전체 V96의 F1@0.3과 다른 질문이므로 두 수치를 직접 비교하지 않는다. 각 모델의 쌍 점수 B는 두 방향에서 `F1(원래 영상 출력, recipient GT)−F1(교환 영상 출력, recipient GT)`를 평균한 값이다. 교환 출력의 실제 donor GT F1도 반드시 보고한다. 높은 B가 단순 invalid 증가나 엉뚱한 출력으로 만들어진 경우 영상 구별 성공으로 해석하지 않는다.

출력은 실제 입력 영상의 affine을 역변환해 original normalized 좌표로 옮긴 뒤 두 환자의 normalized GT와 비교한다. clipping으로 오류를 감추지 않는다. 동일 영상 조건의 변환 전후 F1 불변성을 검사한다.

V96 비교는 환자 bootstrap 10,000회, 쌍 비교는 17개 동일 문장 cluster bootstrap 10,000회를 사용한다. 환자는 쌍 사이에 중복되지 않는다. seed는4302로 고정하고 두 방식의 표본 단위를 혼동하지 않는다. gate용 차이에는 97.5% CI를 사용한다. 개발 자료의 선택 편향은 CI로 해소되지 않는다.

## 최소 가치 기준

전체 F1@0.3의 허용 차이0.03은 C≈0.578에서 약5% 상대 차이에 해당한다. 단순 retrieval이 이 범위에 들어오는지 본다. 쌍별 F1@0.5의0.10은 GT 교차 구별 가능성0.548에 비해 작지만 환자별 구별 투자 판단에 의미 있는 차이로 둔다. 임상 허용 기준이 아니라 이번 연구 투자 기준이다.

text-only는 valid율이 실제 영상 조건보다5pp 이상 낮으면 성능 차이를 내용상 영상 기여로 해석하지 않는다. 그 조건의 실패는 그대로 보고하고 prompt를 고쳐 재시도하지 않는다.

## 양성: 환자별 구별 방법 pilot 후보

다음을 모두 충족해야 한다.

- 전체 V96에서 P−C의 F1@0.3 CI 하한이 −0.03 이상으로, train-only 문장 prior가 직접 SFT와 경쟁적이다.
- 21쌍의 C 실제 영상 F1@0.5가0.20 이상으로, 거의 전부 실패한 모델의 무반응만을 관찰한 경우가 아니다.
- C의 쌍 점수 B의 CI 상한이0.10 이하이고, GT 교차 구별 가능성의 CI 하한은0.20보다 크다.
- 교환 결과의 provenance·좌표·출력 길이·parser 검사에 결론을 막는 문제가 없다.

이 경우 단순 prior는 전체 점수를 설명하지만 환자별 위치 차이를 해결하지 못하고 C도 충분히 구별하지 못한다는 제한된 관찰이다. 다음 최소 pilot 후보는 동일 문장·다른 영상의 구별을 학습시키는 개입이다. 직접 추가 CE, 같은 어려운 쌍 sampling을 적용한 CE, 추가 구별 신호를 비교해야 한다. 이번 결과만으로 특정 loss의 신규성·성공·full 확대를 승인하지 않는다.

## 음성: prior 중심 설명 약화

C−P의 전체 F1@0.3 CI 하한이0.03보다 크고 C의 B CI 하한이0.10보다 크며 교환 출력이 실제 donor GT와 대응하면, 현재 직접 SFT는 단순 prior 이상의 영상 구별을 보였다고 판단한다. M0 대비 차이는 보조적으로 해석하고 일반적 내부 원인을 확정하지 않는다.

C를 보존하고 현재 shortcut 교정 방법 투자는 보류한다. 이 결과를 공동 요청·부재 거부 loss의 재개 근거로 사용하지 않는다. 실제 모듈형 비교 또는 외부 자료가 가능해질 때 사용할 자산으로 남긴다.

## 불확정·혼합 결과

어느 기준도 완결되지 않거나 F1과 donor 대응이 충돌하면 불확정이다. 21쌍·17cluster의 정밀도 한계를 보고하고 이 후보 투자를 보류한다. 추가 환자·문구·seed·text-only SFT·reserve 개방을 자동 실행하지 않는다. 유효한 작은 진단의 불확정을 모든 시각적 grounding 또는 경량 적응의 실패로 확대하지 않는다.

# Risks / Checks

- 91/192의 문장 일치는 정상적인 반복 서술일 수 있다. 환자·영상 leakage와 구분한다.
- 동일 문장 쌍은 흔한 소견에 치우치며 위치가 실제로 다른 쌍은 제한적이다. 전체 소견으로 일반화하지 않는다.
- text-only는 C의 학습 분포 밖이다. 이 조건의 invalid나 성능 하락만으로 이미지 사용을 증명하지 않는다.
- 영상 교환 후 recipient GT와의 낮은 일치만으로 성공을 선언하지 않는다. donor GT 성능과 함께 본다.
- GT 교차 기준은 영상에서 구별 가능한 모든 정보나 임상 annotation 완결성의 증명이 아니다.
- 문장 retrieval은 강한 시각적 모듈형 비교군이 아니다. MedGrounder 미실행과 서로 다른 pretraining budget을 숨기지 않는다.
- 성능·통계·출처 검사는 full GPT 리뷰에서 독립 재계산한다. token 일치 검사를 실제4-worker 실행 또는 중단 복구 전체 검증으로 확대하지 않는다.
- VinDr 승인 통지 전 다운로드·외부 평가를 하지 않는다. 기존 private 원문을 공개 산출물에 포함하지 않는다.

## 대규모 GPU 필요 후보

환자별 영상 구별의 잔여 문제가 확인되고 경량 개입과 강한 직접 CE 이후에도 유지된다면, 동일 문장·다기관·다양한 위치의 영상쌍으로 vision encoder와 언어층을 공동 post-training하는 후보를 보존한다. 고해상도 다기관 학습에는 현재 두 GPU보다 큰 자원이 필요할 수 있다. 이번 진단은 그 필요성이나 신규성을 증명하지 않는다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 사실

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/REPORTING_STYLE.md`, 관련 LIMITATIONS·CODE_ASSETS 항목과 iter_037–042의 관련 plan/review 원문을 확인했다. iter_040·042의 review.json은 valid_experiment=true, blocking_issues=[]다. iter_041의 비용 판정 blocker는 정확도 관찰과 구분한다.
- iter_040의 직접 SFT C는 V96에서 F1@0.3=0.577951, F1@0.5=0.29115다. 문장 대조 M의 C 대비 차이는 −0.005208이었다. 영상 정보 사용 증가라는 내부 설명은 해당 리뷰에서도 미확인으로 남았다.
- 출력이나 성능을 새로 계산하지 않고 기존 manifest의 문장 구조를 확인했다. 소문자화·앞뒤/연속 공백 정규화 기준으로 V96 192문장 중 91문장이 T305에 정확히 존재한다. V96 내부에는 반복 문장 25종, 해당 질의 69건이 있다. 이는 환자 누수가 아니라 언어 내용의 반복이다.
- 원문이 완전히 같은 문장에 대해 seed4301의 hash 순서로 edge를 정렬하고 환자를 중복 사용하지 않는 greedy pairing을 적용하면 21쌍·42명·17문장 cluster가 남는다. 출력은 선택에 사용하지 않았다. 원본 normalized GT 집합의 교차 F1으로 자료의 구별 가능성만 점검했으며 평균 1−cross-F1은 IoU0.3에서 0.30952, IoU0.5에서 0.54762다. 차이가 0보다 큰 쌍은 각각 7개·12개다. 이 제한 때문에 전체 V96과 쌍 분석을 구분하고 불확정 자동 확대를 금지한다.
- 현재 research HEAD는 `e7ee15464cf404a44a877997661b9f50dd8c3096`이고 status/diff는 깨끗했다. 선별 반입할 12개 파일의 blob이 현재 파일과 모두 같았다. 승인 기반 iter_006의 SHA는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`다.
- C는 `results/iter_040/train2/C_s17/epoch_03`이며 protocol의 adapter digest는 `419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8`, adapter 파일 SHA256은 `85a2512d8215caa2d20a544a7de082b1d248ae16f4df276b45a68a2d0e522158`이다.

## 선행연구와 대안 판단

[MedGrounder 논문](https://arxiv.org/html/2512.01085v1)의 소견별 분석은 해부학적 위치가 일정한 소견과 위치 변동이 큰 소견을 구분한다. 이 미확인 세부 사항을 이번에 확인했다. 문장 grounding 전체를 새 과제로 주장할 수 없으며, 환자별 위치 구별을 직접 측정할 이유가 된다. [공식 저장소](https://github.com/aehrc/MedGrounder)는 Chest ImaGenome pretrain과 PadChest 적응 checkpoint를 구분한다. 기존 feasibility 기록의 환경 blocker를 해소한 새 근거는 없다. 이번에는 설치·환경 혼합·후처리 재구현을 계획하지 않는다.

[Vision-language models for chest radiography do not always need the image](https://arxiv.org/html/2606.17710v1)는 의료 VLM의 영상 교환·text-only 대조를 이미 다룬다. 따라서 영상 개입이나 prior 관찰 자체는 novelty가 아니다. 이번 진단은 동일 문장이 실제로 성립하는 두 영상의 좌표 출력과 직접 SFT 전후 변화에 한정한다. 영역 제거 후 정상이라는 잘못된 정답은 만들지 않는다.

현재 방법 개선은 iter_040–042에서 자동 연장 근거가 부족하다. 실제 MedGrounder 비교는 환경 blocker가 있고, 새 보고서·시간 변화 과제는 정답·권한·강한 baseline 준비 비용이 더 크다. 기존 성과의 핵심 해석을 바꾸는 제한된 영상 기여 진단을 선택한다. 문장 prior가 경쟁력 있다는 사실만으로 새 방법을 시작하지 않고, 환자 구별 과제의 중요한 잔여 문제까지 요구한다.

## 의미와 한계

새 model output·학습·파일 생성은 하지 않았다. 문장 반복과 GT 구별 가능성은 자료 관찰이며 모델 결함 근거가 아니다. 이번 실험도 개발 자료·단일 SFT seed로 한정한다. 독립 일반화와 신규 contribution은 별도 판단이다. 인용 논문은 조사 근거이며 사용자 논문 추천으로 등록하지 않는다.
